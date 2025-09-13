from collections import deque, defaultdict


class InsightEngine:
    """Lightweight, non-LLM insight and KPI engine over recent loop history."""

    def __init__(self, history_len: int = 24):
        self.actions = deque(maxlen=history_len)         # {verb, target, success}
        self.impulses = deque(maxlen=history_len)        # [ {verb, target, urgency} ]
        self.triggers = deque(maxlen=history_len)        # ["phone: ringing", …]
        self.moods = deque(maxlen=history_len)           # ["calm", …]

    def add_cycle(self, *, action: dict, success: bool, impulses: list, triggers: list, mood: str):
        self.actions.append({"verb": action.get("verb"), "target": action.get("target"), "success": bool(success)})
        self.impulses.append(impulses or [])
        self.triggers.append(triggers or [])
        self.moods.append(mood or "")

    # KPI helpers
    def _frustration(self, n=10):
        recent = list(self.actions)[-n:]
        if not recent:
            return 0.0
        fails = sum(1 for a in recent if not a.get("success"))
        return round(fails / len(recent), 2)

    def _conflict(self):
        if not self.impulses or not self.actions:
            return 0.0
        last_imps = self.impulses[-1] or []
        chosen = self.actions[-1]
        highs = [imp for imp in last_imps if float(imp.get("urgency", 0)) >= 0.7]
        if not highs:
            return 0.0
        suppressed = [
            imp for imp in highs
            if not (imp.get("verb") == chosen.get("verb") and imp.get("target") == chosen.get("target"))
        ]
        return round(len(suppressed) / len(highs), 2)

    def _novelty(self, n=10):
        recent = list(self.triggers)[-n:]
        flat = [t for L in recent for t in L]
        if len(flat) <= 1:
            return 0.0
        return round(len(set(flat)) / len(flat), 2)

    def _loop_score(self, n=10):
        recent = list(self.actions)[-n:]
        if not recent:
            return 0.0
        best = 0
        streak = 0
        last_pair = None
        for a in recent:
            pair = (a.get("verb"), a.get("target"))
            if pair == last_pair and not a.get("success"):
                streak += 1
            else:
                streak = 1 if not a.get("success") else 0
            last_pair = pair
            best = max(best, streak)
        return round(min(1.0, best / max(1, n / 2)), 2)

    def _goal_progress(self, last_action):
        helpful = {"investigate", "answer", "go", "turn_on", "open"}
        detour = {"sleep", "read", "eat"}
        v = (last_action or {}).get("verb")
        t = (last_action or {}).get("target")
        if v in helpful:
            return 0.7 if t in {"door", "phone", "tv", "radio", "computer"} else 0.5
        if v in detour:
            return 0.2
        return 0.3

    def compute_kpis(self):
        last_action = self.actions[-1] if self.actions else {}
        return {
            "frustration": self._frustration(10),
            "conflict": self._conflict(),
            "novelty": self._novelty(10),
            "goal_progress": round(self._goal_progress(last_action), 2),
            "loop_score": self._loop_score(10),
        }

    def badges(self, kpis):
        out = []
        if kpis.get("loop_score", 0) >= 0.6:
            out.append({"type": "Loop", "text": "Repeating failed attempts"})
        if kpis.get("frustration", 0) >= 0.6:
            out.append({"type": "Frustration", "text": "Many recent failures"})
        if kpis.get("conflict", 0) >= 0.6:
            out.append({"type": "Avoidance", "text": "Strong impulses suppressed"})
        return out

    def threads(self):
        buckets = defaultdict(list)
        for a in self.actions:
            buckets[a.get("target")] += [a]
        threads = []
        for target, acts in buckets.items():
            if not target:
                continue
            succ = sum(1 for a in acts if a.get("success"))
            total = len(acts)
            threads.append({
                "name": f"{target.title()} storyline",
                "target": target,
                "progress": round(succ / max(1, total), 2),
                "recent": [f"{x.get('verb')} -> {'ok' if x.get('success') else 'fail'}" for x in acts[-2:]],
            })
        # sort by recency
        order = {t: i for i, t in enumerate([a.get("target") for a in self.actions][::-1])}
        threads.sort(key=lambda th: order.get(th["target"], 999))
        return threads

    def causal_line(self, *, triggers, impulses, action, imagined, simulated, emotional_delta):
        trig_txt = ", ".join((triggers or [])[:2]) or "none"
        top = None
        if impulses:
            top = sorted(impulses, key=lambda x: x.get("urgency", 0), reverse=True)[0]
        top_txt = f"{top.get('verb')} {top.get('target')} ({top.get('urgency', 0):.2f})" if top else "none"
        act_txt = f"{(action or {}).get('verb')} {(action or {}).get('target')}"
        out_txt = (simulated or "").split(".")[0]
        mood_txt = ""
        if emotional_delta:
            mood_txt = f" → mood {emotional_delta.get('mood', '?')} ({emotional_delta.get('level_delta', 0):+0.2f})"
        return f"[{trig_txt}] → [{top_txt}] → [{act_txt}] → [{out_txt}]{mood_txt}"

    def cards(self, *, triggers, kpis, chosen, imagined, simulated, emotional_delta):
        change = f"Mood {emotional_delta.get('mood', 'same')} ({emotional_delta.get('level_delta', 0):+0.2f}); Frustration {kpis['frustration']}, Conflict {kpis['conflict']}"
        cause = "; ".join((triggers or [])[:2]) or "routine scan"
        why = f"{cause} → chose {chosen.get('verb')} {chosen.get('target')}"
        result = f"Imagined: {imagined[:60]}… | Simulated: {simulated[:60]}…"
        return [
            {"title": "What changed", "body": change},
            {"title": "Why", "body": why},
            {"title": "Result", "body": result},
        ]

