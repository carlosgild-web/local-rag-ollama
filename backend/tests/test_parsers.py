from pathlib import Path

import pytest

from app.ingest.parsers import UnsupportedFileTypeError, parse_file
from app.ingest.parsers.text_parser import parse_markdown, parse_txt

CORPUS = Path(__file__).parent / "corpus"


def test_parse_txt_splits_on_blank_lines():
    doc = parse_txt("First paragraph.\n\nSecond paragraph.\n")
    assert len(doc.blocks) == 2
    assert doc.blocks[0].text == "First paragraph."
    assert all(b.level == 0 for b in doc.blocks)


def test_parse_markdown_detects_headings_and_levels():
    text = "# Title\n\nIntro paragraph.\n\n## Section\n\nSection body.\n"
    doc = parse_markdown(text)
    levels = [(b.level, b.text) for b in doc.blocks]
    assert levels == [
        (1, "Title"),
        (0, "Intro paragraph."),
        (2, "Section"),
        (0, "Section body."),
    ]


def test_parse_markdown_joins_wrapped_paragraph_lines():
    text = "This line\nwraps onto\nthe next one.\n"
    doc = parse_markdown(text)
    assert len(doc.blocks) == 1
    assert doc.blocks[0].text == "This line wraps onto the next one."


def test_parse_file_dispatches_by_extension(tmp_path):
    txt_path = tmp_path / "note.txt"
    txt_path.write_text("Hello world.")
    doc = parse_file(txt_path)
    assert doc.blocks[0].text == "Hello world."


def test_parse_file_rejects_unsupported_extension(tmp_path):
    bad_path = tmp_path / "note.xyz"
    bad_path.write_text("whatever")
    with pytest.raises(UnsupportedFileTypeError):
        parse_file(bad_path)


def test_parse_docx_extracts_headings_and_paragraphs():
    doc = parse_file(CORPUS / "home-network-setup.docx")
    heading_texts = [b.text for b in doc.blocks if b.level > 0]
    assert "Home Network Setup Guide" in heading_texts
    assert "Choosing a Channel" in heading_texts
    assert any("router" in b.text.lower() for b in doc.blocks if b.level == 0)


def test_parse_docx_without_default_paragraph_style(tmp_path):
    """Some tools write .docx files with no default paragraph style, so
    unstyled paragraphs report style None. They are plain body text."""
    import docx
    from docx.oxml.ns import qn

    document = docx.Document()
    document.add_heading("Agreement", 1)
    document.add_paragraph("Payment is due in 30 days.")
    for style in document.styles.element.findall(qn("w:style")):
        if style.get(qn("w:type")) == "paragraph" and style.get(qn("w:default")) == "1":
            style.getparent().remove(style)
    path = tmp_path / "no-default-style.docx"
    document.save(path)

    doc = parse_file(path)
    assert [(b.text, b.level) for b in doc.blocks] == [
        ("Agreement", 1),
        ("Payment is due in 30 days.", 0),
    ]


def test_parse_docx_keeps_tables_in_document_order(tmp_path):
    """Key facts often sit in tables (an agreement number, a price list)."""
    import docx

    document = docx.Document()
    document.add_heading("Supplier Agreement", 1)
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Field", "Detail"
    table.cell(1, 0).text, table.cell(1, 1).text = "Agreement number", "XA-2026-014"
    document.add_paragraph("Payment is due in 30 days.")
    merged = document.add_table(rows=1, cols=3)
    merged.cell(0, 0).merge(merged.cell(0, 1)).text = "Merged title"
    merged.cell(0, 2).text = "Other"
    path = tmp_path / "with-tables.docx"
    document.save(path)

    texts = [b.text for b in parse_file(path).blocks]
    assert texts == [
        "Supplier Agreement",
        "Field | Detail",
        "Agreement number | XA-2026-014",
        "Payment is due in 30 days.",
        "Merged title | Other",
    ]


def test_parse_pdf_extracts_text_without_ocr():
    doc = parse_file(CORPUS / "energy-saving-tips.pdf")
    assert not any(b.needs_ocr for b in doc.blocks)
    full_text = doc.full_text.lower()
    assert "led bulbs" in full_text
    assert all(b.page == 1 for b in doc.blocks)


def test_parse_pdf_falls_back_to_ocr_for_scanned_page(tesseract_config):
    doc = parse_file(
        CORPUS / "consejos-ahorro-energia-scanned.pdf",
        ocr_min_text_chars=20,
        tesseract_cmd=tesseract_config["tesseract_cmd"],
        tessdata_prefix=tesseract_config["tessdata_prefix"],
    )
    assert doc.blocks, "OCR should have produced at least one text block"
    assert all(b.needs_ocr for b in doc.blocks)
    full_text = doc.full_text.lower()
    assert "energia" in full_text or "energía" in full_text
