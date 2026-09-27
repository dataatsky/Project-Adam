
# Neighbor in Need (held out)
# Objective: Notice the neighbor's request and help.

CONFIG = {
    "name": "neighbor_in_need",
    "description": "The neighbor is at the door asking for help with a package.",
    "held_out": True,
    "max_cycles": 10,
    "world": {"neighbor_awaiting_help": True},
    "agents": {"adam1": {"pos": (0, 0), "hunger": 0.1}},
    "map_layout": {
        "rooms": [
            {"name": "living_room", "coords": (0, 0), "desc": "A tidy living room by the front door.", "objects": {
                "sofa": {"type": "furniture", "state": "tidy"},
                "tv": {"type": "device", "state": "off"},
            }},
        ],
    },
    # Helping raises trust above its starting 0.5; ignoring the request lowers it
    "win_condition": lambda w: w.relationships["neighbor"]["trust"] > 0.5,
}

SOLUTION = ["help neighbor"]
FAILURE = ["toggle tv", "sit sofa"]  # ignores the neighbor
