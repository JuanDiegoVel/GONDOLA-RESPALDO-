"""Tests de la CLI (gondola/cli.py).

Se llama a `main(argv)` directamente en vez de lanzar un proceso: es mas rapido
y permite leer la salida con capsys. `main` devuelve el codigo de salida en vez
de llamar a sys.exit justamente para esto.
"""

import logging

import pytest

from gondola.cli import (
    EXIT_ERROR,
    EXIT_FALTA_REQUISITO,
    EXIT_OK,
    _aplicar_opciones,
    _parser,
    main,
)
from gondola.config import load_config
from gondola.errors import (
    ConfigError,
    ContractError,
    GondolaError,
    MissingInputError,
    ModelError,
    PipelineError,
    VideoError,
)
from gondola.logging_setup import setup_logging
from gondola.pipeline import STAGE_NAMES, STAGES, stage_paths

# 'detect' (Fase 3), 'track' (Persona 3), 'zones' (Persona 4), 'interact'
# (Persona 5) y 'metrics' (Persona 6) ya estan implementadas, asi que no
# imprimen el texto de placeholder. Los tests de placeholder van sobre las
# que siguen pendientes.
ETAPAS_IMPLEMENTADAS = ("detect", "track", "zones", "interact", "metrics")
ETAPAS_PENDIENTES = [e for e in STAGES if e.name not in ETAPAS_IMPLEMENTADAS]


@pytest.fixture(autouse=True)
def entorno_limpio(tmp_path, monkeypatch):
    """Apunta la configuracion a carpetas temporales, sin tocar el .env real."""
    monkeypatch.setenv("VIDEO_ID", "video_001")
    monkeypatch.setenv("VIDEO_PATH", str(tmp_path / "videos" / "scapder.mp4"))
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "models" / "yolo11n.pt"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    return tmp_path


# --------------------------------------------------------------------------
# doctor: informa, nunca falla
# --------------------------------------------------------------------------

def test_doctor_devuelve_cero_aunque_falte_todo(capsys):
    """No hay video ni modelo y aun asi doctor sale con 0: su trabajo es informar."""
    assert main(["doctor"]) == EXIT_OK
    salida = capsys.readouterr().out
    assert "FALTA" in salida  # y lo reporta


def test_doctor_devuelve_cero_aunque_el_env_este_roto(monkeypatch, capsys):
    """Si doctor reventara con un .env malo seria inutil justo cuando mas se necesita."""
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "no_es_un_numero")
    assert main(["doctor"]) == EXIT_OK
    assert "CONFIDENCE_THRESHOLD" in capsys.readouterr().out


def test_doctor_muestra_las_cinco_etapas_y_sus_responsables(capsys):
    main(["doctor"])
    salida = capsys.readouterr().out
    for etapa in STAGES:
        assert etapa.name in salida
        assert etapa.owner in salida


def test_doctor_muestra_la_configuracion_resuelta(capsys):
    main(["doctor"])
    salida = capsys.readouterr().out
    assert "video_001" in salida
    assert "CONFIDENCE_THRESHOLD" in salida


# --------------------------------------------------------------------------
# Las etapas: placeholders
# --------------------------------------------------------------------------

@pytest.mark.parametrize("nombre", STAGE_NAMES)
def test_un_placeholder_sin_su_entrada_avisa_que_falta_el_requisito(nombre):
    """Falta la entrada: es un problema distinto de que falte el codigo, y sale con 2."""
    assert main([nombre]) == EXIT_FALTA_REQUISITO


@pytest.mark.parametrize("etapa", ETAPAS_PENDIENTES, ids=lambda e: e.name)
def test_un_placeholder_con_su_entrada_lista_devuelve_error(etapa, entorno_limpio):
    """Ya no falta nada salvo el codigo: sale con 1 para que `run` se detenga."""
    _crear_entrada_de(etapa, entorno_limpio)
    assert main([etapa.name]) == EXIT_ERROR


def _crear_entrada_de(etapa, tmp_path):
    """Crea el archivo (o el video falso) que esa etapa espera encontrar."""
    if etapa.input_suffix is None:
        entrada = tmp_path / "videos" / "scapder.mp4"
    else:
        entrada = tmp_path / "output" / f"video_001{etapa.input_suffix}"
    entrada.parent.mkdir(parents=True, exist_ok=True)
    entrada.write_text("", encoding="utf-8")


@pytest.mark.parametrize("etapa", ETAPAS_PENDIENTES, ids=lambda e: e.name)
def test_el_placeholder_dice_de_quien_es_y_que_archivos_usa(etapa, capsys):
    """Es lo primero que vera el companero al que le toque el modulo."""
    main([etapa.name])
    salida = capsys.readouterr().out
    assert etapa.owner in salida
    assert f"gondola/stages/{etapa.name}.py" in salida
    assert etapa.output_suffix in salida  # que archivo debe producir


def test_track_sin_su_entrada_dice_que_corras_detect_primero(capsys):
    """track ya esta implementada: sin video_001.detect.jsonl debe fallar con
    codigo 2 y un mensaje claro, nunca con un traceback."""
    assert main(["track"]) == EXIT_FALTA_REQUISITO
    salida = capsys.readouterr()
    assert "python -m gondola detect" in salida.err
    assert "Traceback" not in salida.err


def test_metrics_sin_su_entrada_dice_que_corras_interact_primero(capsys):
    """metrics ya esta implementada: sin video_001.interact.jsonl debe fallar
    con codigo 2 y un mensaje claro, nunca con un traceback."""
    assert main(["metrics"]) == EXIT_FALTA_REQUISITO
    salida = capsys.readouterr()
    assert "python -m gondola interact" in salida.err
    assert "Traceback" not in salida.err


def test_un_subcomando_inventado_no_arranca():
    """argparse rechaza el comando antes de tocar nada."""
    with pytest.raises(SystemExit):
        main(["deteccion"])


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

def test_run_se_detiene_en_detect_si_no_hay_video(capsys):
    """Sin video, detect no puede arrancar: codigo 2 y se dice donde paro."""
    assert main(["run"]) == EXIT_FALTA_REQUISITO
    salida = capsys.readouterr().out
    assert "se detiene en 'detect'" in salida
    assert "[metrics]" not in salida  # no sigue con las siguientes


def test_run_dice_donde_paro_aunque_la_etapa_lance_una_excepcion(entorno_limpio, capsys):
    """Un video corrupto revienta dentro de detect; run debe seguir diciendo donde paro.

    Si el error se dejara subir hasta main(), el codigo de salida seria correcto
    pero se perderia el mensaje de "la cadena se detiene en X".
    """
    pytest.importorskip("cv2")
    video = entorno_limpio / "videos" / "scapder.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_text("esto no es un video", encoding="utf-8")

    assert main(["run"]) == EXIT_ERROR
    salida = capsys.readouterr().out
    assert "se detiene en 'detect'" in salida
    assert "[track]" not in salida


# --------------------------------------------------------------------------
# purge
# --------------------------------------------------------------------------

def test_purge_pide_confirmacion_y_no_borra_si_dices_que_no(entorno_limpio, monkeypatch, capsys):
    video = entorno_limpio / "videos" / "scapder.mp4"
    video.parent.mkdir(parents=True)
    video.write_text("contenido falso", encoding="utf-8")

    monkeypatch.setattr("builtins.input", lambda _: "no")
    assert main(["purge"]) == EXIT_OK
    assert video.exists()
    assert "Cancelado" in capsys.readouterr().out


def test_purge_borra_cuando_confirmas(entorno_limpio, monkeypatch):
    video = entorno_limpio / "videos" / "scapder.mp4"
    video.parent.mkdir(parents=True)
    video.write_text("contenido falso", encoding="utf-8")
    salida = entorno_limpio / "output" / "video_001.detect.jsonl"
    salida.parent.mkdir(parents=True)
    salida.write_text("", encoding="utf-8")

    monkeypatch.setattr("builtins.input", lambda _: "si")
    assert main(["purge"]) == EXIT_OK
    assert not video.exists()
    assert not salida.exists()


def test_purge_no_borra_los_readme(entorno_limpio, monkeypatch):
    """Los README explican que va en cada carpeta: borrarlos deja la carpeta muda."""
    carpeta = entorno_limpio / "videos"
    carpeta.mkdir(parents=True)
    readme = carpeta / "README.md"
    readme.write_text("COLOCAR AQUI EL VIDEO", encoding="utf-8")
    (carpeta / "scapder.mp4").write_text("falso", encoding="utf-8")

    monkeypatch.setattr("builtins.input", lambda _: "si")
    main(["purge"])
    assert readme.exists()


def test_purge_con_yes_no_pregunta(entorno_limpio):
    video = entorno_limpio / "videos" / "scapder.mp4"
    video.parent.mkdir(parents=True)
    video.write_text("falso", encoding="utf-8")

    # Si intentara preguntar, input() reventaria: en los tests no hay teclado.
    assert main(["purge", "--yes"]) == EXIT_OK
    assert not video.exists()


def test_purge_sin_nada_que_borrar(capsys):
    assert main(["purge"]) == EXIT_OK
    assert "No hay nada que borrar" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Codigos de salida
# --------------------------------------------------------------------------

def test_los_tres_codigos_de_salida_son_distintos():
    """0 exito, 1 error, 2 falta un requisito. Un script que llame a la CLI los distingue."""
    assert len({EXIT_OK, EXIT_ERROR, EXIT_FALTA_REQUISITO}) == 3


# --------------------------------------------------------------------------
# Opciones de linea de comandos: sobrescriben el .env solo para esa corrida
# --------------------------------------------------------------------------

def config_con(argv):
    """Parsea los argumentos como lo hace la CLI y devuelve la config resultante."""
    args = _parser().parse_args(argv)
    return _aplicar_opciones(load_config(), args)


def test_sin_opciones_la_configuracion_no_se_toca():
    assert config_con(["detect"]) == load_config()


def test_las_opciones_ganan_al_env_para_esa_corrida():
    cfg = config_con(["detect", "--conf", "0.9", "--stride", "5",
                      "--max-frames", "50", "--imgsz", "320",
                      "--device", "cpu", "--render", "none"])
    assert cfg.confidence_threshold == 0.9
    assert cfg.frame_stride == 5
    assert cfg.max_frames == 50
    assert cfg.imgsz == 320
    assert cfg.render_mode == "none"
    # Las opciones no modifican la configuracion cargada del .env: arman otra.
    assert cfg != load_config()


def test_track_acepta_render_y_open_igual_que_detect():
    """Persona 4, 5 y 6 copian este modulo como plantilla: --render y --open
    deben llamarse y comportarse igual en las dos etapas."""
    cfg = config_con(["track", "--render", "debug"])
    assert cfg.render_mode == "debug"

    args = _parser().parse_args(["track", "--render", "none", "--open"])
    assert args.render == "none"
    assert args.open is True


def test_max_frames_cero_por_opcion_significa_video_completo():
    """0 es un valor legitimo, no 'no me pasaron nada': tiene que llegar igual."""
    assert config_con(["detect", "--max-frames", "0"]).max_frames == 0


def test_pasar_otro_video_cambia_tambien_el_video_id(entorno_limpio):
    """Si no cambiara, dos videos distintos escribirian en el mismo archivo.

    El segundo borraria la salida del primero sin avisar. El video_id sale del
    nombre del archivo justamente para que eso no pueda pasar.
    """
    otro = entorno_limpio / "videos" / "clip_formas.mp4"
    otro.parent.mkdir(parents=True, exist_ok=True)
    otro.write_text("falso", encoding="utf-8")

    cfg = config_con(["detect", "--video", str(otro)])
    assert cfg.video_id == "clip_formas"
    assert cfg.video_path == otro

    original = stage_paths("detect", load_config()).output_path
    nueva = stage_paths("detect", cfg).output_path
    assert original.name != nueva.name


# --------------------------------------------------------------------------
# La jerarquia de errores es la que sostiene los codigos de salida
# --------------------------------------------------------------------------

def test_todos_los_errores_del_proyecto_cuelgan_de_GondolaError():
    """`except GondolaError` en la CLI tiene que atrapar todo lo nuestro."""
    for error in (ConfigError, ContractError, PipelineError,
                  MissingInputError, VideoError, ModelError):
        assert issubclass(error, GondolaError)


def test_falta_de_requisito_es_un_caso_aparte_dentro_de_la_jerarquia():
    """Es un PipelineError, pero la CLI lo atrapa ANTES para darle el codigo 2.

    Si alguien invierte el orden de los `except` en main(), todo pasaria a ser
    codigo 1 y se perderia la distincion entre 'fallo' y 'todavia no toca'.
    """
    assert issubclass(MissingInputError, PipelineError)
    assert main(["track"]) == EXIT_FALTA_REQUISITO


def test_un_error_del_proyecto_sale_con_codigo_1_y_sin_traceback(monkeypatch, capsys):
    def revienta(*args, **kwargs):
        raise VideoError("el video esta corrupto. Que hacer: vuelve a copiarlo.")

    monkeypatch.setattr("gondola.cli.comando_etapa", revienta)
    assert main(["track"]) == EXIT_ERROR
    assert "Que hacer" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Logging: se configura una sola vez, al arrancar
# --------------------------------------------------------------------------

def test_configurar_el_logging_dos_veces_no_duplica_los_mensajes():
    """setup_logging() se llama al arrancar. Si dejara handlers viejos pegados,
    cada mensaje del pipeline saldria dos veces por pantalla."""
    raiz = logging.getLogger()
    handlers, nivel = raiz.handlers[:], raiz.level
    try:
        setup_logging("INFO")
        setup_logging("DEBUG")
        assert len(raiz.handlers) == 1
        assert raiz.level == logging.DEBUG
    finally:
        raiz.handlers[:] = handlers
        raiz.setLevel(nivel)
