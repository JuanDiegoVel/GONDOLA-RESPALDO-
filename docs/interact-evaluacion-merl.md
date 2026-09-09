# Evaluación de interact.py contra el MERL Shopping Dataset

> Ver primero [`docs/evaluation.md`](evaluation.md): esto usa el mismo
> evaluador (`gondola/evaluate/evaluator.py`), pero con groundtruth de
> terceros en vez de anotación propia. Se documenta aparte porque el CSV no
> vive en `data/groundtruth/` (ver sección 4) y la comparación necesita un
> ajuste que merece explicación.

## 1. Qué es esto y de dónde salió

`interact.py` nació sin ninguna cifra de precisión/recall real: no había
video anotado (ver `docs/evaluation.md`). Al investigar por qué un video real
subido por el equipo mostraba muy pocos `PICK_UP`/`PUT_BACK`, se encontró que
los 5 clips `video_demo_merl_*` que ya usa este proyecto pertenecen al **MERL
Shopping Dataset** (Mitsubishi Electric Research Labs), un dataset público
que además publica **etiquetas oficiales** por frame: `Reach To Shelf`,
`Retract From Shelf`, `Hand In Shelf`, `Inspect Product`, `Inspect Shelf`
(`https://www.merl.com/research/downloads/MERL_Shopping_Dataset`,
`Labels_MERL_Shopping_Dataset.zip`, 64 KB, formato `.mat`).

Eso es groundtruth real, hecho por terceros, para exactamente los 5 videos
que este proyecto ya tenía. Se aprovechó para responder dos preguntas con
datos en vez de intuición:

1. ¿La ventana de la mediana móvil (`VENTANA_MEDIANA_S`) de verdad estaba
   cortando gestos reales? (Sí — ver el docstring de la constante en
   `gondola/stages/interact.py`, sección "EL TECHO DEL METODO".)
2. Con la ventana ya corregida, ¿ajustar `UMBRAL_RAZON_ASPECTO` mejora las
   cosas de verdad, o solo cambia el ruido de lugar?

## 2. Por qué se fusionan PICK_UP y PUT_BACK para evaluar

El groundtruth de MERL no dice si la persona **se llevó** el producto o lo
**devolvió** — solo marca que el brazo entró (`Reach To Shelf`) y salió
(`Retract From Shelf`) del estante. Nuestro `PICK_UP`/`PUT_BACK` sale de una
CONVENCIÓN de paridad dentro de la visita (primer alcance = `PICK_UP`,
segundo = `PUT_BACK`; ver `etiqueta_de_alcance()`), no de ver qué hay en la
mano.

Comparar tipo por tipo contra MERL sería inválido: mediría si acertamos una
etiqueta que MERL ni siquiera anota. Por eso, solo para esta evaluación, se
fusionan `PICK_UP`+`PUT_BACK` detectados bajo una sola etiqueta y se comparan
contra las instancias de `Reach To Shelf` (una fila de groundtruth por
instancia, con el timestamp puesto en el frame final del `Reach`, cuando el
brazo está más extendido — el instante más parecido al "pico" que usa
`pico_del_episodio`). No se suma también el `Retract` emparejado: son las dos
fases del MISMO gesto físico, y sumarlas habría contado cada interacción real
dos veces.

Esto mide **si el sistema nota el gesto y a qué hora**, no si `PICK_UP` vs
`PUT_BACK` es correcto -esa distinción sigue sin poder validarse hasta que
alguien anote a mano, con criterio propio, cuál era cuál-.

## 3. Resultado: primera cifra formal de precisión/recall del proyecto

Con tolerancia de 2,0 s (la misma por defecto de `docs/evaluation.md`),
sobre los 5 videos, 84 instancias de `Reach To Shelf` en total:

| VENTANA_MEDIANA_S | UMBRAL_RAZON_ASPECTO | TP | FP | FN | precision | recall | F1 |
|---|---|---|---|---|---|---|---|
| 1,0 (original)     | 1,12 | ~4  | -  | ~163 | -    | ~0,02 | -     |
| 3,0                 | 1,12 | 17 | 11 | 67 | 0,607 | 0,202 | 0,304 |
| 3,5                 | 1,12 | 20 | 11 | 64 | 0,645 | 0,238 | 0,348 |
| **4,0**             | 1,12 | 26 | 12 | 58 | 0,684 | 0,310 | 0,426 |
| 4,5                 | 1,12 | 23 | 14 | 61 | 0,622 | 0,274 | 0,380 |
| 6,0                 | 1,12 | 26 | 21 | 58 | 0,553 | 0,310 | 0,397 |
| 4,0                 | 1,10 | 28 | 15 | 56 | 0,651 | 0,333 | **0,441** |
| 4,0                 | 1,09 | 29 | 17 | 55 | 0,630 | 0,345 | 0,446 |

Conclusiones:

- **`VENTANA_MEDIANA_S=4,0` es un máximo local claro** en el barrido de
  ventana: 3,0/3,5/4,5/6,0 dan todos peor F1. No es el extremo más ancho
  probado (eso seria "mas es mejor", que no es lo que salio) ni el más
  angosto: es el punto donde más se corresponde con la duración real medida
  de los gestos (ver el docstring de la constante).
- **Bajar `UMBRAL_RAZON_ASPECTO` de 1,12 a 1,10 mejora F1 de forma clara**
  (+0,015, +3 aciertos) por una caída de precisión razonable (0,68 -> 0,65).
- **Seguir bajando de 1,10 a 1,09 ya no vale la pena**: la ganancia (+0,005
  F1) es del tamaño del ruido esperable en una muestra de 84 eventos.
  Perseguirla es sobreajustar a estos 5 clips concretos (ver "Lo que estos
  números NO dicen" en `docs/evaluation.md`). Por eso el valor final es
  **1,10**, no 1,09.

Valores finales en `gondola/stages/interact.py`:
`VENTANA_MEDIANA_S=4,0`, `LATENCIA_S=2,5` (derivado), `UMBRAL_RAZON_ASPECTO=1,10`.

## 4. Por qué el CSV convertido NO vive en `data/groundtruth/`

`data/groundtruth/README.md` es explícito: esa carpeta es "anotaciones hechas
a mano por nosotros". El CSV usado aquí es una CONVERSIÓN automática de
etiquetas de terceros (ver script de conversión, no versionado por depender
de un .zip externo descargado aparte), no trabajo de anotación del equipo.
Mezclarlo ahí confundiría las dos fuentes. Si el equipo quiere poder repetir
esta evaluación desde cero, hace falta:

1. Descargar `Labels_MERL_Shopping_Dataset.zip` desde
   `https://www.merl.com/pub/tmarks/MERL_Shopping_Dataset/`.
2. Leer cada `<video>_label.mat` con `scipy.io.loadmat` (no está en
   `requirements-dev.txt` a propósito -es pesado y solo hace falta para
   esto-, instalar aparte con `pip install scipy`).
3. `tlabs[0][0]` son las instancias de `Reach To Shelf`, como pares
   `[frame_inicio, frame_fin]` a 30 fps.

## 5. Límites de esta cifra (léase antes de citarla al jurado)

- Son 5 videos, 84 eventos. `docs/evaluation.md` ya avisa: "un F1 alto sobre
  30 segundos de video no dice casi nada" -esto es más que eso, pero sigue
  siendo una muestra chica-.
- Mide solo "hubo un alcance aquí", fusionado. La distinción real
  `PICK_UP`/`PUT_BACK` (que es la que alimenta la tasa de rechazo de la
  Persona 6) sigue sin evaluación formal.
- Es groundtruth de otra tienda, otra cámara (cenital), otra iluminación.
  No predice el desempeño en video propio del equipo -para eso sigue
  haciendo falta anotar a mano, como dice `docs/evaluation.md`-.
