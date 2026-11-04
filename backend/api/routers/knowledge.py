"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

from backend.api.auth import require_admin

from backend.api.dependencies import get_settings, get_knowledge

import json
import re
from typing import Literal

from fastapi import Depends, APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse

from backend.core.config import Settings
from backend.services.knowledge.knowledge_store import active_directory, inside, read_json, inventory
from backend.services.knowledge.knowledge_report import inspection_data
from backend.services.search.evidence import EvidenceNotFound, CorpusUnavailable
from backend.services.cloud.database import StorageUnavailable


def create_router():
    router = APIRouter(tags=["Knowledge"], dependencies=[Depends(require_admin)])
    @router.get("/api/knowledge/ingest/status")
    def knowledge_ingestion_status(config: Settings = Depends(get_settings)):
        from backend.pipelines.pdf_knowledge.import_file import ingestion_status
        try:
            if config.storage_backend == 'supabase':
                from backend.services.cloud.jobs import job_services
                jobs = job_services(config)
                try:
                    return jobs.status()
                finally:
                    jobs.database.close()
            return ingestion_status(config)
        except (OSError, ValueError, KeyError):
            raise HTTPException(503, "Ingestion status is unavailable") from None


    @router.post("/api/knowledge/ingest", status_code=202)
    async def knowledge_ingest(request: Request, filename: str = Query(min_length=1, max_length=180),
                               role: Literal['technical','research','business','development'] = 'technical', config: Settings = Depends(get_settings)):
        from pathlib import Path
        from uuid import uuid4
        from filelock import FileLock, Timeout
        from backend.pipelines.pdf_knowledge.import_file import ingestion_status, start_worker
        from backend.pipelines.pdf_knowledge.registry import EXTENSIONS
        if request.headers.get('content-type', '').split(';')[0] != 'application/octet-stream':
            raise HTTPException(415, "Upload the file as application/octet-stream")
        if (Path(filename).name != filename or re.search(r'[<>:"/\\|?*\x00-\x1f]', filename)
                or filename.endswith(('.', ' ')) or Path(filename).suffix.lower() not in EXTENSIONS):
            raise HTTPException(422, "Choose a PDF, XLSX or DOCX filename without directory separators")
        if config.storage_backend == 'supabase':
            import asyncio
            from tempfile import TemporaryDirectory
            from backend.services.cloud.jobs import enqueue_file
            from backend.services.history.explainability import HistoryConflict
            with TemporaryDirectory(prefix='spectraplan-upload-') as temporary:
                path = Path(temporary)/filename
                size = 0
                with path.open('wb') as output:
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > config.knowledge_upload_max_bytes:
                            raise HTTPException(413, 'File exceeds the configured upload limit')
                        output.write(chunk)
                if not size:
                    raise HTTPException(422, 'The selected file is empty')
                try:
                    return await asyncio.to_thread(enqueue_file, config, path, filename, role)
                except HistoryConflict as error:
                    raise HTTPException(409, str(error)) from None
                except ValueError as error:
                    raise HTTPException(422, str(error)) from None
        root = config.knowledge_work_dir
        root.mkdir(parents=True, exist_ok=True)
        upload = None
        started = False
        try:
            with FileLock(str(root/'build.lock'), timeout=0):
                if ingestion_status(config)['status'] in {'queued','running'}:
                    raise HTTPException(409, "Another ingestion is running. Try again when it finishes.")
                incoming = root/'import'/'incoming'; incoming.mkdir(parents=True, exist_ok=True)
                upload = incoming/(uuid4().hex+Path(filename).suffix.lower())
                size = 0
                with upload.open('wb') as output:
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > config.knowledge_upload_max_bytes:
                            raise HTTPException(413, "File exceeds the configured upload limit")
                        output.write(chunk)
                if size == 0:
                    raise HTTPException(422, "The selected file is empty")
                state = start_worker(config,upload,filename,role)
                started = True
                return state
        except Timeout:
            raise HTTPException(409, "Another ingestion is running. Try again when it finishes.") from None
        except OSError:
            raise HTTPException(503, "The uploaded file could not be stored or its worker could not start") from None
        finally:
            if upload and not started:
                upload.unlink(missing_ok=True)


    @router.get("/api/knowledge/inspection")
    def knowledge_inspection(config: Settings = Depends(get_settings), knowledge=Depends(get_knowledge)):
        try:
            directory = knowledge.directory() if knowledge else active_directory(config.corpus_dir)
            data = inspection_data(directory)
            version = data["manifest"]["corpus_version"]
            if not re.fullmatch(r"corpus-[a-f0-9]{20}", version) or directory.name != version:
                raise ValueError("No published corpus")
            return {**data, "artifact_base": f"/api/knowledge/versions/{version}/"}
        except StorageUnavailable:
            raise
        except (OSError, ValueError, KeyError, TypeError, EvidenceNotFound, CorpusUnavailable):
            raise HTTPException(503, "Published extracted knowledge is unavailable. Check workspace status.") from None


    @router.get("/api/knowledge/report", include_in_schema=False)
    def knowledge_report(config: Settings = Depends(get_settings), knowledge=Depends(get_knowledge)):
        try:
            directory = knowledge.directory() if knowledge else active_directory(config.corpus_dir)
            version = read_json(directory / "source_manifest.json")["corpus_version"]
            if not re.fullmatch(r"corpus-[a-f0-9]{20}", version):
                raise ValueError("Invalid corpus version")
            return RedirectResponse(f"/api/knowledge/versions/{version}/review.html", status_code=307)
        except StorageUnavailable:
            raise
        except (OSError, ValueError, KeyError, EvidenceNotFound, CorpusUnavailable):
            raise HTTPException(404, "No published knowledge report. Build the corpus first.") from None


    @router.get("/api/knowledge/versions/{version}/source/{source_id}/original", include_in_schema=False)
    def knowledge_original(version: str, source_id: str, config: Settings = Depends(get_settings), knowledge=Depends(get_knowledge)):
        if not re.fullmatch(r"corpus-[a-f0-9]{20}", version):
            raise HTTPException(404, "Unknown corpus")
        try:
            from backend.services.knowledge.knowledge_store import file_hash
            if knowledge:
                directory = knowledge.directory(version=version)
                source = next(s for s in read_json(directory/'source_manifest.json')['sources'] if s['source_id']==source_id)
                path, reference = knowledge.artifact(version, 'originals/'+source_id+'/'+source['file_name'])
                return FileResponse(path, media_type=reference['mime'], filename=source['file_name'],
                    content_disposition_type='inline' if source['file_name'].lower().endswith('.pdf') else 'attachment')
            manifest = read_json(config.corpus_dir / "versions" / version / "source_manifest.json")
            source = next(s for s in manifest["sources"] if s["source_id"] == source_id)
            path = inside(config.source_dir, source.get("file_path", source["file_name"]))
            media = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
            if path.suffix.lower() not in media or file_hash(path) != source["sha256"]:
                raise ValueError("Source changed or unsupported")
            return FileResponse(path, media_type=media[path.suffix.lower()], filename=path.name,
                                content_disposition_type="inline" if path.suffix.lower() == ".pdf" else "attachment")
        except StorageUnavailable:
            raise
        except (OSError, ValueError, KeyError, StopIteration, EvidenceNotFound, CorpusUnavailable):
            raise HTTPException(404, "Original source is unavailable") from None


    @router.get("/api/knowledge/versions/{version}/source/{source_id}.pdf", include_in_schema=False)
    def knowledge_pdf(version: str, source_id: str, config: Settings = Depends(get_settings), knowledge=Depends(get_knowledge)):
        if not re.fullmatch(r"corpus-[a-f0-9]{20}", version):
            raise HTTPException(404, "Unknown corpus")
        try:
            from backend.services.knowledge.knowledge_store import file_hash
            if knowledge:
                directory = knowledge.directory(version=version)
                source = next(s for s in read_json(directory/'source_manifest.json')['sources'] if s['source_id']==source_id and s['file_name'].lower().endswith('.pdf'))
                path, _ = knowledge.artifact(version,'originals/'+source_id+'/'+source['file_name'])
                return FileResponse(path,media_type='application/pdf',headers={'Content-Disposition':'inline'})
            manifest = read_json(config.corpus_dir / "versions" / version / "source_manifest.json")
            source = next(s for s in manifest["sources"] if s["source_id"] == source_id and s["file_name"].lower().endswith(".pdf"))
            path = inside(config.source_dir, source.get("file_path", source["file_name"]))
            if file_hash(path) != source["sha256"]:
                raise ValueError("Source changed")
            return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})
        except StorageUnavailable:
            raise
        except (OSError, ValueError, KeyError, StopIteration, EvidenceNotFound, CorpusUnavailable):
            raise HTTPException(404, "Original source PDF is unavailable") from None


    @router.get("/api/knowledge/versions/{version}/{artifact:path}", include_in_schema=False)
    def knowledge_artifact(version: str, artifact: str, config: Settings = Depends(get_settings), knowledge=Depends(get_knowledge)):
        if not re.fullmatch(r"corpus-[a-f0-9]{20}", version):
            raise HTTPException(404, "Unknown corpus")
        try:
            if knowledge:
                directory = knowledge.directory(version=version)
                allowed = {'review.html'} | {p['image'] for p in read_json(directory/'raw_pages.json') if p.get('image')}
                if artifact not in allowed:
                    raise ValueError('Unknown artifact')
                path, reference = knowledge.artifact(version,artifact)
                return FileResponse(path,media_type=reference['mime'])
            directory = config.corpus_dir / "versions" / version
            allowed = {"review.html"} | {p["image"] for p in read_json(directory / "raw_pages.json")}
            if artifact not in allowed:
                raise ValueError("Unknown artifact")
            path = inside(directory, artifact)
            if not path.is_file():
                raise ValueError("Missing artifact")
            return FileResponse(path)
        except StorageUnavailable:
            raise
        except (OSError, ValueError, KeyError, EvidenceNotFound, CorpusUnavailable):
            raise HTTPException(404, "Unknown corpus artifact") from None

    return router
