"""Append-only history of benchmark and experiment results.

Every run of benchmark.py / personality_experiment.py appends one JSON object
per scenario (or preset) to a .jsonl file, tagged with the model, git commit,
seeds and settings, so later changes can be compared against earlier ones.
"""
import json
import math
import os
import subprocess
import time
from typing import Dict, Iterable, List, Optional, Tuple

import config

DEFAULT_RESULTS = os.path.join("results", "benchmark_results.jsonl")


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval for a success rate; sensible even for 0/5 or 5/5."""
    if trials <= 0:
        return (0.0, 1.0)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def git_revision() -> str:
    """Short commit hash, with "+dirty" when the working tree has uncommitted changes."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip()
        return f"{sha}+dirty" if dirty else sha
    except Exception:
        return "unknown"


def run_context(**extra) -> Dict:
    """Fields that identify how a result was produced."""
    return {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git": git_revision(),
        "model": config.OLLAMA_MODEL,
        "think": config.OLLAMA_THINK,
        **extra,
    }


def append_results(records: Iterable[Dict], path: str = DEFAULT_RESULTS):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_results(path: str = DEFAULT_RESULTS, kind: Optional[str] = None) -> List[Dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if kind is None or row.get("kind") == kind:
                rows.append(row)
    return rows


def format_rate(successes: int, trials: int) -> str:
    """e.g. " 60% [23-88]" (success rate with its 95% interval)."""
    if trials <= 0:
        return "   n/a"
    lo, hi = wilson_interval(successes, trials)
    return f"{successes / trials:4.0%} [{lo * 100:.0f}-{hi * 100:.0f}]"
