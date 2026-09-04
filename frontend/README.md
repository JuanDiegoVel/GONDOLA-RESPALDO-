# frontend/

Dashboard de la **Persona 8**, en Python: mapas de calor de las góndolas,
tiempos de permanencia y recomendaciones de planograma.

**Consume la API REST de la Persona 7.** No lee los `.jsonl` de `data/output/`
ni consulta PostgreSQL directamente: si hace falta un dato que la API no da, se
pide un endpoint. La frontera entre capas está en
[`docs/architecture.md`](../docs/architecture.md).

Aquí van también el motor de recomendaciones, la optimización para ejecución
local (*edge*) con Docker y la integración final de extremo a extremo.

Vacía todavía: es el trabajo de la Persona 8, que aún no ha empezado.
