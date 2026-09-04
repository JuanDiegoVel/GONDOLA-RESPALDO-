# Guía de desarrollo

## Antes del primer commit

```bash
cp .env.example .env
pip install -r requirements-dev.txt
pytest                                  # debe salir todo en verde
```

Si `pytest` falla en `main` recién clonado, no es culpa tuya: avisa al equipo.

---

## Ramas

`main` siempre funciona. Nunca se trabaja directo sobre ella.

```bash
git checkout main
git pull
git checkout -b feature/tracking
```

| Rama | Persona | Qué toca |
|---|---|---|
| `feature/architecture` | 1 | contrato, config, CLI, verify, eval |
| `feature/detection` | 2 | `stages/detect.py`, `video/` |
| `feature/tracking` | 3 | `stages/track.py` |
| `feature/zones` | 4 | `stages/zones.py` |
| `feature/interaction` | 5 | `stages/interact.py` |
| `feature/metrics` | 6 | `stages/metrics.py` |
| `feature/backend` | 7 | `backend/` |
| `feature/recommendations` | 8 | `frontend/` |

**Cada quien toca sus archivos.** Si necesitas cambiar algo de otra persona
—sobre todo `contract.py` o `pipeline.py`— háblalo antes. Esos dos archivos los
lee todo el mundo.

---

## Commits

En español, en imperativo, explicando **por qué** y no solo qué:

```
Añade suavizado al tracking para siluetas parcialmente ocultas

Cuando una persona pasa detrás de una góndola, YOLO la pierde 2 o 3
frames y el track_id se rompía. Ahora se mantiene hasta 10 frames.
```

Commits pequeños y frecuentes. Uno por idea, no uno por día de trabajo.

---

## Antes de abrir un Pull Request

```bash
pytest                                              # todo en verde
python -m gondola verify data/output/<tu_archivo>   # tu salida cumple
```

Los dos tienen que pasar. El PR va contra `main` y describe qué hace y qué
probaste. Los tests corren solos en cada push (ver `.github/workflows/`).

---

## Estándares de código

**Nombres y comentarios en español.** El proyecto se sustenta en español; el
código y los docstrings también. Las palabras clave técnicas (`bbox`,
`track_id`, `stride`) se dejan como están porque son términos del dominio.

**Docstrings cortos y útiles.** Explica **por qué**, no qué. Esto no sirve:

```python
def recortar_bbox(xyxy, ancho, alto):
    """Recorta la bbox."""            # ya se veía en el nombre
```

Esto sí:

```python
def recortar_bbox(xyxy, ancho, alto):
    """Recorta la caja al tamaño del frame. Devuelve None si queda degenerada.

    YOLO a veces devuelve cajas que se salen de la imagen (una persona cortada
    por el borde). Si no se recortan, la Persona 4 acaba con un punto de apoyo
    fuera del plano del piso y no entiende por qué.
    """
```

**Sin abstracciones "por si acaso".** Si algo no se usa hoy, no existe. Este
proyecto lo tiene que poder defender un estudiante ante un jurado: código que
no se entiende es código que no sirve, aunque funcione.

**Ante dos soluciones, la más simple**, y dejando escrito por qué.

**Los mensajes de error dicen qué hacer**, no solo qué falló:

```python
# mal
raise ConfigError("CONFIDENCE_THRESHOLD inválido")

# bien
raise ConfigError(
    "CONFIDENCE_THRESHOLD=1.5 está fuera de rango. "
    "Debe estar entre 0.0 y 1.0. Edita tu .env (por defecto: 0.5)."
)
```

---

## Reglas transversales

Estas aplican a todo el mundo:

| Regla | Por qué |
|---|---|
| Los nombres de archivo salen de `pipeline.stage_paths()`, nunca a mano | Con 8 personas, un nombre mal escrito rompe la integración y el error aparece días después |
| Leer y escribir con `jsonl.read_events()` / `write_events()` | Streaming: un video de 10 min da decenas de miles de eventos |
| Configuración solo en `config.py`; nadie más llama a `os.getenv` | Una variable nueva sin documentar en `.env.example` es una variable que nadie sabe que existe |
| Errores de la jerarquía de `errors.py` | Distingue "el proyecto detectó un problema" de "se rompió una librería" |
| Librerías pesadas importadas **dentro** de las funciones | Si no, nadie corre `pytest` sin instalar 3 GB de PyTorch |
| OpenCV solo en `gondola/video/` | Si cambiamos de librería, se toca un sitio |

---

## Tests

Van en `ai-service/tests/`:

- **`unit/`** — rápidos, sin video, sin modelo, sin GPU. Corren con
  `requirements-dev.txt`. Aquí va casi todo.
- **`integration/`** — cargan el modelo y procesan frames. Lentos. Se saltan
  solos con `pytest.importorskip` si falta la dependencia pesada.

```bash
pytest                            # todo
pytest ai-service/tests/unit -v   # solo los rápidos
pytest -k tracking                # los que te interesan
```

**Cada regla se prueba en los dos sentidos**: el caso que debe pasar y el que
debe fallar. Un test que solo prueba el caso bueno aprobaría cualquier cosa.

Los nombres describen la conducta esperada, en español:

```python
def test_una_caja_que_se_sale_del_frame_se_recorta():
def test_un_campo_inventado_falla_la_validacion():
```

Cuando arregles un bug, **escribe primero el test que lo reproduce**. Así sabes
que lo arreglaste y que no vuelve.

---

## Qué NO se hace

- No se sube el video ni los pesos del modelo al repositorio (`.gitignore` los
  excluye a propósito: pesan y contienen imágenes de personas reales).
- No se suben `.env`, salidas de `data/output/` ni archivos temporales.
- No se cambia el contrato por cuenta propia.
- No se añade ningún campo de edad, género, rostro, identidad, emoción o
  biometría. Rompe la validación, y con razón.
- No se inventan cifras de rendimiento o exactitud. Si no lo mediste, no lo
  escribas.
