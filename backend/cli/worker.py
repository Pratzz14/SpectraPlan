"""Run the local Python ingestion worker; React and FastAPI remain separate."""
import argparse
import json
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from backend.core.config import Settings
from backend.services.cloud.database import Database
from backend.services.cloud.storage import ArtifactStorage
from backend.services.cloud.knowledge import CloudKnowledge
from backend.services.cloud.jobs import IngestionJobs
from backend.services.knowledge.knowledge_store import read_json,write_json,inside


def process(settings,database,storage,jobs,job):
    from backend.services.cloud.migration import prepare_generation,import_generation,verify_generation
    from backend.pipelines.pdf_knowledge.import_file import ingest_file,progress
    from backend.services.knowledge.knowledge_store import active_directory
    repository=CloudKnowledge(settings,database,storage)
    stopped=threading.Event()
    errors=[]
    with TemporaryDirectory(prefix='spectraplan-job-') as temporary:
        root=Path(temporary)
        local=settings.model_copy(update={'storage_backend':'local','source_dir':root/'originals',
            'corpus_dir':root/'knowledge','knowledge_work_dir':root/'work'})
        repository.hydrate(local)
        batch=job['input'].get('batch',False)
        path=root/job['filename']
        if not batch:
            if job['input'].get('staged'):
                from urllib.parse import quote
                data=storage._request('GET','object/authenticated/'+quote(job['input']['bucket'],safe='')+'/'+quote(job['input']['key'],safe='/')).content
                if len(data)!=job['input']['expected_bytes'] or not 0<len(data)<=settings.knowledge_upload_max_bytes:
                    raise ValueError('Uploaded size does not match the registered file.')
                path.write_bytes(data)
                reference=storage.put(data,source=True,filename=job['filename']);del data
                from backend.services.cloud.database import json_value
                with database.connection() as c:
                    previous=c.execute("SELECT checkpoint FROM spectraplan.ingestion_jobs WHERE filename=%s AND role=%s AND input->>'sha256'=%s AND status='failed' ORDER BY created_at DESC LIMIT 1",(job['filename'],job['role'],reference['sha256'])).fetchone()
                    if previous:job['checkpoint']=previous[0]
                    if not c.execute("UPDATE spectraplan.ingestion_jobs SET input=%s WHERE job_id=%s AND claim_token=%s AND status='running' RETURNING job_id",(json_value(reference),job['job_id'],job['token'])).fetchone():
                        raise ValueError('Upload worker lease expired.')
                job['input']=reference
            else:path.write_bytes(storage.get(job['input']))
        latest=local.knowledge_work_dir/'import/latest'
        latest.mkdir(parents=True,exist_ok=True)
        if job['checkpoint']:
            for name,reference in job['checkpoint'].items():
                target=inside(latest,name)
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(storage.get(reference))
        checkpoint=dict(job['checkpoint'] or {})

        def check():
            if errors:
                raise errors[0]

        def report(record=None):
            check()
            # Completed extraction responses are immutable; checkpoint before publication.
            if record:
                names=['manifest.json','schema.json','pdf_prompt.txt','office_prompt.txt']
                names += [u['result_file'] for u in record.get('units',[]) if u.get('status')=='completed' and u.get('result_file')]
                for name in names:
                    file=inside(latest,name)
                    if file.is_file():
                        from backend.services.knowledge.knowledge_store import file_hash
                        if checkpoint.get(name,{}).get('sha256')!=file_hash(file):
                            checkpoint[name]=storage.put(file.read_bytes(),filename=file.name)
                jobs.update(job,checkpoint=checkpoint,progress=progress(record),message='Extracting source locations')
            else:
                jobs.update(job,message='Processing source')

        def heartbeat():
            while not stopped.wait(15):
                try:
                    jobs.update(job)
                except BaseException as error:
                    errors.append(error)
                    break

        reporter=threading.Thread(target=heartbeat,daemon=True)
        reporter.start()
        try:
            if batch:
                from backend.pipelines.pdf_knowledge.extract import extract_all
                from backend.pipelines.pdf_knowledge.store import publish_extraction
                if not job['input'].get('publish_only'):
                    code=extract_all(local,latest,source_ids=job['input'].get('source_ids'),
                        refresh=job['input'].get('refresh',False),concurrency=min(job['input'].get('concurrency',settings.ingest_concurrency),settings.ingest_concurrency),on_progress=report)
                    if code:
                        raise ValueError('Batch extraction failed; the previous corpus remains active')
                result=publish_extraction(local,latest,merge=bool(job['input'].get('source_ids')))
            else:
                result=ingest_file(local,path,role=job['role'],name=job['filename'],on_progress=report,concurrency=settings.ingest_concurrency,
                    prepare_only=job['input'].get('prepare_only',False))
                if result.get('status')=='prepared':
                    jobs.update(job,status='prepared',message='Prepared locally without model calls',source_id=result['source_id'])
                    return
            check()
            generation=prepare_generation(local,'technical',active_directory(local.corpus_dir))
            jobs.update(job,message='Uploading verified corpus')
            import_generation(database,storage,generation)
            verify_generation(database,storage,generation)
            check()
            # Fence publication and the terminal job update in the SAME transaction.
            from backend.services.cloud.database import json_value
            from backend.services.history.explainability import HistoryConflict
            registry=local.corpus_dir/'added_sources.json'
            with database.connection() as c:
                owned=c.execute("SELECT 1 FROM spectraplan.ingestion_jobs WHERE job_id=%s AND claim_token=%s "
                    "AND status='running' AND lease_until>now() FOR UPDATE",(job['job_id'],job['token'])).fetchone()
                if not owned:
                    raise HistoryConflict('Ingestion lease expired before publication')
                c.execute("INSERT INTO spectraplan.active_corpora VALUES ('technical',%s) ON CONFLICT(dataset) DO UPDATE SET version=excluded.version",(generation['version'],))
                c.execute("INSERT INTO spectraplan.app_state VALUES ('source_registry',%s) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",(json_value(read_json(registry) if registry.is_file() else []),))
                c.execute("UPDATE spectraplan.ingestion_jobs SET status='succeeded',state=state || %s,updated_at=now() WHERE job_id=%s",(json_value({'status':'succeeded','message':'File added to extracted knowledge','corpus_version':generation['version'],'source_id':result.get('source_id')}),job['job_id']))
        finally:
            stopped.set()
            reporter.join(timeout=20)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    settings=Settings()
    if settings.storage_backend!='supabase':
        parser.error('Set STORAGE_BACKEND=supabase before starting the cloud worker')
    database=Database(settings)
    storage=ArtifactStorage(settings)
    jobs=IngestionJobs(settings,database)
    import signal,os
    current={}
    def shutdown(signum,frame):
        # Completed extraction units are already checkpointed remotely. Never wait
        # for an uncertain paid request or let an old thread publish after shutdown.
        deadline=threading.Timer(25,lambda:os._exit(0));deadline.daemon=True;deadline.start()
        try:
            if current.get('kind')=='assessment':
                job=current['job']
                with database.connection() as c:
                    c.execute("SET LOCAL lock_timeout='5s'")
                    changed=c.execute("UPDATE spectraplan.assessment_jobs SET status='interrupted',stage='interrupted' WHERE run_id=%s AND claim_token=%s AND status='running' RETURNING run_id",(job['run_id'],job['token'])).fetchone()
                    if changed:c.execute("UPDATE spectraplan.explainability_runs SET status='interrupted' WHERE run_id=%s AND status='running'",(job['run_id'],))
            elif current.get('kind')=='ingestion':
                jobs.update(current['job'],status='failed',message='Worker restarted. Completed source locations are saved; explicitly retry this file.')
            print('Worker stopped; queued jobs and completed checkpoints remain in Supabase.',flush=True)
        finally:os._exit(0)
    signal.signal(signal.SIGTERM,shutdown)
    try:
        while True:
            if settings.background_assessments:
                from backend.services.cloud.assessments import AssessmentJobs
                assessments=AssessmentJobs(database)
                assessment=assessments.claim()
                if assessment:
                    current.update(kind='assessment',job=assessment)
                    try:assessments.execute(assessment,settings,CloudKnowledge(settings,database,storage))
                    except Exception:print('Assessment interrupted; result retained for explicit retry.',flush=True)
                    finally:current.clear()
                    if args.once:break
                    continue
            job=jobs.claim()
            if job:
                current.update(kind='ingestion',job=job)
                try:
                    process(settings,database,storage,jobs,job)
                except Exception:
                    try:
                        jobs.update(job,status='failed',message='Ingestion failed. Existing knowledge was preserved; retry this file.')
                    except Exception:
                        pass  # Expired/failed lease remains fenced; a restarted worker can continue.
                finally:current.clear()
            if args.once:
                break
            threading.Event().wait(2)
    except KeyboardInterrupt:
        pass
    finally:
        database.close()


if __name__=='__main__':
    main()
