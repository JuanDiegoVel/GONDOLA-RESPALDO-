# Arquitectura

## El flujo, de principio a fin

```
   video.mp4
       |
       v
   [ detect ]  YOLO encuentra personas          -> video_001.detect.jsonl
       |
       v
   [ track ]   enlaza siluetas entre frames     -> video_001.track.jsonl
       |
       v
   [ zones ]   ubica en góndolas, mide tiempo   -> video_001.zones.jsonl
       |
       v
   [ interact ] detecta PICK_UP / PUT_BACK      -> video_001.interact.jsonl
       |
       v
   [ metrics ] agrega los totales               -> video_001.metrics.json
       |
       v
   [ Backend ]  importa los archivos  ------->  PostgreSQL      Persona 7
       |       y expone una API REST
       |
       |  API REST  (la única vía: el dashboard nunca consulta PostgreSQL)
       v
   [ Dashboard ]  + recomendaciones                              Persona 8
```

Cada etapa lee el archivo de la anterior, **rellena sus propios campos** del
mismo evento y escribe el siguiente archivo. Nadie inventa formatos: todos
hablan el `Event` de [`contract.py`](../ai-service/gondola/contract.py).

---

## La decisión más importante: el AI Service nunca toca la base de datos

**El pipeline escribe archivos. Solo el backend escribe en PostgreSQL.**

```
   AI Service  ->  .jsonl  ->  Backend  ->  PostgreSQL
   (6 personas)                (1 persona)
```

Tres razones, por orden de importancia:

**1. Seis personas trabajan sin instalar una base de datos.** Las Personas 2 a
6 escriben etapas del pipeline. Si el pipeline escribiera en PostgreSQL,
cada una tendría que instalarlo, configurarlo, tener las credenciales y
mantener su copia sincronizada. Con archivos, `pip install` y a trabajar. El
día que alguien tiene problemas con la base de datos, es una persona parada,
no seis.

**2. Un fallo a medias se arregla borrando un archivo.** El procesamiento tarda
media hora. Si se corta en el minuto 20 habiendo escrito ya en PostgreSQL, hay
que averiguar qué entró, borrarlo sin tocar lo demás y volver a empezar. Con
archivos: `rm video_001.detect.jsonl` y otra vez. Sin transacciones a medias,
sin limpiezas manuales, sin tablas en estado raro.

**3. Se puede inspeccionar con la vista.** Un `.jsonl` se abre con cualquier
editor. Cuando la Persona 4 dice "mis zonas salen mal", se mira el archivo. Con
la base de datos habría que conectarse y escribir consultas para lo mismo.

**El precio, que sí existe:** los datos no están consultables hasta que el
backend los importa, y ocupan espacio en disco duplicado (archivos + tablas).
Para un proyecto que procesa videos por lotes, no en tiempo real, es un precio
barato. Si algún día hiciera falta procesar en vivo, esta decisión habría que
reconsiderarla.

---

## Las tres capas

| Capa | Carpeta | Qué hace | Lenguaje | Quién |
|---|---|---|---|---|
| **AI Service** | `ai-service/` | Del video a los `.jsonl`. | Python 3.12+ (YOLO11n, OpenCV, Pydantic v2) | Personas 1–6 |
| **Backend** | `backend/` | De los `.jsonl` a PostgreSQL. Expone la API REST. | **Python** (FastAPI o equivalente) + PostgreSQL | Persona 7 |
| **Frontend** | `frontend/` | Dashboard y recomendaciones. | **HTML/CSS/JS vanilla** — ver excepción abajo | Persona 8 |

Las capas solo se comunican por **archivos** (AI → Backend) y por **API**
(Backend → Frontend). Nadie importa código de otra capa.

### Las tres capas son Python — con una excepción documentada

**No usamos Java, Spring Boot, JPA, Maven, Gradle ni IntelliJ.** No hay nada de
eso en el repositorio y no hay que instalarlo.

El criterio no es que Python sea mejor: es que **un solo lenguaje para las 8
personas** vale más que la herramienta ideal en cada capa. Con un único entorno,
quien escribe una etapa del pipeline puede leer el backend, y quien hace el
dashboard puede depurar el importador. Con dos lenguajes tendríamos dos
ecosistemas, dos formas de empaquetar y dos mitades del equipo que no se pueden
ayudar entre sí.

**`frontend/` rompe esta regla, a propósito y por escrito.** Es un solo
archivo HTML con CSS y JavaScript vanilla (`frontend/index.html`): sin
Node, sin `npm install`, sin build. Se diseñó primero en React (con ayuda
de una IA) y se portó a mano a HTML/JS plano para no obligar al equipo a
instalar un segundo entorno — la parte que sí se sostiene de "un solo
entorno que instalar" es que seguir sin necesitar Node en ninguna máquina.
Lo que sí se pierde es que quien solo sabe Python no puede leer este
archivo tan fácil como leería un `.py`. El detalle completo, las
limitaciones y qué falta están en [`frontend/README.md`](../frontend/README.md).

---

## Personas 7 y 8: quién hace qué

Las capas Backend y Frontend van a personas distintas a propósito: base de
datos, API y dashboard en una sola persona es demasiada carga para una.

**PERSONA 7 — datos y API** (`backend/`)

- Levantar PostgreSQL y cargar el esquema (`backend/database/schema.sql`).
- **Importador**: de los `.jsonl` del pipeline a las tablas. Idempotente:
  correrlo dos veces sobre el mismo archivo no duplica filas.
- **API REST en Python** (FastAPI o equivalente) que sirve las métricas.
- **LEE:** los archivos del pipeline · **ESCRIBE:** PostgreSQL

**PERSONA 8 — dashboard, recomendaciones e integración final** (`frontend/`)

- **Dashboard** sobre la API de la Persona 7 (HTML/CSS/JS vanilla, ver la
  excepción de lenguaje más arriba y `frontend/README.md`).
- **Motor de recomendaciones** de *space management* y planograma.
- **Optimización para ejecución local** (*edge*) y Docker.
- **Integración final**, pruebas de extremo a extremo y demo.
- **LEE:** la API de la Persona 7 · **ESCRIBE:** la interfaz y las recomendaciones

Esta frontera es la misma regla de arriba aplicada al equipo: la Persona 8 no
lee los `.jsonl` ni consulta PostgreSQL por su cuenta. Si el dashboard necesita
un dato que la API no da, se pide un endpoint; no se salta la capa.

---

## Piezas del AI Service

| Módulo | Responsabilidad |
|---|---|
| `contract.py` | **El contrato.** El único formato de datos del proyecto. |
| `config.py` | Toda la configuración, leída del `.env`. Nadie más llama a `os.getenv`. |
| `pipeline.py` | El registro de etapas. **El código decide los nombres de archivo.** |
| `jsonl.py` | Leer y escribir eventos en streaming. |
| `cli.py` | Punto de entrada único: `python -m gondola`. |
| `video/` | Lo único que sabe de OpenCV: leer video y renderizar. |
| `stages/` | Una etapa por archivo. |
| `verify/` | Comprueba que una salida cumple el contrato y la privacidad. |
| `evaluate/` | Mide la exactitud contra anotaciones humanas. |

Dos reglas transversales:

- **Los nombres de archivo salen de `pipeline.stage_paths()`**, nunca escritos a
  mano. Ocho personas escribiendo nombres de archivo a mano es una integración
  rota garantizada.
- **Las librerías pesadas se importan dentro de las funciones.** `ultralytics`
  arrastra 3 GB de PyTorch. Si estuviera arriba de un archivo, nadie podría
  correr los tests sin instalarlo.

---

## Por qué JSONL y no un JSON grande

Un video de 10 minutos produce decenas de miles de eventos.

- **Un JSON gigante** hay que cargarlo entero en memoria para leer una línea, y
  si se corta a la mitad no sirve nada de él.
- **JSONL** (un objeto JSON por línea) se lee de a poco, se puede procesar
  mientras se escribe, y una línea corrupta solo daña esa línea.

Por eso `read_events()` es un generador y `write_events()` acepta generadores:
una etapa completa se ejecuta sin acumular nada en memoria.

---

## Privacidad en la arquitectura

Que el sistema no identifique personas no es una promesa en un documento: está
en tres capas del diseño.

1. **El contrato usa `extra="forbid"`.** Añadir un campo de edad o rostro rompe
   la validación al instante, en la máquina de quien lo intentó.
2. **`verify` relee los archivos ya escritos** buscando campos prohibidos, por
   si los produjo otra herramienta.
3. **El render por defecto es `privacy`**: dibuja sobre fondo neutro y no
   recibe siquiera el fotograma original.

Detalles en [privacy.md](privacy.md).
