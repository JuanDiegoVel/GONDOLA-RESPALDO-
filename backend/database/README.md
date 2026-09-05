# backend/database/

Esquema SQL y datos de ejemplo. Trabajo de la **Persona 7**.

- `schema.sql` — las cuatro tablas. **Ya está.**
- `seed_example.sql` — datos ficticios con la forma exacta de los reales, para
  trabajar sin esperar al pipeline. **Ya está.**

El esquema debe ser un espejo del contrato de datos
(`ai-service/gondola/contract.py`): si un campo cambia allí, cambia aquí, y se
sube `CONTRACT_VERSION` en los dos lados.

El importador (`backend/importer.py`, idempotente: dos corridas del mismo
archivo no duplican filas) y la API REST (`backend/api.py`) ya están hechos
— ver `backend/README.md` para la guía de arranque y la lista de endpoints.

Cómo cargarlo y por qué el esquema es así: [`docs/database.md`](../../docs/database.md).
