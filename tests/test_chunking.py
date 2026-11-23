from ragdesk.ingestion.chunking import Section, chunk_sections, split_markdown

MARKDOWN = """# Guide

Intro text.

## Install

Run the installer.

### Linux

Use apt.

## Usage

Start the app.
"""


def test_markdown_sections_carry_the_heading_path() -> None:
    sections = split_markdown(MARKDOWN, fallback_title="guide.md")
    assert [s.title for s in sections] == [
        "Guide",
        "Guide > Install",
        "Guide > Install > Linux",
        "Guide > Usage",
    ]
    assert sections[2].text == "Use apt."


def test_text_without_headings_uses_the_fallback_title() -> None:
    sections = split_markdown("Just a paragraph.", fallback_title="notes.txt")
    assert sections == [Section("notes.txt", "Just a paragraph.")]


def test_hash_comments_inside_code_fences_are_not_headings() -> None:
    text = "# Setup\n\n```bash\n# install deps\npip install x\n```\n"
    sections = split_markdown(text, fallback_title="x")
    assert [s.title for s in sections] == ["Setup"]
    assert "# install deps" in sections[0].text


def test_small_paragraphs_are_packed_into_one_chunk() -> None:
    chunks = chunk_sections([Section("T", "one\n\ntwo\n\nthree")], target=100)
    assert [c.content for c in chunks] == ["one\n\ntwo\n\nthree"]
    assert chunks[0].title == "T"


def test_chunks_never_exceed_the_target() -> None:
    paragraph = " ".join(f"Sentence number {i} is here." for i in range(60))
    chunks = chunk_sections([Section("T", paragraph + "\n\n" + paragraph)], target=300)
    assert len(chunks) > 4
    assert all(len(c.content) <= 300 for c in chunks)


def test_a_single_unbreakable_run_is_hard_split() -> None:
    chunks = chunk_sections([Section("T", "x" * 1000)], target=400)
    assert [len(c.content) for c in chunks] == [400, 400, 200]


def test_no_text_is_lost_when_chunking() -> None:
    text = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(12))
    chunks = chunk_sections([Section("T", text)], target=500)
    joined = " ".join(c.content for c in chunks)
    for i in range(12):
        assert f"Paragraph {i} " in joined


def test_empty_sections_produce_no_chunks() -> None:
    assert chunk_sections([Section("T", "   \n\n  ")], target=100) == []
