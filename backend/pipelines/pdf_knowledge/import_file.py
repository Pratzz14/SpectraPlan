"""The shared single-file pipeline used by CMD and the upload worker."""
import os
import subprocess
import shutil
import sys
import time
import threading
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from filelock import FileLock, Timeout

from backend.core.config import PROJECT_ROOT
from backend.services.knowledge.knowledge_store import read_json, write_json, inside
from backend.pipelines.pdf_knowledge.extract import extract_all
from backend.pipelines.pdf_knowledge.registry import register_file
from backend.pipelines.pdf_knowledge.store import publish_extraction

HEARTBEAT_SECONDS = 15


def progress(record):
    units = record.get("units", [])
    return {"completed": sum(u["status"] == "completed" for u in units), "total": len(units),
            "failed": sum(u["status"] == "failed" for u in units),
            "records": sum(u.get("knowledge_items", 0) for u in units),
            "fallback": sum(u.get("extraction_method") in {"pymupdf_embedded","pymupdf_ocr","office_text"} for u in units),
            "unreadable": sum(u.get("extraction_method")=="unreadable" for u in units)}


def ingestion_status(settings):
    root = settings.knowledge_work_dir
    job_file = root / "import" / "job.json"
    job = read_json(job_file) if job_file.is_file() else None
    if job and job["status"] in {"queued", "running"}:
        if time.time() - job.get("updated_at", 0) > 600:
            job = {**job, "status": "failed", "message": "The ingestion worker stopped reporting progress. Retry the file."}
        result = job
    else:
        manifest = read_json(root / "latest" / "manifest.json") if (root / "latest" / "manifest.json").is_file() else {}
        if manifest.get("status") in {"running", "completed_needs_visual_review"} and not manifest.get("production_corpus_modified"):
            result = {"job_id": "batch", "status": "running", "filename": "Source batch", "progress": progress(manifest),
                      "message": "Extracting sources" if manifest["status"] == "running" else "Building search indexes"}
        elif manifest.get('production_corpus_modified') and manifest.get('published_version') and not job:
            result = {'job_id':'batch', 'status':'succeeded', 'filename':'Source batch', 'progress':progress(manifest),
                      'corpus_version':manifest['published_version'], 'message':'Sources added to extracted knowledge'}
        elif manifest.get("status") == "failed" and not job:
            result = {"job_id": "batch", "status": "failed", "filename": "Source batch", "progress": progress(manifest),
                      "message": "The source batch did not finish. Existing knowledge is still available."}
        else:
            result = job or {"job_id": "", "status": "idle", "progress": {"completed": 0, "total": 0, "failed": 0, "records": 0}}
    return {**result, "endpoint_host": urlsplit(settings.dashscope_base_url).hostname,
            "max_bytes": settings.knowledge_upload_max_bytes, "qwen_configured": settings.usable_key(settings.dashscope_api_key)}


def ingest_file(settings, file: Path, *, role="technical", name=None, prepare_only=False,
                concurrency=2, job_file=None):
    root = settings.knowledge_work_dir
    root.mkdir(parents=True, exist_ok=True)
    state = {"job_id": uuid4().hex, "filename": name or file.name, "status": "running", "progress": {}, "message": "Preparing file"}
    if job_file and job_file.is_file():
        state.update(read_json(job_file))
        state["status"] = "running"

    state_lock = threading.Lock()
    stopped = threading.Event()

    def update(**values):
        with state_lock:
            state.update(values, updated_at=time.time())
            if job_file:
                write_json(job_file, state)

    def heartbeat():
        while not stopped.wait(HEARTBEAT_SECONDS):
            update()

    reporter = threading.Thread(target=heartbeat, daemon=True) if job_file else None
    if reporter:
        reporter.start()

    try:
        # The UI launcher holds the same lock briefly while starting this worker.
        with FileLock(str(root / "build.lock"), timeout=5 if job_file else 0):
            update(status="running")
            source = register_file(settings, file, role=role, name=name)
            update(source_id=source["source_id"], message="Extracting with Qwen3.7 Flash" if settings.usable_key(settings.dashscope_api_key) else "Extracting locally with text/OCR recovery")
            latest = root / "import" / "latest"
            if (latest / "manifest.json").is_file():
                prior = read_json(latest / "manifest.json")
                if {s["source_id"] for s in prior.get("sources", [])} != {source["source_id"]}:
                    shutil.rmtree(inside(root, "import/latest"))
            result = extract_all(settings, latest, source_ids=[source["source_id"]],
                                 concurrency=concurrency, prepare_only=prepare_only,
                                 on_progress=lambda record: update(progress=progress(record)))
            if result:
                raise ValueError("Extraction did not finish. Existing knowledge was preserved; retry the file.")
            if prepare_only:
                update(status="prepared", message="Prepared locally. No source content was uploaded.")
                return {"status": "prepared", "source_id": source["source_id"]}
            update(message="Updating knowledge and search indexes")
            report = publish_extraction(settings, root / "import" / "latest", merge=True)
            update(status="succeeded", message="File added to extracted knowledge", corpus_version=report["corpus_version"])
            return {**report, "source_id": source["source_id"]}
    except BaseException as error:
        message = "Another ingestion is running. Try again when it finishes." if isinstance(error, Timeout) else (
            str(error) if isinstance(error, ValueError) else f"Ingestion failed ({type(error).__name__}). Existing knowledge was preserved.")
        update(status="failed", message=message)
        raise ValueError(message) from None
    finally:
        stopped.set()
        if reporter:
            reporter.join()


def start_worker(settings, file, filename, role):
    """Called under build.lock after the upload has been saved locally."""
    root = settings.knowledge_work_dir / "import"
    root.mkdir(parents=True, exist_ok=True)
    job_file = root / "job.json"
    state = {"job_id": uuid4().hex, "filename": filename, "status": "queued", "progress": {},
             "message": "Starting extraction", "updated_at": time.time()}
    write_json(job_file, state)
    env = dict(os.environ)
    env.update(SOURCE_DIR=str(settings.source_dir), CORPUS_DIR=str(settings.corpus_dir),
               EMBEDDING_CACHE_DIR=str(settings.embedding_cache_dir), KNOWLEDGE_WORK_DIR=str(settings.knowledge_work_dir),
               DASHSCOPE_API_KEY=settings.dashscope_api_key.get_secret_value(), DASHSCOPE_BASE_URL=settings.dashscope_base_url,
               QWEN_EXTRACTION_MODEL=settings.qwen_extraction_model)
    env.update(KNOWLEDGE_EXTRACTION_ATTEMPTS=str(settings.knowledge_extraction_attempts),
               KNOWLEDGE_RETRY_DELAY_S=str(settings.knowledge_retry_delay_s),
               KNOWLEDGE_OCR_LANGUAGE=settings.knowledge_ocr_language,
               KNOWLEDGE_OCR_TIMEOUT_S=str(settings.knowledge_ocr_timeout_s),
               KNOWLEDGE_OCR_TESSDATA=settings.knowledge_ocr_tessdata or '')
    command = [sys.executable, "-X", "utf8", "-m", "backend.cli.ingest", "add", "--file", str(file), "--name", filename,
               "--role", role, "--job-file", str(job_file)]
    try:
        with (root / "worker.log").open("w", encoding="utf-8") as log:
            subprocess.Popen(command, cwd=PROJECT_ROOT, env=env, stdout=log, stderr=log,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except OSError:
        write_json(job_file, {**state, "status": "failed", "message": "The extraction worker could not start."})
        raise
    return state
