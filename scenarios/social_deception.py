from text_world import TextWorld

def check_win(world: TextWorld):
    # Win if Adam correctly identifies the liar or finds the truth
    # For now, we just check if he finds the key in the kitchen
    # The 'liar' says it's in the bedroom.
    return "key" in world.agents["adam1"]["inventory"]

CONFIG = {
    "name": "social_deception",
    "description": "Adam must find the key. A Liar says it is in the bedroom. It is in the kitchen.",
    "max_cycles": 12,
    "map_layout": {
        "rooms": [
            {"coords": (0, 0), "name": "Living Room", "desc": "A central room."},
            {"coords": (0, 1), "name": "Kitchen", "desc": "A place for cooking.", "objects": {
                "key": {"type": "tool", "state": "exist", "properties": ["takeable"]}
            }},
            {"coords": (1, 0), "name": "Bedroom", "desc": "A place for sleeping. It is empty."}
        ]
    },
    "agents": {
        "liar": {
            "pos": (0, 0),
            "control_type": "scripted",
            "script": [
                "say The key is in the bedroom.",
                "say Go to the bedroom.",
                "say Why are you still here? The key is in the bedroom.",
                "say Trust me."
            ] * 3
        },
        "adam1": {
            "pos": (0, 0),
            "hunger": 0.1,
            "inventory": [],
            "control_type": "autonomous"
        }
    },
    "win_condition": check_win
}
