# Formato del archivo de zonas

**Version del formato:** 1 · **Codigo:** `ai-service/gondola/zones_config.py`
**Responsable:** Persona 4 (zonas y permanencia)

Este documento describe el archivo que calibra las gondolas y estantes de UNA
camara/tienda concreta. Es la entrada que le falta a la etapa `zones` del
pipeline (`gondola/stages/zones.py`, todavia sin escribir) para poder ubicar a
una persona: sin este archivo no hay donde consultar "que rectangulo es
`gondola_A`".

**Esta fase es solo de formato y calibracion visual.** La logica que compara
`support_point` contra estas zonas y la que acumula `dwell_time` NO estan
implementadas todavia: ver la seccion "Lo que sigue" al final.

---

## 1. Por que existe un archivo aparte (y no va en `.env` ni en el codigo)

Las zonas describen una CAMARA, no el pipeline. Cambian con cada tienda y con
cada instalacion de camara -mover una estanteria no deberia significar tocar
Python-, así que viven en un archivo de datos que cualquiera puede editar.

## 2. Por que JSON y no YAML

YAML admite comentarios, lo cual ayuda a documentar coordenadas a mano. Pero
el proyecto no tiene ninguna dependencia de YAML hoy, y todo lo demas -el
contrato de eventos, los resumenes de cada etapa- ya se valida con Pydantic
sobre JSON. Se prefirio no anadir una libreria nueva para las 8 personas solo
por comentarios que caben igual en el campo `"name"` de cada zona.

## 3. El "punto de apoyo" decide la forma del archivo

Del contrato de datos (`docs/data-contract.md`): a una persona se le ubica por
`support_point`, el centro del borde inferior de su caja -sus pies-, nunca por
el centro de la caja completa. Consecuencia directa para este archivo:

> **El rectangulo de una zona (`floor_zone`) es el AREA DE PISO frente al
> estante -por donde camina y se para la gente-, NO el area donde estan los
> productos en la imagen.**

En la camara de este proyecto (vista cenital/inclinada, ver
`data/zones/video_001.example.json` y su captura de calibracion) los
productos quedan pegados arriba, contra la pared; el piso ocupa el resto del
frame. Si `floor_zone` fuera el rectangulo del producto, ningun
`support_point` caeria nunca dentro: los pies de una persona jamas pisan el
estante.

Esto tambien resuelve una ambiguedad del enunciado del reto ("estante 2 de la
gondola A"): aqui un "estante" (`segment`) es un tramo a lo LARGO de la
gondola -una porcion del pasillo, con su propio espacio de piso enfrente-, no
un nivel vertical (estante de arriba/abajo). Una camara 2D no puede distinguir
niveles verticales desde un punto en el piso; tramos a lo largo de la gondola
si tienen cada uno su propio hueco de piso, y es lo que el reto necesita para
un planograma: que segmento del pasillo genera mas o menos permanencia.

## 4. El formato

```json
{
  "video_id": "video_001",
  "frame_width": 920,
  "frame_height": 680,
  "gondolas": [
    {
      "zone_id": "gondola_A",
      "name": "Estanteria unica (camara cenital)",
      "product_category": null,
      "shelves": [
        {
          "segment": "estante_1",
          "name": "Cereales",
          "product_category": "cereales",
          "floor_zone": {"x": 120, "y": 270, "width": 410, "height": 380}
        },
        {
          "segment": "estante_2",
          "name": "Snacks y pasabocas",
          "product_category": "snacks",
          "floor_zone": {"x": 530, "y": 270, "width": 370, "height": 380}
        }
      ]
    }
  ]
}
```

Ejemplo real (y ejecutable): `data/zones/video_001.example.json`.

### Campos

| Campo | Nivel | Tipo | Que significa |
|---|---|---|---|
| `video_id` | archivo | texto | A que video/camara pertenece esta calibracion. Mismo valor que `VIDEO_ID`. |
| `frame_width`, `frame_height` | archivo | entero > 0 | Tamano del frame para el que se calibraron las coordenadas. Si el video no mide esto, algo se copio de otra camara. |
| `zone_id` | gondola | texto, unico en el archivo | Sale tal cual en `zone.zone_id` del contrato. Ej: `"gondola_A"`. |
| `name` | gondola/estante | texto | Nombre legible, para el dashboard. No sale en el contrato. |
| `product_category` | gondola/estante | texto o `null` | Ej: `"bebidas"`. Si un estante lo omite, no hereda nada automaticamente: es responsabilidad de quien calibra ponerlo explicito en cada nivel donde haga falta. |
| `shelves` | gondola | lista, minimo 1 | Los tramos de esa gondola. |
| `segment` | estante | texto, unico DENTRO de su gondola | Sale tal cual en `zone.segment`. Dos gondolas distintas pueden repetir `"estante_1"` sin chocar: el contrato siempre los acompana de su `zone_id`. |
| `floor_zone` | estante | rectangulo | El area de piso. Ver seccion 3. |
| `floor_zone.x`, `.y` | estante | decimal >= 0 | Esquina superior izquierda, en pixeles. Mismo origen y sentido que `detection.bbox` (0,0 arriba-izquierda, `y` crece hacia abajo). |
| `floor_zone.width`, `.height` | estante | decimal > 0 | Tamano del area, en pixeles. |

### Reglas que el cargador valida (`ZonesConfig`, Pydantic, `extra="forbid"`)

- Al menos una gondola, y cada gondola con al menos un estante.
- `zone_id` unico en todo el archivo.
- `segment` unico dentro de cada gondola.
- Cada `floor_zone` cabe dentro de `frame_width` x `frame_height`.
- Ningun campo fuera de esta lista: un typo de nombre de campo falla al
  cargar, no se ignora en silencio (mismo criterio que el contrato de
  eventos).

Lo que el cargador **no** valida (a proposito, ver seccion 6): que dos
`floor_zone` no se superpongan. Un poco de superposicion en el borde entre dos
segmentos puede ser real (alguien parado justo en la mitad) y decidir que
hacer con eso es parte del algoritmo de asignacion, no del formato.

## 5. Compatibilidad con `backend/database/schema.sql`

La tabla `zones` necesita una fila por gondola (`level='gondola'`,
`parent_id=NULL`) y una fila por estante (`level='shelf'`,
`parent_id=<id de su gondola>`), cada una con su propio `zone_id` **unico**.
Este archivo no repite esa estructura 1:1 a proposito: `segment` en el
contrato es solo una etiqueta de texto (columna `events.segment`, sin FK),
mientras que el `zone_id` de una fila `shelf` en la base de datos si necesita
ser un identificador propio y unico.

**Convencion propuesta para el importador que escriba la Persona 7** (no
implementado, es solo la regla que el formato deja lista para seguir):

- Fila `gondola`: `zone_id = gondola.zone_id` (tal cual del JSON).
- Fila `shelf`: `zone_id = f"{gondola.zone_id}__{shelf.segment}"` (ej.
  `"gondola_A__estante_2"`), `parent_id` = el id de la fila de su gondola,
  `product_category = shelf.product_category` (o el de la gondola, si el
  estante no puso el suyo).

Con esto, `events.zone_id` (la FK) apunta siempre a la fila **gondola**
-es lo unico que tiene el evento (`zone.zone_id`)-, y `events.segment` queda
como el texto plano `"estante_2"`. Para metricas POR ESTANTE (tabla
`metrics`, que exige `zone_id NOT NULL` y lo usa como FK), el importador
necesita cruzar `events.segment` con las filas `shelf` de esa gondola
(join por `parent_id` + nombre/segment) para saber a que fila `shelf` le
suma cada evento. Es una decision de import, no del formato: se documenta
aqui para que quien lo escriba no tenga que releer este archivo dos veces.

## 6. La herramienta de calibracion visual

```
python scripts/draw_zones.py
python scripts/draw_zones.py --zones data/zones/video_001.example.json --frame 500
```

Dibuja todos los `floor_zone` de un archivo sobre un frame real del video
elegido y guarda la imagen (por defecto en
`data/output/<video_id>.zones.png`). Cada estante sale con un color estable
(mismo esquema deterministico -angulo dorado- que usa `track.py` para pintar
`track_id`) y su etiqueta `gondola/estante`.

**Por que hace falta, y no es un lujo:** escribir "el estante 2 va de x=530 a
x=900" a ciegas no dice nada hasta que se ve encima del video real. Con esta
imagen el error de calibracion se ve en dos segundos en vez de aparecer tres
etapas despues como resultados absurdos.

**Contiene imagen real**, a diferencia del render `privacy` del pipeline: es
de uso interno del equipo para calibrar, igual que el render `debug`. No se
comparte fuera del equipo.

`data/zones/video_001.example.json` fue calibrado a ojo, con esta misma
herramienta, contra `data/videos/video_001.mp4` (frame 500, donde una persona
real esta parada frente al segundo tramo). Sirve para desarrollar y probar
`zones.py` desde ya, pero es un primer borrador visual, no una calibracion
verificada tramo por tramo: revisalo con `draw_zones.py` antes de confiar en
el para metricas.

## 7. Lo que sigue (fuera de esta fase)

- `gondola/stages/zones.py`: lee `<video_id>.track.jsonl`, carga este archivo
  con `load_zones_config`, decide en que `floor_zone` cae cada
  `support_point` y acumula `dwell_time`. Sin escribir todavia — ver el
  problema abierto de "pasa de largo vs se detiene" antes de implementarlo.
- Conectar el archivo a la configuracion del pipeline (`ZONES_PATH` en
  `gondola/config.py` y `.env.example`): se deja para cuando exista
  `zones.py`, que es quien realmente lo necesita en tiempo de ejecucion.
- El importador de `zones` hacia PostgreSQL (Persona 7, ver seccion 5).
