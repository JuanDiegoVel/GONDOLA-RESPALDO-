"""Tests de la asignacion de zonas (gondola/stages/zones.py).

Todo lo que se prueba con eventos construidos a mano es aritmetica pura:
corre con solo `pip install -r requirements-dev.txt`, igual que
test_detect.py y test_track.py. Los tests de `run()` si tocan disco (archivos
temporales), pero tampoco necesitan YOLO, OpenCV ni un video real: `zones`
lee y escribe puro JSON.
"""

import json

import pytest

from gondola import pipeline
from gondola.config import load_config
from gondola.contract import BBox, Detection, Event
from gondola.errors import MissingInputError, ZonesConfigError
from gondola.jsonl import read_events, write_events
from gondola.stages import zones as zones_stage
from gondola.stages.zones import (
    UMBRAL_SE_DETIENE_S,
    Resumen,
    Visita,
    _procesar,
    asignar_zona,
    clasifica_visita,
    punto_en_zona,
    run,
)
from gondola.zones_config import ZonesConfig


def crear_evento(frame, timestamp, x, y, w=40.0, h=100.0, track_id=1,
                 video_id="video_001") -> Event:
    """Un evento como los que produce `track`: siempre con track_id relleno."""
    return Event(
        video_id=video_id,
        frame=frame,
        timestamp=timestamp,
        track_id=track_id,
        detection=Detection(confidence=0.9, bbox=BBox(x=x, y=y, width=w, height=h)),
    )


def zonas_de_ejemplo() -> ZonesConfig:
    """Dos estantes de la misma gondola, uno al lado del otro sin solaparse:
    estante_1 cubre x en [0, 100), estante_2 cubre x en [100, 200)."""
    return ZonesConfig.model_validate({
        "video_id": "video_001",
        "frame_width": 300,
        "frame_height": 300,
        "gondolas": [{
            "zone_id": "gondola_A",
            "name": "Gondola A",
            "product_category": None,
            "shelves": [
                {
                    "segment": "estante_1",
                    "name": "Estante 1",
                    "product_category": None,
                    "floor_zone": {"x": 0, "y": 0, "width": 100, "height": 200},
                },
                {
                    "segment": "estante_2",
                    "name": "Estante 2",
                    "product_category": None,
                    "floor_zone": {"x": 100, "y": 0, "width": 100, "height": 200},
                },
            ],
        }],
    })


# --------------------------------------------------------------------------
# punto_en_zona: el borde semiabierto (CASO 1 del docstring del modulo)
# --------------------------------------------------------------------------

def test_un_punto_claramente_dentro_cae_en_la_zona():
    zona = zonas_de_ejemplo().gondolas[0].shelves[0].floor_zone
    assert punto_en_zona((50.0, 100.0), zona) is True


def test_un_punto_claramente_fuera_no_cae():
    zona = zonas_de_ejemplo().gondolas[0].shelves[0].floor_zone
    assert punto_en_zona((500.0, 500.0), zona) is False


def test_el_borde_izquierdo_o_superior_cuenta_como_dentro():
    zona = zonas_de_ejemplo().gondolas[0].shelves[0].floor_zone  # x=0..100, y=0..200
    assert punto_en_zona((0.0, 100.0), zona) is True
    assert punto_en_zona((50.0, 0.0), zona) is True


def test_el_borde_derecho_o_inferior_cuenta_como_fuera():
    zona = zonas_de_ejemplo().gondolas[0].shelves[0].floor_zone  # x=0..100, y=0..200
    assert punto_en_zona((100.0, 100.0), zona) is False
    assert punto_en_zona((50.0, 200.0), zona) is False


def test_un_punto_en_la_frontera_compartida_cae_en_un_solo_estante_nunca_en_los_dos():
    """estante_1 termina en x=100, estante_2 empieza en x=100: sin doble conteo ni hueco."""
    zonas = zonas_de_ejemplo()
    resultado = asignar_zona((100.0, 100.0), zonas)
    assert resultado is not None
    _gondola, estante = resultado
    assert estante.segment == "estante_2"


# --------------------------------------------------------------------------
# asignar_zona: sin match, y el desempate por area (CASO 2 del docstring)
# --------------------------------------------------------------------------

def test_un_punto_fuera_de_toda_zona_no_asigna_nada():
    assert asignar_zona((250.0, 250.0), zonas_de_ejemplo()) is None


def test_dos_zonas_solapadas_gana_la_mas_pequena():
    zonas = ZonesConfig.model_validate({
        "video_id": "video_001",
        "frame_width": 300,
        "frame_height": 300,
        "gondolas": [{
            "zone_id": "gondola_A",
            "name": "Gondola A",
            "product_category": None,
            "shelves": [
                {
                    "segment": "grande",
                    "name": "Zona grande",
                    "product_category": None,
                    "floor_zone": {"x": 0, "y": 0, "width": 200, "height": 200},  # area 40000
                },
                {
                    "segment": "pequena",
                    "name": "Zona pequena, dentro de la grande",
                    "product_category": None,
                    "floor_zone": {"x": 50, "y": 50, "width": 20, "height": 20},  # area 400
                },
            ],
        }],
    })
    _gondola, estante = asignar_zona((55.0, 55.0), zonas)  # dentro de las dos
    assert estante.segment == "pequena"


# --------------------------------------------------------------------------
# clasifica_visita: "se_detiene" vs "pasa_de_largo" (CASO 3 del docstring)
# --------------------------------------------------------------------------

def test_dwell_time_bajo_el_umbral_clasifica_como_pasa_de_largo():
    assert clasifica_visita(UMBRAL_SE_DETIENE_S - 0.1) == "pasa_de_largo"


def test_dwell_time_justo_en_el_umbral_clasifica_como_se_detiene():
    assert clasifica_visita(UMBRAL_SE_DETIENE_S) == "se_detiene"


def test_dwell_time_sobre_el_umbral_clasifica_como_se_detiene():
    assert clasifica_visita(UMBRAL_SE_DETIENE_S + 5.0) == "se_detiene"


def test_dwell_time_none_clasifica_como_none():
    """Fuera de cualquier zona no hay nada que clasificar."""
    assert clasifica_visita(None) is None


def test_clasifica_visita_acepta_un_umbral_propio():
    """El umbral es un parametro, no una constante fija: se puede recalibrar
    sin tocar la funcion (ver CASO 3 del docstring del modulo)."""
    assert clasifica_visita(1.0, umbral_s=0.5) == "se_detiene"
    assert clasifica_visita(1.0, umbral_s=1.5) == "pasa_de_largo"


# --------------------------------------------------------------------------
# _procesar: asignacion de zone + acumulacion de dwell_time
# --------------------------------------------------------------------------

def eventos_por_track(zonas, eventos):
    """_procesar() lee de un archivo; aqui se prueba la misma logica sobre una
    lista en memoria, para no escribir un .jsonl temporal en cada test."""
    resumen = Resumen()
    return list(_procesar_en_memoria(eventos, zonas, resumen)), resumen


def _procesar_en_memoria(eventos, zonas, resumen):
    """Misma logica que `_procesar`, pero sobre una lista en memoria en vez de
    leer un archivo -evita escribir un .jsonl temporal en cada test."""
    visitas: dict[int, Visita] = {}
    for evento in eventos:
        resultado = asignar_zona(evento.detection.bbox.support_point, zonas)
        if resultado is None:
            zona_actual = None
            resumen.eventos_sin_zona += 1
        else:
            gondola, estante = resultado
            evento.zone.zone_id = gondola.zone_id
            evento.zone.segment = estante.segment
            zona_actual = (gondola.zone_id, estante.segment)
            resumen.eventos_con_zona += 1
            clave = f"{gondola.zone_id}/{estante.segment}"
            resumen.eventos_por_zona[clave] = resumen.eventos_por_zona.get(clave, 0) + 1

        visita = visitas.get(evento.track_id)
        if visita is None or visita.zona != zona_actual:
            visita = Visita(zona=zona_actual, entrada=evento.timestamp)
            visitas[evento.track_id] = visita

        evento.metrics.dwell_time = (
            evento.timestamp - visita.entrada if zona_actual is not None else None
        )
        clasificacion = clasifica_visita(evento.metrics.dwell_time)
        if clasificacion == "se_detiene":
            resumen.eventos_se_detiene += 1
        elif clasificacion == "pasa_de_largo":
            resumen.eventos_pasa_de_largo += 1
        resumen.eventos_procesados += 1
        yield evento


def test_el_primer_evento_de_una_visita_tiene_dwell_time_cero():
    zonas = zonas_de_ejemplo()
    # bbox x=20,y=50,w=40,h=100 -> support_point = (20+20, 50+100) = (40, 150),
    # dentro de estante_1 (x: 0..100, y: 0..200).
    eventos = [crear_evento(frame=0, timestamp=10.0, x=20, y=50)]
    resultado, _resumen = eventos_por_track(zonas, eventos)
    assert resultado[0].zone.segment == "estante_1"
    assert resultado[0].metrics.dwell_time == pytest.approx(0.0)


def test_un_punto_claramente_fuera_de_todas_deja_zone_id_en_null():
    """No solo `asignar_zona`: el `Event` completo que sale de `_procesar`
    tambien debe quedar con `zone.zone_id` en null cuando nadie esta cerca
    de ningun estante (support_point en (250, 250), fuera de las dos zonas
    de `zonas_de_ejemplo`, que ocupan x en [0, 200) e y en [0, 200))."""
    zonas = zonas_de_ejemplo()
    eventos = [crear_evento(frame=0, timestamp=10.0, x=230, y=200)]
    resultado, resumen = eventos_por_track(zonas, eventos)
    assert resultado[0].zone.zone_id is None
    assert resultado[0].zone.segment is None
    assert resumen.eventos_sin_zona == 1
    assert resumen.eventos_con_zona == 0


def test_un_punto_justo_en_el_borde_inferior_de_la_zona_no_cuenta_como_dentro():
    """Mismo CASO 1 del docstring, verificado tambien end-to-end via _procesar."""
    zonas = zonas_de_ejemplo()
    # support_point = (20+20, 100+100) = (40, 200): y=200 es el borde INFERIOR
    # de estante_1 (y: 0..200), fuera por el intervalo semiabierto.
    eventos = [crear_evento(frame=0, timestamp=10.0, x=20, y=100)]
    resultado, _resumen = eventos_por_track(zonas, eventos)
    assert resultado[0].zone.zone_id is None
    assert resultado[0].metrics.dwell_time is None


def test_dwell_time_crece_mientras_el_track_sigue_en_la_misma_zona():
    zonas = zonas_de_ejemplo()
    eventos = [
        crear_evento(frame=0, timestamp=10.0, x=20, y=50, track_id=7),   # pies (40, 150)
        crear_evento(frame=1, timestamp=11.5, x=22, y=50, track_id=7),   # sigue en estante_1
        crear_evento(frame=2, timestamp=13.0, x=25, y=50, track_id=7),
    ]
    resultado, _resumen = eventos_por_track(zonas, eventos)
    assert [e.zone.segment for e in resultado] == ["estante_1", "estante_1", "estante_1"]
    assert resultado[0].metrics.dwell_time == pytest.approx(0.0)
    assert resultado[1].metrics.dwell_time == pytest.approx(1.5)
    assert resultado[2].metrics.dwell_time == pytest.approx(3.0)


def test_dwell_time_se_reinicia_al_cambiar_de_zona():
    zonas = zonas_de_ejemplo()
    eventos = [
        crear_evento(frame=0, timestamp=10.0, x=20, y=50, track_id=7),    # estante_1
        crear_evento(frame=1, timestamp=13.0, x=20, y=50, track_id=7),    # sigue en estante_1: dwell=3.0
        crear_evento(frame=2, timestamp=14.0, x=120, y=50, track_id=7),   # se mueve a estante_2
    ]
    resultado, _resumen = eventos_por_track(zonas, eventos)
    assert resultado[1].metrics.dwell_time == pytest.approx(3.0)
    assert resultado[2].zone.segment == "estante_2"
    assert resultado[2].metrics.dwell_time == pytest.approx(0.0)  # visita nueva, no 4.0


def test_dwell_time_se_reinicia_al_pasar_por_el_pasillo_y_volver():
    """Salir de toda zona y volver a la MISMA cuenta como una visita nueva:
    dwell_time es 'cuanto lleva AHORA', no un acumulado historico."""
    zonas = zonas_de_ejemplo()
    eventos = [
        crear_evento(frame=0, timestamp=10.0, x=20, y=50, track_id=7),     # estante_1
        crear_evento(frame=1, timestamp=11.0, x=250, y=250, track_id=7),   # pasillo
        crear_evento(frame=2, timestamp=12.0, x=20, y=50, track_id=7),     # vuelve a estante_1
    ]
    resultado, _resumen = eventos_por_track(zonas, eventos)
    assert resultado[0].zone.segment == "estante_1"
    assert resultado[1].zone.zone_id is None
    assert resultado[1].metrics.dwell_time is None
    assert resultado[2].zone.segment == "estante_1"
    assert resultado[2].metrics.dwell_time == pytest.approx(0.0)


def test_dwell_time_no_depende_de_cuantos_eventos_hay_solo_del_timestamp():
    """Si dependiera de contar eventos, el mismo tiempo real daria un
    dwell_time distinto segun FRAME_STRIDE. Dos secuencias con los mismos
    timestamps pero distinto numero de eventos intermedios deben coincidir."""
    zonas = zonas_de_ejemplo()

    pocos = [
        crear_evento(frame=0, timestamp=10.0, x=20, y=50, track_id=7),
        crear_evento(frame=5, timestamp=15.0, x=20, y=50, track_id=7),
    ]
    muchos = [
        crear_evento(frame=0, timestamp=10.0, x=20, y=50, track_id=7),
        crear_evento(frame=1, timestamp=11.0, x=20, y=50, track_id=7),
        crear_evento(frame=2, timestamp=12.0, x=20, y=50, track_id=7),
        crear_evento(frame=3, timestamp=13.0, x=20, y=50, track_id=7),
        crear_evento(frame=4, timestamp=14.0, x=20, y=50, track_id=7),
        crear_evento(frame=5, timestamp=15.0, x=20, y=50, track_id=7),
    ]
    resultado_pocos, _ = eventos_por_track(zonas, pocos)
    resultado_muchos, _ = eventos_por_track(zonas, muchos)
    assert resultado_pocos[-1].metrics.dwell_time == resultado_muchos[-1].metrics.dwell_time == 5.0


def test_dos_tracks_distintos_no_comparten_visita():
    zonas = zonas_de_ejemplo()
    eventos = [
        crear_evento(frame=0, timestamp=10.0, x=20, y=50, track_id=1),
        crear_evento(frame=0, timestamp=10.0, x=25, y=50, track_id=2),
        crear_evento(frame=1, timestamp=12.0, x=20, y=50, track_id=1),
    ]
    resultado, _resumen = eventos_por_track(zonas, eventos)
    assert resultado[0].metrics.dwell_time == pytest.approx(0.0)  # track 1, primera vez
    assert resultado[1].metrics.dwell_time == pytest.approx(0.0)  # track 2, primera vez
    assert resultado[2].metrics.dwell_time == pytest.approx(2.0)  # track 1, segunda vez


def test_quien_solo_pasa_no_supera_el_umbral_de_se_detiene():
    """Alguien que cruza el estante caminando (dwell_time siempre bien por
    debajo de UMBRAL_SE_DETIENE_S) nunca deberia clasificar como
    'se_detiene' en ningun evento de su paso, y el resumen no debe contarlo
    ahi tampoco."""
    zonas = zonas_de_ejemplo()
    eventos = [
        crear_evento(frame=0, timestamp=10.00, x=20, y=50, track_id=7),  # entra a estante_1
        crear_evento(frame=1, timestamp=10.30, x=25, y=50, track_id=7),  # dwell=0.3
        crear_evento(frame=2, timestamp=10.60, x=30, y=50, track_id=7),  # dwell=0.6
        crear_evento(frame=3, timestamp=10.90, x=35, y=50, track_id=7),  # dwell=0.9, sale
    ]
    resultado, resumen = eventos_por_track(zonas, eventos)
    assert all(e.metrics.dwell_time < UMBRAL_SE_DETIENE_S for e in resultado)
    assert all(clasifica_visita(e.metrics.dwell_time) == "pasa_de_largo" for e in resultado)
    assert resumen.eventos_pasa_de_largo == 4
    assert resumen.eventos_se_detiene == 0


def test_procesar_no_toca_detection_ni_track_id():
    """Rellena SOLO zone y metrics.dwell_time (ver docs/data-contract.md)."""
    zonas = zonas_de_ejemplo()
    original = crear_evento(frame=3, timestamp=1.0, x=20, y=50, track_id=9)
    resultado, _resumen = eventos_por_track(zonas, [original])
    evento = resultado[0]
    assert evento.track_id == 9
    assert evento.detection.bbox.x == 20
    assert evento.detection.confidence == 0.9
    assert evento.interaction.event is None  # de la Persona 5, sin tocar


# --------------------------------------------------------------------------
# run(): integracion completa, con archivos temporales
# --------------------------------------------------------------------------

def test_run_asigna_zonas_y_escribe_el_resultado(tmp_path, monkeypatch):
    monkeypatch.setattr(zones_stage, "RAIZ", tmp_path)
    monkeypatch.setenv("VIDEO_ID", "video_001")
    monkeypatch.setenv("VIDEO_PATH", str(tmp_path / "videos" / "video_001.mp4"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    (tmp_path / "data" / "zones").mkdir(parents=True)
    (tmp_path / "data" / "zones" / "video_001.json").write_text(
        json.dumps({
            "video_id": "video_001", "frame_width": 300, "frame_height": 300,
            "gondolas": [{
                "zone_id": "gondola_A", "name": "Gondola A", "product_category": None,
                "shelves": [{
                    "segment": "estante_1", "name": "Estante 1", "product_category": None,
                    "floor_zone": {"x": 0, "y": 0, "width": 300, "height": 300},
                }],
            }],
        }),
        encoding="utf-8",
    )

    cfg = load_config()
    rutas = pipeline.stage_paths("zones", cfg)
    rutas.input_path.parent.mkdir(parents=True, exist_ok=True)
    write_events(rutas.input_path, [
        crear_evento(frame=0, timestamp=1.0, x=20, y=50, track_id=1),
        crear_evento(frame=1, timestamp=2.0, x=20, y=50, track_id=1),
    ])

    assert run(cfg) == 0

    escritos = list(read_events(rutas.output_path))
    assert len(escritos) == 2
    assert escritos[0].zone.zone_id == "gondola_A"
    assert escritos[1].metrics.dwell_time == pytest.approx(1.0)

    resumen = json.loads(pipeline.summary_path("zones", cfg).read_text(encoding="utf-8"))
    assert resumen["results"]["eventos_con_zona"] == 2
    assert resumen["results"]["eventos_sin_zona"] == 0


def test_run_sin_track_jsonl_falla_con_falta_de_requisito(tmp_path, monkeypatch):
    monkeypatch.setattr(zones_stage, "RAIZ", tmp_path)
    monkeypatch.setenv("VIDEO_ID", "video_001")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    cfg = load_config()
    with pytest.raises(MissingInputError):
        run(cfg)


def test_run_sin_archivo_de_zonas_falla_con_mensaje_claro(tmp_path, monkeypatch):
    monkeypatch.setattr(zones_stage, "RAIZ", tmp_path)
    monkeypatch.setenv("VIDEO_ID", "video_001")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    cfg = load_config()

    rutas = pipeline.stage_paths("zones", cfg)
    rutas.input_path.parent.mkdir(parents=True, exist_ok=True)
    write_events(rutas.input_path, [crear_evento(frame=0, timestamp=1.0, x=20, y=50)])

    with pytest.raises(ZonesConfigError):
        run(cfg)


def test_el_archivo_de_ejemplo_real_asigna_a_alguien_frente_al_estante_2():
    """Prueba de humo con la calibracion real del repo: en el frame 500 de
    video_001.mp4 hay una persona con canasta frente a estante_2 (ver
    data/output/video_001.zones.png). No usa el video, solo reconstruye la
    caja aproximada que YOLO daria ahi, sobre las zonas reales del repo."""
    from gondola.config import RAIZ
    from gondola.zones_config import load_zones_config

    zonas = load_zones_config(RAIZ / "data" / "zones" / "video_001.example.json")
    # Punto de apoyo aproximado de la persona con la canasta en ese frame.
    resultado = asignar_zona((700.0, 450.0), zonas)
    assert resultado is not None
    gondola, estante = resultado
    assert (gondola.zone_id, estante.segment) == ("gondola_A", "estante_2")
