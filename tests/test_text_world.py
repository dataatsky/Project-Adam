import random

import pytest

from text_world import TextWorld


def test_notable_objects_hidden_after_examine(monkeypatch):
    world = TextWorld()
    world.agent_location = "kitchen"
    world.world_time = 10

    world.world_state["kitchen"]["fridge"]["state"] = "open"
    world.process_action({"verb": "examine", "target": "fridge"})

    state = world.get_world_state()
    assert not any(evt.get("object") == "fridge" for evt in state["sensory_events"])  # hidden

    world.world_time += 4
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

    monkeypatch.setattr(random, "random", lambda: 0.0)
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])

    state = world.get_world_state()
    assert any(evt.get("details") == "idle" for evt in state["sensory_events"])  # idle surfaced


def test_action_rejects_missing_objects():
    world = TextWorld()
    world.agent_location = "living_room"
    res = world.process_action({"verb": "open", "target": "fridge"})
    assert res["success"] is False
    assert "don't see" in res["reason"] or "can't open" in res["reason"]


if __name__ == "__main__":
    pytest.main([__file__])
