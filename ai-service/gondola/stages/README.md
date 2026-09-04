# stages/

Una etapa del pipeline por archivo. Cada etapa recibe eventos, **rellena sus
propios campos del contrato** y los devuelve. Ninguna etapa inventa un formato
nuevo: todas hablan el mismo `Event` de `gondola/contract.py`.

| Archivo | Responsable | Campos que rellena | Estado |
|---|---|---|---|
| `detect.py`   | Persona 2 | `detection` | **hecha** (Fase 3) |
| `track.py`    | Persona 3 | `track_id` | pendiente |
| `zones.py`    | Persona 4 | `zone`, `metrics.dwell_time` | pendiente |
| `interact.py` | Persona 5 | `interaction` | pendiente |
| `metrics.py`  | Persona 6 | agregados finales | pendiente |

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
