"""Configuracion del logging. Un solo lugar, un solo formato para todo el equipo."""

import logging
import sys

_FORMATO = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_FECHA = "%H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Deja el logging listo para escribir a la consola.

    Llamalo UNA vez, al arrancar el programa. Nunca desde dentro de una etapa:
    las etapas solo hacen `logger = logging.getLogger(__name__)`.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMATO, datefmt=_FECHA))

    raiz = logging.getLogger()
    raiz.handlers.clear()  # evita mensajes duplicados si se llama dos veces
    raiz.addHandler(handler)
    raiz.setLevel(level.upper())
