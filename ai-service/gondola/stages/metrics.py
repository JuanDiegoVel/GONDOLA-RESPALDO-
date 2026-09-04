"""Etapa 5: metricas agregadas del video. Responsable: Oscar Torres.

QUE HACE
--------
Lee `<video_id>.interact.jsonl` (todos los eventos, con `zone`,
`metrics.dwell_time` e `interaction` ya rellenos) y agrega, por zona, los
totales que espera la tabla `metrics` de `backend/database/schema.sql`:
personas distintas, conteos de interaccion y tasas derivadas. No enriquece el
contrato `Event` (`pipeline.py` declara `fills=()` para esta etapa): escribe
un JSON agregado aparte, `<video_id>.metrics.json`.

EL BUG QUE ESTO EXISTE PARA EVITAR
-----------------------------------
`schema.sql` marca en mayusculas que `people_count` se cuenta con
`COUNT(DISTINCT track_id)`, nunca contando filas: una persona parada 20 s
genera cientos de eventos (uno por frame), y contarlos todos infla el numero
cientos de veces sin lanzar ninguna excepcion. Por eso `_agregar` acumula un
`set()` de `track_id` por zona en vez de un contador que suba en cada evento.

POR QUE HAY UN MODELO PYDANTIC AQUI Y NO SOLO UN DICT
-------------------------------------------------------
`ZoneMetrics` no es el contrato de `Event` (por eso vive aqui y no en
`contract.py`, y no hace falta subir `CONTRACT_VERSION`), pero usa el mismo
`extra="forbid"` y los mismos rangos (`ge=0`, tasas en `[0, 1]`) que los
`CHECK` de la tabla `metrics`. Es la red de seguridad barata para el error de
arriba: si un bug de calculo produce un conteo negativo o una tasa por
encima de 1.0, esto revienta en desarrollo con un mensaje claro en vez de
llegar callado hasta el dashboard.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from pydantic import BaseModel, ConfigDict, Field

from gondola import pipeline
from gondola.config import Config
from gondola.contract import CONTRACT_VERSION, Event, InteractionEvent
from gondola.jsonl import read_events


class ZoneMetrics(BaseModel):
    """Agregados de una zona para todo el video. Espejo de la tabla `metrics`
    de `backend/database/schema.sql` (sin `video_id`/`zone_id`/`window_*`,
    que los pone quien arma el JSON final, no este modelo)."""

    model_config = ConfigDict(extra="forbid")

    people_count: int = Field(
        ge=0, description="track_id DISTINTOS vistos en la zona, nunca filas"
    )
    interaction_count: int = Field(ge=0)
    pick_up_count: int = Field(ge=0)
    put_back_count: int = Field(ge=0)

    average_dwell_time_s: float | None = Field(default=None, ge=0)

    interaction_rate: float | None = Field(
        default=None, ge=0, le=1,
        description="personas DISTINTAS con >=1 interaccion / people_count",
    )
    pick_up_rate: float | None = Field(
        default=None, ge=0, le=1, description="pick_up_count / interaction_count"
    )
    conversion_rate: float | None = Field(
        default=None, ge=0, le=1,
        description="personas DISTINTAS con >=1 PICK_UP / people_count",
    )


# --------------------------------------------------------------------------
# Agregacion pura: se prueba con eventos construidos a mano, sin archivos
# --------------------------------------------------------------------------

@dataclass
class _Acumulador:
    """Lo que se va sumando por zona mientras se recorre el .jsonl.

    `track_ids` es un `set()`, no un contador: es lo que garantiza que
    `people_count` cuente personas DISTINTAS y no filas. Ver el docstring del
    modulo, seccion "EL BUG QUE ESTO EXISTE PARA EVITAR".

    `track_ids_con_interaccion` y `track_ids_con_pick_up` son tambien
    conjuntos, y no derivados de dividir un conteo entre `people_count`: la
    convencion de `interact.py` (`etiqueta_de_alcance`) puede darle a una
    misma persona varios PICK_UP/PUT_BACK dentro de una sola visita, asi que
    `interaction_count / people_count` puede pasarse de 1.0 y romper el
    `CHECK (... BETWEEN 0 AND 1)` de `schema.sql`. Contando personas
    distintas con al menos una interaccion, la tasa queda acotada en [0, 1]
    por construccion y ademas es la metrica de negocio mas util: "que
    porcentaje de clientes interactuo", no "cuantas interacciones por
    cliente en promedio".
    """

    track_ids: set[int] = field(default_factory=set)
    track_ids_con_interaccion: set[int] = field(default_factory=set)
    track_ids_con_pick_up: set[int] = field(default_factory=set)
    interaction_count: int = 0
    pick_up_count: int = 0
    put_back_count: int = 0
    dwell_suma: float = 0.0
    dwell_cuenta: int = 0


def _agregar(eventos: Iterable[Event]) -> dict[str, ZoneMetrics]:
    """Recorre los eventos de `interact.jsonl` y agrega por `zone.zone_id`.

    Eventos sin zona (pasillo, entre gondolas) no cuentan para ninguna zona:
    la tabla `metrics` de `schema.sql` exige `zone_id NOT NULL`. Ver
    `_cerrar_zona` para como se convierten los conteos en `ZoneMetrics`
    (con tasas ya validadas por Pydantic).
    """
    acumuladores: dict[str, _Acumulador] = defaultdict(_Acumulador)

    for evento in eventos:
        zone_id = evento.zone.zone_id
        if zone_id is None:
            continue
        acumulador = acumuladores[zone_id]

        if evento.track_id is not None:
            acumulador.track_ids.add(evento.track_id)

        if evento.interaction.event is not None:
            acumulador.interaction_count += 1
            if evento.track_id is not None:
                acumulador.track_ids_con_interaccion.add(evento.track_id)
            if evento.interaction.event is InteractionEvent.PICK_UP:
                acumulador.pick_up_count += 1
                if evento.track_id is not None:
                    acumulador.track_ids_con_pick_up.add(evento.track_id)
            elif evento.interaction.event is InteractionEvent.PUT_BACK:
                acumulador.put_back_count += 1

        if evento.metrics.dwell_time is not None:
            acumulador.dwell_suma += evento.metrics.dwell_time
            acumulador.dwell_cuenta += 1

    return {
        zone_id: _cerrar_zona(acumulador)
        for zone_id, acumulador in acumuladores.items()
    }


def _cerrar_zona(acumulador: _Acumulador) -> ZoneMetrics:
    """Convierte los contadores en bruto de una zona en su `ZoneMetrics`.

    Las tasas se guardan como `None` (nunca `NaN`/`inf`) cuando el
    denominador es 0: no hay personas, o no hubo interacciones. `ZoneMetrics`
    valida los rangos al construirse.
    """
    people_count = len(acumulador.track_ids)
    average_dwell_time_s = (
        acumulador.dwell_suma / acumulador.dwell_cuenta
        if acumulador.dwell_cuenta > 0
        else None
    )
    return ZoneMetrics(
        people_count=people_count,
        interaction_count=acumulador.interaction_count,
        pick_up_count=acumulador.pick_up_count,
        put_back_count=acumulador.put_back_count,
        average_dwell_time_s=average_dwell_time_s,
        interaction_rate=(
            len(acumulador.track_ids_con_interaccion) / people_count
            if people_count else None
        ),
        pick_up_rate=(
            acumulador.pick_up_count / acumulador.interaction_count
            if acumulador.interaction_count else None
        ),
        conversion_rate=(
            len(acumulador.track_ids_con_pick_up) / people_count
            if people_count else None
        ),
    )


# --------------------------------------------------------------------------
# Punto de entrada de la etapa
# --------------------------------------------------------------------------

def _contar(eventos: Iterable[Event], contador: list[int]) -> Iterator[Event]:
    """Deja pasar cada evento y lleva la cuenta en `contador[0]`, sin cargar
    nada en memoria: es la unica forma de contar eventos procesados y seguir
    agregando en streaming."""
    for evento in eventos:
        contador[0] += 1
        yield evento


def run(cfg: Config) -> int:
    """Ejecuta la agregacion de metricas. Devuelve el codigo de salida."""
    rutas = pipeline.stage_paths("metrics", cfg)
    pipeline.require_input("metrics", cfg)

    print(f"[metrics] Entrada: {rutas.input_path}")
    print()

    inicio = time.perf_counter()
    eventos_procesados = [0]
    zonas = _agregar(_contar(read_events(rutas.input_path), eventos_procesados))
    transcurrido = time.perf_counter() - inicio

    _escribir_metrics(rutas.output_path, cfg, zonas)

    ruta_resumen = pipeline.summary_path("metrics", cfg)
    _escribir_resumen(ruta_resumen, cfg, eventos_procesados[0], zonas, transcurrido)

    _imprimir_resultado(
        zonas, eventos_procesados[0], transcurrido, rutas.output_path, ruta_resumen
    )
    return 0


def _escribir_metrics(destino: Path, cfg: Config, zonas: dict[str, ZoneMetrics]) -> None:
    """Escribe el JSON agregado que consume la Persona 7. Cada `ZoneMetrics`
    ya paso por Pydantic al construirse, asi que no puede colarse aqui un
    conteo negativo, una tasa fuera de [0, 1] ni un NaN/Infinity."""
    datos = {
        "contract_version": CONTRACT_VERSION,
        "video_id": cfg.video_id,
        "zones": {
            zone_id: zone_metrics.model_dump()
            for zone_id, zone_metrics in zonas.items()
        },
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def _escribir_resumen(
    destino: Path, cfg: Config, eventos_procesados: int,
    zonas: dict[str, ZoneMetrics], transcurrido: float,
) -> None:
    """Guarda las metricas DE LA CORRIDA (tiempos, conteos), no las del video.
    Mismo patron que las demas etapas: sin esto no se puede comparar nada."""
    datos = {
        "contract_version": CONTRACT_VERSION,
        "stage": "metrics",
        "video_id": cfg.video_id,
        "results": {
            "eventos_procesados": eventos_procesados,
            "zonas_encontradas": len(zonas),
        },
        "performance": {
            "segundos": round(transcurrido, 2),
            "eventos_por_segundo": round(
                eventos_procesados / transcurrido, 2
            ) if transcurrido > 0 else 0.0,
        },
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def _imprimir_resultado(
    zonas: dict[str, ZoneMetrics], eventos_procesados: int, transcurrido: float,
    metrics_path: Path, resumen_path: Path,
) -> None:
    """Conteos por zona, nunca `track_id` individuales: son datos personales
    dentro del proyecto (permiten reconstruir el recorrido de alguien)."""
    print("-" * 66)
    print(f"  Eventos procesados     {eventos_procesados}")
    print(f"  Zonas encontradas      {len(zonas)}")
    for zone_id in sorted(zonas):
        zm = zonas[zone_id]
        print(
            f"    {zone_id:<20} personas={zm.people_count:<4} "
            f"interacciones={zm.interaction_count:<4} "
            f"pick_up={zm.pick_up_count:<4} put_back={zm.put_back_count}"
        )
    print(f"  Tiempo                 {transcurrido:.2f} s")
    print("-" * 66)
    print(f"  Metricas  {metrics_path}")
    print(f"  Resumen   {resumen_path}")
    print()
    print("  Cadena completa: detect -> track -> zones -> interact -> metrics.")
