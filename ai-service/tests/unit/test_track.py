"""Tests del seguimiento (gondola/stages/track.py).

Todo lo que se prueba aqui es aritmetica pura sobre eventos construidos a
mano: no hace falta YOLO, ni OpenCV, ni un video. Corren con solo
`pip install -r requirements-dev.txt`, igual que test_detect.py.
"""

import json

import pytest

from gondola import pipeline
from gondola.config import load_config
from gondola.contract import BBox, Detection, Event
from gondola.errors import MissingInputError
from gondola.jsonl import read_events, write_events
from gondola.stages.track import (
    IOU_MINIMO_PARA_EMPAREJAR,
    MAX_AGE_S,
    Resumen,
    Track,
    actualizar_track,
    asignar_track_ids,
    centro,
    coherencia_de_movimiento,
    color_desde_id,
    contar_cruces_sospechosos,
    emparejar,
    iou,
    predecir_bbox,
    run,
)


def crear_evento(frame, timestamp, x, y, w=40.0, h=100.0, conf=0.9,
                 video_id="video_001") -> Event:
    return Event(
        video_id=video_id,
        frame=frame,
        timestamp=timestamp,
        detection=Detection(confidence=conf, bbox=BBox(x=x, y=y, width=w, height=h)),
    )


# --------------------------------------------------------------------------
# iou / centro / prediccion de movimiento
# --------------------------------------------------------------------------

def test_iou_de_cajas_identicas_es_uno():
    caja = BBox(x=10, y=10, width=50, height=100)
    assert iou(caja, caja) == 1.0


def test_iou_de_cajas_que_no_se_tocan_es_cero():
    a = BBox(x=0, y=0, width=10, height=10)
    b = BBox(x=100, y=100, width=10, height=10)
    assert iou(a, b) == 0.0


def test_iou_de_solape_parcial():
    a = BBox(x=0, y=0, width=10, height=10)   # area 100
    b = BBox(x=5, y=0, width=10, height=10)   # solapan en un area de 50
    assert iou(a, b) == pytest.approx(50 / 150)


def test_centro_es_el_punto_medio_de_la_caja():
    assert centro(BBox(x=0, y=0, width=10, height=20)) == (5.0, 10.0)


def test_sin_velocidad_la_prediccion_no_mueve_la_caja():
    """Un track recien creado no asume movimiento sin haber visto una segunda posicion."""
    track = Track(bbox=BBox(x=10, y=10, width=50, height=100), timestamp=0.0)
    predicha = predecir_bbox(track, 1.0)
    assert (predicha.x, predicha.y) == (10.0, 10.0)


def test_con_velocidad_la_prediccion_extrapola():
    """A dt=0.5s con MAX_AGE_S=2.0, la velocidad ya se amortiguo un 25%
    (factor=1-0.5/2.0=0.75): 10 + (20*0.75)*0.5 = 17.5, no 20."""
    track = Track(bbox=BBox(x=10, y=10, width=50, height=100), timestamp=0.0,
                 velocity=(20.0, 0.0))
    predicha = predecir_bbox(track, 0.5)
    assert predicha.x == pytest.approx(17.5)


def test_la_prediccion_converge_a_la_ultima_posicion_con_el_tiempo():
    """Cuanto mas viejo el track, menos se aleja la prediccion de su ultima
    caja conocida -lo contrario de extrapolar sin limite. Justo al borde de
    MAX_AGE_S, la velocidad esta completamente amortiguada: la prediccion es
    la ultima posicion, tal cual."""
    track = Track(bbox=BBox(x=100, y=100, width=40, height=100), timestamp=0.0,
                 velocity=(50.0, 0.0))
    cerca = predecir_bbox(track, 0.1)
    lejos = predecir_bbox(track, MAX_AGE_S - 0.01)
    al_borde = predecir_bbox(track, MAX_AGE_S)

    assert cerca.x > 100.0            # recien perdido, casi sin amortiguar
    assert al_borde.x == pytest.approx(100.0)   # se congela en la ultima posicion
    assert 100.0 < lejos.x < cerca.x  # cuanto mas viejo, menos se aleja


def test_amortiguacion_recupera_una_persona_casi_quieta_tras_una_oclusion_larga():
    """Version compacta del caso real medido en video_003.mp4: alguien que
    apenas se movia (velocidad chica, estimada con solo dos frames, con algo
    de ruido) queda oculto 1.53s detras de otra persona que camina enfrente,
    y reaparece casi en el mismo sitio. Sin amortiguar, la extrapolacion
    lineal se habria alejado de donde en realidad seguia (ver docstring del
    modulo); amortiguada, la recupera."""
    eventos = [
        crear_evento(0, 0.000, x=970, y=100),
        crear_evento(1, 0.033, x=954, y=100),
        crear_evento(2, 0.067, x=952, y=100),
        # se pierde 1.53s -oculto detras de alguien que camina enfrente-
        crear_evento(3, 1.600, x=949, y=100),
    ]
    resumen = Resumen()
    ids = [e.track_id for e in asignar_track_ids(iter(eventos), resumen)]
    assert ids == [1, 1, 1, 1]
    assert resumen.tracks_creados == 1


def test_la_prediccion_no_cae_en_coordenadas_negativas():
    """BBox exige x, y >= 0 (contract.py); una prediccion hacia el borde no debe reventar."""
    track = Track(bbox=BBox(x=5, y=5, width=50, height=100), timestamp=0.0,
                 velocity=(-1000.0, -1000.0))
    predicha = predecir_bbox(track, 1.0)
    assert (predicha.x, predicha.y) == (0.0, 0.0)


def test_actualizar_track_calcula_la_velocidad_entre_dos_posiciones():
    track = Track(bbox=BBox(x=0, y=0, width=50, height=100), timestamp=0.0)
    actualizar_track(track, crear_evento(1, 1.0, x=20, y=0, w=50))  # mismo ancho: el
    # centro se mueve exactamente lo que se movio x
    assert track.velocity[0] == pytest.approx(20.0)
    assert track.timestamp == 1.0


def test_actualizar_track_con_el_mismo_timestamp_no_revienta():
    """dt=0 no debe dividir por cero: conserva la velocidad que ya tenia."""
    track = Track(bbox=BBox(x=0, y=0, width=50, height=100), timestamp=1.0, velocity=(5.0, 0.0))
    actualizar_track(track, crear_evento(1, 1.0, x=20, y=0))
    assert track.velocity == (5.0, 0.0)


# --------------------------------------------------------------------------
# emparejar: un frame a la vez
# --------------------------------------------------------------------------

def test_emparejar_prefiere_el_mayor_iou():
    tracks = {1: Track(bbox=BBox(x=0, y=0, width=50, height=100), timestamp=0.0)}
    cerca = crear_evento(1, 0.0, x=2, y=0)
    lejos = crear_evento(1, 0.0, x=500, y=500)
    emparejados, sin_emparejar = emparejar(tracks, [lejos, cerca])
    assert emparejados[1] is cerca
    assert sin_emparejar == [lejos]


def test_emparejar_no_fuerza_por_debajo_del_umbral():
    """Mejor un track nuevo que un emparejamiento dudoso (ver docstring del modulo)."""
    tracks = {1: Track(bbox=BBox(x=0, y=0, width=50, height=100), timestamp=0.0)}
    lejos = crear_evento(1, 0.0, x=1000, y=1000)
    emparejados, sin_emparejar = emparejar(tracks, [lejos])
    assert emparejados == {}
    assert sin_emparejar == [lejos]


def test_emparejar_no_repite_ni_track_ni_deteccion():
    """Dos tracks casi en el mismo sitio: cada uno se lleva UNA deteccion, no las dos."""
    tracks = {
        1: Track(bbox=BBox(x=0, y=0, width=50, height=100), timestamp=0.0),
        2: Track(bbox=BBox(x=3, y=0, width=50, height=100), timestamp=0.0),
    }
    e1 = crear_evento(1, 0.0, x=0, y=0)
    e2 = crear_evento(1, 0.0, x=3, y=0)
    emparejados, sin_emparejar = emparejar(tracks, [e1, e2])
    assert set(id(e) for e in emparejados.values()) == {id(e1), id(e2)}
    assert sin_emparejar == []


# --------------------------------------------------------------------------
# coherencia_de_movimiento: el empate que el IoU solo no puede resolver
# --------------------------------------------------------------------------

def test_coherencia_favorece_continuar_el_rumbo():
    track = Track(bbox=BBox(x=34, y=16, width=40, height=40), timestamp=0.04,
                 velocity=(400.0, 100.0))
    prediccion = predecir_bbox(track, 0.08)
    continua = crear_evento(2, 0.08, x=54, y=21, w=40, h=40)  # sigue el rumbo
    reversa = crear_evento(2, 0.08, x=46, y=19, w=40, h=40)   # implica dar la vuelta

    assert coherencia_de_movimiento(track, prediccion, continua) == pytest.approx(1.0, abs=1e-3)
    assert coherencia_de_movimiento(track, prediccion, reversa) == pytest.approx(0.0, abs=1e-3)


def test_coherencia_es_neutra_sin_rumbo_establecido():
    """Track recien creado (velocidad (0,0)): no hay direccion previa que
    comparar, asi que no se penaliza nada."""
    track = Track(bbox=BBox(x=0, y=0, width=40, height=40), timestamp=0.0)
    prediccion = predecir_bbox(track, 0.04)
    cualquiera = crear_evento(1, 0.04, x=200, y=200, w=40, h=40)
    assert coherencia_de_movimiento(track, prediccion, cualquiera) == 1.0


def test_coherencia_es_neutra_si_el_candidato_cae_sobre_la_prediccion():
    track = Track(bbox=BBox(x=0, y=0, width=40, height=40), timestamp=0.0, velocity=(400.0, 0.0))
    prediccion = predecir_bbox(track, 0.04)
    cx, cy = centro(prediccion)
    encima = crear_evento(1, 0.04, x=cx - 20, y=cy - 20, w=40, h=40)
    assert coherencia_de_movimiento(track, prediccion, encima) == 1.0


def test_sin_coherencia_el_empate_simetrico_depende_del_orden_de_llegada(monkeypatch):
    """Expone el problema (no lo esquiva): forzando la logica VIEJA -coherencia
    siempre neutra, emparejar solo por IoU-, el resultado de un cruce con
    velocidades simetricas cambia segun el orden en que llegan las cajas del
    frame. La mitad de las veces es un ID switch, por pura casualidad de cual
    caja escribio YOLO primero. Este test pasa HOY (asi de real es el bug) y
    seguiria pasando aunque se borrara la coherencia: es la prueba de que el
    problema existia antes del arreglo."""
    import gondola.stages.track as track_mod

    monkeypatch.setattr(track_mod, "coherencia_de_movimiento", lambda *_a, **_k: 1.0)

    track_a = Track(bbox=BBox(x=34, y=16, width=40, height=40), timestamp=0.04,
                    velocity=(400.0, 100.0))
    track_b = Track(bbox=BBox(x=66, y=24, width=40, height=40), timestamp=0.04,
                    velocity=(-400.0, -100.0))
    det_a_real = crear_evento(2, 0.08, x=54, y=21, w=40, h=40)  # continua el rumbo de A
    det_b_real = crear_evento(2, 0.08, x=46, y=19, w=40, h=40)  # continua el rumbo de B

    tracks = {1: track_a, 2: track_b}
    en_un_orden, _ = track_mod.emparejar(tracks, [det_a_real, det_b_real])
    en_el_otro, _ = track_mod.emparejar(tracks, [det_b_real, det_a_real])

    assert en_un_orden[1] is det_a_real and en_un_orden[2] is det_b_real  # este orden acierta...
    assert en_el_otro[1] is det_b_real and en_el_otro[2] is det_a_real    # ...el otro CAMBIA el resultado


def test_dos_personas_con_velocidades_simetricas_el_iou_solo_empata():
    """El mismo cruce del test anterior, pero con la logica ACTUAL (coherencia
    incluida): las predicciones de A y B coinciden EXACTO -el empate de IoU es
    real, no redondeo-, y aun asi el resultado ya NO depende del orden: la
    direccion distingue lo que el IoU no puede.

    Los bbox de partida se calculan hacia atras desde el punto de cruce
    (70, 40) usando el desplazamiento YA amortiguado (velocidad * dt * factor),
    no el crudo: con la velocidad amortiguandose con el tiempo, ese es el
    desplazamiento que `predecir_bbox` de verdad aplica."""
    dt = 0.04
    factor = max(0.0, 1.0 - dt / MAX_AGE_S)
    vx, vy = 400.0, 100.0
    track_a = Track(bbox=BBox(x=70 - vx * dt * factor - 20, y=40 - vy * dt * factor - 20,
                              width=40, height=40),
                    timestamp=0.04, velocity=(vx, vy))
    track_b = Track(bbox=BBox(x=70 + vx * dt * factor - 20, y=40 + vy * dt * factor - 20,
                              width=40, height=40),
                    timestamp=0.04, velocity=(-vx, -vy))

    pred_a = predecir_bbox(track_a, 0.08)
    pred_b = predecir_bbox(track_b, 0.08)
    assert centro(pred_a) == pytest.approx(centro(pred_b))  # el empate de verdad

    det_a_real = crear_evento(2, 0.08, x=54, y=21, w=40, h=40)  # continua el rumbo de A
    det_b_real = crear_evento(2, 0.08, x=46, y=19, w=40, h=40)  # continua el rumbo de B
    assert iou(pred_a, det_a_real.detection.bbox) == iou(pred_a, det_b_real.detection.bbox)

    tracks = {1: track_a, 2: track_b}
    for orden in ([det_a_real, det_b_real], [det_b_real, det_a_real]):
        emparejados, _ = emparejar(tracks, orden)
        assert emparejados[1] is det_a_real  # A se queda con SU continuacion...
        assert emparejados[2] is det_b_real  # ...B con la suya, sin importar el orden


# --------------------------------------------------------------------------
# asignar_track_ids: los tres problemas acordados en la Fase 1
# --------------------------------------------------------------------------

def test_una_persona_quieta_conserva_su_track_id():
    eventos = [crear_evento(f, f * 0.04, x=100, y=100) for f in range(5)]
    resumen = Resumen()
    ids = [e.track_id for e in asignar_track_ids(iter(eventos), resumen)]
    assert ids == [1, 1, 1, 1, 1]
    assert resumen.tracks_creados == 1


def test_dos_personas_que_se_cruzan_no_intercambian_id():
    """Problema 1 (oclusion). A camina a velocidad constante hacia la derecha,
    B hacia la izquierda; en el frame 3 sus cajas se solapan fuertemente. La
    prediccion de movimiento (no la ultima posicion cruda) es lo que permite
    distinguir cual caja es cual incluso durante el solape."""
    posiciones_a = [0, 15, 30, 45, 60]     # camina a la derecha, velocidad constante
    posiciones_b = [100, 85, 70, 55, 40]   # camina a la izquierda, velocidad constante
    # en el frame 3 las cajas se solapan fuertemente (A=[45,85], B=[55,95])

    eventos = []
    for f, (xa, xb) in enumerate(zip(posiciones_a, posiciones_b)):
        eventos.append(crear_evento(f, f * 0.04, x=xa, y=0))
        eventos.append(crear_evento(f, f * 0.04, x=xb, y=0))

    resumen = Resumen()
    salida = list(asignar_track_ids(iter(eventos), resumen))

    id_a = salida[0].track_id   # el que arranco en x=0
    id_b = salida[1].track_id   # el que arranco en x=100
    assert id_a != id_b
    assert resumen.tracks_creados == 2  # nadie se confundio con un track nuevo

    por_frame_y_x = {(e.frame, round(e.detection.bbox.x)): e.track_id for e in salida}
    assert por_frame_y_x[(4, 60)] == id_a   # A termino a la derecha con SU id
    assert por_frame_y_x[(4, 40)] == id_b   # B termino a la izquierda con SU id


def test_un_hueco_corto_conserva_el_track_id():
    """Problema 2: la deteccion del frame 1 se 'perdio' (confianza baja), pero
    el tiempo real transcurrido sigue dentro de MAX_AGE_S."""
    eventos = [
        crear_evento(0, 0.0, x=100, y=100),
        crear_evento(2, MAX_AGE_S - 0.1, x=100, y=100),
    ]
    ids = [e.track_id for e in asignar_track_ids(iter(eventos), Resumen())]
    assert ids == [1, 1]


def test_un_hueco_mas_largo_que_max_age_crea_un_track_nuevo():
    """Aunque el archivo pase de un frame al 'siguiente', si en tiempo real
    paso mas de MAX_AGE_S, la persona se da por perdida: es lo esperado, no un
    fallo. La deteccion de vuelta abre un track nuevo."""
    eventos = [
        crear_evento(0, 0.0, x=100, y=100),
        crear_evento(1, MAX_AGE_S + 0.1, x=100, y=100),
    ]
    resumen = Resumen()
    ids = [e.track_id for e in asignar_track_ids(iter(eventos), resumen)]
    assert ids == [1, 2]
    assert resumen.tracks_creados == 2


def test_dos_personas_lejanas_nunca_comparten_id():
    eventos = [
        crear_evento(0, 0.00, x=0, y=0),
        crear_evento(0, 0.00, x=1000, y=1000),
        crear_evento(1, 0.04, x=5, y=0),
        crear_evento(1, 0.04, x=1005, y=1000),
    ]
    ids = [e.track_id for e in asignar_track_ids(iter(eventos), Resumen())]
    assert ids[0] == ids[2]
    assert ids[1] == ids[3]
    assert ids[0] != ids[1]


def test_el_formato_del_track_id_es_el_acordado():
    """Entero positivo, empieza en 1: lo que exige el contrato (contract.py)."""
    eventos = [crear_evento(0, 0.0, x=0, y=0), crear_evento(1, 0.04, x=1000, y=1000)]
    salida = list(asignar_track_ids(iter(eventos), Resumen()))
    for e in salida:
        assert isinstance(e.track_id, int)
        assert e.track_id >= 1
    assert salida[0].track_id == 1


def test_quien_reaparece_no_hereda_el_id_de_otra_persona():
    """A desaparece dos frames (dentro de MAX_AGE_S) mientras B sigue presente
    todo el tiempo; al volver, A debe recuperar SU id, nunca el de B, y B no
    debe cambiar de id en ningun momento."""
    eventos = [
        crear_evento(0, 0.00, x=0, y=0),      # A
        crear_evento(0, 0.00, x=500, y=0),    # B
        crear_evento(1, 0.04, x=500, y=0),    # solo B: A "desaparecio"
        crear_evento(2, 0.08, x=500, y=0),    # solo B otra vez
        crear_evento(3, 0.12, x=5, y=0),      # A reaparece cerca de donde estaba
        crear_evento(3, 0.12, x=500, y=0),    # B sigue
    ]
    resumen = Resumen()
    salida = list(asignar_track_ids(iter(eventos), resumen))

    id_a = salida[0].track_id
    id_b = salida[1].track_id
    assert id_a != id_b

    frame3 = {round(e.detection.bbox.x): e.track_id for e in salida if e.frame == 3}
    assert frame3[5] == id_a     # A recupero SU id, no uno nuevo ni el de B
    assert frame3[500] == id_b   # B nunca cambio de id
    assert resumen.tracks_creados == 2  # nadie de mas


def test_dos_detecciones_muy_solapadas_en_el_mismo_frame_reciben_ids_distintos():
    """DEBE pasar: aunque casi no se puedan distinguir, dos detecciones del
    MISMO frame nunca terminan con el mismo track_id. Fusionarlas en una sola
    persona seria peor que un ID switch: se perderia gente de las metricas."""
    e1 = crear_evento(0, 0.0, x=10, y=10)
    e2 = crear_evento(0, 0.0, x=12, y=10)  # solape casi total
    resumen = Resumen()
    salida = list(asignar_track_ids(iter([e1, e2]), resumen))
    assert salida[0].track_id != salida[1].track_id
    assert resumen.tracks_creados == 2


def test_bajo_oclusion_fuerte_no_se_fusionan_ni_aparece_un_tercer_id():
    """DEBE pasar: bajo oclusion casi total puede que se cruce la identidad
    (eso es un cruce sospechoso, se cuenta aparte), pero las dos personas
    JAMAS se convierten en una sola ni aparece una tercera de la nada."""
    eventos = [
        crear_evento(0, 0.00, x=0, y=0),
        crear_evento(0, 0.00, x=10, y=0),
        crear_evento(1, 0.04, x=5, y=0),
        crear_evento(1, 0.04, x=15, y=0),   # solape casi total con la anterior
    ]
    resumen = Resumen()
    salida = list(asignar_track_ids(iter(eventos), resumen))

    ids_iniciales = {salida[0].track_id, salida[1].track_id}
    ids_frame1 = [e.track_id for e in salida if e.frame == 1]
    assert len(set(ids_frame1)) == 2         # dos personas, dos ids -- nunca una
    assert set(ids_frame1) == ids_iniciales  # los MISMOS dos ids de siempre
    assert resumen.tracks_creados == 2
    assert resumen.id_switches_sospechosos >= 1  # la oclusion se detecto y se conto


def test_contar_cruces_sospechosos_ve_el_swap_valido_en_ambos_sentidos():
    """Prueba directa de la funcion, sin pasar por todo asignar_track_ids."""
    tracks = {
        1: Track(bbox=BBox(x=0, y=0, width=40, height=100), timestamp=0.0),
        2: Track(bbox=BBox(x=10, y=0, width=40, height=100), timestamp=0.0),
    }
    emparejados = {
        1: crear_evento(1, 0.04, x=5, y=0),
        2: crear_evento(1, 0.04, x=15, y=0),
    }
    assert contar_cruces_sospechosos(tracks, emparejados, 0.04) >= 1


def test_contar_cruces_sospechosos_no_ve_nada_cuando_estan_lejos():
    tracks = {
        1: Track(bbox=BBox(x=0, y=0, width=40, height=100), timestamp=0.0),
        2: Track(bbox=BBox(x=1000, y=0, width=40, height=100), timestamp=0.0),
    }
    emparejados = {
        1: crear_evento(1, 0.04, x=5, y=0),
        2: crear_evento(1, 0.04, x=1005, y=0),
    }
    assert contar_cruces_sospechosos(tracks, emparejados, 0.04) == 0


def test_color_desde_id_es_estable_y_distingue_ids_distintos():
    assert color_desde_id(7) == color_desde_id(7)   # estable: mismo id, mismo color
    assert color_desde_id(1) != color_desde_id(2)   # ids consecutivos, colores distintos


def test_track_no_toca_los_campos_de_otras_personas():
    """Lo mas importante de esta etapa: solo escribe track_id."""
    e = crear_evento(0, 0.0, x=10, y=10)
    e.zone.zone_id = "gondola_A"
    e.interaction.product_zone = "bebidas"
    e.metrics.dwell_time = 3.5

    salida = next(iter(asignar_track_ids(iter([e]), Resumen())))
    assert salida.zone.zone_id == "gondola_A"
    assert salida.interaction.product_zone == "bebidas"
    assert salida.metrics.dwell_time == 3.5
    assert salida.detection.confidence == 0.9
    assert salida.track_id == 1


def test_el_resumen_empieza_en_cero():
    r = Resumen()
    assert (r.eventos_procesados, r.tracks_creados, r.emparejamientos) == (0, 0, 0)


# --------------------------------------------------------------------------
# El resultado no puede depender de FRAME_STRIDE: solo del timestamp real.
# --------------------------------------------------------------------------

def test_el_resultado_no_depende_del_frame_stride():
    """Si MAX_AGE se contara en frames del archivo, la misma pausa real
    cambiaria de tamano segun el stride con el que corrio `detect`. Dos
    secuencias con los MISMOS timestamps pero numeros de frame distintos
    (una 'consecutiva', otra como si viniera de --stride 5) deben dar
    exactamente el mismo resultado."""
    consecutivos = [
        crear_evento(10, 0.40, x=100, y=100),
        crear_evento(11, 0.44, x=105, y=100),
        crear_evento(13, 0.52, x=115, y=100),  # un frame se perdio en el medio
    ]
    salteados = [
        crear_evento(50, 0.40, x=100, y=100),
        crear_evento(55, 0.44, x=105, y=100),
        crear_evento(65, 0.52, x=115, y=100),
    ]

    ids_consecutivos = [e.track_id for e in asignar_track_ids(iter(consecutivos), Resumen())]
    ids_salteados = [e.track_id for e in asignar_track_ids(iter(salteados), Resumen())]

    assert ids_consecutivos == [1, 1, 1]
    assert ids_salteados == [1, 1, 1]
    assert ids_consecutivos == ids_salteados


# --------------------------------------------------------------------------
# run(): lectura y escritura reales, en streaming
# --------------------------------------------------------------------------

def test_run_asigna_track_id_y_preserva_lo_demas(tmp_path):
    cfg = load_config(env={"VIDEO_ID": "video_001", "OUTPUT_DIR": str(tmp_path / "output")})
    rutas = pipeline.stage_paths("track", cfg)
    write_events(rutas.input_path, [
        crear_evento(0, 0.00, x=0, y=0),
        crear_evento(1, 0.04, x=5, y=0),
    ])

    assert run(cfg) == 0

    salida = list(read_events(rutas.output_path))
    assert [e.track_id for e in salida] == [1, 1]
    assert all(e.detection.confidence == 0.9 for e in salida)

    resumen = json.loads(pipeline.summary_path("track", cfg).read_text(encoding="utf-8"))
    assert resumen["stage"] == "track"
    assert resumen["results"]["tracks_creados"] == 1
    assert resumen["results"]["emparejamientos"] == 1


def test_run_sin_su_entrada_dice_que_corras_detect_antes(tmp_path):
    cfg = load_config(env={"VIDEO_ID": "video_001", "OUTPUT_DIR": str(tmp_path / "output")})
    with pytest.raises(MissingInputError) as error:
        run(cfg)
    assert "python -m gondola detect" in str(error.value)


# --------------------------------------------------------------------------
# Propagacion de dimensiones/fps hacia el resumen, para que verify pueda
# comprobar bbox_en_frame y timestamps tambien sobre la salida de track.
# --------------------------------------------------------------------------

def test_run_propaga_dimensiones_y_fps_del_resumen_de_detect(tmp_path):
    cfg = load_config(env={"VIDEO_ID": "video_001", "OUTPUT_DIR": str(tmp_path / "output"),
                           "RENDER_MODE": "none"})
    rutas = pipeline.stage_paths("track", cfg)
    write_events(rutas.input_path, [crear_evento(0, 0.0, x=0, y=0)])

    ruta_resumen_detect = pipeline.summary_path("detect", cfg)
    ruta_resumen_detect.write_text(
        json.dumps({"video": {"width": 640, "height": 480, "fps": 25.0}}), encoding="utf-8"
    )

    assert run(cfg) == 0
    resumen = json.loads(pipeline.summary_path("track", cfg).read_text(encoding="utf-8"))
    assert resumen["video"] == {"width": 640, "height": 480, "fps": 25.0}


def test_run_sin_resumen_de_detect_no_falla_y_deja_video_vacio(tmp_path):
    """No haber corrido detect con render (o no tener su resumen) no es un
    fallo: track simplemente no tiene ese dato para propagar."""
    cfg = load_config(env={"VIDEO_ID": "video_001", "OUTPUT_DIR": str(tmp_path / "output"),
                           "RENDER_MODE": "none"})
    rutas = pipeline.stage_paths("track", cfg)
    write_events(rutas.input_path, [crear_evento(0, 0.0, x=0, y=0)])

    assert run(cfg) == 0
    resumen = json.loads(pipeline.summary_path("track", cfg).read_text(encoding="utf-8"))
    assert resumen["video"] == {}


# --------------------------------------------------------------------------
# El video propio de track (--render), reutilizando gondola/video/render.py
# --------------------------------------------------------------------------

def test_run_con_video_ausente_no_falla_y_avisa(tmp_path, capsys):
    """Pedido explicito: si el video no existe, el .jsonl se escribe igual y
    se avisa; nunca se rompe la corrida por no poder dibujar."""
    cfg = load_config(env={
        "VIDEO_ID": "video_001",
        "OUTPUT_DIR": str(tmp_path / "output"),
        "VIDEO_PATH": str(tmp_path / "videos" / "no_existe.mp4"),
        "RENDER_MODE": "privacy",
    })
    rutas = pipeline.stage_paths("track", cfg)
    write_events(rutas.input_path, [crear_evento(0, 0.0, x=0, y=0)])

    assert run(cfg) == 0
    salida = capsys.readouterr().out
    assert "no encuentro el video" in salida.lower()
    assert list(read_events(rutas.output_path))[0].track_id == 1


def test_run_con_video_real_genera_un_video_anotado(tmp_path):
    """Con un video real disponible, track debe producir su propio
    video.track.<modo>.mp4, con un frame por cada frame del video original."""
    pytest.importorskip("cv2")
    import cv2
    import numpy as np

    video_path = tmp_path / "videos" / "clip.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter.fourcc(*"mp4v"), 25.0, (100, 100))
    for _ in range(3):
        writer.write(np.zeros((100, 100, 3), dtype=np.uint8))
    writer.release()

    cfg = load_config(env={
        "VIDEO_ID": "video_001",
        "OUTPUT_DIR": str(tmp_path / "output"),
        "VIDEO_PATH": str(video_path),
        "RENDER_MODE": "privacy",
    })
    rutas = pipeline.stage_paths("track", cfg)
    write_events(rutas.input_path, [
        crear_evento(0, 0.00, x=10, y=10),
        crear_evento(2, 0.08, x=15, y=10),  # el frame 1 no tiene a nadie
    ])

    assert run(cfg) == 0

    video_salida = pipeline.render_path("track", cfg, "privacy")
    assert video_salida.exists()
    assert video_salida.stat().st_size > 0

    # el .jsonl sigue completo: el render no se comio ningun evento
    salida = list(read_events(rutas.output_path))
    assert [e.frame for e in salida] == [0, 2]
    assert all(e.track_id is not None for e in salida)
