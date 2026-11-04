"""Read-only cloud API/retrieval check. No model calls or business-data writes."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from backend.core.config import Settings
from backend.services.cloud.database import Database
from backend.services.cloud.storage import ArtifactStorage
from backend.services.cloud.knowledge import CloudKnowledge
from backend.services.search.search_service import SearchService
from backend.services.search.retrieval import CaseRetrievalService,Embedder
from backend.schemas.models import CaseFacts,MeasurementContext
from backend.services.knowledge.knowledge_store import write_json


def run(settings,compare_local=False):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.api.auth import Identity,get_current_user
    with TemporaryDirectory(prefix='spectraplan-cloud-smoke-') as temporary:
        root=Path(temporary)
        isolated=settings.model_copy(update={'storage_backend':'supabase','cloud_cache_dir':root/'cache',
            'corpus_dir':root/'absent-corpus','source_dir':root/'absent-originals','web_corpus_dir':root/'absent-website',
            'explainability_db_path':root/'absent-history.sqlite'})
        database=Database(isolated)
        storage=ArtifactStorage(isolated)
        repository=CloudKnowledge(isolated,database,storage)
        try:
            embedder=Embedder(settings.embedding_cache_dir,local_only=True)
            remote=SearchService(isolated,repository=repository);remote.embedder=embedder
            baseline=SearchService(settings);baseline.embedder=embedder
            comparisons=[]
            for dataset in ('technical','inspection','website','all'):
                for query in ('powder moisture','fluorescence infrared probe','Raman pharmaceutical analysis'):
                    result=remote.compare(query,dataset=dataset,mode='compare')
                    if compare_local:
                        expected=baseline.compare(query,dataset=dataset,mode='compare')
                        for branch in ('bm25','qdrant','hybrid'):
                            actual_rows=result['rankings'][branch];expected_rows=expected['rankings'][branch]
                            if [r['evidence']['evidence_id'] for r in actual_rows]!=[r['evidence']['evidence_id'] for r in expected_rows]:
                                raise ValueError('Search ranking mismatch for '+dataset+'/'+branch+'/'+query)
                            if any(abs(a['score']-b['score'])>1e-6 for a,b in zip(actual_rows,expected_rows,strict=True)):
                                raise ValueError('Search scores differ from the local baseline')
                    comparisons.append({'dataset':dataset,'query':query,'branches':{k:len(v) for k,v in result['rankings'].items()}})
            facts=CaseFacts(contexts=[MeasurementContext(context_id='stream_1',label='powder blend',sample_matrix='powder blend',sample_phase='powder',target_analytes=['moisture'])])
            retrieval=CaseRetrievalService(isolated,repository=repository);retrieval.embedder=embedder
            actual=retrieval.retrieve_case(facts)
            from backend.pipelines.assessment.validation import authenticate_ledger
            authenticate_ledger(facts,actual,isolated.corpus_dir,repository=repository)
            if compare_local:
                local=CaseRetrievalService(settings);local.embedder=embedder
                expected=local.retrieve_case(facts)
                if [e.evidence.evidence_id for e in actual.evidence]!=[e.evidence.evidence_id for e in expected.evidence]:
                    raise ValueError('Assessment evidence selection differs from local baseline')
            app=create_app(isolated)
            app.dependency_overrides[get_current_user]=lambda:Identity('read-only-local-smoke','smoke@example.invalid','admin')
            with TestClient(app) as client:
                for url in ('/api/health','/api/enquiries','/api/knowledge/inspection','/api/search/status','/api/knowledge/ingest/status'):
                    response=client.get(url)
                    if response.status_code!=200:
                        raise ValueError('Cloud API smoke failed: '+url)
                inspection=client.get('/api/knowledge/inspection').json()
                version=inspection['manifest']['corpus_version']
                page=next(p for p in inspection['pages'] if p.get('image'))
                source=next(s for s in inspection['manifest']['sources'] if s['file_name'].lower().endswith('.pdf'))
                for suffix in (page['image'],'source/'+source['source_id']+'/original','review.html'):
                    if client.get('/api/knowledge/versions/'+version+'/'+suffix).status_code!=200:
                        raise ValueError('Cloud file API smoke failed')
            if isolated.corpus_dir.exists() or isolated.source_dir.exists() or isolated.explainability_db_path.exists() or list(isolated.cloud_cache_dir.rglob('qdrant')):
                raise ValueError('Cloud runtime unexpectedly required legacy local persistence')
            return {'status':'passed','corpus_version':version,'local_baseline_compared':compare_local,
                'search_cases':comparisons,'assessment_evidence_records':len(actual.evidence),
                'cloud_only_runtime':True,'model_calls':0}
        finally:
            database.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare-local',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        result=run(Settings(),args.compare_local)
        if args.output:write_json(args.output,result)
        print(json.dumps(result,indent=2))
        return 0
    except Exception as error:
        print('Cloud smoke failed ('+type(error).__name__+'). Inspect configuration and retrieval parity before cutover.')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
