"""Single-file ingestion and asynchronous upload boundaries use synthetic sources."""
import asyncio
import json
from pathlib import Path

import httpx
import pymupdf
import pytest
from filelock import FileLock

from backend.services.knowledge.knowledge_store import active_directory, load_records, read_json, file_hash
from tests.auth_helpers import create_app
from backend.pipelines.pdf_knowledge import extract, import_file
from backend.pipelines.pdf_knowledge.store import publish_extraction
from tests.test_pdf_knowledge import prepared, answer


def pdf(path, pages=1):
    with pymupdf.open() as doc:
        for _ in range(pages):
            p=doc.new_page();p.insert_text((40,60),'Synthetic imported spectroscopy document.')
        doc.save(path)


@pytest.fixture
def adding(prepared, tmp_path, monkeypatch):
    settings, latest=prepared
    publish_extraction(settings,latest)
    settings=settings.model_copy(update={'knowledge_work_dir':tmp_path/'work'})
    original=httpx.Client
    calls=[]
    def extraction(config, directory, **kwargs):
        def respond(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer())}}]})
        with monkeypatch.context() as patch:
            patch.setattr(extract.httpx,'Client',lambda **options:original(transport=httpx.MockTransport(respond),**options))
            return extract.extract_all(config,directory,**kwargs)
    monkeypatch.setattr(import_file,'extract_all',extraction)
    return settings,calls


def test_add_and_update_keep_existing_sources_and_immutable_originals(adding,tmp_path):
    settings,calls=adding
    sample=tmp_path/'new study.pdf';pdf(sample)
    report=import_file.ingest_file(settings,sample,role='research')
    sid=report['source_id'];assert report['sources']==2 and len(calls)==1
    directory=active_directory(settings.corpus_dir)
    manifest,records,_=load_records(directory)
    assert {r['source_id'] for r in records}=={'S04',sid}
    imported=next(s for s in manifest['sources'] if s['source_id']==sid)
    stored=settings.source_dir/imported['file_path'];first_bytes=stored.read_bytes()
    assert first_bytes==sample.read_bytes()
    replacement=tmp_path/'replacement.pdf';pdf(replacement,2)
    report=import_file.ingest_file(settings,replacement,name=sample.name,role='research')
    assert report['source_id']==sid and report['sources']==2
    _,records,_=load_records(active_directory(settings.corpus_dir))
    assert len([r for r in records if r['source_id']==sid])==2
    assert stored.read_bytes()==first_bytes
    assert all(r['evidence_scope']=='research_demonstration' for r in records if r['source_id']==sid)
    async def original_api():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings)),base_url='http://test') as client:
            prefix='/api/knowledge/versions/'+report['corpus_version']+'/'
            response=await client.get(prefix+f'source/{sid}/original')
            assert response.status_code==200 and response.content==replacement.read_bytes()
    asyncio.run(original_api())


def test_failed_replacement_keeps_published_knowledge_and_original(adding,tmp_path,monkeypatch):
    settings,_=adding
    sample=tmp_path/'study.pdf';pdf(sample)
    result=import_file.ingest_file(settings,sample)
    directory=active_directory(settings.corpus_dir)
    manifest,_,_=load_records(directory)
    source=next(s for s in manifest['sources'] if s['source_id']==result['source_id'])
    before=file_hash(settings.source_dir/source['file_path'])
    replacement=tmp_path/'update.pdf';pdf(replacement,2)
    monkeypatch.setattr(import_file,'extract_all',lambda *a,**k:1)
    job=settings.knowledge_work_dir/'import/job.json'
    with pytest.raises(ValueError,match='Existing knowledge was preserved'):
        import_file.ingest_file(settings,replacement,name='study.pdf',job_file=job)
    assert active_directory(settings.corpus_dir)==directory
    assert file_hash(settings.source_dir/source['file_path'])==before
    assert read_json(job)['status']=='failed'


def test_upload_api_queues_only_selected_file_and_rejects_invalid_requests(adding,tmp_path,monkeypatch):
    settings,_=adding
    calls=[]
    def start(config,path,filename,role):
        calls.append((path.read_bytes(),filename,role))
        return {'job_id':'test-job','status':'queued','filename':filename,'progress':{}}
    monkeypatch.setattr(import_file,'start_worker',start)
    async def requests():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings)),base_url='http://test') as client:
            headers={'Content-Type':'application/octet-stream'}
            response=await client.post('/api/knowledge/ingest?filename=uploaded.pdf&role=research',content=b'synthetic upload',headers=headers)
            assert response.status_code==202 and response.json()['job_id']=='test-job'
            assert calls==[(b'synthetic upload','uploaded.pdf','research')]
            assert (await client.post('/api/knowledge/ingest?filename=../escape.pdf',content=b'x',headers=headers)).status_code==422
            assert (await client.post('/api/knowledge/ingest?filename=script.exe',content=b'x',headers=headers)).status_code==422
            assert (await client.post('/api/knowledge/ingest?filename=empty.pdf',content=b'',headers=headers)).status_code==422
            assert (await client.post('/api/knowledge/ingest?filename=test.pdf',content=b'x')).status_code==415
            settings.knowledge_upload_max_bytes=1024
            assert (await client.post('/api/knowledge/ingest?filename=large.pdf',content=b'x'*1025,headers=headers)).status_code==413
            with FileLock(str(settings.knowledge_work_dir/'build.lock')):
                assert (await client.post('/api/knowledge/ingest?filename=busy.pdf',content=b'x',headers=headers)).status_code==409
            state=(await client.get('/api/knowledge/ingest/status')).json()
            assert state['max_bytes']==1024 and state['endpoint_host']
    asyncio.run(requests())


def test_prepare_only_and_invalid_formats_do_not_call_model(adding,tmp_path):
    settings,calls=adding
    sample=tmp_path/'prepared.PDF';pdf(sample)
    report=import_file.ingest_file(settings,sample,prepare_only=True)
    assert report['status']=='prepared' and not calls
    invalid=tmp_path/'bad.docx';invalid.write_bytes(b'not an Office document')
    before=active_directory(settings.corpus_dir)
    with pytest.raises(ValueError): import_file.ingest_file(settings,invalid)
    assert active_directory(settings.corpus_dir)==before and not calls


def test_context_only_first_file_is_inspectable_without_assessment_evidence(adding,tmp_path):
    from backend.services.health import inspect_corpus
    settings,_=adding
    settings=settings.model_copy(update={'corpus_dir':tmp_path/'empty-library','knowledge_work_dir':tmp_path/'empty-work'})
    sample=tmp_path/'vendor flyer.pdf';pdf(sample)
    report=import_file.ingest_file(settings,sample,role='business')
    assert report['sources']==1 and report['eligible_passages']==0
    assert inspect_corpus(settings.corpus_dir).status=='empty'
    manifest,records,_=load_records(active_directory(settings.corpus_dir))
    assert records[0]['evidence_scope']=='business_context' and not records[0]['retrieval_eligible']
    assert (active_directory(settings.corpus_dir)/'inspection/index_manifest.json').is_file()


def test_atomic_json_write_retries_windows_sharing_locks_without_losing_old_data(tmp_path,monkeypatch):
    import os
    import backend.services.knowledge.knowledge_store as store
    if os.name!='nt': pytest.skip('Windows sharing-lock behavior')
    path=tmp_path/'status.json';store.write_json(path,{'value':'old'})
    original=os.replace
    calls=[]
    def replace(source,destination):
        calls.append(1)
        if len(calls)<3:
            assert store.read_json(path)=={'value':'old'}
            error=PermissionError('Transient sharing lock');error.winerror=32
            raise error
        return original(source,destination)
    with monkeypatch.context() as patch:
        patch.setattr(store.os,'replace',replace)
        store.write_json(path,{'value':'new'})
    assert len(calls)==3 and store.read_json(path)=={'value':'new'}
    assert not list(tmp_path.glob('*.tmp'))


def test_completed_batch_status_refreshes_the_inspector(adding):
    from backend.services.knowledge.knowledge_store import write_json
    settings,_=adding
    write_json(settings.knowledge_work_dir/'latest/manifest.json',{'status':'completed_needs_visual_review',
        'production_corpus_modified':True,'published_version':'corpus-test','units':[{'status':'completed'}]})
    state=import_file.ingestion_status(settings)
    assert state['status']=='succeeded' and state['corpus_version']=='corpus-test'


def test_selected_cli_build_retains_other_sources(adding,tmp_path,monkeypatch):
    import sys
    import backend.cli.ingest as cli
    settings,_=adding
    sample=tmp_path/'retained.pdf';pdf(sample)
    imported=import_file.ingest_file(settings,sample)
    monkeypatch.setattr(cli,'Settings',lambda:settings)
    monkeypatch.setattr(cli,'extract_all',import_file.extract_all)
    monkeypatch.setattr(sys,'argv',['ingest','build','--source','S04','--concurrency','1'])
    assert cli.main()==0
    manifest,_,_=load_records(active_directory(settings.corpus_dir))
    assert {s['source_id'] for s in manifest['sources']}=={'S04',imported['source_id']}


def test_busy_cli_does_not_mark_running_manifest_failed(adding,monkeypatch):
    import sys
    import backend.cli.ingest as cli
    from backend.services.knowledge.knowledge_store import write_json
    settings,_=adding
    path=settings.knowledge_work_dir/'latest/manifest.json'
    write_json(path,{'status':'running','units':[]})
    before=path.read_bytes()
    monkeypatch.setattr(cli,'Settings',lambda:settings)
    monkeypatch.setattr(sys,'argv',['ingest','build'])
    with FileLock(str(settings.knowledge_work_dir/'build.lock')):
        assert cli.main()==1
    assert path.read_bytes()==before


def test_upload_worker_heartbeats_during_indexing(adding,tmp_path,monkeypatch):
    import time
    settings,_=adding
    sample=tmp_path/'heartbeat.pdf';pdf(sample)
    job=settings.knowledge_work_dir/'import/job.json'
    original=import_file.publish_extraction
    monkeypatch.setattr(import_file,'HEARTBEAT_SECONDS',.01)
    def publish(*args,**kwargs):
        before=read_json(job)['updated_at']
        time.sleep(.08)
        after=read_json(job)
        assert after['updated_at']>before and after['status']=='running'
        return original(*args,**kwargs)
    monkeypatch.setattr(import_file,'publish_extraction',publish)
    import_file.ingest_file(settings,sample,job_file=job)
    assert read_json(job)['status']=='succeeded'
