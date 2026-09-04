"""Etapa 2: seguimiento entre frames. Responsable: Persona 3.

QUE HACE
--------
Lee las detecciones sueltas de la Persona 2 (una caja por persona y por frame,
sin relacion entre si) y les asigna un `track_id`: el numero que dice "esta
caja y aquella son la misma silueta". Ningun otro campo se toca.

COMO DECIDE QUE DOS CAJAS SON LA MISMA PERSONA (acordado en la Fase 1 de diseno)
---------------------------------------------------------------------------
Sin apariencia (prohibida por privacidad, ver docs/data-contract.md) lo unico
que queda es la geometria: donde estaba, hacia donde se movia, y que tanto se
solapa con lo que se ve ahora.

Cada track guarda su ultima caja, el instante en que se vio (`timestamp`) y su
velocidad (px/s, estimada con las dos ultimas posiciones). En cada frame nuevo:

    1. Se PREDICE donde deberia estar cada track activo, extrapolando su
       velocidad hasta el timestamp del frame actual. Emparejar contra la
       posicion predicha (no contra la ultima posicion cruda) es lo que
       distingue a dos personas que se cruzan: aunque sus cajas de este frame
       se solapen casi del todo, sus predicciones -que vienen de direcciones
       distintas- no.
    2. Se EMPAREJA cada prediccion con las cajas del frame. El candidato
       tiene que solapar por encima de IOU_MINIMO_PARA_EMPAREJAR para ser
       geometricamente plausible. Entre candidatos cuyo IoU ya es parecido
       (mismo escalon, NIVEL_IOU_PARA_DESEMPATE), se desempata por
       `coherencia_de_movimiento`, que favorece al que continua el rumbo que
       el track ya traia y penaliza al que implicaria una reversa de 180
       grados en un solo frame. Hace falta, y no es un detalle: en un cruce
       con direcciones opuestas, el IoU solo puede dar el MISMO valor a las
       dos cajas del otro lado (un empate real, no redondeo), y sin mas
       informacion el orden en que YOLO entrego las cajas termina decidiendo
       por accidente cual identidad se queda con cual. La direccion sí las
       distingue. Si ningun candidato llega al umbral, no se fuerza: es
       preferible abrir un track nuevo a intercambiar dos identidades en
       silencio (un ID switch no da ningun error, solo datos mal atribuidos).
    3. Un track que no se empareja NO muere de inmediato: sigue "flotando"
       sobre su prediccion hasta MAX_AGE_S segundos sin ver nada. Esto es lo
       que le permite sobrevivir a una persona que YOLO dejo de ver un par de
       frames (confianza inestable) sin creerla otra persona nueva. La
       prediccion durante ese tiempo no sigue extrapolando la velocidad tal
       cual: se AMORTIGUA (ver `predecir_bbox`), para que un track viejo
       converja hacia su ultima posicion conocida en vez de alejarse cada
       vez mas persiguiendo una velocidad que quiza se estimo con solo dos
       frames, algo de ruido incluido.

POR QUE MAX_AGE Y LA VELOCIDAD SE MIDEN EN SEGUNDOS Y NO EN FRAMES DEL ARCHIVO
-------------------------------------------------------------------------
El pipeline puede correr con FRAME_STRIDE > 1: diez lineas seguidas del
.jsonl pueden ser diez frames reales o cincuenta, segun con que stride corrio
`detect`. Contar EVENTOS o FRAMES para decidir "hace cuanto se vio" haria que
la misma tolerancia real cambiara de tamano sin que nadie lo note. Por eso
todo este modulo trabaja con `evento.timestamp` (segundos reales del video,
ya calculados por la Persona 2) y nunca con `evento.frame` para nada que
tenga que ver con tiempo transcurrido. `frame` solo se usa para saber que
detecciones pertenecen al mismo instante (agruparlas), no para medir tiempo.

SIN APARIENCIA, A PROPOSITO
----------------------------
`track_id` sale unicamente de esta geometria: posicion, velocidad y solape.
Nunca se deriva del contenido de la caja (color, textura, forma de la
silueta). De hecho esta etapa ni siquiera RECIBE pixeles para decidir el
seguimiento: lee un .jsonl con cajas y numeros. Eso no es una promesa de buen
comportamiento, es que la reidentificacion por apariencia es estructuralmente
imposible con esa entrada. El video solo se reabre, opcionalmente, para
DIBUJAR el resultado (ver mas abajo); nunca para decidir un track_id.

QUE NO RESUELVE (honesto, no una promesa)
-------------------------------------------
Sin apariencia, una oclusion CASI TOTAL entre dos personas que se mueven
parecido no siempre se puede desambiguar: la geometria sola no alcanza. Eso
produce ID switches de verdad. `contar_cruces_sospechosos` (mas abajo) cuenta
los momentos en que la geometria se quedo sin margen para decidir -es la unica
senal medible sin anotar video a mano-, pero es una cota, no una certeza.

Un caso distinto, medido y documentado a proposito: una oclusion que ademas
viene con un CAMBIO DE ESCALA grande (la persona reaparece mucho mas cerca o
mas lejos de la camara que cuando se perdio) puede no recuperar su id aunque
la posicion se prediga perfecto. Medido contra video_003.mp4: una persona
ocluida 1.53s reaparecio con una caja 62% mas alta (de 256px a 416px), porque
`predecir_bbox` nunca actualiza el ANCHO ni el ALTO, solo x,y. Con la caja de
antes y la de despues de tamanos tan distintos, el techo teorico de IoU -aun
con la posicion perfectamente centrada- fue 0.528, no 1.0. Subir mas el
umbral de emparejamiento no arregla esto (bajarlo tampoco: solo cambia a
quien mas se le acepta un emparejamiento dudoso). Lo unico que de verdad lo
resolveria es comparar el CONTENIDO de las dos cajas -re-identificacion por
apariencia-, y esa es justo la tecnica prohibida por la Ley 1581 y el
contrato de privacidad del proyecto (ver docs/data-contract.md). Se documenta
como limite conocido, no se persigue con mas parametros.

CUENTA DE CRUCES SOSPECHOSOS (medicion de calidad, sin necesitar groundtruth)
-------------------------------------------------------------------------
No hay anotaciones humanas todavia (eso es evaluacion contra `groundtruth`,
Fase futura y de todo el equipo). Mientras tanto, esta etapa se autodiagnostica:
en cada frame, si el emparejamiento elegido para dos tracks tambien habria sido
valido AL REVES (intercambiando a quien le toca cada caja), no hay forma de
saber cual de las dos versiones era la correcta. Eso se cuenta como un cruce
sospechoso. Es una cota superior de los ID switches reales, no un conteo
certificado: subestima si tres o mas personas se enredan a la vez, y no puede
saber si el cruce de verdad ocurrio o si la geometria solo se puso ambigua sin
que hubiera swap. Sirve para lo que pide el equipo: un numero que empeora o
mejora cuando alguien toca el algoritmo.

EL VIDEO PROPIO (--render), REUTILIZANDO gondola/video/
-------------------------------------------------------
`detect` ya sabe dibujar cajas en modo privacy/debug (`gondola/video/render.py`).
Esta etapa reutiliza exactamente ese `Renderer`, pasandole un color y una
etiqueta ("id N") por evento en vez de las de `detect` (verde, confianza). El
color sale de `color_desde_id`: una funcion determinista del numero, nunca
una tabla guardada ni nada derivado de la persona. Si el video de origen no
existe, no se falla: el .jsonl se escribe igual y se avisa que no se pudo
renderizar.

POR QUE LOS IMPORTS DE VIDEO ESTAN DENTRO DE LAS FUNCIONES
------------------------------------------------------------
A diferencia del resto de este modulo (aritmetica pura, cero dependencias
nuevas), reabrir el video para dibujar SI necesita OpenCV, que no esta en
requirements-dev.txt. Por eso, igual que en `detect.py`, esos imports viven
dentro de las funciones que los usan: los 7 companeros siguen corriendo
`pytest` sin instalarlo.
"""

from __future__ import annotations

import colorsys
import json
import math
import time
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from typing import Iterator

from gondola import pipeline
from gondola.config import Config
from gondola.contract import CONTRACT_VERSION, BBox, Event
from gondola.jsonl import read_events, write_events

IOU_MINIMO_PARA_EMPAREJAR = 0.3
"""Por debajo de este solape, dos cajas no se consideran la misma persona.
Mas vale abrir un track nuevo que forzar un emparejamiento dudoso: un track de
mas se ve y se puede filtrar despues, un ID switch no avisa a nadie.

Se probo (y se descarto) hacer que este umbral crezca con el tiempo que un
track lleva perdido -mas exigente cuanto mas viejo-, exactamente para que
subir MAX_AGE_S no fuera gratis. Con datos reales (video_003.mp4) esa version
resulto MENOS estable que esta (el rango de tracks creados entre distintos
MAX_AGE_S paso de 32-33 a 33-40, y de forma no monotona) y encima no
alcanzaba a recuperar el caso concreto que la motivo. La razon: el umbral
creciente y la ventana de espera compartian la misma referencia (MAX_AGE_S),
asi que tocar un numero movia dos comportamientos a la vez de formas dificiles
de predecir. Un sistema estable y explicable vale mas que uno afinado que ya
no se puede defender con claridad. La proteccion contra que un track viejo le
robe la caja a otra persona vive ahora solo en `predecir_bbox`
(amortiguacion de la velocidad): una prediccion que converge a la ultima
posicion conocida, en vez de seguir alejandose, ya es mucho menos probable
que se cruce por casualidad con alguien mas."""

MAX_AGE_S = 2.0
"""Segundos que un track puede pasar sin ninguna deteccion emparejada antes de
darse por perdido. EN SEGUNDOS, no en frames ni en eventos: ver el docstring
del modulo sobre por que (FRAME_STRIDE cambia cuantos eventos representan el
mismo tiempo real).

Medido contra video_003.mp4 (real): una oclusion de 1.53s -alguien tapado por
otra persona que camina enfrente- necesita al menos 1.7s de margen para
recuperar su id; 2.0s le sobra un poco sin llegar a ser un valor arbitrario.
Subirlo ya no es una apuesta ciega gracias a la amortiguacion de velocidad en
`predecir_bbox` (ver mas abajo): un track viejo no sigue extrapolando a la
velocidad -posiblemente ruidosa- con la que se le vio por ultima vez, sino
que converge hacia esa ultima posicion."""

NIVEL_IOU_PARA_DESEMPATE = 0.1
"""Ancho del escalon de IoU dentro del cual dos candidatos se consideran
'igual de buenos' y se desempatan por coherencia de movimiento
(ver `emparejar`). Una diferencia de IoU mayor que esto es una senal
geometrica demasiado fuerte como para que la direccion la contradiga."""

EVENTOS_ENTRE_AVISOS = 2000
"""Cada cuantos eventos se informa del progreso. Esta etapa es mucho mas
rapida que YOLO, pero un video largo igual conviene que avise que sigue viva."""

VELOCIDAD_MINIMA_PARA_COHERENCIA = 20.0
"""Px/s por debajo de esto, un track no tiene un rumbo confiable que comparar
(recien creado, o alguien casi quieto): la coherencia de movimiento queda
neutra (1.0) en vez de penalizar una direccion que no significa nada."""


@dataclass
class Track:
    """Lo que sabemos de una silueta seguida: donde estaba y hacia donde iba.

    Vive solo en memoria mientras corre `run()`; no es lo que se escribe en el
    .jsonl (eso es el `track_id`, un entero, dentro de cada `Event`).
    """

    bbox: BBox
    timestamp: float
    velocity: tuple[float, float] = (0.0, 0.0)  # (vx, vy) en pixeles/segundo


@dataclass
class Resumen:
    """Lo que se va contando durante la corrida y acaba en el JSON de resumen."""

    eventos_procesados: int = 0
    tracks_creados: int = 0
    emparejamientos: int = 0
    tracks_activos_al_cierre: int = 0
    id_switches_sospechosos: int = 0


# --------------------------------------------------------------------------
# Logica pura: se prueba sin archivos ni video
# --------------------------------------------------------------------------

def iou(a: BBox, b: BBox) -> float:
    """Interseccion sobre union de dos cajas. 0.0 si no se tocan."""
    ix1, iy1 = max(a.x, b.x), max(a.y, b.y)
    ix2 = min(a.x + a.width, b.x + b.width)
    iy2 = min(a.y + a.height, b.y + b.height)
    ancho_i, alto_i = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    interseccion = ancho_i * alto_i
    if interseccion <= 0.0:
        return 0.0
    union = a.width * a.height + b.width * b.height - interseccion
    return interseccion / union if union > 0 else 0.0


def centro(bbox: BBox) -> tuple[float, float]:
    """Centro geometrico de la caja, para medir movimiento.

    No es `bbox.support_point` (los pies): ese punto es para ubicar a la
    persona en el plano del piso (trabajo de la Persona 4), y usarlo aqui
    mezclaria dos ideas distintas. Para seguimiento, el centro de la caja
    basta.
    """
    return (bbox.x + bbox.width / 2, bbox.y + bbox.height / 2)


def predecir_bbox(track: Track, timestamp: float) -> BBox:
    """Donde deberia estar la caja del track AHORA, si siguio a la misma
    velocidad -amortiguada por cuanto lleva perdido.

    Con velocidad (0, 0) -si el track solo tiene una deteccion todavia- la
    prediccion es simplemente su ultima caja: no se asume movimiento sin
    evidencia de al menos dos posiciones.

    LA VELOCIDAD SE AMORTIGUA CON EL TIEMPO PERDIDO. Una velocidad estimada
    con dos observaciones (posiblemente ruidosas) y extrapolada varios
    segundos en linea recta es PEOR que no extrapolar nada -medido contra
    video_003.mp4: un track ocluido durante 1.53s, con una velocidad de solo
    -17.6 px/s estimada de dos frames cercanos, terminaba con una prediccion
    27px mas lejos de la persona real (que apenas se habia movido) que si se
    hubiera asumido quieta. La velocidad efectiva decae en linea recta hasta
    0 segun el track se acerca a MAX_AGE_S sin verse, de forma que la
    prediccion CONVERGE hacia su ultima posicion conocida en vez de seguir
    alejandose indefinidamente. Tiene sentido fisico: si no vi a alguien hace
    1.5 segundos, la mejor apuesta es "sigue cerca de donde estaba", no
    "siguio caminando en linea recta a la velocidad que le medi con dos
    frames".

    `x` e `y` se recortan en 0 porque `BBox` (contract.py) exige coordenadas
    no negativas: una prediccion hacia el borde de la imagen no debe romper
    la validacion.
    """
    dt = timestamp - track.timestamp
    factor_amortiguacion = max(0.0, 1.0 - dt / MAX_AGE_S)
    vx, vy = track.velocity
    vx_efectiva = vx * factor_amortiguacion
    vy_efectiva = vy * factor_amortiguacion
    return BBox(
        x=max(0.0, track.bbox.x + vx_efectiva * dt),
        y=max(0.0, track.bbox.y + vy_efectiva * dt),
        width=track.bbox.width,
        height=track.bbox.height,
    )


def actualizar_track(track: Track, evento: Event) -> None:
    """Registra una nueva deteccion emparejada: mueve el track y reestima su velocidad."""
    dt = evento.timestamp - track.timestamp
    if dt > 0:
        cx0, cy0 = centro(track.bbox)
        cx1, cy1 = centro(evento.detection.bbox)
        track.velocity = ((cx1 - cx0) / dt, (cy1 - cy0) / dt)
    track.bbox = evento.detection.bbox
    track.timestamp = evento.timestamp


def coherencia_de_movimiento(track: Track, prediccion: BBox, evento: Event) -> float:
    """Que tan bien encaja este candidato con el RUMBO que el track ya traia.

    No compara contra la ultima posicion cruda, sino contra el RESIDUAL: hacia
    donde queda el candidato respecto a lo que ya se predijo. Si ese residual
    apunta en la misma direccion que la velocidad establecida, el candidato
    continua el rumbo (cerca de 1.0). Si apunta en la direccion contraria,
    implicaria que la persona invirtio su movimiento en un solo frame (cerca
    de 0.0) -que es exactamente lo que pasa cuando dos identidades se cruzan
    y el emparejamiento las intercambia.

    Es neutro (1.0, no penaliza) cuando no hay rumbo confiable que comparar:
    un track recien creado (velocidad (0,0)), uno casi quieto (por debajo de
    VELOCIDAD_MINIMA_PARA_COHERENCIA), o un candidato que cae practicamente
    encima de la prediccion (residual ~0, nada que indique una direccion).
    """
    vx, vy = track.velocity
    magnitud_velocidad = math.hypot(vx, vy)
    if magnitud_velocidad < VELOCIDAD_MINIMA_PARA_COHERENCIA:
        return 1.0

    cx_p, cy_p = centro(prediccion)
    cx_e, cy_e = centro(evento.detection.bbox)
    residual = (cx_e - cx_p, cy_e - cy_p)
    magnitud_residual = math.hypot(*residual)
    if magnitud_residual < 1.0:
        return 1.0

    coseno = (vx * residual[0] + vy * residual[1]) / (magnitud_velocidad * magnitud_residual)
    return (1.0 + coseno) / 2.0


def emparejar(
    tracks: dict[int, Track], eventos: list[Event]
) -> tuple[dict[int, Event], list[Event]]:
    """Empareja los tracks activos con las detecciones de UN mismo frame.

    El candidato tiene que solapar lo suficiente con la prediccion
    (IOU_MINIMO_PARA_EMPAREJAR) para ser geometricamente plausible; ESO nunca
    lo relaja la coherencia de movimiento. La coherencia SOLO desempata entre
    candidatos cuyo IoU ya cae en el mismo escalon (NIVEL_IOU_PARA_DESEMPATE);
    nunca hace perder a un IoU muchisimo mejor. Esto no es un detalle: se
    intento primero multiplicar iou*coherencia directo, y en video real
    (video_003.mp4) eso hizo que un IoU excelente (0.99, una persona
    practicamente quieta) perdiera contra uno mediocre (0.32) solo porque la
    caja de YOLO tembló un poco en la altura de un frame a otro -la direccion
    de un residual minusculo es puro ruido, no una senal real de reversa, y
    fragmento un track que no tenia nada de ambiguo. Por escalones, la
    coherencia solo puede decidir entre candidatos que YA eran parecidos.

    Dentro de un mismo escalon, dos personas que se cruzan en direcciones
    opuestas pueden dar el MISMO IoU a las dos cajas del otro lado del cruce
    -un empate real, no un error de redondeo- y el orden en que YOLO entrego
    las cajas terminaria decidiendo, por accidente, cual identidad se queda
    con cual. La direccion sí distingue: la opcion correcta continua el rumbo
    de cada quien, la cruzada implica que alguien invirtio su movimiento de
    un frame a otro.

    Voraz: se ordenan todos los pares (track, deteccion) por (escalon,
    coherencia), descendente, y se van tomando mientras ninguno de los dos ya
    este usado. No es el optimo matematico (eso seria el algoritmo Hungaro),
    pero con la poca gente que hay a la vez frente a una gondola la diferencia
    es despreciable, y evita sumar una dependencia (scipy) solo para esto.

    Devuelve (emparejados: {track_id: evento}, sin_emparejar: detecciones que
    no encontraron track y necesitan uno nuevo).
    """
    timestamp = eventos[0].timestamp
    candidatos: list[tuple[tuple[float, float], int, int]] = []
    for track_id, track in tracks.items():
        prediccion = predecir_bbox(track, timestamp)
        for indice, evento in enumerate(eventos):
            valor = iou(prediccion, evento.detection.bbox)
            if valor >= IOU_MINIMO_PARA_EMPAREJAR:
                escalon = round(valor / NIVEL_IOU_PARA_DESEMPATE)
                coherencia = coherencia_de_movimiento(track, prediccion, evento)
                candidatos.append(((escalon, coherencia), track_id, indice))
    candidatos.sort(key=lambda c: c[0], reverse=True)

    usados_tracks: set[int] = set()
    usados_eventos: set[int] = set()
    emparejados: dict[int, Event] = {}
    for _valor, track_id, indice in candidatos:
        if track_id in usados_tracks or indice in usados_eventos:
            continue
        emparejados[track_id] = eventos[indice]
        usados_tracks.add(track_id)
        usados_eventos.add(indice)

    sin_emparejar = [e for i, e in enumerate(eventos) if i not in usados_eventos]
    return emparejados, sin_emparejar


def contar_cruces_sospechosos(
    tracks: dict[int, Track], emparejados: dict[int, Event], timestamp: float
) -> int:
    """Cuenta pares de tracks cuyo emparejamiento en ESTE frame se pudo haber
    intercambiado sin violar el umbral de IoU.

    Se llama ANTES de actualizar los tracks (con su posicion previa a este
    frame): para cada par de tracks emparejados (ta -> ea, tb -> eb), si
    tambien habria sido valido asignar ta -> eb y tb -> ea (las dos con IoU
    por encima de IOU_MINIMO_PARA_EMPAREJAR), la geometria por si sola no
    alcanzaba para distinguirlos. Eso es exactamente la situacion que produce
    un ID switch real: dos identidades que se pudieron haber cruzado entre
    este frame y el anterior.

    Es una senal SOSPECHOSA, no una certeza: sin apariencia ni groundtruth no
    se puede confirmar que el intercambio de verdad ocurrio, solo que la
    geometria no lo descarta. Ver el docstring del modulo.
    """
    ids = list(emparejados.keys())
    sospechosos = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            id_a, id_b = ids[i], ids[j]
            pred_a = predecir_bbox(tracks[id_a], timestamp)
            pred_b = predecir_bbox(tracks[id_b], timestamp)
            cruzado_a_con_b = iou(pred_a, emparejados[id_b].detection.bbox)
            cruzado_b_con_a = iou(pred_b, emparejados[id_a].detection.bbox)
            if (cruzado_a_con_b >= IOU_MINIMO_PARA_EMPAREJAR
                    and cruzado_b_con_a >= IOU_MINIMO_PARA_EMPAREJAR):
                sospechosos += 1
    return sospechosos


def color_desde_id(track_id: int) -> tuple[int, int, int]:
    """Color BGR estable y distinto por track_id, para pintarlo en el video.

    Es una funcion matematica determinista del numero (angulo dorado sobre el
    circulo de tono, para que colores consecutivos se vean bien distintos): no
    se guarda ninguna tabla ni se deriva de nada de la persona. El mismo
    track_id siempre da el mismo color, en cualquier frame del video.
    """
    tono = (track_id * 0.618033988749895) % 1.0  # razon aurea: tonos bien repartidos
    r, g, b = colorsys.hsv_to_rgb(tono, 0.65, 0.95)
    return (int(b * 255), int(g * 255), int(r * 255))  # BGR: el orden de OpenCV


def _asignar_por_frame(
    eventos: Iterator[Event], resumen: Resumen
) -> Iterator[tuple[int, list[Event]]]:
    """El nucleo del seguimiento: agrupa por frame y va asignando track_id.

    Entrega (numero_de_frame, eventos_de_ese_frame_con_track_id) en orden, en
    vez de eventos sueltos, para que quien dibuje el video (`_procesar`) pueda
    emparejar cada grupo con su frame real sin volver a agrupar nada.
    """
    tracks: dict[int, Track] = {}
    siguiente_id = 1

    for frame, grupo_iter in groupby(eventos, key=lambda e: e.frame):
        grupo = list(grupo_iter)
        timestamp = grupo[0].timestamp

        # Los tracks que llevan demasiado sin verse se dan por perdidos ANTES
        # de emparejar, para que no le "roben" el track_id a una persona
        # distinta que aparece despues en el mismo sitio.
        vencidos = [tid for tid, tr in tracks.items() if timestamp - tr.timestamp > MAX_AGE_S]
        for tid in vencidos:
            del tracks[tid]

        emparejados, sin_emparejar = emparejar(tracks, grupo)
        resumen.id_switches_sospechosos += contar_cruces_sospechosos(
            tracks, emparejados, timestamp
        )

        for track_id, evento in emparejados.items():
            actualizar_track(tracks[track_id], evento)
            evento.track_id = track_id
            resumen.emparejamientos += 1

        for evento in sin_emparejar:
            tracks[siguiente_id] = Track(bbox=evento.detection.bbox, timestamp=evento.timestamp)
            evento.track_id = siguiente_id
            resumen.tracks_creados += 1
            siguiente_id += 1

        resumen.eventos_procesados += len(grupo)
        resumen.tracks_activos_al_cierre = len(tracks)
        if resumen.eventos_procesados % EVENTOS_ENTRE_AVISOS < len(grupo):
            _avisar_progreso(resumen)

        yield frame, grupo


def asignar_track_ids(eventos: Iterator[Event], resumen: Resumen) -> Iterator[Event]:
    """Recorre los eventos en orden y les va asignando track_id, de a un frame.

    Es un generador: solo mantiene en memoria los tracks activos y las
    detecciones del frame que esta procesando, nunca el archivo completo.
    """
    for _frame, grupo in _asignar_por_frame(eventos, resumen):
        yield from grupo


def _avisar_progreso(resumen: Resumen) -> None:
    print(
        f"  eventos {resumen.eventos_procesados:>7}   "
        f"tracks_creados {resumen.tracks_creados:>5}   "
        f"emparejamientos {resumen.emparejamientos:>7}"
    )


# --------------------------------------------------------------------------
# Render: reutiliza gondola/video/, no reimplementa nada de OpenCV aqui
# --------------------------------------------------------------------------

def _fusionar_con_video(grupos, frames_de_video):
    """Empareja los grupos (frame, eventos) con los frames reales del video.

    Un frame de video sin ninguna deteccion se entrega con lista vacia -igual
    que hace `detect`-, para que el video de salida tenga tantos frames como
    el original. Si el video se acaba antes que los datos (por ejemplo,
    porque se reconfiguro MAX_FRAMES entre una corrida y otra), lo que sobra
    se entrega igual, con `imagen=None`, para que NUNCA se pierda un evento
    del .jsonl por culpa del render: dibujar es secundario, escribir el
    contrato no.
    """
    grupos_iter = iter(grupos)
    frame_actual, grupo_actual = next(grupos_iter, (None, None))
    for indice, timestamp, imagen in frames_de_video:
        if frame_actual == indice:
            eventos = grupo_actual
            frame_actual, grupo_actual = next(grupos_iter, (None, None))
        else:
            eventos = []
        yield indice, timestamp, imagen, eventos

    while frame_actual is not None:
        yield frame_actual, None, None, grupo_actual
        frame_actual, grupo_actual = next(grupos_iter, (None, None))


def _procesar(cfg: Config, entrada: Path, resumen: Resumen) -> Iterator[Event]:
    """Asigna track_id y, si hay video disponible, dibuja el resultado.

    Reutiliza `gondola.video.render.Renderer` (el mismo que usa `detect`, en
    los mismos modos privacy/debug), pasandole el color y la etiqueta por
    track_id en vez de las de confianza. Sin video, o con RENDER_MODE=none,
    el .jsonl se escribe exactamente igual: el render es un extra, nunca un
    requisito.
    """
    grupos = _asignar_por_frame(read_events(entrada), resumen)

    if cfg.render_mode == "none":
        for _frame, grupo in grupos:
            yield from grupo
        return

    if not cfg.video_path.exists():
        print(f"[track] Aviso: no encuentro el video en {cfg.video_path}; "
              f"no se puede renderizar. El .jsonl se escribe igual.")
        for _frame, grupo in grupos:
            yield from grupo
        return

    from gondola.video.reader import VideoReader
    from gondola.video.render import Renderer

    video_salida = pipeline.render_path("track", cfg, cfg.render_mode)
    with VideoReader(cfg.video_path) as video, Renderer(
        video_salida, cfg.render_mode, video.info.width, video.info.height, video.info.fps
    ) as renderer:
        print(f"[track] Render: {cfg.render_mode}  ->  {video_salida.name}")
        for indice, timestamp, imagen, grupo in _fusionar_con_video(
            grupos, video.frames(cfg.frame_stride, cfg.max_frames)
        ):
            if imagen is not None:
                renderer.write(
                    imagen, grupo, indice, timestamp,
                    color_de=lambda e: color_desde_id(e.track_id),
                    etiqueta_de=lambda e: f"id {e.track_id}",
                )
            yield from grupo


# --------------------------------------------------------------------------
# Punto de entrada de la etapa
# --------------------------------------------------------------------------

def run(cfg: Config, abrir_video: bool = False) -> int:
    """Ejecuta el seguimiento completo. Devuelve el codigo de salida.

    `abrir_video` (igual que en `detect`): al terminar, abre el video anotado
    con el reproductor por defecto del sistema. No hace nada si RENDER_MODE es
    "none" o si el video no se pudo generar (por ejemplo, porque el video de
    origen no existia).
    """
    rutas = pipeline.stage_paths("track", cfg)
    pipeline.require_input("track", cfg)

    print(f"[track] Entrada: {rutas.input_path}")
    print(f"[track] iou_minimo={IOU_MINIMO_PARA_EMPAREJAR}  max_age={MAX_AGE_S}s")
    print()

    resumen = Resumen()
    inicio = time.perf_counter()
    escritos = write_events(rutas.output_path, _procesar(cfg, rutas.input_path, resumen))
    transcurrido = time.perf_counter() - inicio

    ruta_resumen = pipeline.summary_path("track", cfg)
    _escribir_resumen(ruta_resumen, cfg, resumen, transcurrido)

    video_salida = pipeline.render_path("track", cfg, cfg.render_mode)
    _imprimir_resultado(resumen, escritos, transcurrido, rutas.output_path, ruta_resumen,
                       cfg, video_salida)

    if abrir_video and cfg.render_mode != "none" and video_salida.exists():
        from gondola.video.render import abrir_con_el_sistema

        abrir_con_el_sistema(video_salida)

    return 0


def _leer_info_de_video_desde_detect(cfg: Config) -> dict:
    """Lee width/height/fps del resumen de `detect`, para que `verify` tambien
    pueda comprobar "bbox cabe dentro del frame" y "timestamp coincide con
    frame/fps" sobre la salida de esta etapa (si no los propagamos, verify
    omite esas dos reglas para track.jsonl aunque las tenga para detect.jsonl).

    Si el resumen anterior no existe, esta corrupto o no trae esos campos, no
    se falla: track no depende de que detect se haya corrido con render
    activado ni de nada mas alla de su propia entrada; solo aprovecha el dato
    si esta.
    """
    ruta = pipeline.summary_path("detect", cfg)
    if not ruta.exists():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return datos.get("video", {})


def _escribir_resumen(destino: Path, cfg: Config, resumen: Resumen, transcurrido: float) -> None:
    """Guarda las metricas de la corrida. Sin esto no se puede comparar nada."""
    datos = {
        "contract_version": CONTRACT_VERSION,
        "stage": "track",
        "video_id": cfg.video_id,
        "video": _leer_info_de_video_desde_detect(cfg),
        "params": {
            "iou_minimo_para_emparejar": IOU_MINIMO_PARA_EMPAREJAR,
            "max_age_s": MAX_AGE_S,
        },
        "results": {
            "eventos_procesados": resumen.eventos_procesados,
            "tracks_creados": resumen.tracks_creados,
            "emparejamientos": resumen.emparejamientos,
            "tracks_activos_al_cierre": resumen.tracks_activos_al_cierre,
            "id_switches_sospechosos": resumen.id_switches_sospechosos,
        },
        "performance": {
            "segundos": round(transcurrido, 2),
            "eventos_por_segundo": round(
                resumen.eventos_procesados / transcurrido, 2
            ) if transcurrido > 0 else 0.0,
        },
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def _imprimir_resultado(
    resumen: Resumen, escritos: int, transcurrido: float, jsonl: Path, ruta_resumen: Path,
    cfg: Config, video_salida: Path,
) -> None:
    print()
    print("-" * 66)
    print(f"  Eventos procesados     {resumen.eventos_procesados}")
    print(f"  Tracks creados         {resumen.tracks_creados}")
    print(f"  Emparejamientos        {resumen.emparejamientos}")
    print(f"  Tracks activos al cierre  {resumen.tracks_activos_al_cierre}  "
          f"(quedaron 'vivos' al terminar el video)")
    print(f"  ID switches sospechosos   {resumen.id_switches_sospechosos}  "
          f"(cota superior sin groundtruth; ver docstring del modulo)")
    print(f"  Tiempo                 {transcurrido:.2f} s")
    print("-" * 66)
    print(f"  Eventos   {jsonl}  ({escritos} lineas)")
    print(f"  Resumen   {ruta_resumen}")
    if cfg.render_mode != "none" and video_salida.exists():
        print(f"  Video     {video_salida}")
    print()
    print("  Siguiente etapa:  python -m gondola zones   (Persona 4)")
