"""Fixtures compartidas de los tests del backend.

Los tests hablan con PostgreSQL DE VERDAD (no hay mock de base de datos):
la garantia que interesa -que el importador y la API respeten el esquema
real, con sus CHECK y sus UNIQUE- se pierde si se prueba contra algo que no
es Postgres. Si DATABASE_URL no apunta a un servidor alcanzable, los tests
se saltan con un mensaje claro en vez de fallar en rojo sin explicacion.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import db  # noqa: E402  (necesita el sys.path.insert de arriba)


@pytest.fixture(scope="session")
def _servidor_disponible() -> None:
    """Se salta TODA la sesion de tests de base de datos si no hay Postgres
    a mano, en vez de fallar test por test con el mismo error de conexion."""
    try:
        with db.get_connection() as conn:
            conn.execute("SELECT 1")
    except db.DatabaseError as exc:
        pytest.skip(f"PostgreSQL no disponible para los tests: {exc}")


@pytest.fixture
def video_id(_servidor_disponible) -> str:
    """Un video_id unico por test, para que dos tests no choquen entre si
    y para poder borrarlo limpio al terminar (ver `_borrar_video` abajo)."""
    return f"video_test_{uuid4().hex[:12]}"


@pytest.fixture
def db_conn(_servidor_disponible):
    with db.get_connection() as conn:
        yield conn


@pytest.fixture(autouse=True)
def _borrar_video(video_id, _servidor_disponible):
    """Limpieza automatica: borra el video de prueba (y en cascada sus
    events/metrics) al terminar cada test, exista o no."""
    yield
    with db.get_connection() as conn:
        conn.execute("DELETE FROM videos WHERE video_id = %(id)s", {"id": video_id})
        # Los estantes cuelgan (ON DELETE CASCADE) de su gondola: basta con
        # borrar las gondolas de prueba para llevarse tambien sus estantes.
        conn.execute(
            "DELETE FROM zones WHERE level = 'gondola' AND zone_id LIKE %(prefijo)s",
            {"prefijo": f"{video_id}_%"},
        )
        conn.commit()
