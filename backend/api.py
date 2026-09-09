"""API REST: sirve lo que el importador dejo en PostgreSQL. Responsable: Persona 7.

Arranque local:
    cd backend
    uvicorn api:app --reload --host 0.0.0.0 --port 8000

STACK Y POR QUE
----------------
FastAPI + psycopg (via `db.py`), sin ORM. Para cuatro consultas de solo
lectura un ORM es una capa de traduccion que nadie mas del equipo necesita
aprender; SQL explicito en `db.py` es mas facil de leer para las otras 7
personas del proyecto, que ya conocen `schema.sql`.

Esta capa NO calcula nada: cada endpoint llama a una funcion de `db.py` y
devuelve lo que llega. Toda la aritmetica (tasas, agregados) ya la hizo la
Persona 6 al escribir `metrics.json`, o Postgres al agregar `events`.

QUE NO HAY AQUI TODAVIA A PROPOSITO
--------------------------------------
Mapa de calor y recomendaciones con nivel de confianza son de otra
fase/persona (Persona 8 consume esta API, no le pega a la base de datos por
su cuenta: ver docs/architecture.md, seccion "Personas 7 y 8"). Esta API
solo expone datos.

CORS: POR QUE UNA LISTA DE ORIGENES, NO "*"
-----------------------------------------------
`frontend/index.html` es un archivo HTML suelto (sin build, sin servidor
propio) que la Persona 8 abre directo con el navegador (`file://...`). Un
navegador que abre un archivo local manda `Origin: null` en sus peticiones
`fetch()`, y sin `CORSMiddleware` el navegador BLOQUEA la respuesta aunque
la API la haya procesado bien -el bloqueo es del lado del navegador, no de
este servidor-.

Antes esto era `allow_origins=["*"]`, aceptable cuando la API solo
RESPONDIA datos (puros GET). Desde que existe `uploads.py` (Persona 7) hay
endpoints que ESCRIBEN -guardan un video, lanzan el pipeline-, y con "*"
cualquier pagina que alguien de la tienda visitara en su navegador podia
dispararlos contra `127.0.0.1` sin que la persona se enterara: "esto no
sale a internet" no protege de eso, el navegador si sale a internet.
`ORIGENES_PERMITIDOS` (mas abajo) solo deja pasar `null` (el dashboard como
archivo) y `localhost`/`127.0.0.1` (el dashboard servido por HTTP).
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from psycopg.errors import Error as PsycopgError

import db

# RENDER_DIR (mas abajo) es la unica variable de entorno propia de api.py:
# se carga aqui, aparte de db._cargar_env(), porque esa funcion es privada
# de db.py y este archivo necesita el valor ANTES de la primera consulta a
# PostgreSQL (que es cuando db.py cargaria backend/.env por su cuenta).
# dotenv.load_dotenv() no pisa una variable que el sistema ya tenga puesta,
# asi que llamarlo aqui y de nuevo desde db.py es seguro, no se pisan.
from dotenv import load_dotenv

load_dotenv(db.BACKEND_DIR / ".env")

app = FastAPI(
    title="Gondola Inteligente - API",
    description="Metricas de flujo, permanencia e interaccion frente a las gondolas.",
    version="1.0.0",
)

# Carpeta donde el AI Service deja los videos renderizados (RENDER_MODE en
# ai-service/.env). Por defecto <raiz del repo>/data/output -mismo OUTPUT_DIR
# que usa gondola/config.py-, mas PROCESSED_VIDEOS_DIR en backend/.env por si
# alguien corre la API desde otra maquina con los datos en otro lado.
#
# El nombre de esta variable NO empieza por "RENDER_" a proposito: se llamo
# asi al principio (RENDER_DIR) y en un despliegue real en Render.com esa
# variable jamas llegaba con el valor puesto a mano -Render reserva ese
# prefijo para sus propias variables internas y lo pisa en silencio-, asi
# que cualquier "RENDER_algo" que declares en su dashboard es terreno
# minado. Verificado en la practica, no una suposicion.
#
# Esto SI es una excepcion puntual a "el backend solo lee lo que el AI
# Service pone en PostgreSQL" (ver docstring de arriba y
# docs/architecture.md): un video renderizado es un archivo estatico que
# nunca pasa por la base de datos, no un dato para agregar/consultar. Si en
# vez de esto se copiara el video a una tabla, se estaria guardando binarios
# de varios MB en PostgreSQL sin ninguna necesidad.
RENDER_DIR = Path(
    os.environ.get("PROCESSED_VIDEOS_DIR")
    or (Path(__file__).resolve().parent.parent / "data" / "output")
)

# NO es "*" a proposito -ver el docstring de arriba, seccion CORS-.
# `null` es el Origin que manda un archivo abierto con file://, que es como
# se usa el dashboard en local. Los localhost cubren servirlo por HTTP en
# local. El dominio de Firebase Hosting (gondola-inteligente, ver
# frontend/README.md o el deploy con `firebase deploy`) cubre el dashboard
# publicado -Firebase Hosting siempre sirve por HTTPS, de ahi el
# "https://" fijo en ese tramo, a diferencia de los otros dos que son http.
ORIGENES_PERMITIDOS = (
    r"^(null"
    r"|http://(localhost|127\.0\.0\.1)(:\d+)?"
    r"|https://gondola-inteligente\.(web\.app|firebaseapp\.com))$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=ORIGENES_PERMITIDOS,
    allow_methods=["GET", "POST", "DELETE"],  # POST desde uploads.py, DELETE desde eliminar_video
    allow_headers=["*"],
)

# En su propio modulo por ser la unica parte de esta API que ESCRIBE (sube
# un video, dibuja zonas, lanza el pipeline): ver backend/uploads.py.
import uploads  # noqa: E402  (despues de crear `app`, a proposito)

app.include_router(uploads.router)


@app.get("/", include_in_schema=False)
def raiz() -> RedirectResponse:
    """La API no tiene nada que mostrar en '/': manda a la documentacion
    interactiva (Swagger) en vez de devolver un 404 que parezca un fallo."""
    return RedirectResponse(url="/docs")


@app.exception_handler(db.DatabaseError)
def _sobre_error_de_base_de_datos(_request, exc: db.DatabaseError) -> JSONResponse:
    """Un DatabaseError ya trae un mensaje que dice que hacer (ver db.py):
    se devuelve tal cual, en vez de un 500 generico sin contexto."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(PsycopgError)
def _sobre_error_de_postgres(_request, exc: PsycopgError) -> JSONResponse:
    """Cualquier otro error de PostgreSQL que no se haya anticipado: se
    informa igual, sin tumbar el proceso con una traza cruda."""
    return JSONResponse(
        status_code=500,
        content={"detail": f"Error de base de datos: {exc}"},
    )


def _serializable(fila: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convierte UUID/datetime de una fila de psycopg a texto para JSON.

    FastAPI ya sabe serializar estos tipos via Pydantic, pero los endpoints
    devuelven dicts directos de `db.py`, sin modelo intermedio, asi que se
    hace a mano aqui. OJO: se comprueba con `isinstance`, nunca con
    `hasattr(valor, "hex")` como atajo para "es un UUID": los `float` de
    Python TAMBIEN tienen un metodo `.hex()` (`(25.0).hex()` es valido), y
    ese atajo convertia numeros como `fps` o las tasas en texto (`"25.0"`
    en vez de `25.0`) sin que ninguna excepcion lo delatara.
    """
    if fila is None:
        return None
    return {
        clave: (str(valor) if isinstance(valor, (UUID, datetime, date)) else valor)
        for clave, valor in fila.items()
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Confirma que la API puede alcanzar PostgreSQL. Para el arranque del
    equipo y para la demo: si esto falla, nada mas de la API va a funcionar."""
    with db.get_connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/videos")
def listar_videos() -> list[dict[str, Any]]:
    """Los videos ya importados, mas reciente primero."""
    with db.get_connection() as conn:
        filas = db.list_videos(conn)
    return [_serializable(f) for f in filas]


def _requiere_video(conn, video_id: str) -> dict[str, Any]:
    fila = db.find_video(conn, video_id)
    if fila is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No hay ningun video importado con video_id='{video_id}'. "
                "Que hacer: python -m gondola run (ai-service/) y despues "
                "python importer.py --video-id " + video_id + " (backend/)."
            ),
        )
    return fila


@app.get("/videos/{video_id}")
def resumen_de_video(video_id: str) -> dict[str, Any]:
    """Resumen general: personas, interacciones, permanencia media."""
    with db.get_connection() as conn:
        _requiere_video(conn, video_id)
        resumen = db.video_summary(conn, video_id)
    return _serializable(resumen)


@app.get("/videos/{video_id}/metrics")
def metricas_del_video(video_id: str) -> list[dict[str, Any]]:
    """Las metricas agregadas, una fila por zona (gondola o estante)."""
    with db.get_connection() as conn:
        _requiere_video(conn, video_id)
        filas = db.metrics_by_video(conn, video_id)
    return [_serializable(f) for f in filas]


@app.get("/videos/{video_id}/metrics/{zone_id}")
def metricas_de_zona(video_id: str, zone_id: str) -> dict[str, Any]:
    """Las metricas agregadas de UNA zona concreta dentro de un video."""
    with db.get_connection() as conn:
        _requiere_video(conn, video_id)
        fila = db.metrics_by_zone(conn, video_id, zone_id)
    if fila is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"El video '{video_id}' no tiene metricas para la zona "
                f"'{zone_id}'. Usa GET /videos/{video_id}/metrics para ver "
                "las zonas disponibles."
            ),
        )
    return _serializable(fila)


@app.get("/videos/{video_id}/zones")
def jerarquia_de_zonas(video_id: str) -> list[dict[str, Any]]:
    """Góndolas y estantes con métricas en este video, con su jerarquía
    (parent_zone_id) resuelta. Es lo que usa el mapa de calor del dashboard
    para agrupar cada estante bajo su góndola."""
    with db.get_connection() as conn:
        _requiere_video(conn, video_id)
        filas = db.list_zones_for_video(conn, video_id)
    return [_serializable(f) for f in filas]


@app.get("/videos/{video_id}/zones/geometry")
def geometria_de_zonas(video_id: str) -> dict[str, Any]:
    """El área de piso (`floor_zone`) de cada estante, en píxeles del frame
    original -la calibración de cámara que vive en
    `data/zones/<video_id>.json`, nunca en PostgreSQL (`zones` solo guarda
    nombre y jerarquía, ver schema.sql: no hay columnas x/y/width/height).

    Existe para que el mapa de calor real del dashboard (coordenadas
    crudas de GET /videos/{video_id}/positions) pueda dibujar de fondo la
    misma silueta de góndola -un rectángulo con dos líneas de "estante"-
    que ya dibuja el render 'privacy' del AI Service (ver
    ai-service/gondola/video/render.py, `_dibujar_lineas_estante`): sin
    esa referencia, los puntos de densidad flotan sobre un fondo vacío sin
    forma de saber a qué estante corresponden.

    `zone_id` de cada estante sale compuesto ("<gondola>:<segment>", igual
    que arma `_zone_id_de_estante` en importer.py) para que el frontend
    pueda cruzarlo con el `zone_id` que ya trae GET /videos/{video_id}/zones.

    Lee el JSON directo del disco (no pasa por `gondola.zones_config`: el
    backend evita a propósito las dependencias pesadas del ai-service, ver
    el comentario de requirements.txt) -por eso, igual que /render, devuelve
    404 si el archivo no está: un video puede no tener calibración de zonas
    en disco todavía, o alguien pudo borrarla con 'python -m gondola purge'."""
    with db.get_connection() as conn:
        _requiere_video(conn, video_id)
    ruta = uploads.ZONES_DIR / f"{video_id}.json"
    if not ruta.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"El video '{video_id}' no tiene calibración de zonas en disco "
                f"({ruta}). Sin ese archivo no hay geometría que dibujar."
            ),
        )
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    estantes = [
        {
            "zone_id": f"{gondola['zone_id']}:{estante['segment']}",
            "gondola_zone_id": gondola["zone_id"],
            "name": estante["name"],
            "x": estante["floor_zone"]["x"],
            "y": estante["floor_zone"]["y"],
            "width": estante["floor_zone"]["width"],
            "height": estante["floor_zone"]["height"],
        }
        for gondola in datos.get("gondolas", [])
        for estante in gondola.get("shelves", [])
    ]
    return {
        "frame_width": datos["frame_width"],
        "frame_height": datos["frame_height"],
        "shelves": estantes,
    }


@app.get("/videos/{video_id}/render")
def video_renderizado(video_id: str) -> FileResponse:
    """El video ya procesado por el AI Service en modo `privacy`: fondo gris
    inventado (nunca el fotograma real, ver ai-service/gondola/video/render.py)
    con los rectangulos de deteccion. Es lo unico de esta API que no sale de
    PostgreSQL -ver el comentario de RENDER_DIR, mas arriba-.

    Prefiere el render de la etapa 'interact' (resalta el instante exacto de
    cada APPROACH/PICK_UP/PUT_BACK, ver gondola/stages/interact.py) sobre el
    de 'track' (solo cajas + ID de seguimiento, sin interacciones: esa etapa
    corre ANTES de que existan). Cae a 'track' si un video se proceso antes
    de que 'interact' supiera renderizar, para no dejar sin video a nadie
    que ya lo tenia importado.

    Devuelve 404 si el video no tiene NINGUNO de los dos en disco: no todos
    lo tienen (RENDER_MODE=none corre mas rapido, o alguien pudo borrar
    data/output/ con 'python -m gondola purge' despues de importar).

    `Cache-Control: no-cache` a proposito: sin este header, el navegador
    puede reusar una copia vieja del video de su cache local sin siquiera
    preguntarle a este servidor -bug real, encontrado en la practica: el
    archivo en disco ya tenia el contador de "productos" nuevo, pero el
    navegador seguia mostrando la version de antes de reprocesar el video-.
    "no-cache" no significa "no guardes nada": significa "revalida con el
    servidor (ETag/Last-Modified) antes de usar lo que tengas guardado", asi
    que sigue siendo rapido cuando el video no cambio, y correcto cuando si."""
    ruta = RENDER_DIR / f"{video_id}.interact.privacy.mp4"
    if not ruta.exists():
        ruta = RENDER_DIR / f"{video_id}.track.privacy.mp4"
    if not ruta.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"El video '{video_id}' no tiene un render 'privacy' en disco "
                f"({ruta}). Que hacer: corre 'python -m gondola run' con "
                "RENDER_MODE=privacy en ai-service/.env para ese video."
            ),
        )
    return FileResponse(ruta, media_type="video/mp4", headers={"Cache-Control": "no-cache"})


@app.get("/videos/{video_id}/positions")
def posiciones_del_video(video_id: str) -> list[dict[str, Any]]:
    """El punto de apoyo (x, y en píxeles del frame) de cada evento del
    video: la materia prima de un mapa de calor real (densidad espacial),
    no un agregado por zona. Puede ser una lista larga (miles de puntos en
    un video de varios minutos) — es solo lectura, sin paginar: para los
    tamaños de este proyecto el JSON se sigue sirviendo en milisegundos."""
    with db.get_connection() as conn:
        _requiere_video(conn, video_id)
        filas = db.positions_for_video(conn, video_id)
    return [_serializable(f) for f in filas]


def _borrar_archivos_del_video(video_id: str) -> list[str]:
    """Borra el video original y todo lo que el pipeline escribio para el
    -incluida su calibracion de zonas-. Nunca lanza por un archivo que no
    exista (borrar algo que ya no esta no es un error); devuelve los
    nombres de lo que si se borro, para que quien pida el borrado sepa que
    paso de verdad, no solo que "no hubo excepcion".

    El punto (`.`) despues de `video_id` en cada patron no es decorativo:
    todo archivo que este modulo o el pipeline escriben usa exactamente
    `<video_id>.<algo>` como nombre (`.mp4`, `.detect.jsonl`,
    `.interact.privacy.mp4`, `.calib.jpg`...), asi que sin ese punto un
    video_id que fuera PREFIJO de otro (ej. `video_002` de un futuro
    `video_0020`) podria borrar archivos ajenos."""
    rutas = [uploads.VIDEOS_DIR / f"{video_id}.mp4", uploads.ZONES_DIR / f"{video_id}.json"]
    if uploads.OUTPUT_DIR.is_dir():
        rutas.extend(uploads.OUTPUT_DIR.glob(f"{video_id}.*"))

    borrados = []
    for ruta in rutas:
        if ruta.exists():
            ruta.unlink()
            borrados.append(ruta.name)
    return borrados


@app.delete("/videos/{video_id}")
def eliminar_video(video_id: str) -> dict[str, Any]:
    """Borra un video por completo: su fila en PostgreSQL (con sus
    `events`/`metrics` en cascada, ver `db.delete_video`) y todos sus
    archivos en disco (`data/videos/`, `data/output/`, `data/zones/`).

    NO se puede deshacer -no hay papelera-: por eso el dashboard pide
    confirmar antes de llamar a esto. Las filas de `zones` (los nombres de
    gondola/estante, compartidos entre videos que reusan la misma
    calibracion de camara) nunca se tocan: son del MOBILIARIO, no de este
    video en concreto.

    Solo se puede borrar un video SUBIDO por un usuario (`video_id` con el
    prefijo `uploads.PREFIJO_VIDEO_SUBIDO`, ver `uploads.subir()`): los
    videos de ejemplo (`video_001`, `video_demo_merl_*`) no llevan ese
    prefijo y este endpoint los rechaza, aunque el dashboard ya oculta el
    boton de borrar para ellos -es una segunda barrera por si alguien llama
    a la API directo, no solo desde la interfaz."""
    if not video_id.startswith(uploads.PREFIJO_VIDEO_SUBIDO):
        raise HTTPException(
            status_code=403,
            detail=(
                f"'{video_id}' es un video de ejemplo, no uno subido por un "
                "usuario: no se puede borrar desde este endpoint."
            ),
        )
    with db.get_connection() as conn:
        borrado = db.delete_video(conn, video_id)
    if not borrado:
        raise HTTPException(
            status_code=404,
            detail=f"No hay ningun video importado con video_id='{video_id}'.",
        )

    archivos_borrados = _borrar_archivos_del_video(video_id)
    return {"video_id": video_id, "borrado": True, "archivos_borrados": archivos_borrados}
