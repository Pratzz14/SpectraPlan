"""Publish image-derived knowledge with format and provenance checks only."""
import json
import shutil
from pathlib import Path

from backend.schemas.knowledge_models import Evidence
from backend.services.knowledge.knowledge_store import digest, file_hash, inside, load_records, read_json, write_json

SCHEMA = "qwen-image-v1"


def validate_v1(directory: Path, *, source_dir=None, deep=False):
    manifest, records, methods = load_records(directory)
    sources = {s["source_id"]: s for s in manifest["sources"]}
    if set(sources) != {"S04"} or methods or read_json(directory / "method_notes.json"):
        raise ValueError("Image corpus must contain S04 only")
    source = sources["S04"]
    pages = read_json(directory / "raw_pages.json")
    expected = set(range(1, source["page_count"] + 1))
    if (len(pages) != len(expected) or {p["page"] for p in pages} != expected
            or any(p["source_id"] != "S04" for p in pages)
            or {p["page"] for p in manifest["coverage"]} != expected
            or any(p["status"] != "completed" for p in manifest["coverage"])):
        raise ValueError("Incomplete source page coverage")
    ids = set()
    for record in records:
        Evidence.model_validate(record)
        if (record["evidence_id"] in ids or record["source_id"] != "S04"
                or record["source_sha256"] != source["sha256"]
                or record["file_name"] != source["file_name"] or record["page"] not in expected
                or record["content_kind"] != "llm_knowledge"
                or record["validation_basis"] != "basic_format"
                or record["text"] != record["knowledge"]["support_quote"]):
            raise ValueError("Invalid knowledge provenance")
        ids.add(record["evidence_id"])
    if not ids:
        raise ValueError("No extracted knowledge to publish")
    for name, checksum in manifest["artifacts"].items():
        if file_hash(inside(directory, name)) != checksum:
            raise ValueError(f"Artifact changed: {name}")
    index = read_json(directory / "index_manifest.json")
    segments = read_json(directory / "segments.json")
    lexical = read_json(directory / "bm25.json")
    eligible = {r["evidence_id"] for r in records if r["retrieval_eligible"]}
    if (index["corpus_version"] != manifest["corpus_version"]
            or lexical["corpus_version"] != manifest["corpus_version"]
            or {s["evidence_id"] for s in segments} != eligible
            or {d["evidence_id"] for d in lexical["documents"]} != eligible
            or index["segment_count"] != len(segments)):
        raise ValueError("Index membership/version mismatch")
    if deep:
        for page in pages:
            if file_hash(inside(directory, page["image"])) != page["image_sha256"]:
                raise ValueError("Source page image changed")
        for name, checksum in index["qdrant_files"].items():
            if file_hash(inside(directory, name)) != checksum:
                raise ValueError("Vector index changed")
    if source_dir and file_hash(source_dir / source["file_name"]) != source["sha256"]:
        raise ValueError("Original source changed")
    return {"status": "passed", "validation_basis": "basic_format", "corpus_version": manifest["corpus_version"],
            "pages": len(pages), "passages": len(records), "eligible_passages": len(eligible),
            "eligible_methods": 0, "flagged": 0, "human_verified": 0}



SCHEMA_V2 = 'qwen-sources-v2'


def validate(directory: Path, *, source_dir=None, deep=False):
    manifest, records, methods = load_records(directory)
    if manifest.get('schema_version') == SCHEMA:
        return validate_v1(directory, source_dir=source_dir, deep=deep)
    sources = {s['source_id']:s for s in manifest['sources']}
    if len(sources) != len(manifest['sources']):
        raise ValueError('Duplicate source IDs')
    pages = read_json(directory/'raw_pages.json')
    units = {p['unit_id']:p for p in pages}
    coverage = manifest['coverage']
    if (len(units)!=len(pages) or {c['unit_id'] for c in coverage}!=set(units)
            or len(coverage)!=len(units) or any(c['status']!='completed' for c in coverage)):
        raise ValueError('Incomplete source coverage')
    for sid, source in sources.items():
        members = [p for p in pages if p['source_id']==sid]
        if len(members)!=source['unit_count'] or not members:
            raise ValueError('Source units missing')
        if source['format']=='pdf' and {p['page'] for p in members}!=set(range(1,source['page_count']+1)):
            raise ValueError('Incomplete PDF page coverage')
        if source_dir and file_hash(inside(source_dir,source.get('file_path',source['file_name'])))!=source['sha256']:
            raise ValueError('Original source changed')
    all_records = records+methods
    ids = set()
    from backend.pipelines.pdf_knowledge.extract import Knowledge
    for record in all_records:
        Evidence.model_validate(record)
        source = sources[record['source_id']]
        if (record['evidence_id'] in ids or record['source_sha256']!=source['sha256']
                or record['file_name']!=source['file_name'] or record['source_unit_id'] not in units
                or units[record['source_unit_id']]['source_id']!=record['source_id']):
            raise ValueError('Invalid source reference')
        if record['retrieval_eligible'] and not source['technical_eligible']:
            raise ValueError('Context source cannot enter assessment retrieval')
        if record['content_kind']=='llm_knowledge':
            item=Knowledge.model_validate(record['knowledge'])
            if manifest.get('pipeline',{}).get('quality_policy'):
                from backend.pipelines.pdf_knowledge.quality import validate_answer
                from backend.pipelines.pdf_knowledge.extract import PageKnowledge
                validate_answer(PageKnowledge(page_title=None,page_kind='other',knowledge=[item],unreadable_regions=[],page_limitations=[]))
            if record['text']!=record['knowledge']['support_quote']:
                raise ValueError('Supporting text differs from model output')
        elif record['content_kind']=='extracted_text':
            from backend.pipelines.pdf_knowledge.quality import readable
            if not readable(record['text']) or record.get('knowledge'):
                raise ValueError('Invalid local source-text record')
        elif record['content_kind']!='method_row':
            raise ValueError('Unexpected record type')
        ids.add(record['evidence_id'])
    for name, checksum in manifest['artifacts'].items():
        if file_hash(inside(directory,name))!=checksum:
            raise ValueError(f'Artifact changed: {name}')
    for folder,expected in ((directory,{r['evidence_id'] for r in all_records if r['retrieval_eligible']}),
                            (directory/'inspection',{r['evidence_id'] for r in all_records if r.get('search_eligible',True)})):
        index = read_json(folder/'index_manifest.json')
        segments = read_json(folder/'segments.json')
        lexical = read_json(folder/'bm25.json')
        if (index['corpus_version']!=manifest['corpus_version'] or lexical['corpus_version']!=manifest['corpus_version']
                or {s['evidence_id'] for s in segments}!=expected
                or {d['evidence_id'] for d in lexical['documents']}!=expected or index['segment_count']!=len(segments)):
            raise ValueError('Index membership/version mismatch')
        if deep:
            for name,checksum in index['qdrant_files'].items():
                if file_hash(inside(folder,name))!=checksum:
                    raise ValueError('Vector index changed')
    if deep:
        for unit in pages:
            if unit.get('image') and file_hash(inside(directory,unit['image']))!=unit['image_sha256']:
                raise ValueError('Source page image changed')
    return {'status':'passed','validation_basis':manifest.get('pipeline',{}).get('validation_basis','basic_format'),'corpus_version':manifest['corpus_version'],
            'sources':len(sources),'pages':sum(s.get('page_count') or 0 for s in sources.values()),'source_units':len(units),
            'passages':len(records),'eligible_passages':sum(r['retrieval_eligible'] for r in records),
            'eligible_methods':sum(r['retrieval_eligible'] for r in methods),'flagged':0,'human_verified':0,
            'fallback_units':sum(p.get('extraction_method') in {'pymupdf_embedded','pymupdf_ocr','office_text'} for p in pages),
            'unreadable_units':sum(p.get('extraction_method')=='unreadable' for p in pages)}


def workbook_records(source, units, sources):
    """Preserve every source row and all notes independently of model summaries."""
    from backend.services.knowledge.knowledge_store import METHOD_COLUMNS
    by_sheet = {u['sheet']:u for u in units if u['source_id']==source['source_id'] and 'sheet' in u}
    notes_unit = by_sheet.get('notes')
    notes = [{'source_id':source['source_id'],'sheet':'notes','row':row['row'],
              'text':' '.join(str(c['value']) for c in row['cells'])} for row in (notes_unit or {}).get('rows',[])]
    unit = by_sheet.get('method_comparison')
    methods = []
    if not unit:
        return methods,notes
    for row in unit['rows']:
        if row['row']==1:
            continue
        cells = {c['cell'].rstrip('0123456789'):c['value'] for c in row['cells']}
        raw = {column:cells.get(chr(65+i)) for i,column in enumerate(METHOD_COLUMNS)}
        text = '\n'.join(f'{key}: {value}' for key,value in raw.items())
        identity = digest([source['sha256'],row['row'],raw])
        record = {'evidence_id':f"T01:method_comparison:r{row['row']:03}",'source_id':'T01','file_name':source['file_name'],
                  'source_sha256':source['sha256'],'page':None,'sheet':'method_comparison','row':row['row'],
                  'source_unit_id':unit['unit_id'],'source_location':f"method_comparison row {row['row']}",
                  'section':f"{raw['method']} · {raw['measurement_technique']}",'text':text,'content_kind':'method_row',
                  'evidence_scope':'general_method','revision':identity,'validation_status':'passed',
                  'validation_basis':'source_cells','human_review_status':'not_reviewed','retrieval_eligible':True,
                  'search_eligible':True,'issues':[],'method':raw['method'],'geometry':raw['measurement_technique'],
                  'raw_values':raw,'source_spans':[],'region':None}
        s01 = next((s for s in sources if s['source_id']=='S01'),None)
        if s01:
            record['underlying_citation'] = {'source_id':'S01','page':6,'table':'Table 1','sha256':s01['sha256']}
        methods.append(record)
    return methods,notes


def publish_extraction(settings, run_dir: Path, *, merge=False):
    from backend.services.knowledge.knowledge_report import render_report
    from backend.services.knowledge.knowledge_store import publish
    from backend.pipelines.pdf_knowledge.extract import PageKnowledge
    from backend.services.search.retrieval import Embedder, build_indexes, SEARCH_LOCK

    run = read_json(run_dir/'manifest.json')
    if run['status']!='completed_needs_visual_review' or any(u['status']!='completed' for u in run['units']):
        raise ValueError('Extraction is incomplete; active corpus was preserved')
    sources = [dict(s) for s in run['sources']]
    for source in sources:
        if file_hash(inside(settings.source_dir,source.get('file_path',source['file_name'])))!=source['sha256']:
            raise ValueError('Original source changed')
    root = settings.corpus_dir
    staged = root/'.staging/pdf-knowledge-latest'
    if staged.exists():
        shutil.rmtree(inside(root,'.staging/pdf-knowledge-latest'))
    staged.mkdir(parents=True)
    (staged/'assets').mkdir()
    pages,records,coverage,methods,notes = [],[],[],[],[]
    by_source = {s['source_id']:s for s in sources}
    for unit in run['units']:
        sid,number = unit['source_id'],unit['page']
        source = by_source[sid]
        raw_result=read_json(inside(run_dir,unit['result_file']))
        result=PageKnowledge.model_validate(raw_result)
        metadata=raw_result.get('_extraction',{})
        method=metadata.get('method','qwen')
        if method=='qwen':
            from backend.pipelines.pdf_knowledge.quality import validate_answer
            validate_answer(result)
        attempts=len(metadata.get('attempts',[]))
        page = {k:unit[k] for k in ('unit_id','source_id','page','label','format','width','height','blocks','image')}
        for k in ('rows','sheet'):
            if k in unit: page[k]=unit[k]
        if unit['image']:
            image = f'assets/{sid}-p{number:03}.png'
            input_image = inside(run_dir,unit['image'])
            if file_hash(input_image)!=unit['image_sha256']:
                raise ValueError('Rendered input changed')
            shutil.copyfile(input_image,staged/image)
            page.update(image=image,image_sha256=unit['image_sha256'])
        page.update(page_title=result.page_title,page_kind=result.page_kind,
                    unreadable_regions=result.unreadable_regions,page_limitations=result.page_limitations)
        page.update(extraction_method=method,extraction_attempts=attempts,
                    extraction_warnings=metadata.get('warnings',[]),fallback_reason=metadata.get('fallback_reason'))
        if method in {'pymupdf_embedded','pymupdf_ocr'}:
            page['blocks']=[{'text':text,'location':unit['label']} for text in raw_result.get('source_texts',[])]
        pages.append(page)
        scope = {'research':'research_demonstration','business':'business_context','development':'development_example'}.get(source['role'],'general_method')
        for i,item in enumerate(result.knowledge):
            knowledge = item.model_dump(); identity = digest([source['sha256'],unit['unit_id'],i,knowledge])
            records.append({'evidence_id':f'{sid}:u{number}:qwen:{identity[:16]}','source_id':sid,'file_name':source['file_name'],
                'source_sha256':source['sha256'],'page':number if unit['format']=='pdf' else None,
                'source_unit_id':unit['unit_id'],'source_location':unit['label'],
                'section':result.page_title or unit['label'],'text':item.support_quote,'content_kind':'llm_knowledge',
                'evidence_scope':scope,'revision':identity,'validation_status':'passed','validation_basis':'readability_checks',
                'human_review_status':'not_reviewed','retrieval_eligible':source['technical_eligible'],'search_eligible':True,
                'issues':[],'source_spans':[],'region':None,'knowledge':knowledge,'facts':[],
                'extraction_model':run['model'],'reference':unit['reference'],'extraction_method':'qwen','extraction_attempts':attempts})
        if method!='qwen':
            from backend.pipelines.pdf_knowledge.quality import readable
            for i,text in enumerate(raw_result.get('source_texts',[])):
                if not readable(text):
                    raise ValueError('Fallback text is too short or unreadable')
                identity=digest([source['sha256'],unit['unit_id'],method,i,text])
                records.append({'evidence_id':f'{sid}:u{number}:text:{identity[:16]}','source_id':sid,'file_name':source['file_name'],
                    'source_sha256':source['sha256'],'page':number if unit['format']=='pdf' else None,
                    'source_unit_id':unit['unit_id'],'source_location':unit['label'],
                    'section':f"{unit['label']} · extracted text {i+1}",'text':text,'content_kind':'extracted_text',
                    'evidence_scope':scope,'revision':identity,'validation_status':'passed','validation_basis':'source_text_checks',
                    'human_review_status':'not_reviewed','retrieval_eligible':source['technical_eligible'],'search_eligible':True,
                    'issues':[],'source_spans':[],'region':None,'facts':[],'reference':unit['reference'],
                    'extraction_method':method,'extraction_attempts':attempts,'fallback_reason':metadata.get('fallback_reason')})
        coverage.append({'source_id':sid,'unit_id':unit['unit_id'],'page':number if unit['format']=='pdf' else None,
                         'location':unit['label'],'status':'completed','records':unit.get('knowledge_items',len(result.knowledge)), 'extraction_method':method})
    if 'T01' in by_source:
        methods,notes = workbook_records(by_source['T01'],run['units'],sources)
    if merge and (root/'current.json').is_file():
        from backend.services.knowledge.knowledge_store import active_directory, validate_corpus
        old_directory=active_directory(root)
        validate_corpus(old_directory)
        validate_corpus_old=read_json(old_directory/'source_manifest.json')
        if validate_corpus_old.get('schema_version') not in {SCHEMA,SCHEMA_V2}:
            raise ValueError('Rebuild the historical corpus with the current pipeline before adding files')
        old_manifest,old_records,old_methods=load_records(old_directory)
        replacing=set(by_source)
        retained=[s for s in old_manifest['sources'] if s['source_id'] not in replacing]
        for old_source in retained:
            source=dict(old_source)
            source.setdefault('format','pdf')
            source_pages=[p for p in read_json(old_directory/'raw_pages.json') if p['source_id']==source['source_id']]
            source['unit_count']=len(source_pages)
            sources.append(source)
            for original_page in source_pages:
                page=dict(original_page)
                page.setdefault('unit_id',f"{source['source_id']}:p{page['page']}")
                page.setdefault('label',f"Page {page['page']}")
                page.setdefault('format',source['format'])
                if page.get('image'):
                    destination=inside(staged,page['image']);destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(inside(old_directory,page['image']),destination)
                pages.append(page)
                coverage.append({'source_id':source['source_id'],'unit_id':page['unit_id'],'page':page['page'] if page['format']=='pdf' else None,
                                 'location':page['label'],'status':'completed','records':sum(r.get('source_unit_id',f"{r['source_id']}:p{r['page']}")==page['unit_id'] for r in old_records)})
        for old,collection in ((old_records,records),(old_methods,methods)):
            for original in old:
                if original['source_id'] not in replacing:
                    record=dict(original)
                    record.setdefault('source_unit_id',f"{record['source_id']}:p{record['page']}")
                    record.setdefault('source_location',f"Page {record['page']}")
                    record.setdefault('search_eligible',True)
                    collection.append(record)
        if 'T01' not in replacing:
            notes.extend(read_json(old_directory/'method_notes.json'))
    embedder = Embedder(settings.embedding_cache_dir,local_only=True)
    version = 'corpus-'+digest([SCHEMA_V2,run['prompt_sha256'],run['office_prompt_sha256'],run['schema_sha256'],
        records,methods,notes,pages,embedder.fingerprint,file_hash(Path(__file__).resolve().parents[2]/'templates'/'knowledge_report.html')])[:20]
    manifest = {'schema_version':SCHEMA_V2,'corpus_version':version,'sources':sources,'coverage':coverage,
                'pipeline':{k:run[k] for k in ('model','input_mode','validation_basis','prompt_sha256','office_prompt_sha256','schema_sha256')},'artifacts':{}}
    manifest['pipeline']['quality_policy']=run.get('quality_policy','readable-source-v1')
    (staged/'passages.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    for name,value in (('methods.json',methods),('method_notes.json',notes),('raw_pages.json',pages),('source_manifest.json',manifest)):
        write_json(staged/name,value)
    build_indexes(staged,records+methods,version,embedder,allow_empty=True)
    inspection=staged/'inspection';inspection.mkdir()
    build_indexes(inspection,[{**r,'retrieval_eligible':True} for r in records+methods if r.get('search_eligible',True)],version,embedder,allow_empty=True)
    render_report(staged)
    names=['passages.jsonl','methods.json','method_notes.json','raw_pages.json','segments.json','bm25.json','index_manifest.json','review.html',
           'inspection/segments.json','inspection/bm25.json','inspection/index_manifest.json']
    manifest['artifacts']={name:file_hash(staged/name) for name in names}
    write_json(staged/'source_manifest.json',manifest)
    report=validate(staged,source_dir=settings.source_dir,deep=True)
    write_json(staged/'validation_report.json',report)
    manifest['artifacts']['validation_report.json']=file_hash(staged/'validation_report.json')
    write_json(staged/'source_manifest.json',manifest)
    with SEARCH_LOCK:
        final=publish(root,staged,manifest)
        for previous in (root/'versions').iterdir():
            if previous!=final and previous.is_dir() and (previous/'source_manifest.json').is_file():
                if read_json(previous/'source_manifest.json').get('schema_version') in {SCHEMA,SCHEMA_V2}:
                    shutil.rmtree(inside(root,previous.relative_to(root).as_posix()))
    run.update(production_corpus_modified=True,published_version=version)
    write_json(run_dir/'manifest.json',run)
    return report
