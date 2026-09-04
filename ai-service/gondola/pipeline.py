"""Registro de etapas: quien hace que, que lee y que escribe.

EL PROBLEMA QUE RESUELVE
------------------------
Somos 8 personas en cadena. Si cada quien escribe a mano el nombre de su
archivo, basta un `salida.jsonl` contra un `salidas.jsonl` para que la cadena
se rompa, y el error aparece dias despues en la integracion.

LA SOLUCION
-----------
Los nombres de archivo los decide el CODIGO. La tabla `STAGES` de abajo es la
unica fuente de verdad, y `stage_paths()` es la unica forma permitida de
obtener una ruta. Nadie escribe `"video_001.track.jsonl"` en su modulo: pide
`stage_paths("track", cfg).output_path` y ya.

Cambiar el nombre de un archivo es cambiar una linea de esta tabla, y toda la
cadena se entera al mismo tiempo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gondola.config import Config
from gondola.errors import MissingInputError, PipelineError


@dataclass(frozen=True)
class Stage:
    """Una etapa de la cadena, descrita como datos y no como codigo."""

    name: str
    owner: str
    description: str
    input_suffix: str | None  # None significa: esta etapa lee el video, no un archivo
    output_suffix: str
    fills: tuple[str, ...]  # que campos del contrato rellena, en notacion punto


# La tabla. Se lee de arriba a abajo: la salida de cada etapa es la entrada de
# la siguiente. Este es el documento de trabajo del equipo.
STAGES: tuple[Stage, ...] = (
    Stage(
        name="detect",
        owner="Persona 2",
        description="Detecta personas en cada frame con YOLO",
        input_suffix=None,
        output_suffix=".detect.jsonl",
        fills=("detection",),
    ),
    Stage(
        name="track",
        owner="Persona 3",
        description="Enlaza las detecciones entre frames y asigna track_id",
        input_suffix=".detect.jsonl",
        output_suffix=".track.jsonl",
        fills=("track_id",),
    ),
    Stage(
        name="zones",
        owner="Persona 4",
        description="Ubica a cada persona en una zona y acumula dwell_time",
        input_suffix=".track.jsonl",
        output_suffix=".zones.jsonl",
        fills=("zone", "metrics.dwell_time"),
    ),
    Stage(
        name="interact",
        owner="Persona 5",
        description="Detecta APPROACH, PICK_UP y PUT_BACK frente al estante",
        input_suffix=".zones.jsonl",
        output_suffix=".interact.jsonl",
        fills=("interaction",),
    ),
    Stage(
        name="metrics",
        owner="Persona 6",
        description="Agrega las metricas finales del video",
        input_suffix=".interact.jsonl",
        output_suffix=".metrics.json",
        fills=(),  # produce un resumen agregado, no enriquece eventos
    ),
)

STAGE_NAMES: tuple[str, ...] = tuple(etapa.name for etapa in STAGES)


def stages_after(name: str) -> tuple[Stage, ...]:
    """Las etapas que van DESPUES de esta en la cadena.

    El verificador la usa para saber que campos deben seguir en null: si un
    archivo .detect.jsonl trae un track_id, alguien se salio de su carril.
    """
    get_stage(name)  # valida el nombre
    indice = STAGE_NAMES.index(name)
    return STAGES[indice + 1:]


def stage_for_file(ruta: Path) -> Stage | None:
    """Deduce a que etapa pertenece un archivo por su nombre. None si no encaja.

    Asi `verify archivo.jsonl` sabe que reglas aplicar sin que se lo digan.
    """
    for etapa in STAGES:
        if ruta.name.endswith(etapa.output_suffix):
            return etapa
    return None


@dataclass(frozen=True)
class StagePaths:
    """Las dos rutas de una etapa, ya resueltas y absolutas."""

    stage: Stage
    input_path: Path
    output_path: Path


def get_stage(name: str) -> Stage:
    """Devuelve la etapa por su nombre.

    Si no existe, el error lista las validas: nadie deberia tener que abrir
    este archivo para recordar como se llamaban.
    """
    for etapa in STAGES:
        if etapa.name == name:
            return etapa
    validas = ", ".join(STAGE_NAMES)
    raise PipelineError(
        f"La etapa {name!r} no existe. Las etapas validas son: {validas}."
    )


def stage_paths(name: str, cfg: Config) -> StagePaths:
    """Devuelve que lee y que escribe una etapa. LA UNICA forma de obtener rutas.

    Ningun modulo debe construir un nombre de archivo a mano ni concatenar
    rutas por su cuenta. Todo pasa por aqui.
    """
    etapa = get_stage(name)

    if etapa.input_suffix is None:
        entrada = cfg.video_path  # la primera etapa lee el video, no un .jsonl
    else:
        entrada = cfg.output_dir / f"{cfg.video_id}{etapa.input_suffix}"

    salida = cfg.output_dir / f"{cfg.video_id}{etapa.output_suffix}"

    if salida == entrada:
        # Solo puede pasar si alguien edita mal la tabla STAGES. Mejor reventar
        # aqui que borrar el trabajo de la etapa anterior a mitad de ejecucion.
        raise PipelineError(
            f"La etapa {name!r} escribiria sobre su propia entrada ({salida}). "
            "Revisa input_suffix y output_suffix en gondola/pipeline.py."
        )

    return StagePaths(stage=etapa, input_path=entrada, output_path=salida)


def previous_stage(name: str) -> Stage | None:
    """Devuelve la etapa que produce la entrada de esta. None si es la primera."""
    etapa = get_stage(name)
    if etapa.input_suffix is None:
        return None
    for candidata in STAGES:
        if candidata.output_suffix == etapa.input_suffix:
            return candidata
    raise PipelineError(
        f"Ninguna etapa produce {etapa.input_suffix!r}, que necesita {name!r}. "
        "La tabla STAGES de gondola/pipeline.py esta descuadrada."
    )


def require_input(name: str, cfg: Config) -> Path:
    """Comprueba que exista la entrada de la etapa y devuelve su ruta.

    Si no existe, lanza `MissingInputError` diciendo EXACTAMENTE que comando
    hay que correr antes. Nadie deberia tener que adivinar el orden.
    """
    rutas = stage_paths(name, cfg)
    if rutas.input_path.exists():
        return rutas.input_path

    anterior = previous_stage(name)
    if anterior is None:
        raise MissingInputError(
            f"No encuentro el video en:\n"
            f"    {rutas.input_path}\n\n"
            f"Que hacer: deja el video de Scapder en data/videos/ y apunta a el "
            f"con VIDEO_PATH en tu .env (ver data/videos/README.md)."
        )

    raise MissingInputError(
        f"La etapa '{name}' necesita este archivo, que todavia no existe:\n"
        f"    {rutas.input_path}\n\n"
        f"Que hacer: corre primero la etapa que lo produce:\n"
        f"    python -m gondola {anterior.name}"
    )


def summary_path(name: str, cfg: Config) -> Path:
    """Ruta del resumen JSON de una etapa (metricas de la corrida, no eventos).

    Vive aqui, junto al resto de rutas, para que nadie construya
    "video_001.detect.summary.json" a mano en su modulo.
    """
    get_stage(name)  # valida que la etapa exista
    return cfg.output_dir / f"{cfg.video_id}.{name}.summary.json"


def render_path(name: str, cfg: Config, modo: str) -> Path:
    """Ruta del video renderizado de una etapa.

    El modo va en el nombre a proposito: asi el video de privacidad y el de
    depuracion nunca se pisan, y al ver el archivo se sabe cual es cual.
    """
    return cfg.output_dir / f"{cfg.video_id}.{name}.{modo}.mp4"
