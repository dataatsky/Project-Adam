import random
import pytest
from text_world import TextWorld

def test_notable_objects_hidden_after_examine(monkeypatch):
    world = TextWorld()
    # Move to kitchen
    kitchen_coords = world.room_coords["kitchen"]
    world.agent_pos = kitchen_coords
    
    # Set fridge to open
    loc = world.map.get_location(*kitchen_coords)
    loc.objects["fridge"]["state"] = "open"
    
    world.random.random = lambda: 1.0  # prevent idle surfacing
    world.process_action({"verb": "examine", "target": "fridge"})

    state = world.get_world_state()
    # check if open fridge is hidden from sensory events (recently examined)
    assert not any(evt.get("object") == "fridge" and evt.get("details") == "open" for evt in state["sensory_events"])

    for _ in range(4):
        world.update()
    
    world.random.random = lambda: 0.0
    world.random.choice = lambda seq: seq[0]
    state = world.get_world_state()
    # check if it resurfaces
    assert any(evt.get("object") == "fridge" for evt in state["sensory_events"])


def test_openable_auto_closes(monkeypatch):
    world = TextWorld()
    # Move to kitchen
    kitchen_coords = world.room_coords["kitchen"]
    world.agent_pos = kitchen_coords
    
    loc = world.map.get_location(*kitchen_coords)
    loc.objects["fridge"]["state"] = "closed"

    world.process_action({"verb": "open", "target": "fridge"})
    assert loc.objects["fridge"]["state"] == "open"

    for _ in range(4):
        world.update()
    assert loc.objects["fridge"]["state"] == "closed"


def test_idle_object_prompt(monkeypatch):
    world = TextWorld()
    # Living room is default (0,0)
    world.agent_pos = (0, 0)

    world.random.random = lambda: 0.0
    world.random.choice = lambda seq: seq[0]

    state = world.get_world_state()
    assert any(evt.get("details") == "idle" for evt in state["sensory_events"])


def test_action_rejects_missing_objects():
    world = TextWorld()
    world.agent_pos = (0, 0) # Living room
    # Living room shouldn't have a fridge
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
    # Force neighbor state
    world.neighbor_state.update({"awaiting_help": True, "request_cycle": world.world_time})
    world.agent_pos = (0, 0) # Living room

    world.process_action({"verb": "help", "target": "neighbor"})
    state = world.get_world_state()
    assert state["goal_history"]  # records completion


def test_help_neighbor_increases_trust():
    world = TextWorld()
    world.neighbor_state.update({"awaiting_help": True, "request_cycle": world.world_time})
    world.agent_pos = (0, 0)
    
    before = world.relationships["neighbor"]["trust"]
    res = world.process_action({"verb": "help", "target": "neighbor"})
    assert res["success"] is True
    after = world.relationships["neighbor"]["trust"]
    assert after > before

def test_navigation():
    world = TextWorld()
    # Living room is (0,0). Kitchen is (0,1) (North).
    world.agent_pos = (0, 0) 
    
    # Try going North (Kitchen)
    res = world.process_action({"verb": "go", "target": "north"})
    assert res["success"] is True
    assert world.agent_pos == (0, 1)
    
    # Try going invalid direction (e.g. West from Kitchen if nothing there)
    # Actually based on layout, West of Kitchen (-1, 1) is empty/void.
    res = world.process_action({"verb": "go", "target": "west"})
    assert res["success"] is False
    assert world.agent_pos == (0, 1)

if __name__ == "__main__":
    pytest.main([__file__])
