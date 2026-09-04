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
Dashboard, mapa de calor y recomendaciones son de otra fase/persona (Persona
8 consume esta API, no le pega a la base de datos por su cuenta: ver
docs/architecture.md, seccion "Personas 7 y 8"). Esta API solo expone datos.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from psycopg.errors import Error as PsycopgError

import db

app = FastAPI(
    title="Gondola Inteligente - API",
    description="Metricas de flujo, permanencia e interaccion frente a las gondolas.",
    version="1.0.0",
)


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
