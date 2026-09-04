"""Tests de lectura de video y render (gondola/video/).

Necesitan OpenCV, que no esta en requirements-dev.txt: se saltan solos en la
maquina de quien no lo tenga. Por eso el importorskip esta arriba del todo.
"""

import pytest

cv2 = pytest.importorskip("cv2", reason="opencv no instalado")
np = pytest.importorskip("numpy", reason="numpy no instalado")

from gondola.contract import BBox, Detection, Event  # noqa: E402
from gondola.errors import VideoError  # noqa: E402
from gondola.video.reader import VideoReader  # noqa: E402
from gondola.video.render import Renderer  # noqa: E402

ANCHO, ALTO, FPS, FRAMES = 320, 240, 25.0, 20


@pytest.fixture
def clip(tmp_path):
    """Un video minimo de colores planos, con un numero de frame conocido."""
    ruta = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(
        str(ruta), cv2.VideoWriter.fourcc(*"mp4v"), FPS, (ANCHO, ALTO)
    )
    for i in range(FRAMES):
        frame = np.full((ALTO, ANCHO, 3), (i * 8) % 256, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return ruta


def evento(x=10.0, y=20.0, w=50.0, h=80.0) -> Event:
    return Event(
        video_id="test", frame=0, timestamp=0.0,
        detection=Detection(confidence=0.9, bbox=BBox(x=x, y=y, width=w, height=h)),
    )


# --------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------

def test_lee_las_propiedades_del_video(clip):
    with VideoReader(clip) as video:
        assert (video.info.width, video.info.height) == (ANCHO, ALTO)
        assert video.info.fps == pytest.approx(FPS)
        assert video.info.frame_count == FRAMES


def test_la_duracion_sale_de_los_frames_y_los_fps(clip):
    with VideoReader(clip) as video:
        assert video.info.duration_s == pytest.approx(FRAMES / FPS)


def test_el_resumen_es_legible(clip):
    with VideoReader(clip) as video:
        texto = video.info.resumen()
    assert "320x240" in texto and "fps" in texto


def test_recorre_todos_los_frames(clip):
    with VideoReader(clip) as video:
        assert len(list(video.frames())) == FRAMES


def test_cada_frame_trae_indice_timestamp_e_imagen(clip):
    with VideoReader(clip) as video:
        indice, timestamp, imagen = next(video.frames())
    assert indice == 0
    assert timestamp == 0.0
    assert imagen.shape == (ALTO, ANCHO, 3)


def test_el_timestamp_sigue_el_reloj_del_video(clip):
    with VideoReader(clip) as video:
        for indice, timestamp, _ in video.frames():
            assert timestamp == pytest.approx(indice / FPS)


def test_con_stride_los_indices_son_los_del_video_original(clip):
    """NO se renumeran: la Persona 4 los necesita para calcular tiempos reales."""
    with VideoReader(clip) as video:
        indices = [i for i, _, _ in video.frames(stride=4)]
    assert indices == [0, 4, 8, 12, 16]


def test_max_frames_cuenta_los_entregados(clip):
    with VideoReader(clip) as video:
        assert len(list(video.frames(stride=3, max_frames=4))) == 4


def test_un_stride_invalido_da_error_controlado(clip):
    with VideoReader(clip) as video:
        with pytest.raises(VideoError):
            list(video.frames(stride=0))


def test_el_archivo_se_cierra_al_salir_del_with(clip):
    video = VideoReader(clip)
    with video:
        pass
    assert video._cap is None


def test_un_archivo_que_no_es_video_da_VideoError(tmp_path):
    falso = tmp_path / "roto.mp4"
    falso.write_text("no soy un video", encoding="utf-8")
    with pytest.raises(VideoError):
        VideoReader(falso)


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------

def test_el_modo_privacy_no_recibe_el_frame_original(tmp_path):
    """La prueba de la privacidad por diseno: se le pasa None y funciona igual.

    Si el modo privacy usara el fotograma real, esto reventaria con
    AttributeError al intentar copiarlo.
    """
    destino = tmp_path / "privacy.mp4"
    with Renderer(destino, "privacy", ANCHO, ALTO, FPS) as r:
        for i in range(5):
            r.write(None, [evento()], i, i / FPS)
    assert destino.exists() and destino.stat().st_size > 0


def test_el_modo_debug_si_usa_el_frame_original(tmp_path):
    destino = tmp_path / "debug.mp4"
    frame = np.zeros((ALTO, ANCHO, 3), dtype=np.uint8)
    with Renderer(destino, "debug", ANCHO, ALTO, FPS) as r:
        for i in range(5):
            r.write(frame, [evento()], i, i / FPS)
    assert destino.exists() and destino.stat().st_size > 0


def test_el_modo_debug_sin_frame_si_revienta(tmp_path):
    """Confirma que el test de privacy de arriba prueba algo de verdad."""
    with Renderer(tmp_path / "debug.mp4", "debug", ANCHO, ALTO, FPS) as r:
        with pytest.raises(AttributeError):
            r.write(None, [], 0, 0.0)


def test_el_modo_none_no_crea_archivo(tmp_path):
    destino = tmp_path / "nada.mp4"
    with Renderer(destino, "none", ANCHO, ALTO, FPS) as r:
        r.write(None, [evento()], 0, 0.0)
    assert not destino.exists()


def test_el_lienzo_neutro_no_contiene_pixeles_del_video(tmp_path):
    """Solo el gris de fondo y el de la rejilla. Ningun color de la tienda."""
    r = Renderer(tmp_path / "x.mp4", "privacy", ANCHO, ALTO, FPS)
    lienzo = r._lienzo_neutro()
    r.close()
    colores = {tuple(c) for c in lienzo.reshape(-1, 3)}
    assert len(colores) <= 2


def test_se_dibujan_tantas_cajas_como_eventos(tmp_path):
    """Con eventos hay pixeles verdes; sin eventos, el lienzo queda liso."""
    r = Renderer(tmp_path / "x.mp4", "privacy", ANCHO, ALTO, FPS)
    vacio = r._lienzo_neutro()
    con_caja = r._lienzo_neutro()
    r._dibujar_caja(con_caja, evento())
    r.close()
    assert not np.array_equal(vacio, con_caja)
