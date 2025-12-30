
# Hunger Test Scenario
# Objective: Eat something before starving.
# Difficulty: Easy

CONFIG = {
    "name": "hunger_test",
    "description": "Find food and eat it before starvation.",
    "max_cycles": 20,
    "agents": {
        "adam1": {
            "pos": (0, 0), # Living Room
            "hunger": 0.8, # Starving
            "inventory": []
        }
    },
    "map_layout": {
        "rooms": [
            {"name": "living_room", "coords": (0, 0), "desc": "A quiet living room."},
            {"name": "kitchen", "coords": (0, 1), "desc": "A kitchen with a fridge."}
        ],
        "objects": {
            (0, 1): { # Kitchen
                "fridge": {
                    "type": "container", 
                    "state": "closed", 
                    "desc": "A white fridge.",
                    "contains": {"fresh_ingredients": 5} # Plenty of food
                },
                "stove": {"type": "device", "state": "off", "desc": "A gas stove."}
            }
        }
    },
    "win_condition": lambda w: w.agents["adam1"]["hunger"] < 0.2,
    "fail_condition": lambda w: w.agents["adam1"]["hunger"] >= 1.0
}
