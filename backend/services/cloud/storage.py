"""Private, immutable content-addressed Storage objects; backend access only."""
import hashlib
import mimetypes
from urllib.parse import quote
import httpx
from backend.services.cloud.database import StorageUnavailable


class ArtifactStorage:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def _request(self, method, path, **kwargs):
        key = self.settings.supabase_secret_key.get_secret_value()
        if not key or not self.settings.supabase_url.startswith("https://"):
            raise StorageUnavailable("Configure the backend Supabase Storage secret and HTTPS URL.")
        headers = {"apikey": key}
        # Legacy service-role keys are JWTs; new sb_secret keys use apikey only.
        if not key.startswith("sb_secret_"):
            headers["Authorization"] = "Bearer " + key
        headers.update(kwargs.pop("headers", {}))
        try:
            with httpx.Client(timeout=120, transport=self.transport, follow_redirects=False) as client:
                result = client.request(method, self.settings.supabase_url.rstrip("/") + "/storage/v1/" + path,
                                        headers=headers, **kwargs)
            if not result.is_success:
                raise StorageUnavailable("Supabase file storage rejected the operation.")
            return result
        except httpx.HTTPError:
            raise StorageUnavailable("Supabase file storage is unavailable.") from None

    def provision(self):
        existing = {b["id"] for b in self._request("GET", "bucket").json()}
        for bucket in (self.settings.supabase_source_bucket, self.settings.supabase_artifact_bucket):
            if bucket in existing:
                details = self._request("GET", "bucket/" + quote(bucket, safe="")).json()
                if details.get("public"):
                    raise StorageUnavailable("SpectraPlan requires private Storage buckets.")
            else:
                self._request("POST", "bucket", json={"id": bucket, "name": bucket, "public": False,
                    "file_size_limit": self.settings.knowledge_upload_max_bytes})

    def put(self, data, *, source=False, filename="artifact"):
        sha = hashlib.sha256(data).hexdigest()
        bucket = self.settings.supabase_source_bucket if source else self.settings.supabase_artifact_bucket
        key = sha[:2] + "/" + sha
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        # Checking first makes import retries idempotent and detects damaged existing objects.
        try:
            prior = self.get({"bucket": bucket, "key": key, "sha256": sha})
        except StorageUnavailable:
            prior = None
        if prior is None:
            try:
                self._request("POST", "object/" + quote(bucket, safe="") + "/" + key,
                    content=data, headers={"Content-Type": mime, "x-upsert": "false"})
            except StorageUnavailable:
                # A concurrent writer may already have installed these exact bytes.
                self.get({"bucket": bucket, "key": key, "sha256": sha})
        return {"bucket": bucket, "key": key, "sha256": sha, "bytes": len(data), "mime": mime}

    def get(self, reference):
        data = self._request("GET", "object/authenticated/" + quote(reference["bucket"], safe="") +
                             "/" + quote(reference["key"], safe="/")).content
        if hashlib.sha256(data).hexdigest() != reference["sha256"]:
            raise StorageUnavailable("Stored file checksum does not match its reference.")
        return data
