"""Lanceur sans exécutable : double-clic (ou `pythonw ChatLocal.pyw`) pour ouvrir ChatLocal sans console.

Pratique si Windows bloque ChatLocal.exe (application non signée) : ce fichier n'est pas un .exe.
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
