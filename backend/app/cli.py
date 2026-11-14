"""CLI entry point.

Usage:
    python -m app.cli ingest <path>
    python -m app.cli ask "<question>"
    python -m app.cli seed-demo [path]
    python -m app.cli eval [--set NAME] [--mode hybrid|vector|keyword] [--answers] [--judge]
    python -m app.cli eval-compare <run a> <run b>
    python -m app.cli set-password [--stdin]
    python -m app.cli clear-password
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


def cmd_backup(args: argparse.Namespace) -> int:
    """A backup while the app is stopped (when it runs, use Back up now in the console)."""
    from app.db import backup

    settings = get_settings()
    if backup.app_is_running(settings) and not args.force:
        print(
            "The app is running: use Back up now in the console (Backups), or stop the app first."
        )
        return 1
    path = backup.create_backup(settings, reason="manual")
    print(f"Backup written: {path} ({path.stat().st_size // 1024} KB)")
    return 0


def cmd_backups(args: argparse.Namespace) -> int:
    from app.db import backup

    for item in backup.list_backups(get_settings()):
        m = item["manifest"] or {}
        counts = m.get("counts", {})
        print(
            f"{item['name']}  {item['size'] // 1024:>8} KB  "
            f"{counts.get('documents', '?')} documents  {item['error'] or ''}"
        )
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Replaces the data with a backup's; the current data is backed up first."""
    from app.db import backup
    from app.db.migrate import known_revisions, upgrade_to_head

    settings = get_settings()
    path = Path(args.backup)
    if not path.is_file():
        path = settings.backups_dir / args.backup
    if not path.is_file():
        print(f"No backup at {args.backup}")
        return 1
    try:
        result = backup.restore_backup(
            settings, path, known_revisions=known_revisions(), force=args.force
        )
    except backup.BackupError as exc:
        print(f"Not restored: {exc}")
        return 1
    upgrade_to_head(settings.db_path)  # an older backup gets the current schema
    runtime = build_runtime(settings)
    with runtime.session_factory() as db:
        service.audit_event(db, "restore", "backup", None, f"from {path.name}")
    restored = result["restored"]
    counts = restored.get("counts", {})
    made, docs = restored.get("created_at"), counts.get("documents")
    print(f"Restored {path.name} (made {made}, {docs} documents).")
    if result["safety_backup"]:
        print(f"The data from before the restore is in {result['safety_backup']}.")
    return 0


_METRICS = (
    ("hit_rate_at_5", "hit rate@5", "pct"),
    ("mrr", "MRR", "num"),
    ("pass_rate", "cases passed", "pct"),
    ("answered_rate", "answered (not 'not found')", "pct"),
    ("facts_rate", "required facts present", "pct"),
    ("trap_rate", "'not found' when it should be", "pct"),
    ("citation_rate", "citations to the right file", "pct"),
    ("faithfulness", "faithfulness (LLM judge)", "num"),
    ("variant_rate", "wording groups all passed", "pct"),
    ("retrieval_ms", "retrieval ms per question", "ms"),
    ("answer_ms", "answer ms per question", "ms"),
)


def _fmt(value, kind: str) -> str:
    if value is None:
        return "-"
    if kind == "pct":
        return f"{value:.0%}"
    if kind == "ms":
        return f"{value:.0f}"
    return f"{value:.3f}"


def cmd_eval(args: argparse.Namespace) -> int:
    """Runs a golden set in this process (app stopped). With the app running,
    use the console's Evaluation page, which queues the run as a job."""
    from app.db import backup
    from app.eval import service as eval_service
    from app.versioning import profiles

    settings = get_settings()
    if backup.app_is_running(settings) and not args.force:
        print("The app is running: start the run from the console (Evaluation), or stop the app.")
        return 1
    runtime = build_runtime(settings)
    with runtime.session_factory() as db:
        sets = {s.name: s for s in eval_service.list_sets(db)}
        if args.set is None and not sets:
            eval_set = eval_service.load_demo_set(db)
            print(f"loaded the demo golden set {eval_set.name!r}")
        elif args.set is None:
            eval_set = next(iter(sets.values()))
        elif args.set in sets:
            eval_set = sets[args.set]
        else:
            print(f"no golden set named {args.set!r}; there are: {', '.join(sets) or 'none'}")
            return 1
        profile = profiles.get_active_profile(db, settings, args.profile)
        run = eval_service.start_run(
            db,
            settings,
            eval_set.id,
            profile_id=profile.id,
            mode=args.mode,
            top_k=args.top_k,
            answers=args.answers or args.judge,
            judge=args.judge,
            repair=not args.no_repair,
            glossary=not args.no_glossary,
            rerank=args.rerank,
            label=args.label or "",
            queue_job=False,
        )
        print(f"run #{run.id}: {eval_set.name}, {run.label}, {len(eval_set.cases)} cases")

        def progress(fraction: float) -> None:
            print(f"\r{fraction:.0%}", end="", flush=True)

        eval_service.execute_run(
            db,
            run.id,
            settings=settings,
            embedding_client_for=runtime.embedding_client_for,
            vector_store=runtime.vector_store,
            llm_client_for=runtime.llm_client_for,
            progress=progress,
            reranker=runtime.reranker,
        )
        print()
        _print_metrics([run])
        for result in run.results:
            if result.passed is False:
                why = result.error or (
                    "not found" if result.not_found else f"rank {result.first_relevant_rank}"
                )
                print(f"  failed  [{result.shelf or 'all'}] {result.question}  ({why})")
    return 0


def cmd_eval_compare(args: argparse.Namespace) -> int:
    from app.eval import service as eval_service

    runtime = build_runtime(get_settings())
    with runtime.session_factory() as db:
        comparison = eval_service.compare_runs(db, args.a, args.b)
        _print_metrics([comparison["a"], comparison["b"]])
        if not comparison["same_index"]:
            print("\nThe two runs searched different indexes (documents or versions changed).")
        for row in comparison["cases"]:
            if row["change"] != "same":
                print(f"  {row['change']:<7} [{row['shelf'] or 'all'}] {row['question']}")
    return 0


def _print_metrics(runs) -> None:
    header = f"{'':<32}" + "".join(f"{'#' + str(r.id):>12}" for r in runs)
    print(header)
    for key, name, kind in _METRICS:
        values = [(r.metrics or {}).get(key) for r in runs]
        if all(v is None for v in values):
            continue
        print(f"{name:<32}" + "".join(f"{_fmt(v, kind):>12}" for v in values))


def cmd_reranker_download(args: argparse.Namespace) -> int:
    """Fetches the pinned bge-reranker-v2-m3 ONNX files (about 588 MB) into DATA_DIR/hf."""
    from app.retrieval import onnx_reranker

    settings = get_settings()
    print(f"{onnx_reranker.REPO} @ {onnx_reranker.REVISION[:7]} -> {settings.reranker_dir}")
    onnx_reranker.download(settings.reranker_dir)
    print("Ready. Turn it on for the chat with RERANK_ENABLED=true, or per evaluation run.")
    return 0


def _audit(action: str, detail: str) -> None:
    runtime = build_runtime(get_settings())
    with runtime.session_factory() as db:
        service.audit_event(db, action, "auth", None, detail)


def cmd_set_password(args: argparse.Namespace) -> int:
    """Stores an scrypt hash in DATA_DIR/auth.json (decision 0026). The app picks
    it up at once and everyone already signed in is signed out."""
    import getpass

    from app.core import auth

    settings = get_settings()
    if args.stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("New password: ")
        if getpass.getpass("Again: ") != password:
            print("The two passwords don't match; nothing changed.", file=sys.stderr)
            return 1
    try:
        auth.set_password(settings, password)
    except auth.AuthError as exc:
        print(f"Not set: {exc}.", file=sys.stderr)
        return 1
    _audit("password_set", "password set from the CLI")
    if settings.app_password:
        print("Saved, but APP_PASSWORD is set too and wins until you remove it.")
    else:
        print("Saved. The app now asks for this password; sessions already open are signed out.")
    return 0


def cmd_clear_password(args: argparse.Namespace) -> int:
    from app.core import auth

    settings = get_settings()
    env_note = " APP_PASSWORD is still set, so sign-in stays on." if settings.app_password else ""
    if not auth.clear_password(settings):
        print("No password was stored." + env_note)
        return 0
    _audit("password_clear", "password removed from the CLI")
    print("Removed." + (env_note or " The app is open again: keep it on localhost."))
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

    backup_parser = subparsers.add_parser("backup", help="Back up the data (app stopped)")
    backup_parser.add_argument("--force", action="store_true", help="even if the app seems to run")
    backup_parser.set_defaults(func=cmd_backup)

    backups_parser = subparsers.add_parser("backups", help="List the backups")
    backups_parser.set_defaults(func=cmd_backups)

    restore_parser = subparsers.add_parser(
        "restore", help="Restore a backup (app stopped); the current data is backed up first"
    )
    restore_parser.add_argument("backup", help="A backup file, or its name in DATA_DIR/backups")
    restore_parser.add_argument("--force", action="store_true", help="even if the app seems to run")
    restore_parser.set_defaults(func=cmd_restore)

    eval_parser = subparsers.add_parser(
        "eval", help="Run a golden set (app stopped); loads the demo set if there is none"
    )
    eval_parser.add_argument("--set", help="Golden set name (default: the first one)")
    eval_parser.add_argument("--profile", default="default", help="RAG profile name")
    eval_parser.add_argument(
        "--mode", choices=["hybrid", "vector", "keyword"], default="hybrid", help="Retrieval"
    )
    eval_parser.add_argument("--top-k", type=int, help="Chunks sent to the model")
    eval_parser.add_argument("--answers", action="store_true", help="Also generate answers")
    eval_parser.add_argument("--judge", action="store_true", help="LLM-judged faithfulness")
    eval_parser.add_argument(
        "--no-repair", action="store_true", help="Keep the model's citation numbers as written"
    )
    eval_parser.add_argument(
        "--no-glossary", action="store_true", help="Ask the questions without the glossary"
    )
    eval_parser.add_argument(
        "--rerank", action="store_true", help="Rescore candidates with bge-reranker-v2-m3"
    )
    eval_parser.add_argument("--label", help="A name for the run")
    eval_parser.add_argument("--force", action="store_true", help="even if the app seems to run")
    eval_parser.set_defaults(func=cmd_eval)

    compare_parser = subparsers.add_parser("eval-compare", help="Compare two evaluation runs")
    compare_parser.add_argument("a", type=int, help="Run id")
    compare_parser.add_argument("b", type=int, help="Run id")
    compare_parser.set_defaults(func=cmd_eval_compare)

    download_parser = subparsers.add_parser(
        "reranker-download", help="Download the reranker model (about 588 MB) to DATA_DIR/hf"
    )
    download_parser.set_defaults(func=cmd_reranker_download)

    password_parser = subparsers.add_parser(
        "set-password", help="Require a password to use the app (stores a hash in DATA_DIR)"
    )
    password_parser.add_argument(
        "--stdin", action="store_true", help="Read the password from standard input (scripts)"
    )
    password_parser.set_defaults(func=cmd_set_password)
    clear_parser = subparsers.add_parser("clear-password", help="Remove the stored password")
    clear_parser.set_defaults(func=cmd_clear_password)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
