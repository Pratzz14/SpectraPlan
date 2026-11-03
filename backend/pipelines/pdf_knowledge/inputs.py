"""Local source inventory and reviewable PDF/Office extraction units."""
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import openpyxl
import pymupdf

from backend.knowledge_store import SOURCES, digest, file_hash, inside

SUPPORTED = {sid: spec for sid, spec in SOURCES.items() if Path(spec[0]).suffix in {".pdf", ".xlsx", ".docx"}}


def office_blocks(path):
    """Return source text and coordinates without changing original Office files."""
    blocks = []
    if path.suffix.lower() == ".xlsx":
        book = openpyxl.load_workbook(path, read_only=True, data_only=False)
        try:
            for sheet in book:
                rows = []
                for row in sheet:
                    cells = [{"cell": c.coordinate, "value": c.value.isoformat() if hasattr(c.value, "isoformat") else c.value} for c in row if c.value is not None]
                    if cells:
                        rows.append({"row": row[0].row, "cells": cells})
                blocks.append({"sheet": sheet.title, "rows": rows})
        finally:
            book.close()
        return blocks
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        body = ET.fromstring(archive.read("word/document.xml")).find("w:body", ns)
    def paragraph_text(node):
        pieces=[]
        for element in node.iter():
            name=element.tag.rsplit('}',1)[-1]
            if name=='t': pieces.append(element.text or '')
            elif name=='tab': pieces.append('\t')
            elif name in {'br','cr'}: pieces.append('\n')
        return ''.join(pieces)
    paragraph, table = 0, 0
    for node in body:
        if node.tag.endswith("}p"):
            paragraph += 1
            text = paragraph_text(node)
            if text.strip():
                blocks.append({"location": f"paragraph {paragraph}", "text": text})
        elif node.tag.endswith("}tbl"):
            table += 1
            for row_no, row in enumerate(node.findall("w:tr", ns), 1):
                values = ["\n".join(paragraph_text(p) for p in cell.findall(".//w:p", ns)) for cell in row.findall("w:tc", ns)]
                blocks.append({"location": f"table {table}, row {row_no}", "text": " | ".join(values)})
    return blocks


def prepare_inputs(settings, destination, *, source_ids=None, dpi=180):
    from backend.pipelines.pdf_knowledge.registry import registered_sources
    specs = {sid: {"source_id":sid,"file_name":name,"role":role} for sid,(name,role) in SUPPORTED.items()}
    specs.update({s["source_id"]:s for s in registered_sources(settings)})
    selected = list(source_ids) if source_ids else [sid for sid,s in specs.items() if inside(settings.source_dir,s.get("file_path",s["file_name"])).is_file()]
    if not selected or any(sid not in specs for sid in selected):
        raise ValueError("Select supported PDF, Excel, or Word sources")
    sources, units = [], []
    for sid in specs:
        if sid not in selected:
            continue
        spec = specs[sid]
        name, role = spec["file_name"], spec["role"]
        path = inside(settings.source_dir,spec.get("file_path",name))
        fingerprint = file_hash(path)
        kind = {".pdf": "pdf", ".xlsx": "workbook", ".docx": "document"}[path.suffix.lower()]
        source = {"source_id": sid, "file_name": name, "sha256": fingerprint, "role": role,
                  "technical_eligible": role in {"technical", "research", "method_table"}, "format": kind, "page_count": None}
        if "file_path" in spec: source["file_path"] = spec["file_path"]
        local = []
        source_dir = destination / "sources" / sid
        source_dir.mkdir(parents=True, exist_ok=True)
        if kind == "pdf":
            with pymupdf.open(path) as pdf:
                source["page_count"] = len(pdf)
                for number, page in enumerate(pdf, 1):
                    image = source_dir / f"page_{number:03}.png"
                    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
                    pixmap.save(image)
                    local.append({"unit_id": f"{sid}:p{number}", "page": number, "label": f"Page {number}",
                                  "image": image.relative_to(destination).as_posix(), "image_sha256": file_hash(image),
                                  "width": pixmap.width, "height": pixmap.height, "blocks": []})
        elif kind == "workbook":
            for sheet in office_blocks(path):
                groups,group,length=[],[],0
                for row in sheet["rows"]:
                    text=" | ".join(f"{c['cell']}: {c['value']}" for c in row["cells"])
                    if group and (len(group)>=40 or length+len(text)>12000):
                        groups.append(group);group,length=[],0
                    group.append(row);length+=len(text)
                if group: groups.append(group)
                for rows in groups:
                    number=len(local)+1
                    sectioned=len(groups)>1
                    context=[sheet["rows"][0]]+rows if sectioned and rows[0]!=sheet["rows"][0] else rows
                    text="\n".join(" | ".join(f"{c['cell']}: {c['value']}" for c in row["cells"]) for row in context)
                    label=f"{sheet['sheet']} rows {rows[0]['row']}–{rows[-1]['row']}" if sectioned else sheet['sheet']
                    identity=f"{sid}:sheet:{sheet['sheet']}"+(f":rows:{rows[0]['row']}-{rows[-1]['row']}" if sectioned else "")
                    local.append({"unit_id":identity,"page":number,"label":label,"sheet":sheet["sheet"],"rows":context,
                                  "blocks":[{"text":text,"location":label}],"input_text":text,"width":0,"height":0,"image":""})

        else:
            groups, group, length = [], [], 0
            for block in office_blocks(path):
                if group and length + len(block["text"]) > 3600:
                    groups.append(group); group, length = [], 0
                group.append(block); length += len(block["text"])
            if group:
                groups.append(group)
            for number, group in enumerate(groups, 1):
                local.append({"unit_id": f"{sid}:section:{number}", "page": number,
                              "label": f"{group[0]['location']} – {group[-1]['location']}", "blocks": group,
                              "input_text": "\n\n".join(f"[{b['location']}] {b['text']}" for b in group),
                              "width": 0, "height": 0, "image": ""})
        for unit in local:
            unit.update(source_id=sid, file_name=name, source_sha256=fingerprint, format=kind,
                        status="prepared", reference={"source_id": sid, "unit_id": unit["unit_id"], "location": unit["label"]})
            unit["input_sha256"] = digest(unit.get("image_sha256") or unit["input_text"])
        source["unit_count"] = len(local)
        sources.append(source); units.extend(local)
    return sources, units
