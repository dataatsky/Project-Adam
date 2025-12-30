
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
            "inventory": []
        }
    },
    "map_layout": {
        "rooms": [
            {"name": "bedroom", "coords": (0, 0), "desc": "A small bedroom with a locked door to the east."},
            {"name": "office", "coords": (1, 0), "desc": "An office with a desk."}
        ],
        "doors": {
            ((0, 0), (1, 0)): "locked" # Locked door between bedroom and office
        },
        "objects": {
            (0, 0): { # Bedroom
                "bed": {"type": "furniture", "state": "made", "desc": "A tidy bed."}
            },
            (0, 0): { # Bedroom (hidden key potentially? No, key usually in other room, but here he needs key to GET to other room? Wait logic.)
             # Logic check: If door is locked, he can't go to office. Key must be in Bedroom.
                "drawer": {
                    "type": "container",
                    "state": "closed",
                    "desc": "A bedside drawer.",
                    "contains": {"key": 1}
                }
            }
        }
    },
    # Win if agent makes it to the office (1, 0) - implying door was unlocked and passed through
    "win_condition": lambda w: w.agents["adam1"]["pos"] == (1, 0),
    "fail_condition": lambda w: False # No explicit fail other than timeout
}
