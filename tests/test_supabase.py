"""Cloud contracts; opt-in SQL tests use an isolated schema on localhost only."""
import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from backend.core.config import Settings
from backend.services.cloud.database import StorageUnavailable
from backend.services.cloud.storage import ArtifactStorage
from tests.test_pdf_knowledge import prepared


class MemoryStorage:
    def __init__(self):
        self.objects={}

    def put(self,data,*,source=False,filename='artifact'):
        sha=hashlib.sha256(data).hexdigest()
        self.objects[sha]=data
        return {'bucket':'test','key':sha,'sha256':sha,'mime':'application/octet-stream','bytes':len(data)}

    def get(self,reference):
        data=self.objects[reference['sha256']]
        if hashlib.sha256(data).hexdigest()!=reference['sha256']:
            raise StorageUnavailable('Checksum mismatch')
        return data


@pytest.fixture
def cloud_db():
    url=os.environ.get('SPECTRAPLAN_TEST_DATABASE_URL','')
    if not url:
        pytest.skip('Set SPECTRAPLAN_TEST_DATABASE_URL to an isolated local Postgres with pgvector')
    if urlsplit(url).hostname not in {'localhost','127.0.0.1','::1'}:
        pytest.fail('Cloud tests refuse to modify a remote database')
    import psycopg
    from uuid import uuid4
    schema='spectraplan_test_'+uuid4().hex
    class Connection:
        def __init__(self,c):self.c=c
        def execute(self,query,parameters=None):
            text=query if isinstance(query,str) else query.as_string(self.c)
            text=re.sub(r'\bspectraplan\b',schema,text)
            return self.c.execute(text,parameters)
    class DB:
        @contextmanager
        def connection(self):
            with psycopg.connect(url,connect_timeout=5,prepare_threshold=None) as c:
                yield Connection(c)
    db=DB()
    with db.connection() as c:
        c.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF; IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF; END $$;")
        for script in sorted(Path('backend/services/cloud/migrations').glob('*.sql')):
            c.execute(script.read_text())
    try:
        yield db
    finally:
        from psycopg import sql
        with psycopg.connect(url,prepare_threshold=None) as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_storage_private_and_checksum_validation():
    data=b'private document'
    sha=hashlib.sha256(data).hexdigest()
    requests=[]
    def handler(request):
        requests.append(request)
        assert request.headers['apikey']=='sb_secret_test'
        assert 'authorization' not in request.headers
        return httpx.Response(200,content=data)
    settings=Settings(_env_file=None,supabase_url='https://example.test',supabase_secret_key='sb_secret_test')
    storage=ArtifactStorage(settings,httpx.MockTransport(handler))
    assert storage.get({'bucket':'private','key':'aa/secret','sha256':sha})==data
    with pytest.raises(StorageUnavailable):
        storage.get({'bucket':'private','key':'aa/secret','sha256':'0'*64})
    assert '/object/authenticated/' in str(requests[0].url)


def test_storage_failure_does_not_echo_secret():
    settings=Settings(_env_file=None,supabase_url='https://example.test',supabase_secret_key='sb_secret_private')
    storage=ArtifactStorage(settings,httpx.MockTransport(lambda r:httpx.Response(403,text='sb_secret_private')))
    with pytest.raises(StorageUnavailable) as error:
        storage.get({'bucket':'a','key':'b','sha256':'c'})
    assert 'sb_secret_private' not in str(error.value)


def test_history_rounds_events_ownership_and_literal_filter(cloud_db):
    from backend.services.cloud.history import PostgresHistory
    from backend.services.history.explainability import HistoryConflict
    store=PostgresHistory(cloud_db)
    first=store.begin('moisture',[],owner_user_id='owner',customer_email='Alice@example.test')
    with pytest.raises(HistoryConflict):
        store.begin('again',[],enquiry_id=first['enquiry_id'],parent_run_id=first['run_id'])
    store.append(first['run_id'],{'stage':'provider','event_type':'response','payload':{'private':'trace'}})
    store.finish(first['run_id'],{'run_status':'complete','assessment':None})
    second=store.begin('again',[],enquiry_id=first['enquiry_id'],parent_run_id=first['run_id'],owner_user_id='admin')
    assert second['round_no']==2
    assert store.enquiry(first['enquiry_id'])['owner_user_id']=='owner'
    assert len(store.list_enquiries(email='ALICE@EXAMPLE'))==1
    assert store.list_enquiries(email='%')==[]
    assert [e['sequence'] for e in store.read(first['run_id'])['events']]==[0,1,2]
    with pytest.raises(HistoryConflict):
        store.finish(first['run_id'],{})
    store.recover_interrupted()
    assert store.read(second['run_id'])['status']=='running'
    with cloud_db.connection() as c:
        c.execute("UPDATE spectraplan.explainability_runs SET lease_until=now()-interval '1 second' WHERE run_id=%s",(second['run_id'],))
    store.recover_interrupted()
    assert store.read(second['run_id'])['status']=='interrupted'


def test_job_claim_fencing_expiration_and_explicit_retry(cloud_db):
    from backend.services.cloud.jobs import IngestionJobs
    from backend.services.history.explainability import HistoryConflict
    jobs=IngestionJobs(Settings(_env_file=None),cloud_db)
    reference={'sha256':'a','bucket':'x','key':'a'}
    jobs.enqueue('source.pdf','technical',reference)
    with pytest.raises(HistoryConflict):jobs.enqueue('other.pdf','technical',reference)
    first=jobs.claim()
    assert jobs.claim() is None
    jobs.update(first,checkpoint={'manifest.json':reference},progress={'completed':1})
    with cloud_db.connection() as c:
        c.execute("UPDATE spectraplan.ingestion_jobs SET lease_until=now()-interval '1 second' WHERE job_id=%s",(first['job_id'],))
    assert jobs.status()['status']=='failed'
    with pytest.raises(HistoryConflict):jobs.update(first,status='succeeded')
    jobs.enqueue('source.pdf','technical',reference)
    retry=jobs.claim()
    assert retry['checkpoint']=={'manifest.json':reference}
    jobs.update(retry,status='succeeded')
    assert jobs.status()['status']=='succeeded'


def test_import_history_idempotency_and_conflict_detection(cloud_db,tmp_path):
    from backend.services.history.explainability import ExplainabilityStore
    from backend.services.cloud.migration import history_rows,import_history,verify_history
    source=ExplainabilityStore(tmp_path/'history.sqlite')
    run=source.begin('legacy',[])
    source.finish(run['run_id'],{'run_status':'complete'})
    rows=history_rows(source.path)
    import_history(cloud_db,rows)
    import_history(cloud_db,rows)
    assert verify_history(cloud_db,rows)['enquiries']==1
    rows['enquiries'][0]['original_description']='conflict'
    with pytest.raises(ValueError):verify_history(cloud_db,rows)


def test_corpus_import_search_without_local_indexes_and_artifacts(cloud_db,tmp_path,monkeypatch):
    from tests.corpus_fixture import make_corpus,FakeEmbedder,rehash
    from backend.services.knowledge.knowledge_store import read_json,write_json,validate_corpus
    from backend.services.cloud.migration import prepare_generation,import_generation,verify_generation,activate
    from backend.services.cloud.knowledge import CloudKnowledge
    from backend.services.search.search_service import SearchService
    from backend.services.search.retrieval import CaseRetrievalService
    from tests.test_retrieval import powder_case
    version='corpus-'+'1'*20
    root=tmp_path/'source'
    directory=root/'versions'/version
    make_corpus(directory)
    for name in ('source_manifest.json','index_manifest.json','bm25.json'):
        data=read_json(directory/name);data['corpus_version']=version;write_json(directory/name,data)
    rehash(directory)
    write_json(root/'current.json',{'corpus_version':version,'directory':'versions/'+version})
    originals=tmp_path/'originals';originals.mkdir()
    (originals/'test.pdf').write_bytes(b'fixture pdf');(originals/'test.xlsx').write_bytes(b'fixture workbook')
    config=Settings(_env_file=None,corpus_dir=root,source_dir=originals,cloud_cache_dir=tmp_path/'fresh-cloud-cache')
    # Synthetic fixtures use intentionally fabricated original hashes; validate the corpus structure.
    monkeypatch.setattr('backend.services.cloud.migration.validate_corpus',lambda d,**kw:validate_corpus(d,deep=True))
    generation=prepare_generation(config,'technical',directory)
    storage=MemoryStorage()
    import_generation(cloud_db,storage,generation)
    import_generation(cloud_db,storage,generation)
    with pytest.raises(ValueError):activate(cloud_db,{'technical':version})
    assert verify_generation(cloud_db,storage,generation)['verified']
    activate(cloud_db,{'technical':version})
    repository=CloudKnowledge(config,cloud_db,storage)
    monkeypatch.setattr('backend.services.search.search_service.Embedder',lambda *a,**k:FakeEmbedder())
    monkeypatch.setattr('backend.services.search.retrieval.Embedder',lambda *a,**k:FakeEmbedder())
    baseline=SearchService(config).compare('powder Raman',mode='compare')
    remote=SearchService(config,repository=repository).compare('powder Raman',mode='compare')
    for branch in ('bm25','qdrant','hybrid'):
        assert [r['evidence']['evidence_id'] for r in remote['rankings'][branch]]==[r['evidence']['evidence_id'] for r in baseline['rankings'][branch]]
        for a,b in zip(remote['rankings'][branch],baseline['rankings'][branch],strict=True):assert abs(a['score']-b['score'])<1e-6
    assert not list(config.cloud_cache_dir.rglob('qdrant'))
    result=CaseRetrievalService(config,repository=repository).retrieve_case(powder_case())
    assert result.corpus_version==version
    assert result.evidence
    path,reference=repository.artifact(version,'assets/p1.jpg')
    assert path.read_bytes()==b'test image'
    # An outage must not serve the cached corpus as if cloud storage were ready.
    class Offline:
        @contextmanager
        def connection(self):raise StorageUnavailable('offline');yield
    repository.database=Offline()
    with pytest.raises(StorageUnavailable):repository.directory()


def test_cloud_auth_and_missing_credentials_fail_closed(tmp_path):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.api.auth import Identity,get_current_user
    app=create_app(Settings(_env_file=None,storage_backend='supabase',cloud_cache_dir=tmp_path))
    with TestClient(app) as client:
        assert client.get('/api/enquiries').status_code==401
        app.dependency_overrides[get_current_user]=lambda:Identity('a','a@example.test','admin')
        assert client.get('/api/enquiries').status_code==503
    assert not (tmp_path/'history.sqlite').exists()


def test_cloud_history_http_owner_and_admin_projections(cloud_db):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.services.cloud.history import PostgresHistory
    from backend.api.auth import get_current_user
    from tests.test_auth import OWNER,OTHER,ADMIN,seed
    app=create_app(Settings(_env_file=None,storage_backend='supabase'))
    store=PostgresHistory(cloud_db)
    app.state.explainability_store=store
    own=seed(store,OWNER);other=seed(store,OTHER);legacy=seed(store,None)
    app.dependency_overrides[get_current_user]=lambda:OWNER
    with TestClient(app) as client:
        result=client.get('/api/assess/'+own['run_id'])
        assert result.status_code==200 and 'private provider response' not in result.text
        assert client.get('/api/assess/'+other['run_id']).status_code==404
        assert client.get('/api/assess/'+legacy['run_id']).status_code==404
        assert client.get('/api/enquiries').status_code==403
        assert client.get('/api/assess/'+own['run_id']+'/report.pdf').content.startswith(b'%PDF-')
        app.dependency_overrides[get_current_user]=lambda:ADMIN
        assert len(client.get('/api/enquiries').json())==3
        assert 'private provider response' in client.get('/api/assess/'+own['run_id']+'/explainability').text


def test_cloud_assessment_request_persists_result_outside_api_loop(cloud_db,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.services.cloud.history import PostgresHistory
    from backend.api.auth import get_current_user
    from backend.services.search.retrieval import CaseRetrievalService
    from tests.test_auth import OWNER
    from tests.test_assessment_api import provider_for,mock_retrieval
    from tests.test_assessment import draft,ledger
    from tests.test_extraction import powder,wire_for
    text='A powder; measure moisture.'
    adapter,calls=provider_for([wire_for(powder(text).model_dump()),draft(empty=True)])
    config=adapter.settings.model_copy(update={'storage_backend':'supabase'})
    mock_retrieval(monkeypatch,ledger(empty=True))
    monkeypatch.setattr('backend.pipelines.assessment.pipeline.Provider',lambda _:adapter)
    app=create_app(config)
    store=PostgresHistory(cloud_db)
    app.state.explainability_store=store
    app.state.retrieval_service=CaseRetrievalService(config)
    app.dependency_overrides[get_current_user]=lambda:OWNER
    with TestClient(app) as client:
        response=client.post('/api/assess',json={'description':text})
        assert response.status_code==200
        result=response.json()
        saved=store.read(result['metadata']['run_id'])
        assert saved['run'] and saved['status']!='running'
        assert store.enquiry(saved['enquiry_id'])['owner_user_id']==OWNER.user_id
        assert len(calls)==2


def test_worker_hydrates_inputs_checkpoints_and_publishes_without_model_calls(cloud_db,prepared,tmp_path):
    from pydantic import SecretStr
    from backend.pipelines.pdf_knowledge.store import publish_extraction
    from backend.services.knowledge.knowledge_store import active_directory
    from backend.services.cloud.migration import prepare_generation,import_generation,verify_generation,activate
    from backend.services.cloud.jobs import IngestionJobs
    from backend.services.cloud.knowledge import CloudKnowledge
    from backend.cli.worker import process
    from tests.test_file_ingestion import pdf
    settings,latest=prepared
    publish_extraction(settings,latest)
    generation=prepare_generation(settings,'technical',active_directory(settings.corpus_dir))
    storage=MemoryStorage()
    import_generation(cloud_db,storage,generation)
    verify_generation(cloud_db,storage,generation)
    activate(cloud_db,{'technical':generation['version']})
    remote=settings.model_copy(update={'storage_backend':'supabase','source_dir':tmp_path/'absent-originals',
        'corpus_dir':tmp_path/'absent-corpus','cloud_cache_dir':tmp_path/'worker-cloud-cache',
        'dashscope_api_key':SecretStr('')})
    source=tmp_path/'imported.pdf';pdf(source)
    reference=storage.put(source.read_bytes(),source=True,filename=source.name)
    jobs=IngestionJobs(remote,cloud_db)
    jobs.enqueue(source.name,'research',reference)
    job=jobs.claim()
    process(remote,cloud_db,storage,jobs,job)
    status=jobs.status()
    assert status['status']=='succeeded'
    repository=CloudKnowledge(remote,cloud_db,storage)
    assert repository.snapshot().version!=generation['version']
    assert len(json.loads((repository.directory()/'source_manifest.json').read_text())['sources'])==2
    with cloud_db.connection() as c:
        assert c.execute('SELECT checkpoint FROM spectraplan.ingestion_jobs WHERE job_id=%s',(job['job_id'],)).fetchone()[0]
    assert not remote.source_dir.exists() and not remote.corpus_dir.exists()
    from backend.services.cloud.export import export_cloud
    output=tmp_path/'export'
    export_cloud(remote,cloud_db,storage,output)
    manifest=json.loads((output/'manifest.json').read_text())
    assert manifest['files'] and 'database.json' in manifest['files']
    dump=json.loads((output/'database.json').read_text())
    assert len(dump['corpus_versions'])==2 and dump['ingestion_jobs'][0]['status']=='succeeded'
