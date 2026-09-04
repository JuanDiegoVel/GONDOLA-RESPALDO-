"""Conexion a PostgreSQL y consultas. Responsable: Persona 7.

Este es el UNICO modulo del backend que sabe hablar SQL. El importador
(`importer.py`) y la API (`api.py`) piden datos aqui; ninguno de los dos
arma una consulta por su cuenta. Igual que en el AI Service nadie llama a
`os.getenv` fuera de `gondola/config.py`, aqui nadie abre una conexion fuera
de este archivo.

DATABASE_URL se lee de `backend/.env`, NO del `.env` de la raiz del
repositorio. Parece romper la regla de "un solo .env para todo el proyecto",
pero `ai-service/tests/unit/test_config.py` exige que el `.env.example` de
la raiz documente EXACTAMENTE las variables que lee `gondola/config.py`, ni
una mas: si `DATABASE_URL` viviera ahi, ese test se rompe cada vez que se
toca el backend. El backend es una capa aparte (ver docs/architecture.md) y
tiene su propia configuracion, en `backend/.env.example`.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

# Carpeta del backend: aqui vive su propio .env (ver docstring del modulo).
BACKEND_DIR = Path(__file__).resolve().parent

_ENV_CARGADO = False


class DatabaseError(Exception):
    """La base de datos no esta configurada o no se pudo alcanzar."""


def _cargar_env() -> None:
    """Carga `backend/.env` una sola vez por proceso."""
    global _ENV_CARGADO
    if not _ENV_CARGADO:
        load_dotenv(BACKEND_DIR / ".env")
        _ENV_CARGADO = True


def database_url() -> str:
    """Devuelve la cadena de conexion. Falla con un mensaje claro si falta."""
    _cargar_env()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseError(
            "DATABASE_URL no esta configurada.\n"
            "Que hacer: copia .env.example a .env en la raiz del repositorio "
            "y ajusta DATABASE_URL a tu PostgreSQL (ver backend/database/README.md)."
        )
    return url


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Abre una conexion, la entrega y la cierra siempre al salir.

    Uso:
        with get_connection() as conn:
            ...

    `row_factory=dict_row` hace que cada fila llegue como un dict
    (`{"video_id": ..., "people_count": ...}`) en vez de una tupla posicional:
    el codigo que lee el resultado no depende del ORDEN de las columnas en el
    SELECT, solo de sus nombres.
    """
    try:
        conn = psycopg.connect(database_url(), row_factory=dict_row)
    except psycopg.OperationalError as exc:
        raise DatabaseError(
            f"No pude conectar a PostgreSQL.\nDetalle: {exc}\n\n"
            "Que hacer: comprueba que el servidor este corriendo y que "
            "DATABASE_URL en tu .env sea correcta (ver backend/database/README.md)."
        ) from exc
    try:
        yield conn
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Videos
# ----------------------------------------------------------------------------

def upsert_video(
    conn: psycopg.Connection,
    *,
    video_id: str,
    source_name: str | None,
    fps: float,
    width: int,
    height: int,
    frame_count: int | None,
    duration_s: float | None,
    contract_version: str,
) -> UUID:
    """Crea el video o actualiza sus columnas si `video_id` ya existia.

    Devuelve el UUID estable de la fila: si el video ya existia, es el MISMO
    UUID de antes (no uno nuevo), asi los `events`/`metrics` que ya
    apuntaban a el se quedan enlazados. Es la base de que reimportar el
    mismo video sea idempotente.
    """
    fila = conn.execute(
        """
        INSERT INTO videos (video_id, source_name, fps, width, height,
                             frame_count, duration_s, contract_version)
        VALUES (%(video_id)s, %(source_name)s, %(fps)s, %(width)s, %(height)s,
                %(frame_count)s, %(duration_s)s, %(contract_version)s)
        ON CONFLICT (video_id) DO UPDATE SET
            source_name       = EXCLUDED.source_name,
            fps                = EXCLUDED.fps,
            width              = EXCLUDED.width,
            height             = EXCLUDED.height,
            frame_count        = EXCLUDED.frame_count,
            duration_s         = EXCLUDED.duration_s,
            contract_version   = EXCLUDED.contract_version,
            processed_at       = now()
        RETURNING id
        """,
        {
            "video_id": video_id,
            "source_name": source_name,
            "fps": fps,
            "width": width,
            "height": height,
            "frame_count": frame_count,
            "duration_s": duration_s,
            "contract_version": contract_version,
        },
    ).fetchone()
    return fila["id"]


def list_videos(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Los videos procesados, mas recientes primero."""
    return conn.execute(
        """
        SELECT video_id, source_name, fps, width, height, frame_count,
               duration_s, contract_version, processed_at
        FROM videos
        ORDER BY processed_at DESC
        """
    ).fetchall()


def find_video(conn: psycopg.Connection, video_id: str) -> dict[str, Any] | None:
    """Un video por su etiqueta corta (`video_id`), o None si no existe."""
    return conn.execute(
        """
        SELECT id, video_id, source_name, fps, width, height, frame_count,
               duration_s, contract_version, processed_at
        FROM videos
        WHERE video_id = %(video_id)s
        """,
        {"video_id": video_id},
    ).fetchone()


# ----------------------------------------------------------------------------
# Zonas
# ----------------------------------------------------------------------------

def upsert_zone(
    conn: psycopg.Connection,
    *,
    zone_id: str,
    name: str,
    level: str,
    parent_id: UUID | None,
    product_category: str | None,
) -> UUID:
    """Crea la zona o actualiza sus columnas si `zone_id` ya existia.

    Igual que `upsert_video`: el UUID se conserva entre reimportaciones, asi
    que actualizar el nombre o la categoria de una gondola no revienta las
    filas de `events`/`metrics` que ya la referencian.
    """
    fila = conn.execute(
        """
        INSERT INTO zones (zone_id, name, level, parent_id, product_category)
        VALUES (%(zone_id)s, %(name)s, %(level)s, %(parent_id)s, %(product_category)s)
        ON CONFLICT (zone_id) DO UPDATE SET
            name             = EXCLUDED.name,
            level            = EXCLUDED.level,
            parent_id        = EXCLUDED.parent_id,
            product_category = EXCLUDED.product_category
        RETURNING id
        """,
        {
            "zone_id": zone_id,
            "name": name,
            "level": level,
            "parent_id": parent_id,
            "product_category": product_category,
        },
    ).fetchone()
    return fila["id"]


def list_zones_for_video(conn: psycopg.Connection, video_id: str) -> list[dict[str, Any]]:
    """Las zonas (gondolas y estantes) que tienen al menos una fila de
    `metrics` para este video, con su jerarquia resuelta."""
    return conn.execute(
        """
        SELECT DISTINCT
            z.zone_id, z.name, z.level, z.product_category,
            padre.zone_id AS parent_zone_id
        FROM zones z
        JOIN metrics m ON m.zone_id = z.id
        JOIN videos v  ON v.id = m.video_id
        LEFT JOIN zones padre ON padre.id = z.parent_id
        WHERE v.video_id = %(video_id)s
        ORDER BY z.zone_id
        """,
        {"video_id": video_id},
    ).fetchall()


# ----------------------------------------------------------------------------
# Eventos
# ----------------------------------------------------------------------------

def delete_events_and_metrics(conn: psycopg.Connection, video_uuid: UUID) -> None:
    """Borra los `events`/`metrics` existentes de un video antes de
    reimportarlo. Ver el docstring de `importer.import_video` para por que
    la idempotencia se resuelve asi y no con `ON CONFLICT`."""
    conn.execute("DELETE FROM metrics WHERE video_id = %(id)s", {"id": video_uuid})
    conn.execute("DELETE FROM events  WHERE video_id = %(id)s", {"id": video_uuid})


def insert_events(conn: psycopg.Connection, filas: list[dict[str, Any]]) -> int:
    """Inserta un lote de eventos ya traducidos a columnas de `events`.
    Devuelve cuantos filas se insertaron."""
    if not filas:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO events (
                video_id, frame_number, timestamp_s, track_id,
                confidence, bbox_x, bbox_y, bbox_width, bbox_height,
                zone_id, segment, interaction_event, product_zone, dwell_time_s
            ) VALUES (
                %(video_id)s, %(frame_number)s, %(timestamp_s)s, %(track_id)s,
                %(confidence)s, %(bbox_x)s, %(bbox_y)s, %(bbox_width)s, %(bbox_height)s,
                %(zone_id)s, %(segment)s, %(interaction_event)s, %(product_zone)s, %(dwell_time_s)s
            )
            """,
            filas,
        )
    return len(filas)


def insert_metrics(conn: psycopg.Connection, filas: list[dict[str, Any]]) -> int:
    """Inserta las filas agregadas de `metrics` para un video."""
    if not filas:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO metrics (
                video_id, zone_id, window_start_s, window_end_s,
                people_count, interaction_count, pick_up_count, put_back_count,
                average_dwell_time_s, interaction_rate, pick_up_rate, conversion_rate
            ) VALUES (
                %(video_id)s, %(zone_id)s, %(window_start_s)s, %(window_end_s)s,
                %(people_count)s, %(interaction_count)s, %(pick_up_count)s, %(put_back_count)s,
                %(average_dwell_time_s)s, %(interaction_rate)s, %(pick_up_rate)s, %(conversion_rate)s
            )
            """,
            filas,
        )
    return len(filas)


# ----------------------------------------------------------------------------
# Consultas para la API: resumen y metricas
# ----------------------------------------------------------------------------
# `people_count` SIEMPRE con COUNT(DISTINCT track_id), nunca COUNT(*): ver el
# aviso en la cabecera de la tabla `metrics` en backend/database/schema.sql.

def video_summary(conn: psycopg.Connection, video_id: str) -> dict[str, Any] | None:
    """Resumen general de un video: gente, interacciones, permanencia media.

    Se calcula sobre `events` (no sobre `metrics`) para dar un numero de
    video completo sin depender de como este particionado `metrics` por
    zona/ventana.
    """
    return conn.execute(
        """
        SELECT
            v.video_id, v.source_name, v.duration_s, v.processed_at,
            COUNT(DISTINCT e.track_id) FILTER (WHERE e.track_id IS NOT NULL) AS people_count,
            COUNT(*) FILTER (WHERE e.interaction_event IS NOT NULL)          AS interaction_count,
            COUNT(*) FILTER (WHERE e.interaction_event = 'PICK_UP')          AS pick_up_count,
            COUNT(*) FILTER (WHERE e.interaction_event = 'PUT_BACK')         AS put_back_count,
            AVG(e.dwell_time_s)                                             AS average_dwell_time_s
        FROM videos v
        LEFT JOIN events e ON e.video_id = v.id
        WHERE v.video_id = %(video_id)s
        GROUP BY v.id
        """,
        {"video_id": video_id},
    ).fetchone()


def metrics_by_video(conn: psycopg.Connection, video_id: str) -> list[dict[str, Any]]:
    """Las filas de `metrics` de un video, una por zona, con el nombre y la
    categoria de producto ya resueltos (sin que quien llame tenga que hacer
    un segundo join a `zones`)."""
    return conn.execute(
        """
        SELECT
            z.zone_id, z.name, z.level, z.product_category,
            m.window_start_s, m.window_end_s,
            m.people_count, m.interaction_count, m.pick_up_count, m.put_back_count,
            m.average_dwell_time_s, m.interaction_rate, m.pick_up_rate, m.conversion_rate
        FROM metrics m
        JOIN zones z  ON z.id = m.zone_id
        JOIN videos v ON v.id = m.video_id
        WHERE v.video_id = %(video_id)s
        ORDER BY z.zone_id
        """,
        {"video_id": video_id},
    ).fetchall()


def metrics_by_zone(conn: psycopg.Connection, video_id: str, zone_id: str) -> dict[str, Any] | None:
    """La fila de `metrics` de UNA zona concreta dentro de un video."""
    return conn.execute(
        """
        SELECT
            z.zone_id, z.name, z.level, z.product_category,
            m.window_start_s, m.window_end_s,
            m.people_count, m.interaction_count, m.pick_up_count, m.put_back_count,
            m.average_dwell_time_s, m.interaction_rate, m.pick_up_rate, m.conversion_rate
        FROM metrics m
        JOIN zones z  ON z.id = m.zone_id
        JOIN videos v ON v.id = m.video_id
        WHERE v.video_id = %(video_id)s AND z.zone_id = %(zone_id)s
        """,
        {"video_id": video_id, "zone_id": zone_id},
    ).fetchone()


def positions_for_video(conn: psycopg.Connection, video_id: str) -> list[dict[str, Any]]:
    """El punto de apoyo (los pies) de cada evento del video, en pixeles del
    frame original. Es la materia prima de un mapa de calor REAL (densidad
    espacial continua): sin esto, un "mapa de calor" es solo una tarjeta
    coloreada por conteo agregado, no una densidad de verdad sobre el plano
    de la tienda.

    Mismo punto de apoyo que usa el resto del pipeline para ubicar a una
    persona en el piso (ver `BBox.support_point` en
    `ai-service/gondola/contract.py`): el centro del borde inferior de la
    caja, nunca su centro geometrico (que "flotaria" a la altura del pecho).
    Se calcula en SQL, no en Python, para no traer bbox_width/bbox_height
    sueltos y repetir la aritmetica en cada capa.
    """
    return conn.execute(
        """
        SELECT
            (e.bbox_x + e.bbox_width / 2) AS x,
            (e.bbox_y + e.bbox_height)    AS y
        FROM events e
        JOIN videos v ON v.id = e.video_id
        WHERE v.video_id = %(video_id)s
        """,
        {"video_id": video_id},
    ).fetchall()
