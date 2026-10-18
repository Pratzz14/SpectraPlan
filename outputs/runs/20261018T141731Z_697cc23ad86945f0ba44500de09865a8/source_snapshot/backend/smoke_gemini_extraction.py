"""Run the opt-in original-file extraction comparison."""

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from backend.config import Settings
from backend.gemini_extraction import compare_original_extraction
from backend.knowledge_store import write_json


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Optional output JSON path")
    parser.add_argument("--limit", type=int, help="Process only the first N original files")
    parser.add_argument("--source-id", action="append", dest="source_ids",
                        help="Process only this source ID; repeat for multiple sources")
    args = parser.parse_args()
    settings = Settings()
    result = await compare_original_extraction(settings, source_limit=args.limit,
                                               source_ids=set(args.source_ids or []))
    path = args.output or (str(settings.smoke_output_dir / "gemini_complete_comparison.json")
        if not args.limit and not args.source_ids else str(settings.smoke_output_dir / (
        "gemini_extraction_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")))
    write_json(Path(path), result)
    print(path)
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
