"""Video de salida, en dos modos muy distintos.

    privacy  (POR DEFECTO)  Fondo neutro, SIN NINGUNA IMAGEN REAL. Solo los
                            rectangulos, el numero de frame, el timestamp y el
                            conteo de personas. Se puede proyectar ante un
                            jurado, subir a una presentacion o mandar por
                            correo sin exponer a nadie: literalmente no
                            contiene un solo pixel de la tienda.
    debug                   Cajas verdes sobre el video original. Sirve para
                            comprobar que la deteccion esta bien puesta. NO se
                            comparte: contiene imagenes de personas reales.
    none                    No genera video. Mas rapido.

El modo privacy no es una version censurada del modo debug: es un video que se
dibuja desde cero sobre un lienzo vacio. El frame original ni siquiera se le
pasa. Esa es la diferencia entre tapar los datos y no tenerlos.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np

from gondola.contract import Event
from gondola.errors import VideoError

# Colores en BGR, que es el orden que usa OpenCV.
VERDE = (80, 220, 80)
GRIS_FONDO = (32, 32, 34)
GRIS_REJILLA = (48, 48, 52)
BLANCO = (235, 235, 235)
GRIS_TEXTO = (150, 150, 150)

FUENTE = cv2.FONT_HERSHEY_SIMPLEX


class Renderer:
    """Escribe el video de salida. Usar como context manager.

    En modo 'none' no crea ningun archivo y `write` no hace nada: asi quien
    llama no necesita repetir `if modo != "none"` en cada frame.
    """

    def __init__(self, destino: Path, modo: str, ancho: int, alto: int, fps: float):
        self.modo = modo
        self.destino = destino
        self.ancho = ancho
        self.alto = alto
        self._writer = None

        if modo == "none":
            return

        destino.parent.mkdir(parents=True, exist_ok=True)
        # VideoWriter.fourcc es la forma moderna; funciona en OpenCV 4 y 5.
        codec = cv2.VideoWriter.fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(destino), codec, fps, (ancho, alto))
        if not writer.isOpened():
            raise VideoError(
                f"No pude crear el video de salida en:\n    {destino}\n\n"
                f"Que hacer: comprueba que la carpeta se pueda escribir, o corre "
                f"con --render none si no necesitas video."
            )
        self._writer = writer

    def write(
        self,
        frame_original,
        eventos: Sequence[Event],
        indice: int,
        timestamp: float,
        color_de: Callable[[Event], tuple[int, int, int]] | None = None,
        etiqueta_de: Callable[[Event], str] | None = None,
    ) -> None:
        """Escribe un frame. En modo privacy, `frame_original` se ignora.

        `color_de` y `etiqueta_de` son opcionales: sin ellos, cada caja sale
        verde con su confianza (lo que necesita `detect`). Pasarlos permite
        que otra etapa (por ejemplo `track`, con su track_id) dibuje distinto
        sin duplicar nada de OpenCV fuera de este modulo.
        """
        if self._writer is None:
            return

        if self.modo == "privacy":
            lienzo = self._lienzo_neutro()
        else:
            lienzo = frame_original.copy()

        for evento in eventos:
            color = color_de(evento) if color_de else VERDE
            etiqueta = etiqueta_de(evento) if etiqueta_de else f"person {evento.detection.confidence:.2f}"
            self._dibujar_caja(lienzo, evento, color, etiqueta)

        self._dibujar_cabecera(lienzo, indice, timestamp, len(eventos))
        self._writer.write(lienzo)

    def _lienzo_neutro(self) -> np.ndarray:
        """Un fondo gris con una rejilla suave. Cero informacion de la tienda."""
        lienzo = np.full((self.alto, self.ancho, 3), GRIS_FONDO, dtype=np.uint8)
        paso = 80
        for x in range(paso, self.ancho, paso):
            cv2.line(lienzo, (x, 0), (x, self.alto), GRIS_REJILLA, 1)
        for y in range(paso, self.alto, paso):
            cv2.line(lienzo, (0, y), (self.ancho, y), GRIS_REJILLA, 1)
        return lienzo

    def _dibujar_caja(
        self,
        lienzo: np.ndarray,
        evento: Event,
        color: tuple[int, int, int] = VERDE,
        etiqueta: str | None = None,
    ) -> None:
        """Dibuja el rectangulo, su etiqueta y el punto de apoyo, en el color dado.

        Sin `color` ni `etiqueta` se comporta como siempre (verde, confianza):
        son opcionales para que `write()` pueda pasarlos por track, y para que
        una caja se pueda dibujar suelta (como hacen los tests) sin tener que
        inventarselos.
        """
        if etiqueta is None:
            etiqueta = f"person {evento.detection.confidence:.2f}"
        caja = evento.detection.bbox
        x1, y1 = int(caja.x), int(caja.y)
        x2, y2 = int(caja.x + caja.width), int(caja.y + caja.height)

        cv2.rectangle(lienzo, (x1, y1), (x2, y2), color, 2)

        (ancho_txt, alto_txt), _ = cv2.getTextSize(etiqueta, FUENTE, 0.5, 1)
        cv2.rectangle(lienzo, (x1, y1 - alto_txt - 6), (x1 + ancho_txt + 6, y1), color, -1)
        cv2.putText(lienzo, etiqueta, (x1 + 3, y1 - 4), FUENTE, 0.5, (20, 20, 20), 1,
                    cv2.LINE_AA)

        # El punto de apoyo (los pies): lo que la Persona 4 usara para ubicar a
        # la persona en el plano del piso.
        px, py = caja.support_point
        cv2.circle(lienzo, (int(px), int(py)), 4, color, -1)

    def _dibujar_cabecera(self, lienzo, indice: int, timestamp: float, personas: int) -> None:
        """Frame, timestamp y conteo. En privacy es toda la informacion que hay."""
        cv2.rectangle(lienzo, (0, 0), (self.ancho, 34), (0, 0, 0), -1)
        izquierda = f"frame {indice}   t={timestamp:6.2f}s   personas: {personas}"
        cv2.putText(lienzo, izquierda, (10, 22), FUENTE, 0.6, BLANCO, 1, cv2.LINE_AA)

        derecha = "SIN IMAGEN REAL" if self.modo == "privacy" else "MODO DEBUG - NO COMPARTIR"
        color = GRIS_TEXTO if self.modo == "privacy" else (80, 80, 235)
        (ancho_txt, _), _ = cv2.getTextSize(derecha, FUENTE, 0.5, 1)
        cv2.putText(lienzo, derecha, (self.ancho - ancho_txt - 10, 22), FUENTE, 0.5,
                    color, 1, cv2.LINE_AA)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None

    def __enter__(self) -> "Renderer":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def abrir_con_el_sistema(ruta: Path) -> None:
    """Abre el video con el reproductor por defecto del sistema operativo."""
    import subprocess
    import sys

    try:
        if sys.platform == "win32":
            import os

            os.startfile(ruta)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(ruta)], check=False)
        else:
            subprocess.run(["xdg-open", str(ruta)], check=False)
    except OSError as exc:
        # No poder abrir el reproductor no es motivo para fallar: el video ya
        # esta escrito y la ruta se acaba de imprimir.
        print(f"  (no pude abrir el reproductor: {exc})")
