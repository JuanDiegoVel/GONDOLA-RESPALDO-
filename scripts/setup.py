"""Deja el proyecto listo para correr, DETECTANDO E INSTALANDO lo que
falte, en vez de solo avisar -a diferencia de `python -m gondola doctor`,
que solo diagnostica-. Pensado para que un companero nuevo, o un agente
como Claude Code, corra un solo comando despues de clonar el repo y quede
listo sin tener que leer cinco README distintos para ensamblar los pasos.

    python scripts/setup.py            # lo LIGERO: .env, tests, Docker+Postgres, DLL de Windows
    python scripts/setup.py --full     # ademas instala requirements.txt del ai-service (~3 GB: PyTorch/YOLO)
    python scripts/setup.py --model    # ademas descarga data/models/yolo11n.pt

Corre esto con el interprete de Python que quieras usar para el proyecto
(activa tu entorno virtual primero si vas a usar uno; este script no crea
ninguno, eso sigue siendo una decision de cada quien).

QUE SI AUTOMATIZA
------------------
1. Copia .env.example -> .env (raiz y backend/), si no existen.
2. `pip install -r requirements-dev.txt` (raiz, ligero) y
   `backend/requirements.txt`.
3. En Windows, descarga y VERIFICA (checksum MD5 oficial de Cisco) la
   libreria `openh264-2.5.0-win64.dll` en `data/models/`: sin ella, los
   videos renderizados no se pueden reproducir en un navegador, y OpenCV
   no avisa con ningun error -ver `data/models/README.md`-.
4. Levanta PostgreSQL con Docker (`backend/docker-compose.yml`) y carga
   `backend/database/schema.sql`, si la tabla `videos` todavia no existe.

QUE NO HACE SIN QUE SE LO PIDAS EXPLICITAMENTE (--full / --model)
-------------------------------------------------------------------
- Instalar `requirements.txt` completo del ai-service (PyTorch, ~3 GB): es
  una descarga grande como para hacerla sin que alguien la pida a proposito.
- Descargar el modelo YOLO (`yolo11n.pt`, unos 5-6 MB): mismo criterio,
  aunque pese poco.
- Descargar ningun video de la tienda: eso sigue siendo trabajo humano
  (ver `data/videos/README.md`) y no hay de donde descargarlo solo.

Cada paso comprueba si ya esta hecho antes de repetirlo: correr esto varias
veces, o despues de que alguien mas ya corrio parte de esto, es seguro.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

OPENH264_URL = "http://ciscobinary.openh264.org/openh264-2.5.0-win64.dll.bz2"
OPENH264_MD5 = "83234500b244daf1e79c8b772c06e66f"
OPENH264_DESTINO = RAIZ / "data" / "models" / "openh264-2.5.0-win64.dll"

YOLO_MODEL = RAIZ / "data" / "models" / "yolo11n.pt"


def _titulo(texto: str) -> None:
    print(f"\n=== {texto} ===")


def _ok(texto: str) -> None:
    print(f"  [OK]    {texto}")


def _hecho(texto: str) -> None:
    print(f"  [HECHO] {texto}")


def _aviso(texto: str) -> None:
    print(f"  [AVISO] {texto}")


def copiar_env_faltantes() -> None:
    _titulo(".env")
    pares = [
        (RAIZ / ".env.example", RAIZ / ".env"),
        (RAIZ / "backend" / ".env.example", RAIZ / "backend" / ".env"),
    ]
    for ejemplo, destino in pares:
        if not ejemplo.exists():
            _aviso(f"no encuentro {ejemplo}, no puedo copiarlo")
            continue
        if destino.exists():
            _ok(f"{destino.relative_to(RAIZ)} ya existe, no lo toco")
            continue
        destino.write_text(ejemplo.read_text(encoding="utf-8"), encoding="utf-8")
        _hecho(f"creado {destino.relative_to(RAIZ)} a partir de {ejemplo.name}")


def instalar_dependencias_ligeras() -> None:
    _titulo("Dependencias de Python (ligeras)")
    pip = [sys.executable, "-m", "pip", "install", "-q"]
    pasos = [
        ("requirements-dev.txt (tests del ai-service)", RAIZ / "requirements-dev.txt"),
        ("backend/requirements.txt (importador + API)", RAIZ / "backend" / "requirements.txt"),
    ]
    for etiqueta, archivo in pasos:
        if not archivo.exists():
            _aviso(f"no encuentro {archivo}, me lo salto")
            continue
        print(f"  instalando {etiqueta}...")
        resultado = subprocess.run(pip + ["-r", str(archivo)])
        if resultado.returncode == 0:
            _hecho(etiqueta)
        else:
            _aviso(f"fallo instalando {etiqueta} (codigo {resultado.returncode})")


def instalar_dependencias_pesadas() -> None:
    _titulo("Dependencias PESADAS del ai-service (--full)")
    archivo = RAIZ / "requirements.txt"
    if not archivo.exists():
        _aviso(f"no encuentro {archivo}")
        return
    print("  Esto arrastra PyTorch (~3 GB). Puede tardar varios minutos...")
    resultado = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(archivo)])
    if resultado.returncode == 0:
        _hecho("requirements.txt (YOLO/PyTorch)")
    else:
        _aviso(f"fallo instalando requirements.txt (codigo {resultado.returncode})")


def descargar_modelo_yolo() -> None:
    _titulo("Modelo YOLO (--model)")
    if YOLO_MODEL.exists():
        _ok(f"{YOLO_MODEL.relative_to(RAIZ)} ya existe")
        return
    print("  Dejando que 'ultralytics' descargue el modelo (necesita el paquete instalado)...")
    try:
        from ultralytics import YOLO  # import pesado, solo si hace falta

        YOLO_MODEL.parent.mkdir(parents=True, exist_ok=True)
        YOLO(str(YOLO_MODEL))
        if YOLO_MODEL.exists():
            _hecho(f"descargado {YOLO_MODEL.relative_to(RAIZ)}")
        else:
            _aviso("ultralytics no dejo el archivo donde se esperaba; descargalo a mano (ver data/models/README.md)")
    except ImportError:
        _aviso("'ultralytics' no esta instalado -corre con --full primero, o instala requirements.txt-")
    except Exception as exc:  # noqa: BLE001 -- solo se informa, no se detiene el resto del setup
        _aviso(f"no se pudo descargar el modelo automaticamente: {exc}")
        _aviso("descargalo a mano: ver data/models/README.md")


def descargar_openh264() -> None:
    _titulo("Libreria openh264 (solo Windows)")
    if sys.platform != "win32":
        _ok("no hace falta fuera de Windows")
        return
    if OPENH264_DESTINO.exists():
        _ok(f"{OPENH264_DESTINO.relative_to(RAIZ)} ya existe")
        return

    print(f"  Descargando {OPENH264_URL} ...")
    try:
        with urllib.request.urlopen(OPENH264_URL, timeout=30) as respuesta:
            comprimido = respuesta.read()
    except Exception as exc:  # noqa: BLE001
        _aviso(f"no se pudo descargar: {exc}. Descargala a mano (ver data/models/README.md)")
        return

    import bz2

    contenido = bz2.decompress(comprimido)
    checksum = hashlib.md5(contenido).hexdigest()
    if checksum != OPENH264_MD5:
        _aviso(
            f"el checksum no coincide (esperado {OPENH264_MD5}, obtenido {checksum}): "
            "no se guarda el archivo, para no usar un binario sin verificar."
        )
        return

    OPENH264_DESTINO.parent.mkdir(parents=True, exist_ok=True)
    OPENH264_DESTINO.write_bytes(contenido)
    _hecho(f"descargada y verificada {OPENH264_DESTINO.relative_to(RAIZ)}")


def _docker_disponible() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=15)
        return True
    except Exception:  # noqa: BLE001
        return False


def _contenedor_corriendo(nombre: str) -> bool:
    resultado = subprocess.run(
        ["docker", "ps", "--filter", f"name=^{nombre}$", "--filter", "status=running", "-q"],
        capture_output=True, text=True,
    )
    return bool(resultado.stdout.strip())


def levantar_postgres_y_esquema() -> None:
    _titulo("PostgreSQL (Docker) + esquema")
    if not _docker_disponible():
        _aviso("Docker no esta disponible (¿esta instalado y corriendo?). Sin esto no hay base de datos.")
        _aviso("Instala Docker Desktop, arrancalo, y vuelve a correr este script.")
        return

    if _contenedor_corriendo("gondola-postgres"):
        # Ya hay un contenedor con ese nombre corriendo -lo haya creado
        # `docker compose` o alguien a mano con `docker run`-: no hace
        # falta (ni conviene) volver a crearlo, `docker compose up -d`
        # falla con un conflicto de nombre si el contenedor existente no
        # quedo registrado como "de este proyecto de compose".
        _ok("el contenedor 'gondola-postgres' ya esta corriendo, no se toca")
    else:
        backend_dir = RAIZ / "backend"
        resultado = subprocess.run(
            ["docker", "compose", "up", "-d"], cwd=backend_dir, capture_output=True, text=True
        )
        if resultado.returncode != 0:
            _aviso(f"'docker compose up -d' fallo:\n{resultado.stderr}")
            return
        _hecho("contenedor de PostgreSQL levantado")

    print("  Esperando a que PostgreSQL acepte conexiones...")
    listo = False
    for _ in range(15):
        chequeo = subprocess.run(
            ["docker", "exec", "gondola-postgres", "pg_isready", "-U", "gondola"],
            capture_output=True,
        )
        if chequeo.returncode == 0:
            listo = True
            break
        time.sleep(2)
    if not listo:
        _aviso("PostgreSQL no respondio a tiempo; revisa 'docker logs gondola-postgres'")
        return

    ya_existe = subprocess.run(
        ["docker", "exec", "gondola-postgres", "psql", "-U", "gondola", "-d", "gondola",
         "-tAc", "SELECT to_regclass('public.videos')"],
        capture_output=True, text=True,
    )
    if ya_existe.returncode == 0 and ya_existe.stdout.strip() == "videos":
        _ok("el esquema ya estaba cargado (tabla 'videos' existe)")
        return

    schema = backend_dir / "database" / "schema.sql"
    if not schema.exists():
        _aviso(f"no encuentro {schema}")
        return
    with open(schema, "rb") as f:
        carga = subprocess.run(
            ["docker", "exec", "-i", "gondola-postgres", "psql", "-U", "gondola", "-d", "gondola"],
            stdin=f, capture_output=True, text=True,
        )
    if carga.returncode == 0:
        _hecho("esquema cargado (backend/database/schema.sql)")
    else:
        _aviso(f"fallo cargando el esquema:\n{carga.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", action="store_true", help="Ademas instala requirements.txt (~3 GB, PyTorch/YOLO)")
    parser.add_argument("--model", action="store_true", help="Ademas descarga data/models/yolo11n.pt")
    args = parser.parse_args()

    copiar_env_faltantes()
    instalar_dependencias_ligeras()
    if args.full:
        instalar_dependencias_pesadas()
    if args.model:
        descargar_modelo_yolo()
    descargar_openh264()
    levantar_postgres_y_esquema()

    print("\n" + "=" * 70)
    print("Listo. Siguiente paso:")
    print("  cd ai-service && python -m gondola doctor")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
