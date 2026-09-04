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
linea de eso en el repositorio y no debe aparecer ninguna. Que `backend/` hoy
solo contenga `.sql` no significa que el backend sea de otro lenguaje: significa
que la Persona 7 aun no ha escrito el importador ni la API, y los escribira en
Python.

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

## Ejecutar el proyecto

Todo pasa por la CLI. Se ejecuta desde `ai-service/`, que es donde vive el
paquete:

```
cd ai-service
python -m gondola doctor     # diagnostico; empieza SIEMPRE por aqui
python -m gondola run        # la cadena completa
```

Codigos de salida: 0 exito, 1 error de ejecucion, 2 falta un requisito (el
video o el archivo de la etapa anterior).

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
  cinco etapas como placeholders), lectura y escritura de .jsonl en streaming.
- **Fase 3 (hecha):** lectura de video (`gondola/video/reader.py`), deteccion
  YOLO (`gondola/stages/detect.py`), render en modo privacy/debug
  (`gondola/video/render.py`) y clips sinteticos de prueba.
- **Fase 4 (hecha):** verificador de contrato y privacidad
  (`gondola/verify/`) y evaluacion contra `groundtruth` (`gondola/evaluate/`).
- **Fase 5 (hecha):** esquema SQL y datos de ejemplo (`backend/database/`),
  documentacion (`docs/`), CI en GitHub Actions y README completo.

Lo que sigue NO es una fase de arquitectura: son los modulos del equipo.
`track` (Persona 3), `zones` (Persona 4), `interact` (Persona 5) y `metrics`
(Persona 6) siguen siendo placeholders en la CLI. Cada uno crea su archivo en
`gondola/stages/` y rellena SOLO sus campos del contrato.

Sin video anotado a mano en `data/groundtruth/` no se puede afirmar nada sobre
la exactitud del sistema. Ningun porcentaje de precision es publicable hasta
entonces.

No construir cosas de fases futuras.
