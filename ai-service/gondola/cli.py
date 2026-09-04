"""Punto de entrada unico del proyecto.

    cd ai-service
    python -m gondola <subcomando>

Todos los comandos del proyecto pasan por aqui. Nadie ejecuta un modulo suelto:
asi la configuracion se carga igual para todos y los nombres de archivo salen
siempre del registro de etapas (gondola/pipeline.py).

Codigos de salida:
    0  todo bien
    1  error de ejecucion (incluida una etapa aun sin implementar)
    2  falta un requisito: el video o el archivo de la etapa anterior
"""

from __future__ import annotations

import argparse
import importlib.metadata
import shutil
import sys
from dataclasses import replace
from pathlib import Path

from gondola import pipeline
from gondola.config import (
    DEVICES_VALIDOS,
    RAIZ,
    RENDER_MODES_VALIDOS,
    Config,
    load_config,
)
from gondola.contract import CONTRACT_VERSION
from gondola.errors import ConfigError, GondolaError, MissingInputError
from gondola.logging_setup import setup_logging

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_FALTA_REQUISITO = 2

# Lo que doctor comprueba. (nombre para importar, para que sirve, desde que fase)
DEPENDENCIAS = (
    ("pydantic", "validacion del contrato de datos", "Fase 1"),
    ("dotenv", "lectura del archivo .env", "Fase 1"),
    ("cv2", "lectura de video (opencv-python)", "Fase 3"),
    ("ultralytics", "deteccion YOLO", "Fase 3"),
)


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------

def comando_doctor() -> int:
    """Diagnostica el entorno. NUNCA falla: informa.

    Es lo primero que debe correr cualquiera del equipo cuando algo no le
    funciona, antes de preguntar. Por eso atrapa hasta los errores de
    configuracion en vez de reventar con ellos.
    """
    print("=" * 70)
    print("  GONDOLA INTELIGENTE - diagnostico")
    print("=" * 70)

    print("\n[1] Entorno")
    print(f"    Python           {sys.version.split()[0]}")
    print(f"    Contrato         v{CONTRACT_VERSION}")
    print(f"    Raiz del repo    {RAIZ}")

    print("\n[2] Dependencias")
    for modulo, para_que, fase in DEPENDENCIAS:
        version = _version_instalada(modulo)
        marca = "OK   " if version else "FALTA"
        detalle = f"v{version}" if version else f"se necesita en la {fase}"
        print(f"    [{marca}] {modulo:<12} {detalle:<22} ({para_que})")

    print("\n[3] Configuracion")
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"    [FALLA] {exc}")
        print("\n    No puedo seguir revisando archivos sin una configuracion valida.")
        print("    Arregla tu .env y vuelve a correr: python -m gondola doctor")
        print("\n" + "=" * 70)
        return EXIT_OK  # doctor informa, no falla

    if not (RAIZ / ".env").exists():
        print("    [AVISO] No hay archivo .env; se usan los valores por defecto.")
        print("            Para personalizar:  cp .env.example .env")
    else:
        print("    [OK   ] .env encontrado")
    print(f"    VIDEO_ID             {cfg.video_id}")
    print(f"    CONFIDENCE_THRESHOLD {cfg.confidence_threshold}")
    print(f"    IOU_THRESHOLD        {cfg.iou_threshold}")
    print(f"    IMGSZ                {cfg.imgsz}")
    print(f"    FRAME_STRIDE         {cfg.frame_stride}")
    print(f"    MAX_FRAMES           {cfg.max_frames}  (0 = video completo)")
    print(f"    DEVICE               {cfg.device}")
    print(f"    RENDER_MODE          {cfg.render_mode}")
    print(f"    LOG_LEVEL            {cfg.log_level}")

    print("\n[4] Archivos de entrada")
    _informar_archivo("Video ", cfg.video_path,
                      "deja el video de Scapder en data/videos/ (ver su README)")
    _informar_archivo("Modelo", cfg.model_path,
                      "descarga los pesos YOLO a data/models/ (hace falta en la Fase 3)")

    print("\n[5] Estado de la cadena")
    print(f"    Carpeta de salida: {cfg.output_dir}")
    for etapa in pipeline.STAGES:
        rutas = pipeline.stage_paths(etapa.name, cfg)
        marca = "HECHA " if rutas.output_path.exists() else "faltan"
        print(f"    [{marca}] {etapa.name:<9} -> {rutas.output_path.name:<24} "
              f"({etapa.owner})")

    print("\n" + "=" * 70)
    print("  Siguiente paso:  python -m gondola run")
    print("=" * 70)
    return EXIT_OK


def _version_instalada(modulo: str) -> str | None:
    """Devuelve la version instalada del paquete, o None si no esta."""
    # El nombre para importar y el nombre del paquete no siempre coinciden.
    paquetes = {"cv2": "opencv-python", "dotenv": "python-dotenv"}
    try:
        return importlib.metadata.version(paquetes.get(modulo, modulo))
    except importlib.metadata.PackageNotFoundError:
        return None


def _informar_archivo(etiqueta: str, ruta: Path, sugerencia: str) -> None:
    """Dice si un archivo existe y, si no, que hacer al respecto."""
    if ruta.exists():
        mb = ruta.stat().st_size / (1024 * 1024)
        print(f"    [OK   ] {etiqueta}  {ruta}  ({mb:.1f} MB)")
    else:
        print(f"    [FALTA] {etiqueta}  {ruta}")
        print(f"             Que hacer: {sugerencia}")


# --------------------------------------------------------------------------
# etapas (todas sin implementar todavia)
# --------------------------------------------------------------------------

def comando_etapa(nombre: str, cfg: Config, abrir_video: bool = False) -> int:
    """Ejecuta una etapa. Las que faltan son placeholders con instrucciones.

    El texto del placeholder es lo primero que vera el companero al que le
    toque el modulo, asi que dice quien es, que archivo crear, que leer y que
    escribir.
    """
    if nombre == "detect":
        # El import va aqui dentro porque detect arrastra opencv. Arriba haria
        # que `python -m gondola doctor` fallara en una maquina sin instalarlo,
        # justo cuando mas falta hace el diagnostico.
        from gondola.stages import detect

        return detect.run(cfg, abrir_video=abrir_video)

    if nombre == "track":
        from gondola.stages import track

        return track.run(cfg, abrir_video=abrir_video)

    if nombre == "zones":
        from gondola.stages import zones

        return zones.run(cfg)

    if nombre == "interact":
        from gondola.stages import interact

        return interact.run(cfg)
    if nombre == "metrics":
        from gondola.stages import metrics
        return metrics.run(cfg)

    rutas = pipeline.stage_paths(nombre, cfg)
    etapa = rutas.stage
    anterior = pipeline.previous_stage(nombre)

    print(f"[{etapa.name}] TODAVIA NO ESTA IMPLEMENTADA.")
    print()
    print(f"  Responsable:  {etapa.owner}")
    print(f"  Que hace:     {etapa.description}")
    print(f"  Archivo:      ai-service/gondola/stages/{etapa.name}.py")
    print()
    if anterior is None:
        print(f"  Debe LEER:      el video  ->  {rutas.input_path}")
    else:
        print(f"  Debe LEER:      {rutas.input_path}")
        print(f"                  (lo produce la etapa '{anterior.name}')")
    print(f"  Debe ESCRIBIR:  {rutas.output_path}")
    print()
    print("  Como empezar:")
    print("    - Pide las rutas con pipeline.stage_paths(...); no las escribas a mano.")
    print("    - Lee con jsonl.read_events() y escribe con jsonl.write_events().")
    print("    - Rellena SOLO tus campos del contrato (ver docs/data-contract.md).")

    # Que falte la entrada es un problema distinto de que falte la implementacion,
    # y mas urgente: por eso tiene su propio codigo de salida.
    try:
        pipeline.require_input(nombre, cfg)
    except MissingInputError as exc:
        print()
        print(f"  ADEMAS, LE FALTA UN REQUISITO:\n{exc}")
        return EXIT_FALTA_REQUISITO

    print()
    print("  Su entrada ya existe: solo falta escribir la etapa.")
    return EXIT_ERROR


def comando_run(cfg: Config) -> int:
    """Recorre la cadena en orden y se detiene en la primera etapa que no pueda seguir."""
    print("Ejecutando la cadena completa:", " -> ".join(pipeline.STAGE_NAMES))
    print()
    for nombre in pipeline.STAGE_NAMES:
        # Los errores se atrapan aqui, etapa por etapa, para poder decir DONDE
        # se detuvo la cadena. Si se dejaran subir hasta main(), el codigo de
        # salida seria correcto pero el mensaje de "se detiene en X" se perderia.
        try:
            codigo = comando_etapa(nombre, cfg)
        except MissingInputError as exc:
            print()
            print(f"  FALTA UN REQUISITO:\n{exc}")
            codigo = EXIT_FALTA_REQUISITO
        except GondolaError as exc:
            print()
            print(f"  ERROR: {exc}")
            codigo = EXIT_ERROR

        if codigo != EXIT_OK:
            print()
            print("-" * 70)
            print(f"La cadena se detiene en '{nombre}'. Las etapas que siguen "
                  "no pueden correr sin su salida.")
            print("-" * 70)
            return codigo
    return EXIT_OK


# --------------------------------------------------------------------------
# purge
# --------------------------------------------------------------------------

def comando_purge(cfg: Config, sin_preguntar: bool) -> int:
    """Borra videos y salidas de data/. Es nuestra minimizacion de datos.

    No toca data/groundtruth/ (trabajo manual que no se puede regenerar) ni los
    README que explican cada carpeta.
    """
    carpetas = (cfg.video_path.parent, cfg.output_dir)
    victimas = sorted(
        ruta
        for carpeta in carpetas
        if carpeta.is_dir()
        for ruta in carpeta.iterdir()
        if ruta.name != "README.md"
    )

    if not victimas:
        print("No hay nada que borrar: data/videos/ y data/output/ ya estan limpias.")
        return EXIT_OK

    print("Se van a borrar estos archivos:")
    for ruta in victimas:
        print(f"    {ruta}")
    print(f"\nTotal: {len(victimas)}. No se toca data/groundtruth/ ni los README.")

    if not sin_preguntar:
        respuesta = input("\nEscribe 'si' para confirmar: ").strip().lower()
        if respuesta != "si":
            print("Cancelado. No se borro nada.")
            return EXIT_OK

    for ruta in victimas:
        if ruta.is_dir():
            shutil.rmtree(ruta)
        else:
            ruta.unlink()
    print(f"\nBorrados {len(victimas)} archivos.")
    return EXIT_OK


# --------------------------------------------------------------------------
# verify y eval
# --------------------------------------------------------------------------

def comando_verify(cfg: Config, archivo: str | None) -> int:
    """Revisa una salida del pipeline contra el contrato y las reglas de privacidad."""
    from gondola.verify.verifier import imprimir_informe, verificar

    if archivo:
        ruta = _resolver_ruta(archivo)
    else:
        # Sin argumento, verifica la salida de detect: es la que existe hoy.
        ruta = pipeline.stage_paths("detect", cfg).output_path

    if not ruta.exists():
        raise MissingInputError(
            f"No existe el archivo a verificar:\n    {ruta}\n\n"
            f"Que hacer: genera una salida primero, por ejemplo\n"
            f"    python -m gondola detect"
        )

    informe = verificar(ruta, cfg)
    imprimir_informe(informe)
    return EXIT_OK if informe.ok else EXIT_ERROR


def comando_eval(cfg: Config, tolerancia: float, archivo: str | None) -> int:
    """Compara la salida del pipeline contra las anotaciones manuales."""
    from gondola.evaluate.evaluator import (
        evaluar,
        eventos_detectados,
        imprimir_evaluacion,
        leer_groundtruth,
    )

    gt = _resolver_ruta(archivo) if archivo else cfg.groundtruth_dir / f"{cfg.video_id}.csv"
    if not gt.exists():
        print("No hay anotaciones manuales para este video.")
        print()
        print(f"  Buscaba: {gt}")
        print()
        print("  SIN ANOTACIONES NO SE PUEDE AFIRMAR NADA SOBRE LA EXACTITUD.")
        print("  No hay forma de saber si el sistema acierta sin que una persona")
        print("  haya visto el video y escrito lo que de verdad pasa en el.")
        print()
        print("  Que hacer: copia data/groundtruth/ejemplo.csv, anota el video")
        print("  siguiendo docs/evaluation.md y vuelve a correr este comando.")
        return EXIT_FALTA_REQUISITO

    salida = pipeline.stage_paths("interact", cfg).output_path
    if not salida.exists():
        raise MissingInputError(
            f"No existe la salida a evaluar:\n    {salida}\n\n"
            f"Que hacer: corre la cadena hasta 'interact', que es la etapa que\n"
            f"produce los eventos de interaccion:\n"
            f"    python -m gondola run"
        )

    anotados = leer_groundtruth(gt)
    detectados = eventos_detectados(salida)
    print(f"  Anotaciones: {gt}")
    print(f"  Salida:      {salida}")
    print()

    if not anotados:
        print("El archivo de anotaciones esta vacio: no hay contra que comparar.")
        return EXIT_FALTA_REQUISITO

    imprimir_evaluacion(evaluar(anotados, detectados, tolerancia), tolerancia)
    return EXIT_OK


# --------------------------------------------------------------------------
# arranque
# --------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    """Arma los subcomandos. Las etapas salen del registro, no de una lista aparte."""
    parser = argparse.ArgumentParser(
        prog="python -m gondola",
        description="Gondola Inteligente: analisis de dinamica de clientes en retail.",
    )
    subcomandos = parser.add_subparsers(dest="comando", required=True)

    subcomandos.add_parser("doctor", help="Diagnostica el entorno. Empieza por aqui.")
    for etapa in pipeline.STAGES:
        sub = subcomandos.add_parser(
            etapa.name, help=f"{etapa.description} ({etapa.owner})"
        )
        if etapa.name == "detect":
            _opciones_de_detect(sub)
        elif etapa.name == "track":
            _opciones_de_track(sub)
    subcomandos.add_parser("run", help="Ejecuta la cadena completa en orden.")

    verify = subcomandos.add_parser(
        "verify", help="Revisa una salida contra el contrato y la privacidad."
    )
    verify.add_argument("archivo", nargs="?",
                        help="Archivo .jsonl a revisar. Por defecto, el de detect.")

    ev = subcomandos.add_parser(
        "eval", help="Compara la salida contra las anotaciones manuales."
    )
    ev.add_argument("--groundtruth", help="CSV de anotaciones. Por defecto, <video_id>.csv")
    ev.add_argument("--tolerance", type=float, default=2.0,
                    help="Tolerancia temporal en segundos (defecto: 2.0).")

    purge = subcomandos.add_parser(
        "purge", help="Borra videos y salidas de data/ (minimizacion de datos)."
    )
    purge.add_argument("--yes", action="store_true", help="No preguntar antes de borrar.")

    return parser


def _opciones_de_detect(sub: argparse.ArgumentParser) -> None:
    """Opciones que sobrescriben el .env solo para esta corrida.

    Sirven para probar rapido sin editar el .env: `--max-frames 50 --render none`
    da un resultado en segundos.
    """
    sub.add_argument("--video", help="Ruta del video, en vez de VIDEO_PATH.")
    sub.add_argument("--conf", type=float, help="Confianza minima (0.0 a 1.0).")
    sub.add_argument("--stride", type=int, help="Procesar 1 de cada N frames.")
    sub.add_argument("--max-frames", type=int, help="Cortar tras N frames. 0 = todos.")
    sub.add_argument("--imgsz", type=int, help="Lado en pixeles para el modelo.")
    sub.add_argument("--device", choices=sorted(DEVICES_VALIDOS), help="cpu, cuda o mps.")
    sub.add_argument("--render", choices=sorted(RENDER_MODES_VALIDOS),
                     help="privacy (defecto), debug o none.")
    sub.add_argument("--open", action="store_true",
                     help="Abrir el video resultante al terminar.")


def _opciones_de_track(sub: argparse.ArgumentParser) -> None:
    """Mismas opciones de render que `detect` (--render y --open), con el
    mismo nombre y el mismo significado: las etapas que siguen (zones,
    interact, metrics) van a copiar este modulo como plantilla, y conviene
    que a todas las opciones de render se les llame igual."""
    sub.add_argument("--render", choices=sorted(RENDER_MODES_VALIDOS),
                     help="privacy (defecto), debug o none.")
    sub.add_argument("--open", action="store_true",
                     help="Abrir el video resultante al terminar.")


def _aplicar_opciones(cfg: Config, args: argparse.Namespace) -> Config:
    """Devuelve una copia de la configuracion con lo que se paso por linea de comandos.

    Se hace con `replace` sobre el dataclass congelado: la configuracion sigue
    siendo inmutable, simplemente se arma otra distinta antes de empezar.
    """
    cambios = {}
    if getattr(args, "video", None):
        ruta = _resolver_ruta(args.video)
        cambios["video_path"] = ruta
        # El video_id tambien cambia, si no analizar dos videos distintos
        # escribiria los dos en video_001.detect.jsonl y el segundo borraria al
        # primero sin avisar.
        nuevo_id = ruta.stem
        if nuevo_id != cfg.video_id:
            print(f"  (VIDEO_ID pasa a ser '{nuevo_id}', tomado del nombre del archivo)")
            cambios["video_id"] = nuevo_id
    if getattr(args, "conf", None) is not None:
        cambios["confidence_threshold"] = args.conf
    if getattr(args, "stride", None) is not None:
        cambios["frame_stride"] = args.stride
    if getattr(args, "max_frames", None) is not None:
        cambios["max_frames"] = args.max_frames
    if getattr(args, "imgsz", None) is not None:
        cambios["imgsz"] = args.imgsz
    if getattr(args, "device", None):
        cambios["device"] = args.device
    if getattr(args, "render", None):
        cambios["render_mode"] = args.render
    return replace(cfg, **cambios) if cambios else cfg


def _resolver_ruta(texto: str) -> Path:
    """Acepta la ruta tal como la escribio el usuario, o relativa a la raiz del repo.

    El comando se lanza desde ai-service/, pero es natural escribir
    "data/videos/clip.mp4" pensando en la raiz. Probamos las dos.
    """
    ruta = Path(texto)
    if ruta.is_absolute() or ruta.exists():
        return ruta.resolve()
    desde_raiz = RAIZ / ruta
    return desde_raiz if desde_raiz.exists() else ruta.resolve()


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada. Devuelve el codigo de salida en vez de llamar a sys.exit.

    Devolverlo en vez de salir permite probar la CLI entera desde los tests.
    """
    args = _parser().parse_args(argv)

    if args.comando == "doctor":
        return comando_doctor()

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"ERROR de configuracion: {exc}", file=sys.stderr)
        print("Para un diagnostico completo: python -m gondola doctor", file=sys.stderr)
        return EXIT_ERROR

    cfg = _aplicar_opciones(cfg, args)
    setup_logging(cfg.log_level)

    try:
        if args.comando == "purge":
            return comando_purge(cfg, args.yes)
        if args.comando == "run":
            return comando_run(cfg)
        if args.comando == "verify":
            return comando_verify(cfg, args.archivo)
        if args.comando == "eval":
            return comando_eval(cfg, args.tolerance, args.groundtruth)
        return comando_etapa(args.comando, cfg, abrir_video=getattr(args, "open", False))
    except MissingInputError as exc:
        print(f"\nFALTA UN REQUISITO\n{exc}", file=sys.stderr)
        return EXIT_FALTA_REQUISITO
    except GondolaError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
