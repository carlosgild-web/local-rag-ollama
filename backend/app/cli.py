"""CLI entry point.

Usage:
    python -m app.cli ingest <path>
"""

import argparse
import sys
from pathlib import Path

from app.core.config import get_settings
from app.ingest.pipeline import ingest_path
from app.llm.ollama_client import OllamaEmbeddingClient
from app.retrieval.chroma_store import ChromaVectorStore


def cmd_ingest(args: argparse.Namespace) -> int:
    settings = get_settings()
    settings.ensure_data_dirs()

    embedding_client = OllamaEmbeddingClient(settings.ollama_base_url, settings.embedding_model)
    vector_store = ChromaVectorStore(settings.chroma_dir)

    results = ingest_path(
        Path(args.path),
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    ingested = [r for r in results if r.status == "ingested"]
    skipped = [r for r in results if r.status == "skipped_duplicate"]

    for r in ingested:
        print(f"ingested  {r.path}  ({r.chunk_count} chunks)")
    for r in skipped:
        print(f"skipped   {r.path}  (duplicate)")

    print(
        f"\n{len(ingested)} ingested, {len(skipped)} skipped, "
        f"{sum(r.chunk_count for r in ingested)} chunks total"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest a file or directory")
    ingest_parser.add_argument("path", help="File or directory to ingest")
    ingest_parser.set_defaults(func=cmd_ingest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
