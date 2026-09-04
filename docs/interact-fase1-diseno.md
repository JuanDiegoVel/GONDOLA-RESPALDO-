# Etapa `interact`: diseño de fase 1

**Responsable:** Persona 5 (interacción con productos)  
**Estado:** fase de diseño, previa a escribir `ai-service/gondola/stages/interact.py`  
**Entrada:** `<video_id>.zones.jsonl` · **Salida:** `<video_id>.interact.jsonl`  
**Campo que rellena:** `interaction` (`event`, `product_zone`)

Este documento es la decisión de diseño que se lleva al líder antes de implementar. No describe código existente: describe qué se va a construir, con qué evidencia, y qué no va a poder hacer.

---

## 1. Lo que se decide, en corto

| Decisión | Se elige | Estado |
|---|---|---|
| Enfoque de detección | Reglas geométricas sobre la caja, sin pose | Decidida (Persona 5) |
| Rasgo principal | Aspecto (`w/h`) contra la mediana móvil del propio track | Decidida (Persona 5) |
| Cuántos eventos por gesto | **Uno solo**, en el pico del episodio | Decidida — **afecta a la Persona 6** |
| Qué va en `product_zone` | La categoría del estante, no el segmento | **Abierta: líder + Persona 4** |
| Unidades de los umbrales | Alturas de caja, no píxeles | **Abierta: propuesta** |
| Dependencias nuevas | Ninguna | Decidida (Persona 5) |

---

## 2. Lo que se midió antes de opinar

Todo lo que sigue sale de `data/output/video_001.zones.jsonl`, ya producido por las Personas 2, 3 y 4: **3.801 eventos, 16 tracks, 920×680 a 30 fps, 205 segundos** de video real. Sin estos números la comparación de enfoques sería literatura.

| Medición | Valor | Por qué importa |
|---|---|---|
| Caja típica de persona | 205 × 238 px | La cámara está cerca: hay resolución de sobra para ver un brazo |
| Ruido de la caja entre frames consecutivos | 0,5 % mediana · 5–8 % p95 | El piso de ruido contra el que compite cualquier regla |
| Excursión máxima del ancho dentro de un track | +22 % … +43 % | La señal supera el ruido por 4–8×. Existe |
| Episodios ≥ 0,3 s usando **aspecto** (`w/h`) | 12 en todo el video | El mejor de los cuatro rasgos probados |
| Episodios ≥ 0,3 s usando **ancho** | 5 | El ancho solo no basta: no absorbe el cambio de escala |
| Episodios ≥ 0,3 s usando **alto** | 3 | Peor aún |
| … de los 12 de aspecto, con los pies quietos | 3 | La conjunción es brutal. Ver la advertencia de abajo |
| Duración típica de los picos | 0,03 – 0,37 s | Más corto que un gesto real de tomar algo |
| Cajas que tocan el borde del frame | 3,7 % | Ahí el ancho lo recorta el frame, no el cuerpo: hay que excluirlas |
| Velocidad de pies "en reposo" | 21 – 57 px/s | Es sobre todo temblor de YOLO, no caminar: el umbral de "quieto" debe ir por encima |
| `detect` en CPU | 10,6 frames/s | 579 s de cómputo para 205 s de video: 2,8× tiempo real |

Los cuatro rasgos probados fueron ancho, alto, área y aspecto, todos normalizados contra la **mediana móvil del propio track** (ventana ≈ 1 s). Esa normalización es la que absorbe el cambio lento de escala cuando la persona se acerca o se aleja de la cámara, y es lo que hace que el aspecto gane: es el único rasgo que ya es adimensional antes de normalizar.

### La lectura honesta de esos números

La señal existe, pero es delgada. La mayoría de los picos duran menos de 0,2 s, que es **más corto que un gesto real** de tomar algo (estirar, agarrar, retraer ≈ 0,5–1,5 s). Filtrando por duración quedan 12 episodios en todo el video; exigiendo además pies quietos, 3.

No se sabe si eso es porque en `video_001` hubo tres interacciones o porque el método se pierde el resto. **Sin groundtruth no hay forma de saberlo.** Eso también es parte del diseño: hay que anotar antes de creerle a ningún umbral.

### Por qué la caja no puede decir de qué lado salió el brazo

Es un límite estructural, no de calibración. `support_point` está definido en el contrato como `(x + width/2, y + height)`: **la caja es simétrica respecto a los pies por construcción**. De una bounding box solo salen cuatro números, y de ellos solo se derivan posición, tamaño y aspecto. No hay ningún rasgo posible que distinga un brazo saliendo a la izquierda de uno saliendo a la derecha.

---

## 3. Comparación de enfoques

### (a) Reglas geométricas

| A favor | En contra |
|---|---|
| Cero dependencias nuevas; corre en 0,2 s sobre este video | La caja es simétrica respecto a los pies: no se sabe hacia qué lado salió el brazo |
| La etapa sigue siendo una transformación pura de `.jsonl`, sin píxeles | Girarse de perfil a frontal ensancha la caja **exactamente igual** que estirar el brazo |
| La barrera de privacidad es **estructural**, no una promesa de disciplina | La señal es delgada: 12 episodios en 205 s, y no se sabe cuántos son reales |

### (b) Pose estimation

| A favor | En contra |
|---|---|
| La muñeca contra el rectángulo del estante es la señal correcta, no un proxy | Obliga a `interact` a reabrir el video para **decidir**, no solo para dibujar |
| `ultralytics` **ya es dependencia**: no hay paquete nuevo que instalar | Segunda pasada de YOLO en CPU: ~10 min por cada 3,4 min de video |
| `yolo11n-pose.pt` pesa ≈ 6 MB, del mismo orden que el detector de 5,6 MB ya presente | 5 de los 17 puntos COCO son faciales |

En peso de dependencias pose es **casi gratis**, y decir lo contrario sería deshonesto. Lo caro es otra cosa: hoy `track` reabre el video *solo para dibujar*, nunca para decidir, y eso es lo que hace estructuralmente imposible la reidentificación por apariencia (lo dice su propio docstring). Si `interact` necesita píxeles para decidir, esa propiedad se pierde justo en la etapa donde más incómodo es perderla.

### La lectura de privacidad sobre pose

COCO-17 entrega 17 puntos, de los cuales **cinco son faciales**: nariz, dos ojos, dos orejas. La pregunta era si se puede usar el modelo descartándolos.

1. **Descartarlos es trivial y nada se rompe.** El contrato no tiene campo donde ponerlos y `verify` busca subcadenas sobre el `.jsonl`, donde nunca aparecerían. Las tres barreras técnicas del proyecto siguen pasando.
2. **Legalmente tampoco parece ser el problema.** Cinco puntos faciales gruesos no son un *embedding*: no reidentifican a nadie y no se almacenan. Es materialmente distinto del reconocimiento facial.
3. **El problema es de demostrabilidad, y es el eje por el que nos evalúan.** Hoy `docs/privacy.md` afirma *«No se ejecuta ningún modelo de rostros»* y *«No hay un módulo de identidad desactivado ni una función comentada. No existe el concepto.»* Un modelo de pose cuyas salidas faciales se enmascaran es, literalmente, la cosa que ese párrafo dice que no existe.

Ante el jurado, la respuesta pasaría de **«no»** a **«calcula cinco puntos faciales que descartamos»**. Sí se puede hacer bien —un cargador que solo lea los índices 5–16 y un test que lo verifique—, pero exige reescribir ese párrafo de `privacy.md`, y esa reescritura no es una decisión de implementación: es del líder.

### Recomendación: enfoque (a), reglas geométricas

No porque sean más precisas. **Pose es claramente más precisa.** Por tres razones, en orden de peso:

1. **Pose no rescata la métrica que de verdad importa.** Aun con muñecas perfectas, no se puede saber si la mano volvió *con* producto. El límite duro no es el brazo, es el producto. Pagar 10 minutos de CPU y el párrafo de privacidad para mejorar la detección del alcance —sin resolver PICK_UP contra PUT_BACK— es mal negocio.
2. La barrera de privacidad se mantiene estructural en vez de disciplinar.
3. La etapa sigue siendo una transformación pura de `.jsonl`, igual que `zones`.

---

## 4. La decisión que afecta al equipo: un gesto = UN solo evento

Un mismo `track_id` genera cientos de eventos, uno por frame. ¿El `PICK_UP` se marca en uno solo o en varios?

No es una preferencia: está forzado por código que ya existe en el repositorio. En `gondola/evaluate/evaluator.py`, `emparejar()` casa cada anotación humana con **una sola** detección; todo lo que sobra se devuelve como falso positivo. Y la Persona 6 va a contar filas para calcular la tasa de rechazo. Las dos consecuencias apuntan al mismo lado.

| Cómo se marca | Resultado del evaluador | Lo que contaría la Persona 6 |
|---|---|---|
| En 40 frames seguidos | 1 TP + 39 FP → precisión **0,025**, F1 ≈ 0,05 | 40 pick-ups donde hubo uno |
| En el pico del episodio | 1 TP + 0 FP → precisión **1,000** | 1 pick-up |

El mismo gesto físico y las mismas anotaciones. Lo único que cambia es en cuántas líneas del `.jsonl` se escribe.

### Lo que se decide, en concreto

- **`PICK_UP` / `PUT_BACK`** — en el evento del **pico** del episodio (máximo aspecto), desempate por número de frame menor. El pico es más estable que el inicio, que se corre cada vez que se mueve el umbral.
- **`APPROACH`** — uno por visita, en el evento donde `metrics.dwell_time` cruza los 2,0 s de `zones.UMBRAL_SE_DETIENE_S`. Reutiliza el umbral que la Persona 4 ya justificó en vez de inventar un segundo, y coincide con la definición de `docs/evaluation.md`: *«se acerca a la góndola y **se detiene** frente a ella»*. Un `dwell_time` que baja señala una visita nueva.
- **Periodo refractario** de 1,0 s por `track_id` tras emitir un evento. Una caja temblorosa no puede disparar dos veces el mismo gesto. Nota para quien calibre: la tolerancia del evaluador es de 2,0 s, así que dos detecciones separadas por menos de eso nunca podrán ser ambas acierto contra una misma anotación.
- **Todo lo demás** sale con `interaction.event = null`. El archivo conserva los 3.801 eventos íntegros: la Persona 6 necesita `zone` y `dwell_time` de todos, no solo de los que interactuaron. Es lo que ya asume `eventos_detectados()`, que se salta las líneas sin `interaction.event`.

### Consecuencia sobre el streaming

Decidir "esto fue un pico" exige ver frames posteriores, y la mediana móvil necesita media ventana de adelanto. La etapa emitirá con una **latencia fija de ≈ 1 s de video**, manteniendo en memoria solo esa ventana por track activo —no el archivo completo—, y liberando los eventos **en el mismo orden en que llegaron**, porque `verify` comprueba que los números de frame no retrocedan.

---

## 5. Lo que este enfoque NO puede hacer

Ordenado por gravedad. El primero le pega directo a la tesis del módulo.

1. **No distingue `PICK_UP` de `PUT_BACK` físicamente.** Es el mismo gesto: el brazo sale hacia el estante y vuelve. Lo único que cambia es qué hay en la mano, que es justo lo que no se ve. Se trata con una **convención de emparejamiento** —dentro de una visita, el primer alcance es `PICK_UP` y el segundo es `PUT_BACK`— y hay que escribirla como convención, no como medición. Consecuencia directa: **la tasa de rechazo no se mide, se infiere de un supuesto** que el groundtruth tendrá que confirmar o tumbar.
2. **No se sabe qué producto se tomó.** Sin detección de productos, solo se puede decir de qué segmento del estante y de qué categoría salió.
3. **Un giro del cuerpo produce la misma firma que un alcance.** Pasar de perfil a frontal ensancha la caja igual que estirar el brazo. Es el falso positivo dominante y con una bounding box no se puede separar.
4. **Un brazo ocluido no cambia la caja.** Tapado por el propio cuerpo o por otra persona: falso negativo que no deja ninguna huella medible.
5. **Si `track` fragmenta una visita, la convención de emparejamiento se rompe.** Los dos alcances caen en `track_id` distintos, salen dos `PICK_UP` y cero `PUT_BACK`, y la tasa de rechazo se sesga hacia cero. Es la fragilidad que la Persona 4 ya documentó, heredada aquí con peores consecuencias.
6. **Con personas solapadas el rasgo deja de significar nada.** La caja de YOLO se funde o se recorta. En `video_001` hay 0,62 personas por frame y es benigno; en `video_003` había 5,6.
7. **`FRAME_STRIDE` mayor que 3 rompe el método.** Un gesto de 0,3 s son 9 muestras con stride 1 y 1,8 con stride 5. La etapa tiene que comprobarlo al arrancar y avisar, no fallar en silencio.
8. **Ninguna cifra es publicable todavía.** Y aun anotando: con 16 tracks y ~10 interacciones plausibles, un F1 sobre este video tendría barras de error enormes. Hace falta más metraje anotado antes de poner un número en una diapositiva.

---

## 6. Dependencias

**Ninguna nueva.** Solo la librería estándar sobre lo que `zones` ya produce. Nada que instalar para las otras siete personas, nada que añadir a `requirements.txt` ni a `requirements-dev.txt`.

Si el líder eligiera pose pese a la recomendación:

| Concepto | Costo |
|---|---|
| Paquetes nuevos | 0 — `ultralytics` ya está en `requirements.txt` |
| Pesos del modelo | ≈ 6 MB (`yolo11n-pose.pt`) — cifra de la tabla de modelos de Ultralytics, no descargada ni verificada localmente |
| Cómputo | Una pasada de video extra: ~10 min por cada 3,4 min analizados en CPU |
| Documentación | Reescribir el párrafo de `docs/privacy.md` sobre modelos de rostro |

---

## 7. Dos preguntas abiertas para el líder

### 7.1 `product_zone` debería ser la categoría, no el segmento

El brief inicial pedía `"product_zone": "estante_2"`, pero `zone.segment` **ya lleva** `"estante_2"`: duplicarlo gasta el único campo que puede cargar significado comercial, y deja a la Persona 6 sin forma de agregar por categoría entre estantes. El contrato dice `Ej: 'bebidas'` y `zones_config.Shelf` tiene `product_category` exactamente para esto.

**Propuesta:** la cadena `shelf.product_category → gondola.product_category → null`.

**Ojo con una inconsistencia de documentación que hay que cerrar antes:** `docs/zones-format.md` §4 dice que un estante **no** hereda la categoría de su góndola, mientras que el docstring de `zones_config.Shelf` y la convención de importación de la §5 del mismo documento **sí** asumen herencia. Hay que decidirlo con la Persona 4 y dejar los tres sitios de acuerdo.

### 7.2 Los umbrales van en alturas de caja, no en píxeles

«Pies quietos por debajo de 40 px/s» no transfiere a otra cámara ni a otra resolución; «por debajo de 0,3 alturas de caja por segundo» sí. Es el mismo espíritu por el que `track.py` mide en segundos y no en frames, y por el que `zones.clasifica_visita` recibe su umbral como parámetro en vez de fijarlo.

Con la caja típica de 238 px de este video, 0,3 alturas/s son unos 71 px/s. Se anota el número concreto para que quien recalibre sepa de dónde salió el valor inicial.

---

## 8. Qué haría falta para poder afirmar algo

Nada de lo anterior produce una cifra de exactitud, y no debe presentarse como si lo hiciera. Para llegar a un número defendible hacen falta tres cosas, en este orden:

1. **Acordar el criterio de anotación antes de anotar.** Sobre todo qué cuenta como `APPROACH` y qué se hace cuando alguien alcanza el estante dos veces seguidas. Dos personas anotando con criterios distintos producen un groundtruth inservible, y la convención de emparejamiento de la sección 5 depende justo de ese criterio.
2. **Anotar metraje de verdad** en `data/groundtruth/video_001.csv`. Cinco minutos bien anotados valen más que treinta mal anotados.
3. **Recalibrar los umbrales contra esas anotaciones**, no contra la intuición. Los valores propuestos aquí (0,3 s de duración mínima, 1,12 de razón de aspecto, 1,0 s de refractario, 0,3 alturas/s de pies quietos) son puntos de partida razonados a partir del ruido medido, **no valores validados**.

Hasta entonces, lo único afirmable es lo de la sección 2: qué tan grande es la señal comparada con el ruido, y cuántos episodios sobreviven a cada filtro.