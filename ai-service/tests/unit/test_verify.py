"""Tests del verificador (gondola/verify/verifier.py).

Cada regla se prueba en los dos sentidos: un archivo que la cumple debe PASAR,
y uno que la rompe debe FALLAR. Un verificador que solo se prueba con datos
buenos no sirve de nada: aprobaria cualquier cosa.
"""

import json

import pytest

from gondola.config import load_config
from gondola.verify.verifier import FRAGMENTOS_PROHIBIDOS, verificar

ANCHO, ALTO, FPS = 640, 480, 25.0


@pytest.fixture
def cfg(tmp_path):
    return load_config(env={"VIDEO_ID": "video_001", "OUTPUT_DIR": str(tmp_path)})


def evento_crudo(frame=0, conf=0.9, **cambios) -> dict:
    """Un evento valido de detect, como diccionario, listo para retocar."""
    datos = {
        "video_id": "video_001",
        "frame": frame,
        "timestamp": frame / FPS,
        "track_id": None,
        "detection": {
            "class": "person",
            "confidence": conf,
            "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 200.0},
        },
        "zone": {"zone_id": None, "segment": None},
        "interaction": {"event": None, "product_zone": None},
        "metrics": {"dwell_time": None},
    }
    datos.update(cambios)
    return datos


def escribir(tmp_path, eventos, con_resumen=True, umbral=0.5):
    """Escribe un .detect.jsonl y (opcionalmente) su resumen de corrida."""
    jsonl = tmp_path / "video_001.detect.jsonl"
    jsonl.write_text(
        "".join(json.dumps(e) + "\n" for e in eventos), encoding="utf-8"
    )
    if con_resumen:
        (tmp_path / "video_001.detect.summary.json").write_text(
            json.dumps({
                "video": {"width": ANCHO, "height": ALTO, "fps": FPS},
                "params": {"confidence_threshold": umbral},
            }),
            encoding="utf-8",
        )
    return jsonl


def regla(informe, nombre):
    return next(r for r in informe.reglas if r.nombre == nombre)


# --------------------------------------------------------------------------
# El caso bueno
# --------------------------------------------------------------------------

def test_una_salida_correcta_pasa_todas_las_reglas(tmp_path, cfg):
    ruta = escribir(tmp_path, [evento_crudo(i) for i in range(10)])
    informe = verificar(ruta, cfg)
    assert informe.ok, [r.nombre for r in informe.reglas if r.fallos]
    assert informe.eventos == 10
    assert informe.etapa == "detect"


def test_un_archivo_vacio_pasa_sin_verificar_nada(tmp_path, cfg):
    """Cero eventos no es un fallo: es lo que produce un video sin personas."""
    ruta = escribir(tmp_path, [])
    informe = verificar(ruta, cfg)
    assert informe.ok
    assert informe.eventos == 0


# --------------------------------------------------------------------------
# Privacidad
# --------------------------------------------------------------------------

def test_un_campo_de_edad_hace_fallar_la_verificacion(tmp_path, cfg):
    ruta = escribir(tmp_path, [evento_crudo(0, age=32)])
    informe = verificar(ruta, cfg)
    assert not informe.ok
    assert regla(informe, "privacidad").fallos


def test_un_campo_prohibido_anidado_tambien_se_detecta(tmp_path, cfg):
    """Escondido dentro de detection, no en la raiz."""
    evento = evento_crudo(0)
    evento["detection"]["face_embedding"] = [0.1, 0.2, 0.3]
    ruta = escribir(tmp_path, [evento])
    informe = verificar(ruta, cfg)
    assert regla(informe, "privacidad").fallos


@pytest.mark.parametrize(
    "campo", ["edad", "gender", "rostro", "identidad", "emotion", "biometrico",
              "documento", "telefono", "foto", "nombre"]
)
def test_los_campos_prohibidos_se_detectan_en_espanol_y_en_ingles(tmp_path, cfg, campo):
    ruta = escribir(tmp_path, [evento_crudo(0, **{campo: "x"})])
    assert regla(verificar(ruta, cfg), "privacidad").fallos


def test_el_mensaje_dice_que_campo_y_que_fragmento(tmp_path, cfg):
    ruta = escribir(tmp_path, [evento_crudo(0, face_id="abc")])
    _, detalle = regla(verificar(ruta, cfg), "privacidad").fallos[0]
    assert "face_id" in detalle


def test_track_id_no_se_considera_campo_prohibido(tmp_path, cfg):
    """track_id es anonimo y temporal: si lo prohibieramos, la Persona 3 no podria trabajar."""
    assert not any(f in "track_id" for f in FRAGMENTOS_PROHIBIDOS)


# --------------------------------------------------------------------------
# Contrato y claves de raiz
# --------------------------------------------------------------------------

def test_una_clave_de_raiz_de_mas_hace_fallar(tmp_path, cfg):
    ruta = escribir(tmp_path, [evento_crudo(0, extra="lo que sea")])
    informe = verificar(ruta, cfg)
    assert regla(informe, "claves_raiz").fallos
    assert regla(informe, "contrato").fallos  # extra="forbid" tambien lo rechaza


def test_una_clave_de_raiz_que_falta_hace_fallar(tmp_path, cfg):
    evento = evento_crudo(0)
    del evento["metrics"]
    ruta = escribir(tmp_path, [evento])
    assert regla(verificar(ruta, cfg), "claves_raiz").fallos


def test_una_linea_que_no_es_json_hace_fallar(tmp_path, cfg):
    ruta = tmp_path / "video_001.detect.jsonl"
    ruta.write_text(json.dumps(evento_crudo(0)) + "\n{roto\n", encoding="utf-8")
    assert regla(verificar(ruta, cfg), "contrato").fallos


def test_el_informe_dice_el_numero_de_linea_que_fallo(tmp_path, cfg):
    eventos = [evento_crudo(0), evento_crudo(1), evento_crudo(2, age=40)]
    ruta = escribir(tmp_path, eventos)
    numero, _ = regla(verificar(ruta, cfg), "privacidad").fallos[0]
    assert numero == 3


# --------------------------------------------------------------------------
# Clase, confianza y cajas
# --------------------------------------------------------------------------

def test_una_clase_distinta_de_person_hace_fallar(tmp_path, cfg):
    evento = evento_crudo(0)
    evento["detection"]["class"] = "car"
    ruta = escribir(tmp_path, [evento])
    assert regla(verificar(ruta, cfg), "clase_person").fallos


def test_una_confianza_por_debajo_del_umbral_hace_fallar(tmp_path, cfg):
    """El detector no deberia haberla escrito: o el umbral no se aplico, o se toco el archivo."""
    ruta = escribir(tmp_path, [evento_crudo(0, conf=0.2)], umbral=0.5)
    assert regla(verificar(ruta, cfg), "confianza_umbral").fallos


def test_una_confianza_justo_en_el_umbral_pasa(tmp_path, cfg):
    ruta = escribir(tmp_path, [evento_crudo(0, conf=0.5)], umbral=0.5)
    assert not regla(verificar(ruta, cfg), "confianza_umbral").fallos


def test_una_confianza_fuera_de_rango_la_rechaza_el_contrato(tmp_path, cfg):
    evento = evento_crudo(0)
    evento["detection"]["confidence"] = 1.4
    ruta = escribir(tmp_path, [evento])
    assert regla(verificar(ruta, cfg), "contrato").fallos


def test_una_caja_que_se_sale_del_frame_hace_fallar(tmp_path, cfg):
    evento = evento_crudo(0)
    evento["detection"]["bbox"] = {"x": 600.0, "y": 10.0, "width": 200.0, "height": 50.0}
    ruta = escribir(tmp_path, [evento])
    assert regla(verificar(ruta, cfg), "bbox_en_frame").fallos


def test_una_caja_pegada_al_borde_pasa(tmp_path, cfg):
    evento = evento_crudo(0)
    evento["detection"]["bbox"] = {"x": 540.0, "y": 380.0, "width": 100.0, "height": 100.0}
    ruta = escribir(tmp_path, [evento])
    assert not regla(verificar(ruta, cfg), "bbox_en_frame").fallos


def test_una_caja_de_ancho_cero_la_rechaza_el_contrato(tmp_path, cfg):
    evento = evento_crudo(0)
    evento["detection"]["bbox"]["width"] = 0
    ruta = escribir(tmp_path, [evento])
    assert regla(verificar(ruta, cfg), "contrato").fallos


# --------------------------------------------------------------------------
# Frames y timestamps
# --------------------------------------------------------------------------

def test_los_frames_que_retroceden_hacen_fallar(tmp_path, cfg):
    ruta = escribir(tmp_path, [evento_crudo(10), evento_crudo(3)])
    assert regla(verificar(ruta, cfg), "frames_crecientes").fallos


def test_varias_detecciones_en_el_mismo_frame_no_son_un_fallo(tmp_path, cfg):
    """Tres personas en el frame 5 son tres lineas con frame=5. Es lo normal."""
    ruta = escribir(tmp_path, [evento_crudo(5), evento_crudo(5), evento_crudo(6)])
    assert not regla(verificar(ruta, cfg), "frames_crecientes").fallos


def test_un_timestamp_que_no_cuadra_con_los_fps_hace_fallar(tmp_path, cfg):
    ruta = escribir(tmp_path, [evento_crudo(0, timestamp=99.0)])
    assert regla(verificar(ruta, cfg), "timestamps").fallos


def test_sin_resumen_las_reglas_que_lo_necesitan_se_omiten(tmp_path, cfg):
    """OMITE no es PASA: el informe dice claramente que no se pudo comprobar."""
    ruta = escribir(tmp_path, [evento_crudo(0)], con_resumen=False)
    informe = verificar(ruta, cfg)
    assert regla(informe, "timestamps").omitida
    assert regla(informe, "bbox_en_frame").omitida
    assert informe.ok  # omitida no cuenta como fallo
    assert any("OMITIDAS" in c for c in informe.contexto)


# --------------------------------------------------------------------------
# Campos de etapas posteriores
# --------------------------------------------------------------------------

def test_un_track_id_en_la_salida_de_detect_hace_fallar(tmp_path, cfg):
    """track_id lo rellena la Persona 3, no la 2."""
    ruta = escribir(tmp_path, [evento_crudo(0, track_id=7)])
    assert regla(verificar(ruta, cfg), "campos_posteriores").fallos


def test_una_zona_en_la_salida_de_detect_hace_fallar(tmp_path, cfg):
    evento = evento_crudo(0)
    evento["zone"]["zone_id"] = "gondola_A"
    ruta = escribir(tmp_path, [evento])
    assert regla(verificar(ruta, cfg), "campos_posteriores").fallos


def test_en_la_salida_de_track_el_track_id_ya_es_valido(tmp_path, cfg):
    """La misma linea que falla en detect.jsonl debe pasar en track.jsonl."""
    ruta = tmp_path / "video_001.track.jsonl"
    ruta.write_text(json.dumps(evento_crudo(0, track_id=7)) + "\n", encoding="utf-8")
    informe = verificar(ruta, cfg)
    assert informe.etapa == "track"
    assert not regla(informe, "campos_posteriores").fallos


def test_en_la_salida_de_track_una_zona_sigue_estando_de_mas(tmp_path, cfg):
    evento = evento_crudo(0, track_id=7)
    evento["zone"]["zone_id"] = "gondola_A"
    ruta = tmp_path / "video_001.track.jsonl"
    ruta.write_text(json.dumps(evento) + "\n", encoding="utf-8")
    assert regla(verificar(ruta, cfg), "campos_posteriores").fallos


def test_un_archivo_con_nombre_desconocido_omite_esa_regla(tmp_path, cfg):
    ruta = tmp_path / "cualquier_cosa.jsonl"
    ruta.write_text(json.dumps(evento_crudo(0)) + "\n", encoding="utf-8")
    informe = verificar(ruta, cfg)
    assert informe.etapa == "desconocida"
    assert regla(informe, "campos_posteriores").omitida
