"""Durable single-ingestion queue with fenced worker leases."""
from urllib.parse import urlsplit
from uuid import uuid4
from backend.services.cloud.database import Database, json_value
from backend.services.cloud.storage import ArtifactStorage
from backend.services.history.explainability import HistoryConflict


class IngestionJobs:
    def __init__(self, settings, database):
        self.settings,self.database=settings,database

    def _expire(self,c):
        c.execute("UPDATE spectraplan.ingestion_jobs SET status='failed',claim_token=NULL, "
            "state=state || %s WHERE status='running' AND lease_until < now()",
            (json_value({'status':'failed','message':'Worker heartbeat expired. Retry this file.'}),))

    def enqueue(self, filename, role, reference):
        job_id=uuid4().hex
        state={'job_id':job_id,'filename':filename,'status':'queued','progress':{},'message':'Waiting for local Python worker'}
        with self.database.connection() as c:
            c.execute("SELECT pg_advisory_xact_lock(hashtext('spectraplan:ingestion'))")
            self._expire(c)
            if c.execute("SELECT 1 FROM spectraplan.ingestion_jobs WHERE status IN ('queued','running')").fetchone():
                raise HistoryConflict('Another ingestion is running. Try again when it finishes.')
            previous=c.execute("SELECT checkpoint FROM spectraplan.ingestion_jobs WHERE filename=%s AND role=%s "
                "AND input->>'sha256'=%s AND status='failed' ORDER BY created_at DESC LIMIT 1",(filename,role,reference['sha256'])).fetchone()
            c.execute('INSERT INTO spectraplan.ingestion_jobs(job_id,status,filename,role,input,state,checkpoint) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                (job_id,'queued',filename,role,json_value(reference),json_value(state),json_value(previous[0]) if previous else None))
        return state

    def claim(self):
        with self.database.connection() as c:
            self._expire(c)
            row=c.execute("SELECT job_id,filename,role,input,state,checkpoint FROM spectraplan.ingestion_jobs "
                "WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
            if not row:
                return None
            token=uuid4().hex
            c.execute("UPDATE spectraplan.ingestion_jobs SET status='running',claim_token=%s,lease_until=now()+interval '10 minutes',"
                "updated_at=now(),state=state || %s WHERE job_id=%s",(token,json_value({'status':'running'}),row[0]))
            return dict(zip(('job_id','filename','role','input','state','checkpoint'),row)) | {'token':token}

    def update(self, job, *, checkpoint=None, **values):
        with self.database.connection() as c:
            row=c.execute("UPDATE spectraplan.ingestion_jobs SET state=state || %s,updated_at=now(),"
                "lease_until=now()+interval '10 minutes',checkpoint=COALESCE(%s,checkpoint),status=COALESCE(%s,status) "
                "WHERE job_id=%s AND claim_token=%s AND status='running' RETURNING job_id",
                (json_value(values),json_value(checkpoint) if checkpoint is not None else None,values.get('status'),job['job_id'],job['token'])).fetchone()
            if not row:
                raise HistoryConflict('Ingestion lease was lost. Publication stopped.')

    def status(self):
        with self.database.connection() as c:
            self._expire(c)
            row=c.execute('SELECT state FROM spectraplan.ingestion_jobs ORDER BY created_at DESC LIMIT 1').fetchone()
        return (row[0] if row else {'job_id':'','status':'idle','progress':{}}) | {
            'endpoint_host':urlsplit(self.settings.dashscope_base_url).hostname,
            'max_bytes':self.settings.knowledge_upload_max_bytes,'qwen_configured':self.settings.provider_configured}


def job_services(settings):
    # Short-lived CLI/status service. Close its database via the caller's context.
    return IngestionJobs(settings,Database(settings))


def enqueue_file(settings,path,filename,role,prepare_only=False):
    from tempfile import TemporaryDirectory
    from pathlib import Path
    from backend.pipelines.pdf_knowledge.registry import register_file
    with TemporaryDirectory(prefix='spectraplan-validate-') as temp:
        local=settings.model_copy(update={'source_dir':Path(temp)/'sources','corpus_dir':Path(temp)/'knowledge'})
        entry=register_file(local,path,role=role,name=filename)
    reference=ArtifactStorage(settings).put(path.read_bytes(),source=True,filename=filename)
    if prepare_only:
        reference['prepare_only']=True
    jobs=job_services(settings)
    try:
        return jobs.enqueue(filename,entry['role'],reference)
    finally:
        jobs.database.close()
