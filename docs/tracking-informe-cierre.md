# Informe de cierre — Persona 3 (Seguimiento)

Rama `feature/tracking`, 5 commits. Todos los números de este documento salen
de correr el código tal como quedó commiteado, no de memoria.

---

## 1. Qué construí

| Archivo | Estado | Líneas |
|---|---|---|
| `ai-service/gondola/stages/track.py` | nuevo | 678 |
| `ai-service/tests/unit/test_track.py` | nuevo | 620 |
| `ai-service/gondola/cli.py` | modificado | +18 |
| `ai-service/gondola/video/render.py` | modificado | +39 / −10 |
| `ai-service/tests/unit/test_cli.py` | modificado | +22 / −9 |

**Total: 1377 líneas insertadas, 19 eliminadas, en 5 archivos.** No toqué
`contract.py`, `pipeline.py` ni `config.py` — cero cambios al contrato.

Commits, en orden:

1. `18564c6` — módulo `track.py` base: predicción por velocidad, emparejamiento
   por IoU, `MAX_AGE_S=0.6s`. Engancha `track` en la CLI.
2. `27a1430` — video anotado propio (`--render`, reutilizando
   `gondola/video/render.py`), conteo de cruces sospechosos, propagación de
   dimensiones/fps del resumen de `detect` hacia el de `track`.
3. `4a7e46d` — opciones `--render` y `--open` en la CLI, con el mismo nombre
   y comportamiento que en `detect`.
4. `ea6497a` — coste de asociación con coherencia de movimiento.
5. `f3ab88c` — amortiguación de la velocidad con el tiempo perdido.

---

## 2. El algoritmo que quedó

Lee `<video>.detect.jsonl` (una caja por persona y por frame, `track_id` en
`null`) y escribe `<video>.track.jsonl`: los mismos eventos, con `track_id`
relleno. No toca ningún otro campo — verificado con un test dedicado
(`test_track_no_toca_los_campos_de_otras_personas`).

Por cada frame, en orden:

1. **Predicción.** Cada track activo guarda su última caja, cuándo se vio
   (`timestamp`) y su velocidad (px/s, de las dos últimas posiciones). Se
   predice dónde debería estar ahora extrapolando esa velocidad — pero
   **amortiguada** según cuánto lleva sin verse: la velocidad efectiva decae
   en línea recta hasta 0 según el track se acerca a `MAX_AGE_S` sin
   encontrar nada, así que la predicción converge hacia la última posición
   conocida en vez de alejarse sin límite.
2. **Emparejamiento.** Se calcula el IoU (intersección sobre unión) entre
   cada predicción y cada caja del frame. Un candidato es válido si su IoU
   pasa `IOU_MINIMO_PARA_EMPAREJAR`. Entre candidatos cuyo IoU cae en el
   mismo "escalón" (`NIVEL_IOU_PARA_DESEMPATE`), se desempata por
   **coherencia de movimiento**: se prefiere el candidato cuya posición,
   respecto a la predicción, continúa el rumbo que el track ya traía, sobre
   el que implicaría una reversa de 180° en un solo frame. La asignación es
   voraz: se ordenan todos los pares posibles por (escalón, coherencia) y se
   van tomando de mayor a menor sin repetir track ni detección.
3. **Memoria.** Un track sin emparejar no muere de inmediato: sigue vivo
   hasta `MAX_AGE_S` segundos reales sin verse (medido con `timestamp`,
   nunca con `frame` — ver sección 3). Si nadie lo reclama a tiempo, se
   purga. Las detecciones sin track se convierten en tracks nuevos,
   numerados de forma secuencial desde 1, nunca reutilizados.

**Parámetros finales** (constantes en `track.py`):

| Parámetro | Valor | Qué hace |
|---|---|---|
| `IOU_MINIMO_PARA_EMPAREJAR` | 0.3 | Umbral mínimo de solape para considerar un candidato. |
| `MAX_AGE_S` | 2.0 s | Cuánto tiempo real puede pasar un track sin verse antes de darse por perdido. |
| `NIVEL_IOU_PARA_DESEMPATE` | 0.1 | Ancho del "empate" de IoU dentro del cual decide la coherencia de movimiento. |
| `VELOCIDAD_MINIMA_PARA_COHERENCIA` | 20.0 px/s | Por debajo de esto, un track no tiene rumbo confiable: la coherencia queda neutra. |
| `EVENTOS_ENTRE_AVISOS` | 2000 | Solo para el mensaje de progreso en consola; no afecta el resultado. |

Además: `contar_cruces_sospechosos` cuenta, por frame, pares de tracks cuyo
emparejamiento se pudo haber intercambiado sin violar el umbral de IoU — una
cota superior de ID switches reales, no una certeza (no hay groundtruth
todavía). Y `run()` puede generar su propio video anotado (`--render
privacy|debug|none`, `--open`), reutilizando el `Renderer` de `detect` con un
color estable por `track_id` (`color_desde_id`, función determinista del
número, sin apariencia ni tabla guardada).

---

## 3. El recorrido de decisiones

### Elección del algoritmo (antes de escribir código, Fase 1)

Se evaluaron ByteTrack completo, Kalman, IoU voraz y Húngaro. Se decidió: IoU
voraz + predicción por velocidad, sin apariencia (privacidad) y sin
dependencias nuevas (ni `scipy` para Húngaro, ni `numpy`/`filterpy` para
Kalman) — documentado en el docstring del módulo.

### Reducir ID switches en cruces (pedido explícito)

Se investigaron 4 opciones: Kalman, coste con coherencia de movimiento,
Húngaro, y congelar la predicción en oclusión detectada. Se implementó
**solo la 2** (coherencia de movimiento): mejor relación costo/beneficio,
cero dependencias nuevas. Las otras 3 quedaron como análisis, no como código.

**Primer intento, descartado:** multiplicar `iou * coherencia` directo.
Probado contra `video_003.mp4` (video real, 5.6 personas/frame en promedio):
un IoU excelente (0.99, una persona casi quieta) perdió contra uno mediocre
(0.32) solo porque la caja de YOLO tembló un poco en la altura de un frame a
otro. Se corrigió con un escalón (`NIVEL_IOU_PARA_DESEMPATE`): la coherencia
ahora solo desempata candidatos con IoU ya parecido, nunca supera una
diferencia grande.

**Verificación del empate real:** se construyó un caso sintético donde las
predicciones de dos tracks con velocidades exactamente simétricas coinciden
en la MISMA caja (empate de IoU real, no redondeo). Con la lógica vieja
(coherencia forzada a neutra vía monkeypatch, para simular el código previo
al arreglo), el resultado cambiaba según el orden en que llegaban las cajas
del frame. Con la lógica actual, no — verificado en
`test_sin_coherencia_el_empate_simetrico_depende_del_orden_de_llegada` y
`test_dos_personas_con_velocidades_simetricas_el_iou_solo_empata`.

### Oclusión real (reportada después: no cruces, alguien tapado por otra persona)

**Paso barato primero:** antes de tocar el algoritmo, se corrió `track` sobre
`video_003.mp4` con `MAX_AGE_S` en 0.6, 1.5, 1.7, 2.5 y 4.0 segundos, sin
cambiar nada más. El punto exacto de recuperación de un caso real (una
persona ocluida) está entre 1.5s y 1.7s — el hueco real medido fue 1.53s.
`tracks_creados` bajó de 33 a 32 en ese punto. Riesgo identificado: nada le
exige más a un track que lleva mucho tiempo perdido; uno de 0.1s y uno de
1.9s compiten en igualdad de condiciones por la siguiente detección.

**Segundo intento, implementado y luego eliminado:** un umbral de IoU
creciente con el tiempo perdido (`umbral_efectivo`, tope 0.75). Con datos
reales:

| | Sin nada | Umbral creciente |
|---|---|---|
| Rango de `tracks_creados` (5 valores de `MAX_AGE_S`) | 32–33 | 33–40, **no monótono** |
| ¿Recupera el caso real? | Sí (con `MAX_AGE_S≥1.7`) | **No** (IoU logrado 0.358 < umbral exigido 0.645 en ese punto) |

Se eliminó por completo: la función `umbral_efectivo`, la constante
`UMBRAL_IOU_MAXIMO_POR_ANTIGUEDAD` y sus 5 tests. Motivo: compartía la misma
referencia (`MAX_AGE_S`) que la ventana de espera, así que tocar un número
movía dos comportamientos a la vez de forma difícil de predecir — y ni así
resolvía el caso que lo motivó.

**Lo que se quedó:** amortiguar la velocidad con el tiempo perdido
(`predecir_bbox`). Diagnóstico: una velocidad estimada con solo dos frames
(potencialmente ruidosa) extrapolada 1.5+ segundos en línea recta aleja la
predicción de donde la persona en realidad seguía. Medido en el caso real: el
IoU de recuperación subió de 0.358 (sin amortiguar) a 0.504 (amortiguado).
Repetido el barrido de los 5 valores de `MAX_AGE_S`:

| | Sin nada | Umbral creciente | **Amortiguación (final)** |
|---|---|---|---|
| Rango de `tracks_creados` | 32–33 | 33–40, no monótono | **29–33** |
| ¿Recupera el caso real? | Sí | No | **Sí, con más margen** |

La amortiguación sola resultó más estable que las otras dos versiones,
incluida la que no tenía ninguna mejora. Confirmado visualmente: en el video
anotado (`video_003.track.debug.mp4`), el `track_id 11` es la misma persona
antes (frame 41) y después (frame 87) de quedar 1.53s tapada por otra
persona caminando enfrente.

### Límite de escala (encontrado, no buscado)

Verificando el caso concreto se encontró que, aunque la posición se prediga
perfecto, un cambio de tamaño de caja grande entre el antes y el después de
la oclusión limita el IoU máximo posible. Medido: la persona del caso real
reapareció con una caja **62% más alta** (256px → 416px); el techo teórico
de IoU con la posición perfectamente centrada fue **0.528**, no 1.0. Ni subir
ni bajar el umbral lo arregla — ver sección 5.

---

## 4. Resultados medidos sobre video real

Video: `data/videos/video_003.mp4` — 3840×2160, 30 fps, 300 frames (10
segundos), video real (no sintético). Es una escena de calle comercial
concurrida, no específicamente un pasillo de góndola, pero sirvió para medir
con densidad real de gente (5.60 personas/frame en promedio).

Parámetros de la corrida: `CONFIDENCE_THRESHOLD=0.5`, `IOU_THRESHOLD`
(YOLO)`=0.45`, modelo `yolo11n.pt`, `device=cpu`; en `track`:
`IOU_MINIMO_PARA_EMPAREJAR=0.3`, `MAX_AGE_S=2.0`,
`NIVEL_IOU_PARA_DESEMPATE=0.1`, `VELOCIDAD_MINIMA_PARA_COHERENCIA=20.0`.

| Etapa | Resultado |
|---|---|
| `detect` | 1679 detecciones en 300 frames (promedio 5.60/frame) |
| `track` | 1679 eventos procesados, **29** tracks creados, **1650** emparejamientos, **10** tracks activos al cierre, **0** cruces sospechosos |
| `verify` | **PASA**, las 11 reglas del contrato, sobre las 1679 líneas de `video_003.track.jsonl` |

`track` corrió en 0.07s (~25.700 eventos/s) sobre este archivo — la parte
lenta del pipeline es `detect` (YOLO), no esto.

También se corrió una primera prueba de humo sobre `video_001.mp4` (300
frames reales, pero con muy poca gente, ~0.13 personas/frame) al principio
de la Fase 3: 40 detecciones, 2 tracks, `verify` pasando. **No volví a
correr esa prueba con el código final** — los archivos de esa corrida se
sobrescribieron durante las pruebas posteriores, así que esos números
concretos no están re-confirmados con la versión que queda commiteada. Todo
lo demás en este informe sí corrió contra el código final.

---

## 5. Limitaciones — sin suavizar

- **Límite de escala, medido:** una oclusión que además viene con un cambio
  de tamaño de caja grande (persona que se acerca o aleja de la cámara
  mientras está tapada) puede no recuperar su id aunque la posición se
  prediga perfecto. Medido: 62% de cambio de altura → techo de IoU 0.528. Ni
  subir ni bajar `IOU_MINIMO_PARA_EMPAREJAR` lo arregla — solo cambia a
  quién más se le acepta un emparejamiento dudoso. Lo único que de verdad lo
  resolvería es comparar el contenido de las cajas (re-identificación por
  apariencia), prohibido por la Ley 1581 y el contrato de privacidad del
  proyecto. Se deja documentado como límite conocido, no se persigue con más
  parámetros.
- **`id_switches_sospechosos` es una cota, no una medición validada.** En
  las pruebas sobre `video_003.mp4` dio 0 en todos los barridos — no puedo
  afirmar que eso signifique "cero switches reales": significa que, bajo la
  definición de la heurística (ambas asignaciones cruzadas por encima del
  umbral), ninguno de los casos observados calificó. Sin groundtruth con
  identidad estable por persona, no hay forma de confirmar cuántos switches
  reales hay.
- **El emparejamiento es voraz, no óptimo matemáticamente** (no se
  implementó el algoritmo Húngaro). Con 3 o más personas muy cercanas a la
  vez podría ser subóptimo. No medí cuánto importa esto en la práctica: en
  `video_003.mp4` hay momentos con varias personas simultáneas y no se
  detectó ningún caso problemático, pero no investigué esto a fondo.
- **Todos los números de las secciones 3 y 4 salen de UN video de 10
  segundos.** No hay groundtruth anotado (una persona viendo el video y
  marcando qué pasó de verdad), así que ningún porcentaje de acierto real
  (tasa de ID switches por hora, tasa de recuperación de oclusiones) se
  puede publicar todavía — es la misma regla que ya rige para `detect` en
  `docs/evaluation.md`.
- **Oclusión casi total con movimiento parecido:** sin apariencia, dos
  personas que se mueven muy parecido durante una oclusión casi total no
  siempre se pueden desambiguar. Es un límite estructural de la privacidad
  por diseño del proyecto, no un bug.

---

## 6. Pendiente de acuerdo de equipo — no construido

- **Extensión del CSV de groundtruth con identidad estable por persona**,
  para medir ID switches reales (no solo la cota heurística). Propuesta en
  la Fase 1 de diseño; toca `evaluate/` y el formato de anotación, que son
  de todo el equipo — no lo construí sin acuerdo.
- **Opciones 1 (Kalman), 3 (Húngaro) y 4 (congelar en oclusión detectada)**
  para reducir ID switches: quedaron como investigación documentada (ver
  conversación de diseño), no como código. Tampoco se implementó el umbral
  de IoU creciente — se probó y se descartó (sección 3).
- **Bajar `CONFIDENCE_THRESHOLD` en `detect.py`** para exponer detecciones de
  baja confianza a `track` (permitiendo un segundo intento de emparejamiento
  tipo ByteTrack): identificado en la Fase 1 como posible mejora, pero cruza
  a la etapa de la Persona 2 — no se tocó.
- `zones`, `interact`, `metrics` siguen siendo placeholders (Personas 4, 5 y
  6): fuera de mi alcance.
