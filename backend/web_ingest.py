"""Compatibility entrypoint; implementation: backend.pipelines.website.ingest."""
import sys
from backend.pipelines.website import ingest as _implementation
if __name__ == "__main__":
    import asyncio
    result = _implementation.main()
    sys.exit(asyncio.run(result) if hasattr(result, "__await__") else result)
else:
    sys.modules[__name__] = _implementation
