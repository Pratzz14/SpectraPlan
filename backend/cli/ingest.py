"""PDF and Office knowledge ingestion: python -m backend.cli.ingest build|publish|validate|report|search."""
import argparse
import json
from pathlib import Path
from filelock import FileLock, Timeout
from backend.core.config import PROJECT_ROOT, Settings
from backend.services.knowledge.knowledge_store import active_directory, validate_corpus
from backend.pipelines.pdf_knowledge.extract import extract_all, pipeline_fingerprint
from backend.pipelines.pdf_knowledge.store import publish_extraction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ('build', 'pilot'):
        command = commands.add_parser(name, help='Extract all supported PDF, Excel and Word sources and publish')
        command.add_argument('--refresh', action='store_true', help='Replace even matching completed answers')
        command.add_argument('--concurrency', type=int, choices=range(1,5), default=2)
        command.add_argument('--source', action='append', dest='source_ids')
    command = commands.add_parser('add', help='Add or update a PDF, XLSX, or DOCX without replacing the library')
    command.add_argument('--file', required=True, type=Path)
    command.add_argument('--role', choices=['technical','research','business','development'], default='technical')
    command.add_argument('--name', help='Optional original display filename')
    command.add_argument('--prepare-only', action='store_true')
    command.add_argument('--concurrency', type=int, choices=range(1,5), default=2)
    command.add_argument('--job-file', type=Path, help=argparse.SUPPRESS)
    commands.add_parser('publish', help='Publish completed latest extraction without model calls')
    commands.add_parser('validate')
    commands.add_parser('report')
    command = commands.add_parser('search')
    command.add_argument('--query', required=True)
    args = parser.parse_args()
    settings = Settings()
    if settings.storage_backend == 'supabase':
        from backend.services.cloud.commands import ingestion
        return ingestion(settings,args)
    latest = settings.knowledge_work_dir / 'latest'
    latest.mkdir(parents=True, exist_ok=True)
    try:
        if args.command == 'add':
            from backend.pipelines.pdf_knowledge.import_file import ingest_file
            print(json.dumps(ingest_file(settings,args.file,role=args.role,name=args.name,prepare_only=args.prepare_only,
                                         concurrency=args.concurrency,job_file=args.job_file),indent=2))
        elif args.command in {'build', 'pilot', 'publish'}:
            with FileLock(str(latest.parent / 'build.lock'), timeout=0):
                if args.command != 'publish':
                    result = extract_all(settings,latest,source_ids=args.source_ids,concurrency=args.concurrency,refresh=args.refresh)
                    if result:
                        return result
                    from backend.services.knowledge.knowledge_store import read_json, write_json
                    run=read_json(latest/'manifest.json')
                    run['merge_existing']=bool(args.source_ids)
                    write_json(latest/'manifest.json',run)
                from backend.services.knowledge.knowledge_store import read_json
                # Selected-source rebuilds replace those sources, retaining the library.
                print(json.dumps(publish_extraction(settings, latest, merge=read_json(latest/'manifest.json').get('merge_existing',False)), indent=2))
        elif args.command == 'validate':
            print(json.dumps(validate_corpus(active_directory(settings.corpus_dir), source_dir=settings.source_dir, deep=True), indent=2))
        elif args.command == 'report':
            print(active_directory(settings.corpus_dir) / 'review.html')
        else:
            from backend.services.search.retrieval import search
            print(json.dumps(search(settings.corpus_dir, settings.embedding_cache_dir, args.query), indent=2))
        return 0
    except Timeout:
        print('Another ingestion is running. Try again when it finishes.')
        return 1
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        if args.command in {'build','pilot','publish'} and (latest/'manifest.json').is_file():
            from backend.services.knowledge.knowledge_store import read_json, write_json
            failed=read_json(latest/'manifest.json')
            failed.update(status='failed',message=f'Publication failed ({type(error).__name__}). Existing knowledge was preserved.')
            write_json(latest/'manifest.json',failed)
        print(f'Ingestion failed ({type(error).__name__}): {error}')
        return 1
    finally:
        if args.command == 'add' and args.job_file:
            incoming = settings.knowledge_work_dir/'import'/'incoming'
            if args.file.resolve().is_relative_to(incoming.resolve()):
                args.file.unlink(missing_ok=True)



if __name__ == '__main__':
    raise SystemExit(main())
