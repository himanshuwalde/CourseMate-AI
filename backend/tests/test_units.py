from app.services.chunking import split_text
from app.services.exporters import ExportItem, export, parse_blocks
from app.services.formats import detect_format
from app.services.prompts import cited_indexes, is_not_found, strip_citations
from app.services.question_parser import parse_with_regex


def test_chunking_overlap_and_size():
    text = ". ".join(f"Sentence number {i} about neural networks" for i in range(200))
    chunks = split_text(text, 500, 100)
    assert len(chunks) > 5
    assert all(len(c) <= 500 for c in chunks)
    assert split_text("short text", 500, 100) == ["short text"]
    assert split_text("   ", 500, 100) == []


def test_parse_numbered_questions_with_marks_and_headings():
    text = """UNIT I
1. What is overfitting? (5 marks)
   Explain with an example.
2) Define dropout. [2M]
UNIT II
Q3. Compare L1 and L2 regularization.
"""
    qs = parse_with_regex(text)
    assert [q["number"] for q in qs] == ["1", "2", "3"]
    assert qs[0]["marks"] == 5 and "Explain with an example." in qs[0]["text"]
    assert qs[1]["marks"] == 2
    assert "UNIT" not in qs[2]["text"]


def test_parse_table_rows():
    qs = parse_with_regex("1 | What is a GAN? | 5\n2 | Explain LSTM gates | 10")
    assert len(qs) == 2 and qs[1]["marks"] == 10


def test_helpers():
    assert detect_format("give me this as a PDF please") == "pdf"
    assert detect_format("export in a Word file") == "docx"
    assert detect_format("what is dropout") is None
    assert is_not_found("NOT_FOUND") and is_not_found("Not found, sorry")
    assert not is_not_found("Dropout is a technique")
    assert strip_citations("A fact [1][2]. Another [3]") == "A fact. Another"
    assert cited_indexes("x [1] y [3] z [9]", 3) == [1, 3]
    assert parse_blocks("# H\n- a\n1. b\n\ntext")[0] == ("h", "H")


def test_exports_open_correctly():
    from io import BytesIO

    from docx import Document
    from pypdf import PdfReader

    items = [ExportItem("What is dropout?", "**Dropout** drops units.\n- point one\n1. step", ["book.pdf, p.3"], 5)]
    docx_bytes, _, name = export("My Answers", items, "docx")
    text = "\n".join(p.text for p in Document(BytesIO(docx_bytes)).paragraphs)
    assert "Q1. What is dropout?" in text and "Sources: book.pdf, p.3" in text and name.endswith(".docx")

    pdf_bytes, _, _ = export("My Answers", items, "pdf")
    assert "Q1. What is dropout?" in PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()

    md, _, _ = export("My Answers", items, "md")
    assert b"## Q1." in md
