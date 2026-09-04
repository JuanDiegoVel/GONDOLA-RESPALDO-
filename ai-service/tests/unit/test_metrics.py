"""Tests de las metricas agregadas (gondola/stages/metrics.py).

Todo lo de aqui corre con solo `pip install -r requirements-dev.txt`: la
etapa es una agregacion pura de .jsonl y no necesita YOLO, ni OpenCV, ni el
video.
"""

import json

import pytest
from pydantic import ValidationError

from gondola import pipeline
from gondola.config import load_config
from gondola.contract import BBox, Detection, Event, InteractionEvent
from gondola.errors import MissingInputError
from gondola.jsonl import write_events
from gondola.stages.metrics import _agregar, run, ZoneMetrics

BBOX = BBox(x=0.0, y=0.0, width=100.0, height=200.0)


def crear_evento(
    frame, track_id=1, zone_id="gondola_A", dwell=1.0, interaction=None,
    video_id="video_001",
) -> Event:
    """Un evento minimo como los que produce `interact`: con track_id, zone
    (o sin ella, si `zone_id=None`) e interaccion opcional."""
    evento = Event(
        video_id=video_id,
        frame=frame,
        timestamp=frame / 30.0,
        track_id=track_id,
        detection=Detection(confidence=0.9, bbox=BBOX),
    )
    evento.zone.zone_id = zone_id
    evento.metrics.dwell_time = dwell
    evento.interaction.event = interaction
    return evento


def test_zone_metrics_rechaza_conteos_negativos():
    with pytest.raises(ValidationError):
        ZoneMetrics(
            people_count=-1,
            interaction_count=0,
            pick_up_count=0,
            put_back_count=0,
        )


def test_zone_metrics_rechaza_una_tasa_fuera_de_0_1():
    with pytest.raises(ValidationError):
        ZoneMetrics(
            people_count=1,
            interaction_count=2,
            pick_up_count=2,
            put_back_count=0,
            interaction_rate=1.5,
        )


def test_zone_metrics_acepta_valores_validos_con_promedio_en_null():
    metrics = ZoneMetrics(
        people_count=3,
        interaction_count=2,
        pick_up_count=1,
        put_back_count=1,
        average_dwell_time_s=None,
        interaction_rate=2 / 3,
        pick_up_rate=0.5,
        conversion_rate=1 / 3,
    )
    assert metrics.people_count == 3
    assert metrics.average_dwell_time_s is None


# --------------------------------------------------------------------------
# _agregar: logica pura, sin pasar por run() ni por disco
# --------------------------------------------------------------------------

def test_un_track_con_muchos_eventos_cuenta_como_una_sola_persona():
    """El bug que `schema.sql` llama 'el mas caro del proyecto': una persona
    parada genera cientos de eventos, y people_count debe seguir siendo 1."""
    eventos = [crear_evento(frame=i, track_id=7) for i in range(50)]

    agregados = _agregar(eventos)

    assert agregados["gondola_A"].people_count == 1


def test_cuenta_pick_up_put_back_y_approach_por_zona():
    eventos = [
        crear_evento(frame=0, track_id=1, interaction=InteractionEvent.APPROACH),
        crear_evento(frame=1, track_id=1, interaction=InteractionEvent.PICK_UP),
        crear_evento(frame=2, track_id=1, interaction=InteractionEvent.PUT_BACK),
        crear_evento(frame=3, track_id=1, interaction=None),
    ]

    agregados = _agregar(eventos)
    zona = agregados["gondola_A"]

    assert zona.interaction_count == 3  # APPROACH + PICK_UP + PUT_BACK
    assert zona.pick_up_count == 1
    assert zona.put_back_count == 1


def test_varias_interacciones_de_la_misma_persona_no_pasan_la_tasa_de_1():
    """`etiqueta_de_alcance` (interact.py) puede darle a un track varios
    PICK_UP/PUT_BACK en una sola visita: interaction_count/people_count
    se pasaria de 1.0 y rompe el CHECK de schema.sql. Las tasas se definen
    sobre personas DISTINTAS que interactuaron, no sobre el conteo crudo."""
    eventos = [
        crear_evento(frame=0, track_id=1, interaction=InteractionEvent.APPROACH),
        crear_evento(frame=1, track_id=1, interaction=InteractionEvent.PICK_UP),
        crear_evento(frame=2, track_id=1, interaction=InteractionEvent.PUT_BACK),
        crear_evento(frame=3, track_id=1, interaction=InteractionEvent.PICK_UP),
    ]

    zona = _agregar(eventos)["gondola_A"]

    assert zona.interaction_count == 4  # conteo crudo, puede superar people_count
    assert zona.people_count == 1
    assert zona.interaction_rate == 1.0  # 1 persona distinta interactuo, no 4.0
    assert zona.conversion_rate == 1.0   # 1 persona distinta hizo PICK_UP


def test_promedio_de_dwell_time_ignora_los_null_y_no_revienta_si_todos_son_null():
    con_dwell = [crear_evento(frame=0, track_id=1, dwell=2.0)]
    con_dwell.append(crear_evento(frame=1, track_id=1, dwell=None))
    con_dwell.append(crear_evento(frame=2, track_id=1, dwell=4.0))

    agregados = _agregar(con_dwell)
    assert agregados["gondola_A"].average_dwell_time_s == pytest.approx(3.0)

    todos_sin_dwell = [crear_evento(frame=0, track_id=1, dwell=None)]
    agregados_sin_dwell = _agregar(todos_sin_dwell)
    assert agregados_sin_dwell["gondola_A"].average_dwell_time_s is None


def test_dos_zonas_no_mezclan_sus_contadores():
    eventos = [
        crear_evento(frame=0, track_id=1, zone_id="gondola_A",
                     interaction=InteractionEvent.PICK_UP),
        crear_evento(frame=1, track_id=2, zone_id="gondola_B"),
    ]

    agregados = _agregar(eventos)

    assert agregados["gondola_A"].people_count == 1
    assert agregados["gondola_A"].pick_up_count == 1
    assert agregados["gondola_B"].people_count == 1
    assert agregados["gondola_B"].pick_up_count == 0


def test_agregar_sin_eventos_devuelve_diccionario_vacio():
    assert _agregar([]) == {}


def test_eventos_sin_zona_no_cuentan_para_ninguna_zona():
    eventos = [crear_evento(frame=0, track_id=1, zone_id=None)]
    assert _agregar(eventos) == {}


# --------------------------------------------------------------------------
# run(): integracion completa, con archivos temporales
# --------------------------------------------------------------------------

def preparar_entorno(tmp_path, monkeypatch, eventos):
    """Deja en tmp_path el .interact.jsonl de entrada y devuelve (cfg, rutas)."""
    monkeypatch.setenv("VIDEO_ID", "video_001")
    monkeypatch.setenv("VIDEO_PATH", str(tmp_path / "videos" / "video_001.mp4"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    cfg = load_config()
    rutas = pipeline.stage_paths("metrics", cfg)
    rutas.input_path.parent.mkdir(parents=True, exist_ok=True)
    write_events(rutas.input_path, eventos)
    return cfg, rutas


def test_run_sin_interact_jsonl_falla_con_falta_de_requisito(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_ID", "video_001")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    with pytest.raises(MissingInputError):
        run(load_config())


def test_run_con_interact_jsonl_vacio_escribe_metrics_json_valido(tmp_path, monkeypatch):
    cfg, rutas = preparar_entorno(tmp_path, monkeypatch, [])

    assert run(cfg) == 0

    datos = json.loads(rutas.output_path.read_text(encoding="utf-8"))
    assert datos["video_id"] == "video_001"
    assert datos["zones"] == {}

    resumen = json.loads(pipeline.summary_path("metrics", cfg).read_text(encoding="utf-8"))
    assert resumen["results"]["eventos_procesados"] == 0
    assert resumen["results"]["zonas_encontradas"] == 0


def test_run_con_eventos_reales_escribe_los_numeros_esperados(tmp_path, monkeypatch, capsys):
    eventos = [
        crear_evento(frame=0, track_id=1, zone_id="gondola_A",
                     interaction=InteractionEvent.APPROACH, dwell=2.0),
        crear_evento(frame=1, track_id=1, zone_id="gondola_A",
                     interaction=InteractionEvent.PICK_UP, dwell=2.5),
        crear_evento(frame=2, track_id=2, zone_id="gondola_A", dwell=1.0),
    ]
    cfg, rutas = preparar_entorno(tmp_path, monkeypatch, eventos)

    assert run(cfg) == 0

    datos = json.loads(rutas.output_path.read_text(encoding="utf-8"))
    zona = datos["zones"]["gondola_A"]
    assert zona["people_count"] == 2
    assert zona["interaction_count"] == 2
    assert zona["pick_up_count"] == 1
    assert zona["conversion_rate"] == pytest.approx(0.5)  # 1 de 2 personas

    salida = capsys.readouterr().out
    assert "Zonas encontradas" in salida
    assert "gondola_A" in salida
    assert "track_id" not in salida.lower()  # nunca listar ids individuales
