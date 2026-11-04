"""Cloud-aware ingestion CLI operations; all processing remains local Python."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from backend.services.cloud.database import Database
from backend.services.cloud.storage import ArtifactStorage
from backend.services.cloud.knowledge import CloudKnowledge
from backend.services.cloud.jobs import IngestionJobs,enqueue_file
from backend.services.cloud.migration import prepare_generation,import_generation,verify_generation,activate
from backend.services.knowledge.knowledge_store import read_json,digest


def ingestion(settings,args):
    database=Database(settings)
    storage=ArtifactStorage(settings)
    repository=CloudKnowledge(settings,database,storage)
    jobs=IngestionJobs(settings,database)
    try:
        if args.command=='add':
            print(json.dumps(enqueue_file(settings,args.file,args.name or args.file.name,args.role,prepare_only=args.prepare_only),indent=2))
        elif args.command in {'build','pilot','publish'}:
            if args.command=='publish':
                with database.connection() as c:
                    prior=c.execute("SELECT input FROM spectraplan.ingestion_jobs WHERE status='failed' AND input->>'batch'='true' ORDER BY created_at DESC LIMIT 1").fetchone()
                if not prior:
                    raise ValueError('No failed cloud batch is available to resume')
                reference=prior[0] | {'publish_only':True}
            else:
                version=repository.snapshot().version
                reference={'batch':True,'source_ids':args.source_ids,'refresh':args.refresh,
                    'sha256':digest([version,args.source_ids,args.refresh]),'concurrency':args.concurrency}
            print(json.dumps(jobs.enqueue('Source batch','batch',reference),indent=2))
        elif args.command=='validate':
            snapshot=repository.snapshot()
            print(json.dumps({'status':'ready','corpus_version':snapshot.version,'eligible_records':len(snapshot.records)},indent=2))
        elif args.command=='report':
            print('/api/knowledge/versions/'+repository.snapshot().version+'/review.html')
        else:
            from backend.services.search.search_service import SearchService
            print(json.dumps(SearchService(settings,repository=repository).compare(args.query,mode='hybrid'),indent=2))
        return 0
    finally:
        database.close()


def website(settings,args):
    database=Database(settings)
    storage=ArtifactStorage(settings)
    try:
        repository=CloudKnowledge(settings,database,storage)
        directory=repository.directory('website')
        if args.command=='validate':
            return {'status':'ready','corpus_version':directory.name}
        seed=read_json(directory/'manifest.json')['seed_url']
        with TemporaryDirectory(prefix='spectraplan-crawl-') as temporary:
            root=Path(temporary)
            sources=root/'sources';sources.mkdir()
            (sources/'S06_Laboratory_Link.txt').write_text(seed,encoding='utf-8')
            local=settings.model_copy(update={'storage_backend':'local','source_dir':sources,'web_corpus_dir':root/'web'})
            from backend.pipelines.website.ingest import crawl,web_directory
            result=crawl(local,max_pages=args.max_pages,max_depth=args.max_depth)
            generation=prepare_generation(local,'website',web_directory(local.web_corpus_dir))
            import_generation(database,storage,generation)
            verify_generation(database,storage,generation)
            activate(database,{'website':generation['version']})
            return result
    finally:
        database.close()
