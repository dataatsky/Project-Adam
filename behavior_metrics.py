"""Per-episode behaviour metrics used to compare personalities.

An episode is the list of steps an agent took: for each cycle, the action it
chose, the world's result, and where it was before and after acting.
"""
from statistics import mean, pstdev
from typing import Dict, List

METRICS = ("exploration", "coverage", "novelty", "wait_ratio", "social_ratio", "success_rate")

METRIC_HELP = {
    "exploration": "share of cycles spent moving into a room not visited before",
    "coverage": "share of the house's rooms visited",
    "novelty": "distinct (verb, target) pairs / cycles",
    "wait_ratio": "share of cycles spent waiting",
    "social_ratio": "share of cycles spent talking or helping",
    "success_rate": "share of actions that succeeded",
}


def episode_metrics(steps: List[Dict], total_rooms: int) -> Dict[str, float]:
    """steps: [{"verb", "target", "success", "room_before", "room_after"}, ...]"""
    n = len(steps)
    if n == 0:
        return {m: 0.0 for m in METRICS}
    visited = set()
    new_rooms = 0
    for step in steps:
        visited.add(step["room_before"])
        if step["room_after"] not in visited:
            new_rooms += 1
        visited.add(step["room_after"])
    pairs = {(s["verb"], s.get("target")) for s in steps}
    return {
        "exploration": new_rooms / n,
        "coverage": len(visited) / max(1, total_rooms),
        "novelty": len(pairs) / n,
        "wait_ratio": sum(1 for s in steps if s["verb"] == "wait") / n,
        "social_ratio": sum(1 for s in steps if s["verb"] in {"say", "help"}) / n,
        "success_rate": sum(1 for s in steps if s["success"]) / n,
    }


def summarize(episodes: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    """Mean and standard deviation of each metric across episodes."""
    out = {}
    for m in METRICS:
        values = [e[m] for e in episodes]
        out[m] = {"mean": mean(values) if values else 0.0, "sd": pstdev(values) if len(values) > 1 else 0.0}
    return out
