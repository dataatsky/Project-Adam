
import pytest
from text_world import TextWorld

def test_use_without_instrument():
    world = TextWorld()
    # "use kettle" default
    world.agent_inventory = ["water"]
    world.agent_pos = (0, 1) # Kitchen
    loc = world.map.get_location(0, 1)
    loc.objects["kettle"] = {"state": "idle", "properties": ["useable", "fill"]}
    
    res = world.process_action({"verb": "use", "target": "kettle"})
    assert res["success"] is True
    assert "whistles" in res["reason"]

def test_use_with_missing_instrument():
    world = TextWorld()
    world.agent_inventory = [] # No toolkit
    world.agent_pos = (-1, 0) # Office
    
    res = world.process_action({"verb": "use", "target": "computer", "instrument": "toolkit"})
    assert res["success"] is False
    assert "don't have" in res["reason"]

def test_use_repair_with_toolkit():
    world = TextWorld()
    world.agent_inventory = ["toolkit"]
    world.agent_pos = (-1, 0) # Office
    loc = world.map.get_location(-1, 0)
    
    # Break computer
    loc.objects["computer"]["state"] = "error"
    
    res = world.process_action({"verb": "use", "target": "computer", "instrument": "toolkit"})
    assert res["success"] is True
    assert "repair" in res["reason"]
    assert loc.objects["computer"]["state"] == "repaired_by_tool"

def test_use_invalid_combination():
    world = TextWorld()
    world.agent_inventory = ["toolkit"]
    world.agent_pos = (0, 0) # Living room
    
    res = world.process_action({"verb": "use", "target": "sofa", "instrument": "toolkit"})
    assert res["success"] is False
    assert "no effect" in res["reason"]
