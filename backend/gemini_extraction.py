"""Compatibility entrypoint; implementation: backend.pipelines.document_comparison.pipeline."""
import sys
from backend.pipelines.document_comparison import pipeline as _implementation
if __name__ == "__main__":
    import asyncio
    result = _implementation.main()
    sys.exit(asyncio.run(result) if hasattr(result, "__await__") else result)
else:
    sys.modules[__name__] = _implementation
