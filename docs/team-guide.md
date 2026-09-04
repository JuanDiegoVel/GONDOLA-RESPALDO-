# Guía del equipo

Quién hace qué, en qué orden y con qué archivos.

---

## Primero: que te funcione el proyecto

```bash
git clone <url-del-repo>
cd "PROYECTO GONDOLA INTELIGENTE"

cp .env.example .env
pip install -r requirements-dev.txt     # ligero, unos MB
pytest                                  # todo debe salir en verde

cd ai-service
python -m gondola doctor                # te dice qué tienes y qué te falta
```

**Si algo no funciona, corre `python -m gondola doctor` antes de preguntar.**
Te dice qué está instalado, qué archivos faltan y en qué punto va la cadena.

Para ejecutar el pipeline de verdad (no solo los tests) necesitas lo pesado:

```bash
pip install -r requirements.txt         # ~3 GB, arrastra PyTorch
```

---

## Un solo lenguaje: Python

**Todo el proyecto es Python**, de la detección al dashboard.

| Capa | Lenguaje y herramientas |
|---|---|
| Pipeline (Personas 1–6) | Python 3.12+, Ultralytics YOLO11n, OpenCV, Pydantic v2 |
| Backend y API (Persona 7) | **Python** (FastAPI o equivalente) + PostgreSQL |
| Dashboard (Persona 8) | **Python**, lo más simple que sirva |

**No usamos Java, Spring Boot, JPA, Maven, Gradle ni IntelliJ.** No hace falta
instalar nada de eso y no hay una sola línea de eso en el repositorio.

El criterio es un único lenguaje para las 8 personas: un solo entorno que
instalar, y cualquiera puede leer y arreglar el código de cualquier otra.

---

## Las 8 personas

| # | Rol | Comando | LEE | ESCRIBE | Estado |
|---|---|---|---|---|---|
| **1** | Arquitectura | — | — | contrato, config, CLI, verify, eval | ✅ hecho |
| **2** | Detección | `detect` | el video | `<video>.detect.jsonl` | ✅ hecho |
| **3** | Seguimiento | `track` | `<video>.detect.jsonl` | `<video>.track.jsonl` | ⬜ **siguiente** |
| **4** | Zonas y permanencia | `zones` | `<video>.track.jsonl` | `<video>.zones.jsonl` | ⬜ |
| **5** | Interacción | `interact` | `<video>.zones.jsonl` | `<video>.interact.jsonl` | ⬜ |
| **6** | Métricas | `metrics` | `<video>.interact.jsonl` | `<video>.metrics.json` | ⬜ |
| **7** | Datos y API (Python) | — | los `.jsonl` del pipeline | PostgreSQL + API REST | ⬜ |
| **8** | Dashboard, recomendaciones e integración (Python) | — | la API de la Persona 7 | dashboard + recomendaciones | ⬜ |

### Qué campo del contrato rellena cada quien

| Persona | Campo |
|---|---|
| 2 | `detection` (clase, confianza, bbox) |
| 3 | `track_id` |
| 4 | `zone`, `metrics.dwell_time` |
| 5 | `interaction` |

**Rellenas SOLO lo tuyo.** Los campos de las demás etapas se quedan como están.
El verificador lo comprueba y falla si te sales de tu carril.

### Cuidado: "metrics" son tres cosas distintas

La palabra aparece en tres sitios y conviene no confundirlos:

| Dónde | Qué es | De quién |
|---|---|---|
| `metrics.dwell_time` | un **CAMPO** del contrato | Persona 4 |
| la etapa `metrics` | un **COMANDO** del pipeline | Persona 6 |
| la tabla `metrics` | una **TABLA** de PostgreSQL | Persona 7 |

**El campo guarda el tiempo de UNA persona en UNA zona. La etapa y la tabla
guardan totales agregados de todo el video.** No se renombra ninguno: el campo
está fijado por el contrato y la tabla por el esquema, y cambiarlos ahora
rompería las dos cosas.

### Personas 7 y 8, en detalle

Las Personas 7 y 8 no escriben etapas del pipeline ni rellenan campos del
contrato: **lo consumen**. El reparto va separado a propósito — base de datos,
API y dashboard en una sola persona es demasiado para una.

**PERSONA 7 — datos y API**

- Levantar PostgreSQL y cargar el esquema (`backend/database/schema.sql`).
- **Importador**: de los `.jsonl` del pipeline a las tablas. Idempotente:
  correrlo dos veces sobre el mismo archivo no duplica filas.
- **API REST en Python** (FastAPI o equivalente) que sirve las métricas.
- **LEE:** los archivos del pipeline · **ESCRIBE:** PostgreSQL

**PERSONA 8 — dashboard, recomendaciones e integración final**

- **Dashboard** sobre la API de la Persona 7, en Python, lo más simple que sirva.
- **Motor de recomendaciones** de *space management* y planograma.
- **Optimización para ejecución local** (*edge*) y Docker.
- **Integración final**, pruebas de extremo a extremo y demo.
- **LEE:** la API de la Persona 7 · **ESCRIBE:** la interfaz y las recomendaciones

La Persona 8 **no** lee los `.jsonl` ni consulta PostgreSQL directamente: todo
pasa por la API. Si el dashboard necesita un dato que la API no da, se le pide
un endpoint a la Persona 7; no se salta la capa.

---

## Orden de trabajo

**En cadena** (cada una necesita la salida de la anterior):

```
   Persona 2  ->  Persona 3  ->  Persona 4  ->  Persona 5  ->  Persona 6
     hecho        siguiente
```

**En paralelo, desde ya, sin esperar a nadie:**

- **Persona 7** — carga `backend/database/seed_example.sql` y trabaja con datos
  ficticios que tienen la forma exacta de los reales.
- **Persona 8** — arranca en cuanto la Persona 7 tenga la API en pie, aunque
  todavía devuelva los datos ficticios del `seed_example.sql`. El dashboard se
  construye **contra la API**, no leyendo los `.jsonl` ni la base de datos.
- **Quien pueda** — anotar video para el ground truth (ver
  [evaluation.md](evaluation.md)). Es trabajo manual que no depende del código
  y sin él no podemos medir nada.

---

## Cómo escribir tu etapa (Personas 3 a 6)

Tu archivo es `ai-service/gondola/stages/<tu_etapa>.py`. Copia la forma de
[`detect.py`](../ai-service/gondola/stages/detect.py).

```python
from gondola import pipeline
from gondola.jsonl import read_events, write_events

def run(cfg) -> int:
    rutas = pipeline.stage_paths("track", cfg)     # 1. pide las rutas
    pipeline.require_input("track", cfg)           # 2. comprueba la entrada

    def procesar():
        for evento in read_events(rutas.input_path):
            evento.track_id = ...                  # 3. rellena SOLO lo tuyo
            yield evento

    escritos = write_events(rutas.output_path, procesar())
    print(f"Escritos {escritos} eventos.")
    return 0
```

Y en `cli.py`, cambia una línea para que tu comando llame a tu `run()`.

### Cuatro reglas

1. **Nunca escribas un nombre de archivo a mano.** Pídelo con
   `pipeline.stage_paths()`. Con 8 personas, un `salida.jsonl` contra un
   `salidas.jsonl` rompe la integración y el error aparece días después.
2. **Lee y escribe en streaming**, con `read_events()` y `write_events()`. Un
   video de 10 minutos da decenas de miles de eventos.
3. **Rellena solo tus campos.**
4. **Si usas una librería pesada, impórtala dentro de la función**, no arriba
   del archivo. Si no, el resto del equipo no puede correr `pytest`.

### Antes de decir "ya terminé"

```bash
pytest                                              # los tests en verde
python -m gondola verify data/output/<tu_archivo>   # tu salida cumple
```

**El verificador es tu prueba.** Si pasa, tu etapa cumple el contrato y no
filtra datos prohibidos, y nadie tiene que revisarte el código a mano.

---

## Git

Una rama por persona. Nunca se trabaja directo en `main`.

```bash
git checkout -b feature/tracking      # tu rama
# ... trabajas, commits pequeños ...
pytest && python -m gondola verify data/output/<tu_archivo>
git push -u origin feature/tracking
# abres Pull Request hacia main
```

| Rama | Persona |
|---|---|
| `feature/architecture` | 1 |
| `feature/detection` | 2 |
| `feature/tracking` | 3 |
| `feature/zones` | 4 |
| `feature/interaction` | 5 |
| `feature/metrics` | 6 |
| `feature/backend` | 7 |
| `feature/recommendations` | 8 |

Detalles en [development.md](development.md).

---

## Las tres cosas que no se negocian

**1. El contrato.** Nadie inventa campos ni cambia el formato por su cuenta.
Si de verdad falta algo, se habla con el equipo, se sube `CONTRACT_VERSION` y
se actualiza [data-contract.md](data-contract.md).

**2. La privacidad.** Prohibido cualquier campo de edad, género, rostro,
identidad, emoción o biometría. No es una recomendación: rompe la validación.
Ver [privacy.md](privacy.md).

**3. `people_count` se cuenta con `COUNT(DISTINCT track_id)`, nunca `COUNT(*)`.**
Una persona parada 20 segundos genera ~500 eventos. Contar filas convierte una
persona en 500 clientes, no lanza ningún error, y arruina todas las
recomendaciones. Ver [database.md](database.md).

---

## Documentación, por orden de lectura

| Documento | Cuándo leerlo |
|---|---|
| [data-contract.md](data-contract.md) | **Primero. Antes de escribir una línea.** |
| [architecture.md](architecture.md) | Para entender por qué las piezas están así. |
| [development.md](development.md) | Antes de tu primer commit. |
| [evaluation.md](evaluation.md) | Si vas a anotar video. |
| [database.md](database.md) | Personas 7 y 8. |
| [privacy.md](privacy.md) | Antes de la sustentación. Todos. |
