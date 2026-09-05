# Instrucciones del proyecto: Gondola Inteligente

## Que es

Reto de la empresa Scapder: a partir del video de una tienda, cuantificar la
dinamica de los clientes alrededor de las gondolas (flujo, permanencia,
interaccion fisica con productos) para recomendar mejoras de *space management*
y planogramas.

Proyecto universitario de 8 personas. La Persona 1 lidera la arquitectura.

## Un solo lenguaje: todo el proyecto es Python

Las tres capas son Python:

| Capa | Lenguaje | Quien |
|---|---|---|
| Pipeline (`ai-service/`) | Python 3.12+, YOLO11n, OpenCV, Pydantic v2 | Personas 1-6 |
| Backend y API (`backend/`) | **Python** (FastAPI) + PostgreSQL | Persona 7 |
| Dashboard (`frontend/`) | **EXCEPCION, ver abajo** | Persona 8 |

**`frontend/` es la unica excepcion a "todo Python", y esta documentada a
proposito, no escondida.** Es HTML + CSS + JavaScript vanilla en un solo
archivo (`frontend/index.html`), sin Node, sin build, sin `package.json`:
se abre directo en el navegador y consume la API de la Persona 7 por
`fetch()`. Se hizo asi porque se diseno primero en React con ayuda de una
IA y se prefirio portarlo a HTML/JS plano antes que arrastrar un segundo
entorno (Node/npm) para las 8 personas. El detalle completo -que hace, que
le falta, que instalar (nada, pero necesita internet para sus CDN sin
version fijada), y una limitacion de CORS ya resuelta en `backend/api.py`-
esta en [`frontend/README.md`](frontend/README.md). Si vas a seguir
tocando el dashboard, lee ese archivo primero.

**No se usa Java, Spring Boot, JPA, Maven, Gradle ni IntelliJ.** No hay una sola
linea de eso en el repositorio y no debe aparecer ninguna. `backend/` ya
tiene su importador (`importer.py`) y su API REST (`api.py`) en Python,
ademas del esquema SQL — ver [`backend/README.md`](backend/README.md).

El criterio es un unico lenguaje para las 8 personas: un solo entorno que
instalar, y cualquiera puede leer y arreglar el codigo de cualquier otra. Vale
mas que la herramienta ideal en cada capa.

## Regla numero uno: el proyecto debe ser PEQUENO

Quien lo escribe tiene que poder defenderlo ante un jurado. Codigo que no se
entiende es codigo que no sirve, aunque funcione.

- Ninguna abstraccion "por si acaso". **Si no se usa hoy, no existe.**
- Nada de patrones de diseno elaborados, capas extra ni configuracion dinamica.
- Ante dos soluciones, la mas simple, y explicando por que.
- Docstrings en espanol, cortos y utiles.
- Si algo hace falta pero no toca en esta fase: se anota, no se construye.

## Privacidad por diseno (no negociable)

El sistema **no** identifica personas, **no** reconoce rostros, **no** infiere
emociones y **no** crea perfiles biometricos.

Prohibido en todo el codigo: edad, genero, rostro, `embeddings` faciales,
identidad, emocion, biometria, o cualquier caracteristica fisica derivada de la
bounding box. Los modelos usan `extra="forbid"` justamente para que esto falle
solo.

`bbox.width` y `bbox.height` son **pixeles de la caja**, nunca la estatura ni la
contextura de nadie.

## El contrato de datos manda

`ai-service/gondola/contract.py` es la pieza central. Documentado en
`docs/data-contract.md`.

Las etapas **enriquecen** el mismo evento; nunca inventan formatos:

| Campo | Responsable |
|---|---|
| `detection` | Persona 2 (YOLO) |
| `track_id` | Persona 3 |
| `zone`, `metrics.dwell_time` | Persona 4 |
| `interaction` | Persona 5 |

Cambiar la forma del evento implica subir `CONTRACT_VERSION`, actualizar
`docs/data-contract.md` y avisar al equipo. Nunca por cuenta propia.

## Primer arranque: un solo comando

Antes de nada, **`python scripts/setup.py`** deja el proyecto listo:
copia los `.env`, instala las dependencias ligeras, levanta PostgreSQL con
Docker y carga el esquema, y en Windows descarga la libreria `openh264`
que hace falta para los videos renderizados. Es seguro correrlo varias
veces -cada paso comprueba si ya esta hecho antes de repetirlo-. Con
`--full` ademas instala PyTorch/YOLO (~3 GB); con `--model` ademas
descarga `yolo11n.pt`. Detalle completo en el docstring del propio script.

Si alguien (persona o Claude Code) pide "prepara/instala/arranca el
proyecto" y todavia no se ha corrido esto en la maquina, este es el primer
paso, antes de instalar nada a mano.

## Ejecutar el proyecto

Tres capas, en orden. El pipeline pasa por la CLI, desde `ai-service/`:

```
cd ai-service
python -m gondola doctor     # diagnostico; empieza SIEMPRE por aqui
python -m gondola run        # la cadena completa (las cinco etapas: hechas)
```

Codigos de salida: 0 exito, 1 error de ejecucion, 2 falta un requisito (el
video o el archivo de la etapa anterior).

Para subir los resultados a PostgreSQL y verlos en el dashboard: ver
[`backend/README.md`](backend/README.md) (arranque, endpoints) y
[`frontend/README.md`](frontend/README.md) (el dashboard se abre directo
con el navegador, sin build).

## Convenciones

- **Nombres de archivo: nunca a mano.** Se piden con
  `pipeline.stage_paths(nombre, cfg)`. La tabla `STAGES` de
  `gondola/pipeline.py` es la unica fuente de verdad de la cadena.
- **Leer y escribir .jsonl:** `jsonl.read_events()` y `jsonl.write_events()`,
  que van en streaming. Nunca `open()` a pelo ni cargar todo en una lista.
- Configuracion: solo en `gondola/config.py`. Nadie mas llama a `os.getenv`.
  Toda variable nueva se documenta en `.env.example`.
- Errores: usar la jerarquia de `gondola/errors.py`. El mensaje dice **que
  hacer**, no solo que fallo.
- Logging: `setup_logging()` se llama una sola vez al arrancar. Las etapas solo
  hacen `logging.getLogger(__name__)`.
- OpenCV vive unicamente en `gondola/video/`.
- **Las librerias pesadas (ultralytics, torch, OpenCV) se importan DENTRO de
  las funciones**, nunca arriba del archivo. Si no, nadie puede correr `pytest`
  sin instalar 3 GB. Ver el docstring de `gondola/stages/detect.py`.
- El render por defecto es `privacy`: fondo neutro, sin ningun pixel del video
  original. El modo `debug` contiene imagenes de personas reales y NO se
  comparte.
- Serializar siempre con `Event.to_jsonl()`; leer con `Event.from_jsonl()`.

## Correr los tests

```
pip install -r requirements-dev.txt
pytest
```

`requirements-dev.txt` es ligero a proposito: los 7 companeros deben poder
correr los tests sin descargar 3 GB de PyTorch. Lo pesado va en
`requirements.txt` y solo lo necesita quien ejecuta el pipeline completo.

## Estado por fases

- **Fase 1 (hecha):** estructura, contrato, configuracion, errores, logging,
  documentacion del contrato, tests unitarios.
- **Fase 2 (hecha):** registro de etapas, CLI (`doctor`, `run`, `purge` y las
  cinco etapas), lectura y escritura de .jsonl en streaming.
- **Fase 3 (hecha):** lectura de video (`gondola/video/reader.py`), deteccion
  YOLO (`gondola/stages/detect.py`), render en modo privacy/debug
  (`gondola/video/render.py`, H.264 -ver `data/models/README.md` sobre la
  libreria `openh264` en Windows-) y clips sinteticos de prueba.
- **Fase 4 (hecha):** verificador de contrato y privacidad
  (`gondola/verify/`) y evaluacion contra `groundtruth` (`gondola/evaluate/`).
- **Fase 5 (hecha):** esquema SQL y datos de ejemplo (`backend/database/`),
  documentacion (`docs/`), CI en GitHub Actions y README completo.
- **Fase 6 (hecha):** las cuatro etapas que faltaban del pipeline -
  `track` (Persona 3), `zones` (Persona 4), `interact` (Persona 5, ademas
  renderiza su propio video resaltando APPROACH/PICK_UP/PUT_BACK) y
  `metrics` (Persona 6, agrega por gondola Y por estante)-. Todas
  implementadas, sin placeholders. Ver `ai-service/gondola/stages/README.md`.
- **Fase 7 (hecha):** importador idempotente y API REST (Persona 7,
  `backend/`) -incluye posiciones para un mapa de calor real y el video
  renderizado servido por HTTP-. Ver `backend/README.md`.
- **Fase 8 (hecha, primera version):** dashboard (Persona 8, `frontend/`):
  resumen por video, analisis por zona/estante, mapa de calor real por
  coordenadas, video anonimizado embebido, comparacion completa de dos
  videos, retroalimentacion automatica, exportar a PDF/Excel. Falta el
  motor de recomendaciones con nivel de confianza y la optimizacion *edge*/
  Docker. Ver `frontend/README.md`.

Hay 6 videos reales ya importados y visibles en el dashboard: `video_001`
(Scapder) y cinco clips del dataset publico MERL Shopping Dataset. Ver
`backend/README.md`, seccion "Videos reales importados hoy".

Sin video anotado a mano en `data/groundtruth/` no se puede afirmar una
cifra de **precision/recall formal** todavia -eso sigue pendiente-, aunque
ya hay deteccion, interaccion y metricas funcionando sobre video real.

No construir cosas de fases futuras que no se hayan pedido.
