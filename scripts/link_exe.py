"""Fait pointer le lien de téléchargement du README vers la version exacte de l'exécutable.

Le lien contient l'identifiant (SHA) du dernier commit qui a modifié download/ChatLocal.exe : cette adresse est
unique pour chaque version, donc aucun cache (navigateur ou GitHub) ne peut servir une ancienne copie.

À lancer APRÈS avoir commité (et idéalement poussé) un nouvel exécutable, puis commiter le README :
    python scripts/link_exe.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sha = subprocess.run(["git", "log", "-1", "--format=%H", "--", "download/ChatLocal.exe"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
if not sha:
    sys.exit("Aucun commit ne contient download/ChatLocal.exe : commite d'abord l'exécutable.")

readme = ROOT / "README.md"
text = readme.read_text(encoding="utf-8")
pattern = r"https://raw\.githubusercontent\.com/alexmrgy/ChatLocal/[^/\s\"')]+/download/ChatLocal\.exe(\?v=\d+)?"
new = f"https://raw.githubusercontent.com/alexmrgy/ChatLocal/{sha}/download/ChatLocal.exe"
text, n = re.subn(pattern, new, text)
readme.write_text(text, encoding="utf-8")
print(f"{n} lien(s) mis à jour -> {new}")
