"""Tests de la fontaneria de la cadena: gondola/pipeline.py y gondola/jsonl.py.

Van juntos porque prueban la misma idea: que las etapas se pasen archivos sin
que ninguna persona tenga que escribir un nombre de archivo a mano.
"""

import pytest

from gondola.config import load_config
from gondola.contract import BBox, Detection, Event
from gondola.errors import ContractError, MissingInputError, PipelineError
from gondola.jsonl import count_events, read_events, write_events
from gondola.pipeline import (
    STAGE_NAMES,
    STAGES,
    get_stage,
    previous_stage,
    require_input,
    stage_paths,
)


@pytest.fixture
def cfg(tmp_path):
    """Configuracion apuntando a una carpeta temporal, distinta en cada test."""
    return load_config(
        env={
            "VIDEO_ID": "video_001",
            "VIDEO_PATH": str(tmp_path / "videos" / "scapder.mp4"),
            "OUTPUT_DIR": str(tmp_path / "output"),
        }
    )


def evento(frame: int = 1) -> Event:
    return Event(
        video_id="video_001",
        frame=frame,
        timestamp=frame / 30.0,
        detection=Detection(
            confidence=0.9, bbox=BBox(x=10, y=20, width=30, height=40)
        ),
    )


# --------------------------------------------------------------------------
# El registro de etapas
# --------------------------------------------------------------------------

def test_estan_las_cinco_etapas_en_orden():
    assert STAGE_NAMES == ("detect", "track", "zones", "interact", "metrics")


@pytest.mark.parametrize(
    "nombre, entrada_esperada, salida_esperada",
    [
        ("detect", None, "video_001.detect.jsonl"),
        ("track", "video_001.detect.jsonl", "video_001.track.jsonl"),
        ("zones", "video_001.track.jsonl", "video_001.zones.jsonl"),
        ("interact", "video_001.zones.jsonl", "video_001.interact.jsonl"),
        ("metrics", "video_001.interact.jsonl", "video_001.metrics.json"),
    ],
)
def test_cada_etapa_devuelve_las_rutas_esperadas(
    cfg, nombre, entrada_esperada, salida_esperada
):
    """La tabla del enunciado, comprobada linea por linea."""
    rutas = stage_paths(nombre, cfg)
    assert rutas.output_path.name == salida_esperada
    if entrada_esperada is None:
        assert rutas.input_path == cfg.video_path  # detect lee el video
    else:
        assert rutas.input_path.name == entrada_esperada


def test_las_rutas_salen_de_la_carpeta_de_salida(cfg):
    for nombre in STAGE_NAMES:
        assert stage_paths(nombre, cfg).output_path.parent == cfg.output_dir


def test_el_nombre_de_archivo_lleva_el_video_id(cfg):
    """Dos videos distintos no deben pisarse los archivos."""
    otro = load_config(env={"VIDEO_ID": "video_042", "OUTPUT_DIR": str(cfg.output_dir)})
    assert stage_paths("track", otro).output_path.name == "video_042.track.jsonl"


def test_ninguna_etapa_comparte_su_salida_con_otra(cfg):
    """Si dos etapas escribieran el mismo archivo, una borraria a la otra."""
    salidas = [stage_paths(n, cfg).output_path for n in STAGE_NAMES]
    assert len(set(salidas)) == len(salidas)


def test_ninguna_etapa_escribe_sobre_su_propia_entrada(cfg):
    for nombre in STAGE_NAMES:
        rutas = stage_paths(nombre, cfg)
        assert rutas.output_path != rutas.input_path


def test_la_cadena_esta_encadenada(cfg):
    """La salida de cada etapa debe ser exactamente la entrada de la siguiente."""
    for actual, siguiente in zip(STAGES, STAGES[1:]):
        assert actual.output_suffix == siguiente.input_suffix
        assert (
            stage_paths(actual.name, cfg).output_path
            == stage_paths(siguiente.name, cfg).input_path
        )


def test_una_etapa_inventada_lanza_excepcion(cfg):
    with pytest.raises(PipelineError):
        stage_paths("deteccion", cfg)


def test_el_error_de_etapa_inventada_lista_las_validas():
    """Nadie deberia tener que abrir pipeline.py para recordar los nombres."""
    with pytest.raises(PipelineError) as error:
        get_stage("seguimiento")
    mensaje = str(error.value)
    for nombre in STAGE_NAMES:
        assert nombre in mensaje


def test_la_etapa_anterior_es_la_correcta():
    assert previous_stage("detect") is None  # la primera lee el video
    assert previous_stage("track").name == "detect"
    assert previous_stage("metrics").name == "interact"


def test_cada_etapa_tiene_responsable_y_descripcion():
    """El placeholder los muestra: si faltan, el companero no sabe que hacer."""
    for etapa in STAGES:
        assert etapa.owner
        assert etapa.description


# --------------------------------------------------------------------------
# require_input: decir que correr antes
# --------------------------------------------------------------------------

def test_require_input_devuelve_la_ruta_si_existe(cfg):
    entrada = stage_paths("track", cfg).input_path
    write_events(entrada, [evento()])
    assert require_input("track", cfg) == entrada


def test_si_falta_el_video_el_error_habla_del_video(cfg):
    with pytest.raises(MissingInputError) as error:
        require_input("detect", cfg)
    assert "video" in str(error.value).lower()
    assert "data/videos/" in str(error.value)


def test_si_falta_la_entrada_el_error_dice_que_comando_correr(cfg):
    """Lo importante de esta fase: el error dice el comando exacto, no 'falta un archivo'."""
    with pytest.raises(MissingInputError) as error:
        require_input("zones", cfg)
    assert "python -m gondola track" in str(error.value)


# --------------------------------------------------------------------------
# JSONL en streaming
# --------------------------------------------------------------------------

def test_escribe_y_relee_sin_perder_nada(tmp_path):
    originales = [evento(i) for i in range(100)]
    destino = tmp_path / "salida.jsonl"

    escritos = write_events(destino, originales)
    recuperados = list(read_events(destino))

    assert escritos == 100
    assert recuperados == originales


def test_crea_la_carpeta_de_salida_si_no_existe(tmp_path):
    destino = tmp_path / "no" / "existe" / "salida.jsonl"
    write_events(destino, [evento()])
    assert destino.exists()


def test_un_evento_por_linea(tmp_path):
    destino = tmp_path / "salida.jsonl"
    write_events(destino, [evento(i) for i in range(5)])
    lineas = destino.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 5


def test_la_lectura_es_perezosa(tmp_path):
    """read_events no debe cargar el archivo entero: 50.000 eventos no caben comodos."""
    destino = tmp_path / "salida.jsonl"
    write_events(destino, [evento(i) for i in range(10)])
    flujo = read_events(destino)
    primero = next(flujo)  # funciona sin haber leido el resto
    assert primero.frame == 0


def test_las_lineas_en_blanco_se_ignoran(tmp_path):
    destino = tmp_path / "salida.jsonl"
    destino.write_text(evento().to_jsonl() + "\n\n\n", encoding="utf-8")
    assert len(list(read_events(destino))) == 1


def test_una_linea_corrupta_dice_el_numero_de_linea(tmp_path):
    """En un archivo de 50.000 lineas, 'algo fallo' no sirve de nada."""
    destino = tmp_path / "salida.jsonl"
    destino.write_text(
        evento(1).to_jsonl() + "\n" + evento(2).to_jsonl() + "\n{roto\n",
        encoding="utf-8",
    )
    with pytest.raises(ContractError) as error:
        list(read_events(destino))
    assert "linea 3" in str(error.value)


def test_leer_un_archivo_que_no_existe_da_error_claro(tmp_path):
    with pytest.raises(ContractError):
        list(read_events(tmp_path / "fantasma.jsonl"))


def test_contar_eventos(tmp_path):
    destino = tmp_path / "salida.jsonl"
    write_events(destino, [evento(i) for i in range(7)])
    assert count_events(destino) == 7


def test_escribir_sobrescribe_la_salida_anterior(tmp_path):
    """Una etapa produce su salida completa desde cero, no la va acumulando."""
    destino = tmp_path / "salida.jsonl"
    write_events(destino, [evento(i) for i in range(10)])
    write_events(destino, [evento(0)])
    assert count_events(destino) == 1
