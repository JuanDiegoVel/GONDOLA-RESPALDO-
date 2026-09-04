# data/models/

Aqui cae el modelo YOLO (`.pt`). No se sube a git: pesa decenas o cientos de MB.

    MODEL_PATH=data/models/yolo11n.pt

**Descargalo a mano y dejalo en esta carpeta.** Automatizar la descarga se
quedo anotado y no construido: hoy se hace una vez y ya. `python -m gondola
doctor` te dice si falta.

## openh264-2.5.0-win64.dll (solo Windows)

Necesaria para que `gondola/video/render.py` escriba los videos `.privacy.mp4`
en H.264 (el codec que reproduce un `<video>` de navegador -antes se usaba
`mp4v`, que se descarga bien pero ningun navegador sabe decodificar, bug real
que se encontro probando el reproductor del dashboard). Sin esta DLL, OpenCV
NO lanza ningun error: escribe un archivo casi vacio en silencio, asi que si
un video sale corrupto o pesa unos pocos KB, revisa esto primero.

Descarga (oficial, de Cisco, licencia permisiva):

    http://ciscobinary.openh264.org/openh264-2.5.0-win64.dll.bz2

Descomprimela (`bunzip2` o 7-Zip) y deja el `.dll` resultante en esta misma
carpeta, junto a `yolo11n.pt`. Verifica el checksum contra el `.md5.txt` que
Cisco publica al lado del `.bz2`, antes de usarla. `render.py` la encuentra
sola (`os.add_dll_directory`); no hace falta tocar el PATH del sistema.

Mac/Linux no la necesitan: ahi el backend FFmpeg de OpenCV normalmente ya
sabe codificar H.264 sin depender de esta libreria aparte.
