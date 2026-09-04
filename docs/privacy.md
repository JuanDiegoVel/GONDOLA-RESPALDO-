# Privacidad por diseño

El sistema mide **cómo se mueve la gente** alrededor de las góndolas. No mide
**quién** es esa gente, y está construido para que no pueda hacerlo.

---

## Lo que el sistema NO hace

| No hace | Cómo se garantiza |
|---|---|
| **Reconocimiento facial** | No se ejecuta ningún modelo de rostros. El contrato rechaza cualquier campo facial. |
| **Identificación de personas** | No hay base de datos de personas. `track_id` se reinicia con cada video. |
| **Inferencia de emociones** | No se ejecuta ningún clasificador de expresión. Campo prohibido. |
| **Perfiles biométricos** | No se extrae ni almacena ninguna característica corporal. |
| **Edad, género, etnia** | Campos prohibidos: rompen la validación. |
| **Almacenar imágenes de personas** | La base de datos no guarda fotogramas. |

---

## Las tres barreras técnicas

Esto no es una declaración de intenciones. Está en el código, en tres sitios
independientes:

**1. El contrato rechaza los campos prohibidos.**
Todos los modelos de [`contract.py`](../ai-service/gondola/contract.py) usan
`extra="forbid"`. Añadir un campo `age` o `face_embedding` no es una discusión
de equipo: es un error de validación inmediato, en la máquina de quien lo
intentó, antes de llegar a la integración.

**2. `verify` relee los archivos ya escritos.**
```bash
python -m gondola verify data/output/video_001.detect.jsonl
```
Busca por subcadena cualquier rastro de `age`, `edad`, `gender`, `face`,
`rostro`, `embedding`, `identity`, `emotion`, `biometric`, `documento`,
`telefono`, `foto`... en español y en inglés, en las claves anidadas también.
Si aparece uno, el comando falla con código 1. Existe por si un archivo lo
produjo otra herramienta que no pasó por el contrato.

**3. El render por defecto no contiene ni un píxel real.**
El modo `privacy` dibuja los rectángulos sobre un **fondo neutro generado desde
cero**. No es una versión censurada del video: al renderizador ni siquiera se
le pasa el fotograma original. Ese video se puede proyectar ante un jurado,
adjuntar a un informe o subir a una presentación sin exponer a nadie.

El modo `debug` sí dibuja sobre el video real, lleva la marca
`MODO DEBUG - NO COMPARTIR` y es solo para trabajar.

---

## `track_id` es anónimo

`track_id` es un entero temporal que solo significa *"esta caja y aquella son
la misma silueta dentro de este video"*.

- Se reinicia con cada procesamiento.
- No corresponde a ninguna persona real ni a ningún registro.
- Si alguien sale de cámara y vuelve a entrar, recibe **otro** número — y eso
  está bien: **no queremos** reconocerlo.

Sin `track_id` no se puede medir permanencia, que es el objetivo del proyecto.
Con él, tampoco se puede identificar a nadie.

---

## `bbox` no describe a las personas

`bbox.width` y `bbox.height` son **el ancho y el alto del rectángulo en
píxeles**. No son la estatura, ni el peso, ni la contextura de nadie.

La misma persona produce cajas completamente distintas según lo lejos que esté
de la cámara: cerca da 400 píxeles de alto, al fondo del pasillo da 90. Y
agachada da una caja baja y ancha sin haber encogido.

Nadie debe derivar de `bbox` ninguna característica física, y ninguna etapa
debe escribirla.

---

## Minimización de datos

Solo se guarda lo que hace falta para el objetivo:

- **No se guardan fotogramas** en la base de datos.
- **El video no entra al repositorio**: `.gitignore` excluye `data/videos/`.
- **Las salidas del pipeline son regenerables** y se pueden borrar sin pérdida.
- **`python -m gondola purge`** borra videos y salidas en un comando, pidiendo
  confirmación. Es nuestra herramienta de minimización: cuando el análisis
  termina, el material se elimina.
- **Borrado en la base**: `DELETE FROM videos WHERE video_id = ...` arrastra en
  cascada todos sus eventos y métricas. Un video se elimina entero con una
  sentencia.

---

## Procesamiento local

Todo corre **en la máquina de quien lo ejecuta**:

- El modelo YOLO se descarga una vez y se ejecuta en local.
- El video nunca sale del equipo.
- No hay llamadas a servicios de terceros, ni de visión ni de nada.
- No hace falta conexión a internet para procesar.

Es lo que hace que "percepción visual **soberana**" signifique algo.

---

## Separación entre detección e identidad

La arquitectura separa las dos cosas de forma estructural:

```
   detección     ->  "hay una silueta en estas coordenadas"
   seguimiento   ->  "esta silueta y aquella son la misma, en este video"
   ---------------------------------------------------------------
   identidad     ->  NO EXISTE en ninguna capa del sistema
```

No hay un módulo de identidad desactivado ni una función comentada. No existe
el concepto. Una línea de salida completa dice:

> *"a los 8.43 segundos, una silueta llevaba 12.5 segundos frente al estante 2
> de la góndola A y tomó un producto de bebidas"*

Suficiente para optimizar un planograma. Y no dice absolutamente nada sobre
**quién** era.

---

## Sobre la Ley 1581 de 2012 (Colombia)

La Ley 1581 de 2012 regula el tratamiento de datos personales en Colombia.

**Lo que sí podemos afirmar sobre este sistema:**

- Aplica **privacidad por diseño**: las restricciones son técnicas y están en el
  código, no solo en la documentación.
- **Minimiza el tratamiento de datos personales**: no captura ni almacena
  identificadores, biometría, rostros ni atributos personales.
- Los identificadores que usa (`track_id`) son **anónimos y temporales**, sin
  vínculo con persona identificada o identificable.
- El **procesamiento es local**: no hay transferencia a terceros.
- Existen **mecanismos de eliminación** de los datos tratados.

**Lo que NO podemos afirmar:**

> **Este documento no constituye una certificación de cumplimiento legal.**

La evaluación jurídica definitiva —incluyendo si el tratamiento requiere
autorización, aviso de privacidad, registro ante la SIC, política de
tratamiento, o si la información resulta anonimizada en el sentido de la
norma— **corresponde al responsable del tratamiento**, que en un despliegue real
sería el establecimiento comercial, asesorado por su área jurídica.

Nuestro trabajo es que la arquitectura **facilite** ese cumplimiento y reduzca
al mínimo la superficie de datos personales. Afirmar "cumplimos la Ley 1581"
desde un proyecto universitario, sin concepto jurídico, sería irresponsable.

Aspectos que el responsable debería evaluar y que **exceden lo técnico**:

- Si el video de origen, antes de procesarse, ya constituye dato personal y bajo
  qué base legal se capturó.
- Señalización y aviso a las personas en el establecimiento.
- Plazos de conservación del video original.
- Si el nivel de anonimización alcanzado satisface el criterio de la autoridad.
