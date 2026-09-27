
# Broken Computer (held out)
# Objective: Repair the computer; the toolkit is stored in another room.

CONFIG = {
    "name": "broken_computer",
    "description": "The office computer shows an error; a toolkit is somewhere in the house.",
    "held_out": True,
    "max_cycles": 15,
    "agents": {"adam1": {"pos": (0, 0), "hunger": 0.1, "goal": "Fix the computer"}},
    "map_layout": {
        "rooms": [
            {"name": "office", "coords": (0, 0), "desc": "A home office.", "objects": {
                "computer": {"state": "error", "properties": ["toggleable", "repairable"]},
            }},
            {"name": "basement", "coords": (0, -1), "desc": "A dusty basement.", "objects": {
                "storage_box": {"type": "container", "state": "closed", "items": ["toolkit"]},
            }},
        ],
    },
    "win_condition": lambda w: w.map.get_location(0, 0).objects["computer"]["state"] in {"repaired", "repaired_by_tool"},
}

SOLUTION = ["go south", "open storage_box", "take toolkit", "go north", "repair computer"]
FAILURE = ["toggle computer", "use computer"]  # never fetches the toolkit
