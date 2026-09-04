# data/zones/

Archivos de calibracion de camara: donde estan las gondolas y estantes de una
tienda, en pixeles. Formato completo: [`docs/zones-format.md`](../../docs/zones-format.md).

- `video_001.example.json` — **ejemplo**, calibrado a ojo contra
  `data/videos/video_001.mp4` con `scripts/draw_zones.py`. Sirve para
  desarrollar y probar sin depender de que alguien mas haya calibrado ya el
  video real. No lo trates como calibracion final: revisalo con la
  herramienta antes de confiar en el.
- A diferencia de los videos y los modelos, **estos archivos SI se versionan
  en git**: son texto plano, pequenos, y no contienen ninguna imagen ni dato
  de personas -son coordenadas de una camara fija, no de gente.

Para calibrar un video nuevo: copia el ejemplo, ajusta las coordenadas, y
revisa el resultado con

    python scripts/draw_zones.py --zones data/zones/<tu_archivo>.json --frame <algun_frame_con_gente>
