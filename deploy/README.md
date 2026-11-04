# Hosted deployment work

The container definition packages React, Python, Tesseract and pinned public embedding artifacts. It intentionally excludes local credentials and source originals. Place the public Supabase CA certificate at `deploy/supabase-ca.crt` before building.

Do not scale up this image yet. Background assessment submission/polling, the signed-upload flow, access restrictions, graceful worker shutdown and the 450 MiB Linux memory gate are still required before production deployment. The current worker handles ingestion only.
