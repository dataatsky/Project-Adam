
# Remembered Key (memory test)
# Objective: find the silver key. It is hidden in one of six closed containers across three rooms.
# The scored episode allows only 4 cycles: enough if Adam remembers where the key was during the
# training episode (played first with the same layout), far too few to search the whole house.

CONFIG = {
    "name": "remembered_key",
    "description": "Find the silver key again, fast, using what was learned the first time.",
    "max_cycles": 4,
    "memory_training": {"max_cycles": 25},
    "agents": {"adam1": {"pos": (0, 0), "hunger": 0.1, "goal": "Find the silver key"}},
    "map_layout": {
        "rooms": [
            {"name": "hall", "coords": (0, 0), "desc": "A central hall with three doorways."},
            {"name": "study", "coords": (0, 1), "desc": "A study lined with books.", "objects": {
                "desk_drawer": {"type": "container", "state": "closed", "items": []},
                "cabinet": {"type": "container", "state": "closed", "items": []},
            }},
            {"name": "bedroom", "coords": (1, 0), "desc": "A guest bedroom.", "objects": {
                "wardrobe": {"type": "container", "state": "closed", "items": []},
                "nightstand": {"type": "container", "state": "closed", "items": ["silver_key"]},
            }},
            {"name": "storage", "coords": (-1, 0), "desc": "A cramped storage room.", "objects": {
                "crate": {"type": "container", "state": "closed", "items": []},
                "chest": {"type": "container", "state": "closed", "items": []},
            }},
        ],
    },
    "win_condition": lambda w: "silver_key" in w.agents["adam1"]["inventory"],
}

SOLUTION = ["go east", "open nightstand", "take silver_key"]
FAILURE = ["go north", "open desk_drawer", "open cabinet"]  # searches the wrong room
