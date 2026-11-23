"""Construit l'exécutable Windows : dist/ChatLocal.exe (un seul fichier, sans console).

Prérequis : pip install -r requirements.txt pyinstaller
Usage     : python scripts/build_exe.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEP = ";" if sys.platform == "win32" else ":"

icon = ROOT / "assets" / "app.ico"
if not icon.exists():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_icon.py")], check=False)

cmd = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
    "--onefile", "--windowed", "--name", "ChatLocal",
    "--paths", str(ROOT),
    "--add-data", f"{ROOT / 'assets'}{SEP}assets",
    "--add-data", f"{ROOT / 'styles'}{SEP}styles",
    "--collect-submodules", "pygments",
    "--distpath", str(ROOT / "dist"),
    "--workpath", str(ROOT / "build"),
    "--specpath", str(ROOT / "build"),
]
if icon.exists():
    cmd += ["--icon", str(icon)]
cmd.append(str(ROOT / "main.py"))

print(" ".join(cmd))
code = subprocess.call(cmd, cwd=ROOT)
shutil.rmtree(ROOT / "build", ignore_errors=True)
exe = ROOT / "dist" / "ChatLocal.exe"
if code == 0 and exe.exists():
    dl = ROOT / "download"          # copie versionnée dans le dépôt : lien de téléchargement du README
    dl.mkdir(exist_ok=True)
    shutil.copy2(exe, dl / "ChatLocal.exe")
    print(f"\nExécutable prêt : {exe} ({exe.stat().st_size / 1_000_000:.0f} Mo)")
    print(f"Copie pour le dépôt : {dl / 'ChatLocal.exe'}")
    print("Ensuite : commiter, puis `python scripts/link_exe.py` (lien de téléchargement du README) et recommiter.")
sys.exit(code)
