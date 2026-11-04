# Hosted deployment work

The container definition packages React, Python, Tesseract and pinned public embedding artifacts. It intentionally excludes local credentials and source originals. Place the public Supabase CA certificate at `deploy/supabase-ca.crt` before building.

The image includes durable background assessments, direct signed uploads, existing-account access restrictions, worker shutdown recovery and a build-time 450 MiB Linux memory gate. See `docs/heroku.md` for launch, billing activation, cloud backup and recovery procedures. Start only Eco dynos after enabling the account's Eco subscription.
