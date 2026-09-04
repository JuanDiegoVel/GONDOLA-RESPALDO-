# Lo que necesitas saber de `track` antes de escribir `zones`

De Persona 3 para Persona 4. Todo lo de aquí sale de `ai-service/gondola/stages/track.py`
y de sus tests — si algo no cuadra con lo que ves en el código, confía en el
código, no en esto.

---

## Qué archivo lees y qué garantías tiene

Nunca escribas el nombre a mano. Pídelo así, igual que hace `track` con el
suyo:

```python
rutas = pipeline.stage_paths("zones", cfg)
pipeline.require_input("zones", cfg)
# rutas.input_path -> <video_id>.track.jsonl
```

Garantías sobre ese archivo:

- Cada línea es un `Event` válido — ya pasó por `Event.from_jsonl()`, que
  valida contra el contrato. Si una línea estuviera corrupta, `read_events()`
  falla al leerla con el número de línea exacto; tú nunca la ves a medias.
- **Todo evento tiene `track_id` relleno, como entero.** Nunca vas a
  encontrar un `null` en ese campo dentro de `<video>.track.jsonl`. `track`
  le asigna un id a cada detección que le entra, matched o nueva — no hay
  ningún camino en el código donde un evento salga sin él (verificado en
  `test_track_no_toca_los_campos_de_otras_personas` y en todos los tests de
  `run()`).
- El orden se preserva: mismo orden de frame que traía `<video>.detect.jsonl`,
  eventos del mismo frame consecutivos.

## Qué viene relleno y qué sigue en `null`

| Campo | Estado | De quién |
|---|---|---|
| `track_id` | **relleno, siempre entero** | ya hecho, es lo mío |
| `detection` (clase, confianza, bbox) | igual que te la dio Persona 2 | Persona 2, `track` no la toca |
| `zone.zone_id`, `zone.segment` | `null` | **tuyo** |
| `metrics.dwell_time` | `null` | **tuyo** |
| `interaction.event`, `interaction.product_zone` | `null` | Persona 5 |

Rellena solo `zone` y `metrics.dwell_time`. El verificador falla si tocas algo
más (`python -m gondola verify <tu_archivo>` te lo dice exacto).

## Qué significa `track_id` en la práctica — y qué NO puedes asumir

Del contrato (`docs/data-contract.md`): *"`track_id` es un número temporal y
sin significado: solo dice 'esta caja y aquella son la misma silueta dentro
de este video'. Se reinicia con cada video y no corresponde a ninguna persona
real."*

Lo que eso significa para tu cálculo de permanencia: **`track_id` es una
apuesta geométrica, no una certeza de identidad.** Concretamente:

- **Una persona real puede recibir más de un `track_id` en el mismo video**
  si estuvo oculta el tiempo suficiente (`MAX_AGE_S=2.0` segundos hoy) detrás
  de otra persona, o si al reaparecer su caja cambió mucho de tamaño (medido:
  un cambio de 62% en la altura ya puede romper la recuperación, sin importar
  qué tan bien se prediga la posición — ver el docstring de `predecir_bbox`
  en `track.py` si quieres el detalle).
- **Consecuencia directa para `dwell_time`:** el contrato dice que
  `dwell_time` son *"segundos acumulados que ESE `track_id`"* lleva en una
  zona. Si el `track_id` cambia a mitad de una permanencia real — alguien
  parado frente a una góndola, otro cliente pasa por delante y lo tapa 2+
  segundos — tu acumulador se corta ahí y arranca de cero con el id nuevo,
  **aunque la persona real nunca se movió**. Esto subestima sistemáticamente
  el `dwell_time` en escenas concurridas. No hay ningún campo en el contrato
  que te diga "este `track_id` es continuación de aquel" — no puedes
  detectarlo desde tu propia etapa con la información que tienes hoy.
- **No sé cuántas veces pasa esto en la práctica.** Lo medí UNA vez, a
  propósito, en un caso real (persona ocluida 1.53s en `video_003.mp4`, ver
  `docs/tracking-informe-cierre.md`) y en ese caso puntual SÍ recuperó su id
  correctamente. No tengo groundtruth con identidad estable por persona para
  contar cuántas fragmentaciones de este tipo hay en total — así que no
  asumas que es raro, pero tampoco que es constante: no está medido.
- `id_switches_sospechosos` (en `<video>.track.summary.json`) es una cota
  superior heurística de posibles intercambios de identidad, no una tasa de
  acierto. No la uses como si midiera qué tan bien funciona tu etapa.

## La trampa del `FRAME_STRIDE`

`detect` puede correr con `FRAME_STRIDE > 1` (procesa 1 de cada N frames). Si
tu código de permanencia contara EVENTOS o FRAMES para saber cuánto tiempo
pasó, el mismo tiempo real cambiaría de tamaño según con qué stride corrió
`detect` — sin que nada te avise. Por eso todo en `track.py` usa
`evento.timestamp` (segundos reales, ya calculados por Persona 2) para
cualquier cosa relacionada con tiempo transcurrido, y `evento.frame` **solo**
para saber qué detecciones son del mismo instante.

A mí me lo señalaron antes de escribir la primera línea de la lógica de
emparejamiento — mi primer plan iba a medir la ventana de espera contando
frames del archivo, y me lo corrigieron antes de implementar. Quedó un test
que prueba justo esto — `test_el_resultado_no_depende_del_frame_stride` en
`tests/unit/test_track.py`: dos secuencias con los mismos `timestamp` pero
números de `frame` distintos (una "consecutiva", otra como si viniera de
`--stride 5`) dan exactamente el mismo resultado. Si vas a acumular
`dwell_time`, hazlo con diferencias de `timestamp`, nunca contando cuántos
eventos llevas en una zona.

## Convenciones del proyecto que me hubiera ahorrado tiempo saber antes

- **Rutas, siempre desde `pipeline`:** `pipeline.stage_paths("zones", cfg)` y
  `pipeline.require_input("zones", cfg)`. Nunca construyas
  `f"{video_id}.zones.jsonl"` a mano.
- **Streaming, siempre:** `read_events()` y `write_events()` procesan de a un
  evento. Nunca cargues el archivo completo en una lista ni uses `open()` a
  pelo — un video de 10 minutos puede dar decenas de miles de eventos.
- **Importa lo pesado dentro de la función**, no arriba del archivo. `track.py`
  no necesita nada pesado casi nunca (solo aritmética), pero SI tu etapa usa
  OpenCV para algo (o cualquier librería no listada en
  `requirements-dev.txt`), el import va dentro de la función que lo usa, para
  que los demás sigan corriendo `pytest` sin instalarlo.
- **El resumen JSON de tu etapa (`<video>.zones.summary.json`) es donde
  `verify` busca el tamaño del frame y los fps** para comprobar `bbox_en_frame`
  y `timestamps`. Si no lo propagas desde el resumen de la etapa anterior,
  `verify` omite esas reglas para tu salida EN SILENCIO — no falla, solo dice
  "no se pudo comprobar". A mí me pasó: tuve que agregar
  `_leer_info_de_video_desde_detect()` en `track.py` para copiar el campo
  `"video"` del resumen de `detect` al mío. Copia ese patrón.
- **`test_cli.py` tiene una lista `ETAPAS_PENDIENTES`** que hay que sacar tu
  etapa de ahí cuando la implementes, si no los tests de "placeholder" de las
  demás etapas se confunden con la tuya (ver el commit `18564c6` en la rama
  `feature/tracking` para ver exactamente qué cambié en `test_cli.py`).
- **Enganchar tu comando en `cli.py`:** una rama `if nombre == "zones":` dentro
  de `comando_etapa()` que llama a tu `run(cfg)`. Si tu etapa también genera
  video (probablemente no, pero por si acaso), copia el patrón de
  `_opciones_de_track()` para que `--render`/`--open` se llamen igual en
  todas las etapas — Persona 1 lo pidió así para que las etapas futuras usen
  la misma interfaz.
- **Antes de decir que terminaste:** `pytest` en verde y
  `python -m gondola verify data/output/<tu_archivo>` pasando. El
  verificador es tu prueba real de que cumples el contrato y la privacidad;
  no hay revisión manual de código que lo reemplace.

## Trampas que no están documentadas en ningún otro sitio

- **No hay ninguna señal en el contrato de que un `track_id` "es nuevo por
  oclusión" vs "es una persona que de verdad acaba de entrar".** Si algún día
  quieres estimar cuánta gente entró de verdad (para otra métrica), no puedes
  distinguirlo desde `zones` con lo que hay hoy.
- **`bbox.width` y `bbox.height` cambian entre frames para la MISMA persona
  real** (distancia a la cámara, pose) — no asumas continuidad de tamaño de
  caja entre frames, ni siquiera dentro del mismo `track_id`.
- **`support_point` es una propiedad calculada (`bbox.support_point` en
  Python), no un campo del JSON.** No la busques en el archivo; hay que
  llamarla sobre el `BBox` ya cargado.
- **El video anotado de `track` (`--render`) no agrega ningún campo al
  `.jsonl`.** Es solo para que un humano compruebe visualmente que el
  seguimiento se ve bien. No dependas de él ni lo generes como parte de tu
  flujo — es opcional y puede no existir.
