"""Create a chunked cloud backup using runtime credentials, without PC files."""
import hashlib,json,zipfile
from tempfile import TemporaryDirectory
from pathlib import Path
from uuid import uuid4
from backend.core.config import Settings
from backend.services.cloud.database import Database,json_value
from backend.services.cloud.storage import ArtifactStorage
from backend.services.cloud.export import export_cloud


def main():
    settings=Settings();database=Database(settings);storage=ArtifactStorage(settings)
    bucket='spectraplan-backups'
    try:
        buckets=storage._request('GET','bucket').json()
        existing=next((b for b in buckets if b['id']==bucket),None)
        if existing and existing.get('public'):raise ValueError('Backup bucket must be private')
        if not existing:storage._request('POST','bucket',json={'id':bucket,'name':bucket,'public':False,'file_size_limit':settings.knowledge_upload_max_bytes})
        with TemporaryDirectory(prefix='cloud-backup-') as temporary:
            root=Path(temporary);export_cloud(settings,database,storage,root/'export')
            archive=root/'backup.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for path in (root/'export').rglob('*'):
                    if path.is_file():z.write(path,path.relative_to(root/'export').as_posix())
            identity=uuid4().hex;parts=[]
            with archive.open('rb') as stream:
                while data:=stream.read(16*1024*1024):
                    key=f'{identity}/{len(parts):04}.part'
                    storage._request('POST','object/'+bucket+'/'+key,content=data,headers={'Content-Type':'application/octet-stream','x-upsert':'false'})
                    parts.append({'key':key,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
            item={'id':identity,'bucket':bucket,'parts':parts,'format':'zip'}
            with database.connection() as c:
                c.execute("SELECT pg_advisory_xact_lock(hashtext('spectraplan:backup'))")
                old=c.execute("SELECT payload FROM spectraplan.app_state WHERE key='cloud_backups' FOR UPDATE").fetchone()
                previous=old[0] if old else []
                retained=([item]+previous)[:2]
                c.execute("INSERT INTO spectraplan.app_state VALUES ('cloud_backups',%s) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",(json_value(retained),))
            for expired in previous[1:]:
                storage._request('DELETE','object/'+bucket,json={'prefixes':[p['key'] for p in expired['parts']]})
            print(json.dumps({'backup_id':identity,'parts':len(parts),'retained':len(retained),'status':'complete'}))
    finally:database.close()


if __name__=='__main__':main()
