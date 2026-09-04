"""Evaluacion: cuanto acierta el sistema, comparado contra anotaciones humanas.

    python -m gondola eval

ADVERTENCIA QUE HAY QUE LEER ENTERA
-----------------------------------
Este modulo NO mide nada por si solo. Compara la salida del pipeline contra un
archivo CSV que una persona llena a mano viendo el video (el "ground truth",
o verdad de referencia).

SIN ESE ARCHIVO NO SE PUEDE AFIRMAR NADA SOBRE LA EXACTITUD DEL SISTEMA.

Hoy no tenemos anotaciones: existen el formato, el lector y el calculo, y
estan probados con datos sinteticos. Publicar una cifra de precision sin
haber anotado video real seria inventarsela, y eso es exactamente lo que este
modulo esta hecho para evitar.

COMO SE COMPARA
---------------
Un evento anotado y uno detectado se consideran el mismo si coinciden en tipo
y en zona, y ocurren dentro de una tolerancia de tiempo (por defecto 2
segundos). La tolerancia existe porque una persona anotando a mano no acierta
al frame exacto: escribe "sobre el segundo 12" y el sistema dice 12.4.

    Verdadero positivo (TP)  el sistema lo detecto y estaba anotado    -> acierto
    Falso positivo (FP)      el sistema lo detecto y NO estaba         -> se lo invento
    Falso negativo (FN)      estaba anotado y el sistema no lo vio     -> se lo perdio

    precision = TP / (TP + FP)   de lo que dijo, cuanto era cierto
    recall    = TP / (TP + FN)   de lo que habia, cuanto encontro
    F1        = media armonica de las dos
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from gondola.errors import GondolaError
from gondola.jsonl import read_events

TOLERANCIA_POR_DEFECTO_S = 2.0

COLUMNAS = ("video_id", "timestamp", "zone_id", "event")


@dataclass(frozen=True)
class Anotacion:
    """Una linea del CSV: un evento que una persona vio en el video."""

    video_id: str
    timestamp: float
    zone_id: str
    event: str


@dataclass(frozen=True)
class Puntaje:
    """Precision, recall y F1 de un tipo de evento."""

    etiqueta: str
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        """De lo que el sistema dijo, cuanto era cierto. 0.0 si no dijo nada."""
        total = self.tp + self.fp
        return self.tp / total if total else 0.0

    @property
    def recall(self) -> float:
        """De lo que habia, cuanto encontro. 0.0 si no habia nada anotado."""
        total = self.tp + self.fn
        return self.tp / total if total else 0.0

    @property
    def f1(self) -> float:
        """Media armonica. Castiga que una de las dos sea mala."""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def anotados(self) -> int:
        return self.tp + self.fn

    @property
    def detectados(self) -> int:
        return self.tp + self.fp


def leer_groundtruth(ruta: Path) -> list[Anotacion]:
    """Lee el CSV de anotaciones manuales. Ver docs/evaluation.md.

    Los errores dicen la linea exacta: quien anota trabaja en una hoja de
    calculo y necesita saber que fila corregir.
    """
    if not ruta.exists():
        raise GondolaError(
            f"No existe el archivo de anotaciones:\n    {ruta}\n\n"
            f"Que hacer: crea un CSV con las columnas {', '.join(COLUMNAS)} "
            f"siguiendo data/groundtruth/ejemplo.csv y el formato descrito en "
            f"docs/evaluation.md."
        )

    anotaciones: list[Anotacion] = []
    with ruta.open("r", encoding="utf-8", newline="") as archivo:
        lector = csv.DictReader(archivo)

        faltan = set(COLUMNAS) - set(lector.fieldnames or [])
        if faltan:
            raise GondolaError(
                f"A {ruta.name} le faltan columnas: {sorted(faltan)}.\n"
                f"La primera fila debe ser exactamente:  {','.join(COLUMNAS)}"
            )

        for numero, fila in enumerate(lector, start=2):  # 1 es la cabecera
            if not any((fila.get(c) or "").strip() for c in COLUMNAS):
                continue  # fila en blanco al final de la hoja de calculo
            try:
                timestamp = float((fila["timestamp"] or "").strip())
            except ValueError:
                raise GondolaError(
                    f"{ruta.name}, linea {numero}: timestamp "
                    f"{fila['timestamp']!r} no es un numero. Escribe los "
                    f"segundos, por ejemplo 12.5"
                ) from None
            if timestamp < 0:
                raise GondolaError(
                    f"{ruta.name}, linea {numero}: timestamp negativo ({timestamp})."
                )
            anotaciones.append(
                Anotacion(
                    video_id=(fila["video_id"] or "").strip(),
                    timestamp=timestamp,
                    zone_id=(fila["zone_id"] or "").strip(),
                    event=(fila["event"] or "").strip().upper(),
                )
            )
    return anotaciones


def eventos_detectados(ruta_jsonl: Path) -> list[Anotacion]:
    """Extrae del .jsonl los eventos de interaccion, en el mismo formato que el CSV.

    Solo cuentan las lineas que tienen `interaction.event` relleno: el resto son
    detecciones de personas, no eventos de interaccion, y no hay nada que
    comparar con ellas.
    """
    detectados = []
    for evento in read_events(ruta_jsonl):
        if evento.interaction.event is None:
            continue
        detectados.append(
            Anotacion(
                video_id=evento.video_id,
                timestamp=evento.timestamp,
                zone_id=evento.zone.zone_id or "",
                event=evento.interaction.event.value,
            )
        )
    return detectados


def emparejar(
    anotados: list[Anotacion],
    detectados: list[Anotacion],
    tolerancia_s: float = TOLERANCIA_POR_DEFECTO_S,
) -> tuple[int, int, int]:
    """Empareja anotaciones con detecciones. Devuelve (TP, FP, FN).

    Cada anotacion se empareja con UNA sola deteccion, la mas cercana en el
    tiempo dentro de la tolerancia. Si dos detecciones caen cerca de la misma
    anotacion, una es acierto y la otra es falso positivo: el sistema conto el
    mismo evento dos veces y eso hay que penalizarlo.
    """
    sin_usar = list(range(len(detectados)))
    aciertos = 0

    for anotacion in anotados:
        mejor_indice = None
        mejor_distancia = tolerancia_s

        for i in sin_usar:
            candidato = detectados[i]
            if candidato.event != anotacion.event:
                continue
            if candidato.zone_id != anotacion.zone_id:
                continue
            distancia = abs(candidato.timestamp - anotacion.timestamp)
            if distancia <= mejor_distancia:
                mejor_distancia = distancia
                mejor_indice = i

        if mejor_indice is not None:
            sin_usar.remove(mejor_indice)
            aciertos += 1

    return aciertos, len(sin_usar), len(anotados) - aciertos


def evaluar(
    anotados: list[Anotacion],
    detectados: list[Anotacion],
    tolerancia_s: float = TOLERANCIA_POR_DEFECTO_S,
) -> list[Puntaje]:
    """Calcula los puntajes por tipo de evento, mas uno global.

    Se separa por tipo porque no es lo mismo fallar en APPROACH (acercarse, que
    pasa constantemente) que en PICK_UP (tomar un producto, que es el evento
    que de verdad importa para el planograma).
    """
    tipos = sorted({a.event for a in anotados} | {d.event for d in detectados})

    puntajes = []
    for tipo in tipos:
        tp, fp, fn = emparejar(
            [a for a in anotados if a.event == tipo],
            [d for d in detectados if d.event == tipo],
            tolerancia_s,
        )
        puntajes.append(Puntaje(etiqueta=tipo, tp=tp, fp=fp, fn=fn))

    tp, fp, fn = emparejar(anotados, detectados, tolerancia_s)
    puntajes.append(Puntaje(etiqueta="TOTAL", tp=tp, fp=fp, fn=fn))
    return puntajes


def imprimir_evaluacion(puntajes: list[Puntaje], tolerancia_s: float) -> None:
    """Imprime la tabla de resultados."""
    print("=" * 72)
    print(f"  EVALUACION   (tolerancia temporal: +/- {tolerancia_s} s)")
    print("=" * 72)
    print(f"  {'evento':<12} {'anotados':>9} {'detectados':>11} "
          f"{'TP':>5} {'FP':>5} {'FN':>5} {'prec':>7} {'recall':>7} {'F1':>7}")
    print("  " + "-" * 68)
    for p in puntajes:
        separador = "  " + "-" * 68 if p.etiqueta == "TOTAL" else None
        if separador:
            print(separador)
        print(f"  {p.etiqueta:<12} {p.anotados:>9} {p.detectados:>11} "
              f"{p.tp:>5} {p.fp:>5} {p.fn:>5} "
              f"{p.precision:>7.3f} {p.recall:>7.3f} {p.f1:>7.3f}")
    print("=" * 72)
    print("  precision = de lo que el sistema dijo, cuanto era cierto")
    print("  recall    = de lo que habia en el video, cuanto encontro")
    print("  F1        = media armonica de las dos")
    print()
    print("  Estas cifras valen exactamente lo que valga el archivo de")
    print("  anotaciones. Si se anoto poco video, o se anoto mal, el numero")
    print("  no significa nada aunque salga alto.")
