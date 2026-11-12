"""Serves original documents (demo files, stored uploads) for people to open.

PDFs and text open in the browser; Word files download, because browsers
can't show them. Markdown and text go out as plain text, never HTML, and
`nosniff` stops a browser from guessing otherwise.
"""

from pathlib import Path

from fastapi.responses import FileResponse

_INLINE = {
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
}
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def opens_in_browser(ext: str) -> bool:
    return ext.lower() in _INLINE


def original_response(path: Path, filename: str) -> FileResponse:
    ext = Path(filename).suffix.lower()
    inline = opens_in_browser(ext)
    return FileResponse(
        path,
        media_type=_INLINE.get(ext) or (_DOCX if ext == ".docx" else "application/octet-stream"),
        filename=filename,
        content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"},
    )
