"""Turn uploaded bytes or fetched pages into titled sections of plain text."""

import asyncio
from io import BytesIO
from pathlib import PurePath

import trafilatura
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from ragdesk.ingestion.chunking import Section, split_markdown
from ragdesk.ingestion.errors import IngestionError

PDF = "application/pdf"
MARKDOWN = "text/markdown"
PLAIN = "text/plain"
HTML = "text/html"

_BY_EXTENSION = {
    ".pdf": PDF,
    ".md": MARKDOWN,
    ".markdown": MARKDOWN,
    ".txt": PLAIN,
    ".html": HTML,
    ".htm": HTML,
}
MAX_PDF_PAGES = 500


def content_type_for(filename: str) -> str | None:
    """The supported content type for a file name, or None if it is not supported."""
    return _BY_EXTENSION.get(PurePath(filename).suffix.lower())


async def extract_sections(data: bytes, *, content_type: str, name: str) -> list[Section]:
    """Extract sections without blocking the event loop (PDF and HTML parsing are CPU-bound)."""
    sections = await asyncio.to_thread(_extract, data, content_type, name)
    if not sections:
        raise IngestionError("No readable text was found in this source")
    return sections


def _extract(data: bytes, content_type: str, name: str) -> list[Section]:
    if content_type == PDF:
        return _pdf(data)
    if content_type == HTML:
        return _html(data, name)
    if content_type in {MARKDOWN, PLAIN}:
        return split_markdown(_decode(data), fallback_title=name)
    raise IngestionError("Unsupported file type")


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").replace("\x00", "")


def _pdf(data: bytes) -> list[Section]:
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise IngestionError("Password-protected PDFs are not supported")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise IngestionError(f"PDFs are limited to {MAX_PDF_PAGES} pages")
        pages = [(page.extract_text() or "").replace("\x00", "").strip() for page in reader.pages]
    except PyPdfError as exc:
        raise IngestionError("The PDF could not be read") from exc
    return [Section(f"Page {number}", text) for number, text in enumerate(pages, start=1) if text]


def _html(data: bytes, name: str) -> list[Section]:
    html = _decode(data)
    markdown = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
        include_links=False,
        favor_precision=True,
    )
    if not markdown:
        return []
    metadata = trafilatura.extract_metadata(html)
    title = (metadata.title if metadata and metadata.title else None) or name
    return split_markdown(markdown, fallback_title=title)
