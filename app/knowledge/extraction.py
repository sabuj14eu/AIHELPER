"""Text extraction from uploaded files.

Supported: PDF, TXT, Markdown, DOCX, CSV, JSON.

A format we cannot read is an explicit error, never an empty document. A
document that silently ingests as zero characters is worse than a rejected
upload: it looks present in the listing and answers nothing.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field

from app.core.errors import ValidationError

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".docx", ".csv", ".json", ".jsonl"}

MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
}


@dataclass
class Extraction:
    text: str
    page_count: int = 0
    meta: dict = field(default_factory=dict)


def extension_of(filename: str) -> str:
    name = (filename or "").lower()
    for ext in sorted(SUPPORTED_EXTENSIONS, key=len, reverse=True):
        if name.endswith(ext):
            return ext
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def extract(data: bytes, filename: str) -> Extraction:
    ext = extension_of(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValidationError(
            f"unsupported file type '{ext or filename}'. Supported: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )
    if not data:
        raise ValidationError("the uploaded file is empty")

    if ext == ".pdf":
        return _extract_pdf(data)
    if ext == ".docx":
        return _extract_docx(data)
    if ext == ".csv":
        return _extract_csv(data)
    if ext in (".json", ".jsonl"):
        return _extract_json(data, ext)
    return _extract_text(data)


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1250", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_text(data: bytes) -> Extraction:
    text = _decode(data)
    if not text.strip():
        raise ValidationError("the file contains no text")
    return Extraction(text=text, meta={"encoding": "detected"})


def _extract_pdf(data: bytes) -> Extraction:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ValidationError("PDF support requires the 'pypdf' package") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ValidationError("the PDF is encrypted and cannot be read") from exc
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(f"could not read the PDF: {type(exc).__name__}") from exc

    text = "\n\n".join(f"[page {i + 1}]\n{p}".rstrip() for i, p in enumerate(pages) if p.strip())
    if not text.strip():
        # The honest failure. A scanned PDF has no text layer, and pretending
        # otherwise produces a document that answers nothing.
        raise ValidationError(
            "no text layer found in this PDF — it is probably a scan, which needs OCR "
            "before it can be ingested"
        )
    return Extraction(text=text, page_count=len(pages), meta={"pages": len(pages)})


def _extract_docx(data: bytes) -> Extraction:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ValidationError("DOCX support requires the 'python-docx' package") from exc
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ValidationError(f"could not read the DOCX: {type(exc).__name__}") from exc

    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table_index, table in enumerate(document.tables):
        rows = [
            " | ".join(cell.text.strip() for cell in row.cells)
            for row in table.rows
            if any(c.text.strip() for c in row.cells)
        ]
        if rows:
            parts.append(f"[table {table_index + 1}]\n" + "\n".join(rows))
    text = "\n\n".join(parts)
    if not text.strip():
        raise ValidationError("the DOCX contains no readable text")
    return Extraction(
        text=text,
        meta={"paragraphs": len(document.paragraphs), "tables": len(document.tables)},
    )


def _extract_csv(data: bytes) -> Extraction:
    raw = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(raw), dialect)
    rows = list(reader)
    if not rows:
        raise ValidationError("the CSV contains no rows")
    header = rows[0]
    lines = [" | ".join(header)]
    for row in rows[1:]:
        # Keep the header alongside each row so a chunk boundary does not
        # separate a value from the column it belongs to.
        lines.append(" | ".join(row))
    text = "\n".join(lines)
    return Extraction(
        text=text,
        meta={"rows": len(rows) - 1, "columns": len(header), "header": header[:50]},
    )


def _extract_json(data: bytes, ext: str) -> Extraction:
    raw = _decode(data)
    if ext == ".jsonl":
        records = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValidationError(f"invalid JSON on line {line_number}: {exc.msg}") from exc
        text = "\n\n".join(json.dumps(r, indent=2, ensure_ascii=False) for r in records)
        return Extraction(text=text, meta={"records": len(records)})

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc
    text = json.dumps(parsed, indent=2, ensure_ascii=False)
    return Extraction(
        text=text,
        meta={"top_level_type": type(parsed).__name__, "keys": sorted(parsed)[:50] if isinstance(parsed, dict) else None},
    )
