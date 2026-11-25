"""Éditeur de code : numéros de ligne, coloration (pygments), indentation automatique."""
from __future__ import annotations

from bisect import bisect_right

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QSyntaxHighlighter, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.token import Token

from . import theme

FONT_FAMILIES = "Cascadia Code, Cascadia Mono, Consolas, monospace"

BG = "#0a0f1c"            # fond marine profond façon VS Code
LINE_BG = QColor(255, 255, 255, 14)
GUIDE = QColor(255, 255, 255, 24)

# palette de coloration : (type de jeton, couleur, gras, italique) ; le premier qui correspond gagne
PALETTE = [
    (Token.Comment, "#5c6b8a", False, True),
    (Token.Literal.String.Escape, "#f2c078", False, False),
    (Token.Literal.String, "#e7a56a", False, False),
    (Token.Literal.Number, "#f2d27a", False, False),
    (Token.Keyword.Constant, "#5ea6ff", False, False),
    (Token.Keyword.Namespace, "#a5b4fc", False, False),
    (Token.Operator.Word, "#5ea6ff", False, False),
    (Token.Keyword, "#a5b4fc", False, False),
    (Token.Name.Decorator, "#f2c078", False, False),
    (Token.Name.Class, "#7fdcc0", False, False),
    (Token.Name.Namespace, "#7fdcc0", False, False),
    (Token.Name.Exception, "#7fdcc0", False, False),
    (Token.Name.Function, "#f1f5fb", False, False),
    (Token.Name.Builtin, "#7fdcc0", False, False),
    (Token.Name.Tag, "#a5b4fc", False, False),
    (Token.Name.Attribute, "#7fdcc0", False, False),
    (Token.Operator, "#c7d2e6", False, False),
]


class _Highlighter(QSyntaxHighlighter):
    """Colore le document entier avec pygments (les commentaires / chaînes sur plusieurs lignes restent justes)."""

    def __init__(self, doc):
        super().__init__(doc)
        self._lexer = TextLexer()
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
        fmt = None
        for base, color, bold, italic in PALETTE:
            if ttype in base:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(color))
                if bold:
                    fmt.setFontWeight(QFont.Bold)
                if italic:
                    fmt.setFontItalic(True)
                break
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
        have = set(QFontDatabase.families())
        fam = next((n.strip() for n in FONT_FAMILIES.split(",") if n.strip() in have), None)
        f = QFont(fam) if fam else QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        f.setPixelSize(15)
        f.setStyleHint(QFont.Monospace)
        f.setFixedPitch(True)
        self.setFont(f)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.document().setDocumentMargin(12)
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
        sel.format.setBackground(LINE_BG)
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
            self._apply_line_height()

    def _apply_line_height(self) -> None:
        """Interligne aéré façon VS Code (appliqué à tout le document, hérité par les nouvelles lignes)."""
        fmt = QTextBlockFormat()
        fmt.setLineHeight(165, QTextBlockFormat.ProportionalHeight.value)
        c = QTextCursor(self.document())
        c.select(QTextCursor.Document)
        c.mergeBlockFormat(fmt)

    # ----- langage -----
    def set_language(self, lang: str) -> None:
        self._lang = (lang or "").lower()
        self.highlighter.set_language(lang)

    # ----- numéros de ligne -----
    def gutter_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 30 + self.fontMetrics().horizontalAdvance("9") * digits

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
        p.fillRect(e.rect(), QColor(BG))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        cur = self.textCursor().blockNumber()
        while block.isValid() and top <= e.rect().bottom():
            h = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + h >= e.rect().top():
                is_cur = block.blockNumber() == cur and not self.isReadOnly()
                if is_cur:
                    p.fillRect(0, top, self.gutter.width(), h, LINE_BG)
                f = QFont(self.font())
                f.setBold(is_cur)
                p.setFont(f)
                p.setPen(QColor("#e6edf7" if is_cur else "#47557a"))
                p.drawText(0, top, self.gutter.width() - 16, h, Qt.AlignRight | Qt.AlignVCenter,
                           str(block.blockNumber() + 1))
            block = block.next()
            top += h

    # ----- repères d'indentation -----
    @staticmethod
    def _indent_levels(text: str) -> int:
        return (len(text) - len(text.lstrip(" "))) // len(CodeEditor.INDENT)

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        p = QPainter(self.viewport())
        p.setPen(GUIDE)
        cw = self.fontMetrics().horizontalAdvance(" ")
        margin = self.document().documentMargin()
        block = self.firstVisibleBlock()
        carry = 0
        while block.isValid():
            geo = self.blockBoundingGeometry(block).translated(self.contentOffset())
            if geo.top() > e.rect().bottom():
                break
            text = block.text()
            if text.strip():
                levels = self._indent_levels(text)
                carry = levels
            else:
                nxt, look = block.next(), 0
                nxt_levels = 0
                while nxt.isValid() and look < 40:
                    if nxt.text().strip():
                        nxt_levels = self._indent_levels(nxt.text())
                        break
                    nxt, look = nxt.next(), look + 1
                levels = min(carry, nxt_levels)
            if geo.bottom() >= e.rect().top():
                for k in range(levels):
                    x = round(self.contentOffset().x() + margin + k * len(self.INDENT) * cw)
                    p.drawLine(x, round(geo.top()), x, round(geo.bottom()))
            block = block.next()

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
