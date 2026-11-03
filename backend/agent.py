"""Compatibility entrypoint; implementation: backend.pipelines.assessment.pipeline."""
import sys
from backend.pipelines.assessment import pipeline as _implementation
if __name__ == "__main__":
    import asyncio
    result = _implementation.main()
    sys.exit(asyncio.run(result) if hasattr(result, "__await__") else result)
else:
    sys.modules[__name__] = _implementation
