# backend/

Importador + API REST en Python. Trabajo de la **Persona 7**. Lee lo que el
AI Service dejó en `data/output/` y `data/zones/`, lo sube a PostgreSQL, y
sirve las métricas por HTTP. El AI Service nunca toca la base de datos —
ver [`docs/architecture.md`](../docs/architecture.md).

## Arrancar

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # o source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # ya trae la URL de Postgres que arma docker-compose.yml
```

Levanta PostgreSQL con Docker (`docker-compose.yml` en esta misma carpeta
ya trae las credenciales que espera `.env.example`) y carga el esquema una
sola vez — detalle completo en [`docs/database.md`](../docs/database.md):

```bash
docker compose up -d
docker exec -i gondola-postgres psql -U gondola -d gondola < database/schema.sql
```

Y ya se puede importar y servir:

```bash
# 1. Importa lo que el pipeline ya dejó en data/output/ para un video
python importer.py --video-id video_001 --source-name video_001.mp4

# 2. Arranca la API
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

`--source-name` es opcional pero recomendado: sin él, `source_name` queda
`null` y el selector de video del dashboard muestra un nombre vacío.

Correr los tests (necesitan PostgreSQL real, ver `tests/`):

```bash
pytest
```

## Endpoints

| Método y ruta | Qué devuelve |
|---|---|
| `GET /health` | `{"status": "ok"}` si la API alcanza PostgreSQL |
| `GET /videos` | Los videos importados, más reciente primero |
| `GET /videos/{video_id}` | Resumen general (personas, interacciones, pick-ups, put-backs, permanencia) |
| `GET /videos/{video_id}/metrics` | Métricas por zona — una fila por góndola **y** una por cada estante (`gondola_A`, `gondola_A:estante_1`, ...) |
| `GET /videos/{video_id}/metrics/{zone_id}` | Métricas de una sola zona |
| `GET /videos/{video_id}/zones` | Jerarquía de zonas (qué estante cuelga de qué góndola), para agrupar en el dashboard |
| `GET /videos/{video_id}/positions` | El punto de apoyo (pies) de cada evento, en píxeles del frame — materia prima del mapa de calor real por coordenadas |
| `GET /videos/{video_id}/render` | El video ya procesado en modo `privacy` (fondo gris inventado + cajas de detección). Prefiere el render de `interact` (resalta APPROACH/PICK_UP/PUT_BACK) y cae al de `track` si no existe. 404 si el video no tiene ninguno de los dos en disco |

Todo esto sale de PostgreSQL, **excepto** `/render`, que sirve un archivo
estático de `data/output/` (ver el comentario de `RENDER_DIR` en `api.py`)
— es la única excepción a "esta capa solo lee de la base de datos".

## Configuración (`backend/.env`)

Vive **aparte** del `.env` de la raíz (el del AI Service) a propósito: hay
un test en `ai-service/` que exige que el `.env.example` de la raíz
documente exactamente las variables que lee `gondola/config.py`, ni una
más — meter `DATABASE_URL` ahí lo rompería.

| Variable | Para qué | Obligatoria |
|---|---|---|
| `DATABASE_URL` | Cadena de conexión a PostgreSQL | Sí |
| `RENDER_DIR` | Carpeta con los videos renderizados, si la API corre en otra máquina distinta a la que tiene `data/output/`. Por defecto `<raíz del repo>/data/output` | No |

## CORS

`allow_origins=["*"]` a propósito: `frontend/index.html` es un archivo
suelto que el navegador abre con `file://...`, y eso manda `Origin: null`
en cada `fetch()` — sin CORS abierto, el navegador bloquea la respuesta
aunque la API la haya procesado bien. Es aceptable porque esta API corre en
la red local de la tienda, nunca expuesta a internet: no hay credenciales
que proteger ni un origen externo del que cuidarse.

## Videos reales importados hoy

`video_001` (video de Scapder) y cinco clips del dataset público **MERL
Shopping Dataset** (`video_demo_merl_24_3`, `_15_3`, `_39_1`, `_18_3`,
`_36_1` — mismo prefijo `video_demo_` que los datos de prueba del
dashboard, pero corridos por el pipeline de verdad, no inventados a mano).
Reutilizan la calibración de cámara de `video_001` porque comparten la
misma resolución (920×680): ver `data/zones/README.md`.

**Esto vive SOLO en la máquina donde se corrió el pipeline, no en git.**
Estos seis videos quedaron importados en el volumen de Docker de Postgres
de esa máquina (`gondola_pg_data`); un clon nuevo del repositorio arranca
con `schema.sql` cargado pero la tabla `videos` **vacía** -los archivos de
video en sí tampoco están en git, ver `data/videos/README.md`, así que ni
siquiera se puede correr el pipeline sobre ellos sin conseguirlos aparte-.
Para ver algo en el dashboard sin esperar a un video propio: `python -m
gondola run` con un video que sí tengas, cargar `seed_example.sql` (datos
ficticios con la forma exacta de los reales), o el "Modo Datos de
Demostración" que ya trae el propio `frontend/index.html` (no necesita
backend corriendo).

## Tests

`tests/test_importer.py` y `tests/test_api.py` corren contra PostgreSQL
real (no una base de datos falsa): si `DATABASE_URL` no apunta a un
servidor alcanzable, se saltan solos con un mensaje claro en vez de fallar
en rojo sin explicación (ver `tests/conftest.py`). Cada test usa un
`video_id` único (`video_test_<uuid>`) y lo borra al terminar —no dejan
residuos, pero tampoco corren dentro de una transacción revertida.
