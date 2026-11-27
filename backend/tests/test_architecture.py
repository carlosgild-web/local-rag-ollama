"""CLAUDE.md invariant 1, one service layer: routes and the CLI never write to SQLite,
Chroma or the file store themselves. They call versioning/ and ingest/, which do.

Checked on the source: no session writes (add, delete, merge...), no SQL insert, update or
delete statements, no vector-store writes and no file-store writes in app/api/routes/ or
app/cli.py.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
FILES = sorted((APP / "api" / "routes").glob("*.py")) + [APP / "cli.py"]

SESSION_WRITES = {"add", "add_all", "delete", "merge", "bulk_save_objects", "bulk_insert_mappings"}
VECTOR_WRITES = {"add", "upsert", "delete", "delete_collection", "create_collection"}
WRITE_FUNCTIONS = {"insert", "update", "delete", "store_file"}
# `@router.delete(...)` declares an HTTP route; `runtime.ollama.delete` removes a model from
# Ollama (the Models page), not data of this app.
ALLOWED_RECEIVERS = {"router", "ollama"}


def _receiver(node: ast.expr) -> str:
    """The last name before the method: `runtime.vector_store.add` -> "vector_store"."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _writes(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            receiver = _receiver(func.value)
            if receiver in ALLOWED_RECEIVERS:
                continue
            vector_write = "vector_store" in receiver and func.attr in VECTOR_WRITES
            if vector_write or func.attr in SESSION_WRITES:
                found.append(f"{path.name}:{node.lineno} {receiver}.{func.attr}")
        elif isinstance(func, ast.Name) and func.id in WRITE_FUNCTIONS:
            found.append(f"{path.name}:{node.lineno} {func.id}()")
    return found


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_routes_and_the_cli_write_only_through_the_service_layer(path):
    assert _writes(path) == []


def test_the_check_finds_a_direct_write(tmp_path):
    bad = tmp_path / "bad_route.py"
    bad.write_text(
        "def f(db, runtime, doc):\n"
        "    db.add(doc)\n"
        "    runtime.vector_store.delete(['1'])\n"
        "    store_file(doc, None)\n",
        encoding="utf-8",
    )
    assert len(_writes(bad)) == 3
