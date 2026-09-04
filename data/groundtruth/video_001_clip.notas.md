# Anotacion manual de `video_001`, ventana 5,0 s - 37,0 s

Acompana a `video_001_clip.csv`. Sin estas notas, esa tabla no se puede
interpretar ni rehacer.

## Que se anoto

- **Video:** `data/videos/video_001.mp4` (920x680, 30 fps, 205,4 s).
- **Ventana anotada:** de 5,0 s a 37,0 s. **32 segundos**, no el video entero.
- **Camara:** cenital (mira al piso desde arriba). La gondola ocupa la franja
  superior del encuadre; la persona camina por debajo de ella.
- **Contenido:** una sola persona, con canasta, que entra por la esquina
  inferior derecha, se para frente a la gondola y va tomando productos.
- **Anotado por:** Claude (Persona 5), inspeccionando el video frame a frame
  con hojas de contacto a 0,25 s. **No es una anotacion humana
  independiente:** ver "Lo que esta anotacion NO es" al final.

## Criterio, escrito ANTES de anotar

`docs/evaluation.md` avisa de que dos personas con criterios distintos
producen un groundtruth inservible. El criterio usado fue:

| Evento | Instante que se anota |
|---|---|
| `APPROACH` | Cuando la persona llega frente a la gondola y **deja de trasladarse**. Uno por visita. |
| `PICK_UP` | Cuando la mano **vuelve del estante** con un producto hacia la canasta. Se ancla en el retorno porque el instante del agarre queda tapado por el propio estante en una camara cenital. |
| `PUT_BACK` | El inverso: la mano lleva un producto del cuerpo/canasta al estante y lo suelta. |

Ademas, para cada `PICK_UP` se anoto la **duracion del gesto completo**:
desde que el brazo empieza a separarse del cuerpo hasta que vuelve. Esa
columna no cabe en el CSV (el formato tiene cuatro columnas fijas), asi que
vive aqui.

## La tabla, con las duraciones

| # | Evento | t anotado | Gesto: inicio -> fin | Duracion |
|---|---|---|---|---|
| 1 | APPROACH | 9,5 s | entra 5,3 -> se detiene 9,5 | (traslado, 4,2 s) |
| 2 | PICK_UP | 12,9 s | 12,1 -> 12,9 | **0,8 s** |
| 3 | PICK_UP | 16,0 s | 14,7 -> 16,0 | **1,3 s** |
| 4 | PICK_UP | 19,0 s | 16,7 -> 19,0 | **2,3 s** |
| 5 | PICK_UP | 32,3 s | 22,4 -> 32,5 | **10,1 s** |
| 6 | PICK_UP | 35,2 s | 33,0 -> 35,2 | **2,2 s** |

**Total: 1 APPROACH, 5 PICK_UP, 0 PUT_BACK en 32 segundos.**

Duracion del gesto: minimo **0,8 s**, mediana **2,2 s**, maximo 10,1 s.
**Ninguno baja de 0,8 s.**

## Incertidumbre, dicha en voz alta

- **Resolucion temporal: 0,25 s.** Los limites de cada gesto tienen ese error;
  las duraciones, el doble (+-0,5 s).
- **El evento 5 (10,1 s) es casi con seguridad mas de una toma.** Entre 22,4 s
  y 32,5 s la persona manipula varios productos sin bajar del todo el brazo, y
  no se ve con claridad ningun deposito intermedio en la canasta. Se anoto como
  uno solo por prudencia: **esta infra-anotado**.
- **`APPROACH` a 9,5 s tiene +-1 s de holgura.** La persona sigue reacomodandose
  hasta ~11,5 s; "dejar de trasladarse" no es un instante nitido.
- **No se observo ningun `PUT_BACK`.** La persona esta llenando una canasta, no
  devolviendo nada. Por eso ese tipo no tiene ni una sola fila, y sus metricas
  no se pueden calcular: no hay contra que compararlas.
- Que el evento 5 sean una o tres tomas **no cambia la conclusion** del
  experimento: el sistema detecto cero `PICK_UP` en esta ventana, asi que el
  recall es 0,000 con cualquier conteo razonable.

## Como reproducir la medicion

El pipeline ya corrio sobre el video completo. Para evaluar solo esta ventana
se recorta la salida de `zones` -sin volver a pasar YOLO- y se corre `interact`
sobre el recorte, con un `VIDEO_ID` propio para no pisar nada:

```bash
# 1. Recortar la salida de zones a la ventana anotada
python - <<'PY'
import json
from pathlib import Path
sal = Path("data/output/video_001_clip.zones.jsonl")
with Path("data/output/video_001.zones.jsonl").open(encoding="utf-8") as f, \
     sal.open("w", encoding="utf-8", newline="\n") as g:
    for linea in f:
        if not linea.strip():
            continue
        d = json.loads(linea)
        if 5.0 <= d["timestamp"] <= 37.0:
            d["video_id"] = "video_001_clip"
            g.write(json.dumps(d, ensure_ascii=False) + "\n")
# el resumen de zones y el archivo de zonas, con el nuevo video_id
r = json.loads(Path("data/output/video_001.zones.summary.json").read_text("utf-8"))
r["video_id"] = "video_001_clip"
Path("data/output/video_001_clip.zones.summary.json").write_text(
    json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
z = json.loads(Path("data/zones/video_001.json").read_text("utf-8"))
z["video_id"] = "video_001_clip"
Path("data/zones/video_001_clip.json").write_text(
    json.dumps(z, indent=2, ensure_ascii=False), encoding="utf-8")
PY

# 2. Correr la etapa y evaluar
cd ai-service
VIDEO_ID=video_001_clip python -m gondola interact
VIDEO_ID=video_001_clip python -m gondola eval
```

Aviso sobre el recorte: `interact` arranca su mediana movil en el primer evento
del recorte, asi que el primer y el ultimo medio segundo de la ventana estan
peor sostenidos que el resto. Con 32 segundos anotados es despreciable, pero
conviene saberlo.

## Lo que esta anotacion NO es

`docs/evaluation.md` pide decir junto a la cifra **cuantos minutos se anotaron,
quien los anoto y con que criterio**. Los minutos y el criterio estan arriba.
El "quien" es la parte incomoda:

**La anoto la misma IA que escribio el modulo que se esta evaluando.** Eso no
la invalida -se hizo mirando pixeles, no la salida del detector, y el resultado
sale mal parado para el modulo, que es la direccion en la que un sesgo no
suele empujar-, pero **no sustituye a un anotador humano independiente**, que
es lo que pide el documento y lo que hay que tener antes de publicar cualquier
cifra fuera del equipo.

Ademas son **32 segundos y una sola persona**: aunque el numero saliera bueno,
no soportaria una afirmacion general sobre la exactitud del sistema.
