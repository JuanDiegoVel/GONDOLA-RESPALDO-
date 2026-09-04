"""Dibuja las zonas de un archivo de calibracion sobre un frame real del video.

    python scripts/draw_zones.py
    python scripts/draw_zones.py --zones data/zones/video_001.json --frame 800

CONTIENE IMAGEN REAL: a diferencia del render 'privacy' del pipeline
(gondola/video/render.py), esta herramienta dibuja sobre un frame de verdad
de la camara -es justo lo que hace falta para calibrar zonas a ojo-. La
imagen que genera es de uso interno del equipo, igual que el render
'debug': NO se comparte fuera del equipo.

POR QUE EXISTE
---------------
Configurar rectangulos de zona a ciegas, solo mirando numeros de pixeles, es
una fuente enorme de errores: escribir que un estante va de x=100 a x=400 no
dice nada hasta que se ve dibujado sobre el frame real. Esta herramienta
cierra ese ciclo: edita el JSON, corre el script, mira la imagen, ajusta.

QUE NO HACE
------------
No decide en que zona esta una persona ni acumula dwell_time -eso es
gondola/stages/zones.py, todavia sin escribir. Esto solo dibuja rectangulos
sobre una imagen; es una herramienta de calibracion, no una etapa del
pipeline, y por eso no pasa por gondola/pipeline.py ni por `python -m gondola`.
"""

from __future__ import annotations

import argparse
import colorsys
import sys
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "ai-service"))

from gondola.errors import GondolaError  # noqa: E402
from gondola.zones_config import ZonesConfig, load_zones_config  # noqa: E402

FUENTE = cv2.FONT_HERSHEY_SIMPLEX
OPACIDAD_RELLENO = 0.28


def color_desde_texto(texto: str) -> tuple[int, int, int]:
    """Color BGR estable por texto (zone_id/segment), distinto de zona en zona.

    No usa `hash()` de Python porque no es estable entre ejecuciones (esta
    aleatorizado por proceso). Mismo esquema -angulo dorado sobre el circulo
    de tono- que `color_desde_id` en gondola/stages/track.py: una funcion
    determinista del texto, nada guardado ni derivado de ninguna persona.
    """
    semilla = sum(ord(c) for c in texto)
    tono = (semilla * 0.618033988749895) % 1.0
    r, g, b = colorsys.hsv_to_rgb(tono, 0.55, 0.95)
    return (int(b * 255), int(g * 255), int(r * 255))


def dibujar_zonas(frame, zonas: ZonesConfig):
    """Devuelve una COPIA de `frame` con todos los floor_zone superpuestos."""
    lienzo = frame.copy()
    for gondola, estante in zonas.shelves():
        color = color_desde_texto(f"{gondola.zone_id}/{estante.segment}")
        z = estante.floor_zone
        x1, y1 = int(z.x), int(z.y)
        x2, y2 = int(z.x + z.width), int(z.y + z.height)

        relleno = lienzo.copy()
        cv2.rectangle(relleno, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(relleno, OPACIDAD_RELLENO, lienzo, 1 - OPACIDAD_RELLENO, 0, lienzo)
        cv2.rectangle(lienzo, (x1, y1), (x2, y2), color, 2)

        etiqueta = f"{gondola.zone_id}/{estante.segment}"
        (ancho_txt, alto_txt), _ = cv2.getTextSize(etiqueta, FUENTE, 0.5, 1)
        cv2.rectangle(lienzo, (x1, y1), (x1 + ancho_txt + 6, y1 + alto_txt + 8), color, -1)
        cv2.putText(lienzo, etiqueta, (x1 + 3, y1 + alto_txt + 3), FUENTE, 0.5,
                    (20, 20, 20), 1, cv2.LINE_AA)
    return lienzo


def _dibujar_cabecera(lienzo, zonas: ZonesConfig, ruta_zonas: Path, indice: int) -> None:
    ancho = lienzo.shape[1]
    cv2.rectangle(lienzo, (0, 0), (ancho, 30), (0, 0, 0), -1)

    texto_izq = f"{ruta_zonas.name}   frame {indice}   {len(zonas.gondolas)} gondola(s)"
    cv2.putText(lienzo, texto_izq, (8, 20), FUENTE, 0.55, (235, 235, 235), 1, cv2.LINE_AA)

    texto_der = "CALIBRACION - imagen real, no compartir fuera del equipo"
    (ancho_txt, _), _ = cv2.getTextSize(texto_der, FUENTE, 0.45, 1)
    cv2.putText(lienzo, texto_der, (ancho - ancho_txt - 8, 20), FUENTE, 0.45,
                (80, 80, 235), 1, cv2.LINE_AA)


def _resolver_ruta(texto: str) -> Path:
    ruta = Path(texto)
    return ruta if ruta.is_absolute() else (RAIZ / ruta)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zones", default="data/zones/video_001.example.json",
                        help="Archivo de zonas a dibujar (por defecto, el ejemplo).")
    parser.add_argument("--video", default="data/videos/video_001.mp4",
                        help="Video sobre el que dibujar.")
    parser.add_argument("--frame", type=int, default=0,
                        help="Numero de frame a usar como fondo (por defecto, el primero).")
    parser.add_argument("--out", default=None,
                        help="Ruta de la imagen de salida. Por defecto, "
                             "data/output/<video_id del archivo de zonas>.zones.png")
    args = parser.parse_args(argv)

    ruta_zonas = _resolver_ruta(args.zones)
    ruta_video = _resolver_ruta(args.video)

    try:
        zonas = load_zones_config(ruta_zonas)
    except GondolaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not ruta_video.exists():
        print(f"ERROR: no encuentro el video en:\n    {ruta_video}", file=sys.stderr)
        return 1

    cap = cv2.VideoCapture(str(ruta_video))
    if not cap.isOpened():
        print(f"ERROR: OpenCV no pudo abrir {ruta_video}.", file=sys.stderr)
        return 1

    ancho_video = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto_video = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (ancho_video, alto_video) != (zonas.frame_width, zonas.frame_height):
        print(
            f"AVISO: {ruta_zonas.name} se calibro para "
            f"{zonas.frame_width}x{zonas.frame_height}, pero {ruta_video.name} mide "
            f"{ancho_video}x{alto_video}. Las zonas se van a ver desplazadas."
        )

    cap.set(cv2.CAP_PROP_POS_FRAMES, args.frame)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        print(f"ERROR: el video no tiene el frame {args.frame} (o esta corrupto).",
              file=sys.stderr)
        return 1

    lienzo = dibujar_zonas(frame, zonas)
    _dibujar_cabecera(lienzo, zonas, ruta_zonas, args.frame)

    if args.out:
        destino = _resolver_ruta(args.out)
    else:
        destino = RAIZ / "data" / "output" / f"{zonas.video_id}.zones.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(destino), lienzo)

    print(f"Zonas dibujadas: {len(zonas.shelves())} estante(s) en {len(zonas.gondolas)} gondola(s).")
    print(f"Imagen: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
