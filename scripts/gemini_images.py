"""Makes the demo site's images with Google Gemini (a build-time tool; the app never calls it).

Uses the free-tier API key in the GEMINI_API_KEY environment variable. The key is
sent only in a request header and is never printed, logged or put in a URL.
Run from the repo root with the backend's Python (it already has httpx and Pillow):

    backend/.venv/Scripts/python scripts/gemini_images.py check
    backend/.venv/Scripts/python scripts/gemini_images.py generate [--only NAME ...] [--model M]
    backend/.venv/Scripts/python scripts/gemini_images.py prompts   # prompts for manual use
    backend/.venv/Scripts/python scripts/gemini_images.py sheet     # a page for the Gemini app

Jobs come from scripts/gemini_jobs.json and run in order. Each result is saved as
data/gemini/raw/<name>.png (git-ignored), so a later run skips finished jobs.
When the free quota runs out (HTTP 429) the run stops; run it again later.
Then scripts/prepare_site_photos.py turns the raw images into the site's WebP files.
"""

import argparse
import base64
import datetime as dt
import html
import io
import json
import os
import sys
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "scripts" / "gemini_jobs.json"
RAW = ROOT / "data" / "gemini" / "raw"
MANIFEST = ROOT / "data" / "gemini" / "manifest.json"
API = "https://generativelanguage.googleapis.com/v1beta"


class QuotaExhausted(Exception):
    """The free quota (or a rate limit) is used up for now."""


def api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        sys.exit(
            "GEMINI_API_KEY isn't set. Create a key at https://aistudio.google.com, then in your "
            'own PowerShell run: setx GEMINI_API_KEY "<key>" and restart the terminal.'
        )
    return key


def is_quota_error(status: int, body: str) -> bool:
    return status == 429 or "RESOURCE_EXHAUSTED" in body


def client() -> httpx.Client:
    return httpx.Client(base_url=API, headers={"x-goog-api-key": api_key()}, timeout=180)


def image_models(http: httpx.Client) -> list[str]:
    """Model ids that can generate images with generateContent."""
    names, page = [], None
    while True:
        response = http.get(
            "/models", params={"pageSize": 200, **({"pageToken": page} if page else {})}
        )
        response.raise_for_status()
        data = response.json()
        for model in data.get("models", []):
            methods = model.get("supportedGenerationMethods", [])
            if "generateContent" in methods and "image" in model["name"].lower():
                names.append(model["name"].removeprefix("models/"))
        page = data.get("nextPageToken")
        if not page:
            return names


def pick_model(http: httpx.Client, wanted: str | None) -> str:
    if wanted:
        return wanted
    models = image_models(http)
    if not models:
        sys.exit(
            "This key has no image-capable Gemini model. "
            "See docs/site-images.md for the manual route."
        )
    # Prefer a stable "flash" image model; previews and "pro" come after.
    models.sort(key=lambda m: ("preview" in m, "flash" not in m, m))
    return models[0]


def png_bytes(path: Path) -> bytes:
    with Image.open(path) as image:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "PNG")
        return buffer.getvalue()


def build_prompt(job: dict, spec: dict) -> str:
    if "product" in job:
        return f"{spec['product_style']} The object: {job['product']}. {spec['style']}"
    return f"{job['prompt']} {spec['style']}"


def generate_one(
    http: httpx.Client, model: str, prompt: str, reference: Path | None, aspect: str
) -> bytes:
    parts: list[dict] = [{"text": prompt}]
    if reference:
        data = base64.b64encode(png_bytes(reference)).decode()
        parts.append({"inline_data": {"mime_type": "image/png", "data": data}})
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": aspect},
        },
    }
    response = http.post(f"/models/{model}:generateContent", json=body)
    if response.status_code == 400 and "imageConfig" in response.text:
        # An older image model without aspect-ratio support: ask without it.
        body["generationConfig"].pop("imageConfig")
        response = http.post(f"/models/{model}:generateContent", json=body)
    if is_quota_error(response.status_code, response.text):
        raise QuotaExhausted(_short_error(response))
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {_short_error(response)}")
    for candidate in response.json().get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise RuntimeError("the response had no image (the model may have declined the prompt)")


def _short_error(response: httpx.Response) -> str:
    try:
        return response.json().get("error", {}).get("message", "")[:300]
    except ValueError:
        return response.text[:300]


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}


def cmd_check(args) -> int:
    with client() as http:
        models = image_models(http)
        print("Image-capable models for this key:", ", ".join(models) or "none")
        model = pick_model(http, args.model)
        print(f"Test image with {model} ...")
        try:
            image = generate_one(
                http,
                model,
                "A single round blue glass bead on white paper, product photo.",
                None,
                "1:1",
            )
        except QuotaExhausted as error:
            print(f"No free quota for image generation right now: {error}")
            return 2
        RAW.mkdir(parents=True, exist_ok=True)
        (RAW.parent / "check.png").write_bytes(image)
        print(f"OK: {len(image) // 1024} KB image saved to data/gemini/check.png")
    return 0


def cmd_generate(args) -> int:
    spec = json.loads(JOBS.read_text(encoding="utf-8"))
    jobs = [j for j in spec["jobs"] if not args.only or j["name"] in args.only]
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    todo = [j for j in jobs if args.force or not (RAW / f"{j['name']}.png").exists()]
    print(f"{len(jobs) - len(todo)} of {len(jobs)} already done; {len(todo)} to make.")
    done = 0
    with client() as http:
        model = pick_model(http, args.model)
        print(f"Model: {model}")
        for job in todo:
            reference = ROOT / job["reference"] if job.get("reference") else None
            prompt = build_prompt(job, spec)
            try:
                image = generate_one(http, model, prompt, reference, job.get("aspect", "1:1"))
            except QuotaExhausted as error:
                left = len(todo) - done
                print(f"\nQuota reached after {done} new image(s); {left} left. Run again later.")
                print(f"  ({error})")
                return 3
            except RuntimeError as error:
                print(f"  {job['name']}: skipped, {error}")
                continue
            (RAW / f"{job['name']}.png").write_bytes(image)
            manifest[job["name"]] = {
                "model": model,
                "date": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "prompt": prompt,
                "reference": job.get("reference"),
            }
            MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            done += 1
            print(f"  {job['name']}: saved ({len(image) // 1024} KB)")
    print(f"\nFinished: {done} new image(s).")
    return 0


def cmd_prompts(_args) -> int:
    spec = json.loads(JOBS.read_text(encoding="utf-8"))
    for job in spec["jobs"]:
        ref = f"  [attach: {job['reference']}]" if job.get("reference") else ""
        print(f"## {job['name']} ({job.get('aspect', '1:1')}){ref}\n{build_prompt(job, spec)}\n")
    return 0


ASPECT_WORDS = {
    "1:1": "square (1:1)",
    "4:3": "landscape (4:3)",
    "16:9": "wide landscape (16:9)",
    "21:9": "very wide panoramic (21:9)",
}


def manual_prompt(job: dict, spec: dict) -> str:
    """The prompt for the Gemini app, which takes the shape from the words."""
    shape = ASPECT_WORDS.get(job.get("aspect", "1:1"), job.get("aspect", "1:1"))
    attach = "Use the attached image as the reference. " if job.get("reference") else ""
    return f"Create a {shape} image. {attach}{build_prompt(job, spec)}"


def cmd_sheet(_args) -> int:
    """Writes data/gemini/prompts.html: every job with its reference and a copy button."""
    spec = json.loads(JOBS.read_text(encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW.parent / "prompts.html"
    cards = []
    for number, job in enumerate(spec["jobs"], 1):
        done = any(
            (RAW / f"{job['name']}{ext}").exists() for ext in (".png", ".jpg", ".jpeg", ".webp")
        )
        ref = ""
        if job.get("reference"):
            rel = os.path.relpath(ROOT / job["reference"], out.parent).replace("\\", "/")
            ref = (
                f'<figure><img src="{html.escape(rel)}" alt="reference render" draggable="true">'
                f"<figcaption>Attach this reference (drag it into Gemini)</figcaption></figure>"
            )
        cards.append(
            f'<section class="{"done" if done else ""}"><h2>{number}. <code>{job["name"]}</code>'
            f"{' ✓ saved' if done else ''}</h2>"
            f"<p>Save as <code>data/gemini/raw/{job['name']}.png</code></p>{ref}"
            f"<textarea readonly>{html.escape(manual_prompt(job, spec))}</textarea>"
            f'<button type="button">Copy prompt</button></section>'
        )
    out.write_text(
        SHEET.replace("{{cards}}", "\n".join(cards)).replace("{{count}}", str(len(cards))),
        encoding="utf-8",
    )
    print(f"Wrote {out.relative_to(ROOT)} ({len(cards)} prompts)")
    return 0


SHEET = (ROOT / "scripts" / "gemini_sheet.html").read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="list image models and make one test image")
    check.add_argument("--model")
    gen = sub.add_parser("generate", help="make the images in gemini_jobs.json")
    gen.add_argument("--only", nargs="*", help="job names to make")
    gen.add_argument("--model")
    gen.add_argument("--force", action="store_true", help="remake images that already exist")
    sub.add_parser("prompts", help="print every prompt, for use in the Gemini app")
    sub.add_parser("sheet", help="write data/gemini/prompts.html for the Gemini app")
    args = parser.parse_args()
    return {
        "check": cmd_check,
        "generate": cmd_generate,
        "prompts": cmd_prompts,
        "sheet": cmd_sheet,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
