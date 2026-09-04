"""Tests del contrato de datos (gondola/contract.py)."""

import json

import pytest
from pydantic import ValidationError

from gondola.contract import (
    CONTRACT_VERSION,
    BBox,
    Detection,
    Event,
    InteractionEvent,
)
from gondola.errors import ContractError


def evento_de_ejemplo() -> Event:
    """Un evento recien salido de la deteccion: solo `detection` esta lleno."""
    return Event(
        video_id="video_001",
        frame=253,
        timestamp=8.43,
        detection=Detection(confidence=0.94, bbox=BBox(x=145, y=40, width=90, height=150)),
    )


def test_existe_version_del_contrato():
    """La version debe existir y ser un texto no vacio."""
    assert isinstance(CONTRACT_VERSION, str)
    assert CONTRACT_VERSION


def test_campos_sin_rellenar_nacen_en_none():
    """Un evento recien detectado tiene vacio lo que rellenan las otras etapas."""
    evento = evento_de_ejemplo()
    assert evento.track_id is None
    assert evento.zone.zone_id is None
    assert evento.zone.segment is None
    assert evento.interaction.event is None
    assert evento.interaction.product_zone is None
    assert evento.metrics.dwell_time is None


def test_serializa_a_una_sola_linea():
    """to_jsonl() debe producir UNA linea: los .jsonl son un evento por linea."""
    linea = evento_de_ejemplo().to_jsonl()
    assert "\n" not in linea


def test_el_campo_class_sale_como_class_en_el_json():
    """En Python el atributo es `class_name`, pero en el JSON debe decir "class"."""
    datos = json.loads(evento_de_ejemplo().to_jsonl())
    assert datos["detection"]["class"] == "person"
    assert "class_name" not in datos["detection"]


def test_ida_y_vuelta_conserva_todo():
    """Serializar y volver a leer debe devolver un evento identico."""
    original = evento_de_ejemplo()
    recuperado = Event.from_jsonl(original.to_jsonl())
    assert recuperado == original


def test_ida_y_vuelta_con_el_evento_ya_enriquecido():
    """Igual que el anterior, pero con todos los campos rellenos por las 4 etapas."""
    evento = evento_de_ejemplo()
    evento.track_id = 7
    evento.zone.zone_id = "gondola_A"
    evento.zone.segment = "estante_2"
    evento.interaction.event = InteractionEvent.PICK_UP
    evento.interaction.product_zone = "bebidas"
    evento.metrics.dwell_time = 12.5

    datos = json.loads(evento.to_jsonl())
    assert datos["interaction"]["event"] == "PICK_UP"  # el enum sale como texto
    assert Event.from_jsonl(evento.to_jsonl()) == evento


def test_un_campo_inventado_falla_la_validacion():
    """extra="forbid": si alguien inventa un campo, revienta en SU maquina."""
    with pytest.raises(ValidationError):
        Event(
            video_id="video_001",
            frame=1,
            timestamp=0.0,
            detection=Detection(confidence=0.9, bbox=BBox(x=0, y=0, width=10, height=20)),
            edad=30,  # type: ignore[call-arg]
        )


def test_un_campo_prohibido_de_biometria_falla():
    """Privacidad por diseno: no se puede colar un campo de rostro ni aunque se intente."""
    linea = json.dumps(
        {
            "video_id": "video_001",
            "frame": 1,
            "timestamp": 0.0,
            "track_id": None,
            "detection": {
                "class": "person",
                "confidence": 0.9,
                "bbox": {"x": 0, "y": 0, "width": 10, "height": 20},
                "face_embedding": [0.1, 0.2],
            },
            "zone": {"zone_id": None, "segment": None},
            "interaction": {"event": None, "product_zone": None},
            "metrics": {"dwell_time": None},
        }
    )
    with pytest.raises(ValidationError):
        Event.from_jsonl(linea)


def test_una_confianza_imposible_falla():
    """La confianza es una probabilidad: tiene que estar entre 0 y 1."""
    with pytest.raises(ValidationError):
        Detection(confidence=1.5, bbox=BBox(x=0, y=0, width=10, height=20))


def test_una_caja_sin_ancho_falla():
    """Una caja de ancho 0 no rodea a nadie: es un error de la etapa anterior."""
    with pytest.raises(ValidationError):
        BBox(x=0, y=0, width=0, height=20)


def test_una_linea_rota_lanza_error_del_proyecto():
    """Un JSON mal formado debe dar ContractError, no un error crudo de libreria."""
    with pytest.raises(ContractError):
        Event.from_jsonl("{esto no es json")


def test_el_punto_de_apoyo_es_el_centro_del_borde_inferior():
    """Los pies: centro horizontal (x + ancho/2) y borde de abajo (y + alto)."""
    caja = BBox(x=145, y=40, width=90, height=150)
    assert caja.support_point == (190.0, 190.0)


def test_el_punto_de_apoyo_no_es_el_centro_de_la_caja():
    """Comprobacion explicita: el centro "flota" al pecho y falsearia la distancia."""
    caja = BBox(x=0, y=0, width=100, height=200)
    centro = (caja.x + caja.width / 2, caja.y + caja.height / 2)
    assert caja.support_point == (50.0, 200.0)
    assert caja.support_point != centro


def test_el_punto_de_apoyo_no_se_serializa():
    """Es una propiedad calculada, no un campo: no debe ensuciar el JSON."""
    datos = json.loads(evento_de_ejemplo().to_jsonl())
    assert "support_point" not in datos["detection"]["bbox"]
