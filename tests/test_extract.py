import pytest

from ragdesk.ingestion.errors import IngestionError
from ragdesk.ingestion.extract import HTML, MARKDOWN, PDF, PLAIN, content_type_for, extract_sections
from tests.pdfs import make_pdf


def test_content_type_is_chosen_by_extension() -> None:
    assert content_type_for("Manual.PDF") == PDF
    assert content_type_for("notes.md") == MARKDOWN
    assert content_type_for("readme.txt") == PLAIN
    assert content_type_for("page.html") == HTML
    assert content_type_for("virus.exe") is None
    assert content_type_for("no-extension") is None


async def test_pdf_pages_become_sections_titled_by_page_number() -> None:
    data = make_pdf([["Refunds are issued within 14 days."], ["Shipping takes 3 to 5 days."]])
    sections = await extract_sections(data, content_type=PDF, name="policy.pdf")
    assert [s.title for s in sections] == ["Page 1", "Page 2"]
    assert "Refunds are issued within 14 days." in sections[0].text
    assert "Shipping takes 3 to 5 days." in sections[1].text


async def test_garbage_pdf_is_rejected_with_a_safe_message() -> None:
    with pytest.raises(IngestionError, match="could not be read"):
        await extract_sections(b"%PDF-1.4 not really", content_type=PDF, name="x.pdf")


async def test_markdown_keeps_the_heading_structure() -> None:
    data = b"# Guide\n\n## Install\n\nRun it.\n"
    sections = await extract_sections(data, content_type=MARKDOWN, name="guide.md")
    assert [s.title for s in sections] == ["Guide > Install"]


async def test_plain_text_tolerates_invalid_bytes_and_nul() -> None:
    sections = await extract_sections(b"caf\xe9 \x00ok", content_type=PLAIN, name="a.txt")
    assert sections[0].title == "a.txt"
    assert "\x00" not in sections[0].text


async def test_html_keeps_the_article_and_drops_the_navigation() -> None:
    sentence = b"You can return any item within thirty days of delivery for a full refund. "
    html = (
        b"<html><head><title>Returns policy</title></head><body>"
        b"<nav><a href='/'>Home</a><a href='/x'>Careers</a></nav>"
        b"<article><h1>Returns</h1><p>" + sentence * 6 + b"</p></article>"
        b"<footer>Copyright</footer></body></html>"
    )
    sections = await extract_sections(html, content_type=HTML, name="page")
    text = " ".join(s.text for s in sections)
    assert "thirty days" in text
    assert "Careers" not in text


async def test_empty_source_is_an_error() -> None:
    with pytest.raises(IngestionError, match="No readable text"):
        await extract_sections(b"   ", content_type=PLAIN, name="empty.txt")
