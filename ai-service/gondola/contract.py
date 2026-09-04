"""Contrato de datos: el unico formato que hablan todas las etapas.

Un `Event` es una persona detectada en un frame. Las etapas posteriores lo
ENRIQUECEN (rellenan sus campos), nunca crean formatos nuevos.

    detection                 -> Persona 2 (deteccion YOLO)
    track_id                  -> Persona 3 (seguimiento)
    zone, metrics.dwell_time  -> Persona 4 (zonas y permanencia)
    interaction               -> Persona 5 (interaccion con productos)

PRIVACIDAD POR DISENO: aqui no hay ni habra campos de edad, genero, rostro,
identidad, emocion ni biometria. Como todos los modelos usan `extra="forbid"`,
anadir uno no es una discusion de equipo: es un error de validacion inmediato.
"""

from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from gondola.errors import ContractError

CONTRACT_VERSION = "1.0.0"
"""Version del contrato. Si cambia la forma del evento, sube este numero y
avisa al equipo: los .jsonl viejos dejan de ser compatibles."""


class InteractionEvent(str, Enum):
    """Tipos de interaccion fisica con la gondola (los rellena la Persona 5)."""

    APPROACH = "APPROACH"  # la persona se acerca a la gondola
    PICK_UP = "PICK_UP"    # toma un producto del estante
    PUT_BACK = "PUT_BACK"  # devuelve un producto al estante


class BBox(BaseModel):
    """Caja que rodea a la persona detectada, en PIXELES de la imagen.

    OJO: `width` y `height` son el ancho y el alto DE LA CAJA en pixeles.
    NO son la estatura, ni el peso, ni ninguna caracteristica de la persona.
    Una misma persona da cajas distintas segun que tan lejos este de la camara.
    """

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, description="Borde izquierdo de la caja, en pixeles")
    y: float = Field(ge=0, description="Borde superior de la caja, en pixeles")
    width: float = Field(gt=0, description="Ancho de la caja, en pixeles")
    height: float = Field(gt=0, description="Alto de la caja, en pixeles")

    @property
    def support_point(self) -> tuple[float, float]:
        """Punto de apoyo: centro del borde inferior de la caja (los pies).

        Aproxima donde la persona toca el piso. Es el punto correcto para
        ubicarla en el plano de la tienda, porque el centro de la caja "flota"
        a la altura del pecho y falsea las distancias a la gondola.
        """
        return (self.x + self.width / 2, self.y + self.height)


class Detection(BaseModel):
    """Que se detecto y con cuanta certeza. La rellena la Persona 2 (YOLO)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # `class` es palabra reservada de Python, asi que el atributo se llama
    # `class_name`, pero entra y sale del JSON como "class" gracias al alias.
    class_name: str = Field(default="person", alias="class")
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BBox


class Zone(BaseModel):
    """Donde esta la persona dentro de la tienda. La rellena la Persona 4."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str | None = Field(default=None, description="Ej: 'gondola_A'")
    segment: str | None = Field(default=None, description="Ej: 'estante_2'")


class Interaction(BaseModel):
    """Interaccion con un producto. La rellena la Persona 5."""

    model_config = ConfigDict(extra="forbid")

    event: InteractionEvent | None = None
    product_zone: str | None = Field(default=None, description="Ej: 'bebidas'")


class Metrics(BaseModel):
    """Metricas derivadas del evento. `dwell_time` lo rellena la Persona 4."""

    model_config = ConfigDict(extra="forbid")

    dwell_time: float | None = Field(
        default=None, ge=0, description="Segundos acumulados en la zona"
    )


class Event(BaseModel):
    """Una persona detectada en un frame. La unidad de informacion del sistema."""

    model_config = ConfigDict(extra="forbid")

    video_id: str
    frame: int = Field(ge=0, description="Numero de frame dentro del video")
    timestamp: float = Field(ge=0, description="Segundos desde el inicio del video")
    track_id: int | None = Field(
        default=None, description="Id temporal de seguimiento (Persona 3)"
    )
    detection: Detection
    zone: Zone = Field(default_factory=Zone)
    interaction: Interaction = Field(default_factory=Interaction)
    metrics: Metrics = Field(default_factory=Metrics)

    def to_jsonl(self) -> str:
        """Serializa el evento a UNA linea de JSON (sin salto de linea final).

        Usa `by_alias=True` para que el campo salga como "class" y no como
        "class_name". Siempre serializa con este metodo, nunca con
        `json.dumps(evento.model_dump())` a pelo.
        """
        return json.dumps(self.model_dump(by_alias=True), ensure_ascii=False)

    @classmethod
    def from_jsonl(cls, line: str) -> "Event":
        """Lee un evento desde una linea de JSON y lo valida contra el contrato."""
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(
                f"La linea no es JSON valido ({exc.msg} en la posicion {exc.pos}). "
                "Revisa que el archivo tenga UN evento completo por linea y que "
                "se haya escrito con Event.to_jsonl()."
            ) from exc
        return cls.model_validate(data)
