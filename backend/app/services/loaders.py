"""Read text out of PDF, DOCX, TXT and MD files."""
from pathlib import Path
from typing import List, Tuple

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

# (page_number or None, text)
Page = Tuple[int | None, str]


def load_pages(path: Path) -> List[Page]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _load_pdf(path)
    if ext == ".docx":
        return _load_docx(path)
    if ext in {".txt", ".md"}:
        return [(None, path.read_text(encoding="utf-8", errors="replace"))]
    raise ValueError(f"Unsupported file type: {ext}")


def load_text(path: Path) -> str:
    return "\n".join(text for _, text in load_pages(path))


def _load_pdf(path: Path) -> List[Page]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise ValueError("This PDF is password protected.") from exc
    pages: List[Page] = []
    for i, page in enumerate(reader.pages, start=1):
        pages.append((i, page.extract_text() or ""))
    return pages


def _load_docx(path: Path) -> List[Page]:
    from docx import Document

    doc = Document(str(path))
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = []
            for cell in row.cells:
                t = cell.text.strip().replace("\n", " ")
                if t and (not cells or cells[-1] != t):  # skip merged-cell repeats
                    cells.append(t)
            if cells:
                lines.append(" | ".join(cells))
    return [(None, "\n".join(lines))]
