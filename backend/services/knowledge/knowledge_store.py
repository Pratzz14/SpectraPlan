"""Source inventory, deterministic provenance and atomic corpus publication."""

import hashlib
import json
import os
import re
import zipfile
from xml.etree import ElementTree
from pathlib import Path
from uuid import uuid4

import openpyxl
import pymupdf

from backend.schemas.knowledge_models import EXTRACTOR_VERSION, SCHEMA_VERSION, Candidate, Evidence, Fact, Region

SOURCES = {
    "S01": ("S01_Multispectral_Laboratory.pdf", "technical"),
    "S02": ("S02_AFS_Process_Control_Slides.pdf", "technical"),
    "S03": ("S03_LED_Kidney_Study_2017.pdf", "research"),
    "S04": ("S04_Combi_MIR_Fluorescence_2021.pdf", "research"),
    "S05": ("S05_AFS_Flyer.pdf", "business"),
    "S06": ("S06_Laboratory_Link.txt", "business_link"),
    "T01": ("AFS_method_comparison_table.xlsx", "method_table"),
    "D01_DOC": ("AFS_Examples_and_Reference.docx", "development"),
}
MISSING_OPTIONAL = ["AI-based molecular media analysis by process-spectroscopy in-line.pdf",
                    "customer_scenarios_for_final_evaluation.txt"]
METHOD_COLUMNS = ["method_no", "method", "measurement_technique", "physical_phenomenon", "sample_type",
                  "optical_path_or_depth", "sensitivity", "selectivity", "cost"]


def digest(value) -> str:
    data = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Windows readers and sync clients can briefly hold a sharing lock on JSON.
    import time
    try:
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as error:
                if os.name != "nt" or getattr(error, "winerror", None) not in {5, 32, 33} or attempt == 4:
                    raise
                time.sleep(.025 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes corpus")
    return path


def active_directory(root: Path) -> Path:
    pointer = root / "current.json"
    if not pointer.exists():
        return root
    data = read_json(pointer)
    path = inside(root, data["directory"])
    if read_json(path / "source_manifest.json")["corpus_version"] != data["corpus_version"]:
        raise ValueError("Corpus pointer/version mismatch")
    return path


def inventory(source_dir: Path) -> list[dict]:
    if not source_dir.is_dir():
        raise ValueError("SOURCE_DIR does not exist")
    known = {name: (sid, role) for sid, (name, role) in SOURCES.items()}
    result = []
    for path in sorted(source_dir.iterdir()):
        if not path.is_file():
            continue
        sid, role = known.get(path.name, ("X-" + digest(path.name)[:12], "excluded_unknown"))
        entry = {"source_id": sid, "file_name": path.name, "role": role,
                 "sha256": file_hash(path), "size_bytes": path.stat().st_size,
                 "technical_eligible": role in {"technical", "research", "method_table"}, "page_count": None}
        if path.suffix.lower() == ".pdf":
            with pymupdf.open(path) as doc:
                entry["page_count"] = len(doc)
        if sid == "S06":
            entry["supplied_url"] = path.read_text(encoding="utf-8").strip()
            entry["url_fetched"] = False
        if sid == "T01":
            with_workbook = openpyxl.load_workbook(path, read_only=True, data_only=False)
            try:
                entry["sheets"] = [{"name": s.title, "rows": s.max_row, "columns": s.max_column} for s in with_workbook]
            finally:
                with_workbook.close()
        result.append(entry)
    required = {"S01", "S02", "S03", "S04", "S05", "T01"}
    if missing := required - {s["source_id"] for s in result}:
        raise ValueError(f"Missing required supplied sources: {sorted(missing)}")
    return result


def extract_pages(source_dir: Path, sources: list[dict], destination: Path) -> list[dict]:
    pages = []
    for source in sources:
        if source["source_id"] not in {"S01", "S02", "S03", "S04", "S05"}:
            continue
        with pymupdf.open(source_dir / source["file_name"]) as doc:
            for index, page in enumerate(doc):
                blocks = []
                for block in page.get_text("blocks", sort=True):
                    if block[6] != 0 or not block[4].strip():
                        continue
                    raw = block[4]
                    # No unit/symbol or hyphen rewriting. Quotes refer to this exact text.
                    text = raw.replace("\r\n", "\n").replace("\r", "\n")
                    blocks.append({"block_id": f"b{len(blocks) + 1:03}", "text": text, "raw_text": raw,
                                   "bbox": list(block[:4])})
                image = f"assets/{source['sha256'][:16]}/{source['source_id']}-p{index + 1:03}.jpg"
                image_path = destination / image
                image_path.parent.mkdir(parents=True, exist_ok=True)
                page.get_pixmap(matrix=pymupdf.Matrix(1.8, 1.8), alpha=False).save(image_path, jpg_quality=90)
                significant_image = any(pymupdf.Rect(info["bbox"]).get_area() > page.rect.get_area() * .12
                                        for info in page.get_image_info())
                needs_vision = source["source_id"] in {"S02", "S05"} or significant_image or len(page.get_drawings()) > 40
                pages.append({"source_id": source["source_id"], "file_name": source["file_name"],
                              "source_sha256": source["sha256"], "role": source["role"], "page": index + 1,
                              "width": page.rect.width, "height": page.rect.height, "blocks": blocks,
                              "image": image, "image_sha256": file_hash(image_path), "needs_vision": needs_vision})
    return pages


def _docx_blocks(path: Path) -> list[dict]:
    """Extract paragraphs and table cells without rewriting source text."""
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    blocks = []
    for node_index, node in enumerate(root.findall(".//w:body/*", namespace), 1):
        if node.tag.endswith("}p"):
            text = "".join(t.text or "" for t in node.findall(".//w:t", namespace))
            if text.strip():
                blocks.append({"block_id": f"b{len(blocks) + 1:03}", "text": text, "raw_text": text,
                               "location": f"paragraph:{len(blocks) + 1}"})
        elif node.tag.endswith("}tbl"):
            for row_no, row in enumerate(node.findall("./w:tr", namespace), 1):
                cells = ["".join(t.text or "" for t in cell.findall(".//w:t", namespace)).strip()
                         for cell in row.findall("./w:tc", namespace)]
                text = "\t".join(cells).strip()
                if text:
                    blocks.append({"block_id": f"b{len(blocks) + 1:03}", "text": text, "raw_text": text,
                                   "location": f"table:{node_index}/row:{row_no}"})
    return blocks


def _xlsx_blocks(path: Path) -> list[dict]:
    blocks = []
    book = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        for sheet in book.worksheets:
            for row in sheet.iter_rows():
                values = ["" if cell.value is None else str(cell.value) for cell in row]
                if not any(value.strip() for value in values):
                    continue
                text = "\t".join(values)
                blocks.append({"block_id": f"b{len(blocks) + 1:03}", "text": text, "raw_text": text,
                               "location": f"sheet:{sheet.title}!{row[0].row}"})
    finally:
        book.close()
    return blocks


def extract_original_documents(source_dir: Path, sources: list[dict]) -> list[dict]:
    """Return deterministic, reviewable text payloads for original files.

    The existing page/image extraction remains available for the ingestion model.
    This text-oriented view lets comparison tools use the same original PDF,
    DOCX, and XLSX inputs while retaining exact source locations.
    """
    documents = []
    for source in sources:
        path = source_dir / source["file_name"]
        suffix = path.suffix.casefold()
        if suffix == ".pdf":
            blocks = []
            with pymupdf.open(path) as pdf:
                for page_no, page in enumerate(pdf, 1):
                    for block in page.get_text("blocks", sort=True):
                        if block[6] == 0 and block[4].strip():
                            text = block[4].replace("\r\n", "\n").replace("\r", "\n")
                            blocks.append({"block_id": f"b{len(blocks) + 1:03}", "text": text,
                                           "raw_text": block[4], "location": f"page:{page_no}"})
        elif suffix == ".docx":
            blocks = _docx_blocks(path)
        elif suffix == ".xlsx":
            blocks = _xlsx_blocks(path)
        else:
            continue
        documents.append({"source_id": source["source_id"], "file_name": source["file_name"],
                          "source_sha256": source["sha256"], "role": source["role"],
                          "format": suffix[1:], "blocks": blocks,
                          "block_count": len(blocks)})
    return documents


def anchored_quote(text: str, quote: str) -> str | None:
    """Permit only PDF whitespace differences; retain the actual source spelling/units."""
    if quote and quote in text:
        return quote
    characters, offsets = [], []
    for match in re.finditer(r"\S+|\s+", text):
        token = match.group()
        normalized = " " if token.isspace() else token
        characters.extend(normalized)
        offsets.extend([match.start()] if token.isspace() else range(match.start(), match.end()))
    normalized_quote = " ".join(quote.split())
    start = "".join(characters).find(normalized_quote) if normalized_quote else -1
    if start < 0:
        return None
    return text[offsets[start]:offsets[start + len(normalized_quote) - 1] + 1]


def canonical_candidate(candidate: Candidate, page: dict, verification: dict, extraction_revision: str) -> dict:
    item = candidate.model_dump()
    blocks = {b["block_id"]: b for b in page["blocks"]}
    issues = list(candidate.issues)
    anchors = []
    for span in candidate.spans:
        block = blocks.get(span.block_id)
        quote = span.quote if span.quote is not None else (block["text"] if block else "")
        start = block["text"].find(quote) if block and quote else -1
        if start < 0:
            issues.append(f"Unmatched source quote in {span.block_id}")
        else:
            anchors.append({"block_id": span.block_id, "quote": quote, "start": start, "end": start + len(quote), "bbox": block["bbox"]})
    if candidate.content_kind == "verbatim_text":
        text = "\n\n".join(span["quote"] for span in anchors)
        if not anchors or candidate.region or candidate.transcription or candidate.interpretation:
            issues.append("Invalid verbatim-text shape")
    else:
        text = candidate.transcription or ""
        r = candidate.region
        if not r or r.x0 >= r.x1 or r.y0 >= r.y1 or not text.strip():
            issues.append("Missing or invalid figure region/transcription")
    if not text.strip():
        # Keep rejected candidates inspectable, never make this placeholder searchable.
        text = "\n".join(b["text"] for b in page["blocks"]).strip() or candidate.section
        issues.append("No supported passage content")
    for fact in item["facts"]:
        matched_quotes = [anchored_quote(text, q) for q in fact["support_quotes"]]
        if not matched_quotes or any(q is None for q in matched_quotes):
            issues.append("Fact has missing or unmatched supporting quotes")
        else:
            fact["support_quotes"] = matched_quotes
        for quantity in fact["quantities"]:
            if not re.search(r"\d", quantity["value"]):
                issues.append("Quantity value is not numerical")
            matched = anchored_quote(text, quantity["source_quote"])
            if matched is None:
                issues.append("Quantity has no exact supporting source quote")
            else:
                quantity["source_quote"] = matched
            normalized = " ".join(quantity["source_quote"].split())
            if quantity["value"] not in normalized or (quantity["unit"] and quantity["unit"] not in normalized):
                issues.append("Quantity value/unit does not match its source quote")
    if verification.get("status") != "supported":
        issues.append("Model verification: " + verification.get("status", "missing"))
    scope = candidate.evidence_scope
    if page["role"] == "business" and scope != "business_context":
        issues.append("Business source cannot provide technical evidence")
    if page["role"] == "research" and scope not in {"research_demonstration", "general_method", "business_context"}:
        issues.append("Research evidence scope is overstated")
    identity = {"source": page["source_id"], "page": page["page"], "kind": candidate.content_kind,
                "text": text, "spans": [(s["block_id"], s["start"], s["end"]) for s in anchors],
                "region": item["region"]}
    evidence_id = f"{page['source_id']}:p{page['page']:03}:{'fig' if candidate.region else 'txt'}:{digest(identity)[:16]}"
    issues = sorted(set(issues))
    return {**item, "evidence_id": evidence_id, "source_id": page["source_id"], "file_name": page["file_name"],
            "source_sha256": page["source_sha256"], "page": page["page"], "text": text,
            "source_spans": anchors, "image": page["image"], "verification": verification,
            "revision": digest({"candidate": item, "extraction": extraction_revision})[:24],
            "validation_status": "flagged" if issues else "passed", "human_review_status": "not_reviewed",
            "retrieval_eligible": not issues and page["role"] in {"technical", "research"} and scope != "business_context",
            "issues": issues}


def import_methods(source_dir: Path, sources: list[dict]) -> tuple[list[dict], list[dict]]:
    table = next(s for s in sources if s["source_id"] == "T01")
    primary = next(s for s in sources if s["source_id"] == "S01")
    book = openpyxl.load_workbook(source_dir / table["file_name"], read_only=True, data_only=False)
    try:
        sheet = book["method_comparison"]
        if list(next(sheet.iter_rows(values_only=True))) != METHOD_COLUMNS or sheet.max_row != 20:
            raise ValueError("Workbook must contain the nine expected columns and 19 method rows")
        notes = [{"source_id": "T01", "sheet": "notes", "row": i, "text": row[0]}
                 for i, row in enumerate(book["notes"].iter_rows(values_only=True), 1)]
        methods = []
        for row_no, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
            if any(value is None or (isinstance(value, str) and value.startswith("=")) for value in values):
                raise ValueError("Missing values or formulas in supplied method table")
            raw = dict(zip(METHOD_COLUMNS, values, strict=True))
            methods.append({"evidence_id": f"T01:method_comparison:r{row_no:03}", "source_id": "T01",
                            "file_name": table["file_name"], "source_sha256": table["sha256"], "page": 6,
                            "section": "Table 1", "sheet": "method_comparison", "row": row_no,
                            "method": raw["method"], "geometry": raw["measurement_technique"],
                            "raw_values": raw, "text": "; ".join(f"{k}: {v}" for k, v in raw.items()),
                            "content_kind": "method_row", "evidence_scope": "general_method",
                            "revision": digest({"row": raw, "schema": SCHEMA_VERSION})[:24],
                            "validation_status": "passed", "human_review_status": "not_reviewed",
                            "retrieval_eligible": True, "issues": [], "ratings_are_qualitative": True,
                            "underlying_citation": {"source_id": "S01", "page": 6, "table": "Table 1", "sha256": primary["sha256"]},
                            "validation_basis": "Exact workbook cell import; underlying PDF transcription not human-reviewed"})
        return methods, notes
    finally:
        book.close()


def load_records(directory: Path) -> tuple[dict, list[dict], list[dict]]:
    manifest = read_json(directory / "source_manifest.json")
    passages = [json.loads(line) for line in (directory / "passages.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return manifest, passages, read_json(directory / "methods.json")


def validate_corpus(directory: Path, *, source_dir: Path | None = None, deep: bool = False) -> dict:
    manifest, passages, methods = load_records(directory)
    if manifest.get("schema_version") in {"qwen-image-v1", "qwen-sources-v2"}:
        from backend.pipelines.pdf_knowledge.store import validate
        return validate(directory, source_dir=source_dir, deep=deep)
    sources = {s["source_id"]: s for s in manifest["sources"]}
    if len(sources) != len(manifest["sources"]):
        raise ValueError("Duplicate source IDs")
    for name, expected in manifest["artifacts"].items():
        if file_hash(inside(directory, name)) != expected:
            raise ValueError(f"Artifact checksum mismatch: {name}")
    index = read_json(directory / "index_manifest.json")
    if index["corpus_version"] != manifest["corpus_version"] or index["embedding_model"] != "BAAI/bge-small-en-v1.5":
        raise ValueError("Index/corpus revision mismatch")
    records = [*passages, *methods]
    if len({r["evidence_id"] for r in records}) != len(records):
        raise ValueError("Duplicate evidence IDs")
    raw_pages = read_json(directory / "raw_pages.json")
    pages = {(p["source_id"], p["page"]): p for p in raw_pages}
    coverage = manifest["coverage"]
    expected_pages = {(s["source_id"], p) for s in sources.values() if s["source_id"] in {"S01", "S02", "S03", "S04", "S05"}
                      for p in range(1, s["page_count"] + 1)}
    if len(pages) != len(raw_pages) or len(coverage) != len(expected_pages) or set(pages) != expected_pages or {(p["source_id"], p["page"]) for p in coverage} != expected_pages:
        raise ValueError("Incomplete page coverage")
    for record in records:
        Evidence.model_validate(record)
        source = sources[record["source_id"]]
        if record["source_sha256"] != source["sha256"] or record["file_name"] != source["file_name"]:
            raise ValueError("Record/source fingerprint mismatch")
        if record["content_kind"] == "method_row":
            if record["source_id"] != "T01" or record["page"] != 6 or record["sheet"] != "method_comparison" or not 2 <= record["row"] <= 20:
                raise ValueError("Invalid workbook provenance")
            if record["underlying_citation"] != {"source_id": "S01", "page": 6, "table": "Table 1", "sha256": sources["S01"]["sha256"]}:
                raise ValueError("Invalid underlying table citation")
            raw = record["raw_values"]
            if set(raw) != set(METHOD_COLUMNS) or record["method"] != raw["method"] or record["geometry"] != raw["measurement_technique"]:
                raise ValueError("Method fields differ from workbook values")
            if any(raw[column] not in {"low", "average", "high"} for column in ["sensitivity", "selectivity", "cost"]):
                raise ValueError("Qualitative method ratings changed")
        else:
            page = pages[(record["source_id"], record["page"])]
            check = record.get("project_source_check")
            if check and (check not in manifest.get("project_source_checks", []) or record["retrieval_eligible"]
                          or check["source_sha256"] != record["source_sha256"] or check["image_sha256"] != page["image_sha256"]):
                raise ValueError("Project source inspection exclusion is missing or inconsistent")
            for span in record["source_spans"]:
                block = next(b for b in page["blocks"] if b["block_id"] == span["block_id"])
                if block["text"][span["start"]:span["end"]] != span["quote"] or span["bbox"] != block["bbox"]:
                    raise ValueError("Broken quotation anchor")
            if record["content_kind"] == "verbatim_text" and record["validation_status"] == "passed":
                if record["text"] != "\n\n".join(s["quote"] for s in record["source_spans"]) or not record["source_spans"]:
                    raise ValueError("Verbatim passage does not match source spans")
            if record["content_kind"] == "figure_transcription" and record["validation_status"] == "passed":
                region = Region.model_validate(record["region"])
                if region.x0 >= region.x1 or region.y0 >= region.y1 or record["text"] != record["transcription"]:
                    raise ValueError("Invalid figure transcription/region")
            if record["retrieval_eligible"]:
                if record.get("verification", {}).get("status") != "supported":
                    raise ValueError("Active passage lacks automated source verification")
                for raw_fact in record.get("facts", []):
                    fact = Fact.model_validate(raw_fact)
                    if not fact.support_quotes or any(q not in record["text"] for q in fact.support_quotes):
                        raise ValueError("Active fact has an unanchored quote")
                    for quantity in fact.quantities:
                        if not re.search(r"\d", quantity.value):
                            raise ValueError("Active quantity is not numerical")
                        if quantity.source_quote not in record["text"] or quantity.value not in " ".join(quantity.source_quote.split()) or (quantity.unit and quantity.unit not in quantity.source_quote):
                            raise ValueError("Active quantity has an unanchored value/unit")
        if record["retrieval_eligible"] and (record["validation_status"] != "passed" or record["human_review_status"] == "rejected"
                                              or not source["technical_eligible"] or record["evidence_scope"] == "business_context"
                                              or record["issues"]):
            raise ValueError("Ineligible evidence entered the active corpus")
    if len(methods) != 19 or {r["row"] for r in methods} != set(range(2, 21)):
        raise ValueError("Method rows lost or duplicated")
    notes = read_json(directory / "method_notes.json")
    if len(notes) != 7 or any(not n["text"] for n in notes):
        raise ValueError("Workbook notes lost")
    eligible = {r["evidence_id"] for r in records if r["retrieval_eligible"]}
    indexed = {s["evidence_id"] for s in read_json(directory / "segments.json")}
    if eligible != indexed or index["segment_count"] != len(read_json(directory / "segments.json")):
        raise ValueError("Index membership mismatch")
    lexical = read_json(directory / "bm25.json")
    if lexical["corpus_version"] != manifest["corpus_version"] or {r["evidence_id"] for r in lexical["documents"]} != eligible:
        raise ValueError("Lexical index membership/version mismatch")
    if any(s["token_count"] > 512 or s["token_count"] < 1 for s in read_json(directory / "segments.json")):
        raise ValueError("Invalid embedding segment length")
    if not any(r["retrieval_eligible"] for r in passages) or not eligible:
        raise ValueError("No eligible technical passages")
    if deep:
        for page in raw_pages:
            if file_hash(inside(directory, page["image"])) != page["image_sha256"]:
                raise ValueError("Source page image checksum mismatch")
    for name, expected in index["qdrant_files"].items():
        if file_hash(inside(directory, name)) != expected:
            raise ValueError("Qdrant index checksum mismatch")
    if source_dir:
        for source in sources.values():
            if file_hash(source_dir / source["file_name"]) != source["sha256"]:
                raise ValueError(f"Source changed: {source['source_id']}; rebuild required")
        actual_methods, actual_notes = import_methods(source_dir, list(sources.values()))
        if [r["raw_values"] for r in actual_methods] != [r["raw_values"] for r in methods] or actual_notes != notes:
            raise ValueError("Workbook values differ from supplied cells")
    return {"status": "passed", "corpus_version": manifest["corpus_version"], "pages": len(pages),
            "passages": len(passages), "eligible_passages": sum(r["retrieval_eligible"] for r in passages),
            "eligible_methods": sum(r["retrieval_eligible"] for r in methods),
            "flagged": sum(r["validation_status"] == "flagged" for r in records),
            "human_verified": sum(r["human_review_status"] == "verified" for r in records)}


def publish(root: Path, staged: Path, manifest: dict) -> Path:
    """The pointer is the publication boundary. Root files are convenience exports."""
    import shutil

    final = root / "versions" / manifest["corpus_version"]
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        validate_corpus(final, deep=True)
        shutil.rmtree(staged)
    else:
        os.replace(staged, final)
    write_json(root / "current.json", {"corpus_version": manifest["corpus_version"], "directory": final.relative_to(root).as_posix()})
    # Readers always resolve current.json; a failed convenience copy cannot mix active generations.
    for name in ["source_manifest.json", "passages.jsonl", "methods.json", "method_notes.json", "validation_report.json"]:
        temporary = root / (name + ".tmp")
        shutil.copyfile(final / name, temporary)
        os.replace(temporary, root / name)
    return final
