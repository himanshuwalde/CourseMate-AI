"""Render answers to DOCX, PDF or Markdown. The LLM never writes binary files: it produces text,
and this module turns that text into a nicely formatted document."""
import re
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Tuple
from xml.sax.saxutils import escape

MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "md": "text/markdown",
}


@dataclass
class ExportItem:
    question: str
    answer: str
    sources: List[str] = field(default_factory=list)
    marks: Optional[int] = None
    note: Optional[str] = None


# ---------- tiny markdown parsing shared by DOCX and PDF ----------
_BOLD_OR_ITALIC = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*)")


def parse_blocks(text: str) -> List[Tuple]:
    blocks: List[Tuple] = []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            blocks.append(("gap",))
            continue
        stripped = line.strip()
        if m := re.match(r"^#{1,6}\s+(.*)$", stripped):
            blocks.append(("h", m.group(1)))
        elif m := re.match(r"^[-*\u2022]\s+(.*)$", stripped):
            blocks.append(("ul", m.group(1)))
        elif m := re.match(r"^(\d{1,2})[.)]\s+(.*)$", stripped):
            blocks.append(("ol", m.group(1), m.group(2)))
        else:
            blocks.append(("p", stripped))
    # collapse repeated gaps and drop leading/trailing ones
    out: List[Tuple] = []
    for b in blocks:
        if b[0] == "gap" and (not out or out[-1][0] == "gap"):
            continue
        out.append(b)
    while out and out[-1][0] == "gap":
        out.pop()
    return out


def _inline_runs(text: str) -> List[Tuple[str, bool, bool]]:
    """-> [(text, bold, italic)]"""
    text = text.replace("`", "")
    runs = []
    for part in _BOLD_OR_ITALIC.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            runs.append((part[2:-2], True, False))
        elif part.startswith("__") and part.endswith("__") and len(part) > 4:
            runs.append((part[2:-2], True, False))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            runs.append((part[1:-1], False, True))
        else:
            runs.append((part, False, False))
    return runs


def sources_line(item: ExportItem) -> str:
    return "Sources: " + "; ".join(item.sources) if item.sources else ""


def _subtitle(extra: str = "") -> str:
    stamp = datetime.now().strftime("%d %b %Y, %H:%M")
    return f"Generated {stamp}" + (f" · {extra}" if extra else "")


# ---------- DOCX ----------
def to_docx(title: str, subtitle: str, items: List[ExportItem]) -> bytes:
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    doc.add_heading(title, level=0)
    if subtitle:
        p = doc.add_paragraph()
        r = p.add_run(subtitle)
        r.italic = True
        r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    def add_runs(paragraph, text, base_bold=False):
        for t, bold, italic in _inline_runs(text):
            run = paragraph.add_run(t)
            run.bold = bold or base_bold
            run.italic = italic

    for n, item in enumerate(items, start=1):
        q = doc.add_paragraph()
        q.paragraph_format.space_before = Pt(14)
        q.paragraph_format.keep_with_next = True
        label = f"Q{n}. {item.question}" + (f"  [{item.marks} marks]" if item.marks else "")
        run = q.add_run(label)
        run.bold = True
        run.font.size = Pt(12)

        for block in parse_blocks(item.answer):
            kind = block[0]
            if kind == "gap":
                continue
            if kind == "h":
                add_runs(doc.add_paragraph(), block[1], base_bold=True)
            elif kind == "ul":
                add_runs(doc.add_paragraph(style="List Bullet"), block[1])
            elif kind == "ol":  # manual numbering: Word's "List Number" continues across questions
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Pt(18)
                add_runs(p, f"{block[1]}. {block[2]}")
            else:
                add_runs(doc.add_paragraph(), block[1])

        for extra in (item.note, sources_line(item)):
            if extra:
                p = doc.add_paragraph()
                r = p.add_run(extra)
                r.italic = True
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------- PDF ----------
_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", None, None),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariali.ttf"),
]
_FONT_NAME: Optional[str] = None


def _pdf_font() -> str:
    """Register a Unicode TTF if one exists on this machine; otherwise fall back to built-in Helvetica."""
    global _FONT_NAME
    if _FONT_NAME:
        return _FONT_NAME
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for regular, bold, italic in _FONT_CANDIDATES:
        if Path(regular).exists():
            pdfmetrics.registerFont(TTFont("Body", regular))
            pdfmetrics.registerFont(TTFont("Body-Bold", bold if bold and Path(bold).exists() else regular))
            pdfmetrics.registerFont(TTFont("Body-Italic", italic if italic and Path(italic).exists() else regular))
            pdfmetrics.registerFont(TTFont("Body-BoldItalic", bold if bold and Path(bold).exists() else regular))
            pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic",
                                          boldItalic="Body-BoldItalic")
            _FONT_NAME = "Body"
            return _FONT_NAME
    _FONT_NAME = "Helvetica"
    return _FONT_NAME


def _pdf_safe(text: str, unicode_ok: bool) -> str:
    if unicode_ok:
        return text
    repl = {"\u2192": "->", "\u2190": "<-", "\u2264": "<=", "\u2265": ">=", "\u2022": "-", "\u2713": "v"}
    for a, b in repl.items():
        text = text.replace(a, b)
    return text.encode("cp1252", "replace").decode("cp1252")


def to_pdf(title: str, subtitle: str, items: List[ExportItem]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    font = _pdf_font()
    unicode_ok = font == "Body"
    bold = "Body-Bold" if unicode_ok else "Helvetica-Bold"

    def style(name, **kw):
        return ParagraphStyle(name, fontName=kw.pop("fontName", font), **kw)

    s_title = style("T", fontName=bold, fontSize=20, leading=25, spaceAfter=4)
    s_sub = style("S", fontSize=9, leading=12, textColor=colors.HexColor("#666666"), spaceAfter=10)
    s_q = style("Q", fontName=bold, fontSize=12, leading=16, spaceBefore=14, spaceAfter=4)
    s_body = style("B", fontSize=10.5, leading=15, spaceAfter=3)
    s_bullet = style("L", fontSize=10.5, leading=15, leftIndent=16, bulletIndent=4, spaceAfter=2)
    s_head = style("H", fontName=bold, fontSize=10.5, leading=15, spaceBefore=4, spaceAfter=2)
    s_small = style("M", fontSize=8.5, leading=11, textColor=colors.HexColor("#666666"), spaceAfter=2)

    def inline(text: str) -> str:
        text = escape(_pdf_safe(text.replace("`", ""), unicode_ok))
        text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)
        text = re.sub(r"(?<!\*)\*([^*\s][^*]*)\*(?!\*)", r"<i>\1</i>", text)
        return text

    story = [Paragraph(inline(title), s_title)]
    if subtitle:
        story.append(Paragraph(inline(subtitle), s_sub))

    for n, item in enumerate(items, start=1):
        label = f"Q{n}. {item.question}" + (f"  [{item.marks} marks]" if item.marks else "")
        parts = [Paragraph(inline(label), s_q)]
        for block in parse_blocks(item.answer):
            kind = block[0]
            if kind == "gap":
                parts.append(Spacer(1, 3))
            elif kind == "h":
                parts.append(Paragraph(inline(block[1]), s_head))
            elif kind == "ul":
                parts.append(Paragraph(inline(block[1]), s_bullet, bulletText="\u2022" if unicode_ok else "-"))
            elif kind == "ol":
                parts.append(Paragraph(inline(block[2]), s_bullet, bulletText=f"{block[1]}."))
            else:
                parts.append(Paragraph(inline(block[1]), s_body))
        for extra in (item.note, sources_line(item)):
            if extra:
                parts.append(Paragraph("<i>" + inline(extra) + "</i>", s_small))
        story.append(KeepTogether(parts[:2]))  # keep the question with the first line of its answer
        story.extend(parts[2:])

    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                      bottomMargin=18 * mm, title=title).build(story)
    return buf.getvalue()


# ---------- Markdown ----------
def to_markdown(title: str, subtitle: str, items: List[ExportItem]) -> bytes:
    out = [f"# {title}", ""]
    if subtitle:
        out += [f"*{subtitle}*", ""]
    for n, item in enumerate(items, start=1):
        out.append(f"## Q{n}. {item.question}" + (f" ({item.marks} marks)" if item.marks else ""))
        out += ["", item.answer.strip(), ""]
        if item.note:
            out += [f"*{item.note}*", ""]
        if item.sources:
            out += [f"*{sources_line(item)}*", ""]
    return "\n".join(out).encode("utf-8")


def safe_filename(title: str, ext: str) -> str:
    base = re.sub(r"[^\w\- ]+", "", title).strip().replace(" ", "_")[:60] or "answers"
    return f"{base}.{ext}"


def export(title: str, items: List[ExportItem], fmt: str, subtitle: str = "") -> Tuple[bytes, str, str]:
    """-> (file bytes, mime type, filename)"""
    fmt = fmt.lower()
    if fmt not in MIME:
        raise ValueError(f"Unsupported format '{fmt}'. Use docx, pdf or md.")
    subtitle = subtitle or _subtitle()
    builder = {"docx": to_docx, "pdf": to_pdf, "md": to_markdown}[fmt]
    return builder(title, subtitle, items), MIME[fmt], safe_filename(title, fmt)
