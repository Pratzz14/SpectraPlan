"""Direct Qwen3.8 Flash extraction from PDF images and Office source text."""

from backend.prompts import load_prompt
import argparse
import base64
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.core.config import PROJECT_ROOT, Settings
from backend.services.knowledge.knowledge_store import digest, inside, read_json, write_json, active_directory, load_records
from backend.pipelines.pdf_knowledge.inputs import prepare_inputs
from backend.pipelines.pdf_knowledge.quality import VERSION, QualityError, validate_answer
from backend.pipelines.pdf_knowledge.local_text import embedded_text, recover_text, text_passages

HERE = Path(__file__).resolve().parent
ROOT = PROJECT_ROOT


class OutputModel(BaseModel):
    model_config = ConfigDict(extra='ignore', strict=True)


class Quantity(OutputModel):
    value: str
    unit: str | None
    meaning: str


class Knowledge(OutputModel):
    category: str
    claim: str = Field(min_length=1)
    support_quote: str = Field(min_length=1)
    evidence_kind: str
    scope: str
    quantities: list[Quantity]
    relevance: str
    caveat: str | None

    @field_validator('claim','support_quote')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('Claim and supporting text must not be blank')
        return value


class PageKnowledge(OutputModel):
    page_title: str | None
    page_kind: str
    knowledge: list[Knowledge]
    unreadable_regions: list[str]
    page_limitations: list[str]


def parse_answer(answer):
    import re
    fenced = re.fullmatch(r'\s*```(?:json)?\s*\n(.*?)\n```\s*', answer, flags=re.DOTALL | re.IGNORECASE)
    return PageKnowledge.model_validate_json(fenced.group(1) if fenced else answer)


def response_schema():
    schema = PageKnowledge.model_json_schema()
    # Avoid regex constraints: structured decoders may treat patterns as full
    # strings. Readability is checked locally, beyond these length hints.
    for name in ('claim','support_quote'):
        schema['$defs']['Knowledge']['properties'][name]['minLength'] = 20
    return schema


def pipeline_fingerprint(settings):
    return {'model': settings.qwen_extraction_model, 'endpoint': settings.dashscope_base_url,
            'prompt_sha256': digest(load_prompt('knowledge_prompt.txt').encode()),
            'office_prompt_sha256': digest(load_prompt('knowledge_office_prompt.txt').encode()),
            'schema_sha256': digest(response_schema()),
            'quality_policy': VERSION, 'max_attempts': settings.knowledge_extraction_attempts,
            'ocr_language': settings.knowledge_ocr_language, 'ocr_tessdata': settings.knowledge_ocr_tessdata,
            'input_mode': 'pdf_images_and_office_text', 'validation_basis': 'readability_checks'}


def extract_all(settings, run_dir, *, source_ids=None, dpi=180, concurrency=2, refresh=False, prepare_only=False, on_progress=None):
    run_dir.mkdir(parents=True, exist_ok=True)
    previous = read_json(run_dir/'manifest.json') if (run_dir/'manifest.json').exists() else {}
    # Compatibility with the completed S04 experiment; retain those exact results.
    legacy = {}
    if previous.get('source_file') == 'S04_Combi_MIR_Fluorescence_2021.pdf' and previous.get('status') == 'completed_needs_visual_review':
        for p in previous['pages']:
            name = run_dir/f"page_{p['page']:03}.response.txt"
            if name.is_file():
                legacy[f"S04:p{p['page']}"] = (p, name.read_text(encoding='utf-8'))
    legacy_meta = previous
    if not legacy and (settings.corpus_dir/'current.json').is_file():
        directory = active_directory(settings.corpus_dir)
        manifest, published_records, _ = load_records(directory)
        if manifest.get('schema_version') == 'qwen-image-v1':
            source = manifest['sources'][0]
            legacy_meta = {'source_sha256':source['sha256'], **manifest['pipeline'], 'endpoint':settings.dashscope_base_url}
            for page in read_json(directory/'raw_pages.json'):
                raw = run_dir/f"page_{page['page']:03}.response.txt"
                if raw.is_file():
                    answer = raw.read_text(encoding='utf-8')
                    parsed = parse_answer(answer)
                    if [k.model_dump() for k in parsed.knowledge] == [r['knowledge'] for r in published_records if r['page']==page['page']]:
                        legacy[f"S04:p{page['page']}"] = (page,answer)
    sources, units = prepare_inputs(settings, run_dir, source_ids=source_ids, dpi=dpi)
    fingerprint = pipeline_fingerprint(settings)
    cached = {u['unit_id']: u for u in previous.get('units', [])}
    prompts = {'pdf': load_prompt('knowledge_prompt.txt'),
               'office': load_prompt('knowledge_office_prompt.txt')}
    write_json(run_dir/'schema.json', response_schema())
    for kind, text in prompts.items():
        (run_dir/f'{kind}_prompt.txt').write_text(text, encoding='utf-8')
    record = {'status': 'running', **fingerprint, 'sources': sources, 'units': units,
              'dpi': dpi, 'enable_thinking': True, 'max_tokens': 12000, 'production_corpus_modified': False}
    key = settings.dashscope_api_key.get_secret_value()
    lock = threading.Lock()
    unavailable = threading.Event()

    def save():
        record['updated_at'] = time.time()
        write_json(run_dir/'manifest.json', record)
        if on_progress:
            on_progress(record)

    def process(unit, client):
        started = time.monotonic()
        unit['result_file'] = f"sources/{unit['source_id']}/unit_{unit['page']:03}.knowledge.json"
        unit['response_file'] = f"sources/{unit['source_id']}/unit_{unit['page']:03}.response.txt"
        unit['request_fingerprint'] = digest([unit['source_sha256'],unit['input_sha256'],fingerprint,dpi,12000,True])
        unit['attempt_history'] = []
        unit['quality_policy'] = VERSION
        source_text = ''

        def accept(parsed, method='qwen', *, texts=None, warnings=None, cached=False):
            metadata={'method':method,'quality_policy':VERSION,'attempts':list(unit['attempt_history']),
                      'fallback_reason':unit.get('fallback_reason'),'warnings':warnings or []}
            value={**parsed.model_dump(),'_extraction':metadata}
            if texts is not None: value['source_texts']=texts
            write_json(inside(run_dir,unit['result_file']),value)
            unit.update(status='completed',extraction_method=method,knowledge_items=len(texts) if texts is not None else len(parsed.knowledge),
                        extraction_warnings=warnings or [],cached=cached)

        try:
            source_text=embedded_text(settings,unit,sources)
            old=cached.get(unit['unit_id'],{})
            matched=(old.get('source_sha256')==unit['source_sha256'] and old.get('input_sha256')==unit['input_sha256']
                     and all(previous.get(k)==fingerprint[k] for k in ('model','endpoint','prompt_sha256','office_prompt_sha256')))
            if not refresh and old.get('status')=='completed' and (matched or old.get('request_fingerprint')==unit['request_fingerprint']):
                try:
                    value=read_json(inside(run_dir,unit['result_file']))
                    meta=value.get('_extraction',{})
                    unit['attempt_history']=meta.get('attempts',[])
                    if meta.get('fallback_reason'):
                        unit['fallback_reason']=meta['fallback_reason']
                    if meta.get('method','qwen')=='qwen':
                        parsed=validate_answer(PageKnowledge.model_validate(value),source_text,check_quote=unit['format']!='pdf')
                        unit['origin_request_fingerprint']=old.get('request_fingerprint')
                        accept(parsed,cached=True)
                        return
                    if meta.get('method')!='unreadable' and meta.get('quality_policy')==VERSION and old.get('request_fingerprint')==unit['request_fingerprint']:
                        unit['attempt_history']=meta.get('attempts',[])
                        accept(PageKnowledge.model_validate(value),meta['method'],texts=value.get('source_texts',[]),warnings=meta.get('warnings',[]),cached=True)
                        return
                except (ValueError,KeyError,TypeError,OSError) as error:
                    unit['cache_rejected']=type(error).__name__
                unit['attempt_history']=[]
                unit.pop('fallback_reason',None)
            seed=legacy.get(unit['unit_id'])
            if not refresh and seed and legacy_meta.get('source_sha256')==unit['source_sha256'] and legacy_meta.get('prompt_sha256')==fingerprint['prompt_sha256'] and legacy_meta.get('model')==fingerprint['model'] and seed[0]['image_sha256']==unit.get('image_sha256'):
                try:
                    parsed=validate_answer(parse_answer(seed[1]),source_text,check_quote=unit['format']!='pdf')
                    accept(parsed,cached=True)
                    return
                except (ValueError,TypeError):
                    pass
            if prepare_only:
                unit['status']='prepared'
                return
            if unit['format']=='pdf':
                content=[{'type':'text','text':f"Extract useful knowledge from physical PDF page {unit['page']}. Return complete readable claims and supporting excerpts."},
                         {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(inside(run_dir,unit['image']).read_bytes()).decode()}}]
                system=prompts['pdf']
            else:
                content=[{'type':'text','text':f"Source: {unit['file_name']}\nLocation: {unit['label']}\n\n{unit['input_text']}"}]
                system=prompts['office']
            failure='Qwen credentials are unavailable' if not key else 'Qwen provider is unavailable'
            for attempt in range(1,settings.knowledge_extraction_attempts+1):
                if not key or unavailable.is_set(): break
                entry={'attempt':attempt,'status':'running'}
                unit['attempt_history'].append(entry)
                with lock: save()
                payload={'model':fingerprint['model'],'stream':False,'enable_thinking':False,'max_tokens':12000,
                         'response_format':{'type':'json_schema','json_schema':{'name':'PageKnowledge','strict':True,'schema':response_schema()}},
                         'messages':[{'role':'system','content':system+(load_prompt("knowledge_repair.txt").format(failure=failure) if attempt>1 else '')},
                                     {'role':'user','content':content}]}
                retryable=True
                delay=settings.knowledge_retry_delay_s*attempt
                try:
                    response=client.post(fingerprint['endpoint']+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload)
                    entry['http_status']=response.status_code
                    unit['http_status']=response.status_code
                    if response.status_code in {401,402,403,404}:
                        unavailable.set()
                    response.raise_for_status()
                    envelope=response.json()
                    if not isinstance(envelope,dict) or not isinstance(envelope.get('choices'),list) or not envelope['choices']:
                        raise QualityError('Missing model response choice')
                    choice=envelope['choices'][0]
                    if not isinstance(choice,dict) or not isinstance(choice.get('message'),dict) or not isinstance(choice['message'].get('content'),str):
                        raise QualityError('Missing model response text')
                    unit.update(returned_model=envelope.get('model'),usage=envelope.get('usage'),finish_reason=choice.get('finish_reason'))
                    answer=choice['message']['content']
                    inside(run_dir,unit['response_file']).write_text(answer,encoding='utf-8')
                    if choice.get('finish_reason')!='stop': raise QualityError('Incomplete model response')
                    parsed=validate_answer(parse_answer(answer),source_text,check_quote=unit['format']!='pdf')
                    if not parsed.knowledge and unit['format']=='pdf' and not source_text.strip() and parsed.page_kind.casefold() not in {'references','bibliography'}:
                        raise QualityError('Empty visual-page response requires local text recovery')
                    entry['status']='accepted'
                    accept(parsed)
                    return
                except httpx.HTTPStatusError as error:
                    status=error.response.status_code
                    failure=f'Qwen HTTP {status}'
                    retryable=status in {408,429} or status>=500
                    try: delay=min(10,max(delay,float(error.response.headers.get('retry-after',0))))
                    except ValueError: pass
                except (httpx.TransportError,ValueError,KeyError,TypeError) as error:
                    failure=str(error) if isinstance(error,QualityError) else type(error).__name__
                entry.update(status='rejected',reason=failure)
                if not retryable or attempt==settings.knowledge_extraction_attempts: break
                if delay: time.sleep(delay)
            unit['fallback_reason']=failure
            text,method,warnings=recover_text(settings,unit,sources,text=source_text)
            parsed=PageKnowledge(page_title=None,page_kind='other',knowledge=[],unreadable_regions=[],page_limitations=[])
            accept(parsed,method,texts=text_passages(text),warnings=warnings)
        except (OSError,ValueError,KeyError,TypeError,RuntimeError) as error:
            unit.update(status='failed',error_type=type(error).__name__)
        finally:
            unit['elapsed_s']=round(time.monotonic()-started,2)
            with lock:
                save()
                print(f"{unit['source_id']} {unit['label']}: {unit['status']} ({unit.get('knowledge_items',0)} records) [{unit.get('extraction_method','pending')}]",flush=True)

    save()
    with httpx.Client(timeout=240, follow_redirects=False) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(process, u, client) for u in units]
            for future in as_completed(futures):
                future.result()
    record['status'] = ('prepared' if prepare_only else 'completed_needs_visual_review') if all(u['status'] in {'completed','prepared'} for u in units) else 'failed'
    save()
    print(json.dumps({'status':record['status'], 'sources':len(sources), 'units':len(units),
                      'records':sum(u.get('knowledge_items',0) for u in units), 'failed':[u['unit_id'] for u in units if u['status']=='failed']}), flush=True)
    return int(record['status']=='failed')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', dest='source_ids', help='Source ID; repeat to select several. Default: all supported files.')
    parser.add_argument('--dpi', type=int, default=180)
    parser.add_argument('--concurrency', type=int, choices=range(1,5), default=2)
    parser.add_argument('--refresh', action='store_true', help='Replace even matching completed answers')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args(argv)
    if not 72 <= args.dpi <= 240:
        parser.error('dpi must be between 72 and 240')
    return extract_all(Settings(), ROOT/'outputs/pdf_knowledge/latest', source_ids=args.source_ids,
                       dpi=args.dpi, concurrency=args.concurrency, refresh=args.refresh, prepare_only=args.prepare_only)


if __name__ == '__main__':
    sys.exit(main())
