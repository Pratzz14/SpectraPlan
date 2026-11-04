"""Offline-source import, cloud verification and explicit corpus activation."""
import hashlib
import json
import sqlite3
from pathlib import Path
from backend.services.cloud.database import json_value
from backend.services.knowledge.knowledge_store import active_directory, read_json, inside, validate_corpus, digest, file_hash, write_json


def inventory(settings):
    """Only current working data and available published generations, never archives."""
    versions = []
    technical = active_directory(settings.corpus_dir)
    for directory in sorted((settings.corpus_dir/'versions').iterdir()):
        if (directory/'source_manifest.json').is_file():
            versions.append(('technical',directory))
    if not any(d==technical for _,d in versions):
        versions.append(('technical',technical))
    active = {'technical':read_json(technical/'source_manifest.json')['corpus_version']}
    if (settings.web_corpus_dir/'current.json').is_file():
        from backend.pipelines.website.ingest import web_directory
        website = web_directory(settings.web_corpus_dir)
        active['website'] = read_json(website/'manifest.json')['corpus_version']
        versions.extend(('website',d) for d in sorted((settings.web_corpus_dir/'versions').iterdir()) if (d/'manifest.json').is_file())
    return versions, active


def history_rows(path):
    if not path.is_file():
        return {name:[] for name in ('enquiries','explainability_runs','explainability_events')}
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as c:
        c.row_factory = sqlite3.Row
        result = {}
        for table in ('enquiries','explainability_runs','explainability_events'):
            result[table] = [dict(r) for r in c.execute('SELECT * FROM '+table)]
        return result


def prepare_generation(settings, dataset, directory, *, vectors=True):
    if dataset=='technical':
        report = validate_corpus(directory, source_dir=settings.source_dir, deep=True)
        manifest = read_json(directory/'source_manifest.json')
        records = [json.loads(line) for line in (directory/'passages.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        records += read_json(directory/'methods.json')
    else:
        from backend.pipelines.website.ingest import validate_web
        report = validate_web(directory)
        manifest, records = read_json(directory/'manifest.json'),read_json(directory/'records.json')
    documents, files = {}, {}
    for path in sorted(directory.rglob('*')):
        if not path.is_file() or 'qdrant' in path.relative_to(directory).parts:
            continue
        name = path.relative_to(directory).as_posix()
        if path.suffix in {'.json','.jsonl'}:
            body = path.read_bytes().decode('utf-8')
            documents[name] = body
        else:
            files[name] = path
    if dataset=='technical':
        for source in manifest['sources']:
            files['originals/'+source['source_id']+'/'+source['file_name']] = inside(settings.source_dir,source.get('file_path',source['file_name']))
    # Preserve every source byte and renderer checkpoint, not local vector binaries.
    result = {'version':manifest['corpus_version'],'dataset':dataset,'manifest':manifest,
        'documents':documents,'files':files,'records':records,'report':report,'vectors':[]}
    if vectors:
        from qdrant_client import QdrantClient
        from backend.services.search.retrieval import COLLECTION
        purposes = [('technical',directory)]
        if (directory/'inspection/index_manifest.json').is_file():
            purposes.append(('inspection',directory/'inspection'))
        for purpose,index_dir in purposes:
            segments = {s['id']:s for s in read_json(index_dir/'segments.json')}
            client = QdrantClient(path=str(index_dir/'qdrant'))
            seen = set()
            try:
                offset = None
                while True:
                    points,offset = client.scroll(COLLECTION,limit=128,offset=offset,with_vectors=True,with_payload=True)
                    for point in points:
                        sid = str(point.id)
                        segment = segments[sid]
                        if point.payload['evidence_id'] != segment['evidence_id'] or len(point.vector)!=384:
                            raise ValueError('Vector membership or dimensions differ from source segments')
                        seen.add(sid)
                        result['vectors'].append((purpose,sid,segment['evidence_id'],segment['text'],point.vector))
                    if offset is None:
                        break
            finally:
                client.close()
            if seen != set(segments):
                raise ValueError('Vector index is incomplete')
    result['digest'] = digest({'documents':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in documents.items()},
        'files':{k:file_hash(v) for k,v in files.items()},'vectors':sorted(result['vectors'])})
    return result


def import_generation(database, storage, generation):
    version = generation['version']
    refs = {name:storage.put(path.read_bytes(),source=name.startswith('originals/'),filename=path.name)
            for name,path in generation['files'].items()}
    with database.connection() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",('spectraplan:corpus:'+version,))
        existing = c.execute('SELECT digest FROM spectraplan.corpus_versions WHERE version=%s',(version,)).fetchone()
        if existing:
            if existing[0] != generation['digest']:
                raise ValueError('Published version conflicts with existing cloud content')
            return version
        c.execute('INSERT INTO spectraplan.corpus_versions(version,dataset,manifest,digest) VALUES (%s,%s,%s,%s)',
            (version,generation['dataset'],json_value(generation['manifest']),generation['digest']))
        for name,body in generation['documents'].items():
            c.execute('INSERT INTO spectraplan.corpus_documents VALUES (%s,%s,%s,%s)',
                (version,name,body,hashlib.sha256(body.encode()).hexdigest()))
        for record in generation['records']:
            c.execute('INSERT INTO spectraplan.evidence VALUES (%s,%s,%s)',(version,record['evidence_id'],json_value(record)))
        for source in generation['manifest'].get('sources',[]):
            c.execute('INSERT INTO spectraplan.source_revisions VALUES (%s,%s,%s)',(version,source['source_id'],json_value(source)))
        if generation['dataset']=='technical':
            for page in json.loads(generation['documents']['raw_pages.json']):
                c.execute('INSERT INTO spectraplan.source_locations VALUES (%s,%s,%s)',
                    (version,page.get('unit_id',f"{page['source_id']}:p{page['page']}"),json_value(page)))
        for purpose,sid,eid,text,vector in generation['vectors']:
            c.execute('INSERT INTO spectraplan.embedding_segments VALUES (%s,%s,%s,%s,%s,%s::extensions.vector)',
                (version,purpose,sid,eid,text,'['+','.join(map(str,vector))+']'))
        for name,reference in refs.items():
            c.execute('INSERT INTO spectraplan.corpus_files VALUES (%s,%s,%s)',(version,name,json_value(reference)))
    return version


def verify_generation(database, storage, generation):
    version = generation['version']
    with database.connection() as c:
        identity=c.execute('SELECT digest,manifest FROM spectraplan.corpus_versions WHERE version=%s',(version,)).fetchone()
        if not identity or identity!=(generation['digest'],generation['manifest']):
            raise ValueError('Cloud corpus identity differs from local source')
        actual = dict(c.execute('SELECT path,body FROM spectraplan.corpus_documents WHERE version=%s',(version,)).fetchall())
        if actual != generation['documents']:
            raise ValueError('Cloud corpus documents differ from local source')
        records = dict(c.execute('SELECT evidence_id,payload FROM spectraplan.evidence WHERE version=%s',(version,)).fetchall())
        if records != {r['evidence_id']:r for r in generation['records']}:
            raise ValueError('Cloud evidence differs from local source')
        sources=dict(c.execute('SELECT source_id,payload FROM spectraplan.source_revisions WHERE version=%s',(version,)).fetchall())
        if sources!={s['source_id']:s for s in generation['manifest'].get('sources',[])}:
            raise ValueError('Cloud source revisions differ from source')
        refs = dict(c.execute('SELECT path,reference FROM spectraplan.corpus_files WHERE version=%s',(version,)).fetchall())
        if set(refs) != set(generation['files']):
            raise ValueError('Cloud file membership differs from local source')
        vectors = {(p,s):(e,t,json.loads(v)) for p,s,e,t,v in c.execute(
            'SELECT purpose,segment_id,evidence_id,text,embedding::text FROM spectraplan.embedding_segments WHERE version=%s',(version,)).fetchall()}
    if len(vectors)!=len(generation['vectors']):
        raise ValueError('Cloud vector count differs from local source')
    for purpose,sid,eid,text,vector in generation['vectors']:
        actual = vectors.get((purpose,sid))
        if actual is None or actual[:2]!=(eid,text) or max(abs(a-b) for a,b in zip(vector,actual[2],strict=True))>1e-6:
            raise ValueError('Cloud vector content differs from source')
    for name,reference in refs.items():
        if hashlib.sha256(storage.get(reference)).hexdigest()!=file_hash(generation['files'][name]):
            raise ValueError('Cloud file differs from local source')
    with database.connection() as c:
        c.execute('UPDATE spectraplan.corpus_versions SET ready=true WHERE version=%s',(version,))
    return {'version':version,'records':len(records),'vectors':len(vectors),'files':len(refs),'verified':True}


def activate(database, active, *, initial=False):
    with database.connection() as c:
        if initial and c.execute("SELECT 1 FROM spectraplan.app_state WHERE key='initial_migration_complete'").fetchone():
            current=dict(c.execute('SELECT dataset,version FROM spectraplan.active_corpora').fetchall())
            if current!=active:
                raise ValueError('Cloud knowledge changed after cutover; refusing to reactivate an old local snapshot')
        for dataset,version in active.items():
            row=c.execute('SELECT ready FROM spectraplan.corpus_versions WHERE version=%s AND dataset=%s FOR SHARE',(version,dataset)).fetchone()
            if not row or not row[0]:
                raise ValueError('Only verified versions can be activated')
            c.execute('INSERT INTO spectraplan.active_corpora VALUES (%s,%s) ON CONFLICT(dataset) DO UPDATE SET version=excluded.version',(dataset,version))
        if initial:
            c.execute("INSERT INTO spectraplan.app_state VALUES ('initial_migration_complete',%s) ON CONFLICT(key) DO NOTHING",(json_value(active),))


def import_history(database, rows):
    with database.connection() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('spectraplan:history-import'))")
        for table in ('enquiries','explainability_runs','explainability_events'):
            pending=list(rows[table])
            if table=='explainability_runs':
                # Ancestors must precede child rows even for a nonchronological SQLite scan.
                ordered=[]
                while pending:
                    ready=[r for r in pending if not r.get('parent_run_id') or r['parent_run_id'] in {v['run_id'] for v in ordered}]
                    if not ready:
                        raise ValueError('History contains a missing or cyclic parent reference')
                    ordered.extend(ready)
                    pending=[r for r in pending if r not in ready]
                pending=ordered
            for row in pending:
                values=dict(row)
                for key in ('run_json','clarification_answers','payload_json'):
                    if key in values:
                        values[key]=json_value(json.loads(values[key]))
                # Source-generated identifiers only; no caller-supplied SQL identifiers.
                columns=list(values)
                from psycopg import sql
                query=sql.SQL('INSERT INTO spectraplan.{} ({}) VALUES ({}) ON CONFLICT DO NOTHING').format(
                    sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for _ in columns))
                c.execute(query,list(values.values()))


def verify_history(database, rows):
    with database.connection() as c:
        for table in ('enquiries','explainability_runs','explainability_events'):
            from psycopg import sql
            cursor=c.execute(sql.SQL('SELECT * FROM spectraplan.{}').format(sql.Identifier(table)))
            actual=[dict(zip((col.name for col in cursor.description),r)) for r in cursor.fetchall()]
            keys=('run_id','sequence') if table=='explainability_events' else ('enquiry_id',) if table=='enquiries' else ('run_id',)
            indexed={tuple(r[k] for k in keys):r for r in actual}
            for source in rows[table]:
                target=indexed.get(tuple(source[k] for k in keys))
                for key,value in source.items():
                    if key in ('run_json','clarification_answers','payload_json'):
                        value=json.loads(value)
                    if target is None or target.get(key)!=value:
                        raise ValueError('Imported history conflicts with local source')
    return {t:len(r) for t,r in rows.items()}


def backup(settings, destination):
    destination.mkdir(parents=True,exist_ok=False)
    if settings.explainability_db_path.is_file():
        with sqlite3.connect(settings.explainability_db_path.resolve().as_uri()+'?mode=ro',uri=True) as source:
            with sqlite3.connect(destination/'history.sqlite') as target:
                source.backup(target)
    import shutil
    shutil.copytree(settings.corpus_dir,destination/'knowledge')
    write_json(destination/'receipt.json',{'created_from':'local working data','archives_included':False})
