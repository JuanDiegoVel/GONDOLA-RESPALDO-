"""Tests de la API REST (backend/api.py).

Usan el mismo importador ya probado en test_importer.py para dejar un video
en la base, y despues comprueban que la API lo sirve tal cual. No repiten
aritmetica: solo verifican forma de la respuesta, codigos de estado y
mensajes de error.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api import app  # noqa: E402
from importer import import_video  # noqa: E402
from test_importer import _preparar_archivos  # noqa: E402

cliente = TestClient(app)


@pytest.fixture
def video_importado(tmp_path, video_id, db_conn):
    """Un video con datos reales en la base, listo para que la API lo sirva."""
    output_dir, zones_dir, eventos = _preparar_archivos(tmp_path, video_id)
    import_video(video_id, output_dir=output_dir, zones_dir=zones_dir)
    return video_id


def test_health_confirma_conexion_a_postgres(_servidor_disponible):
    respuesta = cliente.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}


def test_listar_videos_incluye_el_importado(video_importado):
    respuesta = cliente.get("/videos")
    assert respuesta.status_code == 200
    video_ids = [v["video_id"] for v in respuesta.json()]
    assert video_importado in video_ids


def test_video_inexistente_da_404_con_mensaje_util(_servidor_disponible):
    respuesta = cliente.get("/videos/video_que_no_existe")
    assert respuesta.status_code == 404
    assert "video_que_no_existe" in respuesta.json()["detail"]


def test_resumen_de_video_cuenta_personas_distintas(video_importado):
    respuesta = cliente.get(f"/videos/{video_importado}")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["video_id"] == video_importado
    # 3 personas en los eventos de _preparar_archivos, 5 filas de evento.
    assert cuerpo["people_count"] == 3
    assert cuerpo["pick_up_count"] == 1
    assert cuerpo["put_back_count"] == 0


def test_metricas_del_video_devuelve_una_fila_por_zona(video_importado):
    respuesta = cliente.get(f"/videos/{video_importado}/metrics")
    assert respuesta.status_code == 200
    filas = respuesta.json()
    assert len(filas) == 1  # solo la gondola tiene fila en metrics.json
    assert filas[0]["zone_id"] == f"{video_importado}_gondola_A"
    assert filas[0]["people_count"] == 2  # la persona sin zona no cuenta aqui


def test_metricas_de_zona_desconocida_da_404(video_importado):
    respuesta = cliente.get(f"/videos/{video_importado}/metrics/zona_que_no_existe")
    assert respuesta.status_code == 404
    assert "zona_que_no_existe" in respuesta.json()["detail"]
