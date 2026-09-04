# data/groundtruth/

Anotaciones hechas **a mano** por nosotros: la "verdad" contra la que medimos
si el sistema acierta o se equivoca.

A diferencia de `output/`, esto **si se versiona en git**: es trabajo humano que
no se puede regenerar y que si se pierde hay que rehacer desde cero.

La lee `gondola/evaluate/` para calcular precision, recall y F1:
`python -m gondola eval`.

**Hoy aqui solo esta `ejemplo.csv`, que es una plantilla, no anotaciones
reales.** Hasta que alguien anote video de verdad, el sistema no puede afirmar
ninguna cifra de exactitud, y `eval` se niega a inventarla: avisa y sale con
codigo 2.

Formato y como anotar: [`docs/evaluation.md`](../../docs/evaluation.md).
