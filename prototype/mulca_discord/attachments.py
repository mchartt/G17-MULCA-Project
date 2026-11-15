"""
The text of files attached to a message, for MUCA-Server.

Found live (16-17 Oct): Discord turns a paste over 2,000 characters into a
message.txt attachment, which the bot dropped -- groups pasted their user
analysis and MULCA never got it. Plain text, Word (.docx), PDF and
PowerPoint (.pptx, its slides' text) are read; anything else is named, so
MULCA can say it couldn't read it. A PDF made of scanned images has no text
to read and is named the same way.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Per message, all attachments together: a few pages of notes fit, while
# MULCA's 24k-token context keeps most of its room for the conversation.
MAX_CHARS = 20_000
# Not downloaded at all above this (Discord allows up to 10 MB on free
# servers; a text-heavy document is far smaller).
MAX_BYTES = 10 * 1024 * 1024

TEXT_EXTENSIONS = (".txt", ".md", ".csv", ".json", ".log", ".tsv")


@dataclass(frozen=True)
class AttachmentText:
    name: str
    text: str
    # The whole document's length, before any cut.
    chars: int
    # False when it couldn't be read at all (an image, a scan, too big).
    readable: bool = True

    @property
    def truncated(self) -> bool:
        return self.readable and len(self.text) < self.chars


def _kind(name: str, content_type: str | None) -> str | None:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".docx"):
        return "docx"
    # Found live (group 3, 25 Oct): a group shared its presentation.
    if lower.endswith(".pptx"):
        return "pptx"
    if lower.endswith(TEXT_EXTENSIONS) or (content_type or "").startswith("text/"):
        return "text"
    return None


def extract_text(name: str, data: bytes, content_type: str | None = None) -> str | None:
    """The text in a file's bytes, or None if it has none we can read."""

    kind = _kind(name, content_type)
    try:
        if kind == "text":
            return data.decode("utf-8", errors="replace")
        if kind == "docx":
            import docx  # python-docx

            document = docx.Document(io.BytesIO(data))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        if kind == "pdf":
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if kind == "pptx":
            import pptx  # python-pptx

            slides = []
            for number, slide in enumerate(pptx.Presentation(io.BytesIO(data)).slides, 1):
                texts = [
                    shape.text_frame.text
                    for shape in slide.shapes
                    if shape.has_text_frame and shape.text_frame.text.strip()
                ]
                notes = (
                    slide.notes_slide.notes_text_frame.text.strip()
                    if slide.has_notes_slide and slide.notes_slide.notes_text_frame
                    else ""
                )
                if notes:
                    texts.append(f"Notes: {notes}")
                if texts:
                    slides.append(f"Slide {number}:\n" + "\n".join(texts))
            return "\n\n".join(slides)
    except Exception:
        logger.warning("Could not read the text of %s", name, exc_info=True)
    return None


async def read_attachments(attachments) -> list[AttachmentText]:
    """
    Each attachment's text, in order, within MAX_CHARS for all of them
    together. discord.Attachment-like: name, size, content_type, read().
    """

    results: list[AttachmentText] = []
    room = MAX_CHARS
    for attachment in attachments:
        name = getattr(attachment, "filename", None) or getattr(attachment, "name", "file")
        content_type = getattr(attachment, "content_type", None)
        if _kind(name, content_type) is None or (attachment.size or 0) > MAX_BYTES:
            results.append(AttachmentText(name=name, text="", chars=0, readable=False))
            continue

        try:
            data = await attachment.read()
        except Exception:
            logger.warning("Could not download %s", name, exc_info=True)
            results.append(AttachmentText(name=name, text="", chars=0, readable=False))
            continue

        text = (extract_text(name, data, content_type) or "").strip()
        if not text:
            results.append(AttachmentText(name=name, text="", chars=0, readable=False))
            continue

        kept = text[:room]
        room -= len(kept)
        results.append(AttachmentText(name=name, text=kept, chars=len(text)))
    return results
