"""Etapa final: metricas agregadas por gondola. Responsable:
 Persona 6 toco a la  7 pq no lo hicieron!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1111111111111111.

QUE HACE
--------
Lee TODOS los eventos de <video_id>.interact.jsonl (ya con zona, track_id e
interaccion resueltos por las etapas anteriores) y produce UN JSON con los
agregados por gondola: cuanta gente paso, cuantas interacciones hubo, cuantos
productos se tomaron y devolvieron, y la permanencia promedio.

Comando: python -m gondola metrics
Entrada: <video_id>.interact.jsonl  (la produce la etapa 'interact')
Salida:  <video_id>.metrics.json    (la lee backend/importer.py, Persona 7)

LA TRAMPA QUE ESTE MODULO TIENE QUE EVITAR
-------------------------------------------
Un mismo track_id aparece en CIENTOS de eventos, uno por cada frame en el
que esa persona fue detectada. Para "cuanta gente paso" hay que contar
IDENTIFICADORES DISTINTOS (`len(set(track_ids))`), JAMAS numero de filas.
Si se cuentan filas, el flujo sale muchisimas veces mas grande que la
realidad: una tienda por la que pasaron 3 personas mostraria "3801 personas".

Lo mismo con la permanencia: dwell_time_s es un valor ACUMULADO que se repite
en muchos eventos de la misma persona (crece con el tiempo). Promediar TODAS
las filas cuenta el mismo recorrido cientos de veces y desvirtua el numero.
Aqui se toma, para cada (track_id, zone_id), el dwell_time_s MAXIMO visto
(el ultimo acumulado, que es el tiempo real que esa persona estuvo ahi), y
se promedian esos maximos, uno por persona.

QUE ZONA SE USA PARA AGRUPAR
-----------------------------
Cada evento aporta a DOS filas a la vez (cuando trae estante): la de su
GONDOLA completa (evento.zone.zone_id) y la de su ESTANTE dentro de esa
gondola (evento.zone.zone_id + evento.zone.segment). La fila de la gondola
es la suma de todos sus estantes (mas los eventos sin segment, alguien
frente a la gondola sin que el tracker lo ubique en un estante concreto):
sirve para el total de la vitrina; las filas de estante son las que
permiten comparar, por ejemplo, "Cereales" contra "Snacks y pasabocas"
dentro de la misma gondola_A.

El identificador de fila para un estante es "<zone_id de la gondola>:<segment>"
(ej. "gondola_A:estante_2") -exactamente la misma convencion que ya usa
`backend/importer.py` en `_zone_id_de_estante()| para construir el zone_id
unico de esa fila en la tabla `zones`-. Si aqui se usara un identificador
distinto, el importador nunca encontraria una fila de metrics que le
haga match a su zona de estante, y volveria a pasar lo mismo que este
cambio arregla: `GET /videos/{id}/zones` (que hace INNER JOIN con
`metrics`, ver `backend/db.py:list_zones_for_video`) solo devolveria la
gondola, nunca sus estantes.

Eventos con zone.zone_id en null (alguien en un pasillo, entre gondolas) no
se pierden de vista: se cuentan aparte, en 'sin_zona', y se informan en la
salida por pantalla, pero no generan ninguna fila de metrics (la tabla
exige un zone_id valido).

POR QUE NO SE IMPORTA NADA PESADO
-----------------------------------
Esta etapa es aritmetica pura sobre lo que ya escribieron las etapas
anteriores: no toca video, no toca YOLO, no toca PostgreSQL (el pipeline de
vision NUNCA escribe en la base de datos, ver docs/architecture.md). Por eso
no hace falta el patron de "imports pesados dentro de la funcion" que usa
detect.py: aqui no hay ningun import pesado.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from gondola import pipeline
from gondola.config import Config
from gondola.contract import CONTRACT_VERSION
from gondola.jsonl import read_events


@dataclass
class _AgregadoZona:
    """Acumuladores en crudo para UNA gondola, mientras se recorre el archivo.

    Todo lo que aqui es un set() o un dict() existe para no repetir el error
    de contar filas: se guardan IDENTIFICADORES, y al final se cuenta cuantos
    hay, no cuantas veces aparecieron.
    """

    track_ids: set[int] = field(default_factory=set)
    interaction_count: int = 0
    pick_up_count: int = 0
    put_back_count: int = 0
    # dwell_time_s MAXIMO visto por cada track_id en esta zona. Un dict, no
    # una lista: si el mismo track_id aparece 500 veces, solo interesa su
    # valor mas alto, no las 500 filas.
    dwell_maximo_por_persona: dict[int, float] = field(default_factory=dict)


@dataclass
class Resumen:
    """Lo que se informa por pantalla al terminar. Los MISMOS numeros que
    quedan en el JSON, para que sea imposible que la consola diga una cosa
    y el archivo diga otra."""

    eventos_leidos: int = 0
    zonas_con_datos: int = 0
    eventos_sin_zona: int = 0
    personas_totales: int = 0


# --------------------------------------------------------------------------
# Logica pura: se prueba con eventos construidos a mano, sin archivos.
# --------------------------------------------------------------------------

SEPARADOR_ESTANTE = ":"  # igual que backend/importer.py:_zone_id_de_estante


def _sumar_a_fila(agregados: dict[str, _AgregadoZona], fila_id: str, evento) -> None:
    """Suma un evento a UNA fila (gondola o estante). Compartida entre las
    dos filas a las que puede aportar un mismo evento -ver acumular_evento-
    para no repetir la aritmetica dos veces."""
    zona = agregados.setdefault(fila_id, _AgregadoZona())

    if evento.track_id is not None:
        zona.track_ids.add(evento.track_id)
        if evento.metrics.dwell_time is not None:
            actual = zona.dwell_maximo_por_persona.get(evento.track_id, 0.0)
            if evento.metrics.dwell_time > actual:
                zona.dwell_maximo_por_persona[evento.track_id] = evento.metrics.dwell_time

    if evento.interaction.event is not None:
        zona.interaction_count += 1
        valor = evento.interaction.event.value
        if valor == "PICK_UP":
            zona.pick_up_count += 1
        elif valor == "PUT_BACK":
            zona.put_back_count += 1


def acumular_evento(agregados: dict[str, _AgregadoZona], evento, resumen: Resumen) -> None:
    """Suma un evento a su gondola y, si trae estante, tambien a la fila de
    ese estante. Si no tiene ni zona, solo se cuenta aparte (ver
    'sin_zona' en Resumen).

    Eventos sin track_id (una deteccion que el tracker todavia no engancho a
    nadie, ver Persona 3) no aportan a people_count ni a dwell, pero SI
    pueden aportar a interaction_count si de casualidad trajeran una
    interaccion (en la practica no deberia pasar, pero no se asume).
    """
    resumen.eventos_leidos += 1

    zone_id = evento.zone.zone_id
    if zone_id is None:
        resumen.eventos_sin_zona += 1
        return

    _sumar_a_fila(agregados, zone_id, evento)

    segment = evento.zone.segment
    if segment is not None:
        _sumar_a_fila(agregados, f"{zone_id}{SEPARADOR_ESTANTE}{segment}", evento)


def _tasa(numerador: int, denominador: int) -> float | None:
    """Una tasa entre 0 y 1, o None si no hay base para calcularla.

    Acotada a 1.0 a proposito: metrics.interaction_rate/pick_up_rate/
    conversion_rate tienen un CHECK (... BETWEEN 0 AND 1) en schema.sql. Un
    PUT_BACK de algo tomado fuera de la ventana puede hacer que, en teoria,
    un conteo supere a otro; recortar aqui evita que el INSERT de la Persona
    7 se rompa por una tasa de 1.3.
    """
    if denominador <= 0:
        return None
    return round(min(1.0, numerador / denominador), 4)


def cerrar_zona(zona: _AgregadoZona) -> dict:
    """Convierte los acumuladores en crudo de una gondola en las columnas
    exactas que espera backend/importer.py (y, detras, metrics.people_count
    etc. de schema.sql)."""
    people_count = len(zona.track_ids)  # DISTINCT, nunca len(filas)

    average_dwell_time_s = None
    if zona.dwell_maximo_por_persona:
        valores = zona.dwell_maximo_por_persona.values()
        average_dwell_time_s = round(sum(valores) / len(valores), 3)

    return {
        "people_count": people_count,
        "interaction_count": zona.interaction_count,
        "pick_up_count": zona.pick_up_count,
        "put_back_count": zona.put_back_count,
        "average_dwell_time_s": average_dwell_time_s,
        "interaction_rate": _tasa(zona.interaction_count, people_count),
        "pick_up_rate": _tasa(zona.pick_up_count, zona.interaction_count),
        "conversion_rate": _tasa(zona.pick_up_count, people_count),
    }


# --------------------------------------------------------------------------
# Punto de entrada de la etapa
# --------------------------------------------------------------------------

def run(cfg: Config) -> int:
    """Ejecuta el calculo completo. Devuelve el codigo de salida.

    En STREAMING: se recorre interact.jsonl una vez, evento por evento, sin
    cargar el archivo entero en memoria (puede tener decenas de miles de
    lineas). Solo se acumulan sets/dicts pequenos, uno por gondola.
    """
    rutas = pipeline.stage_paths("metrics", cfg)
    pipeline.require_input("metrics", cfg)

    print(f"[metrics] Entrada: {rutas.input_path}")

    agregados: dict[str, _AgregadoZona] = {}
    resumen = Resumen()

    for evento in read_events(rutas.input_path):
        acumular_evento(agregados, evento, resumen)

    zonas_json = {zone_id: cerrar_zona(zona) for zone_id, zona in agregados.items()}
    resumen.zonas_con_datos = len(zonas_json)
    resumen.personas_totales = len({tid for z in agregados.values() for tid in z.track_ids})

    salida = {
        "contract_version": CONTRACT_VERSION,
        "stage": "metrics",
        "video_id": cfg.video_id,
        "zones": zonas_json,
    }

    rutas.output_path.parent.mkdir(parents=True, exist_ok=True)
    rutas.output_path.write_text(
        json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    _imprimir_resultado(resumen, zonas_json, rutas.output_path)
    return 0


def _imprimir_resultado(resumen: Resumen, zonas_json: dict, destino: Path) -> None:
    print()
    print("-" * 66)
    print(f"  Eventos leidos          {resumen.eventos_leidos}")
    print(f"  Zonas con datos         {resumen.zonas_con_datos}")
    print(f"  Personas distintas      {resumen.personas_totales}")
    if resumen.eventos_sin_zona:
        print(f"  Eventos sin zona        {resumen.eventos_sin_zona}  "
              f"(gente en pasillos, entre gondolas: no generan fila de metrics)")
    print("-" * 66)
    for zone_id, agregado in zonas_json.items():
        print(f"  [{zone_id}]")
        print(f"      personas={agregado['people_count']}  "
              f"interacciones={agregado['interaction_count']}  "
              f"pick_up={agregado['pick_up_count']}  "
              f"put_back={agregado['put_back_count']}  "
              f"dwell_prom={agregado['average_dwell_time_s']}")
    print("-" * 66)
    print(f"  Metricas  {destino}")
    print()
    print("  Siguiente paso:  importar a PostgreSQL (Persona 7)")
    print("    cd backend && python importer.py --video-id <video_id>")
