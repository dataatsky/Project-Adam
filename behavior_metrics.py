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


# --- Habits over long runs --------------------------------------------------------

def _action(step: Dict) -> str:
    target = step.get("target")
    return f"{step['verb']} {target}" if target not in (None, "", "null") else step["verb"]


def _distribution(steps: List[Dict]) -> Dict[str, float]:
    counts: Dict[str, int] = {}
    for s in steps:
        counts[_action(s)] = counts.get(_action(s), 0) + 1
    total = sum(counts.values()) or 1
    return {a: c / total for a, c in counts.items()}


def action_entropy(steps: List[Dict]) -> float:
    """How varied the actions are: 0 = always the same action, 1 = every action different (normalized)."""
    import math

    dist = _distribution(steps)
    if len(dist) <= 1:
        return 0.0
    h = -sum(p * math.log2(p) for p in dist.values())
    return h / math.log2(len(steps)) if len(steps) > 1 else 0.0


def js_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
    """Jensen-Shannon divergence (base 2, 0..1) between two action distributions."""
    import math

    keys = set(p) | set(q)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in keys}

    def kl(a):
        return sum(a[k] * math.log2(a[k] / m[k]) for k in keys if a.get(k, 0) > 0)

    return (kl(p) + kl(q)) / 2


def habit_windows(steps: List[Dict], window: int = 20) -> List[Dict]:
    """Per window: entropy, actions never seen before, and drift from the previous window."""
    rows, seen, prev = [], set(), None
    for start in range(0, len(steps), window):
        chunk = steps[start:start + window]
        if not chunk:
            break
        actions = {_action(s) for s in chunk}
        dist = _distribution(chunk)
        rows.append({
            "cycles": f"{start + 1}-{start + len(chunk)}",
            "entropy": round(action_entropy(chunk), 3),
            "new_actions": len(actions - seen),
            "drift": None if prev is None else round(js_divergence(prev, dist), 3),
            "top": max(dist, key=dist.get),
        })
        seen |= actions
        prev = dist
    return rows


def top_routines(steps: List[Dict], n: int = 5, length: int = 2) -> List[tuple]:
    """Most frequent consecutive action sequences, e.g. (("go north", "eat fridge"), 6)."""
    counts: Dict[tuple, int] = {}
    actions = [_action(s) for s in steps]
    for i in range(len(actions) - length + 1):
        seq = tuple(actions[i:i + length])
        if len(set(seq)) > 1:  # a routine links different actions
            counts[seq] = counts.get(seq, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:n]


def top_actions(steps: List[Dict], n: int = 5) -> List[tuple]:
    dist = _distribution(steps)
    return sorted(((a, round(p, 3)) for a, p in dist.items()), key=lambda kv: -kv[1])[:n]
