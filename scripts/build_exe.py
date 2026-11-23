"""Construit l'exécutable Windows : dist/ChatLocal.exe (un seul fichier, sans console).

Prérequis : pip install -r requirements.txt pyinstaller
Usage     : python scripts/build_exe.py
"""
import re
import shutil
import subprocess
import sys
import time
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
    # change le paramètre ?v= du lien de téléchargement du README : plus de vieille version servie par le cache
    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        pattern = r"(raw\.githubusercontent\.com/[^\s\"')]*download/ChatLocal\.exe)(\?v=\d+)?"
        readme.write_text(re.sub(pattern, rf"\g<1>?v={int(time.time())}", text), encoding="utf-8")
    print(f"\nExécutable prêt : {exe} ({exe.stat().st_size / 1_000_000:.0f} Mo)")
    print(f"Copie pour le dépôt : {dl / 'ChatLocal.exe'}")
sys.exit(code)
