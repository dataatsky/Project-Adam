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


def test_world_state_describes_exits_containers_and_people():
    from scenario_runner import load_scenario

    world = TextWorld(scenario_config=load_scenario("locked_room").CONFIG)
    state = world.get_world_state()
    assert state["exit_details"] == {"east": {"room": "office", "visited": False, "door": "locked"}}
    assert state["closed_containers"] == ["drawer"]  # doors are reported with exits, not here
    assert state["goal"] == "Get out of the bedroom"  # scenario-provided objective

    party = TextWorld(scenario_config=load_scenario("social_party").CONFIG)
    party.process_action({"verb": "say", "target": "Hi Adam"}, agent_id="eve")
    state = party.get_world_state()
    assert state["people_here"] == ["eve"]
    assert state["heard"] == ["eve said: 'Hi Adam'"]


def test_exits_remember_visited_rooms():
    world = TextWorld(seed=0)
    world.agent_pos = (0, 0)
    assert world.get_world_state()["exit_details"]["north"]["visited"] is False
    world.process_action({"verb": "go", "target": "north"})
    world.process_action({"verb": "go", "target": "south"})
    assert world.get_world_state()["exit_details"]["north"]["visited"] is True


def test_say_needs_words_not_a_name():
    world = TextWorld()
    world.add_agent("eve")
    res = world.process_action({"verb": "say", "target": "eve"})
    assert res["success"] is False and "words" in res["reason"]
    assert world.process_action({"verb": "say", "target": "Hello eve"})["success"] is True


def test_say_rejects_names_in_any_case_or_punctuation():
    world = TextWorld()
    world.add_agent("eve")
    for name in ["Eve", "EVE!", " eve. ", "Neighbor"]:
        res = world.process_action({"verb": "say", "target": name})
        assert res["success"] is False, name


def test_reactive_keywords_match_whole_words_only():
    eve = {"responses": [{"keywords": ["hi", "hey"], "say": "GREETING"}, {"keywords": ["song"], "say": "MUSIC"}]}
    assert TextWorld._reactive_reply(eve, "What is this song?") == "MUSIC"   # "this" is not "hi"
    assert TextWorld._reactive_reply(eve, "They left.") is None              # "they" is not "hey"
    assert TextWorld._reactive_reply(eve, "Hi there!") == "GREETING"


def test_say_and_wait_steps_complete_goals():
    world = TextWorld()
    world.add_agent("eve")
    world.set_goal("Befriend Eve", steps=["say hello", "wait"])
    assert world.process_action({"verb": "say", "target": "Hello Eve, nice to meet you!"}).get("goal_advanced")
    assert world.process_action({"verb": "wait"}).get("goal_advanced")
    assert world.agents["adam1"]["active_goal"] is None  # plan finished


def test_heard_log_is_bounded():
    from text_world import HEARD_LOG_LIMIT

    world = TextWorld()
    world.add_agent("eve")
    for i in range(HEARD_LOG_LIMIT + 20):
        world.process_action({"verb": "say", "target": f"message {i}"}, agent_id="eve")
    log = world.agents["adam1"]["heard_log"]
    assert len(log) == HEARD_LOG_LIMIT and log[-1]["content"] == f"message {HEARD_LOG_LIMIT + 19}"


def test_world_moods_use_the_fixed_vocabulary():
    world = TextWorld()
    world.apply_emotional_shift("adam1", "Frustration", 0.1)
    assert world.agents["adam1"]["mood"] == "frustrated"
    world.apply_emotional_shift("adam1", "zany", 0.0)
    assert world.agents["adam1"]["mood"] == "frustrated"  # unknown label: keep the current mood
    world.add_agent("eve", mood="Joyful")
    assert world.agents["eve"]["mood"] == "happy"
