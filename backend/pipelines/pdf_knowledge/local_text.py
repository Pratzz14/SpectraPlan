"""Final local fallback: embedded PDF text, Tesseract OCR, or Office text."""
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pymupdf

from backend.config import PROJECT_ROOT
from backend.knowledge_store import inside

PDF_LOCK = threading.RLock()
from backend.pipelines.pdf_knowledge.quality import readable


def tessdata_directory(settings):
    candidates = [settings.knowledge_ocr_tessdata, os.environ.get("TESSDATA_PREFIX")]
    executable = shutil.which("tesseract")
    if executable:
        candidates.append(str(Path(executable).parent / "tessdata"))
    candidates += ["C:/Program Files/Tesseract-OCR/tessdata", "/usr/share/tesseract-ocr/5/tessdata", "/usr/share/tesseract-ocr/4.00/tessdata"]
    for value in candidates:
        if not value: continue
        path=Path(value)
        if not path.is_absolute(): path=PROJECT_ROOT/path
        if all((path/f"{language}.traineddata").is_file() for language in settings.knowledge_ocr_language.split('+')):
            return str(path)
    return None


def embedded_text(settings, unit, sources):
    if unit["format"] != "pdf":
        return unit.get("input_text", "")
    source = next(s for s in sources if s["source_id"] == unit["source_id"])
    path = inside(settings.source_dir, source.get("file_path", source["file_name"]))
    with PDF_LOCK, pymupdf.open(path) as pdf:
        text = pdf[unit["page"] - 1].get_text("text", sort=True)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def recover_text(settings, unit, sources, text=None):
    text = embedded_text(settings, unit, sources) if text is None else text
    if readable(text):
        return text, "pymupdf_embedded" if unit["format"] == "pdf" else "office_text", []
    if unit["format"] != "pdf":
        return "", "unreadable", ["The Office section contains no usable source text"]
    tessdata = tessdata_directory(settings)
    if not tessdata:
        return "", "unreadable", ["Embedded text is unavailable and Tesseract language data is not installed or configured"]
    source = next(s for s in sources if s["source_id"] == unit["source_id"])
    path = inside(settings.source_dir, source.get("file_path", source["file_name"]))
    try:
        result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'backend.pipelines.pdf_knowledge.local_text',
                                 '--ocr', str(path), '--page', str(unit['page']), '--tessdata', tessdata,
                                 '--language', settings.knowledge_ocr_language],
                                cwd=PROJECT_ROOT, capture_output=True, text=True, encoding='utf-8',
                                timeout=settings.knowledge_ocr_timeout_s,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if result.returncode:
            return "", "unreadable", ["Local OCR could not read the page; source preview remains available"]
        text = result.stdout
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if readable(text):
            return text, "pymupdf_ocr", []
        return "", "unreadable", ["Neither embedded text nor local OCR recovered readable source text"]
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        return "", "unreadable", [f"Local OCR failed ({type(error).__name__}); the source page remains available for inspection"]


def text_passages(text, size=1600):
    """Keep every source character, splitting long text on whitespace for indexing."""
    passages = []
    rest = text.strip()
    while rest:
        end = len(rest) if len(rest) <= size else rest.rfind(" ", 0, size)
        if end <= 0:
            end = min(size, len(rest))
        passages.append(rest[:end].strip())
        rest = rest[end:].strip()
    if len(passages)>1 and not readable(passages[-1]):
        tail=passages.pop()
        passages[-1] += "\n"+tail
    return [p for p in passages if p]


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Bounded local OCR worker')
    parser.add_argument('--ocr',type=Path,required=True)
    parser.add_argument('--page',type=int,required=True)
    parser.add_argument('--tessdata',required=True)
    parser.add_argument('--language',default='eng')
    args=parser.parse_args()
    try:
        with pymupdf.open(args.ocr) as pdf:
            page=pdf[args.page-1]
            textpage=page.get_textpage_ocr(language=args.language,dpi=200,full=True,tessdata=args.tessdata)
            print(page.get_text('text',textpage=textpage,sort=True))
    except Exception as error:
        print(type(error).__name__,file=sys.stderr)
        raise SystemExit(1)
