"""Tests de la logica de deteccion, SIN YOLO y SIN OpenCV.

Todo lo que se prueba aqui son funciones puras: entra una deteccion inventada a
mano, sale un evento del contrato. No hace falta instalar PyTorch ni tener un
video. Corren con solo `pip install -r requirements-dev.txt`.

Los tests que si necesitan el modelo estan en tests/integration/.
"""

import pytest

from gondola.stages.detect import (
    AREA_MINIMA_PX,
    DeteccionCruda,
    Resumen,
    construir_evento,
    estimacion_honesta,
    recortar_bbox,
)

ANCHO, ALTO = 640, 480


def persona(xyxy=(100.0, 50.0, 200.0, 300.0), conf=0.9) -> DeteccionCruda:
    return DeteccionCruda(class_id=0, class_name="person", confidence=conf, xyxy=xyxy)


# --------------------------------------------------------------------------
# Filtrado de clase
# --------------------------------------------------------------------------

def test_una_persona_se_convierte_en_evento():
    evento = construir_evento(persona(), "video_001", 10, 0.4, ANCHO, ALTO)
    assert evento is not None
    assert evento.detection.class_name == "person"


@pytest.mark.parametrize("clase", ["car", "chair", "bottle", "backpack", ""])
def test_lo_que_no_es_persona_se_descarta(clase):
    """El modelo ya filtra, pero si alguien cambia el modelo esto es la red de seguridad."""
    cruda = DeteccionCruda(class_id=2, class_name=clase, confidence=0.99,
                           xyxy=(10.0, 10.0, 50.0, 90.0))
    assert construir_evento(cruda, "video_001", 1, 0.0, ANCHO, ALTO) is None


def test_el_filtro_no_distingue_mayusculas():
    """Un modelo reentrenado podria llamar a la clase 'Person'."""
    cruda = DeteccionCruda(class_id=0, class_name="Person", confidence=0.8,
                           xyxy=(10.0, 10.0, 50.0, 90.0))
    assert construir_evento(cruda, "video_001", 1, 0.0, ANCHO, ALTO) is not None


def test_el_filtro_mira_el_nombre_y_no_el_numero():
    """Si un modelo reentrenado pone un coche en el id 0, NO debe pasar como persona."""
    cruda = DeteccionCruda(class_id=0, class_name="car", confidence=0.99,
                           xyxy=(10.0, 10.0, 50.0, 90.0))
    assert construir_evento(cruda, "video_001", 1, 0.0, ANCHO, ALTO) is None


# --------------------------------------------------------------------------
# Construccion del evento
# --------------------------------------------------------------------------

def test_el_evento_lleva_la_caja_correcta():
    evento = construir_evento(persona((100.0, 50.0, 200.0, 300.0)), "v", 0, 0.0, ANCHO, ALTO)
    caja = evento.detection.bbox
    assert (caja.x, caja.y, caja.width, caja.height) == (100.0, 50.0, 100.0, 250.0)


def test_el_evento_lleva_frame_timestamp_y_confianza():
    evento = construir_evento(persona(conf=0.87), "video_007", 253, 8.43, ANCHO, ALTO)
    assert evento.video_id == "video_007"
    assert evento.frame == 253
    assert evento.timestamp == 8.43
    assert evento.detection.confidence == 0.87


def test_la_deteccion_no_rellena_campos_de_otras_personas():
    """Lo mas importante de esta etapa: solo toca lo suyo."""
    evento = construir_evento(persona(), "v", 1, 0.0, ANCHO, ALTO)
    assert evento.track_id is None            # Persona 3
    assert evento.zone.zone_id is None        # Persona 4
    assert evento.zone.segment is None        # Persona 4
    assert evento.metrics.dwell_time is None  # Persona 4
    assert evento.interaction.event is None   # Persona 5
    assert evento.interaction.product_zone is None


def test_el_evento_se_serializa_al_contrato():
    """Si esto falla, la Persona 3 no podra leer nuestra salida."""
    evento = construir_evento(persona(), "v", 1, 0.0, ANCHO, ALTO)
    import json

    datos = json.loads(evento.to_jsonl())
    assert datos["detection"]["class"] == "person"
    assert datos["track_id"] is None


# --------------------------------------------------------------------------
# Recorte de cajas
# --------------------------------------------------------------------------

def test_una_caja_dentro_del_frame_no_se_toca():
    caja = recortar_bbox((10.0, 20.0, 110.0, 220.0), ANCHO, ALTO)
    assert (caja.x, caja.y, caja.width, caja.height) == (10.0, 20.0, 100.0, 200.0)


def test_una_caja_que_se_sale_por_la_derecha_se_recorta():
    caja = recortar_bbox((600.0, 100.0, 800.0, 300.0), ANCHO, ALTO)
    assert caja.x == 600.0
    assert caja.x + caja.width == ANCHO  # no se pasa del borde


def test_una_caja_con_coordenadas_negativas_se_recorta():
    """Una persona entrando por el borde izquierdo."""
    caja = recortar_bbox((-50.0, -30.0, 100.0, 200.0), ANCHO, ALTO)
    assert caja.x == 0.0
    assert caja.y == 0.0
    assert caja.width == 100.0


def test_una_caja_que_se_sale_por_abajo_se_recorta():
    caja = recortar_bbox((100.0, 400.0, 200.0, 700.0), ANCHO, ALTO)
    assert caja.y + caja.height == ALTO


def test_el_punto_de_apoyo_queda_dentro_del_frame_tras_recortar():
    """Es lo que motiva el recorte: la Persona 4 lo usa sobre el plano del piso."""
    caja = recortar_bbox((-50.0, 300.0, 700.0, 900.0), ANCHO, ALTO)
    px, py = caja.support_point
    assert 0 <= px <= ANCHO
    assert 0 <= py <= ALTO


@pytest.mark.parametrize(
    "xyxy",
    [
        (100.0, 100.0, 100.0, 200.0),   # ancho cero
        (100.0, 100.0, 200.0, 100.0),   # alto cero
        (700.0, 100.0, 900.0, 300.0),   # entera fuera del frame por la derecha
        (100.0, 600.0, 200.0, 700.0),   # entera fuera por abajo
    ],
)
def test_las_cajas_degeneradas_se_descartan(xyxy):
    assert recortar_bbox(xyxy, ANCHO, ALTO) is None


def test_una_caja_ridiculamente_pequena_se_descarta():
    """Un pixel no es una persona: es ruido del modelo."""
    assert recortar_bbox((10.0, 10.0, 11.0, 11.0), ANCHO, ALTO) is None


def test_una_caja_justo_por_encima_del_area_minima_se_conserva():
    lado = AREA_MINIMA_PX  # area = lado*lado, holgadamente por encima del minimo
    assert recortar_bbox((10.0, 10.0, 10.0 + lado, 10.0 + lado), ANCHO, ALTO) is not None


def test_una_caja_con_las_esquinas_al_reves_se_ordena():
    """Defensivo: no deberia pasar, pero si pasa no queremos un ancho negativo."""
    caja = recortar_bbox((200.0, 300.0, 100.0, 50.0), ANCHO, ALTO)
    assert caja.width > 0 and caja.height > 0


def test_una_caja_descartada_no_genera_evento():
    cruda = DeteccionCruda(class_id=0, class_name="person", confidence=0.95,
                           xyxy=(700.0, 100.0, 900.0, 300.0))
    assert construir_evento(cruda, "v", 1, 0.0, ANCHO, ALTO) is None


# --------------------------------------------------------------------------
# Resumen y estimacion
# --------------------------------------------------------------------------

def test_el_resumen_empieza_en_cero():
    r = Resumen()
    assert (r.frames_procesados, r.frames_con_personas, r.detecciones_totales) == (0, 0, 0)


def test_la_estimacion_usa_la_velocidad_medida():
    """15.000 frames a 10 frames/s son 1.500 s, o sea 25 minutos."""
    texto = estimacion_honesta(10.0, stride=1)
    assert "25.0 minutos" in texto
    assert "10.0 frames/s" in texto


def test_la_estimacion_tiene_en_cuenta_el_stride():
    """Con stride 5 se procesa la quinta parte de los frames, y se dice."""
    texto = estimacion_honesta(10.0, stride=5)
    assert "5.0 minutos" in texto
    assert "stride 5" in texto


def test_la_estimacion_no_se_inventa_nada_si_no_pudo_medir():
    assert "No pude medir" in estimacion_honesta(0.0, stride=1)


# --------------------------------------------------------------------------
# Ausencia de video
#
# Estos si necesitan OpenCV, que no esta en requirements-dev.txt: se saltan
# solos en la maquina de quien no lo tenga instalado.
# --------------------------------------------------------------------------

def test_un_video_que_no_existe_da_un_mensaje_util_y_no_un_traceback(tmp_path):
    pytest.importorskip("cv2")
    from gondola.errors import MissingInputError
    from gondola.video.reader import VideoReader

    with pytest.raises(MissingInputError) as error:
        VideoReader(tmp_path / "no_existe.mp4")

    mensaje = str(error.value)
    assert "data/videos/" in mensaje          # donde ponerlo
    assert "VIDEO_PATH" in mensaje            # como configurarlo
    assert "--video" in mensaje               # o como pasarlo directo
    assert "make_test_clips" in mensaje       # o como generar clips de prueba


def test_un_archivo_que_no_es_video_da_error_controlado(tmp_path):
    """Un .mp4 que en realidad es texto: OpenCV devuelve False, no lanza nada."""
    pytest.importorskip("cv2")
    from gondola.errors import VideoError
    from gondola.video.reader import VideoReader

    falso = tmp_path / "roto.mp4"
    falso.write_text("esto no es un video", encoding="utf-8")

    with pytest.raises(VideoError) as error:
        VideoReader(falso)
    assert "codec" in str(error.value).lower() or "corrupto" in str(error.value).lower()


def test_la_cli_devuelve_codigo_2_si_falta_el_video(tmp_path, monkeypatch, capsys):
    """Falta un requisito, no es un fallo del programa: codigo 2, sin traceback."""
    pytest.importorskip("cv2")
    from gondola.cli import EXIT_FALTA_REQUISITO, main

    monkeypatch.setenv("VIDEO_PATH", str(tmp_path / "fantasma.mp4"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    assert main(["detect"]) == EXIT_FALTA_REQUISITO
    assert "Traceback" not in capsys.readouterr().err
