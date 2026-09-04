# Evaluación: cómo medimos si el sistema acierta

> **Lo más importante de este documento:** hoy **no tenemos anotaciones**, así
> que **no podemos afirmar ninguna cifra de exactitud**. El formato, el lector
> y el cálculo están hechos y probados. Lo que falta es el trabajo humano de
> ver el video y anotarlo.
>
> Publicar un "94% de precisión" sin haber anotado video real sería
> inventárselo. Esa cifra no existe hasta que alguien se siente a anotar.

---

## 1. Por qué hace falta anotar a mano

El sistema puede correr perfectamente y equivocarse en todo. La única forma de
saber si acierta es comparar lo que dice contra lo que de verdad pasa en el
video, y lo que de verdad pasa solo lo sabe una persona que lo mire.

A esa lista de "lo que de verdad pasa" se le llama **ground truth** (verdad de
referencia). Es un archivo CSV que se llena viendo el video.

---

## 2. El formato

Un CSV con **cuatro columnas**. Se abre con Excel, Google Sheets o el Bloc de
notas.

```csv
video_id,timestamp,zone_id,event
video_001,12.5,gondola_A,APPROACH
video_001,14.0,gondola_A,PICK_UP
video_001,35.1,gondola_A,PUT_BACK
```

| Columna | Qué se escribe |
|---|---|
| `video_id` | La etiqueta del video, la misma de `VIDEO_ID` en el `.env`. |
| `timestamp` | El **segundo** en que ocurre, con decimales. `12.5` = doce segundos y medio. |
| `zone_id` | Qué góndola. Usa siempre los mismos nombres: `gondola_A`, `gondola_B`... |
| `event` | Uno de tres: `APPROACH`, `PICK_UP`, `PUT_BACK`. |

Los tres tipos de evento:

- **`APPROACH`** — alguien se acerca a la góndola y se detiene frente a ella.
- **`PICK_UP`** — alguien toma un producto del estante.
- **`PUT_BACK`** — alguien devuelve un producto al estante.

Hay un archivo listo para copiar en [`data/groundtruth/ejemplo.csv`](../data/groundtruth/ejemplo.csv).

---

## 3. Cómo anotar

1. Copia el ejemplo con el nombre del video:
   `data/groundtruth/video_001.csv`
2. Abre el video en cualquier reproductor que muestre el tiempo en segundos
   (VLC lo hace).
3. Cada vez que veas uno de los tres eventos, escribe una fila.
4. **Una fila por evento.** Si dos personas toman productos a la vez, son dos
   filas con el mismo segundo.
5. Guarda como CSV, no como `.xlsx`.

**Consejos que ahorran discusiones después:**

- Ponte de acuerdo con el equipo **antes de empezar** sobre qué cuenta como
  `APPROACH`. ¿Pasar caminando cuenta? ¿Hay que detenerse? Escríbanlo y
  síganlo. Dos personas anotando con criterios distintos producen un ground
  truth inservible.
- Anota **todo** lo que veas en el tramo que elijas, no solo lo fácil. Si
  saltas los casos dudosos, el resultado sale artificialmente bueno.
- Es mejor anotar bien 5 minutos que mal 30.
- Si dudas de un evento, márcalo y decídanlo entre dos personas.

---

## 4. Cómo se compara

```bash
cd ai-service
python -m gondola eval
python -m gondola eval --tolerance 1.5
```

Un evento anotado y uno detectado se consideran **el mismo** si coinciden en
tipo y zona y ocurren dentro de una **tolerancia de tiempo** (2 segundos por
defecto). La tolerancia existe porque nadie anotando a mano acierta al frame
exacto: escribes "sobre el 12" y el sistema dice 12.4.

Cada anotación se empareja con **una sola** detección. Si el sistema reporta
dos veces el mismo evento, una cuenta como acierto y la otra como error: contar
dos veces es un fallo, no un acierto doble.

---

## 5. Qué significan los números

|  | Significado |
|---|---|
| **TP** (verdadero positivo) | El sistema lo detectó y estaba anotado. Acertó. |
| **FP** (falso positivo) | El sistema lo detectó y no estaba. Se lo inventó. |
| **FN** (falso negativo) | Estaba anotado y el sistema no lo vio. Se lo perdió. |

```
precision = TP / (TP + FP)    De lo que el sistema dijo, cuánto era cierto.
recall    = TP / (TP + FN)    De lo que había, cuánto encontró.
F1        = 2·P·R / (P + R)   Media armónica: castiga que una de las dos sea mala.
```

**Por qué las dos, y no una.** Un sistema que no reporta nunca nada tiene
precisión perfecta (nunca se equivoca al hablar) y recall cero (no encuentra
nada). Uno que reporta un evento en cada frame tiene recall casi perfecto y
precisión pésima. El F1 solo sale alto si las dos lo están.

Los resultados se dan **por tipo de evento**, no solo en total. No es lo mismo
fallar en `APPROACH`, que ocurre constantemente, que en `PICK_UP`, que es el
que de verdad importa para decidir un planograma.

---

## 6. Lo que estos números NO dicen

- **Un F1 alto sobre 30 segundos de video no dice casi nada.** La cifra vale lo
  que valga la muestra.
- **Si el ground truth está mal anotado, el número miente** en la dirección que
  sea. No hay forma de detectarlo desde el código.
- **Medir en un video no predice otro.** Otra tienda, otra cámara, otra
  iluminación, otros resultados.
- **Esto mide los eventos de interacción**, no la detección de personas. Que
  `PICK_UP` salga bien no significa que el detector encuentre a todo el mundo.

Cuando reportemos una cifra al jurado, hay que decir **junto a ella** cuántos
minutos se anotaron, quién los anotó y con qué criterio. Un número sin ese
contexto no es un resultado: es una afirmación.
