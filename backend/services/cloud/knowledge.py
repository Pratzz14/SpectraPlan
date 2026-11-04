"""Cloud corpus snapshots and verified disposable file caches."""
import hashlib
import re
from types import SimpleNamespace
from backend.services.cloud.database import StorageUnavailable
from backend.services.knowledge.knowledge_store import inside, read_json, file_hash, load_records
from backend.services.search.evidence import CorpusSnapshot, EvidenceNotFound, CorpusUnavailable


def repository_for(settings):
    """Standalone Python/CLI services honor cloud mode as well as the API factory."""
    if settings.storage_backend != 'supabase':
        return None
    import atexit
    from backend.services.cloud.database import Database
    from backend.services.cloud.storage import ArtifactStorage
    database=Database(settings)
    atexit.register(database.close)
    return CloudKnowledge(settings,database,ArtifactStorage(settings))


class VectorClient:
    """Small semantic-query interface shared with the existing retrieval algorithm."""
    def __init__(self, repository, version, purpose):
        self.repository, self.version, self.purpose = repository, version, purpose

    def query_points(self, collection, *, query, limit):
        if len(query) != 384:
            raise ValueError("Expected a 384-dimensional BGE query vector")
        vector = "[" + ",".join(str(float(v)) for v in query) + "]"
        with self.repository.database.connection() as c:
            # Exact cosine: no approximate index or post-filtered ANN recall changes.
            rows = c.execute("SELECT segment_id,evidence_id,1-(embedding OPERATOR(extensions.<=>) %s::extensions.vector) AS score "
                "FROM spectraplan.embedding_segments WHERE version=%s AND purpose=%s "
                "ORDER BY score DESC,segment_id LIMIT %s", (vector,self.version,self.purpose,limit)).fetchall()
        return SimpleNamespace(points=[SimpleNamespace(id=s, payload={"evidence_id":e}, score=float(score)) for s,e,score in rows])

    def close(self):
        pass


class CloudKnowledge:
    def __init__(self, settings, database, storage):
        self.settings, self.database, self.storage = settings, database, storage

    def directory(self, dataset="technical", version=None):
        dataset = "technical" if dataset == "inspection" else dataset
        if version and not re.fullmatch(r"(?:corpus|web)-[a-f0-9]{20}", version):
            raise EvidenceNotFound("Unknown corpus version")
        with self.database.connection() as c:
            if version is None:
                row = c.execute("SELECT version FROM spectraplan.active_corpora WHERE dataset=%s", (dataset,)).fetchone()
                if row is None:
                    raise CorpusUnavailable("No active cloud corpus. Run migration verification and activation.")
                version = row[0]
            ready = c.execute("SELECT ready,digest FROM spectraplan.corpus_versions WHERE version=%s AND dataset=%s", (version,dataset)).fetchone()
            if not ready or not ready[0]:
                raise EvidenceNotFound("Unknown or unpublished corpus version")
            root = self.settings.cloud_cache_dir / "corpora" / version
            receipt=root/'_cloud_cache.json'
            if receipt.is_file():
                cached=read_json(receipt)
                if cached.get('digest')==ready[1] and all(inside(root,name).is_file() and file_hash(inside(root,name))==sha for name,sha in cached.get('files',{}).items()) and cached.get('files'):
                    return root
            rows = c.execute("SELECT path,body,sha256 FROM spectraplan.corpus_documents WHERE version=%s ORDER BY path", (version,)).fetchall()
        # Read cloud metadata on every load; local cache never masks a cloud outage.
        from backend.services.knowledge.knowledge_store import write_json
        for name, body, sha in rows:
            if hashlib.sha256(body.encode('utf-8')).hexdigest() != sha:
                raise CorpusUnavailable("Cloud corpus metadata checksum mismatch")
            path = inside(root, name)
            if not path.is_file() or file_hash(path) != sha:
                path.parent.mkdir(parents=True, exist_ok=True)
                import os
                from uuid import uuid4
                temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
                try:
                    temp.write_bytes(body.encode('utf-8'))
                    os.replace(temp, path)
                finally:
                    temp.unlink(missing_ok=True)
        write_json(receipt,{'digest':ready[1],'files':{name:sha for name,_,sha in rows}})
        return root

    def snapshot(self, version=None):
        directory = self.directory(version=version)
        manifest, passages, methods = load_records(directory)
        return CorpusSnapshot(directory, manifest['corpus_version'],
            {r['evidence_id']:r for r in passages+methods if r['retrieval_eligible']},
            read_json(directory/'method_notes.json'))

    def client(self, directory):
        purpose = 'inspection' if directory.name == 'inspection' else 'technical'
        version = directory.parent.name if purpose == 'inspection' else directory.name
        return VectorClient(self, version, purpose)

    def artifact(self, version, name):
        if not re.fullmatch(r"(?:corpus|web)-[a-f0-9]{20}", version):
            raise EvidenceNotFound("Unknown corpus version")
        with self.database.connection() as c:
            row = c.execute("SELECT reference FROM spectraplan.corpus_files f JOIN spectraplan.corpus_versions v "
                "ON v.version=f.version WHERE f.version=%s AND f.path=%s AND v.ready", (version,name)).fetchone()
        if row is None:
            raise EvidenceNotFound("Unknown corpus artifact")
        reference = row[0]
        path = inside(self.settings.cloud_cache_dir/'files'/version, name)
        if not path.is_file() or file_hash(path) != reference['sha256']:
            data = self.storage.get(reference)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Concurrent readers can safely write identical immutable bytes atomically.
            import os
            from uuid import uuid4
            temporary = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
            try:
                temporary.write_bytes(data)
                os.replace(temporary,path)
            finally:
                temporary.unlink(missing_ok=True)
        return path, reference

    def hydrate(self, target):
        """Restore build inputs from cloud for the local processing pipeline."""
        import shutil
        from backend.services.knowledge.knowledge_store import write_json
        directory = self.directory()
        version = directory.name
        destination = target.corpus_dir/'versions'/version
        shutil.copytree(directory, destination, dirs_exist_ok=True)
        with self.database.connection() as c:
            files = c.execute("SELECT path FROM spectraplan.corpus_files WHERE version=%s", (version,)).fetchall()
            registry = c.execute("SELECT payload FROM spectraplan.app_state WHERE key='source_registry'").fetchone()
        manifest = read_json(directory/'source_manifest.json')
        for (name,) in files:
            path, _ = self.artifact(version,name)
            if name.startswith('originals/'):
                sid = name.split('/')[1]
                source = next(s for s in manifest['sources'] if s['source_id']==sid)
                output = inside(target.source_dir, source.get('file_path',source['file_name']))
            else:
                output = inside(destination,name)
            output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,output)
        if registry:
            write_json(target.corpus_dir/'added_sources.json',registry[0])
        write_json(target.corpus_dir/'current.json',{'corpus_version':version,'directory':'versions/'+version})
        return destination
