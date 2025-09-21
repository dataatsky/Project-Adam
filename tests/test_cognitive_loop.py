from pathlib import Path

from loop.cognitive_loop import CognitiveLoop
from constants import LOG_HEADERS


class DummyInsight:
    def __init__(self):
        self.causal_args = None
        self.cards_args = None

    def add_cycle(self, **kwargs):
        pass

    def compute_kpis(self):
        return {}

    def causal_line(self, **kwargs):
        self.causal_args = kwargs
        return "causal"

    def cards(self, **kwargs):
        self.cards_args = kwargs
        return []

    def badges(self, _):
        return []

    def threads(self):
        return []


class WorldStub:
    def __init__(self):
        self.agent_location = "living_room"
        self.world_time = 1

    def process_action(self, action):
        return {"success": True, "reason": "door opens", "state_change": {}}


def test_cognitive_loop_passes_imagination_details(tmp_path: Path):
    log_file = tmp_path / "loop.csv"
    brain = CognitiveLoop(str(log_file), LOG_HEADERS)
    brain.insight = DummyInsight()
    brain.last_hypothetical = [
        {"action": {"verb": "open", "target": "door"}, "imagined": "door opens", "simulated": "door opens"}
    ]

    world = WorldStub()
    impulses = {"impulses": [{"verb": "open", "target": "door", "urgency": 0.9}], "emotional_shift": {}}
    brain.act(world, {"verb": "open", "target": "door"}, "because", {"sensory_events": []}, impulses)

    assert brain.insight.causal_args["imagined"] == "open door: door opens"
    assert brain.insight.cards_args["imagined"] == "open door: door opens"
