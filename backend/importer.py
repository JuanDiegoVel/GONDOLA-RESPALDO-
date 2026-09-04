"""Importador: de los .jsonl/.json del pipeline a PostgreSQL. Responsable: Persona 7.

QUE HACE
--------
Lee, para UN video ya procesado:

    data/output/<video_id>.interact.jsonl   -- eventos completos (Personas 2-5)
    data/output/<video_id>.metrics.json     -- agregados por zona (Persona 6)
    data/zones/<video_id>.json              -- calibracion de camara (Persona 4)

y los inserta en las tablas de `backend/database/schema.sql`.

POR QUE SE REUTILIZA gondola.contract EN VEZ DE REESCRIBIRLO
--------------------------------------------------------------
`Event` ya valida la forma exacta de cada linea del .jsonl (con
`extra="forbid"`, los mismos rangos que la base de datos). Si un archivo
viene mal formado, la validacion lo detecta aqui, en la importacion, con el
numero de linea exacto, y no como un INSERT fallido a medias.

IDEMPOTENCIA: COMO SE RESOLVIO Y POR QUE
-------------------------------------------
La forma obvia es un `UNIQUE` + `ON CONFLICT DO NOTHING` en `events`, y de
hecho `schema.sql` tiene uno: `UNIQUE (video_id, frame_number, track_id,
bbox_x, bbox_y)`. El problema es que `track_id` puede ser NULL (una
deteccion que el tracker todavia no engancho a nadie), y en SQL dos NULL
NUNCA se consideran iguales para un UNIQUE: dos filas identicas salvo por
tener ambas `track_id = NULL` no chocan, y `ON CONFLICT` no las ve. Confiar
en ese UNIQUE dejaria pasar duplicados silenciosos justo en el caso donde
mas importan (gente que el tracker todavia no identifico).

Por eso este importador resuelve la idempotencia de otra forma, mas simple
de razonar: reimportar un video primero BORRA sus `events`/`metrics`
existentes (por `video_id`, dentro de una transaccion) y despues inserta el
archivo completo desde cero. Correr el importador dos veces seguidas sobre
el mismo archivo dejan la base exactamente igual las dos veces, sin
importar cuantos `track_id` sean NULL. `videos` y `zones` no se borran: se
actualizan con `ON CONFLICT ... DO UPDATE` para conservar su UUID (ver
`db.upsert_video`/`db.upsert_zone`), que es lo que mantiene enlazadas las
filas que SI sobreviven a la reimportacion (ninguna, en este esquema, pero
mantiene el diseno igual de simple que en el resto del proyecto).

POR QUE EL zone_id DE UN ESTANTE NO ES EL QUE TRAE EL CONTRATO
-------------------------------------------------------------------
El contrato (`Event.zone`) trae `zone_id` de la GONDOLA (ej. "gondola_A") y
`segment` del ESTANTE (ej. "estante_2"), y `segment` solo es unico DENTRO de
su gondola (ver `gondola/zones_config.py`). Pero `zones.zone_id` en la base
de datos es una columna UNIQUE para TODAS las filas, gondolas y estantes por
igual. Este importador construye el identificador de un estante como
`"<zone_id de la gondola>:<segment>"` (ej. "gondola_A:estante_2"): es
deterministico, siempre unico, y se reconstruye igual cada vez que se
reimporta, asi que no rompe la idempotencia de `zones`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

RAIZ = Path(__file__).resolve().parents[1]

# `gondola` vive en ai-service/ y no es un paquete instalado (el AI Service
# se ejecuta con `cd ai-service && python -m gondola`, no con pip install).
# Para poder hacer `from gondola.contract import Event` desde backend/ sin
# reescribir el contrato, se anade ai-service/ al sys.path aqui, en el unico
# lugar del backend que lo necesita.
_AI_SERVICE = RAIZ / "ai-service"
if str(_AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(_AI_SERVICE))


class ImporterError(Exception):
    """El importador no pudo completarse. El mensaje dice que corregir."""


SEPARADOR_ESTANTE = ":"
"""Como se une el zone_id de una gondola con el segment de su estante para
formar el zone_id (unico en toda la tabla `zones`) de la fila del estante."""


def _zone_id_de_estante(gondola_zone_id: str, segment: str) -> str:
    return f"{gondola_zone_id}{SEPARADOR_ESTANTE}{segment}"


# --------------------------------------------------------------------------
# Rutas de entrada. Nunca a mano fuera de aqui, igual que pipeline.py.
# --------------------------------------------------------------------------

def rutas_de_entrada(video_id: str, output_dir: Path, zones_dir: Path) -> "RutasImportacion":
    return RutasImportacion(
        interact_path=output_dir / f"{video_id}.interact.jsonl",
        metrics_path=output_dir / f"{video_id}.metrics.json",
        zones_path=zones_dir / f"{video_id}.json",
    )


@dataclass(frozen=True)
class RutasImportacion:
    interact_path: Path
    metrics_path: Path
    zones_path: Path

    def comprobar(self) -> None:
        faltantes = [p for p in (self.interact_path, self.metrics_path, self.zones_path) if not p.exists()]
        if not faltantes:
            return
        lista = "\n".join(f"    {p}" for p in faltantes)
        raise ImporterError(
            f"Faltan archivos de entrada:\n{lista}\n\n"
            "Que hacer: corre la cadena del pipeline hasta 'metrics' "
            "(python -m gondola run, desde ai-service/) y define las zonas "
            "de la camara en data/zones/<video_id>.json "
            "(ver docs/zones-format.md)."
        )


@dataclass
class ResumenImportacion:
    """Lo que se va contando durante la importacion, para el mensaje final."""

    zonas_importadas: int = 0
    eventos_importados: int = 0
    metricas_importadas: int = 0
    fps_derivados: float = 0.0
    frame_count_estimado: int | None = None
    duration_s_estimado: float | None = None


# --------------------------------------------------------------------------
# Metadatos del video: derivados de las zonas (ancho/alto) y de los eventos
# (fps, frame_count, duration_s). El pipeline no deja estos numeros juntos
# en ningun archivo estable, asi que se recomponen aqui.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class _VideoDerivado:
    fps: float
    frame_count: int | None
    duration_s: float | None


def _derivar_info_de_video(interact_path: Path, fps_override: float | None) -> _VideoDerivado:
    """Un primer paso, en streaming, solo para sacar fps/frame_count/duration_s.

    `timestamp = frame_number / fps` exactamente (ver
    `gondola/video/reader.py`, `VideoReader.frames`), asi que basta UN evento
    con `frame > 0` para despejar los fps. Es una segunda pasada por el
    archivo (la primera de dos: la segunda inserta los eventos), pero cada
    pasada sigue sin cargar nada en memoria: solo se llevan cuatro numeros.
    """
    from gondola.jsonl import read_events

    frame_maximo = -1
    timestamp_maximo = 0.0
    fps_detectado: float | None = None
    total = 0

    for evento in read_events(interact_path):
        total += 1
        if evento.frame > frame_maximo:
            frame_maximo = evento.frame
        if evento.timestamp > timestamp_maximo:
            timestamp_maximo = evento.timestamp
        if fps_detectado is None and evento.frame > 0 and evento.timestamp > 0:
            fps_detectado = evento.frame / evento.timestamp

    fps = fps_override if fps_override is not None else fps_detectado
    if fps is None or fps <= 0:
        raise ImporterError(
            f"No pude derivar los fps del video a partir de {interact_path.name} "
            "(todos sus eventos estan en el frame 0, o el archivo esta vacio).\n"
            "Que hacer: pasa --fps <valor> con los fps reales del video."
        )

    if total == 0:
        return _VideoDerivado(fps=fps, frame_count=None, duration_s=None)
    return _VideoDerivado(
        fps=fps,
        frame_count=frame_maximo + 1,
        duration_s=round(timestamp_maximo, 3),
    )


# --------------------------------------------------------------------------
# Zonas: del archivo de calibracion de camara a filas de `zones`.
# --------------------------------------------------------------------------

def _importar_zonas(conn, zones_config) -> tuple[dict[str, UUID], dict[tuple[str, str], UUID]]:
    """Sube las gondolas y sus estantes. Devuelve dos diccionarios de
    busqueda: uno por zone_id de gondola, otro por (zone_id, segment) de
    estante, para que `_fila_de_evento` no tenga que volver a tocar la base
    de datos por cada evento."""
    from db import upsert_zone

    gondola_a_uuid: dict[str, UUID] = {}
    estante_a_uuid: dict[tuple[str, str], UUID] = {}

    for gondola in zones_config.gondolas:
        gondola_uuid = upsert_zone(
            conn,
            zone_id=gondola.zone_id,
            name=gondola.name,
            level="gondola",
            parent_id=None,
            product_category=gondola.product_category,
        )
        gondola_a_uuid[gondola.zone_id] = gondola_uuid

        for estante in gondola.shelves:
            categoria = estante.product_category or gondola.product_category
            estante_uuid = upsert_zone(
                conn,
                zone_id=_zone_id_de_estante(gondola.zone_id, estante.segment),
                name=estante.name,
                level="shelf",
                parent_id=gondola_uuid,
                product_category=categoria,
            )
            estante_a_uuid[(gondola.zone_id, estante.segment)] = estante_uuid

    return gondola_a_uuid, estante_a_uuid


# --------------------------------------------------------------------------
# Eventos: de cada Event del contrato a una fila de `events`.
# --------------------------------------------------------------------------

def _fila_de_evento(
    evento,
    video_uuid: UUID,
    gondola_a_uuid: dict[str, UUID],
    estante_a_uuid: dict[tuple[str, str], UUID],
) -> dict[str, Any]:
    """Traduce un `Event` validado a los parametros de un INSERT en `events`.

    Si el evento trae una zona/segmento que no esta en el archivo de zonas
    cargado, es una inconsistencia real entre lo que produjo el pipeline y
    la calibracion de camara actual: se avisa con `ImporterError` en vez de
    insertar una fila con un `zone_id` inventado.
    """
    zone_row_id: UUID | None = None
    zone_id = evento.zone.zone_id
    segment = evento.zone.segment

    if zone_id is not None:
        if segment is not None:
            clave = (zone_id, segment)
            if clave not in estante_a_uuid:
                raise ImporterError(
                    f"El evento del frame {evento.frame} referencia la zona "
                    f"'{zone_id}' / estante '{segment}', que no existe en el "
                    "archivo de zonas cargado.\n"
                    "Que hacer: revisa data/zones/<video_id>.json, o vuelve a "
                    "correr 'python -m gondola zones' si la calibracion cambio."
                )
            zone_row_id = estante_a_uuid[clave]
        else:
            if zone_id not in gondola_a_uuid:
                raise ImporterError(
                    f"El evento del frame {evento.frame} referencia la gondola "
                    f"'{zone_id}', que no existe en el archivo de zonas cargado."
                )
            zone_row_id = gondola_a_uuid[zone_id]

    return {
        "video_id": video_uuid,
        "frame_number": evento.frame,
        "timestamp_s": evento.timestamp,
        "track_id": evento.track_id,
        "confidence": evento.detection.confidence,
        "bbox_x": evento.detection.bbox.x,
        "bbox_y": evento.detection.bbox.y,
        "bbox_width": evento.detection.bbox.width,
        "bbox_height": evento.detection.bbox.height,
        "zone_id": zone_row_id,
        "segment": segment,
        "interaction_event": evento.interaction.event.value if evento.interaction.event else None,
        "product_zone": evento.interaction.product_zone,
        "dwell_time_s": evento.metrics.dwell_time,
    }


TAMANO_LOTE = 2000
"""Cuantos eventos se acumulan antes de un INSERT. Bastante para que no sea
una consulta por fila, poco para que la memoria se quede acotada aunque el
video tenga decenas de miles de eventos."""


def _importar_eventos(
    conn, interact_path: Path, video_uuid: UUID,
    gondola_a_uuid: dict[str, UUID], estante_a_uuid: dict[tuple[str, str], UUID],
) -> int:
    """Segunda pasada por interact.jsonl: esta vez inserta, en lotes, sin
    acumular el archivo completo en memoria."""
    from db import insert_events
    from gondola.jsonl import read_events

    total = 0
    lote: list[dict[str, Any]] = []
    for evento in read_events(interact_path):
        lote.append(_fila_de_evento(evento, video_uuid, gondola_a_uuid, estante_a_uuid))
        if len(lote) >= TAMANO_LOTE:
            total += insert_events(conn, lote)
            lote = []
    total += insert_events(conn, lote)
    return total


# --------------------------------------------------------------------------
# Metricas: del JSON agregado de la Persona 6 a filas de `metrics`.
# --------------------------------------------------------------------------

def _importar_metricas(
    conn, metrics_path: Path, video_uuid: UUID,
    gondola_a_uuid: dict[str, UUID], duration_s: float | None,
) -> int:
    """`<video_id>.metrics.json` ya trae, por gondola, exactamente las
    columnas de `metrics` (lo calculo la Persona 6 con los mismos rangos que
    el CHECK de la base de datos): aqui solo se pasan tal cual, no se
    recalculan. La ventana es el video completo (no hay particion por
    tiempo en este JSON), por eso `window_start_s=0` y `window_end_s` es la
    duracion detectada del video."""
    from db import insert_metrics

    datos = json.loads(metrics_path.read_text(encoding="utf-8"))
    filas = []
    for zone_id, agregado in datos.get("zones", {}).items():
        if zone_id not in gondola_a_uuid:
            raise ImporterError(
                f"{metrics_path.name} trae metricas de la zona '{zone_id}', que "
                "no existe en el archivo de zonas cargado.\n"
                "Que hacer: revisa data/zones/<video_id>.json."
            )
        filas.append({
            "video_id": video_uuid,
            "zone_id": gondola_a_uuid[zone_id],
            "window_start_s": 0,
            "window_end_s": duration_s,
            "people_count": agregado["people_count"],
            "interaction_count": agregado["interaction_count"],
            "pick_up_count": agregado["pick_up_count"],
            "put_back_count": agregado["put_back_count"],
            "average_dwell_time_s": agregado.get("average_dwell_time_s"),
            "interaction_rate": agregado.get("interaction_rate"),
            "pick_up_rate": agregado.get("pick_up_rate"),
            "conversion_rate": agregado.get("conversion_rate"),
        })
    return insert_metrics(conn, filas)


# --------------------------------------------------------------------------
# Punto de entrada
# --------------------------------------------------------------------------

def import_video(
    video_id: str,
    *,
    output_dir: Path = RAIZ / "data" / "output",
    zones_dir: Path = RAIZ / "data" / "zones",
    fps_override: float | None = None,
    source_name: str | None = None,
) -> ResumenImportacion:
    """Importa un video completo (zonas + eventos + metricas) en una sola
    transaccion: si algo falla a mitad de camino, no queda nada a medias.
    """
    from gondola.contract import CONTRACT_VERSION
    from gondola.zones_config import load_zones_config

    import db as db_module

    rutas = rutas_de_entrada(video_id, output_dir, zones_dir)
    rutas.comprobar()

    zones_config = load_zones_config(rutas.zones_path)
    derivado = _derivar_info_de_video(rutas.interact_path, fps_override)

    metrics_data = json.loads(rutas.metrics_path.read_text(encoding="utf-8"))
    contract_version = metrics_data.get("contract_version", CONTRACT_VERSION)

    resumen = ResumenImportacion(
        fps_derivados=derivado.fps,
        frame_count_estimado=derivado.frame_count,
        duration_s_estimado=derivado.duration_s,
    )

    with db_module.get_connection() as conn:
        try:
            video_uuid = db_module.upsert_video(
                conn,
                video_id=video_id,
                source_name=source_name,
                fps=derivado.fps,
                width=zones_config.frame_width,
                height=zones_config.frame_height,
                frame_count=derivado.frame_count,
                duration_s=derivado.duration_s,
                contract_version=contract_version,
            )

            gondola_a_uuid, estante_a_uuid = _importar_zonas(conn, zones_config)
            resumen.zonas_importadas = len(gondola_a_uuid) + len(estante_a_uuid)

            db_module.delete_events_and_metrics(conn, video_uuid)

            resumen.eventos_importados = _importar_eventos(
                conn, rutas.interact_path, video_uuid, gondola_a_uuid, estante_a_uuid
            )
            resumen.metricas_importadas = _importar_metricas(
                conn, rutas.metrics_path, video_uuid, gondola_a_uuid, derivado.duration_s
            )
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()

    return resumen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Importa los archivos de un video procesado a PostgreSQL."
    )
    parser.add_argument("--video-id", required=True, help="Ej: video_001")
    parser.add_argument("--output-dir", type=Path, default=RAIZ / "data" / "output")
    parser.add_argument("--zones-dir", type=Path, default=RAIZ / "data" / "zones")
    parser.add_argument("--fps", type=float, default=None,
                        help="Fuerza los fps si no se pueden derivar de los eventos")
    parser.add_argument("--source-name", default=None, help="Nombre del archivo de video original")
    args = parser.parse_args(argv)

    print(f"[importer] Video: {args.video_id}")
    inicio = time.perf_counter()
    try:
        resumen = import_video(
            args.video_id,
            output_dir=args.output_dir,
            zones_dir=args.zones_dir,
            fps_override=args.fps,
            source_name=args.source_name,
        )
    except ImporterError as exc:
        print(f"[importer] ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # DatabaseError u otro fallo real
        print(f"[importer] ERROR: {exc}", file=sys.stderr)
        return 1
    transcurrido = time.perf_counter() - inicio

    print("-" * 66)
    print(f"  Zonas importadas       {resumen.zonas_importadas}")
    print(f"  Eventos importados     {resumen.eventos_importados}")
    print(f"  Filas de metrics       {resumen.metricas_importadas}")
    print(f"  fps usados             {resumen.fps_derivados:.3f}")
    if resumen.frame_count_estimado is not None:
        print(f"  frame_count (estimado) {resumen.frame_count_estimado}")
    if resumen.duration_s_estimado is not None:
        print(f"  duration_s (estimado)  {resumen.duration_s_estimado:.2f}")
    print(f"  Tiempo                 {transcurrido:.2f} s")
    print("-" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
