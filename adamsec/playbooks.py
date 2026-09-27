"""Synthetic adversary playbooks for the Adam security harness."""

from typing import List, Dict


_PLAYBOOKS: Dict[str, List[Dict]] = {
    "perception_conflict": [
        {"attack": "perception.inject_conflict", "cycles": 5, "params": {"intensity": "high"}},
    ],
    "mixed_alignment": [
        {"attack": "perception.inject_conflict", "cycles": 3},
        # starts once the perception attack (cycles 1-3) has ended, so each effect is attributable
        {"attack": "prompt.inject_alignment_attack", "cycles": 4, "start_cycle": 4},
    ],
}


def load_playbook(name: str | None) -> List[Dict]:
    if not name:
        return []
    return [dict(step) for step in _PLAYBOOKS.get(name, [])]

