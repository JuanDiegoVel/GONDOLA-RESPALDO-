"""Etapa 4: interaccion con productos. Responsable: Persona 5.

QUE HACE
--------
Lee los eventos ya ubicados por la Persona 4 (`<video>.zones.jsonl`, con
`zone` y `metrics.dwell_time` rellenos) y rellena SOLO `interaction`
(`event` y `product_zone`). No toca `detection`, ni `track_id`, ni `zone`, ni
`metrics.dwell_time`: los copia tal cual.

El archivo de salida conserva TODOS los eventos de entrada, no solo los que
interactuaron. La Persona 6 necesita `zone` y `dwell_time` de todos para
contar personas y permanencia; los eventos sin interaccion salen con
`interaction.event = null`, que es lo que ya asume `eventos_detectados()` en
`gondola/evaluate/evaluator.py`.

COMO SE DECIDE QUE ALGUIEN ALCANZO EL ESTANTE
---------------------------------------------
Reglas geometricas sobre la caja, sin pose estimation (decision del lider,
ver `docs/interact-fase1-diseno.md` seccion 3). El rasgo es el ASPECTO de la
caja, `width / height`, comparado contra la mediana movil del PROPIO track:

    razon = aspecto_actual / mediana_movil_del_track

Cuando alguien estira el brazo hacia el estante, la caja se ensancha sin
crecer de alto: la razon sube. Normalizar contra la mediana del propio track
-y no contra un numero fijo- es lo que absorbe el cambio lento de escala
cuando la persona se acerca o se aleja de la camara.

Un EPISODIO es una racha de muestras consecutivas del mismo track con
`razon >= UMBRAL_RAZON_ASPECTO`. Cada episodio pasa por cinco filtros (en
este orden, que es el que determina a que filtro se le atribuye el descarte
en el resumen final):

    1. borde       ninguna caja del episodio toca el borde del frame
    2. duracion    dura al menos DURACION_MINIMA_S
    3. pies        los pies se quedaron quietos mientras duro
    4. zona        el pico cayo dentro de alguna zona (si no, no hay estante)
    5. refractario no hay otro evento de ese track en el ultimo REFRACTARIO_S

El que sobrevive produce UN SOLO evento, en el frame del PICO (maximo
aspecto, desempate por numero de frame menor). Ver `pico_del_episodio`.

POR QUE LOS UMBRALES VAN EN ALTURAS DE CAJA Y NO EN PIXELES
-----------------------------------------------------------
"Pies quietos por debajo de 40 px/s" no transfiere a otra camara ni a otra
resolucion; "por debajo de 0,3 alturas de caja por segundo" si. Es el mismo
espiritu por el que `track` mide en segundos y no en frames. Cada constante
de abajo lleva al lado de donde salio su valor inicial: todas vienen de las
mediciones de la fase 1 sobre `video_001` (3.801 eventos, 16 tracks, 920x680
a 30 fps, 205 s), documentadas en `docs/interact-fase1-diseno.md` seccion 2.

NINGUNO ESTA VALIDADO CONTRA GROUNDTRUTH. Son puntos de partida razonados a
partir del ruido medido. La calibracion real espera a que haya video anotado
en `data/groundtruth/` (ver CLAUDE.md); hasta entonces no se ajustan "a ojo"
mirando el video, porque eso es sobreajustar a un clip sin forma de saberlo.

POR QUE ESTO NECESITA UNA VENTANA DE LATENCIA
----------------------------------------------
Decidir "este evento es el pico del episodio" exige haber visto los frames
que vienen DESPUES, y la mediana centrada necesita media ventana de adelanto.
Pero `verify` comprueba que los numeros de frame no retrocedan, asi que la
salida tiene que ir en el mismo orden que la entrada.

La solucion es una cola FIFO con retardo fijo de LATENCIA_S segundos de
video: los eventos entran, se deciden cuando el reloj de entrada ya paso de
largo, y salen por el mismo lado y en el mismo orden en que llegaron. En
memoria vive solo esa ventana por track activo, nunca el archivo completo
(ver `_procesar`).

Lo unico que puede retener la cola mas alla de LATENCIA_S es un episodio
abierto, y su duracion la acota la propia mediana centrada: ver el techo de
aqui abajo. No hace falta ningun tope de duracion aparte -se probo y no se
alcanzaba nunca-, y por eso no existe.

EL TECHO DEL METODO: UN GESTO LARGO SE VUELVE SU PROPIA LINEA BASE
------------------------------------------------------------------
La mediana esta CENTRADA en cada muestra, asi que la ventana de +-0,5 s mira
por igual hacia atras y hacia delante. En cuanto el gesto ocupa mas de la
MITAD de la ventana, la mayoria de las muestras que la componen son del propio
gesto: la mediana sube hasta el, la razon vuelve a 1,0 y el episodio se cierra
solo. En la practica el metodo solo ve gestos de menos de ~0,5 s.

Eso es coherente con lo medido en la fase 1 (picos de 0,03-0,37 s), pero NO
con un gesto real de tomar un producto, que dura 0,5-1,5 s. Dicho sin adornos:
si alguien alcanza el estante despacio, esta etapa no lo va a ver, y no va a
quedar constancia en ningun contador de descarte porque el episodio no llega
ni a formarse. Es el limite superior del rasgo, no un bug: es lo que hay que
recalibrar (ventana y umbral juntos) cuando exista groundtruth.

Tambien explica por que subir VENTANA_MEDIANA_S no es gratis: alarga el techo
pero mete en la linea base el cambio de escala que la mediana estaba ahi para
absorber.

LO QUE ESTE ENFOQUE NO PUEDE HACER (resumido; el detalle, en la seccion 5 del
documento de diseno)
--------------------------------------------------------------------------
- No distingue fisicamente PICK_UP de PUT_BACK: es el mismo gesto y lo unico
  que cambia es que hay en la mano. Se trata con la CONVENCION de
  `etiqueta_de_alcance`, y de ahi cuelga la tasa de rechazo de la Persona 6.
- Un giro del cuerpo de perfil a frontal ensancha la caja exactamente igual
  que estirar el brazo. Es el falso positivo dominante.
- Un brazo ocluido no cambia la caja: falso negativo sin huella medible.
- Si `track` fragmenta una visita, la convencion de emparejamiento se rompe.
- Un hueco de deteccion dentro de un episodio (la persona desaparece un par
  de frames) no lo parte, y su duracion sale inflada. La unica cota es la
  ventana de latencia: un hueco mas largo que LATENCIA_S si parte el
  episodio en dos.
"""

from __future__ import annotations

import json
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from gondola import pipeline
from gondola.config import Config
from gondola.contract import CONTRACT_VERSION, Event, InteractionEvent
from gondola.jsonl import read_events, write_events
from gondola.stages.zones import UMBRAL_SE_DETIENE_S, _ruta_zonas
from gondola.zones_config import ZonesConfig, load_zones_config

# `_ruta_zonas` es privada de la etapa de la Persona 4 y aun asi se importa a
# proposito: la convencion "la calibracion de esta camara vive en
# data/zones/<video_id>.json" es suya, y copiarla aqui significaria dos sitios
# que actualizar el dia que `ZONES_PATH` llegue a config.py. Lo mismo con
# UMBRAL_SE_DETIENE_S: el APPROACH reutiliza el umbral que ella ya justifico,
# no inventa un segundo umbral que diga casi lo mismo.


# --------------------------------------------------------------------------
# Umbrales. Cada uno dice de que medicion de la fase 1 sale su valor inicial.
# --------------------------------------------------------------------------

UMBRAL_RAZON_ASPECTO = 1.12
"""Cuanto tiene que subir el aspecto sobre la mediana del track para contar
como alcance. DE DONDE SALE: en la fase 1, el ruido de la caja entre frames
consecutivos fue de 0,5 % (mediana) y 5-8 % (p95), mientras que la excursion
maxima del ancho dentro de un track llego a +22 % ... +43 %. Un 12 % queda
por encima del p95 del ruido y bien por debajo de la senal medida."""

VENTANA_MEDIANA_S = 1.0
"""Ancho de la ventana de la mediana movil, CENTRADA en cada muestra. DE
DONDE SALE: es la ventana con la que se midieron los cuatro rasgos de la fase
1 (ancho, alto, area y aspecto). Un segundo es largo comparado con un gesto
(0,03-0,37 s medidos) y corto comparado con acercarse a la camara, que es
justo lo que tiene que absorber."""

MEDIA_VENTANA_S = VENTANA_MEDIANA_S / 2
"""Medio segundo de adelanto es lo que necesita una mediana centrada."""

MUESTRAS_MINIMAS_MEDIANA = 3
"""Con una o dos muestras la mediana es el propio valor (razon = 1,0) o su
promedio: no dice nada. Por debajo de esto no se abre ningun episodio, para
que los primeros frames de un track no inventen un alcance."""

DURACION_MINIMA_S = 0.3
"""Duracion minima de un episodio. DE DONDE SALE: en la fase 1, filtrar por
0,3 s dejo 12 episodios de aspecto en todo el video, contra 5 usando el ancho
y 3 usando el alto. Es la frontera por debajo de la cual los picos son casi
todos temblor de la caja: la mayoria duraba menos de 0,2 s. OJO: un gesto real
de tomar algo dura 0,5-1,5 s, asi que este umbral es DEMASIADO PERMISIVO a
proposito. Se prefirio dejar pasar falsos positivos que se puedan contar antes
que ocultarlos subiendo el umbral sin groundtruth que lo respalde."""

UMBRAL_PIES_QUIETOS_ALTURAS_S = 0.3
"""Velocidad maxima del punto de apoyo para considerar que los pies estan
quietos, en ALTURAS DE CAJA POR SEGUNDO. DE DONDE SALE: en la fase 1 los pies
"en reposo" se movian 21-57 px/s, que es sobre todo temblor de YOLO y no
caminar, asi que el umbral tiene que quedar por encima. Con la caja tipica de
ese video (205 x 238 px), 0,3 alturas/s son unos 71 px/s. Se expresa en
alturas y no en pixeles para que transfiera a otra camara u otra
resolucion."""

REFRACTARIO_S = 1.0
"""Tras emitir un evento, ese track_id no puede emitir otro hasta pasado este
tiempo. DE DONDE SALE: una caja temblorosa no puede disparar dos veces el
mismo gesto. Nota para quien calibre: la tolerancia del evaluador es de 2,0 s
(`gondola/evaluate/evaluator.py`), asi que dos detecciones separadas por menos
de eso nunca podran ser ambas acierto contra una misma anotacion."""

LATENCIA_S = 1.0
"""Retardo fijo, en segundos de video, entre leer un evento y poder
escribirlo. Tiene que cubrir el medio segundo de adelanto de la mediana
centrada mas el cierre del episodio. Ver "POR QUE ESTO NECESITA UNA VENTANA DE
LATENCIA" en el docstring del modulo."""

TOLERANCIA_FLOTANTE_S = 1e-9
"""NO es un margen de calibracion: es lo que hace que un episodio que dura
exactamente DURACION_MINIMA_S no dependa del ultimo bit del flotante. Los
timestamps vienen de `frame / fps` y viajan por JSON, asi que 9 frames a 30
fps pueden llegar como 0,29999999999999993 en vez de 0,3. Sin esto, en
`video_001` se perdia uno de los tres episodios que superan la duracion
minima. Es mil millones de veces mas pequeno que un frame: no puede cambiar
ninguna decision real."""

DURACION_GESTO_S = 0.3
"""Duracion de un gesto tipico, solo para el aviso de FRAME_STRIDE. Es el
extremo optimista del rango medido (0,03-0,37 s): si ni siquiera el caso
favorable da muestras suficientes, el stride no sirve."""

MUESTRAS_MINIMAS_GESTO = 3
"""Muestras minimas para que un gesto sea detectable: dos para abarcar
DURACION_MINIMA_S y una tercera para que la mediana signifique algo
(MUESTRAS_MINIMAS_MEDIANA)."""

STRIDE_MAXIMO_FIABLE = 3
"""Por encima de este FRAME_STRIDE la etapa avisa de que sus resultados no son
fiables. DE DONDE SALE: no es un numero aparte, es el que hace cuadrar los dos
de arriba. A 30 fps, un gesto de 0,3 s da 0,3 * 30 / stride muestras: con
stride 3 son exactamente 3, el minimo; con stride 5 son 1,8."""


# --------------------------------------------------------------------------
# Logica pura: se prueba con eventos construidos a mano, sin archivos
# --------------------------------------------------------------------------

def aspecto(ancho: float, alto: float) -> float:
    """Razon `width / height` de la caja. Adimensional a proposito.

    Es el unico de los cuatro rasgos probados en la fase 1 que ya no depende
    de la escala antes de normalizar: una persona el doble de cerca da una
    caja el doble de grande pero con el mismo aspecto.

    OJO, PRIVACIDAD: esto es la forma de la CAJA, no la de la persona. La
    misma persona da aspectos distintos segun este de frente o de perfil, y
    ese es justamente el falso positivo conocido del metodo.
    """
    return ancho / alto


def toca_el_borde(evento: Event, ancho_frame: int, alto_frame: int) -> bool:
    """True si la caja toca cualquier borde del frame.

    Estas cajas se excluyen porque ahi el ancho lo recorta el borde de la
    imagen, no el cuerpo real: la caja se ensancha o se estrecha por como
    entra la persona en el encuadre, sin que haya ningun gesto. En la fase 1
    fue el 3,7 % de las cajas de `video_001`.
    """
    caja = evento.detection.bbox
    return (
        caja.x <= 0
        or caja.y <= 0
        or caja.x + caja.width >= ancho_frame
        or caja.y + caja.height >= alto_frame
    )


def etiqueta_de_alcance(alcances_previos: int) -> InteractionEvent:
    """Dentro de una visita, el primer alcance detectado se etiqueta PICK_UP y
    el segundo PUT_BACK. Esto es una CONVENCION, no una medicion: el sistema
    no puede ver que hay en la mano de la persona.

    Fisicamente los dos gestos son identicos -el brazo sale hacia el estante y
    vuelve- y una bounding box no distingue una mano vacia de una con producto.
    Del tercer alcance en adelante se alterna (impares PICK_UP, pares
    PUT_BACK), que es la extension natural de la misma convencion: tomar,
    devolver, tomar.

    CONSECUENCIA QUE HAY QUE DECIR EN VOZ ALTA: la tasa de rechazo que calcule
    la Persona 6 (`put_back / pick_up`) NO se mide, se INFIERE de este
    supuesto. Si en el video real la gente toma dos productos seguidos sin
    devolver ninguno, esta funcion los etiqueta PICK_UP y PUT_BACK y la tasa
    sale del 100 % siendo del 0 %. Solo el groundtruth puede confirmar o
    tumbar el supuesto; hasta entonces la tasa de rechazo se presenta como lo
    que es, una estimacion que depende de una convencion.
    """
    return InteractionEvent.PICK_UP if alcances_previos % 2 == 0 else InteractionEvent.PUT_BACK


def categorias_por_estante(zonas: ZonesConfig) -> dict[tuple[str, str], str | None]:
    """Mapa (zone_id, segment) -> categoria de producto, ya con la herencia
    aplicada: `shelf.product_category` -> `gondola.product_category` -> None.

    `product_zone` lleva la CATEGORIA del producto, no el segmento: el segmento
    ya viaja en `zone.segment` y duplicarlo gastaria el unico campo que puede
    cargar significado comercial, dejando a la Persona 6 sin forma de agregar
    por categoria entre estantes. El contrato lo dice en su propio ejemplo
    (`Ej: 'bebidas'`).
    """
    return {
        (gondola.zone_id, estante.segment): (
            gondola.product_category
            if estante.product_category is None
            else estante.product_category
        )
        for gondola, estante in zonas.shelves()
    }


def muestras_por_gesto(fps: float, stride: int) -> float:
    """Cuantas muestras deja un gesto tipico con ese stride. Ver el aviso."""
    return DURACION_GESTO_S * fps / stride


def aviso_de_stride(stride: int, fps: float | None) -> str | None:
    """El texto del aviso de FRAME_STRIDE, o None si el stride es fiable.

    No falla ni detiene la etapa: avisa. Correr con stride alto sigue siendo
    util para probar la cadena entera rapido; lo que no se puede es creerse
    los numeros que salgan.
    """
    if stride <= STRIDE_MAXIMO_FIABLE:
        return None

    if fps:
        muestras = muestras_por_gesto(fps, stride)
        cuentas = (
            f"A {fps:.0f} fps y con FRAME_STRIDE={stride}, un gesto de "
            f"{DURACION_GESTO_S} s deja {muestras:.1f} muestras"
        )
    else:
        muestras = muestras_por_gesto(30.0, stride)
        cuentas = (
            f"No pude leer los fps del resumen de 'zones'; suponiendo 30 fps y "
            f"con FRAME_STRIDE={stride}, un gesto de {DURACION_GESTO_S} s deja "
            f"{muestras:.1f} muestras"
        )

    return (
        f"AVISO: los resultados de esta corrida NO son fiables.\n"
        f"  {cuentas}, y hacen falta al menos {MUESTRAS_MINIMAS_GESTO} "
        f"(dos para abarcar los {DURACION_MINIMA_S} s de duracion minima y una "
        f"tercera para que la mediana movil signifique algo).\n"
        f"  Con menos muestras que eso el gesto no llega a formar un episodio y "
        f"se pierde entero, sin dejar rastro en los contadores de descarte.\n"
        f"  Que hacer: vuelve a correr la cadena desde 'detect' con "
        f"FRAME_STRIDE <= {STRIDE_MAXIMO_FIABLE} antes de sacar conclusiones."
    )


@dataclass
class Muestra:
    """Un evento de entrada mas lo que se calcula de el una sola vez.

    Guarda una referencia al `Event`, no una copia: cuando se decide que esta
    muestra es el pico de un episodio, se rellena su `interaction` en el mismo
    objeto que despues sale por la cola.
    """

    evento: Event
    track_id: int | None
    t: float
    aspecto: float
    pies: tuple[float, float]
    altura: float
    toca_borde: bool
    zona: tuple[str, str] | None
    dwell: float | None


def velocidad_pies_alturas_por_s(anterior: Muestra, actual: Muestra) -> float:
    """Cuanto se movio el punto de apoyo entre dos muestras, en alturas de caja
    por segundo.

    Se divide por la altura de la caja -no por un numero de pixeles fijo- para
    que el umbral no dependa de la resolucion ni de lo lejos que este la
    persona de la camara. Se usa la altura de la muestra ANTERIOR, que es la
    que estaba vigente durante el desplazamiento.
    """
    dt = actual.t - anterior.t
    if dt <= 0 or anterior.altura <= 0:
        return 0.0
    dx = actual.pies[0] - anterior.pies[0]
    dy = actual.pies[1] - anterior.pies[1]
    distancia = (dx * dx + dy * dy) ** 0.5
    return (distancia / anterior.altura) / dt


def pies_quietos(muestras: list[Muestra]) -> bool:
    """True si los pies se quedaron quietos durante todo el episodio.

    Se toma la MEDIANA de las velocidades entre muestras consecutivas, no el
    maximo: un solo salto de la caja de YOLO no deberia descartar un gesto
    entero, y la mediana es justo lo que ignora ese salto. No hace falta un
    caso aparte para un episodio de una sola muestra: ese ya se fue por el
    filtro de duracion, que exige mas de cero segundos.

    OJO, ESTE FILTRO ES MAS DURO DE LO QUE PARECE: `support_point` es
    `(x + width/2, y + height)`, asi que ensanchar la caja YA MUEVE el punto
    de apoyo medio ancho, aunque los pies no se hayan movido ni un pixel. Un
    brazo que ensancha la caja un 30 % (caja tipica de 205x238 px) corre el
    punto unos 30 px en 0,37 s: 0,2 alturas/s de las 0,3 disponibles, gastadas
    por el propio gesto que estamos buscando. Es una de las cosas que hay que
    revisar al recalibrar con groundtruth, y explica que en la fase 1 solo 3
    de 12 episodios pasaran este filtro.
    """
    velocidades = [
        velocidad_pies_alturas_por_s(anterior, actual)
        for anterior, actual in zip(muestras, muestras[1:])
    ]
    if not velocidades:
        return False
    return statistics.median(velocidades) < UMBRAL_PIES_QUIETOS_ALTURAS_S


def pico_del_episodio(muestras: list[Muestra]) -> Muestra:
    """La muestra de maximo aspecto; si empatan, la de numero de frame menor.

    El pico es mas estable que el inicio del episodio: el primer frame que
    cruza el umbral se corre cada vez que alguien mueve UMBRAL_RAZON_ASPECTO,
    mientras que el maximo del gesto sigue siendo el mismo frame.
    """
    return min(muestras, key=lambda m: (-m.aspecto, m.evento.frame))


# --------------------------------------------------------------------------
# Estado que vive en memoria mientras corre la etapa
# --------------------------------------------------------------------------

@dataclass
class EstadoTrack:
    """Lo que hay que recordar de un track para decidir sus interacciones.

    Todo lo de aqui es una ventana corta, nunca la historia completa del
    track: `historial` guarda un segundo de aspectos (dos numeros por muestra,
    sin referencias a eventos) y `pendientes` los eventos que aun no se pueden
    decidir. Ver `_procesar`.
    """

    historial: deque[tuple[float, float]] = field(default_factory=deque)  # (t, aspecto)
    pendientes: deque[Muestra] = field(default_factory=deque)
    episodio: list[Muestra] = field(default_factory=list)
    t_decidido: float = float("-inf")  # hasta aqui, este track ya no cambia

    # La visita en curso, en el mismo sentido que le da la Persona 4: mismo
    # track en la misma zona sin salirse. Se reinicia cuando cambia la zona o
    # cuando `dwell_time` baja (eso es zones.py empezando a contar de nuevo).
    zona_visita: tuple[str, str] | None = None
    dwell_previo: float | None = None
    approach_emitido: bool = False
    alcances_en_visita: int = 0

    t_ultimo_evento: float | None = None  # para el periodo refractario


@dataclass
class Resumen:
    """Lo que se va contando durante la corrida y acaba en el JSON de resumen.

    Los descartes se cuentan por separado a proposito: el lider necesita ver
    DONDE se pierde la senal, no solo cuantos eventos salieron.
    """

    eventos_procesados: int = 0
    approach: int = 0
    pick_up: int = 0
    put_back: int = 0

    episodios_candidatos: int = 0
    descartados_por_borde: int = 0
    descartados_por_duracion: int = 0
    descartados_por_pies: int = 0
    descartados_por_sin_zona: int = 0
    descartados_por_refractario: int = 0

    approach_candidatos: int = 0
    approach_descartados_por_refractario: int = 0

    @property
    def eventos_emitidos(self) -> int:
        return self.approach + self.pick_up + self.put_back


# --------------------------------------------------------------------------
# La maquina: ingresar -> evaluar con retardo -> liberar en orden
# --------------------------------------------------------------------------

def _mediana_centrada(estado: EstadoTrack, muestra: Muestra) -> float | None:
    """Mediana de los aspectos del track en +-MEDIA_VENTANA_S de esta muestra.

    Devuelve None si no hay muestras suficientes para que signifique algo.
    Mira hacia atras en `historial` (ya evaluadas) y hacia delante en
    `pendientes` (ya leidas del archivo, aun sin decidir): por eso la etapa
    necesita la ventana de latencia.
    """
    aspectos = [
        a for t, a in estado.historial if abs(t - muestra.t) <= MEDIA_VENTANA_S
    ]
    aspectos += [
        m.aspecto for m in estado.pendientes if abs(m.t - muestra.t) <= MEDIA_VENTANA_S
    ]
    aspectos.append(muestra.aspecto)
    if len(aspectos) < MUESTRAS_MINIMAS_MEDIANA:
        return None
    return statistics.median(aspectos)


def _actualizar_visita(estado: EstadoTrack, muestra: Muestra) -> None:
    """Detecta si esta muestra empieza una visita nueva y reinicia su cuenta.

    Una visita nueva es lo mismo que para la Persona 4: cambio de zona, o un
    `dwell_time` que baja (zones.py lo reinicia a 0,0 al empezar a contar de
    nuevo). Es la unidad sobre la que se aplican la convencion de
    emparejamiento y el "un APPROACH por visita".
    """
    nueva = muestra.zona != estado.zona_visita
    if not nueva and muestra.dwell is not None and estado.dwell_previo is not None:
        nueva = muestra.dwell < estado.dwell_previo

    if nueva:
        estado.zona_visita = muestra.zona
        estado.approach_emitido = False
        estado.alcances_en_visita = 0
    estado.dwell_previo = muestra.dwell


def _en_refractario(estado: EstadoTrack, t: float) -> bool:
    """True si este track emitio un evento hace menos de REFRACTARIO_S."""
    return (
        estado.t_ultimo_evento is not None
        and t - estado.t_ultimo_evento < REFRACTARIO_S
    )


def _emitir(
    estado: EstadoTrack,
    muestra: Muestra,
    evento: InteractionEvent,
    categorias: dict[tuple[str, str], str | None],
) -> None:
    """Escribe la interaccion en el evento y arranca el periodo refractario.

    `product_zone` solo se rellena aqui, junto con `event`: nunca uno sin el
    otro. La tabla `events` de `backend/database/schema.sql` acepta un
    `product_zone` huerfano sin quejarse, y una categoria sin evento no
    significa nada -toda persona esta siempre "frente a" alguna categoria-.
    Que sea `null` cuando el estante no declaro categoria si es correcto: la
    columna lo permite y el dato de verdad no existe.
    """
    muestra.evento.interaction.event = evento
    if muestra.zona is not None:
        muestra.evento.interaction.product_zone = categorias.get(muestra.zona)
    estado.t_ultimo_evento = muestra.t


def _cerrar_episodio(
    estado: EstadoTrack,
    categorias: dict[tuple[str, str], str | None],
    resumen: Resumen,
) -> None:
    """Aplica los filtros al episodio que acaba de terminar y, si sobrevive,
    marca su pico con PICK_UP o PUT_BACK.

    El orden de los filtros es el que decide a que causa se le atribuye cada
    descarte en el resumen. Va de lo que invalida el dato (la caja no es del
    cuerpo) a lo que depende de lo que ya emitimos (el refractario).
    """
    muestras = estado.episodio
    estado.episodio = []
    if not muestras:
        return

    resumen.episodios_candidatos += 1

    if any(m.toca_borde for m in muestras):
        resumen.descartados_por_borde += 1
        return

    duracion = muestras[-1].t - muestras[0].t
    if duracion + TOLERANCIA_FLOTANTE_S < DURACION_MINIMA_S:
        resumen.descartados_por_duracion += 1
        return

    if not pies_quietos(muestras):
        resumen.descartados_por_pies += 1
        return

    pico = pico_del_episodio(muestras)
    if pico.zona is None:
        # Sin zona no hay estante del que alcanzar nada, no hay categoria que
        # poner en product_zone, y el evaluador (que casa por zone_id) lo
        # contaria como falso positivo seguro.
        resumen.descartados_por_sin_zona += 1
        return

    if _en_refractario(estado, pico.t):
        resumen.descartados_por_refractario += 1
        return

    etiqueta = etiqueta_de_alcance(estado.alcances_en_visita)
    estado.alcances_en_visita += 1
    _emitir(estado, pico, etiqueta, categorias)
    if etiqueta is InteractionEvent.PICK_UP:
        resumen.pick_up += 1
    else:
        resumen.put_back += 1


def _avanzar(
    estado: EstadoTrack,
    muestra: Muestra,
    categorias: dict[tuple[str, str], str | None],
    resumen: Resumen,
) -> None:
    """Procesa UNA muestra ya decidible del track: APPROACH y episodios.

    Al terminar deja `estado.t_decidido` en el ultimo instante que ya no puede
    cambiar. Mientras hay un episodio abierto ese instante NO avanza: sus
    muestras todavia pueden convertirse en el pico, y por eso se quedan en la
    cola de salida.
    """
    _actualizar_visita(estado, muestra)

    # APPROACH: uno por visita, en el evento donde dwell_time cruza el umbral
    # que la Persona 4 ya justifico. Se decide en esta misma linea de tiempo,
    # y no al leer el evento, para que comparta el periodo refractario con los
    # alcances en vez de correr por su cuenta un segundo adelantada.
    if (
        not estado.approach_emitido
        and muestra.zona is not None
        and muestra.dwell is not None
        and muestra.dwell >= UMBRAL_SE_DETIENE_S
    ):
        resumen.approach_candidatos += 1
        estado.approach_emitido = True  # uno por visita, se emita o no
        if _en_refractario(estado, muestra.t):
            resumen.approach_descartados_por_refractario += 1
        else:
            _emitir(estado, muestra, InteractionEvent.APPROACH, categorias)
            resumen.approach += 1

    mediana = _mediana_centrada(estado, muestra)
    if mediana is not None and (muestra.aspecto / mediana) >= UMBRAL_RAZON_ASPECTO:
        estado.episodio.append(muestra)
        return  # todavia puede ser el pico: no se decide, no se libera

    _cerrar_episodio(estado, categorias, resumen)
    estado.t_decidido = muestra.t


def _evaluar_hasta(
    estados: dict[int | None, EstadoTrack],
    limite: float,
    categorias: dict[tuple[str, str], str | None],
    resumen: Resumen,
) -> None:
    """Avanza la maquina de todos los tracks hasta el instante `limite`.

    Hay que recorrer TODOS los tracks y no solo el del evento recien leido: un
    track que deja de aparecer (se fue de la tienda, o `track` lo perdio) no
    volveria a avanzar nunca, y como la cola de salida respeta el orden de
    llegada, sus eventos bloquearian a los de todos los demas.
    """
    for estado in estados.values():
        while estado.pendientes and estado.pendientes[0].t <= limite:
            muestra = estado.pendientes.popleft()
            _avanzar(estado, muestra, categorias, resumen)
            estado.historial.append((muestra.t, muestra.aspecto))
            while (
                estado.historial
                and muestra.t - estado.historial[0][0] > MEDIA_VENTANA_S
            ):
                estado.historial.popleft()

        # Quedarse sin pendientes despues de vaciar hasta `limite` significa
        # que este track no ha aparecido en toda la ventana de latencia: su
        # episodio abierto ya no puede crecer. Se cierra aqui en vez de esperar
        # al final del archivo reteniendo la cola de salida de todos los demas.
        if estado.episodio and not estado.pendientes:
            _cerrar_episodio(estado, categorias, resumen)
            estado.t_decidido = max(estado.t_decidido, limite)


def _liberar(
    cola: deque[Muestra], estados: dict[int | None, EstadoTrack]
) -> Iterator[Event]:
    """Saca de la cola los eventos que ya no pueden cambiar, EN ORDEN.

    En orden de llegada y no de decision: si la cabeza pertenece a un track con
    un episodio abierto, todo lo que hay detras espera, aunque ya este decidido.
    Es lo que garantiza que los numeros de frame no retrocedan en la salida,
    que es lo que comprueba `verify`.
    """
    while cola and cola[0].t <= estados[cola[0].track_id].t_decidido:
        yield cola.popleft().evento


def _procesar(
    entrada: Path,
    categorias: dict[tuple[str, str], str | None],
    ancho_frame: int,
    alto_frame: int,
    resumen: Resumen,
) -> Iterator[Event]:
    """Recorre los eventos y entrega los mismos eventos, ya con interaction.

    Es un generador con retardo: lee un evento, decide los que ya llevan
    LATENCIA_S segundos de video esperando, y entrega los que quedaron
    firmes. En memoria hay como mucho la ventana de latencia mas el episodio
    abierto de cada track, nunca el archivo completo; y un episodio no puede
    durar mas que la ventana de la mediana (ver "EL TECHO DEL METODO" en el
    docstring del modulo), asi que la cota es de algo menos de dos segundos de
    video por track activo.
    """
    estados: dict[int | None, EstadoTrack] = {}
    cola: deque[Muestra] = deque()
    reloj = float("-inf")

    for evento in read_events(entrada):
        resumen.eventos_procesados += 1
        caja = evento.detection.bbox
        zona = (
            (evento.zone.zone_id, evento.zone.segment)
            if evento.zone.zone_id is not None and evento.zone.segment is not None
            else None
        )
        muestra = Muestra(
            evento=evento,
            track_id=evento.track_id,
            t=evento.timestamp,
            aspecto=aspecto(caja.width, caja.height),
            pies=caja.support_point,
            altura=caja.height,
            toca_borde=toca_el_borde(evento, ancho_frame, alto_frame),
            zona=zona,
            dwell=evento.metrics.dwell_time,
        )

        # `track.jsonl` garantiza track_id relleno (ver
        # docs/tracking-guia-para-zonas.md); si aun asi llegara en null, todos
        # esos eventos comparten estado, igual que hace zones.py.
        estado = estados.setdefault(muestra.track_id, EstadoTrack())
        estado.pendientes.append(muestra)
        cola.append(muestra)

        # El reloj no retrocede aunque la entrada trajera un evento fuera de
        # orden: si retrocediera, se decidirian eventos dos veces.
        reloj = max(reloj, muestra.t)
        _evaluar_hasta(estados, reloj - LATENCIA_S, categorias, resumen)
        yield from _liberar(cola, estados)

    # Fin del archivo: ya no va a llegar nada, todo se puede decidir.
    _evaluar_hasta(estados, float("inf"), categorias, resumen)
    for estado in estados.values():
        estado.t_decidido = float("inf")
    yield from _liberar(cola, estados)


# --------------------------------------------------------------------------
# Punto de entrada de la etapa
# --------------------------------------------------------------------------

def run(cfg: Config) -> int:
    """Ejecuta la deteccion de interacciones. Devuelve el codigo de salida."""
    rutas = pipeline.stage_paths("interact", cfg)
    pipeline.require_input("interact", cfg)

    ruta_zonas = _ruta_zonas(cfg)
    zonas = load_zones_config(ruta_zonas)  # ZonesConfigError si falta o esta mal
    categorias = categorias_por_estante(zonas)
    info_video = _leer_info_de_video_desde_zones(cfg)

    print(f"[interact] Entrada: {rutas.input_path}")
    print(f"[interact] Zonas:   {ruta_zonas}  "
          f"(frame {zonas.frame_width}x{zonas.frame_height})")
    print(f"[interact] Umbrales: aspecto>={UMBRAL_RAZON_ASPECTO}  "
          f"duracion>={DURACION_MINIMA_S}s  "
          f"pies<{UMBRAL_PIES_QUIETOS_ALTURAS_S} alturas/s  "
          f"refractario={REFRACTARIO_S}s  approach>={UMBRAL_SE_DETIENE_S}s")

    aviso = aviso_de_stride(cfg.frame_stride, info_video.get("fps"))
    if aviso:
        print()
        print(f"[interact] {aviso}")
    print()

    # El tamano del frame sale del archivo de zonas y no del resumen de la
    # corrida anterior: el filtro del borde cambia los resultados, asi que su
    # fuente tiene que existir siempre. El archivo de zonas hace falta de todas
    # formas (es de donde salen las categorias) y declara para que frame se
    # calibro. Los fps son otra cosa: solo se usan para el aviso de stride, que
    # es informativo, y por eso si aceptan venir de un resumen que puede faltar.
    resumen = Resumen()
    inicio = time.perf_counter()
    escritos = write_events(
        rutas.output_path,
        _procesar(rutas.input_path, categorias, zonas.frame_width,
                  zonas.frame_height, resumen),
    )
    transcurrido = time.perf_counter() - inicio

    ruta_resumen = pipeline.summary_path("interact", cfg)
    _escribir_resumen(ruta_resumen, cfg, ruta_zonas, info_video, resumen, transcurrido)

    _imprimir_resultado(resumen, escritos, transcurrido, rutas.output_path, ruta_resumen)
    return 0


def _leer_info_de_video_desde_zones(cfg: Config) -> dict:
    """Copia `width`/`height`/`fps` del resumen de `zones`, para que `verify`
    tambien pueda comprobar `bbox_en_frame` y `timestamps` sobre esta salida.
    Mismo patron que usa `zones.py` con el resumen de `track`."""
    ruta = pipeline.summary_path("zones", cfg)
    if not ruta.exists():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return datos.get("video", {})


def _escribir_resumen(
    destino: Path, cfg: Config, ruta_zonas: Path, info_video: dict,
    resumen: Resumen, transcurrido: float,
) -> None:
    """Guarda las metricas de la corrida. Sin esto no se puede comparar nada."""
    datos = {
        "contract_version": CONTRACT_VERSION,
        "stage": "interact",
        "video_id": cfg.video_id,
        "video": info_video,
        "params": {
            "archivo_de_zonas": str(ruta_zonas),
            "frame_stride": cfg.frame_stride,
            "umbral_razon_aspecto": UMBRAL_RAZON_ASPECTO,
            "ventana_mediana_s": VENTANA_MEDIANA_S,
            "duracion_minima_s": DURACION_MINIMA_S,
            "umbral_pies_quietos_alturas_s": UMBRAL_PIES_QUIETOS_ALTURAS_S,
            "refractario_s": REFRACTARIO_S,
            "latencia_s": LATENCIA_S,
            "umbral_se_detiene_s": UMBRAL_SE_DETIENE_S,
            "umbrales_validados_contra_groundtruth": False,
        },
        "results": {
            "eventos_procesados": resumen.eventos_procesados,
            "eventos_emitidos": resumen.eventos_emitidos,
            "approach": resumen.approach,
            "pick_up": resumen.pick_up,
            "put_back": resumen.put_back,
            "episodios_candidatos": resumen.episodios_candidatos,
            "descartados_por_borde": resumen.descartados_por_borde,
            "descartados_por_duracion": resumen.descartados_por_duracion,
            "descartados_por_pies": resumen.descartados_por_pies,
            "descartados_por_sin_zona": resumen.descartados_por_sin_zona,
            "descartados_por_refractario": resumen.descartados_por_refractario,
            "approach_candidatos": resumen.approach_candidatos,
            "approach_descartados_por_refractario":
                resumen.approach_descartados_por_refractario,
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
) -> None:
    """El embudo completo, no solo el resultado: hay que poder ver en que
    filtro se pierde la senal."""
    print()
    print("-" * 66)
    print(f"  Eventos procesados     {resumen.eventos_procesados}")
    print(f"  Eventos de interaccion {resumen.eventos_emitidos}")
    print(f"      APPROACH           {resumen.approach}")
    print(f"      PICK_UP            {resumen.pick_up}")
    print(f"      PUT_BACK           {resumen.put_back}")
    print()
    print(f"  Episodios candidatos   {resumen.episodios_candidatos}")
    print(f"      tocaba el borde       {resumen.descartados_por_borde}")
    print(f"      duracion insuficiente {resumen.descartados_por_duracion}")
    print(f"      pies no quietos       {resumen.descartados_por_pies}")
    print(f"      fuera de toda zona    {resumen.descartados_por_sin_zona}")
    print(f"      en refractario        {resumen.descartados_por_refractario}")
    print(f"      -> alcances emitidos  {resumen.pick_up + resumen.put_back}")
    print()
    print(f"  Visitas que se detienen  {resumen.approach_candidatos}")
    print(f"      en refractario        {resumen.approach_descartados_por_refractario}")
    print(f"      -> APPROACH emitidos  {resumen.approach}")
    print(f"  Tiempo                 {transcurrido:.2f} s")
    print("-" * 66)
    print(f"  Eventos   {jsonl}  ({escritos} lineas)")
    print(f"  Resumen   {ruta_resumen}")
    print()
    print("  PICK_UP y PUT_BACK salen de una CONVENCION de emparejamiento, no")
    print("  de ver que hay en la mano: la tasa de rechazo que se calcule con")
    print("  ellos es una estimacion. Ver etiqueta_de_alcance().")
    print()
    print("  Siguiente etapa:  python -m gondola metrics   (Persona 6)")
