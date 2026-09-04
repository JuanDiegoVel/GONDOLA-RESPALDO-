"""Verificador de contrato y de privacidad.

    python -m gondola verify data/output/video_001.detect.jsonl

PARA QUE SIRVE
--------------
Somos 8 personas escribiendo archivos que las demas van a leer. Este comando
revisa una salida del pipeline linea por linea y dice, regla por regla, si
cumple o no. Cada quien lo corre sobre SU salida antes de decir "ya termine",
sin que nadie tenga que revisarle el codigo a mano.

Tambien es nuestra evidencia de privacidad por diseno. La regla de campos
prohibidos no confia en que el contrato los rechace: relee el archivo ya
escrito y busca cualquier rastro de edad, genero, rostro, identidad, emocion o
biometria. Si aparece uno, el comando falla.

QUE REGLAS SE APLICAN
---------------------
Depende del archivo. El verificador deduce la etapa por el nombre
(`...detect.jsonl` -> etapa detect) y sabe, por la tabla STAGES, que campos
debe haber rellenado esa etapa y cuales tienen que seguir en null porque son
de etapas posteriores.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from gondola import pipeline
from gondola.config import Config
from gondola.contract import Event

# Fragmentos prohibidos. Se busca por SUBCADENA sobre las claves del JSON, en
# minusculas, en espanol y en ingles. Es deliberadamente amplio: preferimos un
# falso positivo que nos haga discutir un nombre de campo, a que se cuele un
# dato personal sin que nadie lo note.
FRAGMENTOS_PROHIBIDOS = (
    "age", "edad", "birth", "nacimiento",
    "gender", "genero", "sex", "sexo",
    "face", "rostro", "facial", "cara",
    "embedding", "descriptor", "feature_vector",
    "identity", "identidad", "identif",
    "name", "nombre", "apellido",
    "emotion", "emocion", "mood", "sentiment",
    "biometric", "biometr", "fingerprint", "huella", "iris",
    "document", "documento", "cedula", "dni", "passport",
    "email", "correo", "phone", "telefono",
    "photo", "foto", "image", "imagen", "thumbnail",
    "ethnic", "etnia", "race", "raza",
)

# Cuanto puede desviarse un timestamp de frame/fps antes de considerarse mal.
# Medio frame a 25 fps son 20 ms; damos 50 ms de margen por el redondeo.
TOLERANCIA_TIMESTAMP_S = 0.05

CLAVES_RAIZ = {
    "video_id", "frame", "timestamp", "track_id",
    "detection", "zone", "interaction", "metrics",
}


@dataclass
class Regla:
    """Una comprobacion. Acumula sus propios fallos mientras se recorre el archivo."""

    nombre: str
    descripcion: str
    fallos: list[tuple[int, str]] = field(default_factory=list)
    omitida: str = ""  # si no esta vacio, explica por que no se pudo comprobar

    def falla(self, linea: int, detalle: str) -> None:
        self.fallos.append((linea, detalle))

    @property
    def estado(self) -> str:
        if self.omitida:
            return "OMITE"
        return "FALLA" if self.fallos else "PASA "


@dataclass
class Informe:
    """El resultado completo de verificar un archivo."""

    ruta: Path
    etapa: str
    eventos: int
    reglas: list[Regla]
    contexto: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(r.fallos for r in self.reglas)


def _clave_prohibida(clave: str) -> str | None:
    """Devuelve el fragmento prohibido que contiene la clave, o None."""
    minuscula = clave.lower()
    for fragmento in FRAGMENTOS_PROHIBIDOS:
        if fragmento in minuscula:
            return fragmento
    return None


def _recorrer_claves(datos: Any, prefijo: str = "") -> list[str]:
    """Devuelve todas las claves del JSON, incluidas las anidadas."""
    claves = []
    if isinstance(datos, dict):
        for clave, valor in datos.items():
            ruta = f"{prefijo}.{clave}" if prefijo else clave
            claves.append(ruta)
            claves.extend(_recorrer_claves(valor, ruta))
    elif isinstance(datos, list):
        for elemento in datos:
            claves.extend(_recorrer_claves(elemento, prefijo))
    return claves


def _valor_en_ruta(evento: Event, ruta: str) -> Any:
    """Lee un campo del evento en notacion punto: 'metrics.dwell_time'."""
    valor: Any = evento
    for parte in ruta.split("."):
        valor = getattr(valor, parte)
    return valor


def _esta_vacio(valor: Any) -> bool:
    """True si el campo sigue sin rellenar.

    Un submodelo (zone, interaction) cuenta como vacio si todos sus campos son
    None: `zone` siempre existe como objeto, lo que puede estar vacio es su
    contenido.
    """
    if valor is None:
        return True
    if hasattr(valor, "model_dump"):
        return all(v is None for v in valor.model_dump().values())
    return False


def _leer_resumen(ruta_jsonl: Path) -> dict:
    """Busca el resumen JSON que dejo la etapa, para saber tamano del frame y fps.

    Si no esta, algunas reglas se marcan como OMITIDAS en vez de inventarse los
    datos. Preferimos decir "no lo pude comprobar" antes que dar por buena una
    regla que no se ejecuto.
    """
    for etapa in pipeline.STAGES:
        if ruta_jsonl.name.endswith(etapa.output_suffix):
            base = ruta_jsonl.name[: -len(etapa.output_suffix)]
            candidato = ruta_jsonl.parent / f"{base}.{etapa.name}.summary.json"
            if candidato.exists():
                try:
                    return json.loads(candidato.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    return {}
    return {}


def verificar(ruta: Path, cfg: Config) -> Informe:
    """Revisa un archivo .jsonl completo y devuelve el informe."""
    etapa = pipeline.stage_for_file(ruta)
    nombre_etapa = etapa.name if etapa else "desconocida"

    resumen = _leer_resumen(ruta)
    info_video = resumen.get("video", {})
    ancho = info_video.get("width")
    alto = info_video.get("height")
    fps = info_video.get("fps")
    umbral = resumen.get("params", {}).get(
        "confidence_threshold", cfg.confidence_threshold
    )

    contexto = [f"Etapa deducida del nombre del archivo: {nombre_etapa}"]
    if not resumen:
        contexto.append(
            f"No encontre el resumen de la corrida; uso el umbral del .env "
            f"({umbral}). Las reglas que necesitan el tamano del frame o los "
            f"fps quedan OMITIDAS."
        )
    elif ancho and alto and fps:
        contexto.append(
            f"Parametros leidos del resumen de la corrida "
            f"(umbral={umbral}, frame={ancho}x{alto}, {fps} fps)"
        )
    else:
        # Resumen de una corrida anterior a que el resumen incluyera `video`.
        contexto.append(
            f"El resumen de la corrida no trae el tamano del frame ni los fps "
            f"(umbral={umbral}). Vuelve a correr la etapa para regenerarlo; "
            f"mientras tanto esas reglas quedan OMITIDAS."
        )

    r_claves = Regla("claves_raiz", "Las claves de raiz son exactamente las del contrato")
    r_contrato = Regla("contrato", "Cada linea valida contra el modelo Pydantic")
    r_clase = Regla("clase_person", "detection.class es siempre 'person'")
    r_conf_rango = Regla("confianza_rango", "confidence esta entre 0.0 y 1.0")
    r_conf_umbral = Regla("confianza_umbral", f"confidence nunca por debajo del umbral ({umbral})")
    r_bbox_pos = Regla("bbox_positiva", "bbox tiene width y height positivos")
    r_bbox_frame = Regla("bbox_en_frame", "bbox cabe dentro del frame")
    r_frames = Regla("frames_crecientes", "Los numeros de frame no retroceden")
    r_tiempo = Regla("timestamps", "timestamp coincide con frame / fps")
    r_posteriores = Regla("campos_posteriores", "Los campos de etapas posteriores estan en null")
    r_privacidad = Regla("privacidad", "Ningun campo prohibido (edad, rostro, identidad, emocion...)")

    reglas = [r_claves, r_contrato, r_clase, r_conf_rango, r_conf_umbral,
              r_bbox_pos, r_bbox_frame, r_frames, r_tiempo, r_posteriores,
              r_privacidad]

    if ancho is None or alto is None:
        r_bbox_frame.omitida = "no se conocen las dimensiones del frame"
    if not fps:
        r_tiempo.omitida = "no se conocen los fps del video"

    posteriores: list[str] = []
    if etapa:
        for siguiente in pipeline.stages_after(etapa.name):
            posteriores.extend(siguiente.fills)
    else:
        r_posteriores.omitida = "no se pudo deducir la etapa del archivo"

    eventos = 0
    frame_anterior = -1

    with ruta.open("r", encoding="utf-8") as archivo:
        for numero, linea in enumerate(archivo, start=1):
            linea = linea.strip()
            if not linea:
                continue
            eventos += 1

            try:
                datos = json.loads(linea)
            except json.JSONDecodeError as exc:
                r_contrato.falla(numero, f"no es JSON valido: {exc.msg}")
                continue

            # Privacidad: se revisa el JSON en crudo, ANTES de validarlo. Si el
            # archivo lo escribio otra herramienta, el contrato no lo ha
            # filtrado y justo por eso hay que mirarlo aqui.
            for clave in _recorrer_claves(datos):
                hoja = clave.split(".")[-1]
                fragmento = _clave_prohibida(hoja)
                if fragmento:
                    r_privacidad.falla(
                        numero, f"campo prohibido {clave!r} (contiene '{fragmento}')"
                    )

            if isinstance(datos, dict):
                sobran = set(datos) - CLAVES_RAIZ
                faltan = CLAVES_RAIZ - set(datos)
                if sobran:
                    r_claves.falla(numero, f"claves de mas: {sorted(sobran)}")
                if faltan:
                    r_claves.falla(numero, f"claves que faltan: {sorted(faltan)}")
            else:
                r_claves.falla(numero, "la linea no es un objeto JSON")
                continue

            try:
                evento = Event.model_validate(datos)
            except ValidationError as exc:
                primer_error = exc.errors()[0]
                campo = ".".join(str(p) for p in primer_error["loc"])
                r_contrato.falla(numero, f"{campo}: {primer_error['msg']}")
                continue

            if evento.detection.class_name != "person":
                r_clase.falla(numero, f"class = {evento.detection.class_name!r}")

            confianza = evento.detection.confidence
            if not 0.0 <= confianza <= 1.0:
                r_conf_rango.falla(numero, f"confidence = {confianza}")
            elif confianza < umbral:
                r_conf_umbral.falla(
                    numero, f"confidence = {confianza:.3f} < umbral {umbral}"
                )

            caja = evento.detection.bbox
            if caja.width <= 0 or caja.height <= 0:
                r_bbox_pos.falla(numero, f"width={caja.width}, height={caja.height}")
            elif not r_bbox_frame.omitida:
                if (caja.x < 0 or caja.y < 0
                        or caja.x + caja.width > ancho
                        or caja.y + caja.height > alto):
                    r_bbox_frame.falla(
                        numero,
                        f"caja ({caja.x:.0f},{caja.y:.0f},{caja.width:.0f}x"
                        f"{caja.height:.0f}) se sale de {ancho}x{alto}",
                    )

            if evento.frame < frame_anterior:
                r_frames.falla(
                    numero, f"frame {evento.frame} viene despues de {frame_anterior}"
                )
            frame_anterior = max(frame_anterior, evento.frame)

            if not r_tiempo.omitida:
                esperado = evento.frame / fps
                if abs(evento.timestamp - esperado) > TOLERANCIA_TIMESTAMP_S:
                    r_tiempo.falla(
                        numero,
                        f"timestamp {evento.timestamp:.3f} pero frame "
                        f"{evento.frame} / {fps} fps = {esperado:.3f}",
                    )

            for campo in posteriores:
                if not _esta_vacio(_valor_en_ruta(evento, campo)):
                    r_posteriores.falla(
                        numero,
                        f"{campo} ya viene relleno, pero lo llena una etapa posterior",
                    )

    return Informe(ruta=ruta, etapa=nombre_etapa, eventos=eventos,
                   reglas=reglas, contexto=contexto)


def imprimir_informe(informe: Informe, max_ejemplos: int = 3) -> None:
    """Imprime el informe: una linea por regla, y ejemplos de lo que fallo."""
    print("=" * 72)
    print(f"  VERIFICACION  {informe.ruta.name}")
    print("=" * 72)
    for linea in informe.contexto:
        print(f"  {linea}")
    print(f"  Eventos verificados: {informe.eventos}")
    print()

    for regla in informe.reglas:
        print(f"  [{regla.estado}] {regla.descripcion}")
        if regla.omitida:
            print(f"            (no se pudo comprobar: {regla.omitida})")
        for numero, detalle in regla.fallos[:max_ejemplos]:
            print(f"            linea {numero}: {detalle}")
        if len(regla.fallos) > max_ejemplos:
            print(f"            ... y {len(regla.fallos) - max_ejemplos} fallos mas")

    print()
    print("=" * 72)
    if informe.ok:
        omitidas = sum(1 for r in informe.reglas if r.omitida)
        extra = f" ({omitidas} regla(s) no se pudieron comprobar)" if omitidas else ""
        print(f"  RESULTADO: PASA. {informe.eventos} eventos cumplen el contrato{extra}.")
    else:
        rotas = [r.nombre for r in informe.reglas if r.fallos]
        print(f"  RESULTADO: FALLA. Reglas incumplidas: {', '.join(rotas)}")
    print("=" * 72)
