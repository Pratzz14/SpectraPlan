"""Durable assessment submissions and fenced background execution."""
import asyncio
from contextlib import contextmanager
from uuid import uuid4
import threading
from backend.services.cloud.database import json_value
from backend.services.cloud.history import PostgresHistory
from backend.services.history.explainability import HistoryConflict,question_id


class BoundDatabase:
    def __init__(self,connection):self.value=connection
    @contextmanager
    def connection(self):yield self.value


class AssessmentJobs:
    def __init__(self,database):self.database=database

    def submit(self,request,user,key,settings):
        with self.database.connection() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('assessment:'+user.user_id,))
            old=c.execute('SELECT run_id,request FROM spectraplan.assessment_jobs WHERE owner_user_id=%s AND idempotency_key=%s',(user.user_id,key)).fetchone()
            payload=request.model_dump(mode='json')
            if old:
                if old[1]!=payload:raise HistoryConflict('Submission key belongs to a different enquiry.')
                return self.envelope(c,old[0])
            self.expire(c)
            if c.execute("SELECT 1 FROM spectraplan.assessment_jobs WHERE owner_user_id=%s AND status IN ('queued','running')",(user.user_id,)).fetchone():
                raise HistoryConflict('An assessment is already queued or running for your account.')
            store=PostgresHistory(BoundDatabase(c))
            if request.enquiry_id:
                from backend.api.auth import require_owner
                require_owner(store.enquiry(request.enquiry_id),user)
            identity=store.begin(request.description,[a.model_dump(mode='json') for a in request.clarification_answers],
                enquiry_id=request.enquiry_id,parent_run_id=request.parent_run_id,owner_user_id=user.user_id,
                customer_email=user.email,max_description_chars=settings.assessment_max_description_chars)
            c.execute("UPDATE spectraplan.explainability_runs SET status='queued',lease_until=NULL WHERE run_id=%s",(identity['run_id'],))
            c.execute('INSERT INTO spectraplan.assessment_jobs(run_id,owner_user_id,idempotency_key,request) VALUES (%s,%s,%s,%s)',
                (identity['run_id'],user.user_id,key,json_value(payload)))
            return self.envelope(c,identity['run_id'])

    @staticmethod
    def envelope(c,run_id):
        row=c.execute('SELECT enquiry_id FROM spectraplan.explainability_runs WHERE run_id=%s',(run_id,)).fetchone()
        return {'run_id':run_id,'enquiry_id':row[0],'status_url':'/api/assess/'+run_id+'/status'}

    @staticmethod
    def expire(c):
        rows=c.execute("UPDATE spectraplan.assessment_jobs SET status='interrupted',stage='interrupted' WHERE status='running' AND lease_until<now() RETURNING run_id").fetchall()
        for (run_id,) in rows:
            c.execute("UPDATE spectraplan.explainability_runs SET status='interrupted' WHERE run_id=%s AND status='running'",(run_id,))

    def claim(self):
        with self.database.connection() as c:
            self.expire(c)
            row=c.execute("SELECT run_id FROM spectraplan.assessment_jobs a WHERE status='queued' AND NOT EXISTS (SELECT 1 FROM spectraplan.ingestion_jobs i WHERE i.status='queued' AND i.created_at<a.created_at) ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
            if not row:return None
            version=c.execute("SELECT version FROM spectraplan.active_corpora WHERE dataset='technical'").fetchone()
            if not version:raise ValueError('No published technical corpus')
            token=uuid4().hex
            c.execute("UPDATE spectraplan.assessment_jobs SET status='running',stage='extraction',claim_token=%s,lease_until=now()+interval '10 minutes',corpus_version=%s WHERE run_id=%s",(token,version[0],row[0]))
            c.execute("UPDATE spectraplan.explainability_runs SET status='running',lease_until=now()+interval '10 minutes' WHERE run_id=%s",(row[0],))
            return {'run_id':row[0],'token':token,'version':version[0]}

    @contextmanager
    def owned(self,job):
        with self.database.connection() as c:
            if not c.execute("SELECT 1 FROM spectraplan.assessment_jobs WHERE run_id=%s AND claim_token=%s AND status='running' AND lease_until>now() FOR UPDATE",(job['run_id'],job['token'])).fetchone():
                raise HistoryConflict('Assessment worker lease expired.')
            yield c

    def execute(self,job,settings,repository):
        from backend.pipelines.assessment.pipeline import assess_case
        from backend.services.search.retrieval import CaseRetrievalService
        class Pinned:
            def snapshot(self,version=None):return repository.snapshot(version or job['version'])
            def client(self,directory):return repository.client(directory)
        store=PostgresHistory(self.database)
        saved=store.read(job['run_id'])
        stopped=threading.Event()
        def heartbeat():
            while not stopped.wait(15):
                try:
                    with self.owned(job) as c:
                        c.execute("UPDATE spectraplan.assessment_jobs SET lease_until=now()+interval '10 minutes' WHERE run_id=%s",(job['run_id'],))
                        c.execute("UPDATE spectraplan.explainability_runs SET lease_until=now()+interval '10 minutes' WHERE run_id=%s",(job['run_id'],))
                except Exception:return
        def event(value):
            with self.owned(job) as c:
                PostgresHistory(BoundDatabase(c)).append(job['run_id'],value)
                c.execute('UPDATE spectraplan.assessment_jobs SET stage=%s WHERE run_id=%s',(value.get('stage','processing'),job['run_id']))
        thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
        try:
            result=asyncio.run(assess_case(saved['description'],settings,retrieval_service=CaseRetrievalService(settings,repository=Pinned()),
                on_event=event,on_stage=lambda stage,value:event({'stage':stage,'event_type':'validated_stage','payload':value.model_dump(mode='json')}),run_id=job['run_id']))
            result.metadata.enquiry_id=saved['enquiry_id'];result.metadata.parent_run_id=saved['parent_run_id'];result.metadata.round_no=saved['round_no']
            result.metadata.question_ids=[question_id(job['run_id'],q.model_dump()) for q in result.assessment.clarification_questions] if result.assessment else []
            with self.owned(job) as c:
                PostgresHistory(BoundDatabase(c)).finish(job['run_id'],result.model_dump(mode='json'))
                c.execute('UPDATE spectraplan.assessment_jobs SET status=%s,stage=%s WHERE run_id=%s',(result.run_status,result.run_status,job['run_id']))
        except BaseException:
            with self.owned(job) as c:
                PostgresHistory(BoundDatabase(c)).interrupt(job['run_id'],'Worker interrupted; explicitly retry this enquiry.')
                c.execute("UPDATE spectraplan.assessment_jobs SET status='interrupted',stage='interrupted' WHERE run_id=%s",(job['run_id'],))
            raise
        finally:stopped.set();thread.join(timeout=20)
