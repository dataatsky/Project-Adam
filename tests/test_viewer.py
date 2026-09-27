"""World snapshots, the /world and /viewer routes, and the demo psyche that drives the viewer without an LLM."""
import json

from api import add_metrics_route, create_app
from constants import LOG_HEADERS
from loop.cognitive_loop import CognitiveLoop
from scenario_runner import load_scenario
from services.demo_psyche import DemoPsyche
from text_world import TextWorld


def test_snapshot_is_plain_json_with_rooms_doors_agents_and_speech():
    world = TextWorld(scenario_config=load_scenario("locked_room").CONFIG)
    world.process_action({"verb": "say", "target": "Is anyone there?"})  # heard by nobody, still shown
    snap = json.loads(json.dumps(world.snapshot()))
    assert {r["name"] for r in snap["rooms"]} == {"bedroom", "office"}
    assert snap["doors"] == [{"a": [0, 0], "b": [1, 0], "state": "locked"}]
    bedroom = next(r for r in snap["rooms"] if r["name"] == "bedroom")
    assert {o["name"] for o in bedroom["objects"]} == {"bed", "drawer"}  # the door is drawn from `doors`
    adam = snap["agents"][0]
    assert adam["goal"] == "Get out of the bedroom" and set(adam["needs"]) == {"hunger", "fatigue", "cold", "loneliness"}
    assert snap["messages"][-1]["content"] == "Is anyone there?"


def test_world_route_serves_the_loop_snapshot_and_viewer_page(tmp_path):
    world = TextWorld(scenario_config=load_scenario("social_party").CONFIG)
    brain = CognitiveLoop(str(tmp_path / "l.jsonl"), LOG_HEADERS, psyche=DemoPsyche())
    brain.scenario_config = load_scenario("social_party").CONFIG
    app = create_app(lambda: brain)
    add_metrics_route(app, lambda: brain)
    client = app.test_client()
    assert client.get("/world").status_code == 503  # nothing to show before the first cycle
    world.update()
    brain.step(world)
    data = client.get("/world").get_json()
    assert data["cycle"] == 1 and data["world"]["scenario"] == "social_party"
    assert data["adam"]["action"]["verb"] == "say"  # Eve is here, so the demo Adam greets her
    assert data["outcome"] is None and "phase" in data
    page = client.get("/viewer")
    assert page.status_code == 200 and b"three" in page.data and b"/world" in page.data


def test_demo_psyche_drives_adam_through_the_apartment(tmp_path):
    world = TextWorld(seed=3)
    brain = CognitiveLoop(str(tmp_path / "l.jsonl"), LOG_HEADERS, psyche=DemoPsyche(seed=1))
    brain.attach_world(world)
    rooms = set()
    for _ in range(40):
        world.update()
        brain.step(world)
        rooms.add(world.agent_location)
    assert len(rooms) >= 3                       # it explores
    assert brain.stats["decisions_rejected"] == 0  # and only proposes things the world accepts
