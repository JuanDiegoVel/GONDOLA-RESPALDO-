# video/

Lectura de video y dibujado de resultados: abrir el archivo, recorrer frames
respetando `FRAME_STRIDE` y `MAX_FRAMES`, y generar el video de salida
(`RENDER_MODE`).

Es el unico lugar del proyecto que sabe de OpenCV. Si manana cambiamos de
libreria, solo se toca esta carpeta.

Hecho: `reader.py` (lectura de frames) y `render.py` (modos `privacy`, `debug`
y `none`).
