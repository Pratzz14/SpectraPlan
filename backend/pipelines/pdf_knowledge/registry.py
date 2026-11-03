"""Register user-selected originals without overwriting published source bytes."""
import re
import shutil
from pathlib import Path

import pymupdf

from backend.services.knowledge.knowledge_store import SOURCES, digest, file_hash, inside, read_json, write_json

ROLES = {"technical", "research", "business", "development"}
EXTENSIONS = {".pdf", ".xlsx", ".docx"}


def registered_sources(settings):
    path = settings.corpus_dir / "added_sources.json"
    return read_json(path) if path.is_file() else []


def register_file(settings, path: Path, *, role="technical", name=None):
    from backend.pipelines.pdf_knowledge.inputs import office_blocks

    if role not in ROLES:
        raise ValueError("Choose technical, research, business, or development")
    if not path.is_file():
        raise ValueError("The selected file does not exist")
    filename = name or path.name
    if (Path(filename).name != filename or re.search(r'[<>:"/\\|?*\x00-\x1f]', filename)
            or filename.endswith((".", " "))):
        raise ValueError("Use a filename without directory separators or reserved characters")
    suffix = Path(filename).suffix.lower()
    if path.suffix.lower() != suffix:
        raise ValueError("The display filename must retain the original file extension")
    if suffix not in EXTENSIONS:
        raise ValueError("Supported formats are PDF, XLSX, and DOCX")
    if not 0 < path.stat().st_size <= settings.knowledge_upload_max_bytes:
        raise ValueError("File is empty or exceeds the configured upload limit")
    known = next((sid for sid, spec in SOURCES.items() if spec[0].casefold() == filename.casefold()), None)
    # Open the actual format before registering; extensions alone are insufficient.
    if suffix == ".pdf":
        with pymupdf.open(path) as pdf:
            if not pdf.is_pdf or not len(pdf) or pdf.needs_pass:
                raise ValueError("Use an unencrypted PDF with at least one page")
    else:
        # Uploaded staging paths retain the extension for the Office readers.
        blocks = office_blocks(path)
        if not blocks or (suffix == ".xlsx" and not any(s["rows"] for s in blocks)):
            raise ValueError("The Office file contains no readable source content")
    checksum = file_hash(path)
    sid = known or "U" + digest(filename.casefold())[:12]
    if known:
        role = SOURCES[known][1]
    relative = f"imported/{sid}/{checksum[:20]}/{filename}"
    target = inside(settings.source_dir, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copyfile(path, target)
    if file_hash(target) != checksum:
        raise ValueError("Stored source bytes do not match the selected file")
    entry = {"source_id": sid, "file_name": filename, "file_path": relative, "role": role}
    entries = [s for s in registered_sources(settings) if s["source_id"] != sid]
    entries.append(entry)
    write_json(settings.corpus_dir / "added_sources.json", entries)
    return entry
