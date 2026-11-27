"""Pass 1 of the README video (decision 0043): the storyboard's script on the real model,
with no browser and no recorder on the laptop.

Runs against `start.cmd video` (real Ollama) and follows the storyboard's `script`, the
same steps the take does, through the same API the web app calls:

- `intake:<folder>`: the files are analysed (POST /api/intake), confirmed as suggested,
  and indexed, so the library matches the take's at each question;
- `ask:<turn>`: the retrieval inspector gives the exact prompt the chat will send (same
  code, read only), then the question is asked through the chat (POST /api/chat). Every
  SSE event is saved with its time: the model's answer, word for word, and how long it took.

Pass 2 (replay_server.py + `npm run video:ollama`) replays those answers through the app
while the browser records, matched by the prompt's SHA-256.

    backend/.venv/Scripts/python video/capture.py --base http://127.0.0.1:8010 --out video/out/pass1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def prompt_sha(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def shelf_id(client: httpx.Client, name: str) -> int:
    shelves = client.get("/api/collections").json()
    return next(c["id"] for c in shelves if c["name"] == name and c.get("is_active", True))


def wait_jobs(client: httpx.Client, job_ids: list[int]) -> None:
    while True:
        jobs = {j["id"]: j for j in client.get("/api/jobs").json()}
        states = [jobs.get(i, {}).get("status") for i in job_ids]
        if any(s == "failed" for s in states):
            raise SystemExit(f"a job failed: {states}")
        if all(s == "completed" for s in states):
            return
        time.sleep(2)


def intake(client: httpx.Client, folder: Path) -> dict:
    """Analyse the folder's files and confirm the suggestions as they are (the take's clicks)."""
    paths = sorted(p for p in folder.iterdir() if p.is_file())
    files = [("files", (p.name, p.read_bytes())) for p in paths]
    batch = client.post("/api/intake", files=files).json()["batch_id"]
    while (result := client.get(f"/api/intake/{batch}").json())["state"] != "ready":
        time.sleep(2)
    body = {
        "new_shelves": {s["ref"]: s["name"] for s in result["shelves"] if not s["existing"]},
        "files": [
            {
                "key": f["key"],
                "include": f["include"],
                "shelf": f["shelf"] or "",
                "tags": f["tags"],
                "version_of": (f.get("similar_to") or {}).get("document_id")
                if f["include"]
                else None,
            }
            for f in result["files"]
        ],
    }
    confirmed = client.post(f"/api/intake/{batch}/confirm", json=body)
    confirmed.raise_for_status()
    wait_jobs(client, confirmed.json()["job_ids"])
    return {
        "files": [
            {k: f[k] for k in ("name", "status", "shelf", "tags", "include")}
            for f in result["files"]
        ]
    }


def ask(client: httpx.Client, question: str, shelf: str) -> dict:
    cid = shelf_id(client, shelf)
    inspect = client.post(
        "/api/retrieve/inspect",
        json={"question": question, "scope": "shelf", "collection_id": cid, "include_prompt": True},
    ).json()
    events: list[dict] = []
    started = time.monotonic()
    body = {"question": question, "collection_id": cid}
    with client.stream("POST", "/api/chat", json=body, timeout=None) as response:
        response.raise_for_status()
        kind = "message"
        for line in response.iter_lines():
            if line.startswith("event:"):
                kind = line[6:].strip()
            elif line.startswith("data:"):
                t_ms = round((time.monotonic() - started) * 1000)
                events.append({"t_ms": t_ms, "event": kind, "data": json.loads(line[5:])})
                if kind != "token":
                    print(f"  {t_ms / 1000:7.1f} s  {kind}", flush=True)
    tokens = [e for e in events if e["event"] == "token"]
    sources = next((e for e in events if e["event"] == "sources"), None)
    done = next((e for e in events if e["event"] in ("done", "error")), None)
    answer = "".join(e["data"]["text"] for e in tokens)
    return {
        "question": question,
        "shelf": shelf,
        "expanded_question": inspect["expanded_question"],
        "prompt_sha256": prompt_sha(inspect["prompt"]) if inspect.get("prompt") else None,
        # The inspector's ranking must be the order the chat sent: the same search.
        "inspected_chunk_ids": [c["chunk_id"] for c in inspect["chunks"] if c["sent"]],
        "sources": [
            {k: s.get(k) for k in ("rank", "chunk_id", "filename", "page", "score")}
            for s in (sources["data"] if sources else [])
        ],
        "model_called": bool(
            done and done["event"] == "done" and not done["data"].get("not_found")
        ),
        # Model time: from the passages to the first word, then each word's delay after the last.
        "first_token_ms": tokens[0]["t_ms"] - (sources["t_ms"] if sources else 0)
        if tokens
        else None,
        "pieces": [
            {
                "text": e["data"]["text"],
                "after_ms": e["t_ms"] - (tokens[i - 1]["t_ms"] if i else e["t_ms"]),
            }
            for i, e in enumerate(tokens)
        ],
        "answer": answer,
        "end": done,
        "wall_ms": round((time.monotonic() - started) * 1000),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://127.0.0.1:8010")
    parser.add_argument("--out", default=str(HERE / "out" / "pass1"))
    args = parser.parse_args()
    board = json.loads((HERE / "storyboard-ollama.json").read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    problems = 0
    with httpx.Client(base_url=args.base, timeout=120) as client:
        model = client.get("/api/profiles").json()
        for step_no, step in enumerate(board["script"], start=1):
            kind, _, key = step.partition(":")
            print(f"== {step_no}. {step}", flush=True)
            if kind == "intake":
                result = intake(client, ROOT / board["intake"][key])
                print(
                    f"   {[(f['name'], f['status'], f['shelf']) for f in result['files']]}",
                    flush=True,
                )
            elif kind == "ask":
                turn = board["turns"][key]
                run = ask(client, turn["question"], turn["shelf"])
                run["model"] = next(
                    (p["chat_model"] for p in model if p.get("is_active", True)), None
                )
                (out / f"{step_no:02d}-{key}.json").write_text(
                    json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"   {run['answer']!r} ({run['wall_ms'] / 1000:.0f} s)", flush=True)
                if run["end"] is None or run["end"]["event"] != "done":
                    problems += 1
                if run["inspected_chunk_ids"] != [s["chunk_id"] for s in run["sources"]]:
                    print(
                        "   ! the inspector's ranking differs from the chat's sources", flush=True
                    )
                    problems += 1
            else:
                raise SystemExit(f"unknown script step {step!r}")
    print("pass 1: done" if not problems else f"pass 1: {problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
