# Góndola Inteligente

**Percepción visual soberana para optimizar el espacio en retail.**
Reto de la empresa Scapder.

A partir del video de una tienda, el sistema mide cómo se mueven los clientes
alrededor de las góndolas —flujo, permanencia e interacción con productos— para
recomendar mejoras de *space management* y planogramas.

> **No identifica personas, no reconoce rostros, no infiere emociones y no crea
> perfiles biométricos.** No es una promesa: son restricciones técnicas
> verificables. Ver [privacy.md](docs/privacy.md).

---

## El problema

Un supermercado sabe qué vende, pero no sabe **qué pasa frente al estante**:
cuánta gente pasa sin detenerse, cuánta se para y no toma nada, qué altura de
estante funciona, qué producto se toma y se devuelve.

Ese vacío se llena hoy con intuición. Este sistema lo llena con medición, sin
tocar la privacidad de nadie.

---

## Arquitectura

```
   video.mp4
       |
   [ detect ] --> [ track ] --> [ zones ] --> [ interact ] --> [ metrics ]
       |              |             |              |               |
       +--------- archivos .jsonl (un evento por línea) ------------+
                              |
                    [ Backend ] --> PostgreSQL      (Persona 7)
                          |
                       API REST
                          v
                    [ Dashboard ]                    (Persona 8)
```

Cada etapa lee el archivo de la anterior, **rellena sus propios campos** del
mismo evento y escribe el siguiente. Nadie inventa formatos.

**El AI Service nunca escribe en la base de datos.** Produce archivos; solo el
backend los importa. Así seis personas trabajan sin instalar PostgreSQL, y si
un procesamiento falla a medias se borra un archivo en vez de limpiar tablas.
El razonamiento completo está en [architecture.md](docs/architecture.md).

---

## Tecnologías

| Capa | Herramientas |
|---|---|
| Detección (Personas 1–6) | Python 3.12+, Ultralytics **YOLO11n**, OpenCV |
| Contrato de datos | Pydantic v2 (`extra="forbid"`) |
| Formato de intercambio | JSONL (un evento por línea) |
| Backend y API (Persona 7) | **Python** (FastAPI o equivalente) |
| Base de datos | PostgreSQL |
| Dashboard (Persona 8) | **Python**, lo más simple que sirva |
| Tests | pytest |

**Un solo lenguaje para las 8 personas: Python**, de la detección al dashboard.
No usamos Java, Spring Boot, JPA, Maven, Gradle ni IntelliJ, y no hay nada de
eso en el repositorio. Un único entorno que instalar, y cualquiera puede leer el
código de cualquier otra. El razonamiento está en
[architecture.md](docs/architecture.md).

---

## Estructura

```
PROYECTO GONDOLA INTELIGENTE/
├── ai-service/            El pipeline de visión (Personas 1-6)
│   ├── gondola/
│   │   ├── contract.py      EL CONTRATO. Empieza a leer por aquí.
│   │   ├── config.py        Configuración, leída del .env
│   │   ├── pipeline.py      Registro de etapas: el código decide los nombres
│   │   ├── jsonl.py         Lectura/escritura en streaming
│   │   ├── cli.py           python -m gondola
│   │   ├── stages/          Una etapa por archivo
│   │   ├── video/           Lo único que sabe de OpenCV
│   │   ├── verify/          ¿cumple el contrato y la privacidad?
│   │   └── evaluate/        ¿acierta? (contra anotaciones humanas)
│   └── tests/               unit/ (rápidos) e integration/ (con YOLO)
├── backend/               Importador y API REST en Python (Persona 7)
│   └── database/            schema.sql y datos de ejemplo
├── frontend/              Dashboard (HTML/CSS/JS, ver su README) y recomendaciones (Persona 8)
├── data/                  videos, models, output, groundtruth
├── docs/                  Documentación
└── scripts/               Utilidades
```

---

## Instalación

```bash
git clone <url-del-repo>
cd "PROYECTO GONDOLA INTELIGENTE"
cp .env.example .env
```

**Para correr los tests** (ligero, unos MB):

```bash
pip install -r requirements-dev.txt
pytest
```

**Para ejecutar el pipeline** (pesado, ~3 GB: arrastra PyTorch):

```bash
pip install -r requirements.txt
```

Comprueba que todo está en su sitio:

```bash
cd ai-service
python -m gondola doctor
```

`doctor` es lo primero que hay que correr cuando algo no funciona: dice qué
está instalado, qué archivos faltan y en qué punto va la cadena.

---

## Configuración

Todo se ajusta en el `.env` (copiado de `.env.example`). Lo que más se toca:

| Variable | Para qué |
|---|---|
| `VIDEO_PATH` | Dónde está el video |
| `VIDEO_ID` | Etiqueta corta que queda escrita en cada evento |
| `CONFIDENCE_THRESHOLD` | Confianza mínima (0.0–1.0). Súbela si aparecen personas donde no las hay |
| `FRAME_STRIDE` | Procesar 1 de cada N frames. Súbelo para ir más rápido en pruebas |
| `MAX_FRAMES` | Cortar tras N frames. 0 = video completo |
| `RENDER_MODE` | `privacy` (defecto), `debug` o `none` |
| `DEVICE` | `cpu`, `cuda` o `mps` |

---

## El video de Scapder

**Va en `data/videos/`.** No se sube al repositorio: pesa, y contiene imágenes
de personas reales (`.gitignore` lo excluye a propósito).

```bash
# 1. deja el archivo en data/videos/scapder.mp4
# 2. apúntalo en tu .env:
#      VIDEO_PATH=data/videos/scapder.mp4
#      VIDEO_ID=video_001

cd ai-service
python -m gondola detect
```

**¿Todavía no lo tienes?** Genera clips sintéticos para trabajar:

```bash
python scripts/make_test_clips.py
cd ai-service
python -m gondola detect --video data/videos/clip_formas.mp4
```

Esos clips son **controles negativos**: no hay ninguna persona en ellos, así que
la detección debe dar 0. Eso prueba que el sistema no se inventa personas; **no**
prueba que detecte bien.

---

## Ejecutar

```bash
cd ai-service

python -m gondola doctor      # diagnóstico. Empieza SIEMPRE por aquí
python -m gondola detect      # detección de personas          (Persona 2)  hecho
python -m gondola track       # seguimiento                    (Persona 3)  pendiente
python -m gondola zones       # zonas y permanencia            (Persona 4)  pendiente
python -m gondola interact    # interacción con productos      (Persona 5)  pendiente
python -m gondola metrics     # métricas finales               (Persona 6)  pendiente
python -m gondola run         # la cadena completa
python -m gondola verify <archivo>   # ¿cumple el contrato y la privacidad?
python -m gondola eval        # ¿acierta? (necesita anotaciones)
python -m gondola purge       # borra videos y salidas de data/
```

Opciones de `detect` (sobrescriben el `.env` solo para esa corrida):

```
--video RUTA     --conf 0.6      --stride 5       --max-frames 50
--imgsz 640      --device cpu    --render MODO    --open
```

Códigos de salida: `0` éxito · `1` error · `2` falta un requisito.

---

## Cómo leer la salida

Cada etapa escribe un `.jsonl` en `data/output/`: **un evento por línea**, donde
un evento es *una persona detectada en un frame*.

```json
{"video_id": "video_001", "frame": 253, "timestamp": 8.43, "track_id": 7,
 "detection": {"class": "person", "confidence": 0.94,
               "bbox": {"x": 145.0, "y": 40.0, "width": 90.0, "height": 150.0}},
 "zone": {"zone_id": "gondola_A", "segment": "estante_2"},
 "interaction": {"event": "PICK_UP", "product_zone": "bebidas"},
 "metrics": {"dwell_time": 12.5}}
```

Esa línea dice: *"a los 8.43 segundos, una silueta llevaba 12.5 segundos frente
al estante 2 de la góndola A y tomó un producto de bebidas"*. Suficiente para
optimizar un planograma; nada sobre **quién** era.

Los `null` no son errores: significan *"esa etapa todavía no ha pasado por
aquí"*. Formato completo en [data-contract.md](docs/data-contract.md).

> ⚠️ `bbox.width` y `bbox.height` son **píxeles de la caja**, nunca la estatura
> ni ninguna medida de la persona.

Además de los eventos, cada corrida deja un `.summary.json` con los parámetros
usados y un video renderizado (en modo `privacy`, sin un solo píxel del
original).

---

## Privacidad

Tres barreras técnicas, no una declaración:

1. **El contrato usa `extra="forbid"`.** Un campo de edad o rostro rompe la
   validación al instante, en la máquina de quien lo intentó.
2. **`verify` relee los archivos** buscando campos prohibidos en español e
   inglés, incluso anidados.
3. **El render por defecto es `privacy`**: fondo neutro generado desde cero. Al
   renderizador ni se le pasa el fotograma original.

Detalle, incluida la relación con la Ley 1581 de 2012, en
[privacy.md](docs/privacy.md).

---

## Estado y roadmap

| Fase | Estado |
|---|---|
| Arquitectura y contrato de datos | hecho |
| CLI y registro de etapas | hecho |
| Detección con YOLO + render | hecho |
| Verificador y evaluación | hecho |
| Base de datos, documentación y CI | hecho |
| Seguimiento, zonas, interacción, métricas | pendiente — Personas 3–6 |
| Importador y API REST en Python | hecho (`backend/importer.py`, `backend/api.py`) — falta `backend/README.md` con la guía de arranque completa |
| Dashboard | hecho (HTML/CSS/JS, ver `frontend/README.md`) — faltan recomendaciones con nivel de confianza, *edge*/Docker e integración final |
| **Anotación de video para medir exactitud** | pendiente — **sin esto no hay cifras** |

### Lo que este sistema todavía NO puede afirmar

- **No sabemos si acierta.** Sin video anotado a mano no hay precisión ni
  recall. Cualquier porcentaje sería inventado.
- **Nunca se ha visto una detección positiva verificada**: los clips de prueba
  no tienen personas, y el video real aún no se ha procesado.
- **No mide permanencia ni interacciones todavía**: esas etapas están
  pendientes.
- **Solo se ha probado en CPU.**

---

## Colaborar

Lee primero [team-guide.md](docs/team-guide.md) — quién hace qué, con qué
archivos y en qué orden.

```bash
git checkout -b feature/tracking     # una rama por persona, nunca main
# ... trabajas ...
pytest
python -m gondola verify data/output/<tu_archivo>
git push -u origin feature/tracking  # y abres Pull Request
```

Los tests corren solos en cada push y Pull Request.

---

## Documentación

| Documento | Qué contiene |
|---|---|
| [data-contract.md](docs/data-contract.md) | **El contrato. Empieza aquí.** |
| [team-guide.md](docs/team-guide.md) | Quién hace qué y en qué orden |
| [architecture.md](docs/architecture.md) | Por qué las piezas están así |
| [development.md](docs/development.md) | Estándares y ramas |
| [evaluation.md](docs/evaluation.md) | Cómo anotar y medir exactitud |
| [database.md](docs/database.md) | Esquema SQL |
| [privacy.md](docs/privacy.md) | Privacidad por diseño |
