"""Adam's temperament: trait values (0-1) turned into words the LLM acts on.

Traits reach both prompts through `describe()` (see templates/_preamble.j2),
and `personality_experiment.py` measures whether different presets behave
differently in the same world.
"""
from typing import Dict, Optional

TRAITS = ("curiosity", "bravery", "caution")

# (threshold, word) from high to low; the first threshold the value reaches wins
_WORDS = {
    "curiosity": [(0.75, "very curious"), (0.5, "curious"), (0.25, "not very curious"), (0.0, "incurious")],
    "bravery": [(0.75, "very brave"), (0.5, "brave"), (0.25, "timid"), (0.0, "very timid")],
    "caution": [(0.75, "very cautious"), (0.5, "cautious"), (0.25, "somewhat careless"), (0.0, "reckless")],
}

PRESETS: Dict[str, Dict[str, float]] = {
    "balanced": {"curiosity": 0.5, "bravery": 0.5, "caution": 0.5},
    "curious": {"curiosity": 0.9, "bravery": 0.7, "caution": 0.2},
    "cautious": {"curiosity": 0.2, "bravery": 0.2, "caution": 0.9},
    "bold": {"curiosity": 0.6, "bravery": 0.9, "caution": 0.1},
}


def _word(trait: str, value: float) -> str:
    for threshold, word in _WORDS[trait]:
        if value >= threshold:
            return word
    return _WORDS[trait][-1][1]


def describe(personality: Optional[Dict[str, float]]) -> str:
    """e.g. "very curious, timid, cautious" (empty when no traits are given)."""
    words = []
    for trait in TRAITS:
        value = (personality or {}).get(trait)
        try:
            words.append(_word(trait, float(value)))
        except (TypeError, ValueError):
            continue
    return ", ".join(words)
