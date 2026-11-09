"""scripts/gemini_images.py: quota errors stop a run cleanly, and prompts are built right.

The script is a build-time tool outside the app, loaded here by path. These tests
never call the Gemini API.
"""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gemini_images.py"
spec = importlib.util.spec_from_file_location("gemini_images", SCRIPT)
gemini = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gemini)


def test_quota_errors_are_recognized():
    assert gemini.is_quota_error(429, "")
    assert gemini.is_quota_error(400, '{"error": {"status": "RESOURCE_EXHAUSTED"}}')
    assert not gemini.is_quota_error(400, '{"error": {"status": "INVALID_ARGUMENT"}}')
    assert not gemini.is_quota_error(200, "")


def test_product_prompts_keep_the_reference_and_shared_style():
    spec = {"style": "STYLE.", "product_style": "Turn this render into a photo."}
    job = {
        "name": "GB-1001",
        "product": "three blue beads",
        "reference": "art/blender/GB-1001.webp",
    }
    prompt = gemini.build_prompt(job, spec)
    assert prompt.startswith("Turn this render into a photo.")
    assert "three blue beads" in prompt and prompt.endswith("STYLE.")
    manual = gemini.manual_prompt({**job, "aspect": "4:3"}, spec)
    assert manual.startswith(
        "Create a landscape (4:3) image. Use the attached image as the reference."
    )


def test_every_job_has_a_prompt_and_existing_reference():
    import json

    jobs = json.loads((SCRIPT.parent / "gemini_jobs.json").read_text(encoding="utf-8"))["jobs"]
    names = [job["name"] for job in jobs]
    assert len(names) == len(set(names))
    for job in jobs:
        assert job.get("prompt") or job.get("product"), job["name"]
        if job.get("reference"):
            assert (SCRIPT.parents[1] / job["reference"]).exists(), job["reference"]
