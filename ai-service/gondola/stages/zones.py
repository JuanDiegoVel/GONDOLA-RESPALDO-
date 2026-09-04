"""Etapa 3: zonas y permanencia. Responsable: Persona 4.

QUE HACE
--------
Lee los eventos ya seguidos de la Persona 3 (`<video>.track.jsonl`, con
`track_id` relleno) y, para cada uno, calcula el `support_point` de su caja
(los pies) y decide en que `floor_zone` del archivo de calibracion cae. Si
cae en una, rellena `zone.zone_id` y `zone.segment`; si no cae en ninguna
-estaba en el pasillo, entre gondolas-, `zone` se queda en null: es un
resultado correcto, no un error, y sigue sirviendo para medir flujo. Ademas
acumula `metrics.dwell_time`. Ningun otro campo del contrato se toca; la
clasificacion "se detiene"/"pasa de largo" (ver CASO 3 abajo) solo se cuenta
para el resumen de la corrida, no se escribe en el evento.

DE DONDE SALE EL ARCHIVO DE ZONAS
------------------------------------
`gondola/zones_config.py` (Fase 1) define el formato y lo valida
(`ZonesConfig`, `load_zones_config`). Esta etapa lo busca en
`data/zones/<video_id>.json` (ver `_ruta_zonas`). Si no existe, el mensaje
dice que copiar (`data/zones/video_001.example.json`) y ajustar -exactamente
el mismo patron que `eval` usa con `data/groundtruth/<video_id>.csv` y su
`ejemplo.csv`.

`ZONES_PATH` en `.env` / `gondola/config.py` queda pendiente a proposito:
esta fase solo puede tocar `gondola/stages/`, y esa ruta hoy es la unica
convencion fija que no depende de ningun archivo fuera de esa carpeta.

QUE ES support_point Y POR QUE SE USA EN VEZ DEL CENTRO DE LA CAJA
-----------------------------------------------------------------
`bbox.support_point` (definido en `gondola/contract.py`, Fase 1) es el centro
del borde INFERIOR de la caja -donde los pies tocan el piso-, no el centro
geometrico de la caja completa. Las zonas de este archivo son rectangulos de
PISO (`floor_zone`, ver `gondola/zones_config.py`), asi que solo tiene
sentido compararlas contra un punto que tambien este en el piso. El centro de
la caja "flota" a la altura del pecho: dos personas a la misma distancia de
la gondola, una alta y otra baja, o una de pie y otra agachada, dan centros a
alturas de pixel distintas aunque pisen exactamente el mismo sitio. Los pies
no tienen ese problema.

CASO 1 A DECIDIR: UN PUNTO JUSTO EN EL BORDE ENTRE DOS ZONAS
------------------------------------------------------------
`punto_en_zona` usa un intervalo SEMIABIERTO: `[x, x+width)` x `[y,
y+height)`. Un punto en el borde IZQUIERDO o SUPERIOR de una zona cuenta como
dentro; en el borde DERECHO o INFERIOR cuenta como fuera. Con dos zonas
ADYACENTES que comparten borde (ej. `estante_1` termina en x=530 y
`estante_2` empieza en x=530, como en `data/zones/video_001.example.json`),
el punto x=530 cae SIEMPRE en `estante_2`: nunca en los dos a la vez (lo que
duplicaria a la persona en las metricas de ambos estantes) ni en ninguno (lo
que la mandaria al pasillo estando literalmente pegada a un estante). Es la
misma convencion que usan casi todas las librerias de rasterizado 2D, y no
depende de que gondola se calibro primero.

CASO 2 A DECIDIR: DOS ZONAS QUE SE SOLAPAN
--------------------------------------------
`asignar_zona` le da la zona al candidato con el `floor_zone` de MENOR AREA.
Motivo: si alguien calibro dos zonas que se superponen (a proposito, para
acotar un area mas fina dentro de otra mas general, o por error), la mas
PEQUENA es casi siempre la mas ESPECIFICA -la que alguien dibujo pensando en
un lugar concreto-, mientras que la mas grande suele ser una zona general que
por descuido llego a cubrir mas piso del que debia. Es determinista y no
depende del orden en que se escribieron las gondolas en el JSON. Un empate
exacto de area (rarisimo, dos zonas identicas superpuestas) se resuelve por
el orden en que aparecen en el archivo -estable, nunca aleatorio.

QUE ES metrics.dwell_time AQUI, EXACTO
------------------------------------------
Tiempo real (por `timestamp`, NUNCA contando frames ni eventos -el
`FRAME_STRIDE` de deteccion puede ser mayor que 1, ver
`docs/tracking-guia-para-zonas.md`) que ese `track_id` lleva CONTINUAMENTE en
la MISMA zona (mismo `zone_id` + `segment`). En el primer evento de una
visita nueva vale 0.0. Si el `track_id` cambia de zona, sale de todas, o
sencillamente ese es su primer evento, la cuenta empieza de nuevo desde 0.0:
es literal, "cuanto lleva AHORA en ESTA zona", no un acumulado historico de
todas las visitas que haya hecho. Fuera de cualquier zona (`zone.zone_id` es
`null`) `dwell_time` tambien se deja en `null`: no hay "segundos en la zona"
que contar si no hay zona.

CASO 3 A DECIDIR: "SE DETIENE" vs "PASA DE LARGO"
---------------------------------------------------
El campo `dwell_time` es tiempo continuo, no una etiqueta. `clasifica_visita`
convierte eso en la pregunta que de verdad le importa a un supermercado: si
alguien PARO frente al estante o solo lo cruzo caminando. La regla es un solo
umbral, `UMBRAL_SE_DETIENE_S` (2.0 segundos por defecto): `dwell_time >=
umbral` es "se_detiene", por debajo es "pasa_de_largo", y `None` (fuera de
zona) sigue siendo `None` -no hay clasificacion de algo que no esta en ningun
estante.

Por que 2.0 s: cruzar el ancho de un estante caminando a paso normal toma
bien menos de un segundo; alguien que se queda 2 segundos o mas ya freno el
paso a mirar algo, aunque no haya tomado ningun producto (eso lo decide la
Persona 5 con `interaction`, es informacion aparte). Es un valor inicial
razonable, no medido contra groundtruth -no hay groundtruth de esto todavia,
ver `CLAUDE.md`-, por eso `clasifica_visita` recibe el umbral como parametro
en vez de tenerlo fijo: quien tenga datos reales para recalibrarlo no
necesita tocar esta funcion, solo pasar otro numero.

OJO: esto clasifica el momento actual de la visita, no la visita completa.
Un evento con `dwell_time=1.0` de alguien que dos frames despues llega a
`dwell_time=3.0` sale como "pasa_de_largo" en ese instante y "se_detiene" mas
tarde -es correcto: en el frame 1.0 esa persona, en efecto, todavia no se
habia detenido. Reconstruir "se detuvo en algun momento de su visita" a
partir de la secuencia completa es trabajo de la etapa de metricas o del
dashboard (Persona 6), que ya tienen toda la visita en memoria; aqui solo se
expone el clasificador puro para que lo reutilicen sin reinventarlo.

UNA FRAGILIDAD YA CONOCIDA, HEREDADA DE `track` (no se resuelve aqui)
-------------------------------------------------------------------
Si un `track_id` se fragmenta por oclusion (Persona 3 lo documenta en
`docs/tracking-guia-para-zonas.md`), esta etapa ve dos `track_id` distintos
donde en la realidad hubo una sola persona parada todo el tiempo. Cada
fragmento arranca su propio `dwell_time` en 0.0. El numero por persona real
puede quedar subestimado; no hay forma de detectarlo ni corregirlo desde
aqui, con la informacion que llega de `track.jsonl`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from gondola import pipeline
from gondola.config import RAIZ, Config
from gondola.contract import CONTRACT_VERSION, Event
from gondola.jsonl import read_events, write_events
from gondola.zones_config import FloorZone, Gondola, Shelf, ZonesConfig, load_zones_config


# --------------------------------------------------------------------------
# Logica pura: se prueba sin archivos ni zonas cargadas de disco
# --------------------------------------------------------------------------

def punto_en_zona(punto: tuple[float, float], zona: FloorZone) -> bool:
    """True si `punto` cae dentro de `zona`. Ver "CASO 1" en el docstring del
    modulo: intervalo semiabierto, el borde derecho/inferior no cuenta."""
    px, py = punto
    return zona.x <= px < zona.x + zona.width and zona.y <= py < zona.y + zona.height


def asignar_zona(
    punto: tuple[float, float], zonas: ZonesConfig
) -> tuple[Gondola, Shelf] | None:
    """La (gondola, estante) donde cae `punto`, o `None` si no cae en ninguno.

    Ver "CASO 2" en el docstring del modulo: si varias zonas se solapan,
    gana la de menor area.
    """
    candidatos = [(g, e) for g, e in zonas.shelves() if punto_en_zona(punto, e.floor_zone)]
    if not candidatos:
        return None
    candidatos.sort(key=lambda par: par[1].floor_zone.width * par[1].floor_zone.height)
    return candidatos[0]


UMBRAL_SE_DETIENE_S = 2.0
"""Segundos de `dwell_time` a partir de los cuales una visita cuenta como
"se detiene" en vez de "pasa de largo". Ver "CASO 3" en el docstring del
modulo para el porque de este valor y de por que no esta fijo en el codigo."""


def clasifica_visita(
    dwell_time: float | None, umbral_s: float = UMBRAL_SE_DETIENE_S
) -> str | None:
    """"se_detiene" si `dwell_time >= umbral_s`, "pasa_de_largo" si es menor,
    o `None` si `dwell_time` es `None` (la persona no esta en ninguna zona).

    Pura: no lee ni escribe ningun `Event`. Ver "CASO 3" en el docstring del
    modulo.
    """
    if dwell_time is None:
        return None
    return "se_detiene" if dwell_time >= umbral_s else "pasa_de_largo"


@dataclass
class Visita:
    """La visita en curso de un `track_id`: a que zona, y desde cuando.

    Vive solo en memoria mientras corre `_procesar`; no es lo que se escribe
    en el .jsonl (eso es `zone` y `metrics.dwell_time`, dentro de cada
    `Event`).
    """

    zona: tuple[str, str] | None  # (zone_id, segment), o None si esta en el pasillo
    entrada: float  # timestamp en el que empezo ESTA visita continua


@dataclass
class Resumen:
    """Lo que se va contando durante la corrida y acaba en el JSON de resumen."""

    eventos_procesados: int = 0
    eventos_con_zona: int = 0
    eventos_sin_zona: int = 0
    eventos_por_zona: dict[str, int] = field(default_factory=dict)
    eventos_se_detiene: int = 0
    eventos_pasa_de_largo: int = 0


def _procesar(entrada: Path, zonas: ZonesConfig, resumen: Resumen) -> Iterator[Event]:
    """Recorre los eventos en orden, les asigna zona y acumula dwell_time.

    Es un generador: solo mantiene en memoria la visita en curso de cada
    `track_id` (un dict pequeno, uno por persona activa), nunca el archivo
    completo. `track.jsonl` garantiza `track_id` siempre relleno (ver
    `docs/tracking-guia-para-zonas.md`), asi que no hace falta un caso aparte
    para `track_id is None`.
    """
    visitas: dict[int, Visita] = {}

    for evento in read_events(entrada):
        resultado = asignar_zona(evento.detection.bbox.support_point, zonas)

        if resultado is None:
            zona_actual = None
            resumen.eventos_sin_zona += 1
        else:
            gondola, estante = resultado
            evento.zone.zone_id = gondola.zone_id
            evento.zone.segment = estante.segment
            zona_actual = (gondola.zone_id, estante.segment)
            resumen.eventos_con_zona += 1
            clave = f"{gondola.zone_id}/{estante.segment}"
            resumen.eventos_por_zona[clave] = resumen.eventos_por_zona.get(clave, 0) + 1

        visita = visitas.get(evento.track_id)
        if visita is None or visita.zona != zona_actual:
            visita = Visita(zona=zona_actual, entrada=evento.timestamp)
            visitas[evento.track_id] = visita

        evento.metrics.dwell_time = (
            evento.timestamp - visita.entrada if zona_actual is not None else None
        )

        clasificacion = clasifica_visita(evento.metrics.dwell_time)
        if clasificacion == "se_detiene":
            resumen.eventos_se_detiene += 1
        elif clasificacion == "pasa_de_largo":
            resumen.eventos_pasa_de_largo += 1

        resumen.eventos_procesados += 1
        yield evento


# --------------------------------------------------------------------------
# Punto de entrada de la etapa
# --------------------------------------------------------------------------

def _ruta_zonas(cfg: Config) -> Path:
    """Donde vive la calibracion de esta camara. Ver docstring del modulo:
    `ZONES_PATH` queda pendiente para cuando se pueda tocar `config.py`."""
    return RAIZ / "data" / "zones" / f"{cfg.video_id}.json"


def run(cfg: Config) -> int:
    """Ejecuta la asignacion de zonas completa. Devuelve el codigo de salida."""
    rutas = pipeline.stage_paths("zones", cfg)
    pipeline.require_input("zones", cfg)

    ruta_zonas = _ruta_zonas(cfg)
    zonas = load_zones_config(ruta_zonas)  # ZonesConfigError si falta o esta mal formado

    print(f"[zones] Entrada: {rutas.input_path}")
    print(f"[zones] Zonas:   {ruta_zonas}  "
          f"({len(zonas.gondolas)} gondola(s), {len(zonas.shelves())} estante(s))")
    print()

    resumen = Resumen()
    inicio = time.perf_counter()
    escritos = write_events(rutas.output_path, _procesar(rutas.input_path, zonas, resumen))
    transcurrido = time.perf_counter() - inicio

    ruta_resumen = pipeline.summary_path("zones", cfg)
    _escribir_resumen(ruta_resumen, cfg, zonas, ruta_zonas, resumen, transcurrido)

    _imprimir_resultado(resumen, escritos, transcurrido, rutas.output_path, ruta_resumen)
    return 0


def _leer_info_de_video_desde_track(cfg: Config) -> dict:
    """Copia `width`/`height`/`fps` del resumen de `track`, para que `verify`
    tambien pueda comprobar `bbox_en_frame` y `timestamps` sobre esta salida.
    Mismo patron que usa `track.py` con el resumen de `detect` -ver
    `docs/tracking-guia-para-zonas.md`, seccion de convenciones."""
    ruta = pipeline.summary_path("track", cfg)
    if not ruta.exists():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return datos.get("video", {})


def _escribir_resumen(
    destino: Path, cfg: Config, zonas: ZonesConfig, ruta_zonas: Path,
    resumen: Resumen, transcurrido: float,
) -> None:
    """Guarda las metricas de la corrida. Sin esto no se puede comparar nada."""
    datos = {
        "contract_version": CONTRACT_VERSION,
        "stage": "zones",
        "video_id": cfg.video_id,
        "video": _leer_info_de_video_desde_track(cfg),
        "params": {
            "archivo_de_zonas": str(ruta_zonas),
            "gondolas": len(zonas.gondolas),
            "estantes": len(zonas.shelves()),
        },
        "results": {
            "eventos_procesados": resumen.eventos_procesados,
            "eventos_con_zona": resumen.eventos_con_zona,
            "eventos_sin_zona": resumen.eventos_sin_zona,
            "eventos_por_zona": resumen.eventos_por_zona,
            "eventos_se_detiene": resumen.eventos_se_detiene,
            "eventos_pasa_de_largo": resumen.eventos_pasa_de_largo,
            "umbral_se_detiene_s": UMBRAL_SE_DETIENE_S,
        },
        "performance": {
            "segundos": round(transcurrido, 2),
            "eventos_por_segundo": round(
                resumen.eventos_procesados / transcurrido, 2
            ) if transcurrido > 0 else 0.0,
        },
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def _imprimir_resultado(
    resumen: Resumen, escritos: int, transcurrido: float, jsonl: Path, ruta_resumen: Path,
) -> None:
    print()
    print("-" * 66)
    print(f"  Eventos procesados     {resumen.eventos_procesados}")
    print(f"  Eventos con zona       {resumen.eventos_con_zona}")
    print(f"  Eventos sin zona       {resumen.eventos_sin_zona}  (pasillo, entre gondolas)")
    for clave, cuenta in sorted(resumen.eventos_por_zona.items()):
        print(f"      {clave:<30} {cuenta}")
    print(f"  Se detiene (>= {UMBRAL_SE_DETIENE_S:.1f}s)   {resumen.eventos_se_detiene}")
    print(f"  Pasa de largo          {resumen.eventos_pasa_de_largo}")
    print(f"  Tiempo                 {transcurrido:.2f} s")
    print("-" * 66)
    print(f"  Eventos   {jsonl}  ({escritos} lineas)")
    print(f"  Resumen   {ruta_resumen}")
    print()
    print("  Siguiente etapa:  python -m gondola interact   (Persona 5)")
