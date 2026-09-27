"""A rule-based stand-in for the LLM psyche.

Used by `python main.py --demo` to watch Adam in the 3D viewer without
Ollama, and handy as a simple baseline agent. It reads the same payloads the
LLM psyche gets and answers with the same shapes, following plain habits:
eat when hungry, sleep when tired, warm up when cold, talk to people when
lonely, otherwise explore and open things.
"""
import random
from typing import Dict, List, Optional


class DemoPsyche:
    def __init__(self, seed: Optional[int] = 0):
        self.random = random.Random(seed)

    # --- policy ----------------------------------------------------------------
    def _choices(self, current_state: Dict, ws: Dict) -> List[Dict]:
        needs = current_state.get("needs", {})
        objects = ws.get("perceivable_objects", [])
        exits = ws.get("exit_details", {})
        inventory = ws.get("inventory", [])
        people = ws.get("people_here", [])
        options: List[Dict] = []

        def add(verb, target=None, urgency=0.5, drive="curiosity"):
            options.append({"verb": verb, "target": target, "urgency": urgency, "drive": drive})

        def go_toward(room_name, urgency, drive):
            for direction, info in exits.items():
                if info.get("room") == room_name and info.get("door") != "locked":
                    add("go", direction, urgency, drive)
                    return True
            return False

        if needs.get("hunger", 0) >= 0.5:
            if "fridge" in objects:
                add("eat", "fridge", 0.95, "hunger")
                if "stove" in objects:
                    add("cook", "stove", 0.9, "hunger")
            elif not go_toward("kitchen", 0.9, "hunger"):
                self._explore(add, exits, 0.7, "hunger")
        if needs.get("fatigue", 0) >= 0.7:
            if "bed" in objects:
                add("sleep", "bed", 0.95, "rest")
            elif not go_toward("bedroom", 0.85, "rest"):
                self._explore(add, exits, 0.6, "rest")
        if needs.get("cold", 0) >= 0.5:
            if "blanket" in inventory:
                add("use", "blanket", 0.8, "warmth")
            elif "blanket" in ws.get("visible_items", []):
                add("take", "blanket", 0.8, "warmth")
            elif "window" in objects:
                add("close", "window", 0.6, "warmth")
        if people:
            add("say", f"Hello {people[0]}, how are you?", 0.6 + 0.4 * needs.get("loneliness", 0), "company")
        for event in ws.get("sensory_events", []):
            if event.get("object") == "neighbor" and event.get("details") == "awaiting_help":
                add("help", "neighbor", 0.85, "kindness")
        for item in ws.get("visible_items", []):
            add("take", item, 0.55, "curiosity")
        for container in ws.get("closed_containers", []):
            add("open", container, 0.5, "curiosity")
        self._explore(add, exits, 0.45, "curiosity")
        for obj in objects:
            add("examine", obj, 0.25, "curiosity")
        if not options:
            add("wait", None, 0.1, "rest")
        # a little variety so the demo doesn't look scripted
        for opt in options:
            opt["urgency"] = round(min(1.0, opt["urgency"] + self.random.uniform(0, 0.08)), 2)
        return sorted(options, key=lambda o: -o["urgency"])

    def _explore(self, add, exits: Dict, urgency: float, drive: str):
        unexplored = [d for d, info in exits.items() if not info.get("visited") and info.get("door") != "locked"]
        open_exits = [d for d, info in exits.items() if info.get("door") != "locked"]
        pool = unexplored or open_exits
        if pool:
            add("go", self.random.choice(pool), urgency if unexplored else urgency * 0.6, drive)

    def _shift(self, current_state: Dict) -> Dict:
        needs = current_state.get("needs", {})
        worst = max(needs, key=needs.get) if needs else None
        mood = {"hunger": "hungry", "fatigue": "tired", "cold": "anxious", "loneliness": "sad"}.get(worst, "curious")
        if not worst or needs[worst] < 0.5:
            mood = "curious"
        return {"mood": mood, "level_delta": 0.0, "reason": f"{worst or 'nothing'} on my mind"}

    # --- psyche interface --------------------------------------------------------
    def generate_impulse(self, payload: Dict) -> Dict:
        choices = self._choices(payload.get("current_state", {}), payload.get("world_state", {}))
        return {"emotional_shift": self._shift(payload.get("current_state", {})), "impulses": choices[:3]}

    def imagine_batch(self, actions, seed=None, trace=False) -> Dict:
        return {"outcomes": [f"I expect to {a.get('verb')} {a.get('target') or ''}".strip() + "." for a in actions]}

    def reflect(self, payload: Dict) -> Dict:
        options = payload.get("hypothetical_outcomes") or []
        action = options[0]["action"] if options else {"verb": "wait", "target": None}
        target = f" {action.get('target')}" if action.get("target") else ""
        return {"final_action": action, "reasoning": f"My strongest urge is to {action.get('verb')}{target}.",
                "goal_status": "continue"}

    def decide(self, payload: Dict) -> Dict:
        impulses = self.generate_impulse(payload)
        action = {k: impulses["impulses"][0].get(k) for k in ("verb", "target")}
        return {**impulses, "final_action": action, "reasoning": f"I follow my strongest urge: {action['verb']}.",
                "goal_status": "continue"}

    def theory_of_mind(self, other_agent_id, environment_desc="", recent_actions="", relationship_context="", **_):
        return {"agent_id": other_agent_id, "predicted_goal": "unclear", "beliefs": [], "trust_level": 0.5,
                "potential_threat": False}

    def consolidate(self, recent_memories, seed=None, trace=False) -> Dict:
        return {"insight": "Sleep helps me sort out the day."}
