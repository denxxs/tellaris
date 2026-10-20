"""Context files: pitch decks, product docs, pricing pages, research.

Uploads are stored under var/files/<id>/ with their extracted text. The planner
reads them to build the scenario; the analyst turns them into facts; simulated
people only see what a member of the public would (the scenario's description
and facts marked public), never internal notes.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .config import env

FILES_DIR = env.var_dir / "files"
FILES_DIR.mkdir(parents=True, exist_ok=True)

MAX_BYTES = 25 * 1024 * 1024
MAX_CHARS_PER_FILE = 60_000
ALLOWED = {".pdf", ".docx", ".pptx", ".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".xlsx"}


class FileError(ValueError):
    pass


def _clean(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(name: str, data: bytes) -> str:
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if ext == ".docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    if ext == ".pptx":
        from pptx import Presentation

        prs = Presentation(io.BytesIO(data))
        slides = []
        for i, slide in enumerate(prs.slides, 1):
            texts = [sh.text_frame.text for sh in slide.shapes if getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip()]
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    texts.append(f"(Speaker notes) {notes}")
            slides.append(f"Slide {i}:\n" + "\n".join(texts))
        return "\n\n".join(slides)
    if ext == ".xlsx":
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise FileError("Reading .xlsx needs openpyxl. Save the sheet as CSV instead.") from exc
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            out.append(f"Sheet: {ws.title}")
            for row in ws.iter_rows(values_only=True, max_row=400):
                if any(v is not None for v in row):
                    out.append(" | ".join("" if v is None else str(v) for v in row))
        return "\n".join(out)
    if ext == ".csv":
        rows = list(csv.reader(io.StringIO(data.decode("utf-8", errors="replace"))))[:400]
        return "\n".join(" | ".join(r) for r in rows)
    if ext in (".html", ".htm"):
        html = data.decode("utf-8", errors="replace")
        html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
        return re.sub(r"<[^>]+>", " ", html)
    return data.decode("utf-8", errors="replace")


def save(name: str, data: bytes) -> dict[str, Any]:
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise FileError(f"{Path(name).name}: this file type isn't supported. Use PDF, Word, PowerPoint, Excel, CSV, Markdown, HTML or text.")
    if len(data) > MAX_BYTES:
        raise FileError(f"{Path(name).name} is larger than 25 MB.")
    try:
        text = _clean(extract_text(name, data))
    except FileError:
        raise
    except Exception as exc:  # noqa: BLE001 - parsers raise many kinds of errors
        raise FileError(f"Couldn't read {Path(name).name}: {exc}") from exc
    if not text:
        raise FileError(f"{Path(name).name} has no readable text (a scanned PDF needs OCR first).")
    fid = uuid.uuid4().hex[:12]
    folder = FILES_DIR / fid
    folder.mkdir(parents=True)
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(name).name)[:120]
    (folder / safe).write_bytes(data)
    truncated = len(text) > MAX_CHARS_PER_FILE
    (folder / "text.txt").write_text(text[:MAX_CHARS_PER_FILE], encoding="utf-8")
    meta = {
        "id": fid, "name": safe, "size": len(data), "chars": len(text), "truncated": truncated,
        "preview": text[:280], "uploaded_at": time.time(),
    }
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def get(fid: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"[0-9a-f]{12}", fid or ""):
        return None
    folder = FILES_DIR / fid
    if not (folder / "meta.json").exists():
        return None
    return json.loads((folder / "meta.json").read_text(encoding="utf-8"))


def text_of(fid: str) -> str:
    meta = get(fid)
    if not meta:
        return ""
    return (FILES_DIR / fid / "text.txt").read_text(encoding="utf-8")


def delete(fid: str) -> bool:
    meta = get(fid)
    if not meta:
        return False
    folder = FILES_DIR / fid
    for p in folder.iterdir():
        p.unlink()
    folder.rmdir()
    return True


def bundle(file_ids: list[str], budget: int = 40_000) -> tuple[str, list[dict[str, Any]]]:
    """All files as one context block, shared fairly within a character budget."""
    metas = [m for m in (get(f) for f in file_ids) if m]
    if not metas:
        return "", []
    per = max(2000, budget // len(metas))
    parts = []
    for m in metas:
        t = text_of(m["id"])
        cut = t[:per]
        parts.append(f"=== FILE: {m['name']} ({m['chars']:,} characters{'; shortened' if len(t) > per else ''}) ===\n{cut}")
    return "\n\n".join(parts), metas
