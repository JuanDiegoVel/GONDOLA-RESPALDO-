"""Tests de la deteccion de interacciones (gondola/stages/interact.py).

Todo lo de aqui corre con solo `pip install -r requirements-dev.txt`: la etapa
es una transformacion pura de .jsonl y no necesita YOLO, ni OpenCV, ni el
video. Los tests que llaman a `_procesar` o a `run` escriben archivos
temporales, nada mas.

COMO SE CONSTRUYE UN ALCANCE SINTETICO
--------------------------------------
`secuencia()` fabrica los eventos que produciria `zones` para un track: una
linea base de cajas iguales, un tramo en el que la caja se ENSANCHA sin
crecer de alto (el gesto), y otra linea base. La caja se ensancha alrededor de
su centro a proposito, para que el punto de apoyo NO se mueva: asi cada test
habla de un solo filtro y no de dos a la vez.
"""

import json

import pytest

from gondola import pipeline
from gondola.config import load_config
from gondola.contract import BBox, Detection, Event, InteractionEvent
from gondola.errors import MissingInputError
from gondola.jsonl import read_events, write_events
from gondola.stages import zones as zones_stage
from gondola.stages.interact import (
    DURACION_MINIMA_S,
    MUESTRAS_MINIMAS_GESTO,
    REFRACTARIO_S,
    STRIDE_MAXIMO_FIABLE,
    UMBRAL_SE_DETIENE_S,
    Muestra,
    Resumen,
    _procesar,
    aspecto,
    aviso_de_stride,
    categorias_por_estante,
    etiqueta_de_alcance,
    muestras_por_gesto,
    pico_del_episodio,
    pies_quietos,
    run,
    toca_el_borde,
    velocidad_pies_alturas_por_s,
)
from gondola.zones_config import ZonesConfig

FPS = 30.0
ANCHO_FRAME = 1000
ALTO_FRAME = 1000
ANCHO_BASE = 100.0
ALTO_BASE = 200.0
CENTRO_X = 450.0

CATEGORIAS = {("gondola_A", "estante_1"): "cereales"}

# Rampa de 12 muestras (0,37 s a 30 fps) con un maximo claro en la sexta.
# Todas dan razon >= 1,18 sobre la linea base de 100 px: por encima del
# UMBRAL_RAZON_ASPECTO de 1,12, asi que el episodio entra entero.
ALCANCE = [120.0, 124.0, 128.0, 132.0, 136.0, 140.0, 136.0, 132.0, 128.0,
           124.0, 120.0, 118.0]

# El mismo gesto en 11 muestras (0,33 s), para poder poner dos seguidos sin
# que entre los dos ocupen mas de media ventana de mediana y se conviertan en
# su propia linea base. Ver "EL TECHO DEL METODO" en el docstring del modulo.
ALCANCE_CORTO = ALCANCE[:11]

# El frame en el que dwell_time cruza UMBRAL_SE_DETIENE_S cuando el dwell sube
# a razon de 1 s por segundo de video: es donde sale el APPROACH.
FRAME_DEL_APPROACH = int(UMBRAL_SE_DETIENE_S * FPS)


def rampa(n_muestras, base=120.0, pico=140.0) -> list[float]:
    """El mismo gesto estirado en `n_muestras`: la caja se ensancha de `base`
    a `pico` y vuelve.

    Cambia solo la DURACION, no la forma ni la amplitud. Es lo que hace falta
    para medir hasta que velocidad de gesto llega el metodo.
    """
    mitad = n_muestras // 2
    sube = [base + (pico - base) * i / mitad for i in range(mitad)]
    return sube + [pico] + sube[::-1][:n_muestras - mitad - 1]


def crear_evento(frame, ancho=ANCHO_BASE, centro_x=CENTRO_X, y=400.0,
                 alto=ALTO_BASE, track_id=1, zone_id="gondola_A",
                 segment="estante_1", dwell=1.0, x=None,
                 video_id="video_001") -> Event:
    """Un evento como los que produce `zones`: con track_id, zone y dwell_time.

    Por defecto la caja se ensancha alrededor de `centro_x`, de modo que
    `support_point` no se mueve aunque cambie el ancho.
    """
    evento = Event(
        video_id=video_id,
        frame=frame,
        timestamp=frame / FPS,
        track_id=track_id,
        detection=Detection(
            confidence=0.9,
            bbox=BBox(
                x=centro_x - ancho / 2 if x is None else x,
                y=y, width=ancho, height=alto,
            ),
        ),
    )
    evento.zone.zone_id = zone_id
    evento.zone.segment = segment
    evento.metrics.dwell_time = dwell
    return evento


def secuencia(anchos, frame0=0, **kw) -> list[Event]:
    """Convierte una lista de anchos en eventos consecutivos de un track."""
    return [crear_evento(frame=frame0 + i, ancho=a, **kw) for i, a in enumerate(anchos)]


def con_alcance(antes=20, despues=20, **kw) -> list[Event]:
    """Linea base, un alcance, y linea base otra vez."""
    return secuencia([ANCHO_BASE] * antes + ALCANCE + [ANCHO_BASE] * despues, **kw)


def procesar(tmp_path, eventos, categorias=None, ancho=ANCHO_FRAME, alto=ALTO_FRAME):
    """Corre `_procesar` sobre unos eventos y devuelve (salida, resumen)."""
    ruta = tmp_path / "entrada.jsonl"
    write_events(ruta, eventos)
    resumen = Resumen()
    salida = list(_procesar(
        ruta, CATEGORIAS if categorias is None else categorias, ancho, alto, resumen
    ))
    return salida, resumen


def interacciones(eventos) -> list[tuple[int, str]]:
    """(frame, tipo) de los eventos que salieron con interaccion."""
    return [
        (e.frame, e.interaction.event.value)
        for e in eventos
        if e.interaction.event is not None
    ]


def muestra_de(evento: Event) -> Muestra:
    """Envuelve un evento en la Muestra que usa la etapa por dentro."""
    caja = evento.detection.bbox
    return Muestra(
        evento=evento,
        track_id=evento.track_id,
        t=evento.timestamp,
        aspecto=aspecto(caja.width, caja.height),
        pies=caja.support_point,
        altura=caja.height,
        toca_borde=False,
        zona=(evento.zone.zone_id, evento.zone.segment),
        dwell=evento.metrics.dwell_time,
    )


# --------------------------------------------------------------------------
# aspecto y toca_el_borde
# --------------------------------------------------------------------------

def test_el_aspecto_no_depende_de_la_escala():
    """Una persona al doble de distancia da una caja mitad de grande con el
    mismo aspecto: es lo que hace que este rasgo sirva y el ancho solo no."""
    assert aspecto(100, 200) == pytest.approx(aspecto(50, 100))


def test_ensanchar_la_caja_sube_el_aspecto():
    assert aspecto(130, 200) > aspecto(100, 200)


@pytest.mark.parametrize(
    "x, y, ancho, alto",
    [
        (0.0, 400.0, 100.0, 200.0),      # pegada al borde izquierdo
        (400.0, 0.0, 100.0, 200.0),      # pegada al borde superior
        (900.0, 400.0, 100.0, 200.0),    # x + width == ANCHO_FRAME
        (400.0, 800.0, 100.0, 200.0),    # y + height == ALTO_FRAME
    ],
)
def test_una_caja_que_toca_cualquier_borde_se_detecta(x, y, ancho, alto):
    evento = crear_evento(frame=0, ancho=ancho, alto=alto, x=x, y=y)
    assert toca_el_borde(evento, ANCHO_FRAME, ALTO_FRAME) is True


def test_una_caja_entera_dentro_del_frame_no_toca_ningun_borde():
    evento = crear_evento(frame=0)
    assert toca_el_borde(evento, ANCHO_FRAME, ALTO_FRAME) is False


# --------------------------------------------------------------------------
# La convencion de emparejamiento
# --------------------------------------------------------------------------

def test_el_primer_alcance_de_una_visita_es_pick_up_y_el_segundo_put_back():
    """La CONVENCION del docstring de etiqueta_de_alcance, tal cual."""
    assert etiqueta_de_alcance(0) is InteractionEvent.PICK_UP
    assert etiqueta_de_alcance(1) is InteractionEvent.PUT_BACK


def test_del_tercer_alcance_en_adelante_se_alterna():
    assert etiqueta_de_alcance(2) is InteractionEvent.PICK_UP
    assert etiqueta_de_alcance(3) is InteractionEvent.PUT_BACK


# --------------------------------------------------------------------------
# product_zone: la categoria, con herencia
# --------------------------------------------------------------------------

def zonas_de_ejemplo(categoria_gondola=None, categoria_estante=None) -> ZonesConfig:
    return ZonesConfig.model_validate({
        "video_id": "video_001",
        "frame_width": ANCHO_FRAME,
        "frame_height": ALTO_FRAME,
        "gondolas": [{
            "zone_id": "gondola_A",
            "name": "Gondola A",
            "product_category": categoria_gondola,
            "shelves": [{
                "segment": "estante_1",
                "name": "Estante 1",
                "product_category": categoria_estante,
                "floor_zone": {"x": 0, "y": 0, "width": 900, "height": 900},
            }],
        }],
    })


def test_la_categoria_del_estante_gana_sobre_la_de_la_gondola():
    categorias = categorias_por_estante(zonas_de_ejemplo("bebidas", "cereales"))
    assert categorias[("gondola_A", "estante_1")] == "cereales"


def test_un_estante_sin_categoria_hereda_la_de_su_gondola():
    categorias = categorias_por_estante(zonas_de_ejemplo("bebidas", None))
    assert categorias[("gondola_A", "estante_1")] == "bebidas"


def test_sin_categoria_en_ningun_nivel_queda_en_null():
    categorias = categorias_por_estante(zonas_de_ejemplo(None, None))
    assert categorias[("gondola_A", "estante_1")] is None


# --------------------------------------------------------------------------
# Pies quietos, en alturas de caja por segundo
# --------------------------------------------------------------------------

def test_la_velocidad_de_los_pies_se_mide_en_alturas_no_en_pixeles():
    """Los mismos pixeles de desplazamiento en una caja el doble de alta (la
    misma persona, mas cerca de la camara) valen la mitad de alturas."""
    a = muestra_de(crear_evento(frame=0, centro_x=450.0, alto=200.0))
    b = muestra_de(crear_evento(frame=1, centro_x=460.0, alto=200.0))
    grande_a = muestra_de(crear_evento(frame=0, centro_x=450.0, alto=400.0))
    grande_b = muestra_de(crear_evento(frame=1, centro_x=460.0, alto=400.0))

    assert velocidad_pies_alturas_por_s(a, b) == pytest.approx(
        2 * velocidad_pies_alturas_por_s(grande_a, grande_b)
    )


def test_una_persona_parada_tiene_los_pies_quietos():
    muestras = [muestra_de(e) for e in secuencia([ANCHO_BASE] * 5)]
    assert pies_quietos(muestras) is True


def test_una_persona_caminando_no_tiene_los_pies_quietos():
    eventos = [crear_evento(frame=i, centro_x=450.0 + 10 * i) for i in range(5)]
    assert pies_quietos([muestra_de(e) for e in eventos]) is False


# --------------------------------------------------------------------------
# El pico del episodio
# --------------------------------------------------------------------------

def test_el_pico_es_la_muestra_de_maximo_aspecto():
    muestras = [muestra_de(e) for e in secuencia(ALCANCE)]
    assert pico_del_episodio(muestras).evento.frame == 5  # el ancho 140.0


def test_si_empatan_gana_el_frame_menor():
    """Desempate explicito para que la salida sea determinista."""
    muestras = [muestra_de(e) for e in secuencia([130.0, 130.0, 130.0])]
    assert pico_del_episodio(muestras).evento.frame == 0


# --------------------------------------------------------------------------
# El aviso de FRAME_STRIDE
# --------------------------------------------------------------------------

@pytest.mark.parametrize("stride", [1, 2, STRIDE_MAXIMO_FIABLE])
def test_con_stride_fiable_no_hay_aviso(stride):
    assert aviso_de_stride(stride, FPS) is None


def test_con_stride_alto_el_aviso_dice_cuantas_muestras_quedan():
    aviso = aviso_de_stride(5, FPS)
    assert aviso is not None
    assert "1.8" in aviso                       # 0,3 s * 30 fps / 5
    assert str(MUESTRAS_MINIMAS_GESTO) in aviso
    assert "no son fiables" in aviso.lower()


def test_el_aviso_sin_fps_dice_que_esta_suponiendo_30():
    aviso = aviso_de_stride(5, None)
    assert aviso is not None
    assert "30 fps" in aviso


def test_las_muestras_por_gesto_bajan_al_subir_el_stride():
    assert muestras_por_gesto(FPS, 1) == pytest.approx(9.0)
    assert muestras_por_gesto(FPS, 5) == pytest.approx(1.8)


# --------------------------------------------------------------------------
# _procesar: un gesto produce UN evento, y el archivo sale entero y en orden
# --------------------------------------------------------------------------

def test_un_alcance_produce_un_solo_evento_en_el_pico(tmp_path):
    """La decision que afecta a la Persona 6: 40 frames marcados serian 39
    falsos positivos para el evaluador. Uno solo, en el frame del maximo.

    Ni cero ni tres: se comprueban las tres cuentas del resumen, no solo que
    haya un PICK_UP en la lista.
    """
    salida, resumen = procesar(tmp_path, con_alcance())
    assert interacciones(salida) == [(25, "PICK_UP")]  # 20 de base + 5 de rampa
    assert resumen.pick_up == 1
    assert resumen.put_back == 0
    assert resumen.approach == 0
    assert resumen.episodios_candidatos == 1


def test_el_archivo_conserva_todos_los_eventos_no_solo_los_que_interactuaron(tmp_path):
    """La Persona 6 necesita zone y dwell_time de todos los eventos."""
    eventos = con_alcance()
    salida, resumen = procesar(tmp_path, eventos)
    assert len(salida) == len(eventos)
    assert resumen.eventos_procesados == len(eventos)


def test_los_frames_no_retroceden_en_la_salida(tmp_path):
    """La ventana de latencia no puede reordenar nada: `verify` comprueba
    exactamente esto sobre el archivo resultante."""
    frames = [e.frame for e in procesar(tmp_path, con_alcance())[0]]
    assert frames == sorted(frames)


def test_con_varios_tracks_intercalados_la_salida_sigue_el_orden_de_entrada(tmp_path):
    """Dos personas a la vez: los eventos se intercalan frame a frame y tienen
    que salir en el mismo orden, aunque una de las dos este a mitad de gesto."""
    uno = con_alcance(track_id=1)
    dos = secuencia([ANCHO_BASE] * len(uno), track_id=2, centro_x=700.0)
    entrada = [e for par in zip(uno, dos) for e in par]  # 1,2,1,2,...

    salida, _resumen = procesar(tmp_path, entrada)

    assert [(e.frame, e.track_id) for e in salida] == [
        (e.frame, e.track_id) for e in entrada
    ]


def test_los_eventos_sin_interaccion_salen_en_null(tmp_path):
    salida, _resumen = procesar(tmp_path, con_alcance())
    sin_evento = [e for e in salida if e.interaction.event is None]
    assert len(sin_evento) == len(salida) - 1
    assert all(e.interaction.product_zone is None for e in sin_evento)


def test_nunca_hay_product_zone_sin_event(tmp_path):
    """Restriccion de la base de datos: una categoria sin evento no significa
    nada, porque toda persona esta siempre 'frente a' alguna categoria."""
    salida, _resumen = procesar(tmp_path, con_alcance())
    assert all(
        e.interaction.event is not None
        for e in salida
        if e.interaction.product_zone is not None
    )


def test_product_zone_lleva_la_categoria_del_estante_no_el_segmento(tmp_path):
    salida, _resumen = procesar(tmp_path, con_alcance())
    marcado = next(e for e in salida if e.interaction.event is not None)
    assert marcado.interaction.product_zone == "cereales"
    assert marcado.zone.segment == "estante_1"  # el segmento sigue en lo suyo


def test_sin_categoria_en_el_archivo_de_zonas_product_zone_queda_en_null(tmp_path):
    """El evento se emite igual: lo que falta es el dato, no la interaccion."""
    salida, _resumen = procesar(
        tmp_path, con_alcance(), categorias={("gondola_A", "estante_1"): None}
    )
    marcado = next(e for e in salida if e.interaction.event is not None)
    assert marcado.interaction.event is InteractionEvent.PICK_UP
    assert marcado.interaction.product_zone is None


def test_interact_no_toca_los_campos_de_las_otras_personas(tmp_path):
    """Lo mas importante de esta etapa: solo escribe interaction."""
    entrada = con_alcance()
    salida, _resumen = procesar(tmp_path, entrada)
    for original, resultado in zip(entrada, salida):
        assert resultado.track_id == original.track_id
        assert resultado.detection.bbox.width == original.detection.bbox.width
        assert resultado.detection.confidence == original.detection.confidence
        assert resultado.zone.zone_id == original.zone.zone_id
        assert resultado.zone.segment == original.zone.segment
        assert resultado.metrics.dwell_time == original.metrics.dwell_time


def test_una_caja_que_nunca_se_ensancha_no_produce_nada(tmp_path):
    """Alguien parado mirando el estante sin tocarlo: cero interacciones."""
    salida, resumen = procesar(tmp_path, secuencia([ANCHO_BASE] * 60))
    assert interacciones(salida) == []
    assert resumen.episodios_candidatos == 0


# --------------------------------------------------------------------------
# Los filtros: cada descarte, contado por su causa
# --------------------------------------------------------------------------

def test_un_episodio_demasiado_corto_se_descarta_por_duracion(tmp_path):
    """Dos muestras de gesto son 0,07 s a 30 fps: por debajo del minimo."""
    anchos = [ANCHO_BASE] * 20 + [140.0, 140.0] + [ANCHO_BASE] * 20
    salida, resumen = procesar(tmp_path, secuencia(anchos))
    assert interacciones(salida) == []
    assert resumen.episodios_candidatos == 1
    assert resumen.descartados_por_duracion == 1


def test_un_alcance_con_la_caja_en_el_borde_se_descarta_por_el_borde(tmp_path):
    """Ahi el ancho lo recorta la imagen, no el cuerpo."""
    salida, resumen = procesar(tmp_path, con_alcance(x=0.0))
    assert interacciones(salida) == []
    assert resumen.descartados_por_borde == 1


def test_un_alcance_mientras_la_persona_camina_se_descarta_por_los_pies(tmp_path):
    """Girarse mientras se camina ensancha la caja igual que estirar el brazo:
    el filtro de pies quietos es lo unico que separa los dos casos."""
    anchos = [ANCHO_BASE] * 20 + ALCANCE + [ANCHO_BASE] * 20
    eventos = [
        crear_evento(frame=i, ancho=a, centro_x=450.0 + 5.0 * i)
        for i, a in enumerate(anchos)
    ]
    salida, resumen = procesar(tmp_path, eventos)
    assert interacciones(salida) == []
    assert resumen.descartados_por_pies == 1


def test_un_alcance_fuera_de_toda_zona_se_descarta(tmp_path):
    """En el pasillo no hay estante del que tomar nada, ni categoria que
    poner en product_zone."""
    salida, resumen = procesar(
        tmp_path, con_alcance(zone_id=None, segment=None, dwell=None)
    )
    assert interacciones(salida) == []
    assert resumen.descartados_por_sin_zona == 1


def test_dos_alcances_muy_seguidos_solo_dejan_el_primero(tmp_path):
    """El periodo refractario: una caja temblorosa no dispara dos veces.

    Los dos picos quedan a 26 frames (0,87 s a 30 fps), por debajo de
    REFRACTARIO_S, asi que el segundo episodio se detecta pero no se emite.
    """
    anchos = ([ANCHO_BASE] * 20 + ALCANCE_CORTO + [ANCHO_BASE] * 15
              + ALCANCE_CORTO + [ANCHO_BASE] * 20)
    salida, resumen = procesar(tmp_path, secuencia(anchos))
    assert interacciones(salida) == [(25, "PICK_UP")]
    assert resumen.episodios_candidatos == 2
    assert resumen.descartados_por_refractario == 1


def test_una_caja_ensanchada_mucho_tiempo_se_vuelve_su_propia_linea_base(tmp_path):
    """EL TECHO DEL METODO, comprobado: alguien de perfil tres segundos no
    produce un episodio de tres segundos. La mediana centrada lo alcanza en
    cuanto el tramo ancho ocupa mas de media ventana, la razon vuelve a 1,0 y
    el episodio se cierra solo.

    Tiene dos lecturas y las dos importan: es lo que acota la memoria de la
    cola sin necesidad de un tope de duracion, y es tambien la razon de que un
    gesto lento (0,5-1,5 s, que es lo que dura tomar algo de verdad) sea
    invisible para esta etapa.
    """
    anchos = [ANCHO_BASE] * 20 + [140.0] * 90 + [ANCHO_BASE] * 20
    eventos = secuencia(anchos)
    salida, resumen = procesar(tmp_path, eventos)

    assert interacciones(salida) == []
    assert resumen.descartados_por_duracion == 1  # y no un episodio de 3 s
    assert len(salida) == len(eventos)  # la cola no se quedo con ninguno


def test_un_gesto_lento_no_se_detecta_y_no_deja_rastro_en_ningun_contador(tmp_path):
    """EL TECHO ESTRUCTURAL DEL METODO, con el mismo gesto a dos velocidades.

    `rampa()` estira el MISMO gesto -misma forma, misma amplitud- en mas
    muestras. Lo unico que cambia es cuanto dura, y eso decide si se ve o no:

        0,37 s  ->  PICK_UP
        0,50 s  ->  el episodio se forma pero sale truncado y lo descarta el
                    filtro de duracion
        0,63 s  ->  NO SE FORMA NINGUN EPISODIO

    La causa esta en el docstring del modulo: la mediana esta CENTRADA, asi
    que en cuanto el gesto ocupa mas de la mitad de la ventana (+-0,5 s) la
    mayoria de las muestras que la componen son del propio gesto, la mediana
    sube hasta el y la razon vuelve a 1,0.

    LO GRAVE NO ES QUE NO LO DETECTE, ES QUE NO SE ENTERA: a partir de 0,63 s
    el contador de episodios candidatos se queda en cero, asi que el gesto
    perdido no aparece en el embudo de descartes que imprime la etapa. Quien
    lea el resumen de una corrida no puede distinguir "no hubo gestos" de
    "los hubo y fueron demasiado lentos". Un gesto real de tomar un producto
    dura 0,5-1,5 s (fase 1), o sea que cae entero en esta zona ciega.

    Este test NO comprueba que el comportamiento sea deseable: fija donde
    esta el techo hoy, para que se note si alguien mueve la ventana o el
    umbral al recalibrar con groundtruth.
    """
    base = [ANCHO_BASE] * 25

    rapido = secuencia(base + rampa(12) + base)  # 0,37 s
    salida, resumen = procesar(tmp_path, rapido)
    assert [tipo for _frame, tipo in interacciones(salida)] == ["PICK_UP"]
    assert resumen.episodios_candidatos == 1

    lento = secuencia(base + rampa(20) + base)  # 0,63 s
    salida, resumen = procesar(tmp_path, lento)
    assert interacciones(salida) == []
    assert resumen.episodios_candidatos == 0  # invisible, no descartado


# --------------------------------------------------------------------------
# APPROACH: uno por visita, en el cruce del umbral de la Persona 4
# --------------------------------------------------------------------------

def visita_que_se_detiene(frame0=0, dwell0=0.0, n=90, **kw) -> list[Event]:
    """Una persona quieta en una zona, con el dwell_time subiendo como lo
    haria `zones`: cruza UMBRAL_SE_DETIENE_S por el camino."""
    return [
        crear_evento(frame=frame0 + i, dwell=dwell0 + i / FPS, **kw)
        for i in range(n)
    ]


def test_el_approach_sale_donde_el_dwell_time_cruza_el_umbral(tmp_path):
    salida, resumen = procesar(tmp_path, visita_que_se_detiene())
    marcados = interacciones(salida)
    assert marcados == [(int(UMBRAL_SE_DETIENE_S * FPS), "APPROACH")]
    assert resumen.approach == 1


def test_solo_hay_un_approach_por_visita_aunque_la_persona_siga_ahi(tmp_path):
    """dwell_time sigue creciendo 30 segundos: el APPROACH ya se emitio."""
    salida, _resumen = procesar(tmp_path, visita_que_se_detiene(n=300))
    assert len(interacciones(salida)) == 1


def test_quien_pasa_de_largo_no_genera_approach(tmp_path):
    """dwell_time nunca llega al umbral: no se detuvo, solo cruzo."""
    eventos = visita_que_se_detiene(n=int(UMBRAL_SE_DETIENE_S * FPS) - 5)
    salida, resumen = procesar(tmp_path, eventos)
    assert interacciones(salida) == []
    assert resumen.approach == 0


def test_volver_a_la_zona_es_una_visita_nueva_y_da_otro_approach(tmp_path):
    """`zones` reinicia dwell_time a 0,0 al empezar otra visita; un dwell que
    baja es justo la senal de que empezo otra."""
    primera = visita_que_se_detiene(frame0=0, n=70)
    segunda = visita_que_se_detiene(frame0=70, n=70)  # dwell vuelve a 0,0
    salida, resumen = procesar(tmp_path, primera + segunda)
    assert [tipo for _frame, tipo in interacciones(salida)] == ["APPROACH", "APPROACH"]
    assert resumen.approach == 2


def test_dos_tracks_no_comparten_ni_visita_ni_refractario(tmp_path):
    uno = visita_que_se_detiene(track_id=1)
    dos = visita_que_se_detiene(track_id=2, centro_x=700.0)
    salida, resumen = procesar(tmp_path, [e for par in zip(uno, dos) for e in par])
    assert resumen.approach == 2


def test_quien_solo_pasa_caminando_no_genera_ninguna_interaccion(tmp_path):
    """Alguien que cruza el pasillo sin parar: ni APPROACH ni alcances.

    Es el caso que mas veces se da en un video de tienda y el que mas caro
    saldria equivocar: cada falso positivo aqui inflaria la tasa de
    interaccion de una gondola por la que la gente solo pasa. Se comprueba la
    ausencia COMPLETA -las tres cuentas en cero y ni un episodio candidato-,
    no solo que no haya APPROACH.
    """
    eventos = [
        crear_evento(frame=i, centro_x=200.0 + 12.0 * i, dwell=i / FPS)
        for i in range(45)  # 1,5 s cruzando: el dwell no llega a 2,0
    ]
    salida, resumen = procesar(tmp_path, eventos)

    assert interacciones(salida) == []
    assert (resumen.approach, resumen.pick_up, resumen.put_back) == (0, 0, 0)
    assert resumen.episodios_candidatos == 0
    assert len(salida) == len(eventos)  # pero sus eventos salen todos


# --------------------------------------------------------------------------
# APPROACH y alcance a menos de un refractario: relojes SEPARADOS
# --------------------------------------------------------------------------

def visita_con_alcance_en(frame_alcance, n=140, **kw) -> list[Event]:
    """Una visita que se detiene (dwell subiendo) con un alcance en el frame
    indicado. Es la forma de la unica interaccion real de `video_001`."""
    anchos = [ANCHO_BASE] * n
    for i, ancho in enumerate(ALCANCE):
        anchos[frame_alcance + i] = ancho
    return [
        crear_evento(frame=i, ancho=ancho, dwell=i / FPS, **kw)
        for i, ancho in enumerate(anchos)
    ]


def test_un_alcance_a_menos_de_un_refractario_del_approach_ya_no_se_pierde(tmp_path):
    """El lider decidio separar el refractorio por tipo de evento: este test
    documenta el cambio (ver `EstadoTrack.t_ultimo_approach` /
    `t_ultimo_alcance` y el docstring de `_emitir` en interact.py).

    ANTES el refractorio era GLOBAL por track_id: contaba desde el ultimo
    evento emitido, sea del tipo que sea. Un APPROACH dejaba al track mudo
    durante REFRACTARIO_S, y si la persona alcanzaba el estante dentro de ese
    segundo -que es exactamente lo que hace alguien que se para frente a una
    gondola y toma algo- el alcance se descartaba.

    ESTO PASO DE VERDAD: en `video_001` era la razon de que salieran 0
    PICK_UP. El unico episodio que supero los filtros fisicos (track 9, pico
    en t=98,17 s, 0,300 s de duracion, pies quietos) cayo 0,83 s despues del
    APPROACH de su propio track y se perdia ahi -confirmado ademas viendo el
    frame del video: la persona esta con la canasta, brazo estirado al
    estante-. Con los relojes separados, ese mismo caso ahora SI emite el
    PICK_UP.
    """
    eventos = visita_con_alcance_en(FRAME_DEL_APPROACH + 5)  # pico 0,33 s despues
    salida, resumen = procesar(tmp_path, eventos)

    assert [tipo for _frame, tipo in interacciones(salida)] == ["APPROACH", "PICK_UP"]
    assert resumen.episodios_candidatos == 1
    assert resumen.descartados_por_refractario == 0  # ya no lo tapa el APPROACH
    assert resumen.pick_up == 1


def test_el_mismo_alcance_pasado_el_refractario_si_sale(tmp_path):
    """La contraparte del anterior, y la prueba de que lo que bloquea el
    alcance es el refractorio y no un defecto del gesto: el MISMO gesto, mas
    lejos del APPROACH, se emite sin tocar ningun umbral."""
    eventos = visita_con_alcance_en(FRAME_DEL_APPROACH + 40)  # pico 1,5 s despues
    salida, resumen = procesar(tmp_path, eventos)

    assert [tipo for _frame, tipo in interacciones(salida)] == ["APPROACH", "PICK_UP"]
    assert resumen.descartados_por_refractario == 0


# --------------------------------------------------------------------------
# La convencion de emparejamiento, ya dentro del pipeline
# --------------------------------------------------------------------------

def test_dentro_de_una_visita_el_segundo_alcance_sale_como_put_back(tmp_path):
    """Los dos gestos son identicos para la camara: lo que los separa es la
    CONVENCION, no una medicion (ver etiqueta_de_alcance)."""
    separacion = int(REFRACTARIO_S * FPS) + 20  # bien fuera del refractario
    anchos = ([ANCHO_BASE] * 20 + ALCANCE + [ANCHO_BASE] * separacion
              + ALCANCE + [ANCHO_BASE] * 20)
    salida, resumen = procesar(tmp_path, secuencia(anchos))
    assert [tipo for _frame, tipo in interacciones(salida)] == ["PICK_UP", "PUT_BACK"]
    assert resumen.pick_up == 1
    assert resumen.put_back == 1


def test_una_visita_nueva_vuelve_a_empezar_por_pick_up(tmp_path):
    """Si el emparejamiento no se reiniciara por visita, la segunda persona
    -o la segunda parada de la misma- heredaria el turno de la anterior."""
    separacion = int(REFRACTARIO_S * FPS) + 20
    anchos = [ANCHO_BASE] * 20 + ALCANCE + [ANCHO_BASE] * separacion
    primera = secuencia(anchos)
    # Misma zona, pero el dwell baja: `zones` empezo a contar otra visita.
    segunda = secuencia(anchos, frame0=len(anchos), dwell=0.5)
    salida, _resumen = procesar(tmp_path, primera + segunda)
    assert [tipo for _frame, tipo in interacciones(salida)] == ["PICK_UP", "PICK_UP"]


# --------------------------------------------------------------------------
# run(): integracion completa, con archivos temporales
# --------------------------------------------------------------------------

def preparar_entorno(tmp_path, monkeypatch, eventos):
    """Deja en tmp_path el archivo de zonas y el .zones.jsonl de entrada."""
    monkeypatch.setattr(zones_stage, "RAIZ", tmp_path)
    monkeypatch.setenv("VIDEO_ID", "video_001")
    monkeypatch.setenv("VIDEO_PATH", str(tmp_path / "videos" / "video_001.mp4"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    (tmp_path / "data" / "zones").mkdir(parents=True)
    (tmp_path / "data" / "zones" / "video_001.json").write_text(
        json.dumps(zonas_de_ejemplo(None, "cereales").model_dump()), encoding="utf-8"
    )

    cfg = load_config()
    rutas = pipeline.stage_paths("interact", cfg)
    rutas.input_path.parent.mkdir(parents=True, exist_ok=True)
    write_events(rutas.input_path, eventos)
    return cfg, rutas


def test_run_marca_el_alcance_y_escribe_el_resumen(tmp_path, monkeypatch, capsys):
    cfg, rutas = preparar_entorno(tmp_path, monkeypatch, con_alcance())

    assert run(cfg) == 0

    escritos = list(read_events(rutas.output_path))
    assert len(escritos) == 52
    marcados = [e for e in escritos if e.interaction.event is not None]
    assert len(marcados) == 1
    assert marcados[0].interaction.event is InteractionEvent.PICK_UP
    assert marcados[0].interaction.product_zone == "cereales"

    resumen = json.loads(pipeline.summary_path("interact", cfg).read_text(encoding="utf-8"))
    assert resumen["results"]["pick_up"] == 1
    assert resumen["results"]["episodios_candidatos"] == 1
    assert resumen["params"]["umbrales_validados_contra_groundtruth"] is False


def test_run_imprime_el_embudo_de_descartes(tmp_path, monkeypatch, capsys):
    """El lider necesita ver DONDE se pierde la senal, no solo el resultado."""
    preparar_entorno(tmp_path, monkeypatch, con_alcance(x=0.0))
    run(load_config())

    salida = capsys.readouterr().out
    assert "Episodios candidatos" in salida
    assert "tocaba el borde" in salida
    assert "pies no quietos" in salida
    assert "en refractario" in salida


def test_run_avisa_si_el_stride_es_alto(tmp_path, monkeypatch, capsys):
    """Avisa, pero no falla: correr con stride alto sigue sirviendo para
    probar la cadena entera rapido."""
    monkeypatch.setenv("FRAME_STRIDE", "5")
    preparar_entorno(tmp_path, monkeypatch, con_alcance())

    assert run(load_config()) == 0
    assert "no son fiables" in capsys.readouterr().out.lower()


def test_run_sin_zones_jsonl_falla_con_falta_de_requisito(tmp_path, monkeypatch):
    monkeypatch.setattr(zones_stage, "RAIZ", tmp_path)
    monkeypatch.setenv("VIDEO_ID", "video_001")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    with pytest.raises(MissingInputError):
        run(load_config())


def test_la_salida_de_run_pasa_el_verificador(tmp_path, monkeypatch):
    """El contrato completo sobre el archivo ya escrito: frames que no
    retroceden, campos de etapas posteriores en null y nada prohibido."""
    from gondola.verify.verifier import verificar

    cfg, rutas = preparar_entorno(tmp_path, monkeypatch, con_alcance())
    run(cfg)

    informe = verificar(rutas.output_path, cfg)
    fallidas = [r.nombre for r in informe.reglas if r.fallos]
    assert fallidas == []


def test_el_umbral_de_approach_es_el_de_la_persona_4():
    """No se inventa un segundo umbral que diga casi lo mismo: es literalmente
    la constante de zones.py."""
    assert UMBRAL_SE_DETIENE_S == zones_stage.UMBRAL_SE_DETIENE_S


def test_la_duracion_minima_sigue_siendo_la_de_la_fase_1():
    """Si alguien la mueve 'a ojo' para que salgan mas eventos, este test lo
    dice: la calibracion real espera al groundtruth (ver CLAUDE.md)."""
    assert DURACION_MINIMA_S == 0.3