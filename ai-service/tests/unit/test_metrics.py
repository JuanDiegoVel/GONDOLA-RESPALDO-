"""Tests de las metricas agregadas (gondola/stages/metrics.py).

Todo lo de aqui corre con solo `pip install -r requirements-dev.txt`: la
etapa es una agregacion pura de .jsonl y no necesita YOLO, ni OpenCV, ni el
video.

Reescrito contra la version de metrics.py que de verdad esta en el
repositorio hoy (acumular_evento/cerrar_zona, no la version anterior con
_agregar/ZoneMetrics): ese archivo cambio de implementacion sin que este
archivo se actualizara, y quedo importando un nombre que ya no existe.
"""

import json

import pytest

from gondola import pipeline
from gondola.config import load_config
from gondola.contract import BBox, Detection, Event, InteractionEvent
from gondola.errors import MissingInputError
from gondola.jsonl import write_events
from gondola.stages.metrics import Resumen, acumular_evento, cerrar_zona, run

BBOX = BBox(x=0.0, y=0.0, width=100.0, height=200.0)


def crear_evento(
    frame, track_id=1, zone_id="gondola_A", segment=None, dwell=1.0,
    interaction=None, video_id="video_001",
) -> Event:
    """Un evento minimo como los que produce `interact`: con track_id, zone
    (o sin ella, si `zone_id=None`), segmento opcional e interaccion
    opcional."""
    evento = Event(
        video_id=video_id,
        frame=frame,
        timestamp=frame / 30.0,
        track_id=track_id,
        detection=Detection(confidence=0.9, bbox=BBOX),
    )
    evento.zone.zone_id = zone_id
    evento.zone.segment = segment
    evento.metrics.dwell_time = dwell
    evento.interaction.event = interaction
    return evento


def _agregar(eventos) -> dict:
    """Atajo para los tests de logica pura: acumula una lista de eventos y
    devuelve las filas ya cerradas (gondola/estante -> columnas de
    metrics.json), sin pasar por archivos ni por run()."""
    agregados = {}
    resumen = Resumen()
    for evento in eventos:
        acumular_evento(agregados, evento, resumen)
    return {fila_id: cerrar_zona(zona) for fila_id, zona in agregados.items()}


# --------------------------------------------------------------------------
# acumular_evento/cerrar_zona: logica pura, sin pasar por run() ni por disco
# --------------------------------------------------------------------------

def test_un_track_con_muchos_eventos_cuenta_como_una_sola_persona():
    """El bug mas caro del proyecto: una persona parada genera cientos de
    eventos, y people_count debe seguir siendo 1."""
    eventos = [crear_evento(frame=i, track_id=7) for i in range(50)]

    filas = _agregar(eventos)

    assert filas["gondola_A"]["people_count"] == 1


def test_cuenta_pick_up_put_back_y_approach_por_zona():
    eventos = [
        crear_evento(frame=0, track_id=1, interaction=InteractionEvent.APPROACH),
        crear_evento(frame=1, track_id=1, interaction=InteractionEvent.PICK_UP),
        crear_evento(frame=2, track_id=1, interaction=InteractionEvent.PUT_BACK),
        crear_evento(frame=3, track_id=1, interaction=None),
    ]

    zona = _agregar(eventos)["gondola_A"]

    assert zona["interaction_count"] == 3  # APPROACH + PICK_UP + PUT_BACK
    assert zona["pick_up_count"] == 1
    assert zona["put_back_count"] == 1


def test_varias_interacciones_de_la_misma_persona_no_pasan_la_tasa_de_1():
    """`etiqueta_de_alcance` (interact.py) puede darle a un track varios
    PICK_UP/PUT_BACK en una sola visita: interaction_count/people_count se
    pasaria de 1.0 y rompe el CHECK de schema.sql. `_tasa()` recorta a 1.0
    a proposito -ver su docstring-, y people_count sigue siendo DISTINCT."""
    eventos = [
        crear_evento(frame=0, track_id=1, interaction=InteractionEvent.APPROACH),
        crear_evento(frame=1, track_id=1, interaction=InteractionEvent.PICK_UP),
        crear_evento(frame=2, track_id=1, interaction=InteractionEvent.PUT_BACK),
        crear_evento(frame=3, track_id=1, interaction=InteractionEvent.PICK_UP),
    ]

    zona = _agregar(eventos)["gondola_A"]

    assert zona["interaction_count"] == 4  # conteo crudo, puede superar people_count
    assert zona["people_count"] == 1
    assert zona["interaction_rate"] == 1.0  # 1 persona distinta interactuo, no 4.0
    assert zona["conversion_rate"] == 1.0   # recortado a 1.0, no 4.0


def test_promedio_de_dwell_time_ignora_los_null_y_no_revienta_si_todos_son_null():
    con_dwell = [
        crear_evento(frame=0, track_id=1, dwell=2.0),
        crear_evento(frame=1, track_id=1, dwell=None),
        crear_evento(frame=2, track_id=1, dwell=4.0),
    ]

    zona = _agregar(con_dwell)["gondola_A"]
    assert zona["average_dwell_time_s"] == pytest.approx(4.0)  # el MAXIMO visto por esa persona, no un promedio de filas

    todos_sin_dwell = [crear_evento(frame=0, track_id=1, dwell=None)]
    zona_sin_dwell = _agregar(todos_sin_dwell)["gondola_A"]
    assert zona_sin_dwell["average_dwell_time_s"] is None


def test_dos_gondolas_no_mezclan_sus_contadores():
    eventos = [
        crear_evento(frame=0, track_id=1, zone_id="gondola_A",
                     interaction=InteractionEvent.PICK_UP),
        crear_evento(frame=1, track_id=2, zone_id="gondola_B"),
    ]

    filas = _agregar(eventos)

    assert filas["gondola_A"]["people_count"] == 1
    assert filas["gondola_A"]["pick_up_count"] == 1
    assert filas["gondola_B"]["people_count"] == 1
    assert filas["gondola_B"]["pick_up_count"] == 0


def test_agregar_sin_eventos_devuelve_diccionario_vacio():
    assert _agregar([]) == {}


def test_eventos_sin_zona_no_cuentan_para_ninguna_fila():
    eventos = [crear_evento(frame=0, track_id=1, zone_id=None)]
    assert _agregar(eventos) == {}


def test_evento_con_estante_aporta_a_la_gondola_y_a_su_propio_estante():
    """Cada evento con segment aporta a DOS filas: la gondola completa
    (para el total de la vitrina) y "gondola:estante" (para comparar
    estantes entre si). Es lo que arreglo el bug de que
    GET /videos/{id}/zones solo devolviera la gondola, nunca sus estantes
    -ver el docstring de metrics.py, seccion 'QUE ZONA SE USA PARA
    AGRUPAR'-."""
    eventos = [
        crear_evento(frame=0, track_id=1, zone_id="gondola_A", segment="estante_1",
                     interaction=InteractionEvent.PICK_UP),
        crear_evento(frame=1, track_id=2, zone_id="gondola_A", segment="estante_2"),
        # alguien frente a la gondola sin que el tracker lo ubique en un estante:
        crear_evento(frame=2, track_id=3, zone_id="gondola_A", segment=None),
    ]

    filas = _agregar(eventos)

    assert set(filas.keys()) == {"gondola_A", "gondola_A:estante_1", "gondola_A:estante_2"}
    assert filas["gondola_A"]["people_count"] == 3       # los 3 tracks, gondola completa
    assert filas["gondola_A"]["pick_up_count"] == 1
    assert filas["gondola_A:estante_1"]["people_count"] == 1
    assert filas["gondola_A:estante_1"]["pick_up_count"] == 1
    assert filas["gondola_A:estante_2"]["people_count"] == 1
    assert filas["gondola_A:estante_2"]["pick_up_count"] == 0


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


def test_run_con_eventos_reales_escribe_los_numeros_esperados(tmp_path, monkeypatch, capsys):
    eventos = [
        crear_evento(frame=0, track_id=1, zone_id="gondola_A", segment="estante_1",
                     interaction=InteractionEvent.APPROACH, dwell=2.0),
        crear_evento(frame=1, track_id=1, zone_id="gondola_A", segment="estante_1",
                     interaction=InteractionEvent.PICK_UP, dwell=2.5),
        crear_evento(frame=2, track_id=2, zone_id="gondola_A", dwell=1.0),
    ]
    cfg, rutas = preparar_entorno(tmp_path, monkeypatch, eventos)

    assert run(cfg) == 0

    datos = json.loads(rutas.output_path.read_text(encoding="utf-8"))
    zonas = datos["zones"]

    gondola = zonas["gondola_A"]
    assert gondola["people_count"] == 2
    assert gondola["interaction_count"] == 2
    assert gondola["pick_up_count"] == 1
    assert gondola["conversion_rate"] == pytest.approx(0.5)  # 1 de 2 personas

    estante = zonas["gondola_A:estante_1"]
    assert estante["people_count"] == 1
    assert estante["pick_up_count"] == 1

    salida = capsys.readouterr().out
    assert "Zonas con datos" in salida
    assert "gondola_A" in salida
    assert "track_id" not in salida.lower()  # nunca listar ids individuales
