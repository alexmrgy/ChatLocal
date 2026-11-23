"""Markdown -> segments (texte / code) et HTML compatible QTextDocument."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name

from . import theme

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([\w+#.-]*)")
_FORMATTER = HtmlFormatter(nowrap=True, noclasses=True, style="monokai")

DOC_CSS = f"""
body {{ color: {theme.TEXT}; }}
p {{ margin-top: 0; margin-bottom: 10px; }}
a {{ color: #7aa7ff; }}
h1 {{ font-size: 22px; margin-top: 14px; margin-bottom: 8px; }}
h2 {{ font-size: 19px; margin-top: 14px; margin-bottom: 8px; }}
h3 {{ font-size: 16px; margin-top: 12px; margin-bottom: 6px; }}
h4, h5, h6 {{ font-size: 15px; margin-top: 10px; margin-bottom: 4px; }}
ul, ol {{ margin-top: 0; margin-bottom: 10px; }}
li {{ margin-bottom: 0; }}
code {{ font-family: Consolas, 'Cascadia Mono', monospace; background-color: #2b2b2b; color: #e6e6e6; }}
blockquote {{ color: {theme.TEXT_DIM}; margin-left: 8px; }}
"""

CODE_CSS = "pre { margin: 0; font-family: 'Cascadia Mono', Consolas, monospace; font-size: 14px; }"


@dataclass
class Segment:
    kind: str          # "text" | "code"
    content: str
    lang: str = ""
    closed: bool = True


def split_segments(text: str) -> list[Segment]:
    segs: list[Segment] = []
    buf: list[str] = []
    in_code, fence, lang = False, "", ""

    def flush_text() -> None:
        s = "\n".join(buf).strip("\n")
        if s.strip():
            segs.append(Segment("text", s))
        buf.clear()

    for line in text.split("\n"):
        m = _FENCE.match(line)
        if not in_code:
            if m:
                flush_text()
                in_code, fence, lang = True, m.group(1), m.group(2)
            else:
                buf.append(line)
        else:
            s = line.strip()
            if s and set(s) <= {fence[0]} and len(s) >= len(fence):
                segs.append(Segment("code", "\n".join(buf), lang, True))
                buf.clear()
                in_code = False
            else:
                buf.append(line)
    if in_code:
        segs.append(Segment("code", "\n".join(buf), lang, False))
    else:
        flush_text()
    return segs


_TABLE = re.compile(r"<table>.*?</table>", re.S)
_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_CELL = re.compile(r"<(th|td)(?:\s[^>]*)?>(.*?)</\1>", re.S)
_NUM = re.compile(r"^[\d\s.,%€$£+\-−–/:()]+$")
_RULE = "border-bottom: 1px solid #2c2c2c;"


def _restyle_table(m: re.Match) -> str:
    """Tableau façon ChatGPT : sans cadre, filets horizontaux, colonnes numériques à droite."""
    rows = [_CELL.findall(r) for r in _ROW.findall(m.group(0))]
    if not rows:
        return m.group(0)
    ncol = max(len(r) for r in rows)
    numeric = []
    for c in range(ncol):
        vals = [re.sub(r"<[^>]+>", "", r[c][1]).strip() for r in rows[1:] if c < len(r)]
        numeric.append(bool(vals) and all(v and _NUM.match(v) for v in vals))
    out = ['<table width="100%" border="0" cellspacing="0" cellpadding="11">']
    for i, r in enumerate(rows):
        out.append("<tr>")
        for c, (tag, inner) in enumerate(r):
            align = "right" if numeric[c] else "left"
            style = "" if i == len(rows) - 1 else _RULE
            if tag == "th":
                inner = f"<b>{inner}</b>"
            out.append(f'<td align="{align}" style="{style}">{inner}</td>')
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def replace_code_segment(text: str, nth: int, new_code: str) -> str | None:
    """Remplace le contenu du nᵉ bloc de code (```…```) du texte Markdown ; None si introuvable."""
    lines = text.split("\n")
    in_code, fence, idx, start = False, "", -1, 0
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if not in_code:
            if m:
                in_code, fence, start = True, m.group(1), i + 1
                idx += 1
        else:
            s = line.strip()
            if s and set(s) <= {fence[0]} and len(s) >= len(fence):
                if idx == nth:
                    return "\n".join(lines[:start] + new_code.split("\n") + lines[i:])
                in_code = False
    if in_code and idx == nth:                       # bloc non refermé (code en cours d'écriture)
        return "\n".join(lines[:start] + new_code.split("\n"))
    return None


@lru_cache(maxsize=512)
def md_to_html(text: str) -> str:
    html = markdown.markdown(text, extensions=["tables", "sane_lists", "nl2br"])
    return _TABLE.sub(_restyle_table, html)


@lru_cache(maxsize=256)
def code_to_html(code: str, lang: str) -> str:
    try:
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except Exception:
        lexer = TextLexer()
    body = highlight(code, lexer, _FORMATTER).rstrip("\n")
    return f"<pre>{body}</pre>"
