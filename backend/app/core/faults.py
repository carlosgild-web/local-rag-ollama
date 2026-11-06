"""Developer-only fault simulation (SIMULATE_FAULTS), so every troubleshooting
message can be seen in the browser without breaking anything for real.

Off by default. A simulated fault raises exactly where the real failure
would, with "(simulated)" in the message, and both /health and
/api/diagnostics report that simulation is on.
"""

FAULTS = {
    "sqlite": "the database can't be opened",
    "vector_store": "the vector store doesn't answer",
    "ollama_down": "Ollama can't be reached",
    "ollama_version": "Ollama reports an old version",
    "model_missing": "the chat model isn't installed",
    "low_memory": "free memory is very low",
    "worker": "the job worker isn't running",
}


class SimulatedFault(RuntimeError):
    pass


def active_faults(raw: str) -> set[str]:
    """Parses "sqlite, ollama_down" into known fault names (unknown ones ignored)."""
    return {name.strip() for name in raw.split(",") if name.strip() in FAULTS}


def simulate(raw: str, name: str) -> None:
    if name in active_faults(raw):
        raise SimulatedFault(f"{FAULTS[name]} (simulated)")
