"""Admin-only, scoped direct uploads so large files bypass the Heroku router."""
from pathlib import Path
import re
from uuid import uuid4
from urllib.parse import quote
from backend.services.cloud.assessments import BoundDatabase
from backend.services.cloud.jobs import IngestionJobs
from backend.services.cloud.database import json_value


def create(settings,database,storage,user,payload):
    filename=payload.get('filename','');role=payload.get('role','technical');size=payload.get('size',0)
    if not isinstance(filename,str) or not filename or len(filename)>180 or Path(filename).name!=filename or re.search(r'[<>:"/\\|?*\x00-\x1f]',filename) or filename.endswith(('.', ' ')) or Path(filename).suffix.lower() not in {'.pdf','.xlsx','.docx'}:
        raise ValueError('Choose a PDF, XLSX or DOCX filename without directory separators.')
    if role not in {'technical','research','business','development'} or type(size)!=int or not 0<size<=settings.knowledge_upload_max_bytes:
        raise ValueError('Invalid source role or file size.')
    upload_id=uuid4().hex;key='incoming/'+upload_id+Path(filename).suffix.lower()
    signed=storage._request('POST','object/upload/sign/'+quote(settings.supabase_source_bucket,safe='')+'/'+key,json={}).json()
    path=signed.get('url') or signed.get('signedURL')
    if not path:raise ValueError('Storage did not return a signed upload URL.')
    with database.connection() as c:
        c.execute('INSERT INTO spectraplan.uploads(upload_id,owner_user_id,filename,role,object_key,expected_bytes) VALUES (%s,%s,%s,%s,%s,%s)',(upload_id,user.user_id,filename,role,key,size))
    return {'upload_id':upload_id,'signed_url':settings.supabase_url.rstrip('/')+'/storage/v1'+('/' if not path.startswith('/') else '')+path}


def complete(settings,database,user,upload_id):
    with database.connection() as c:
        row=c.execute('SELECT filename,role,object_key,expected_bytes,job_id FROM spectraplan.uploads WHERE upload_id=%s AND owner_user_id=%s AND expires_at>now() FOR UPDATE',(upload_id,user.user_id)).fetchone()
        if not row:raise ValueError('Upload expired or not found.')
        if row[4]:
            return c.execute('SELECT state FROM spectraplan.ingestion_jobs WHERE job_id=%s',(row[4],)).fetchone()[0]
        reference={'bucket':settings.supabase_source_bucket,'key':row[2],'sha256':'upload-'+upload_id,'staged':True,'expected_bytes':row[3]}
        state=IngestionJobs(settings,BoundDatabase(c)).enqueue(row[0],row[1],reference)
        c.execute('UPDATE spectraplan.uploads SET job_id=%s WHERE upload_id=%s',(state['job_id'],upload_id))
        return state
