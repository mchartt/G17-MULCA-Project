"""Reading the text of attached files (mulca_discord/attachments.py)."""

import io

import pytest

from mulca_discord import attachments as attachments_module
from mulca_discord.attachments import extract_text, read_attachments


class FakeAttachment:
    def __init__(self, filename, data, *, content_type=None, size=None):
        self.filename = filename
        self._data = data
        self.content_type = content_type
        self.size = len(data) if size is None else size
        self.reads = 0

    async def read(self):
        self.reads += 1
        return self._data


async def test_a_pasted_message_txt_is_read():
    paste = FakeAttachment("message.txt", "PRIMARY USERS children".encode())

    [result] = await read_attachments([paste])

    assert result.text == "PRIMARY USERS children"
    assert result.chars == 22 and result.readable and not result.truncated


async def test_long_text_is_cut_across_all_attachments_together(monkeypatch):
    monkeypatch.setattr(attachments_module, "MAX_CHARS", 10)
    first = FakeAttachment("a.md", b"123456")
    second = FakeAttachment("b.txt", b"abcdefgh")

    one, two = await read_attachments([first, second])

    assert one.text == "123456" and not one.truncated
    assert two.text == "abcd" and two.chars == 8 and two.truncated


async def test_images_and_huge_files_are_named_but_not_downloaded():
    image = FakeAttachment("photo.png", b"\x89PNG", content_type="image/png")
    huge = FakeAttachment("big.txt", b"x", size=50 * 1024 * 1024)

    results = await read_attachments([image, huge])

    assert [r.readable for r in results] == [False, False]
    assert [r.name for r in results] == ["photo.png", "big.txt"]
    assert image.reads == 0 and huge.reads == 0


async def test_an_attachment_with_no_text_is_unreadable():
    [result] = await read_attachments([FakeAttachment("empty.txt", b"   ")])

    assert not result.readable


def test_a_word_file_is_read():
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Stakeholders: children")
    document.add_paragraph("Needs: clear cues")
    buffer = io.BytesIO()
    document.save(buffer)

    assert extract_text("analysis.docx", buffer.getvalue()) == (
        "Stakeholders: children\nNeeds: clear cues"
    )


def test_a_powerpoint_file_is_read_slide_by_slide():
    pptx = pytest.importorskip("pptx")
    presentation = pptx.Presentation()
    first = presentation.slides.add_slide(presentation.slide_layouts[1])
    first.shapes.title.text = "Math Without Pressure"
    first.placeholders[1].text = "A farm game for children 6-10"
    first.notes_slide.notes_text_frame.text = "Mention the art style"
    second = presentation.slides.add_slide(presentation.slide_layouts[5])
    second.shapes.title.text = "Art direction"
    buffer = io.BytesIO()
    presentation.save(buffer)

    assert extract_text("pitch.pptx", buffer.getvalue()) == (
        "Slide 1:\nMath Without Pressure\nA farm game for children 6-10\n"
        "Notes: Mention the art style\n\n"
        "Slide 2:\nArt direction"
    )


def test_a_pdf_is_read():
    pytest.importorskip("pypdf")
    # A minimal one-page PDF with one line of text.
    stream = b"BT /F1 12 Tf 72 720 Td (Primary users: children) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    pdf += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )

    assert "Primary users: children" in extract_text("paper.pdf", pdf)


def test_a_broken_pdf_has_no_text():
    pytest.importorskip("pypdf")

    assert extract_text("broken.pdf", b"not a pdf") is None
