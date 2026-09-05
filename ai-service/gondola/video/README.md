# video/

Lectura de video y dibujado de resultados: abrir el archivo, recorrer frames
respetando `FRAME_STRIDE` y `MAX_FRAMES`, y generar el video de salida
(`RENDER_MODE`).

Es el unico lugar del proyecto que sabe de OpenCV. Si manana cambiamos de
libreria, solo se toca esta carpeta.

Hecho: `reader.py` (lectura de frames) y `render.py` (modos `privacy`, `debug`
y `none`).

`render.py` escribe en H.264 (`avc1`), no en `mp4v`: es el codec que un
`<video>` de navegador sabe reproducir (`mp4v` se descarga bien pero ningun
navegador lo decodifica). En Windows hace falta la libreria `openh264` de
Cisco aparte -ver `data/models/README.md`-; si falta, OpenCV no lanza
ningun error, solo escribe un video casi vacio en silencio.
