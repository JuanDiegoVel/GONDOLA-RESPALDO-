"""Tests del formato de zonas (gondola/zones_config.py)."""

import json

import pytest

from gondola.config import RAIZ
from gondola.errors import ZonesConfigError
from gondola.zones_config import FloorZone, Gondola, Shelf, ZonesConfig, load_zones_config


def zona_de_ejemplo(**overrides) -> dict:
    """Un archivo de zonas minimo y valido: una gondola, un estante."""
    base = {
        "video_id": "video_001",
        "frame_width": 920,
        "frame_height": 680,
        "gondolas": [
            {
                "zone_id": "gondola_A",
                "name": "Gondola A",
                "product_category": None,
                "shelves": [
                    {
                        "segment": "estante_1",
                        "name": "Estante 1",
                        "product_category": "cereales",
                        "floor_zone": {"x": 100, "y": 200, "width": 300, "height": 200},
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Un archivo valido carga y conserva sus datos
# --------------------------------------------------------------------------

def test_un_archivo_valido_carga():
    zonas = ZonesConfig.model_validate(zona_de_ejemplo())
    assert zonas.video_id == "video_001"
    assert len(zonas.gondolas) == 1
    assert zonas.gondolas[0].shelves[0].segment == "estante_1"


def test_shelves_aplana_gondolas_y_estantes():
    zonas = ZonesConfig.model_validate(zona_de_ejemplo())
    aplanado = zonas.shelves()
    assert len(aplanado) == 1
    gondola, estante = aplanado[0]
    assert isinstance(gondola, Gondola)
    assert isinstance(estante, Shelf)
    assert estante.floor_zone == FloorZone(x=100, y=200, width=300, height=200)


def test_product_category_de_un_estante_es_independiente_de_la_gondola():
    """Sin herencia automatica: cada nivel dice lo suyo, o nada."""
    datos = zona_de_ejemplo()
    datos["gondolas"][0]["product_category"] = "bebidas"
    datos["gondolas"][0]["shelves"][0]["product_category"] = None
    zonas = ZonesConfig.model_validate(datos)
    assert zonas.gondolas[0].product_category == "bebidas"
    assert zonas.gondolas[0].shelves[0].product_category is None


# --------------------------------------------------------------------------
# Reglas de unicidad
# --------------------------------------------------------------------------

def test_dos_gondolas_con_el_mismo_zone_id_falla():
    datos = zona_de_ejemplo()
    segunda = json.loads(json.dumps(datos["gondolas"][0]))  # copia independiente
    datos["gondolas"].append(segunda)  # mismo zone_id "gondola_A"
    with pytest.raises(Exception):
        ZonesConfig.model_validate(datos)


def test_dos_estantes_con_el_mismo_segment_en_la_misma_gondola_falla():
    datos = zona_de_ejemplo()
    otro_estante = json.loads(json.dumps(datos["gondolas"][0]["shelves"][0]))
    datos["gondolas"][0]["shelves"].append(otro_estante)  # mismo segment "estante_1"
    with pytest.raises(Exception):
        ZonesConfig.model_validate(datos)


def test_el_mismo_segment_en_dos_gondolas_distintas_no_choca():
    """'estante_1' puede repetirse entre gondolas: el contrato lo acompana de zone_id."""
    datos = zona_de_ejemplo()
    segunda = json.loads(json.dumps(datos["gondolas"][0]))
    segunda["zone_id"] = "gondola_B"
    datos["gondolas"].append(segunda)
    zonas = ZonesConfig.model_validate(datos)
    assert len(zonas.gondolas) == 2


# --------------------------------------------------------------------------
# La zona tiene que caber dentro del frame calibrado
# --------------------------------------------------------------------------

def test_una_zona_que_se_sale_del_frame_falla():
    datos = zona_de_ejemplo()
    datos["gondolas"][0]["shelves"][0]["floor_zone"] = {
        "x": 800, "y": 200, "width": 300, "height": 200,  # 800+300 > frame_width=920
    }
    with pytest.raises(Exception):
        ZonesConfig.model_validate(datos)


# --------------------------------------------------------------------------
# extra="forbid": ningun campo fuera de formato pasa en silencio
# --------------------------------------------------------------------------

def test_un_campo_desconocido_falla():
    datos = zona_de_ejemplo()
    datos["gondolas"][0]["altura_metros"] = 1.8  # dato fisico prohibido, ademas de invalido
    with pytest.raises(Exception):
        ZonesConfig.model_validate(datos)


def test_sin_gondolas_falla():
    datos = zona_de_ejemplo(gondolas=[])
    with pytest.raises(Exception):
        ZonesConfig.model_validate(datos)


def test_una_gondola_sin_estantes_falla():
    datos = zona_de_ejemplo()
    datos["gondolas"][0]["shelves"] = []
    with pytest.raises(Exception):
        ZonesConfig.model_validate(datos)


# --------------------------------------------------------------------------
# load_zones_config: lectura de archivo, con errores que dicen que hacer
# --------------------------------------------------------------------------

def test_load_zones_config_lee_un_archivo_valido(tmp_path):
    ruta = tmp_path / "zonas.json"
    ruta.write_text(json.dumps(zona_de_ejemplo()), encoding="utf-8")
    zonas = load_zones_config(ruta)
    assert zonas.video_id == "video_001"


def test_load_zones_config_archivo_inexistente_falla_con_zones_config_error(tmp_path):
    with pytest.raises(ZonesConfigError):
        load_zones_config(tmp_path / "no_existe.json")


def test_load_zones_config_json_corrupto_falla_con_zones_config_error(tmp_path):
    ruta = tmp_path / "zonas.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    with pytest.raises(ZonesConfigError):
        load_zones_config(ruta)


def test_load_zones_config_formato_invalido_falla_con_zones_config_error(tmp_path):
    ruta = tmp_path / "zonas.json"
    ruta.write_text(json.dumps(zona_de_ejemplo(gondolas=[])), encoding="utf-8")
    with pytest.raises(ZonesConfigError):
        load_zones_config(ruta)


# --------------------------------------------------------------------------
# El archivo de ejemplo del repositorio tiene que ser valido de verdad
# --------------------------------------------------------------------------

def test_el_archivo_de_ejemplo_del_repositorio_es_valido():
    ruta = RAIZ / "data" / "zones" / "video_001.example.json"
    zonas = load_zones_config(ruta)
    assert zonas.video_id == "video_001"
    assert len(zonas.shelves()) >= 1
