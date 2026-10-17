"""Static inspection report; source content is escaped and never executable HTML."""

import json
from pathlib import Path

from backend.knowledge_store import load_records, read_json


def render_report(directory: Path) -> Path:
    manifest, passages, methods = load_records(directory)
    data = {"manifest": manifest, "records": passages + methods,
            "notes": read_json(directory / "method_notes.json"), "pages": read_json(directory / "raw_pages.json")}
    payload = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = Path(__file__).with_name("report_template.html").read_text(encoding="utf-8")
    output = directory / "review.html"
    output.write_text(template.replace("__CORPUS_DATA__", payload), encoding="utf-8")
    return output
