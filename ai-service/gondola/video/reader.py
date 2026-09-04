"""Lectura de video con OpenCV.

Este es el unico modulo que abre archivos de video. Si manana cambiamos de
libreria, solo se toca aqui.

OpenCV avisa de los errores devolviendo False o None, nunca lanzando
excepciones. Si no se comprueba cada retorno, el fallo aparece 200 lineas
despues como un "NoneType no tiene shape" que no le dice nada a nadie. Por eso
aqui se comprueba todo y se traduce a errores del proyecto.

OpenCV y numpy no estan en requirements-dev.txt (ver docstring de
gondola/stages/detect.py), asi que se importan dentro de los metodos: crear
un VideoReader sobre un video que no existe debe fallar con MissingInputError
sin necesitar cv2 instalado.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from gondola.errors import MissingInputError, VideoError

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class VideoInfo:
    """Lo que sabemos del video antes de empezar a leerlo."""

    path: Path
    fps: float
    width: int
    height: int
    frame_count: int

    @property
    def duration_s(self) -> float:
        """Duracion en segundos. 0 si el contenedor no reporta el total de frames."""
        return self.frame_count / self.fps if self.fps > 0 else 0.0

    def resumen(self) -> str:
        return (
            f"{self.width}x{self.height} @ {self.fps:.2f} fps, "
            f"{self.frame_count} frames ({self.duration_s:.1f} s)"
        )


class VideoReader:
    """Lee un video frame por frame. Usar siempre como context manager:

        with VideoReader(ruta) as video:
            print(video.info.resumen())
            for indice, timestamp, frame in video.frames(stride=2):
                ...

    Asi el archivo se cierra aunque el proceso falle a mitad de camino.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

        if not self.path.exists():
            raise MissingInputError(
                f"No encuentro el video en:\n"
                f"    {self.path}\n\n"
                f"Que hacer, una de dos:\n"
                f"  1. Deja el video en data/videos/ y ajusta VIDEO_PATH en tu .env\n"
                f"     (ver data/videos/README.md).\n"
                f"  2. O pasa la ruta directamente:\n"
                f"     python -m gondola detect --video ruta/a/tu/video.mp4\n\n"
                f"Si todavia no tienes el video de Scapder, genera clips de prueba:\n"
                f"     python scripts/make_test_clips.py"
            )

        import cv2

        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            raise VideoError(
                f"OpenCV no pudo abrir el video:\n"
                f"    {self.path}\n\n"
                f"Suele ser el archivo corrupto o un codec no soportado. "
                f"Que hacer: prueba a reconvertirlo a H.264/mp4, por ejemplo con\n"
                f"    ffmpeg -i tu_video.ext -c:v libx264 salida.mp4"
            )

        self.info = self._leer_info()

    def _leer_info(self) -> VideoInfo:
        """Lee las propiedades del video y comprueba que tengan sentido."""
        import cv2

        fps = float(self._cap.get(cv2.CAP_PROP_FPS))
        ancho = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if fps <= 0:
            self.close()
            raise VideoError(
                f"El video {self.path.name} reporta {fps} fps, lo cual es imposible.\n"
                f"Sin los fps no se puede calcular el timestamp de cada frame, y el "
                f"timestamp es lo que la Persona 4 usa para medir permanencia.\n"
                f"Que hacer: reconvierte el archivo con\n"
                f"    ffmpeg -i tu_video.ext -c:v libx264 salida.mp4"
            )
        if ancho <= 0 or alto <= 0:
            self.close()
            raise VideoError(
                f"El video {self.path.name} reporta un tamano invalido "
                f"({ancho}x{alto}). El archivo esta corrupto o incompleto."
            )

        return VideoInfo(
            path=self.path,
            fps=fps,
            width=ancho,
            height=alto,
            frame_count=max(total, 0),  # algunos contenedores reportan -1
        )

    def frames(
        self, stride: int = 1, max_frames: int = 0
    ) -> Iterator[tuple[int, float, np.ndarray]]:
        """Entrega (indice_de_frame, timestamp_en_segundos, imagen).

        IMPORTANTE: `indice_de_frame` es el numero del frame EN EL VIDEO
        ORIGINAL. Con stride=5 la secuencia va 0, 5, 10, 15... y NO se renumera
        a 0, 1, 2, 3. La Persona 4 necesita el indice real para calcular tiempos:
        si renumeraramos, un video de 10 minutos pareceria durar 2.

        `max_frames` cuenta frames ENTREGADOS, no recorridos: con stride=5 y
        max_frames=100 se leen 500 frames del video y se entregan 100.
        """
        if stride < 1:
            raise VideoError(f"El stride debe ser 1 o mas, no {stride}.")

        indice = 0
        entregados = 0
        while True:
            if max_frames > 0 and entregados >= max_frames:
                break

            # grab() avanza sin decodificar la imagen; solo decodificamos
            # (retrieve) los frames que de verdad vamos a usar. Con stride alto
            # esto ahorra bastante trabajo.
            if not self._cap.grab():
                break  # fin del video

            if indice % stride == 0:
                ok, frame = self._cap.retrieve()
                if not ok or frame is None:
                    # Un frame suelto ilegible no debe tumbar todo el proceso.
                    indice += 1
                    continue
                yield indice, indice / self.info.fps, frame
                entregados += 1

            indice += 1

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "VideoReader":
        return self

    def __exit__(self, *_) -> None:
        self.close()
