"""Permite ejecutar el proyecto con `python -m gondola <subcomando>`.

Solo conecta el modulo con la CLI real, que vive en gondola/cli.py.
"""

import sys

from gondola.cli import main

sys.exit(main())
