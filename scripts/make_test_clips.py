"""Genera clips sinteticos en data/videos/ para trabajar sin el video de Scapder.

    python scripts/make_test_clips.py

Produce dos clips:

    clip_vacio.mp4    Una escena quieta, sin nada que se mueva.
    clip_formas.mp4   Rectangulos deslizandose, como estanterias vistas de lado.

======================================================================
QUE PRUEBAN ESTOS CLIPS Y QUE NO
======================================================================

Los dos son CONTROLES NEGATIVOS: no hay una sola persona en ninguno, asi que
la deteccion DEBE dar cero en ambos. Si da mas de cero, tenemos falsos
positivos y hay que subir CONFIDENCE_THRESHOLD o revisar el modelo.

LO QUE ESTO PRUEBA:
    Que el sistema no se inventa personas donde no las hay.
    Que el pipeline corre de principio a fin sin reventar.
    Que los archivos de salida se escriben con el formato correcto.

LO QUE ESTO **NO** PRUEBA, Y ES IMPORTANTE DECIRLO:
    NO prueba que el sistema detecte bien a las personas. Un detector
    completamente roto, que nunca encuentre nada, tambien sacaria cero aqui y
    pasaria esta prueba con nota.

    Medir si detecta BIEN (precision y recall) exige video con personas reales
    y anotaciones hechas a mano en data/groundtruth/. Eso es la Fase 5. Hasta
    entonces, un cero en estos clips significa "no alucina", nunca "funciona".
"""

from pathlib import Path

import cv2
import numpy as np

# Raiz del repositorio (este script esta en <raiz>/scripts/).
RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "data" / "videos"

ANCHO, ALTO = 640, 480
FPS = 25
SEGUNDOS = 6
TOTAL_FRAMES = FPS * SEGUNDOS

GRIS_PARED = (150, 148, 145)
GRIS_PISO = (110, 108, 106)
AZUL_ESTANTE = (140, 110, 70)


def _abrir_writer(nombre: str) -> cv2.VideoWriter:
    DESTINO.mkdir(parents=True, exist_ok=True)
    ruta = DESTINO / nombre
    codec = cv2.VideoWriter.fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(ruta), codec, FPS, (ANCHO, ALTO))
    if not writer.isOpened():
        raise SystemExit(f"No pude crear {ruta}. Comprueba permisos de escritura.")
    return writer


def _escena_base() -> np.ndarray:
    """Pared y piso. El fondo comun de los dos clips."""
    frame = np.full((ALTO, ANCHO, 3), GRIS_PARED, dtype=np.uint8)
    cv2.rectangle(frame, (0, 330), (ANCHO, ALTO), GRIS_PISO, -1)
    return frame


def hacer_clip_vacio() -> Path:
    """Escena quieta. El caso mas facil: si aqui detecta algo, algo va muy mal."""
    writer = _abrir_writer("clip_vacio.mp4")
    for _ in range(TOTAL_FRAMES):
        frame = _escena_base()
        # Un poco de ruido para que no sea un color plano perfecto, que no se
        # parece en nada a la senal de una camara real.
        ruido = np.random.randint(-6, 7, frame.shape, dtype=np.int16)
        writer.write(np.clip(frame.astype(np.int16) + ruido, 0, 255).astype(np.uint8))
    writer.release()
    return DESTINO / "clip_vacio.mp4"


def hacer_clip_formas() -> Path:
    """Rectangulos moviendose. Hay movimiento, pero ninguno es una persona."""
    writer = _abrir_writer("clip_formas.mp4")
    for indice in range(TOTAL_FRAMES):
        frame = _escena_base()
        avance = indice * 3

        # Tres "estanterias" deslizandose de derecha a izquierda.
        for i, (ancho_caja, alto_caja, y) in enumerate(
            [(120, 180, 150), (90, 140, 190), (150, 100, 230)]
        ):
            x = (ANCHO - (avance + i * 220) % (ANCHO + 200))
            cv2.rectangle(frame, (x, y), (x + ancho_caja, y + alto_caja),
                          AZUL_ESTANTE, -1)
            # Un par de baldas horizontales.
            for k in (1, 2):
                y_balda = y + (alto_caja * k) // 3
                cv2.line(frame, (x, y_balda), (x + ancho_caja, y_balda),
                         (90, 70, 45), 2)

        ruido = np.random.randint(-6, 7, frame.shape, dtype=np.int16)
        writer.write(np.clip(frame.astype(np.int16) + ruido, 0, 255).astype(np.uint8))
    writer.release()
    return DESTINO / "clip_formas.mp4"


def main() -> None:
    print("Generando clips de prueba...")
    for hacer in (hacer_clip_vacio, hacer_clip_formas):
        ruta = hacer()
        kb = ruta.stat().st_size / 1024
        print(f"  {ruta}  ({ANCHO}x{ALTO}, {SEGUNDOS}s @ {FPS}fps, {kb:.0f} KB)")

    print()
    print("Los dos son CONTROLES NEGATIVOS: no hay ninguna persona en ellos.")
    print("La deteccion DEBE dar 0 en ambos:")
    print()
    print("    cd ai-service")
    print("    python -m gondola detect --video data/videos/clip_formas.mp4")
    print()
    print("Un 0 significa que el sistema no se inventa personas. NO significa")
    print("que detecte bien: eso solo se puede medir con video real y las")
    print("anotaciones manuales de data/groundtruth/ (Fase 5).")


if __name__ == "__main__":
    main()
