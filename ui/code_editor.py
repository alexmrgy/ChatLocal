"""Éditeur de code : numéros de ligne, coloration (pygments), indentation automatique."""
from __future__ import annotations

from bisect import bisect_right

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.styles import get_style_by_name

from . import theme

FONT_FAMILIES = "Cascadia Mono, Consolas, monospace"


class _Highlighter(QSyntaxHighlighter):
    """Colore le document entier avec pygments (les commentaires / chaînes sur plusieurs lignes restent justes)."""

    def __init__(self, doc):
        super().__init__(doc)
        self._lexer = TextLexer()
        self._style = get_style_by_name("github-dark")
        self._fmt_cache: dict = {}
        self._spans: dict[int, list[tuple[int, int, QTextCharFormat]]] = {}
        self._lexed = None            # texte déjà analysé : la coloration elle-même ne doit pas relancer l'analyse
        self._timer = QTimer(self, singleShot=True, interval=90)
        self._timer.timeout.connect(self._relex)
        doc.contentsChanged.connect(self._on_contents)

    def set_language(self, lang: str) -> None:
        try:
            self._lexer = get_lexer_by_name(lang) if lang else TextLexer()
        except Exception:
            self._lexer = TextLexer()
        self._relex()

    def _format(self, ttype) -> QTextCharFormat | None:
        if ttype in self._fmt_cache:
            return self._fmt_cache[ttype]
        st = self._style.style_for_token(ttype)
        fmt = None
        if st["color"] or st["bold"] or st["italic"]:
            fmt = QTextCharFormat()
            if st["color"]:
                fmt.setForeground(QColor("#" + st["color"]))
            if st["bold"]:
                fmt.setFontWeight(QFont.Bold)
            if st["italic"]:
                fmt.setFontItalic(True)
        self._fmt_cache[ttype] = fmt
        return fmt

    def _on_contents(self) -> None:
        if self.document().toPlainText() != self._lexed:
            self._timer.start()

    def _relex(self) -> None:
        text = self.document().toPlainText()
        self._lexed = text
        starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                starts.append(i + 1)
        spans: dict[int, list] = {}
        for pos, ttype, val in self._lexer.get_tokens_unprocessed(text):
            fmt = self._format(ttype)
            if fmt is None:
                continue
            line = bisect_right(starts, pos) - 1
            off = pos
            for part in val.split("\n"):
                if part:
                    spans.setdefault(line, []).append((off - starts[line], len(part), fmt))
                off += len(part) + 1
                line += 1
        self._spans = spans
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for start, length, fmt in self._spans.get(self.currentBlock().blockNumber(), ()):
            self.setFormat(start, length, fmt)


class _Gutter(QWidget):
    def __init__(self, editor: "CodeEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.gutter_width(), 0)

    def paintEvent(self, e) -> None:
        self._editor.paint_gutter(e)


class CodeEditor(QPlainTextEdit):
    INDENT = "    "

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CodeEditor")
        self.setFrameShape(QPlainTextEdit.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        f = QFont()
        f.setFamilies([s.strip() for s in FONT_FAMILIES.split(",")])
        f.setPixelSize(13)
        f.setStyleHint(QFont.Monospace)
        self.setFont(f)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.document().setDocumentMargin(10)
        self.setCursorWidth(2)
        self._lang = ""
        self.highlighter = _Highlighter(self.document())
        self.gutter = _Gutter(self)
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._scroll_gutter)
        self.cursorPositionChanged.connect(self._highlight_line)
        self._update_margin()
        self._highlight_line()

    # ----- ligne courante -----
    def _highlight_line(self) -> None:
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor(255, 255, 255, 12))
        sel.format.setProperty(QTextCharFormat.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([] if self.isReadOnly() else [sel])
        self.gutter.update()

    # ----- ajout en fin de code (génération en direct, sans tout recharger) -----
    def set_code(self, code: str) -> None:
        cur = self.toPlainText()
        if cur and code.startswith(cur):
            if code != cur:
                c = QTextCursor(self.document())
                c.movePosition(QTextCursor.MoveOperation.End)
                c.insertText(code[len(cur):])
        else:
            self.setPlainText(code)

    # ----- langage -----
    def set_language(self, lang: str) -> None:
        self._lang = (lang or "").lower()
        self.highlighter.set_language(lang)

    # ----- numéros de ligne -----
    def gutter_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 22 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margin(self, *_) -> None:
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _scroll_gutter(self, rect, dy) -> None:
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margin()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, e) -> None:
        p = QPainter(self.gutter)
        p.fillRect(e.rect(), QColor("#0f1013"))
        p.fillRect(self.gutter.width() - 1, e.rect().top(), 1, e.rect().height(), QColor(255, 255, 255, 14))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        cur = self.textCursor().blockNumber()
        while block.isValid() and top <= e.rect().bottom():
            h = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + h >= e.rect().top():
                p.setPen(QColor("#c9d1d9" if block.blockNumber() == cur else "#4d5360"))
                p.drawText(0, top, self.gutter.width() - 12, self.fontMetrics().height(), Qt.AlignRight,
                           str(block.blockNumber() + 1))
            block = block.next()
            top += h

    # ----- édition de plusieurs lignes -----
    def _selected_blocks(self):
        c = self.textCursor()
        doc = self.document()
        first = doc.findBlock(c.selectionStart())
        end = c.selectionEnd()
        last = doc.findBlock(end)
        if c.hasSelection() and end == last.position() and last != first:
            last = last.previous()                       # la sélection finit au début d'une ligne : on ne la compte pas
        out = []
        b = first
        while b.isValid():
            out.append(b)
            if b == last:
                break
            b = b.next()
        return out

    def _shift_lines(self, direction: int) -> None:
        """Tab / Maj+Tab : indente ou désindente toutes les lignes touchées par la sélection."""
        blocks = self._selected_blocks()
        c = self.textCursor()
        c.beginEditBlock()
        for b in blocks:
            cur = QTextCursor(b)
            if direction > 0:
                if b.text().strip():             # pas d'espaces inutiles sur les lignes vides
                    cur.insertText(self.INDENT)
            else:
                line = b.text()
                n = min(len(self.INDENT), len(line) - len(line.lstrip(" ")))
                if n:
                    cur.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, n)
                    cur.removeSelectedText()
        c.endEditBlock()

    COMMENT = {"python": "# ", "py": "# ", "bash": "# ", "sh": "# ", "shell": "# ", "powershell": "# ", "ps1": "# ",
               "ruby": "# ", "yaml": "# ", "yml": "# ", "sql": "-- ", "lua": "-- "}

    def _toggle_comment(self) -> None:
        """Ctrl+/ : commente ou décommente les lignes sélectionnées."""
        mark = self.COMMENT.get(self._lang, "// ")
        blocks = [b for b in self._selected_blocks() if b.text().strip()]
        if not blocks:
            return
        all_commented = all(b.text().lstrip().startswith(mark.strip()) for b in blocks)
        c = self.textCursor()
        c.beginEditBlock()
        for b in blocks:
            cur = QTextCursor(b)
            text = b.text()
            ind = len(text) - len(text.lstrip(" \t"))
            cur.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, ind)
            if all_commented:
                rest = text[ind:]
                n = len(mark) if rest.startswith(mark) else len(mark.strip())
                cur.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, n)
                cur.removeSelectedText()
            else:
                cur.insertText(mark)
        c.endEditBlock()

    # ----- saisie -----
    def keyPressEvent(self, e) -> None:
        if self.isReadOnly():
            return super().keyPressEvent(e)
        key = e.key()
        if key == Qt.Key_Tab and not (e.modifiers() & Qt.ShiftModifier):
            if self.textCursor().hasSelection():
                self._shift_lines(+1)
            else:
                self.insertPlainText(self.INDENT)
            return
        if key == Qt.Key_Backtab:
            self._shift_lines(-1)
            return
        if key == Qt.Key_Slash and (e.modifiers() & Qt.ControlModifier):
            self._toggle_comment()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            line = self.textCursor().block().text()
            before = line[: self.textCursor().positionInBlock()]
            indent = line[: len(line) - len(line.lstrip(" \t"))]
            extra = ""
            stripped = before.rstrip()
            if stripped.endswith((":", "{", "(", "[")) and (self._lang in ("python", "py", "c", "cpp", "")
                                                           or stripped.endswith("{")):
                extra = self.INDENT
            self.insertPlainText("\n" + indent + extra)
            return
        super().keyPressEvent(e)
