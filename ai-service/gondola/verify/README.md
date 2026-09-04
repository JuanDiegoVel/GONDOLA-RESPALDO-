# verify/

Verificador de contrato y de privacidad.

    cd ai-service
    python -m gondola verify data/output/video_001.detect.jsonl

Revisa una salida del pipeline linea por linea y dice, regla por regla, si
cumple. **Corre esto sobre TU salida antes de decir que terminaste tu etapa.**
Asi nadie tiene que revisarte el codigo a mano.

Once reglas: claves de raiz, validez del contrato, clase `person`, confianza en
rango y sobre el umbral, cajas positivas y dentro del frame, frames que no
retroceden, timestamps coherentes con los fps, campos de etapas posteriores en
null, y **ningun campo prohibido por privacidad**.

Codigo de salida 1 si algo falla, con el numero de linea de los primeros casos.

El verificador deduce que reglas aplicar por el nombre del archivo:
`...detect.jsonl` exige que `track_id` este en null, `...track.jsonl` ya no.
