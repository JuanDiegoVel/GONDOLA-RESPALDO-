# scripts/

Utilidades de un solo uso: preparar el entorno, preparar el video, generar
reportes. No es codigo del pipeline; es andamiaje.

- `setup.py` — **empieza por aqui.** Detecta e instala lo que falte para
  correr el proyecto: `.env`, dependencias ligeras, PostgreSQL (Docker) +
  esquema, y en Windows la libreria `openh264`. Seguro de correr varias
  veces. `python scripts/setup.py --help` para las opciones (`--full`
  instala PyTorch/YOLO, `--model` descarga `yolo11n.pt`).
- `make_test_clips.py` — genera los clips sinteticos de prueba (controles
  negativos, sin personas).
- `draw_zones.py` — dibuja las zonas calibradas de `data/zones/*.json`
  sobre un frame del video, para revisar la calibracion antes de confiar
  en ella.
