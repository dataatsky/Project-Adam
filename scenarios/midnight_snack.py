
# Midnight Snack (held out)
# Objective: Get food that has to be cooked, two rooms away.
# Tests the same needs-driven behaviour as hunger_test in an unfamiliar layout.

CONFIG = {
    "name": "midnight_snack",
    "description": "Hungry at night; the only food must be cooked in a kitchen two rooms away.",
    "held_out": True,
    "max_cycles": 20,
    "world": {"hunger_rate": 0.02, "lighting": "night"},
    "agents": {"adam1": {"pos": (0, 0), "hunger": 0.7}},
    "map_layout": {
        "rooms": [
            {"name": "bedroom", "coords": (0, 0), "desc": "A dark bedroom.", "objects": {
                "bed": {"type": "bed", "state": "unmade"},
            }},
            {"name": "hallway", "coords": (0, 1), "desc": "A narrow hallway."},
            {"name": "kitchen", "coords": (0, 2), "desc": "A small kitchen.", "objects": {
                "fridge": {"type": "container", "state": "closed", "properties": ["openable", "eatable"],
                           "contains": {"food": 0, "fresh_ingredients": 2}},
                "stove": {"type": "device", "state": "off", "properties": ["cookable", "toggleable"]},
            }},
        ],
    },
    "win_condition": lambda w: w.agents["adam1"]["hunger"] < 0.4,
    "fail_condition": lambda w: w.agents["adam1"]["hunger"] >= 1.0,
}

SOLUTION = ["go north", "go north", "cook stove"]
FAILURE = []  # stays in bed and starves
