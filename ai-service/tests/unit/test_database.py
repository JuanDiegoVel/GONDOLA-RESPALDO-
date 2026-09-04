"""Tests del esquema SQL (backend/database/).

NO necesitan PostgreSQL: leen los .sql como texto. Lo que vigilan es que la
tabla `events` siga siendo el espejo de `gondola/contract.py`. El esquema y el
contrato los tocan personas distintas (Persona 7 y Persona 1) en semanas
distintas: sin este test, se separan sin que nadie se entere hasta que la
importacion falle con datos de verdad.
"""

import re

import pytest
from pydantic import BaseModel

from gondola.config import RAIZ
from gondola.contract import Event, InteractionEvent
from gondola.verify.verifier import FRAGMENTOS_PROHIBIDOS

ESQUEMA = (RAIZ / "backend" / "database" / "schema.sql").read_text(encoding="utf-8")
SEED = (RAIZ / "backend" / "database" / "seed_example.sql").read_text(encoding="utf-8")

# Cada campo del contrato y la columna de `events` donde aterriza. El nombre
# cambia (frame -> frame_number) porque en SQL se lee mejor; la informacion es
# exactamente la misma.
CAMPO_A_COLUMNA = {
    "video_id": "video_id",
    "frame": "frame_number",
    "timestamp": "timestamp_s",
    "track_id": "track_id",
    "detection.class": "detection_class",
    "detection.confidence": "confidence",
    "detection.bbox.x": "bbox_x",
    "detection.bbox.y": "bbox_y",
    "detection.bbox.width": "bbox_width",
    "detection.bbox.height": "bbox_height",
    "zone.zone_id": "zone_id",
    "zone.segment": "segment",
    "interaction.event": "interaction_event",
    "interaction.product_zone": "product_zone",
    "metrics.dwell_time": "dwell_time_s",
}


def campos_del_contrato(modelo=Event, prefijo="") -> set[str]:
    """Todos los campos hoja del contrato, con su ruta ('detection.bbox.x')."""
    campos = set()
    for nombre, campo in modelo.model_fields.items():
        etiqueta = prefijo + (campo.alias or nombre)
        anotacion = campo.annotation
        if isinstance(anotacion, type) and issubclass(anotacion, BaseModel):
            campos |= campos_del_contrato(anotacion, etiqueta + ".")
        else:
            campos.add(etiqueta)
    return campos


def bloque(tabla: str) -> str:
    """El texto del CREATE TABLE de una tabla."""
    inicio = ESQUEMA.index(f"CREATE TABLE {tabla} (")
    return ESQUEMA[inicio:ESQUEMA.index("\n);", inicio)]


def columnas(tabla: str) -> list[str]:
    """Los nombres de columna declarados en una tabla."""
    nombres = []
    for linea in bloque(tabla).splitlines()[1:]:
        linea = linea.strip()
        if not linea or linea.startswith("--") or linea.startswith("CONSTRAINT"):
            continue
        primera = linea.split()[0]
        if primera.isidentifier() and primera.islower():
            nombres.append(primera)
    return nombres


# --------------------------------------------------------------------------
# La tabla events es el espejo del contrato
# --------------------------------------------------------------------------

def test_el_mapa_cubre_todo_el_contrato_y_nada_mas():
    """Si el contrato gana o pierde un campo, este test obliga a mirar el esquema."""
    assert set(CAMPO_A_COLUMNA) == campos_del_contrato()


@pytest.mark.parametrize("campo,columna", sorted(CAMPO_A_COLUMNA.items()))
def test_cada_campo_del_contrato_tiene_su_columna(campo, columna):
    assert columna in columnas("events"), f"'{campo}' no tiene donde guardarse"


def test_los_tipos_de_interaccion_del_esquema_son_los_del_contrato():
    """El CHECK de SQL y el Enum de Python tienen que decir lo mismo."""
    declarados = set(re.findall(r"'([A-Z_]+)'", bloque("events")))
    assert declarados == {e.value for e in InteractionEvent}


def test_el_esquema_solo_acepta_personas():
    """Igual que el verificador: la unica clase detectada es 'person'."""
    assert "CHECK (detection_class = 'person')" in bloque("events")


# --------------------------------------------------------------------------
# Privacidad
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tabla", ["events", "metrics"])
def test_ninguna_columna_de_datos_guarda_nada_personal(tabla):
    """Las tablas que describen a quien aparece en el video no pueden tener una
    columna de edad, rostro, identidad ni ninguna otra caracteristica.

    `videos` y `zones` quedan fuera a proposito: su `name` es el nombre de un
    archivo y la etiqueta de un estante, no el de una persona.

    Se compara palabra por palabra (partiendo por '_') y no por subcadena: si
    no, `average_dwell_time_s` daria un falso positivo por el "age" de
    "average".
    """
    for columna in columnas(tabla):
        palabras = columna.lower().split("_")
        prohibido = [f for f in FRAGMENTOS_PROHIBIDOS
                     if any(p.startswith(f) for p in palabras)]
        assert not prohibido, f"{tabla}.{columna} contiene {prohibido}"


def test_borrar_un_video_arrastra_sus_eventos():
    """Es la herramienta de borrado de datos: una sentencia y no queda rastro."""
    assert "REFERENCES videos(id) ON DELETE CASCADE" in bloque("events")


# --------------------------------------------------------------------------
# Datos de ejemplo
# --------------------------------------------------------------------------

def test_el_ejemplo_solo_inserta_en_tablas_que_existen():
    creadas = set(re.findall(r"CREATE TABLE (\w+)", ESQUEMA))
    usadas = set(re.findall(r"INSERT INTO (\w+)", SEED))
    assert usadas <= creadas


def test_el_ejemplo_tiene_mas_filas_que_personas():
    """La forma de los datos reales: pocas personas, muchas filas por persona.

    Es lo que hace que people_count deba ser COUNT(DISTINCT track_id) y nunca
    COUNT(*). Si el ejemplo tuviera una fila por persona, quien lo lea se
    llevaria la idea equivocada.
    """
    eventos = SEED[SEED.index("INSERT INTO events"):]
    eventos = eventos[:eventos.index(";")]
    tracks = re.findall(r"^\s*\('[0-9a-f-]+',\s*\d+,\s*[\d.]+,\s*(\d+),",
                        eventos, re.MULTILINE)
    assert len(tracks) == 8       # ocho filas de evento
    assert len(set(tracks)) == 3  # ...pero solo tres personas
