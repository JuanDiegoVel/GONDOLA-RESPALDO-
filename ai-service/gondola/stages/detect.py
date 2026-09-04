"""Etapa 1: deteccion de personas con YOLO. Responsable: Persona 2.

QUE HACE
--------
Recorre el video frame por frame, le pasa cada imagen al modelo y, por cada
persona que encuentra, escribe un evento del contrato con su caja y su
confianza. Nada mas. El track_id, la zona y la interaccion los rellenan otras
personas: aqui van en null a proposito.

POR QUE LOS IMPORTS PESADOS ESTAN DENTRO DE LAS FUNCIONES
---------------------------------------------------------
`import ultralytics` arrastra PyTorch (unos 3 GB) y tarda varios segundos;
OpenCV tampoco esta en requirements-dev.txt. Si estuvieran arriba del archivo,
nadie del equipo podria correr `pytest` sin instalarlo todo, porque importar
este modulo lo importaria todo.

Poniendolos dentro de las funciones, los tests unitarios importan `detect` sin
problema y solo quien ejecuta la deteccion de verdad paga el precio.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from gondola import pipeline
from gondola.config import Config
from gondola.contract import CONTRACT_VERSION, BBox, Detection, Event
from gondola.errors import ModelError
from gondola.jsonl import write_events

# gondola.video.* importa OpenCV, y OpenCV no esta en requirements-dev.txt.
# Los imports van dentro de run() para que estos tests unitarios (filtrado de
# clase, recorte de cajas, construccion del evento) corran sin instalar nada
# pesado. Ver el docstring de arriba.

CLASE_PERSONA = "person"
"""La unica clase que nos interesa. Todo lo demas se descarta."""

AREA_MINIMA_PX = 4.0
"""Una caja mas pequena que esto no puede ser una persona: es ruido del modelo."""

FRAMES_ENTRE_AVISOS = 25
"""Cada cuantos frames se informa del progreso. En CPU esto tarda y hay que
saber que el proceso no se colgo."""


@dataclass(frozen=True)
class DeteccionCruda:
    """Lo que devuelve YOLO por cada caja, antes de validarlo.

    Existe para poder probar toda la logica de filtrado y recorte sin tener
    YOLO instalado: los tests construyen estas a mano.
    """

    class_id: int
    class_name: str
    confidence: float
    xyxy: tuple[float, float, float, float]  # x1, y1, x2, y2 en pixeles


@dataclass
class Resumen:
    """Lo que se va contando durante la corrida y acaba en el JSON de resumen."""

    frames_procesados: int = 0
    frames_con_personas: int = 0
    detecciones_totales: int = 0
    descartadas_por_clase: int = 0
    descartadas_por_caja: int = 0


# --------------------------------------------------------------------------
# Logica pura: se prueba sin YOLO y sin video
# --------------------------------------------------------------------------

def recortar_bbox(
    xyxy: tuple[float, float, float, float], ancho: int, alto: int
) -> BBox | None:
    """Recorta la caja al tamano del frame. Devuelve None si queda degenerada.

    YOLO a veces devuelve cajas que se salen de la imagen (una persona cortada
    por el borde). Si no se recortan, la Persona 4 acaba con un punto de apoyo
    fuera del plano del piso y no entiende por que.
    """
    x1, y1, x2, y2 = xyxy

    # Ordenar por si vinieran al reves, y recortar al frame.
    izq = max(0.0, min(x1, x2))
    arr = max(0.0, min(y1, y2))
    der = min(float(ancho), max(x1, x2))
    aba = min(float(alto), max(y1, y2))

    w = der - izq
    h = aba - arr
    if w <= 0 or h <= 0 or (w * h) < AREA_MINIMA_PX:
        return None

    return BBox(x=izq, y=arr, width=w, height=h)


def construir_evento(
    cruda: DeteccionCruda,
    video_id: str,
    frame_idx: int,
    timestamp: float,
    ancho: int,
    alto: int,
) -> Event | None:
    """Convierte una deteccion de YOLO en un evento del contrato.

    Devuelve None si hay que descartarla: no es una persona o la caja no sirve.

    La clase se vuelve a comprobar AQUI aunque ya se haya filtrado en el modelo.
    Parece redundante y no lo es: si manana alguien cambia MODEL_PATH por un
    modelo reentrenado, los numeros de clase cambian de significado (el 0 puede
    dejar de ser 'person') y el filtro del modelo pasaria coches por personas
    sin que nadie se entere. Comprobar el NOMBRE aqui hace que ese cambio se
    note al instante.
    """
    if cruda.class_name.lower() != CLASE_PERSONA:
        return None

    caja = recortar_bbox(cruda.xyxy, ancho, alto)
    if caja is None:
        return None

    return Event(
        video_id=video_id,
        frame=frame_idx,
        timestamp=timestamp,
        detection=Detection(confidence=cruda.confidence, bbox=caja),
        # track_id, zone, interaction y metrics se quedan en null: son de las
        # Personas 3, 4 y 5. Esta etapa no los toca.
    )


def estimacion_honesta(fps_procesamiento: float, stride: int) -> str:
    """Extrapola cuanto tardaria un video de 10 minutos a 25 fps.

    Se calcula con la velocidad REAL que acabamos de medir, no con un numero
    inventado. Si el stride es mayor que 1, se dice, porque cambia el resultado.
    """
    if fps_procesamiento <= 0:
        return "No pude medir la velocidad (muy pocos frames)."

    frames_totales = 10 * 60 * 25          # 15.000 frames
    frames_a_procesar = frames_totales / stride
    segundos = frames_a_procesar / fps_procesamiento

    nota = "" if stride == 1 else f" (con --stride {stride}, o sea 1 de cada {stride} frames)"
    return (
        f"A esta velocidad ({fps_procesamiento:.1f} frames/s), un video de "
        f"10 minutos a 25 fps tardaria unos {segundos / 60:.1f} minutos{nota}."
    )


# --------------------------------------------------------------------------
# Lo que necesita YOLO
# --------------------------------------------------------------------------

def _cargar_modelo(cfg: Config):
    """Carga el modelo y devuelve (modelo, ids_de_persona).

    Si el archivo no existe, ultralytics descarga el modelo la primera vez.
    """
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ModelError(
            "Falta ultralytics (y con el, PyTorch).\n"
            "Que hacer:  pip install -r requirements.txt\n"
            "Ojo: son unos 3 GB. Para los tests no hace falta."
        ) from exc

    ruta = cfg.model_path
    if not ruta.exists():
        print(f"  El modelo no esta en {ruta}")
        print("  Descargandolo (solo la primera vez)...")
        ruta.parent.mkdir(parents=True, exist_ok=True)

    try:
        modelo = YOLO(str(ruta))
    except Exception as exc:  # ultralytics lanza de todo: red, archivo, torch
        raise ModelError(
            f"No pude cargar el modelo desde {ruta}.\n"
            f"Detalle: {exc}\n\n"
            f"Que hacer: comprueba MODEL_PATH en tu .env, o borra el archivo "
            f"para que se vuelva a descargar."
        ) from exc

    ids = [i for i, nombre in modelo.names.items() if str(nombre).lower() == CLASE_PERSONA]
    if not ids:
        clases = ", ".join(sorted(str(n) for n in modelo.names.values())[:10])
        raise ModelError(
            f"El modelo {ruta.name} no tiene ninguna clase '{CLASE_PERSONA}'.\n"
            f"Sus clases son: {clases}...\n\n"
            f"Que hacer: usa un modelo entrenado en COCO (yolo11n.pt) o ajusta "
            f"MODEL_PATH en tu .env."
        )
    return modelo, ids


def _detectar_en_frame(modelo, frame, ids_persona: list[int], cfg: Config) -> Iterator[DeteccionCruda]:
    """Pasa un frame por el modelo y entrega sus detecciones en crudo.

    `classes=ids_persona` hace que el propio modelo descarte todo lo que no sea
    una persona. Es mucho mas rapido que filtrarlo despues, y ademas significa
    que las cajas de coches, sillas o botellas no llegan siquiera a existir en
    memoria.
    """
    resultados = modelo.predict(
        frame,
        classes=ids_persona,
        conf=cfg.confidence_threshold,
        iou=cfg.iou_threshold,
        imgsz=cfg.imgsz,
        device=cfg.device,
        verbose=False,
    )
    for resultado in resultados:
        for caja in resultado.boxes:
            class_id = int(caja.cls.item())
            yield DeteccionCruda(
                class_id=class_id,
                class_name=str(modelo.names.get(class_id, "")),
                confidence=float(caja.conf.item()),
                xyxy=tuple(float(v) for v in caja.xyxy[0].tolist()),
            )


def _eventos_del_video(
    modelo, ids_persona: list[int], video, cfg: Config,
    resumen: Resumen, renderer,
) -> Iterator[Event]:
    """Recorre el video y entrega los eventos de a uno, sin acumularlos.

    Es un generador para que `write_events` los vaya escribiendo segun salen:
    un video de 10 minutos puede dar mas de 50.000 eventos.
    """
    info = video.info
    for indice, timestamp, frame in video.frames(cfg.frame_stride, cfg.max_frames):
        eventos_del_frame = []
        for cruda in _detectar_en_frame(modelo, frame, ids_persona, cfg):
            evento = construir_evento(
                cruda, cfg.video_id, indice, timestamp, info.width, info.height
            )
            if evento is None:
                if cruda.class_name.lower() != CLASE_PERSONA:
                    resumen.descartadas_por_clase += 1
                else:
                    resumen.descartadas_por_caja += 1
                continue
            eventos_del_frame.append(evento)

        resumen.frames_procesados += 1
        resumen.detecciones_totales += len(eventos_del_frame)
        if eventos_del_frame:
            resumen.frames_con_personas += 1

        renderer.write(frame, eventos_del_frame, indice, timestamp)

        if resumen.frames_procesados % FRAMES_ENTRE_AVISOS == 0:
            _avisar_progreso(resumen, indice, info)

        yield from eventos_del_frame


def _avisar_progreso(resumen: Resumen, indice: int, info) -> None:
    """Una linea de progreso. En CPU esto tarda; hay que ver que avanza."""
    if info.frame_count > 0:
        porcentaje = f"{100 * indice / info.frame_count:5.1f}%"
    else:
        porcentaje = "  ?  "
    print(
        f"  {porcentaje}  frame {indice:>6}  "
        f"procesados {resumen.frames_procesados:>6}  "
        f"personas {resumen.detecciones_totales:>6}"
    )


# --------------------------------------------------------------------------
# Punto de entrada de la etapa
# --------------------------------------------------------------------------

def run(cfg: Config, abrir_video: bool = False) -> int:
    """Ejecuta la deteccion completa. Devuelve el codigo de salida."""
    from gondola.video.reader import VideoReader

    rutas = pipeline.stage_paths("detect", cfg)
    resumen = Resumen()

    print(f"[detect] Video:  {rutas.input_path}")
    with VideoReader(rutas.input_path) as video:
        # Se importa aqui, tras confirmar que el video existe: si faltara,
        # el aviso de "falta el video" no debe depender de tener cv2 instalado.
        from gondola.video.render import Renderer, abrir_con_el_sistema

        print(f"[detect] Fuente: {video.info.resumen()}")

        modelo, ids_persona = _cargar_modelo(cfg)
        nombre_modelo = Path(cfg.model_path).name
        print(f"[detect] Modelo: {nombre_modelo}  (clase '{CLASE_PERSONA}' = id {ids_persona})")
        print(f"[detect] conf={cfg.confidence_threshold}  iou={cfg.iou_threshold}  "
              f"imgsz={cfg.imgsz}  stride={cfg.frame_stride}  device={cfg.device}")

        video_salida = pipeline.render_path("detect", cfg, cfg.render_mode)
        print(f"[detect] Render: {cfg.render_mode}"
              + (f"  ->  {video_salida.name}" if cfg.render_mode != "none" else ""))
        print()

        # El verificador necesita saber el tamano del frame y los fps para
        # comprobar que las cajas caben y que los timestamps cuadran.
        dimensiones = (video.info.width, video.info.height)
        fps_video = video.info.fps

        inicio = time.perf_counter()
        with Renderer(video_salida, cfg.render_mode, video.info.width,
                      video.info.height, video.info.fps) as renderer:
            escritos = write_events(
                rutas.output_path,
                _eventos_del_video(modelo, ids_persona, video, cfg, resumen, renderer),
            )
        transcurrido = time.perf_counter() - inicio

    fps_procesamiento = resumen.frames_procesados / transcurrido if transcurrido > 0 else 0.0
    ruta_resumen = pipeline.summary_path("detect", cfg)
    _escribir_resumen(ruta_resumen, cfg, resumen, fps_procesamiento, transcurrido,
                      nombre_modelo, dimensiones, fps_video)

    _imprimir_resultado(resumen, escritos, transcurrido, fps_procesamiento, cfg,
                        rutas.output_path, ruta_resumen, video_salida)

    if abrir_video and cfg.render_mode != "none" and video_salida.exists():
        abrir_con_el_sistema(video_salida)

    return 0


def _escribir_resumen(destino: Path, cfg: Config, resumen: Resumen,
                      fps_procesamiento: float, transcurrido: float,
                      nombre_modelo: str, dimensiones: tuple[int, int],
                      fps_video: float) -> None:
    """Guarda las metricas de la corrida. Sin esto no se puede comparar nada."""
    promedio = (
        resumen.detecciones_totales / resumen.frames_procesados
        if resumen.frames_procesados else 0.0
    )
    datos = {
        "contract_version": CONTRACT_VERSION,
        "stage": "detect",
        "video_id": cfg.video_id,
        "video_path": str(cfg.video_path),
        # `video` lo lee el verificador: sin el tamano del frame no puede
        # comprobar que las cajas esten dentro, ni los timestamps sin los fps.
        "video": {
            "width": dimensiones[0],
            "height": dimensiones[1],
            "fps": round(fps_video, 4),
        },
        "model": nombre_modelo,
        "params": {
            "confidence_threshold": cfg.confidence_threshold,
            "iou_threshold": cfg.iou_threshold,
            "imgsz": cfg.imgsz,
            "frame_stride": cfg.frame_stride,
            "max_frames": cfg.max_frames,
            "device": cfg.device,
            "render_mode": cfg.render_mode,
        },
        "results": {
            "frames_procesados": resumen.frames_procesados,
            "frames_con_personas": resumen.frames_con_personas,
            "detecciones_totales": resumen.detecciones_totales,
            "promedio_por_frame": round(promedio, 4),
            "descartadas_por_clase": resumen.descartadas_por_clase,
            "descartadas_por_caja": resumen.descartadas_por_caja,
        },
        "performance": {
            "segundos": round(transcurrido, 2),
            "fps_procesamiento": round(fps_procesamiento, 2),
        },
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def _imprimir_resultado(resumen: Resumen, escritos: int, transcurrido: float,
                        fps_procesamiento: float, cfg: Config, jsonl: Path,
                        ruta_resumen: Path, video_salida: Path) -> None:
    promedio = (
        resumen.detecciones_totales / resumen.frames_procesados
        if resumen.frames_procesados else 0.0
    )
    print()
    print("-" * 66)
    print(f"  Frames procesados      {resumen.frames_procesados}")
    print(f"  Frames con personas    {resumen.frames_con_personas}")
    print(f"  Detecciones totales    {resumen.detecciones_totales}")
    print(f"  Promedio por frame     {promedio:.2f}")
    if resumen.descartadas_por_clase or resumen.descartadas_por_caja:
        print(f"  Descartadas            {resumen.descartadas_por_clase} por clase, "
              f"{resumen.descartadas_por_caja} por caja invalida")
    print(f"  Tiempo                 {transcurrido:.1f} s  "
          f"({fps_procesamiento:.1f} frames/s)")
    print("-" * 66)
    print(f"  Eventos   {jsonl}  ({escritos} lineas)")
    print(f"  Resumen   {ruta_resumen}")
    if cfg.render_mode != "none":
        print(f"  Video     {video_salida}")
    print()
    print(f"  {estimacion_honesta(fps_procesamiento, cfg.frame_stride)}")
    print()
    print("  Siguiente etapa:  python -m gondola track   (Persona 3)")
