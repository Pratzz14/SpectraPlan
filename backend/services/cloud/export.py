"""Portable logical export of cloud working data and verified Storage bytes."""
import json
from datetime import datetime,timezone
from backend.services.knowledge.knowledge_store import write_json,inside,file_hash


def export_cloud(settings,database,storage,destination):
    destination.mkdir(parents=True,exist_ok=False)
    tables=('enquiries','explainability_runs','explainability_events','corpus_versions','active_corpora',
        'corpus_documents','evidence','source_revisions','source_locations','embedding_segments','corpus_files','app_state','ingestion_jobs','assessment_jobs','uploads')
    exported={}
    from psycopg import sql
    with database.connection() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        for name in tables:
            cursor=c.execute(sql.SQL('SELECT * FROM spectraplan.{}').format(sql.Identifier(name)))
            exported[name]=[dict(zip((col.name for col in cursor.description),row)) for row in cursor.fetchall()]
    # Includes jobs, checkpoints and immutable file references, not just active versions.
    references={}
    for row in exported['corpus_files']:
        reference=row['reference']
        references[(reference['bucket'],reference['key'])]=reference
    for row in exported['ingestion_jobs']:
        for reference in [row['input'],*(row.get('checkpoint') or {}).values()]:
            if 'bucket' in reference:
                references[(reference['bucket'],reference['key'])]=reference
    for (bucket,key),reference in references.items():
        path=inside(destination/'objects',bucket+'/'+key)
        path.parent.mkdir(parents=True,exist_ok=True)
        if reference.get('staged'):
            from urllib.parse import quote
            path.write_bytes(storage._request('GET','object/authenticated/'+quote(bucket,safe='')+'/'+quote(key,safe='/')).content)
        else:path.write_bytes(storage.get(reference))
    # Vector values serialize to their Postgres text representation; datetime fields use ISO 8601.
    payload=json.loads(json.dumps(exported,default=lambda v:v.isoformat() if hasattr(v,'isoformat') else str(v)))
    write_json(destination/'database.json',payload)
    files={p.relative_to(destination).as_posix():file_hash(p) for p in destination.rglob('*') if p.is_file()}
    write_json(destination/'manifest.json',{'format':'spectraplan-cloud-export-v1',
        'created_at':datetime.now(timezone.utc).isoformat(),'files':files})
