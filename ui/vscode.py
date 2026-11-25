"""Ouvre le code généré dans VS Code (fichier temporaire mis à jour en direct pendant l'écriture)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


EXT = {"python": "py", "py": "py", "javascript": "js", "js": "js", "typescript": "ts", "ts": "ts", "html": "html",
       "css": "css", "json": "json", "bash": "sh", "sh": "sh", "shell": "sh", "powershell": "ps1", "ps1": "ps1",
       "c": "c", "cpp": "cpp", "c++": "cpp", "csharp": "cs", "cs": "cs", "java": "java", "go": "go", "rust": "rs",
       "rs": "rs", "sql": "sql", "markdown": "md", "md": "md", "yaml": "yml", "yml": "yml", "xml": "xml",
       "php": "php", "ruby": "rb", "kotlin": "kt", "swift": "swift", "lua": "lua", "pine": "pine"}


def extension_for(lang: str) -> str:
    return EXT.get((lang or "").lower().strip(), "txt")


_DIR = Path(tempfile.gettempdir()) / "ChatLocal" / "code"


def new_path(lang: str) -> Path:
    _DIR.mkdir(parents=True, exist_ok=True)
    return _DIR / f"code-{uuid.uuid4().hex[:8]}.{extension_for(lang)}"


def write(path: Path, code: str) -> None:
    try:
        if not path.exists() or path.read_text(encoding="utf-8") != code:
            path.write_text(code, encoding="utf-8", newline="\n")
    except OSError:
        pass


def _find_code_exe() -> str | None:
    cands = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cands.append(Path(local) / "Programs" / "Microsoft VS Code" / "Code.exe")
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        if base:
            cands.append(Path(base) / "Microsoft VS Code" / "Code.exe")
    for c in cands:
        if c.exists():
            return str(c)
    cli = shutil.which("code")                    # ...\Microsoft VS Code\bin\code(.cmd) -> ...\Code.exe
    if cli:
        exe = Path(cli).resolve().parent.parent / "Code.exe"
        return str(exe) if exe.exists() else cli
    return None


def open_in_vscode(path: Path) -> bool:
    """True si VS Code a été lancé ; sinon ouvre avec l'application par défaut et renvoie False."""
    exe = _find_code_exe()
    if exe:
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            subprocess.Popen([exe, "-r", str(path)], creationflags=flags, close_fds=True)
            return True
        except OSError:
            pass
    try:
        os.startfile(str(path))                   # type: ignore[attr-defined]
    except (OSError, AttributeError):
        pass
    return False
