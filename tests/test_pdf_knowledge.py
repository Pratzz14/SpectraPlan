"""Image-only extraction and S04 publication; no external requests in tests."""
import asyncio
import json
from pathlib import Path

import httpx
import pymupdf
import pytest
from pydantic import ValidationError

from backend.core.config import Settings
from backend.services.knowledge.knowledge_store import active_directory, read_json, validate_corpus, write_json
from backend.pipelines.pdf_knowledge import extract
from backend.pipelines.pdf_knowledge.store import publish_extraction
from tests.auth_helpers import create_app
from tests.corpus_fixture import FakeEmbedder


def answer(empty=False):
    return {'page_title': 'Synthetic probe', 'page_kind': 'research', 'knowledge': [] if empty else [{
        'category': 'new_model_category', 'claim': 'A synthetic probe measures two signals.',
        'support_quote': 'The probe measures fluorescence and infrared absorption.', 'evidence_kind': 'abstract',
        'scope': 'own_study', 'quantities': [{'value': 'a few', 'unit': 'um', 'meaning': 'model-reported depth'}],
        'relevance': 'Complementary spectroscopy signals.', 'caveat': None}],
        'unreadable_regions': [], 'page_limitations': []}


def test_minimal_checks_accept_model_categories_and_unanchored_quantities():
    content = json.dumps(answer())
    assert extract.parse_answer(content) == extract.parse_answer('```json\n' + content + '\n```')
    assert extract.parse_answer(content).knowledge[0].quantities[0].value == 'a few'
    for invalid in ['not json', 'Introduction\n' + content, json.dumps({**answer(), 'knowledge': None})]:
        with pytest.raises(ValidationError):
            extract.parse_answer(invalid)
    invalid = answer(); invalid['knowledge'][0]['support_quote'] = '  '
    with pytest.raises(ValidationError):
        extract.parse_answer(json.dumps(invalid))


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    sources = tmp_path / 'sources'; sources.mkdir()
    path = sources / 'S04_Combi_MIR_Fluorescence_2021.pdf'
    with pymupdf.open() as doc:
        for i in range(2):
            page = doc.new_page(); page.insert_text((40, 60), 'TEXT LAYER MUST NOT ENTER REQUEST')
        doc.save(path)
    settings = Settings(_env_file=None, source_dir=sources, corpus_dir=tmp_path/'knowledge',
        embedding_cache_dir=tmp_path/'models', dashscope_api_key='synthetic-test-key')
    monkeypatch.setattr(extract, 'ROOT', tmp_path)
    monkeypatch.setattr(extract, 'Settings', lambda: settings)
    calls = []
    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload['model'] == 'qwen3.8-flash' and payload['enable_thinking'] is False
        assert 'TEXT LAYER MUST NOT ENTER REQUEST' not in request.content.decode()
        assert payload['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
        return httpx.Response(200, json={'choices':[{'finish_reason':'stop', 'message':{'content':json.dumps(answer(empty='physical PDF page 2.' in payload['messages'][1]['content'][0]['text'])), 'reasoning_content':'DO NOT SAVE REASONING'}}]})
    original = httpx.Client
    monkeypatch.setattr(extract.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    assert extract.main([]) == 0
    monkeypatch.setattr(extract.httpx, 'Client', original)
    assert len(calls) == 2
    latest = tmp_path/'outputs/pdf_knowledge/latest'
    assert all('DO NOT SAVE REASONING' not in p.read_text() for p in latest.glob('*.json'))
    import backend.services.search.retrieval
    monkeypatch.setattr(backend.services.search.retrieval, 'Embedder', lambda *a, **k: FakeEmbedder())
    return settings, latest


def test_publish_s04_only_search_evidence_and_assets(prepared):
    settings, latest = prepared
    report = publish_extraction(settings, latest)
    assert report['pages'] == 2 and report['eligible_passages'] == 1 and report['eligible_methods'] == 0
    directory = active_directory(settings.corpus_dir)
    assert validate_corpus(directory, source_dir=settings.source_dir, deep=True)['status'] == 'passed'
    from backend.services.search.evidence import load_snapshot
    snapshot = load_snapshot(settings.corpus_dir)
    record = next(iter(snapshot.records.values()))
    assert record['content_kind'] == 'llm_knowledge' and not record['source_spans']
    assert record['knowledge']['category'] == 'new_model_category'
    assert snapshot.resolve(record['evidence_id']).human_review_status == 'not_reviewed'
    from backend.services.search.search_service import SearchService
    service = SearchService(settings)
    service.embedder = FakeEmbedder()
    response = service.compare('complementary signals', mode='qdrant')
    assert response['rankings']['qdrant'][0]['evidence']['evidence_id'] == record['evidence_id']
    assert 'Complementary spectroscopy signals.' in response['rankings']['qdrant'][0]['matching_segment']
    # Assessment must validate the same structured BM25 text used by publication.
    from backend.services.search.retrieval import CaseRetrievalService
    from backend.schemas.models import CaseFacts, MeasurementContext
    assessed = CaseRetrievalService(settings).retrieve_case(CaseFacts(contexts=[
        MeasurementContext(context_id="stream_1", label="complementary spectroscopy",
            measurement_goals=["complementary signals"])]))
    assert assessed.corpus_version == report["corpus_version"]

    async def requests():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings)), base_url='http://test') as client:
            data = (await client.get('/api/knowledge/inspection')).json()
            assert len(data['records']) == 1 and len(data['pages']) == 2
            prefix = data['artifact_base']
            assert (await client.get(prefix+data['pages'][1]['image'])).status_code == 200
            assert (await client.get(prefix+'source/S04.pdf')).headers['content-type'] == 'application/pdf'
            assert (await client.get(prefix+'source/S01.pdf')).status_code == 404
            assert (await client.get(prefix+'source_manifest.json')).status_code == 404
    asyncio.run(requests())
    # An incomplete attempt cannot change the active pointer.
    run = read_json(latest/'manifest.json'); run['status'] = 'failed'; write_json(latest/'manifest.json', run)
    with pytest.raises(ValueError, match='incomplete'):
        publish_extraction(settings, latest)
    assert active_directory(settings.corpus_dir) == directory


def test_rebuild_replaces_latest_qwen_generation_and_preserves_legacy(prepared):
    settings, latest = prepared
    publish_extraction(settings, latest)
    old = active_directory(settings.corpus_dir)
    legacy = settings.corpus_dir/'versions'/'legacy'; legacy.mkdir()
    write_json(legacy/'source_manifest.json', {'schema_version':'f02-v1'})
    page = read_json(latest/'sources/S04/unit_001.knowledge.json'); page['knowledge'][0]['claim'] = 'Changed synthetic claim.'
    write_json(latest/'sources/S04/unit_001.knowledge.json', page)
    publish_extraction(settings, latest)
    assert active_directory(settings.corpus_dir) != old and not old.exists() and legacy.exists()
    first = active_directory(settings.corpus_dir)
    # Identical publications are idempotent.
    publish_extraction(settings, latest)
    assert active_directory(settings.corpus_dir) == first


def test_all_formats_keep_source_locations_and_context_out_of_assessment(tmp_path, monkeypatch):
    import zipfile
    import openpyxl
    import backend.services.search.retrieval
    from backend.services.knowledge.knowledge_store import METHOD_COLUMNS, SOURCES
    from backend.pipelines.pdf_knowledge.inputs import prepare_inputs
    from backend.services.search.search_service import SearchService
    source_dir=tmp_path/'sources';source_dir.mkdir()
    for sid in ('S01','S02','S03','S04','S05'):
        with pymupdf.open() as doc:
            for number in range(6 if sid=='S01' else 1):
                page=doc.new_page();page.insert_text((40,60),f'{sid} synthetic source')
            doc.save(source_dir/SOURCES[sid][0])
    book=openpyxl.Workbook();sheet=book.active;sheet.title='method_comparison';sheet.append(METHOD_COLUMNS)
    for i in range(19): sheet.append([1,'IR spectroscopy',f'geometry {i}','absorption','liquid','1-6 um','average','high','high'])
    notes=book.create_sheet('notes')
    for i in range(7): notes.append([f'Source note {i}'])
    book.save(source_dir/SOURCES['T01'][0]);book.close()
    xml='''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Development example devonlytoken.</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Worked answer.</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''
    with zipfile.ZipFile(source_dir/SOURCES['D01_DOC'][0],'w') as z: z.writestr('word/document.xml',xml)
    settings=Settings(_env_file=None,source_dir=source_dir,corpus_dir=tmp_path/'knowledge',embedding_cache_dir=tmp_path/'models',dashscope_api_key='synthetic-key')
    latest=tmp_path/'latest'
    prepared_sources,units=prepare_inputs(settings,latest)
    assert len(prepared_sources)==7 and len([u for u in units if u['format']=='pdf'])==10
    document=next(u for u in units if u['source_id']=='D01_DOC')
    assert document['blocks'][0]['location']=='paragraph 1' and document['blocks'][1]['location']=='table 1, row 1'
    requests=[]
    def respond(request):
        payload=json.loads(request.content);requests.append(payload)
        content=payload['messages'][1]['content']
        data=answer()
        if content[0]['text'].startswith('Source: AFS_Examples'):
            data['knowledge'][0]['claim']='Development devonlytoken example.'
            data['knowledge'][0]['support_quote']='Development example devonlytoken.'
            assert len(content)==1 and 'Worked answer.' in content[0]['text']
        elif content[0]['text'].startswith('Source: AFS_method'):
            assert len(content)==1 and 'A1:' in content[0]['text']
        else:
            assert content[1]['type']=='image_url'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(data)}}]})
    original=httpx.Client
    with monkeypatch.context() as patch:
        patch.setattr(extract.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
        assert extract.extract_all(settings,latest,concurrency=2)==0
    total_calls=len(requests)
    with monkeypatch.context() as patch:
        patch.setattr(extract.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(lambda _:pytest.fail('Matched inputs must reuse cached answers')),**kwargs))
        assert extract.extract_all(settings,latest,concurrency=2)==0
    assert len(requests)==total_calls
    monkeypatch.setattr(backend.services.search.retrieval,'Embedder',lambda *a,**k:FakeEmbedder())
    report=publish_extraction(settings,latest)
    assert report['sources']==7 and report['pages']==10 and report['eligible_methods']==19
    directory=active_directory(settings.corpus_dir)
    from backend.services.search.evidence import load_snapshot
    snapshot=load_snapshot(settings.corpus_dir)
    assert {r['source_id'] for r in snapshot.records.values()}=={'S01','S02','S03','S04','T01'}
    methods=read_json(directory/'methods.json')
    assert len(methods)==19 and methods[0]['source_unit_id']=='T01:sheet:method_comparison'
    assert methods[0]['raw_values']['optical_path_or_depth']=='1-6 um'
    assert methods[0]['underlying_citation']['source_id']=='S01'
    assert len(read_json(directory/'method_notes.json'))==7
    service=SearchService(settings);service.embedder=FakeEmbedder()
    result=service.compare('devonlytoken',mode='bm25',dataset='inspection',source_id='D01_DOC')
    assert result['rankings']['bm25'][0]['evidence']['source_id']=='D01_DOC'
    assert not service.compare('devonlytoken',mode='bm25',dataset='technical')['rankings']['bm25']
    result=service.compare('synthetic probe',mode='qdrant',dataset='inspection',source_id='T01')
    assert result['rankings']['qdrant'] and all(h['evidence']['source_id']=='T01' for h in result['rankings']['qdrant'])
    async def office_api():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings)),base_url='http://test') as client:
            inspection=(await client.get('/api/knowledge/inspection')).json()
            assert {s['source_id'] for s in inspection['manifest']['sources']}==set(SOURCES)-{'S06'}
            prefix=inspection['artifact_base']
            for sid in ('T01','D01_DOC'):
                response=await client.get(prefix+f'source/{sid}/original')
                assert response.status_code==200 and 'attachment' in response.headers['content-disposition']
            response=await client.post('/api/search',json={'query':'devonlytoken','dataset':'inspection','mode':'bm25','source_id':'D01_DOC'})
            assert response.status_code==200 and response.json()['rankings']['bm25']
    asyncio.run(office_api())
