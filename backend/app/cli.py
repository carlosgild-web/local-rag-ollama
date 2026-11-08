"""CLI entry point.

Usage:
    python -m app.cli ingest <path>
    python -m app.cli ask "<question>"
    python -m app.cli seed-demo [path]
"""

import argparse
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.runtime import build_runtime
from app.retrieval.prompt import NOT_FOUND_PHRASE, format_sources
from app.retrieval.qa import prepare_context
from app.versioning import service
from app.versioning.demo import DEMO_DIR, seed_demo


def cmd_ingest(args: argparse.Namespace) -> int:
    runtime = build_runtime(get_settings())
    settings = runtime.settings

    with runtime.session_factory() as db:
        collection = service.get_or_create_default_collection(db, runtime.vector_store, settings)
        embedding_client = runtime.embedding_client_for(collection.embedding_model)

        ingested = skipped = chunks = 0
        for path in service.discover_files(Path(args.path)):
            result = service.ingest_document(
                db,
                collection=collection,
                source_path=path,
                settings=settings,
                embedding_client=embedding_client,
                vector_store=runtime.vector_store,
            )
            if result.status == "ingested":
                ingested += 1
                chunks += result.chunk_count
                print(f"ingested  {path}  ({result.chunk_count} chunks)")
            else:
                skipped += 1
                print(f"skipped   {path}  (duplicate)")

    print(f"\n{ingested} ingested, {skipped} skipped, {chunks} chunks total")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    runtime = build_runtime(get_settings())
    settings = runtime.settings
    question = " ".join(args.question)

    with runtime.session_factory() as db:
        collection = service.get_or_create_default_collection(db, runtime.vector_store, settings)
        context = prepare_context(
            db,
            question,
            collection=collection,
            settings=settings,
            embedding_client=runtime.embedding_client_for(collection.embedding_model),
            vector_store=runtime.vector_store,
        )
    if context is None:
        print(NOT_FOUND_PHRASE)
        return 0

    llm_client = runtime.llm_client_for(settings.chat_model)
    for piece in llm_client.stream_generate(
        context.prompt, temperature=settings.llm_temperature, num_ctx=settings.ollama_num_ctx
    ):
        print(piece, end="", flush=True)

    print("\n\nSources:")
    print(format_sources(context.chunks))
    return 0


def cmd_seed_demo(args: argparse.Namespace) -> int:
    """Loads the fictional Hilda & Luna Beadworks corpus, one shelf per folder."""
    runtime = build_runtime(get_settings())
    with runtime.session_factory() as db:
        results = seed_demo(
            db,
            settings=runtime.settings,
            embedding_client_for=runtime.embedding_client_for,
            vector_store=runtime.vector_store,
            root=Path(args.path) if args.path else DEMO_DIR,
        )
    for item in results:
        if item.status == "ingested":
            print(f"ingested  {item.shelf:<18} {item.path.name}  ({item.chunk_count} chunks)")
        else:
            print(f"skipped   {item.shelf:<18} {item.path.name}  (already stored)")
    ingested = sum(item.status == "ingested" for item in results)
    print(f"\n{ingested} ingested, {len(results) - ingested} skipped")
    print("Open the employee portal at /intranet and ask Luna.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest a file or directory")
    ingest_parser.add_argument("path", help="File or directory to ingest")
    ingest_parser.set_defaults(func=cmd_ingest)

    ask_parser = subparsers.add_parser("ask", help="Ask a question against the ingested documents")
    ask_parser.add_argument("question", nargs="+", help="The question to ask")
    ask_parser.set_defaults(func=cmd_ask)

    seed_parser = subparsers.add_parser(
        "seed-demo", help="Load the fictional Hilda & Luna Beadworks demo documents"
    )
    seed_parser.add_argument("path", nargs="?", help="Demo folder (default: demo/hilda-luna)")
    seed_parser.set_defaults(func=cmd_seed_demo)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
