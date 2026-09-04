"""Formato y validacion del archivo de zonas. Responsable: Persona 4.

FASE 1 (diseno): este modulo SOLO define el formato del archivo y lo valida.
La logica que decide en que zona cae una persona (comparar `support_point`
contra estos rectangulos) y la que acumula `dwell_time` viven en
`gondola/stages/zones.py`, todavia sin escribir. Este modulo no las
adelanta a proposito: eso se discute y se implementa despues.

QUE ES ESTE ARCHIVO Y POR QUE NO ES gondola/config.py
-------------------------------------------------------
`gondola/config.py` lee ajustes del PIPELINE (.env): umbrales, rutas, modo de
render. El archivo de zonas es otra cosa: describe la CAMARA de una tienda
concreta -donde estan sus gondolas y estantes, en pixeles-. Cambia con cada
camara y cada tienda, y quien lo edita (monte la camara, o alguien de
Scapder) no tiene por que tocar Python para mover una estanteria. Por eso
vive en un archivo de datos aparte, no en variables de entorno ni
hardcodeado en el codigo (ver docs/zones-format.md).

POR QUE JSON Y NO YAML
-----------------------
YAML se lee mejor a mano (admite comentarios), pero el proyecto no tiene hoy
ninguna dependencia de YAML, y todo lo demas -el contrato, los resumenes de
cada etapa- ya se valida con Pydantic sobre JSON. Anadir PyYAML solo para
este archivo es una libreria mas que instalar para las 8 personas, a cambio
de comentarios que se pueden poner igual en el campo "name" de cada zona.
Se prefirio seguir con lo que el proyecto ya usa en todas partes.

QUE ES "floor_zone" Y POR QUE NO ES UNA CAJA COMO detection.bbox
-------------------------------------------------------------------
Por la Decision 1 de esta fase de diseno (ver docs/data-contract.md,
`BBox.support_point`): a una persona se le ubica por sus PIES, no por el
centro de su caja. Eso significa que el rectangulo de una zona tiene que
representar el AREA DEL PISO frente al estante -por donde camina y se para
la gente-, no el area donde estan los productos en la imagen (que en una
camara cenital/inclinada como la de este proyecto queda arriba, pegada a la
pared). Si "floor_zone" fuera el rectangulo del producto, ningun
`support_point` caeria nunca dentro: los pies de una persona jamas pisan el
estante.

Por eso tampoco se reutiliza `gondola.contract.BBox` aqui: aunque las dos
formas son "x, y, width, height en pixeles", `BBox` pertenece al CONTRATO de
datos (la caja que YOLO dibuja alrededor de una persona) y mezclar los dos
conceptos en una sola clase haria mas dificil ver donde termina el contrato
y donde empieza la calibracion de camara. `FloorZone` es una clase propia,
mas pequena, con el mismo shape mas no el mismo significado.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from gondola.errors import ZonesConfigError


class FloorZone(BaseModel):
    """Rectangulo en pixeles del AREA DE PISO frente a un estante.

    Mismo sistema de coordenadas que `detection.bbox` (ver
    docs/data-contract.md): origen (0,0) arriba a la izquierda, x crece
    hacia la derecha, y crece hacia ABAJO.
    """

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, description="Borde izquierdo del area, en pixeles")
    y: float = Field(ge=0, description="Borde superior del area, en pixeles")
    width: float = Field(gt=0, description="Ancho del area, en pixeles")
    height: float = Field(gt=0, description="Alto del area, en pixeles")


class Shelf(BaseModel):
    """Un estante: un segmento de la gondola, con su propia area de piso.

    `segment` es EXACTAMENTE lo que va a salir en `zone.segment` del
    contrato de datos. Solo tiene que ser unico DENTRO de su gondola, no en
    todo el archivo: dos gondolas distintas pueden tener cada una un
    "estante_1" sin chocar, porque el contrato siempre los acompana de su
    `zone_id`.
    """

    model_config = ConfigDict(extra="forbid")

    segment: str = Field(min_length=1, description="Ej: 'estante_2'. Sale tal cual en zone.segment")
    name: str = Field(min_length=1, description="Nombre legible, para el dashboard")
    product_category: str | None = Field(
        default=None, description="Ej: 'bebidas'. Si falta, hereda el de la gondola"
    )
    floor_zone: FloorZone


class Gondola(BaseModel):
    """Una gondola: uno o mas estantes.

    `zone_id` es exactamente lo que va a salir en `zone.zone_id` del
    contrato, y tiene que ser unico en TODO el archivo: distintas gondolas
    (incluso de distintas camaras si algun dia se combinan varios archivos)
    no pueden compartirlo.
    """

    model_config = ConfigDict(extra="forbid")

    zone_id: str = Field(min_length=1, description="Ej: 'gondola_A'. Sale tal cual en zone.zone_id")
    name: str = Field(min_length=1, description="Nombre legible, para el dashboard")
    product_category: str | None = Field(
        default=None, description="Categoria por defecto de sus estantes, ej: 'bebidas'"
    )
    shelves: list[Shelf] = Field(min_length=1, description="Al menos un estante")

    @model_validator(mode="after")
    def _segmentos_unicos(self) -> "Gondola":
        segmentos = [estante.segment for estante in self.shelves]
        repetidos = sorted({s for s in segmentos if segmentos.count(s) > 1})
        if repetidos:
            raise ValueError(
                f"la gondola {self.zone_id!r} repite el/los segment {repetidos}. "
                "Cada estante de una misma gondola necesita un 'segment' distinto."
            )
        return self


class ZonesConfig(BaseModel):
    """El archivo de zonas completo: la calibracion de UNA camara/video.

    `video_id` liga el archivo a un video concreto (igual que `VIDEO_ID` en
    `.env`), y `frame_width`/`frame_height` son el tamano de frame para el
    que se calibraron las coordenadas: sirven para detectar en el momento
    -no tres etapas despues- que alguien copio un archivo de zonas de otra
    camara con otra resolucion.
    """

    model_config = ConfigDict(extra="forbid")

    video_id: str = Field(min_length=1)
    frame_width: int = Field(gt=0, description="Ancho del frame para el que se calibro, en pixeles")
    frame_height: int = Field(gt=0, description="Alto del frame para el que se calibro, en pixeles")
    gondolas: list[Gondola] = Field(min_length=1, description="Al menos una gondola")

    @model_validator(mode="after")
    def _zone_ids_unicos(self) -> "ZonesConfig":
        ids = [gondola.zone_id for gondola in self.gondolas]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            raise ValueError(
                f"zone_id repetido(s): {repetidos}. Cada gondola necesita un "
                "zone_id distinto en todo el archivo."
            )
        return self

    @model_validator(mode="after")
    def _zonas_dentro_del_frame(self) -> "ZonesConfig":
        for gondola in self.gondolas:
            for estante in gondola.shelves:
                z = estante.floor_zone
                if z.x + z.width > self.frame_width or z.y + z.height > self.frame_height:
                    raise ValueError(
                        f"{gondola.zone_id}/{estante.segment}: su floor_zone "
                        f"(x={z.x}, y={z.y}, width={z.width}, height={z.height}) "
                        f"se sale del frame declarado ({self.frame_width}x{self.frame_height}). "
                        "Revisa las coordenadas, o frame_width/frame_height si la camara cambio."
                    )
        return self

    def shelves(self) -> list[tuple[Gondola, Shelf]]:
        """Todos los (gondola, estante) del archivo, aplanados.

        Existe para que quien recorra el archivo (por ejemplo, la
        herramienta de dibujo) no repita el mismo doble bucle en cada sitio
        que lo necesite. No decide nada sobre asignacion de personas: solo
        aplana una lista.
        """
        return [(gondola, estante) for gondola in self.gondolas for estante in gondola.shelves]


def load_zones_config(path: Path) -> ZonesConfig:
    """Lee y valida un archivo de zonas. Lanza `ZonesConfigError` con que corregir."""
    if not path.exists():
        raise ZonesConfigError(
            f"No encuentro el archivo de zonas en:\n    {path}\n\n"
            f"Que hacer: copia data/zones/video_001.example.json y ajusta las "
            f"coordenadas a tu video (ver docs/zones-format.md)."
        )
    try:
        datos = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ZonesConfigError(
            f"{path.name} no es JSON valido ({exc.msg} en la posicion {exc.pos})."
        ) from exc
    try:
        return ZonesConfig.model_validate(datos)
    except ValidationError as exc:
        raise ZonesConfigError(
            f"{path.name} no cumple el formato de zonas (ver docs/zones-format.md):\n{exc}"
        ) from exc
