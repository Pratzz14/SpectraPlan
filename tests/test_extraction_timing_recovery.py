"""Replay the real Qwen failure without contacting a model."""
import asyncio
import json
from pathlib import Path
import httpx
import pytest
from backend.core.config import Settings
from backend.providers.provider import Provider
from backend.pipelines.assessment.pipeline import extract_case, ExtractionOutput, recover_extraction_fields
from backend.pipelines.assessment.validation import validate_extraction

FIXTURE = json.loads((Path(__file__).parent/'fixtures/extraction_update_interval.json').read_text(encoding='utf-8'))

def test_actual_qwen_response_keeps_cadence_without_retry():
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":json.dumps(FIXTURE['response'])}}]})
    provider=Provider(Settings(_env_file=None,dashscope_api_key='test-secret'),transport=httpx.MockTransport(respond))
    facts=asyncio.run(extract_case(FIXTURE['description'],provider=provider))
    validate_extraction(facts,FIXTURE['description'])
    assert len(calls)==1
    assert facts.contexts[0].response_time_raw=='every 10 seconds'
    assert facts.contexts[0].response_time_s is None
    assert 'moisture' in facts.contexts[0].target_analytes
    assert provider.repair_counts['extraction']==0

@pytest.mark.parametrize('raw,value,expected',[('10 seconds',10,10),('10 seconds',2,None),('under 10 seconds',10,None),('every 10 seconds',10,None),('2 min',120,None)])
def test_optional_numeric_time_recovers_without_weakening_provenance(raw,value,expected):
    response=json.loads(json.dumps(FIXTURE['response']))
    description=FIXTURE['description']+' Timing: '+raw+'.'
    response['contexts'][0]['response_time_raw']={'value':raw,'input_quote':raw}
    response['contexts'][0]['response_time_s']={'value':value,'input_quote':raw}
    recovered,_=recover_extraction_fields(ExtractionOutput.model_validate(response),description)
    facts=recovered.to_facts(description)
    validate_extraction(facts,description)
    assert facts.contexts[0].response_time_raw==raw
    assert facts.contexts[0].response_time_s==expected
