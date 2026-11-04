"""Linux peak RSS gate, runnable in a one-off dyno without model API calls."""
import json
import resource
from backend.core.config import Settings
from backend.services.search.retrieval import Embedder

s=Settings()
model=Embedder(s.embedding_cache_dir,local_only=True)
model.vectors(['powder moisture'],query=True)
import pymupdf
from tempfile import TemporaryDirectory
from pathlib import Path
from openpyxl import Workbook
from backend.pipelines.pdf_knowledge.inputs import office_blocks
with TemporaryDirectory() as temporary:
    root=Path(temporary)
    with pymupdf.open() as document:
        page=document.new_page()
        page.insert_text((40,60),'Spectroscopy measures fluorescence and infrared absorption for a feasibility study.')
        image=page.get_pixmap(dpi=180).tobytes('png')
    with pymupdf.open() as scanned:
        page=scanned.new_page();page.insert_image(page.rect,stream=image)
        text=page.get_textpage_ocr(language='eng',dpi=180,full=True,tessdata='/usr/share/tesseract-ocr/5/tessdata')
        if not page.get_text(textpage=text).strip():raise RuntimeError('Packaged OCR produced no text')
    workbook=Workbook();sheet=workbook.active
    for i in range(1000):sheet.append([i,'Synthetic spectroscopy feasibility reference','Raman','powder'])
    workbook.save(root/'probe.xlsx');workbook.close()
    if not office_blocks(root/'probe.xlsx'):raise RuntimeError('Packaged workbook reader failed')
peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
print(json.dumps({'embedding_fingerprint':model.fingerprint,'peak_mib':round(peak,2),'limit_mib':450,'passed':peak<450}),flush=True)
raise SystemExit(0 if peak<450 else 1)
