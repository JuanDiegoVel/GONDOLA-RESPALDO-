# stages/

Una etapa del pipeline por archivo. Cada etapa recibe eventos, **rellena sus
propios campos del contrato** y los devuelve. Ninguna etapa inventa un formato
nuevo: todas hablan el mismo `Event` de `gondola/contract.py`.

| Archivo | Responsable | Campos que rellena | Estado |
|---|---|---|---|
| `detect.py`   | Persona 2 | `detection` | **hecha** |
| `track.py`    | Persona 3 | `track_id` | **hecha** |
| `zones.py`    | Persona 4 | `zone`, `metrics.dwell_time` | **hecha** |
| `interact.py` | Persona 5 | `interaction` | **hecha** — ademas de eventos, renderiza su propio video (resalta APPROACH/PICK_UP/PUT_BACK, ver su docstring "Video (--render)") |
| `metrics.py`  | Persona 6 | agregados finales | **hecha** — por gondola Y por estante (`gondola_A:estante_1`) |

`detect.py`, `track.py` e `interact.py` escriben ademas su propio video en
`RENDER_MODE=privacy` (fondo gris inventado, nunca el fotograma real).
`backend/api.py` sirve el de `interact` en `GET /videos/{id}/render` -el
unico que resalta APPROACH/PICK_UP/PUT_BACK-, y cae al de `track` si el
video se proceso antes de que `interact` supiera renderizar.

## Como escribir tu etapa

Copia la forma de `detect.py`. Tres reglas:

1. **Las rutas se piden, no se escriben.** `pipeline.stage_paths(nombre, cfg)`
   te dice que leer y que escribir.
2. **Lee y escribe en streaming.** `jsonl.read_events()` y
   `jsonl.write_events()`. Un video de 10 minutos da decenas de miles de
   eventos y no caben comodos en memoria.
3. **Rellena SOLO tus campos.** Los de las demas etapas se quedan como estan.

Si tu etapa necesita una libreria pesada, importala **dentro de la funcion**,
no arriba del archivo. Asi el resto del equipo puede correr `pytest` sin
instalarla. `detect.py` lo hace con ultralytics y OpenCV; su docstring explica
por que.
