"""Quality checks, retries and real local text/OCR recovery without cloud calls."""
import json
from pathlib import Path
from pydantic import SecretStr

import httpx
import pymupdf
import pytest

from backend.config import Settings
from backend.knowledge_store import active_directory, read_json, load_records
from backend.pipelines.pdf_knowledge import extract
from backend.pipelines.pdf_knowledge.local_text import tessdata_directory, text_passages
from backend.pipelines.pdf_knowledge.store import publish_extraction
from backend.pipelines.pdf_knowledge.quality import QualityError, validate_answer
from tests.corpus_fixture import FakeEmbedder

TEXT='A multispectral probe measures fluorescence and infrared absorption in liquid samples. The measurements require calibration against a reference material before deployment.'


def answer(claim=TEXT,quote=TEXT):
    return {'page_title':'Spectroscopy study','page_kind':'research','knowledge':[{'category':'principle','claim':claim,'support_quote':quote,'evidence_kind':'body_text','scope':'own_study','quantities':[],'relevance':'Describes source measurements.','caveat':None}], 'unreadable_regions':[], 'page_limitations':[]}


@pytest.fixture
def settings(tmp_path,monkeypatch):
    source=tmp_path/'sources';source.mkdir()
    with pymupdf.open() as pdf:
        page=pdf.new_page();page.insert_textbox(pymupdf.Rect(40,40,500,300),TEXT,fontsize=13)
        pdf.save(source/'S04_Combi_MIR_Fluorescence_2021.pdf')
    import backend.retrieval
    monkeypatch.setattr(backend.retrieval,'Embedder',lambda *a,**k:FakeEmbedder())
    return Settings(_env_file=None,source_dir=source,corpus_dir=tmp_path/'knowledge',knowledge_work_dir=tmp_path/'work',embedding_cache_dir=tmp_path/'models',dashscope_api_key='synthetic-key',knowledge_retry_delay_s=0)


def run(settings,monkeypatch,responses):
    original=httpx.Client
    calls=[]
    def respond(request):
        payload=json.loads(request.content);calls.append(payload)
        data=responses[min(len(calls)-1,len(responses)-1)]
        if isinstance(data,int): return httpx.Response(data)
        content=data if isinstance(data,str) else json.dumps(data)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':content}}]})
    with monkeypatch.context() as patch:
        patch.setattr(extract.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
        assert extract.extract_all(settings,settings.knowledge_work_dir/'latest',concurrency=1)==0
    manifest=read_json(settings.knowledge_work_dir/'latest/manifest.json')
    result=read_json(settings.knowledge_work_dir/'latest'/manifest['units'][0]['result_file'])
    return manifest,result,calls


def test_output_schema_has_no_single_character_pattern_and_retry_recovers(settings,monkeypatch):
    manifest,result,calls=run(settings,monkeypatch,[answer('A','a'),answer()])
    assert len(calls)==2 and manifest['units'][0]['extraction_method']=='qwen'
    schema=calls[0]['response_format']['json_schema']['schema']['$defs']['Knowledge']['properties']
    assert 'pattern' not in schema['claim'] and schema['claim']['minLength']>=20
    assert result['knowledge'][0]['claim']==TEXT
    assert [a['status'] for a in result['_extraction']['attempts']]==['rejected','accepted']
    assert 'Previous response rejected' in calls[1]['messages'][0]['content']


def test_failed_retries_fall_back_to_embedded_text_and_index_it(settings,monkeypatch):
    manifest,result,calls=run(settings,monkeypatch,[503,'invalid JSON',answer('A','a')])
    assert len(calls)==3 and manifest['units'][0]['extraction_method']=='pymupdf_embedded'
    assert not result['knowledge'] and 'multispectral probe' in ' '.join(result['source_texts'])
    report=publish_extraction(settings,settings.knowledge_work_dir/'latest')
    assert report['fallback_units']==1 and not report['unreadable_units']
    directory=active_directory(settings.corpus_dir)
    _,records,_=load_records(directory)
    assert records[0]['content_kind']=='extracted_text' and 'knowledge' not in records[0]
    assert 'multispectral' in (directory/'bm25.json').read_text()
    assert records[0]['extraction_attempts']==3


def test_authentication_failure_does_not_retry_and_empty_output_is_rejected(settings,monkeypatch):
    manifest,result,calls=run(settings,monkeypatch,[401])
    assert len(calls)==1 and manifest['units'][0]['extraction_method']=='pymupdf_embedded'
    empty=answer();empty['knowledge']=[]
    settings=settings.model_copy(update={'knowledge_work_dir':settings.knowledge_work_dir.parent/'empty'})
    manifest,result,calls=run(settings,monkeypatch,[empty])
    assert len(calls)==3 and result['_extraction']['method']=='pymupdf_embedded'


def scanned(settings):
    target=settings.source_dir/'S04_Combi_MIR_Fluorescence_2021.pdf'
    with pymupdf.open() as original:
        page=original.new_page();page.insert_textbox(pymupdf.Rect(40,40,500,300),TEXT,fontsize=18)
        image=page.get_pixmap(dpi=150).tobytes('png')
    target.unlink()
    with pymupdf.open() as pdf:
        page=pdf.new_page();page.insert_image(page.rect,stream=image);pdf.save(target)
    return settings.model_copy(update={'dashscope_api_key':SecretStr('')})


def test_scanned_pdf_uses_actual_local_ocr_without_qwen(settings,monkeypatch):
    settings=scanned(settings)
    if not tessdata_directory(settings): pytest.skip('Local Tesseract language data unavailable')
    manifest,result,calls=run(settings,monkeypatch,[pytest.fail])
    assert not calls and result['_extraction']['method']=='pymupdf_ocr'
    assert 'spectral' in ' '.join(result['source_texts']).lower()
    assert publish_extraction(settings,settings.knowledge_work_dir/'latest')['fallback_units']==1


def test_unavailable_ocr_is_reported_instead_of_inventing_a_record(settings,monkeypatch):
    import backend.pipelines.pdf_knowledge.local_text as local
    monkeypatch.setattr(local,'tessdata_directory',lambda _:None)
    settings=scanned(settings)
    manifest,result,calls=run(settings,monkeypatch,[pytest.fail])
    assert not calls and not result['knowledge'] and not result['source_texts']
    assert result['_extraction']['method']=='unreadable' and result['_extraction']['warnings']
    report=publish_extraction(settings,settings.knowledge_work_dir/'latest')
    assert report['unreadable_units']==1 and report['passages']==0
    assert read_json(active_directory(settings.corpus_dir)/'raw_pages.json')[0]['extraction_warnings']


def test_text_splitting_keeps_short_tail_with_its_context():
    text=('Readable spectroscopy measurements require proper calibration. '*50)+'x'
    pieces=text_passages(text,size=300)
    assert ' '.join(' '.join(pieces).split())==' '.join(text.split())
    assert pieces[-1].endswith('x') and len(pieces[-1])>20


def test_visual_pdf_excerpts_need_not_exist_in_partial_embedded_text():
    parsed=extract.PageKnowledge.model_validate(answer(quote='Raman scattering provides molecular fingerprint spectra of process fluids.'))
    assert validate_answer(parsed,TEXT,check_quote=False) is parsed
    with pytest.raises(QualityError,match='does not match'):
        validate_answer(parsed,TEXT)


def test_cached_results_keep_retry_provenance(settings,monkeypatch):
    run(settings,monkeypatch,[503,answer()])
    manifest,result,calls=run(settings,monkeypatch,[pytest.fail])
    assert not calls and manifest['units'][0]['cached']
    assert [a['status'] for a in result['_extraction']['attempts']]==['rejected','accepted']


@pytest.mark.parametrize('envelope',[{}, {'choices':[]}, {'choices':[None]}, {'choices':[{'message':None}]}, {'choices':[{'message':{'content':None}}]}])
def test_malformed_response_envelope_retries_then_recovers(settings,monkeypatch,envelope):
    original=httpx.Client
    calls=[]
    def respond(request):
        calls.append(1)
        return httpx.Response(200,json=envelope)
    with monkeypatch.context() as patch:
        patch.setattr(extract.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
        assert extract.extract_all(settings,settings.knowledge_work_dir/'latest',concurrency=1)==0
    manifest=read_json(settings.knowledge_work_dir/'latest/manifest.json')
    assert len(calls)==3
    assert manifest['units'][0]['extraction_method']=='pymupdf_embedded'
