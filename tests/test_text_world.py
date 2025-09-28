import random

import pytest

from text_world import TextWorld


def test_notable_objects_hidden_after_examine(monkeypatch):
    world = TextWorld()
    world.agent_location = "kitchen"
    world.world_time = 10

    world.world_state["kitchen"]["fridge"]["state"] = "open"
    world.random.random = lambda: 1.0  # prevent idle surfacing
    world.process_action({"verb": "examine", "target": "fridge"})

    state = world.get_world_state()
    assert not any(evt.get("object") == "fridge" and evt.get("details") == "open" for evt in state["sensory_events"])  # hidden

    for _ in range(4):
        world.update()
    world.random.random = lambda: 0.0
    world.random.choice = lambda seq: seq[0]
    state = world.get_world_state()
    assert any(evt.get("object") == "fridge" for evt in state["sensory_events"])  # resurfaced


def test_openable_auto_closes(monkeypatch):
    world = TextWorld()
    world.agent_location = "kitchen"
    world.world_state["kitchen"]["fridge"]["state"] = "closed"

    world.process_action({"verb": "open", "target": "fridge"})
    assert world.world_state["kitchen"]["fridge"]["state"] == "open"

    for _ in range(4):
        world.update()
    assert world.world_state["kitchen"]["fridge"]["state"] == "closed"


def test_idle_object_prompt(monkeypatch):
    world = TextWorld()
    world.agent_location = "living_room"

    world.random.random = lambda: 0.0
    world.random.choice = lambda seq: seq[0]

    state = world.get_world_state()
    assert any(evt.get("details") == "idle" for evt in state["sensory_events"])  # idle surfaced


def test_action_rejects_missing_objects():
    world = TextWorld()
    world.agent_location = "living_room"
    res = world.process_action({"verb": "open", "target": "fridge"})
    assert res["success"] is False
    assert "don't see" in res["reason"] or "can't open" in res["reason"]


def test_goal_progress_tracks_steps():
    world = TextWorld()
    world.active_goal = {
        "name": "Assist the neighbor",
        "steps": [{"room": "living_room", "action": "help", "target": "neighbor"}],
    }
    world.goal_progress_index = 0
    world.current_goal_steps_done = []
    world.neighbor_state.update({"awaiting_help": True, "request_cycle": world.world_time})

    world.process_action({"verb": "help", "target": "neighbor"})
    state = world.get_world_state()
    assert state["goal_history"]  # records completion


def test_help_neighbor_increases_trust():
    world = TextWorld()
    world.neighbor_state.update({"awaiting_help": True, "request_cycle": world.world_time})
    before = world.relationships["neighbor"]["trust"]
    res = world.process_action({"verb": "help", "target": "neighbor"})
    assert res["success"] is True
    after = world.relationships["neighbor"]["trust"]
    assert after > before


if __name__ == "__main__":
    pytest.main([__file__])
