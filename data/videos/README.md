# data/videos/

## >>> COLOCAR AQUI EL VIDEO DE SCAPDER <<<

Deja el archivo de video de la tienda en esta carpeta y apunta a el desde tu
`.env`:

    VIDEO_PATH=data/videos/scapder.mp4
    VIDEO_ID=video_001

Reglas:

- Los videos **NO se suben a git** (pesan mucho y contienen imagenes de
  personas reales). `.gitignore` los excluye a proposito.
- Cada quien descarga el video por su cuenta y lo pone aqui.
- `VIDEO_ID` es la etiqueta corta que quedara escrita en cada evento de salida.
  Si trabajas con otro video, cambia tambien el `VIDEO_ID`.

Ademas de `video_001.mp4` (Scapder), aqui tambien viven -por la misma razon,
no se suben a git- los clips del dataset publico **MERL Shopping Dataset**
que se importaron a PostgreSQL (`video_demo_merl_24_3.mp4`, `_15_3`, `_39_1`,
`_18_3`, `_36_1`): comparten la resolucion 920x680 de `video_001`, asi que
reutilizan su misma calibracion de camara (ver `data/zones/README.md`).
