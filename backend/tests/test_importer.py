"""Tests del importador (backend/importer.py).

Construyen los tres archivos de entrada A MANO -sin video, sin YOLO, sin
correr el pipeline-, igual que los tests de las demas etapas. El
`metrics.json` de prueba se calcula A MANO aqui mismo (ver
`_metrics_esperado_5_eventos`), en vez de reutilizar
`gondola.stages.metrics` como se hacia antes: ese modulo tiene mas de una
implementacion en juego ahora mismo (la del equipo original y la de
Maryi, que no comparten funciones internas), asi que estos tests no deben
depender de las internas de NINGUNA de las dos. Lo que este archivo
prueba es que el IMPORTADOR traduce bien un metrics.json a filas de
PostgreSQL, no que la aritmetica de metricas sea correcta -eso es
responsabilidad de los tests de la Persona 6.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import db  # noqa: E402
from importer import ImporterError, import_video  # noqa: E402

AI_SERVICE = BACKEND.parent / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

from gondola.contract import (  # noqa: E402
    BBox, Detection, Event, Interaction, InteractionEvent, Metrics, Zone,
)
from gondola.jsonl import write_events  # noqa: E402

FPS = 25.0


def _zones_config(video_id: str) -> dict:
    """Una gondola con dos estantes, en el mismo formato que
    data/zones/<video_id>.json (ver gondola/zones_config.py)."""
    gondola_id = f"{video_id}_gondola_A"
    return {
        "video_id": video_id,
        "frame_width": 1280,
        "frame_height": 720,
        "gondolas": [
            {
                "zone_id": gondola_id,
                "name": "Gondola de prueba",
                "product_category": "bebidas",
                "shelves": [
                    {
                        "segment": "estante_1",
                        "name": "Estante 1 de prueba",
                        "product_category": None,
                        "floor_zone": {"x": 100, "y": 300, "width": 200, "height": 150},
                    },
                    {
                        "segment": "estante_2",
                        "name": "Estante 2 de prueba",
                        "product_category": "snacks",
                        "floor_zone": {"x": 400, "y": 300, "width": 200, "height": 150},
                    },
                ],
            }
        ],
    }, gondola_id


def _evento(video_id, frame, track_id, zone_id=None, segment=None,
            interaction=None, product_zone=None, dwell_time=None) -> Event:
    return Event(
        video_id=video_id,
        frame=frame,
        timestamp=frame / FPS,
        track_id=track_id,
        detection=Detection(confidence=0.9, bbox=BBox(x=10, y=10, width=50, height=120)),
        zone=Zone(zone_id=zone_id, segment=segment),
        interaction=Interaction(event=interaction, product_zone=product_zone),
        metrics=Metrics(dwell_time=dwell_time),
    )


def _preparar_archivos(tmp_path: Path, video_id: str) -> tuple[Path, Path, list[Event]]:
    """Escribe zones/<video_id>.json, output/<video_id>.interact.jsonl y
    output/<video_id>.metrics.json bajo tmp_path. Devuelve (output_dir,
    zones_dir, eventos) para que cada test pueda inspeccionar los eventos
    usados."""
    zones_dir = tmp_path / "zones"
    output_dir = tmp_path / "output"
    zones_dir.mkdir()
    output_dir.mkdir()

    config, gondola_id = _zones_config(video_id)
    (zones_dir / f"{video_id}.json").write_text(json.dumps(config), encoding="utf-8")

    # Persona 1: se acerca al estante 1 y toma un producto.
    # Persona 2: pasa por el estante 2, no interactua.
    # Persona 3: sin zona (pasillo, entre gondolas).
    eventos = [
        _evento(video_id, 25, 1, gondola_id, "estante_1", InteractionEvent.APPROACH, "bebidas", 1.0),
        _evento(video_id, 50, 1, gondola_id, "estante_1", None, None, 2.0),
        _evento(video_id, 75, 1, gondola_id, "estante_1", InteractionEvent.PICK_UP, "bebidas", 3.0),
        _evento(video_id, 100, 2, gondola_id, "estante_2", InteractionEvent.APPROACH, "snacks", 0.5),
        _evento(video_id, 125, 3, None, None, None, None, None),
    ]

    interact_path = output_dir / f"{video_id}.interact.jsonl"
    write_events(interact_path, eventos)

    # Calculado a mano (ver test_importa_video_zonas_eventos_y_metricas):
    # track 1 (gondola_id): dwell 1.0, 2.0, 3.0; interacciones APPROACH,
    # None, PICK_UP. track 2 (gondola_id): dwell 0.5; interaccion
    # APPROACH. track 3: sin zona, no cuenta para ninguna zona.
    #   people_count      = 2          (tracks 1 y 2)
    #   interaction_count = 3          (APPROACH+PICK_UP de t1, APPROACH de t2)
    #   pick_up_count     = 1, put_back_count = 0
    #   average_dwell_time_s = (1.0+2.0+3.0+0.5) / 4 = 1.625
    #   interaction_rate  = 2/2 = 1.0  (t1 y t2 tuvieron >=1 interaccion)
    #   pick_up_rate      = 1/3 = 0.3333333333333333
    #   conversion_rate   = 1/2 = 0.5  (solo t1 tuvo un PICK_UP)
    metrics_json = {
        "contract_version": "1.0.0",
        "video_id": video_id,
        "zones": {
            gondola_id: {
                "people_count": 2,
                "interaction_count": 3,
                "pick_up_count": 1,
                "put_back_count": 0,
                "average_dwell_time_s": 1.625,
                "interaction_rate": 1.0,
                "pick_up_rate": 1 / 3,
                "conversion_rate": 0.5,
            },
        },
    }
    (output_dir / f"{video_id}.metrics.json").write_text(
        json.dumps(metrics_json), encoding="utf-8"
    )

    return output_dir, zones_dir, eventos


def test_importa_video_zonas_eventos_y_metricas(tmp_path, video_id, db_conn):
    output_dir, zones_dir, eventos = _preparar_archivos(tmp_path, video_id)

    resumen = import_video(video_id, output_dir=output_dir, zones_dir=zones_dir)

    assert resumen.eventos_importados == len(eventos)
    assert resumen.zonas_importadas == 3  # 1 gondola + 2 estantes
    assert resumen.metricas_importadas == 1  # solo la gondola tiene fila en metrics.json
    assert resumen.fps_derivados == pytest.approx(FPS, rel=1e-3)

    video = db.find_video(db_conn, video_id)
    assert video is not None
    assert video["width"] == 1280
    assert video["height"] == 720

    filas_metrics = db.metrics_by_video(db_conn, video_id)
    assert len(filas_metrics) == 1
    gondola = filas_metrics[0]
    assert gondola["people_count"] == 2       # track_id 1 y 2 (el 3 no tiene zona)
    assert gondola["pick_up_count"] == 1
    # track 1: APPROACH + PICK_UP (estante_1); track 2: APPROACH (estante_2).
    # Ambos estantes cuelgan de la misma gondola, que es el nivel al que
    # agrega metrics.json (ver gondola/stages/metrics.py).
    assert gondola["interaction_count"] == 3

    filas_events = db_conn.execute(
        """
        SELECT count(*) AS n FROM events e
        JOIN videos v ON v.id = e.video_id
        WHERE v.video_id = %(video_id)s
        """,
        {"video_id": video_id},
    ).fetchone()
    assert filas_events["n"] == len(eventos)

    # El evento sin zona (persona 3, pasillo) debe llegar con zone_id NULL,
    # no con una fila inventada.
    sin_zona = db_conn.execute(
        """
        SELECT zone_id FROM events e
        JOIN videos v ON v.id = e.video_id
        WHERE v.video_id = %(video_id)s AND e.track_id = 3
        """,
        {"video_id": video_id},
    ).fetchone()
    assert sin_zona["zone_id"] is None


def test_reimportar_no_duplica_filas(tmp_path, video_id, db_conn):
    """El caso central de la idempotencia: dos corridas seguidas dejan
    exactamente el mismo numero de filas, no el doble."""
    output_dir, zones_dir, eventos = _preparar_archivos(tmp_path, video_id)

    import_video(video_id, output_dir=output_dir, zones_dir=zones_dir)
    import_video(video_id, output_dir=output_dir, zones_dir=zones_dir)

    conteo = db_conn.execute(
        """
        SELECT
            (SELECT count(*) FROM events e  JOIN videos v ON v.id = e.video_id  WHERE v.video_id = %(id)s) AS eventos,
            (SELECT count(*) FROM metrics m JOIN videos v ON v.id = m.video_id WHERE v.video_id = %(id)s) AS metricas,
            (SELECT count(*) FROM videos WHERE video_id = %(id)s) AS videos
        """,
        {"id": video_id},
    ).fetchone()
    assert conteo["eventos"] == len(eventos)
    assert conteo["metricas"] == 1
    assert conteo["videos"] == 1


def test_evento_con_zona_desconocida_falla_con_mensaje_claro(tmp_path, video_id):
    output_dir, zones_dir, eventos = _preparar_archivos(tmp_path, video_id)

    # Se anade un evento que referencia un estante que NO esta en el
    # archivo de zonas: debe fallar en la importacion, no colarse.
    eventos.append(_evento(video_id, 150, 4, f"{video_id}_gondola_A", "estante_fantasma"))
    write_events(output_dir / f"{video_id}.interact.jsonl", eventos)

    with pytest.raises(ImporterError, match="estante_fantasma"):
        import_video(video_id, output_dir=output_dir, zones_dir=zones_dir)


def test_archivos_faltantes_falla_con_mensaje_claro(tmp_path, video_id):
    with pytest.raises(ImporterError, match="Faltan archivos"):
        import_video(video_id, output_dir=tmp_path / "vacio", zones_dir=tmp_path / "vacio")


def test_fps_no_derivable_requiere_override(tmp_path, video_id):
    """Si todos los eventos estan en el frame 0 (clip brevisimo), no se
    pueden derivar los fps de los timestamps: hace falta --fps."""
    output_dir, zones_dir, _ = _preparar_archivos(tmp_path, video_id)
    gondola_id = f"{video_id}_gondola_A"
    solo_frame_cero = [_evento(video_id, 0, 1, gondola_id, "estante_1")]
    write_events(output_dir / f"{video_id}.interact.jsonl", solo_frame_cero)

    # Un solo evento, un solo track, sin interaccion ni dwell registrado:
    #   people_count = 1, interaction_count = pick_up_count = put_back_count = 0
    #   average_dwell_time_s = None (no hay ningun dwell_time que promediar)
    #   interaction_rate = 0/1 = 0.0, pick_up_rate = None (0 interacciones,
    #   division indefinida), conversion_rate = 0/1 = 0.0
    (output_dir / f"{video_id}.metrics.json").write_text(
        json.dumps({
            "contract_version": "1.0.0",
            "video_id": video_id,
            "zones": {
                gondola_id: {
                    "people_count": 1,
                    "interaction_count": 0,
                    "pick_up_count": 0,
                    "put_back_count": 0,
                    "average_dwell_time_s": None,
                    "interaction_rate": 0.0,
                    "pick_up_rate": None,
                    "conversion_rate": 0.0,
                },
            },
        }),
        encoding="utf-8",
    )

    with pytest.raises(ImporterError, match="fps"):
        import_video(video_id, output_dir=output_dir, zones_dir=zones_dir)

    # Con --fps explicito, si funciona.
    resumen = import_video(video_id, output_dir=output_dir, zones_dir=zones_dir, fps_override=30.0)
    assert resumen.fps_derivados == 30.0
