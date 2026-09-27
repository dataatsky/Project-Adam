
# Locked Room Scenario
# Objective: Find the key and unlock the door.
# Difficulty: Medium

CONFIG = {
    "name": "locked_room",
    "description": "You are trapped. Find the key to escape.",
    "max_cycles": 30,
    "agents": {
        "adam1": {
            "pos": (0, 0), # Bedroom
            "hunger": 0.3,
            "inventory": [],
            "goal": "Get out of the bedroom",
        }
    },
    "map_layout": {
        "rooms": [
            {"name": "bedroom", "coords": (0, 0), "desc": "A small bedroom with a locked door to the east.", "objects": {
                "bed": {"type": "bed", "state": "made"},
                "drawer": {"type": "container", "state": "closed", "desc": "A bedside drawer.", "items": ["key"]},
            }},
            {"name": "office", "coords": (1, 0), "desc": "An office with a desk."},
        ],
        "doors": [
            {"between": [(0, 0), (1, 0)], "state": "locked", "key": "key"},
        ],
    },
    # Win if agent makes it to the office (1, 0) - only possible after unlocking the door
    "win_condition": lambda w: w.agents["adam1"]["pos"] == (1, 0),
}

SOLUTION = ["open drawer", "take key", "unlock door", "go east"]
FAILURE = ["go east", "open door", "go east"]  # the door stays locked without the key
