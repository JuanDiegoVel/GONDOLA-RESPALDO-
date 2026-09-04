"""Configuracion del pipeline, leida del archivo .env con valores por defecto.

Un solo objeto `Config` congelado que se arma al arrancar y se pasa hacia
abajo. Nadie llama a `os.getenv` fuera de este archivo: si un valor se puede
cambiar, esta aqui y esta documentado en `.env.example`.

Si un valor esta fuera de rango, el programa falla AQUI, al arrancar, con un
mensaje que dice que corregir; no 20 minutos despues en mitad del video.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

from gondola.errors import ConfigError

# Raiz del repositorio (config.py esta en <raiz>/ai-service/gondola/).
RAIZ = Path(__file__).resolve().parents[2]

DEVICES_VALIDOS = {"cpu", "cuda", "mps"}
RENDER_MODES_VALIDOS = {"none", "debug", "privacy"}
LOG_LEVELS_VALIDOS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True)
class Config:
    """Todos los ajustes del pipeline. Congelado: nadie lo modifica a mitad de camino."""

    video_path: Path
    video_id: str
    model_path: Path
    output_dir: Path
    groundtruth_dir: Path
    confidence_threshold: float
    iou_threshold: float
    imgsz: int
    frame_stride: int
    max_frames: int
    device: str
    render_mode: str
    log_level: str


def _leer_float(env: Mapping[str, str], nombre: str, defecto: float,
                minimo: float, maximo: float) -> float:
    """Lee un decimal y verifica que este dentro del rango permitido."""
    crudo = env.get(nombre, str(defecto))
    try:
        valor = float(crudo)
    except ValueError:
        raise ConfigError(
            f"{nombre}={crudo!r} no es un numero. "
            f"Edita tu .env y pon un decimal entre {minimo} y {maximo} "
            f"(por defecto: {defecto})."
        ) from None
    if not minimo <= valor <= maximo:
        raise ConfigError(
            f"{nombre}={valor} esta fuera de rango. "
            f"Debe estar entre {minimo} y {maximo}. Edita tu .env "
            f"(por defecto: {defecto})."
        )
    return valor


def _leer_int(env: Mapping[str, str], nombre: str, defecto: int,
              minimo: int, maximo: int) -> int:
    """Lee un entero y verifica que este dentro del rango permitido."""
    crudo = env.get(nombre, str(defecto))
    try:
        valor = int(crudo)
    except ValueError:
        raise ConfigError(
            f"{nombre}={crudo!r} no es un numero entero. "
            f"Edita tu .env y pon un entero entre {minimo} y {maximo} "
            f"(por defecto: {defecto})."
        ) from None
    if not minimo <= valor <= maximo:
        raise ConfigError(
            f"{nombre}={valor} esta fuera de rango. "
            f"Debe estar entre {minimo} y {maximo}. Edita tu .env "
            f"(por defecto: {defecto})."
        )
    return valor


def _leer_opcion(env: Mapping[str, str], nombre: str, defecto: str,
                 validos: set[str]) -> str:
    """Lee un texto que solo puede tomar unos pocos valores conocidos."""
    valor = env.get(nombre, defecto).strip()
    if valor not in validos:
        opciones = ", ".join(sorted(validos))
        raise ConfigError(
            f"{nombre}={valor!r} no es un valor permitido. "
            f"Edita tu .env y usa uno de estos: {opciones} "
            f"(por defecto: {defecto})."
        )
    return valor


def _leer_ruta(env: Mapping[str, str], nombre: str, defecto: str) -> Path:
    """Lee una ruta. Si es relativa, la resuelve desde la raiz del repositorio.

    No comprueba que el archivo exista: en la Fase 1 todavia no hay video ni
    modelo. Esa comprobacion la hara quien abra el archivo (Fases 2 y 3).
    """
    crudo = env.get(nombre, defecto).strip()
    if not crudo:
        raise ConfigError(
            f"{nombre} esta vacio en tu .env. Copia .env.example a .env "
            f"y pon una ruta (por defecto: {defecto})."
        )
    ruta = Path(crudo)
    return ruta if ruta.is_absolute() else (RAIZ / ruta)


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Arma la configuracion y la valida.

    Si `env` es None lee el archivo .env y las variables del sistema. Pasarle un
    diccionario permite probarla en los tests sin tocar el entorno real.

    Lanza `ConfigError` con un mensaje que dice que corregir.
    """
    if env is None:
        load_dotenv(RAIZ / ".env")
        env = os.environ

    video_id = env.get("VIDEO_ID", "video_001").strip()
    if not video_id:
        raise ConfigError(
            "VIDEO_ID esta vacio en tu .env. Ponle una etiqueta corta al video, "
            "por ejemplo VIDEO_ID=video_001."
        )

    return Config(
        video_path=_leer_ruta(env, "VIDEO_PATH", "data/videos/scapder.mp4"),
        video_id=video_id,
        model_path=_leer_ruta(env, "MODEL_PATH", "data/models/yolo11n.pt"),
        output_dir=_leer_ruta(env, "OUTPUT_DIR", "data/output"),
        groundtruth_dir=_leer_ruta(env, "GROUNDTRUTH_DIR", "data/groundtruth"),
        confidence_threshold=_leer_float(env, "CONFIDENCE_THRESHOLD", 0.5, 0.0, 1.0),
        iou_threshold=_leer_float(env, "IOU_THRESHOLD", 0.45, 0.0, 1.0),
        imgsz=_leer_int(env, "IMGSZ", 640, 320, 1920),
        frame_stride=_leer_int(env, "FRAME_STRIDE", 1, 1, 100),
        max_frames=_leer_int(env, "MAX_FRAMES", 0, 0, 1_000_000),
        device=_leer_opcion(env, "DEVICE", "cpu", DEVICES_VALIDOS),
        render_mode=_leer_opcion(env, "RENDER_MODE", "privacy", RENDER_MODES_VALIDOS),
        log_level=_leer_opcion(env, "LOG_LEVEL", "INFO", LOG_LEVELS_VALIDOS),
    )
