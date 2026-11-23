"""Crée un raccourci « ChatLocal » sur le Bureau (avec le logo) qui lance l'application sans .exe.

Le raccourci démarre `pythonw ChatLocal.pyw` : c'est Python (signé par Microsoft) qui s'exécute, donc Windows
ne bloque rien. Usage : python scripts/create_shortcut.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
pythonw = Path(sys.executable).with_name("pythonw.exe")
if not pythonw.exists():
    sys.exit("pythonw.exe introuvable : installe Python depuis python.org (en cochant « Add to PATH »).")

desktop = Path.home() / "Desktop"
if not desktop.exists():
    desktop = Path.home() / "OneDrive" / "Bureau"
link = desktop / "Lancer ChatLocal.lnk"
ps = (
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
    "$s.TargetPath = '{py}';"
    "$s.Arguments = '\"{pyw}\"';"
    "$s.WorkingDirectory = '{wd}';"
    "$s.IconLocation = '{ico}';"
    "$s.Description = 'ChatLocal';"
    "$s.Save()"
).format(lnk=link, py=pythonw, pyw=ROOT / "ChatLocal.pyw", wd=ROOT, ico=ROOT / "assets" / "app.ico")
subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
print("Raccourci créé :", link)
