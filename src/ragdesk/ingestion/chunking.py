"""Structure-aware chunking.

Documents are first split into sections (Markdown headings, PDF pages), then each section is packed
into chunks of about `target` characters without cutting paragraphs or sentences in half. The
section title travels with every chunk: it is embedded with the text and shown in the citation.
"""

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_FENCE = re.compile(r"^(```|~~~)")
MAX_TITLE_CHARS = 300


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    title: str
    content: str


def split_markdown(text: str, *, fallback_title: str) -> list[Section]:
    """Split Markdown at headings. The title is the heading path, e.g. `Guide > Install`."""
    sections: list[Section] = []
    path: list[tuple[int, str]] = []
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        body = "\n".join(buffer).strip()
        buffer.clear()
        if body:
            title = " > ".join(name for _, name in path) or fallback_title
            sections.append(Section(title[:MAX_TITLE_CHARS], body))

    for line in text.splitlines():
        if _FENCE.match(line.strip()):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match is None:
            buffer.append(line)
            continue
        flush()
        level = len(match.group(1))
        while path and path[-1][0] >= level:
            path.pop()
        path.append((level, match.group(2).strip()))
    flush()
    return sections


def chunk_sections(sections: list[Section], *, target: int) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    for section in sections:
        for content in _pack(_paragraphs(section.text), target):
            chunks.append(ChunkDraft(section.title, content))
    return chunks


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _pack(paragraphs: list[str], target: int) -> list[str]:
    """Greedy packing: add paragraphs until the next one would overflow the target."""
    pieces: list[str] = []
    for paragraph in paragraphs:
        pieces.extend(_split_long(paragraph, target))

    packed: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if current and len(candidate) > target:
            packed.append(current)
            current = piece
        else:
            current = candidate
    if current:
        packed.append(current)
    return packed


def _split_long(paragraph: str, target: int) -> list[str]:
    if len(paragraph) <= target:
        return [paragraph]
    parts: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(paragraph):
        for piece in _hard_split(sentence, target):
            candidate = f"{current} {piece}" if current else piece
            if current and len(candidate) > target:
                parts.append(current)
                current = piece
            else:
                current = candidate
    if current:
        parts.append(current)
    return parts


def _hard_split(text: str, target: int) -> list[str]:
    """Last resort for a single 'sentence' longer than the target (minified text, tables)."""
    if len(text) <= target:
        return [text]
    return [text[i : i + target] for i in range(0, len(text), target)]
