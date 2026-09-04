# evaluate/

Mide cuanto ACIERTA el sistema, comparando su salida contra anotaciones hechas
a mano por una persona que vio el video.

    cd ai-service
    python -m gondola eval
    python -m gondola eval --tolerance 1.5

Calcula precision, recall y F1 por tipo de evento (`APPROACH`, `PICK_UP`,
`PUT_BACK`) y en total.

> **HOY NO TENEMOS ANOTACIONES.** El formato, el lector y el calculo estan
> hechos y probados con datos sinteticos, pero sin un CSV anotado **no se puede
> afirmar ninguna cifra de exactitud**. Inventarse un porcentaje de precision
> seria deshonesto, y `eval` se niega a hacerlo: sin ground truth avisa y sale
> con codigo 2.

Formato de anotacion y como llenarlo: [`docs/evaluation.md`](../../../docs/evaluation.md).
Ejemplo listo para copiar: `data/groundtruth/ejemplo.csv`.
