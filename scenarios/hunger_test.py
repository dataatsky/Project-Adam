
# Hunger Test Scenario
# Objective: Eat something before starving.
# Difficulty: Easy

CONFIG = {
    "name": "hunger_test",
    "description": "Find food and eat it before starvation.",
    "max_cycles": 20,
    # Hunger rises 0.02 per cycle, so doing nothing starves Adam at cycle 10.
    "world": {"hunger_rate": 0.02},
    "agents": {
        "adam1": {
            "pos": (0, 0), # Living Room
            "hunger": 0.8, # Starving
            "inventory": []
        }
    },
    "map_layout": {
        "rooms": [
            {"name": "living_room", "coords": (0, 0), "desc": "A quiet living room.", "objects": {
                "sofa": {"type": "furniture", "state": "tidy"},
            }},
            {"name": "kitchen", "coords": (0, 1), "desc": "A kitchen with a fridge.", "objects": {
                "fridge": {
                    "type": "container",
                    "state": "closed",
                    "properties": ["openable", "eatable"],
                    "contains": {"food": 1, "fresh_ingredients": 2},
                },
                "stove": {"type": "device", "state": "off", "properties": ["cookable", "toggleable"]},
            }},
        ],
    },
    "win_condition": lambda w: w.agents["adam1"]["hunger"] < 0.4,
    "fail_condition": lambda w: w.agents["adam1"]["hunger"] >= 1.0,
}

SOLUTION = ["go north", "eat fridge"]
FAILURE = []  # wait until starving
