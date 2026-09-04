"""Tests de integracion: el pipeline de deteccion de verdad, con YOLO.

Son LENTOS (cargan el modelo y procesan frames) y necesitan las dependencias
pesadas de requirements.txt. Se saltan solos si ultralytics u OpenCV no estan
instalados, para que los companeros que solo instalaron requirements-dev.txt
puedan correr `pytest` sin que les falle nada.

Correr solo estos:
    pytest ai-service/tests/integration -v

QUE PRUEBAN Y QUE NO
--------------------
Los clips que usan son CONTROLES NEGATIVOS: no hay ninguna persona en ellos, y
la deteccion debe dar cero. Eso prueba que el sistema no se inventa personas y
que la cadena corre entera sin romperse.

NO prueban que detecte bien. Un detector completamente roto, que nunca
encuentre nada, tambien pasaria estos tests. Medir la exactitud de verdad exige
video con personas reales y anotaciones manuales: eso es la Fase 5.
"""

import json

import pytest

from gondola.config import load_config

pytest.importorskip("cv2", reason="opencv no instalado (pip install -r requirements.txt)")
pytest.importorskip(
    "ultralytics", reason="ultralytics no instalado (pip install -r requirements.txt)"
)

RAIZ_CLIPS = "data/videos"


@pytest.fixture(scope="module")
def clip_formas(tmp_path_factory):
    """Genera el clip de rectangulos en una carpeta temporal."""
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(raiz / "scripts"))
    import make_test_clips

    destino = tmp_path_factory.mktemp("clips")
    original = make_test_clips.DESTINO
    make_test_clips.DESTINO = destino
    try:
        ruta = make_test_clips.hacer_clip_formas()
    finally:
        make_test_clips.DESTINO = original
    return ruta


def cfg_para(video, tmp_path, **extra):
    return load_config(
        env={
            "VIDEO_ID": video.stem,
            "VIDEO_PATH": str(video),
            "OUTPUT_DIR": str(tmp_path / "output"),
            "MAX_FRAMES": "6",  # con 6 frames basta: esto es lento en CPU
            "RENDER_MODE": "none",
            **extra,
        }
    )


# --------------------------------------------------------------------------
# Carga del modelo
# --------------------------------------------------------------------------

def test_el_modelo_carga_y_conoce_la_clase_person(tmp_path, clip_formas):
    """Sin una clase 'person', todo lo demas no tiene sentido."""
    from gondola.stages.detect import CLASE_PERSONA, _cargar_modelo

    modelo, ids = _cargar_modelo(cfg_para(clip_formas, tmp_path))
    assert ids, "el modelo no tiene ninguna clase 'person'"
    for i in ids:
        assert str(modelo.names[i]).lower() == CLASE_PERSONA


def test_un_modelo_que_no_existe_da_error_del_proyecto(tmp_path, clip_formas):
    """No un traceback de ultralytics: un ModelError que dice que hacer."""
    from gondola.errors import ModelError
    from gondola.stages.detect import _cargar_modelo

    cfg = cfg_para(clip_formas, tmp_path, MODEL_PATH=str(tmp_path / "no_existe.pt"))
    with pytest.raises(ModelError) as error:
        _cargar_modelo(cfg)
    assert "MODEL_PATH" in str(error.value)


# --------------------------------------------------------------------------
# Procesamiento de un clip completo
# --------------------------------------------------------------------------

def test_el_clip_de_formas_no_produce_ninguna_deteccion(tmp_path, clip_formas):
    """CONTROL NEGATIVO. Si esto falla, tenemos falsos positivos."""
    from gondola import pipeline
    from gondola.stages import detect

    cfg = cfg_para(clip_formas, tmp_path)
    assert detect.run(cfg) == 0

    salida = pipeline.stage_paths("detect", cfg).output_path
    assert salida.exists(), "el .jsonl debe crearse aunque no haya detecciones"
    assert salida.read_text(encoding="utf-8") == "", "hay falsos positivos"


def test_se_escribe_el_resumen_con_los_parametros_usados(tmp_path, clip_formas):
    from gondola import pipeline
    from gondola.contract import CONTRACT_VERSION
    from gondola.stages import detect

    cfg = cfg_para(clip_formas, tmp_path)
    detect.run(cfg)

    resumen = json.loads(
        pipeline.summary_path("detect", cfg).read_text(encoding="utf-8")
    )
    assert resumen["contract_version"] == CONTRACT_VERSION
    assert resumen["stage"] == "detect"
    assert resumen["results"]["frames_procesados"] == 6
    assert resumen["results"]["detecciones_totales"] == 0
    assert resumen["params"]["imgsz"] == cfg.imgsz
    assert resumen["performance"]["fps_procesamiento"] > 0


def test_con_stride_los_numeros_de_frame_son_los_del_video_original(tmp_path, clip_formas):
    """NO se renumeran: la Persona 4 los necesita para calcular tiempos reales."""
    from gondola.video.reader import VideoReader

    with VideoReader(clip_formas) as video:
        indices = [i for i, _, _ in video.frames(stride=5, max_frames=4)]
    assert indices == [0, 5, 10, 15]


def test_con_stride_el_timestamp_sigue_el_reloj_del_video(tmp_path, clip_formas):
    """A 25 fps, el frame 25 ocurre en el segundo 1.0, no en el 0.2."""
    from gondola.video.reader import VideoReader

    with VideoReader(clip_formas) as video:
        fps = video.info.fps
        marcas = [(i, t) for i, t, _ in video.frames(stride=5, max_frames=4)]
    for indice, timestamp in marcas:
        assert timestamp == pytest.approx(indice / fps)


def test_max_frames_cuenta_los_entregados_no_los_recorridos(tmp_path, clip_formas):
    from gondola.video.reader import VideoReader

    with VideoReader(clip_formas) as video:
        entregados = list(video.frames(stride=5, max_frames=3))
    assert len(entregados) == 3


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------

def test_el_render_de_privacidad_no_usa_ni_un_pixel_del_video(tmp_path, clip_formas):
    """La prueba de la privacidad por diseno: el frame real ni se pasa.

    Se le entrega None como frame original. Si el modo privacy lo usara, esto
    reventaria con AttributeError.
    """
    from gondola.video.render import Renderer

    destino = tmp_path / "privacy.mp4"
    with Renderer(destino, "privacy", 320, 240, 25.0) as renderer:
        for i in range(5):
            renderer.write(None, [], i, i / 25.0)

    assert destino.exists()
    assert destino.stat().st_size > 0


def test_el_modo_none_no_crea_ningun_archivo(tmp_path):
    from gondola.video.render import Renderer

    destino = tmp_path / "no_deberia_existir.mp4"
    with Renderer(destino, "none", 320, 240, 25.0) as renderer:
        renderer.write(None, [], 0, 0.0)
    assert not destino.exists()
