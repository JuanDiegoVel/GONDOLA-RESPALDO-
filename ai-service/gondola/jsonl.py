"""Lectura y escritura de archivos .jsonl, evento por evento.

POR QUE EN STREAMING
--------------------
Un video de 10 minutos puede dar mas de 50.000 eventos. Cargarlos todos en una
lista para luego escribirlos gasta cientos de MB de RAM sin ninguna necesidad:
cada evento se procesa una vez y se olvida.

Por eso `read_events` es un generador (entrega los eventos de a uno, segun se
piden) y `write_events` acepta cualquier iterable, incluido otro generador. Una
etapa completa se escribe asi, sin acumular nada en memoria:

    eventos = read_events(entrada)
    write_events(salida, (mi_transformacion(e) for e in eventos))
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from pydantic import ValidationError

from gondola.contract import Event
from gondola.errors import ContractError


def write_events(destino: Path, eventos: Iterable[Event]) -> int:
    """Escribe los eventos, uno por linea, y devuelve cuantos escribio.

    Crea la carpeta de salida si hace falta. Sobrescribe el archivo si ya
    existe: una etapa siempre produce su salida completa desde cero.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    escritos = 0
    with destino.open("w", encoding="utf-8", newline="\n") as archivo:
        for evento in eventos:
            archivo.write(evento.to_jsonl() + "\n")
            escritos += 1
    return escritos


def read_events(origen: Path) -> Iterator[Event]:
    """Lee los eventos de a uno, validando cada linea contra el contrato.

    Si una linea esta corrupta, el error dice el archivo y el NUMERO DE LINEA.
    En un archivo de 50.000 lineas, "algo fallo" no sirve de nada.

    Las lineas en blanco se ignoran: un salto de linea al final del archivo es
    normal y no es un error.
    """
    if not origen.exists():
        raise ContractError(
            f"No existe el archivo {origen}.\n"
            "Que hacer: corre antes la etapa que lo produce "
            "(python -m gondola doctor te dice cuales existen ya)."
        )

    with origen.open("r", encoding="utf-8") as archivo:
        for numero, linea in enumerate(archivo, start=1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield Event.from_jsonl(linea)
            except (ContractError, ValidationError) as exc:
                raise ContractError(
                    f"{origen.name}, linea {numero}: no cumple el contrato.\n{exc}"
                ) from exc


def count_events(origen: Path) -> int:
    """Cuenta los eventos de un archivo sin cargarlo en memoria."""
    return sum(1 for _ in read_events(origen))
