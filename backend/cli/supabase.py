"""Explicit Supabase migration commands; never calls Qwen or publishes evaluations."""
import argparse
import json
from pathlib import Path
from backend.core.config import Settings
from backend.services.cloud.database import Database, StorageUnavailable, json_value
from backend.services.cloud.storage import ArtifactStorage
from backend.services.cloud.migration import inventory,prepare_generation,import_generation,verify_generation,history_rows,import_history,verify_history,activate,backup


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['preflight','backup','provision','create-login','import','verify','activate','export'])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    settings=Settings()
    database=Database(settings,migration=True)
    storage=ArtifactStorage(settings)
    try:
        if args.command=='backup':
            if not args.output:
                parser.error('--output is required')
            backup(settings,args.output)
            print('Local working data backed up.')
            return 0
        if args.command=='provision':
            with database.connection() as c:
                for script in sorted((Path(__file__).resolve().parents[1]/'services/cloud/migrations').glob('*.sql')):
                    c.execute(script.read_text(encoding='utf-8'))
            storage.provision()
            print('Private schema and buckets provisioned. Configure a restricted runtime login before cutover.')
            return 0
        if args.command=='create-login':
            from backend.services.cloud.setup import create_runtime_login
            create_runtime_login(settings,database)
            print('Restricted runtime login created; DATABASE_URL saved in the ignored local .env.')
            return 0
        if args.command=='export':
            if not args.output:
                parser.error('--output is required')
            from backend.services.cloud.export import export_cloud
            export_cloud(settings,database,storage,args.output)
            print('Cloud working data exported with checksums.')
            return 0
        versions,active=inventory(settings)
        rows=history_rows(settings.explainability_db_path)
        if args.command=='preflight':
            result=[]
            for dataset,directory in versions:
                g=prepare_generation(settings,dataset,directory,vectors=False)
                result.append({'dataset':dataset,'version':g['version'],'records':len(g['records']),
                    'file_bytes':sum(p.stat().st_size for p in g['files'].values()),
                    'metadata_bytes':sum(len(b.encode()) for b in g['documents'].values())})
            print(json.dumps({'active':active,'generations':result,'history':{t:len(r) for t,r in rows.items()},
                'database_configured':bool(settings.supabase_migration_database_url.get_secret_value()),
                'storage_configured':bool(settings.supabase_secret_key.get_secret_value()),
                'certificate_configured':bool(settings.database_ssl_root_cert and settings.database_ssl_root_cert.is_file())},indent=2))
            return 0
        if args.command=='activate':
            # Activation requires fresh verification, not a previously set ready flag.
            verify_history(database,rows)
            results=[]
            for dataset,directory in versions:
                print('Verifying '+directory.name,flush=True)
                results.append(verify_generation(database,storage,prepare_generation(settings,dataset,directory)))
            activate(database,active,initial=True)
            if args.output:
                from backend.services.knowledge.knowledge_store import write_json
                write_json(args.output,{'active':active,'history':{t:len(r) for t,r in rows.items()},'generations':results})
            print('Verified cloud corpus pointers activated. Set STORAGE_BACKEND=supabase to cut over.')
            return 0
        results=[]
        if args.command=='import':
            import_history(database,rows)
            registry=settings.corpus_dir/'added_sources.json'
            with database.connection() as c:
                from backend.services.knowledge.knowledge_store import read_json
                value=read_json(registry) if registry.is_file() else []
                if not c.execute("SELECT 1 FROM spectraplan.app_state WHERE key='initial_migration_complete'").fetchone():
                    c.execute("INSERT INTO spectraplan.app_state VALUES ('source_registry',%s) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",(json_value(value),))
        for dataset,directory in versions:
            generation=prepare_generation(settings,dataset,directory)
            print(('Importing' if args.command=='import' else 'Verifying')+' '+generation['version']+' ('+str(len(generation['records']))+' records)',flush=True)
            if args.command=='import':
                results.append({'imported':import_generation(database,storage,generation)})
            else:
                results.append(verify_generation(database,storage,generation))
        print(json.dumps({'history':verify_history(database,rows),'generations':results},indent=2))
        return 0
    except (OSError,ValueError,KeyError,RuntimeError) as error:
        # Never print connection strings, password-bearing exception details or provider bodies.
        print('Supabase migration did not complete ('+type(error).__name__+'). Check configuration, local corpus validity, and connectivity.')
        return 1
    finally:
        database.close()


if __name__=='__main__':
    raise SystemExit(main())
