import copy
import random
import re
from typing import Dict, List, Optional, Tuple, Any

from grid_map import GridMap
from moods import normalize_mood
from sensory import SensoryCortex

# Canonical action vocabulary. The psyche prompts, the psyche response schema
# and action validation are all derived from this table, so adding a verb here
# (plus an `_act_<verb>` handler) is the single place to extend Adam's actions.
VERBS: Dict[str, str] = {
    "wait": "let time pass (target: null)",
    "go": "move to an adjacent room (target: an available exit direction)",
    "examine": "look closely at an object",
    "open": "open something openable",
    "close": "close something openable",
    "toggle": "switch a device on or off",
    "read": "read something readable",
    "eat": "eat from a food source (e.g. fridge)",
    "cook": "cook a meal from fresh ingredients (in the kitchen)",
    "sleep": "sleep on something sleepable",
    "sit": "sit or rest on furniture",
    "play": "play with or enjoy an object",
    "water": "water a plant",
    "fill": "fill a container with water",
    "take": "pick up an object, or an item from an open container",
    "drop": "put down an item from inventory",
    "use": "use an object (optional instrument from inventory)",
    "clean": "clean an object",
    "repair": "repair something (needs a toolkit)",
    "unlock": "unlock a locked door (needs its key in inventory)",
    "help": "help someone who asked (target: neighbor)",
    "say": "speak aloud to whoever is here (target: the exact words, e.g. \"Hello, who are you?\")",
    "break": "destroy an object",
    "inventory": "check what I am carrying (target: null)",
}

# Common LLM phrasings mapped onto canonical verbs.
VERB_ALIASES: Dict[str, str] = {
    "investigate": "examine",
    "inspect": "examine",
    "look": "examine",
    "check": "examine",
    "turn_on": "toggle",
    "turn_off": "toggle",
    "switch": "toggle",
    "ignore": "wait",
    "listen": "wait",
    "rest": "wait",
    "move": "go",
    "walk": "go",
    "pick_up": "take",
    "grab": "take",
    "speak": "say",
    "talk": "say",
    "smash": "break",
    "destroy": "break",
}

# Verbs whose target is not a grounded object.
_UNGROUNDED_VERBS = {"wait", "inventory", "say", "go", "help"}

# Affordances granted to scenario objects that only declare a `type`.
TYPE_PROPERTIES: Dict[str, List[str]] = {
    "container": ["openable"],
    "device": ["toggleable"],
    "furniture": ["sit"],
    "bed": ["sleepable"],
    "window": ["openable"],
    "tool": ["takeable"],
    "book": ["readable", "takeable"],
}

NULL_TARGETS = {None, "", "null", "none"}


def normalize_verb(verb: Optional[str]) -> str:
    v = str(verb or "").strip().lower().replace(" ", "_")
    return VERB_ALIASES.get(v, v)


# Core room templates that always exist; objects include properties to gate actions
BASE_ROOMS: Dict[str, Dict] = {
    "living_room": {
        "sofa": {"state": "tidy", "properties": ["sit", "rest"]},
        "window": {"state": "closed", "properties": ["openable"]},
        "tv": {"state": "off", "properties": ["toggleable", "watchable"]},
        "radio": {"state": "off", "properties": ["toggleable"]},
        "bookshelf": {"state": "arranged", "properties": ["readable", "takeable"], "items": ["mystery_novel"]},
    },
    "kitchen": {
        "fridge": {
            "state": "closed",
            "contains": {"food": 2, "fresh_ingredients": 1},
            "properties": ["openable", "eatable"]
        },
        "stove": {"state": "off", "properties": ["cookable", "toggleable"]},
        "kettle": {"state": "idle", "properties": ["useable", "fill", "heat"]},
        "sink": {"state": "clean", "properties": ["water_source", "cleanable"]},
    },
    "bedroom": {
        "bed": {"state": "made", "properties": ["sleepable"]},
        "desk": {"state": "tidy", "properties": ["workable"], "items": ["journal", "pen"]},
        "wardrobe": {"state": "closed", "properties": ["openable"], "items": ["blanket"]},
    },
    "office": {
        "computer": {"state": "off", "properties": ["toggleable", "investigatable", "repairable"]},
        "plant": {"state": "healthy", "properties": ["waterable"]},
        "whiteboard": {"state": "blank", "properties": ["writeable", "cleanable"]},
    },
}

# Optional rooms randomly grafted onto the base layout each run
OPTIONAL_ROOMS: Dict[str, Dict] = {
    "balcony": {
        "chair": {"state": "empty", "properties": ["sit"]},
        "telescope": {"state": "covered", "properties": ["useable", "openable"]},
    },
    "bathroom": {
        "mirror": {"state": "clear", "properties": ["lookable", "cleanable"]},
        "shower": {"state": "off", "properties": ["useable"]},
        "cabinet": {"state": "closed", "properties": ["openable"], "items": ["first_aid", "towel"]},
    },
    "basement": {
        "generator": {"state": "idle", "properties": ["repairable", "useable"]},
        "storage_box": {"state": "closed", "properties": ["openable"], "items": ["toolkit", "spare_fuse"]},
    },
}

# High-level ambience presets to seed lighting/temperature/noise
ENVIRONMENT_PRESETS = {
    "calm_morning": {"lighting": "day", "temperature": 21.0, "noise": 0.1},
    "storm_night": {"lighting": "night", "temperature": 18.0, "noise": 0.4},
    "winter_evening": {"lighting": "evening", "temperature": 16.0, "noise": 0.2},
}

DEFAULT_HUNGER_RATE = 0.005
# Messages kept per agent in heard_log (the world is deep-copied for every imagined option)
HEARD_LOG_LIMIT = 50


class TextWorld:
    """Procedural apartment sandbox feeding Adam's cognition loop.

    The world is built from a set of base rooms and optional modules mapped to
    a 2D GridMap. This enables cardinal navigation (N/S/E/W) and spatial
    relationships.

    The world is the single source of truth for each agent's body and mind
    state (position, inventory, hunger, mood, goal). The cognitive loop reads
    it through `get_world_state` and changes it only through `process_action`,
    `apply_emotional_shift` and the goal methods.
    """

    def __init__(self, seed: Optional[int] = None, scenario_config: Optional[Dict] = None):
        self.random = random.Random(seed)
        self.agents: Dict[str, Dict] = {}
        # Backwards compatibility map: Room name -> (x, y) coordinates
        self.room_coords: Dict[str, Tuple[int, int]] = {}
        self.world_time = 0
        self.temperature = 21.0
        self.noise_level = 0.1
        self.lighting = "day"
        self.cleanliness = 0.8
        self.hunger_rate = DEFAULT_HUNGER_RATE
        self.random_events = True
        self.neighbor_visits = True
        self.active_events: Dict[str, Dict] = {}
        self.neighbor_state = {"awaiting_help": False, "last_visit": None}
        self.relationships = {"neighbor": {"trust": 0.5, "last_request": None}}
        self.scenario_name: Optional[str] = None
        # Global order of spoken messages, so conversations can be checked turn by turn
        self.message_seq = 0

        # Initialize Grid
        self.map = GridMap()

        if scenario_config:
            self._load_from_scenario(scenario_config)
        else:
            self._generate_layout()
            self._choose_environment_theme()
            # Initialize default agent 'adam1'
            self.add_agent("adam1")

    def add_agent(self, agent_id: str, **kwargs):
        """Register a new agent in the world. Existing agents are left untouched.

        Optional kwargs: pos, inventory, hunger, mood, mood_intensity, script,
        control_type ("autonomous", "scripted" or "reactive"), goal (a name, or
        {"name": ..., "steps": [...]}), and for reactive agents: responses
        ([{"keywords": [...], "say": "...", "once": bool}]) and default_response.
        """
        if agent_id in self.agents:
            return
        pos = tuple(kwargs.get("pos", (0, 0)))  # Living Room
        self.agents[agent_id] = {
            "id": agent_id,
            "pos": pos,
            "visited": {pos},
            "inventory": list(kwargs.get("inventory", [])),
            "hunger": float(kwargs.get("hunger", 0.25)),
            "mood": normalize_mood(kwargs.get("mood"), default="neutral"),
            "mood_intensity": float(kwargs.get("mood_intensity", 0.4)),
            "active_goal": None,
            "goal_progress_index": 0,
            "current_goal_steps_done": [],
            "goal_history": [],
            "recent_examined": {},
            "inbox": [],
            "heard_log": [],  # every message this agent heard, kept after the inbox is read
            "script": list(kwargs.get("script", [])),
            "control_type": kwargs.get("control_type", "autonomous"),
            "responses": [dict(r) for r in kwargs.get("responses", [])],
            "default_response": kwargs.get("default_response"),
        }
        goal = kwargs.get("goal")
        if isinstance(goal, dict):
            self.set_goal(goal["name"], steps=goal.get("steps"), agent_id=agent_id)
        elif goal:
            self.set_goal(goal, agent_id=agent_id)

    @property
    def agent_pos(self) -> Tuple[int, int]:
        """Backward compatibility: adam1 pos."""
        return self.agents["adam1"]["pos"]

    @agent_pos.setter
    def agent_pos(self, value):
        self.agents["adam1"]["pos"] = tuple(value)
        self.agents["adam1"]["visited"].add(tuple(value))

    @property
    def agent_inventory(self) -> List[str]:
        return self.agents["adam1"]["inventory"]

    @agent_inventory.setter
    def agent_inventory(self, value):
        self.agents["adam1"]["inventory"] = list(value)

    @property
    def hunger(self) -> float:
        return self.agents["adam1"]["hunger"]

    @hunger.setter
    def hunger(self, value):
        self.agents["adam1"]["hunger"] = value

    @property
    def mood_intensity(self) -> float:
        return self.agents["adam1"]["mood_intensity"]

    @mood_intensity.setter
    def mood_intensity(self, value):
        self.agents["adam1"]["mood_intensity"] = value

    @property
    def active_goal(self):
        return self.agents["adam1"]["active_goal"]

    @active_goal.setter
    def active_goal(self, value):
        self.agents["adam1"]["active_goal"] = value

    @property
    def goal_progress_index(self):
        return self.agents["adam1"]["goal_progress_index"]

    @goal_progress_index.setter
    def goal_progress_index(self, value):
        self.agents["adam1"]["goal_progress_index"] = value

    @property
    def current_goal_steps_done(self):
        return self.agents["adam1"]["current_goal_steps_done"]

    @current_goal_steps_done.setter
    def current_goal_steps_done(self, value):
        self.agents["adam1"]["current_goal_steps_done"] = value

    @property
    def goal_history(self):
        return self.agents["adam1"]["goal_history"]

    @property
    def recent_examined(self):
        return self.agents["adam1"]["recent_examined"]

    @property
    def agent_location(self) -> str:
        """Backward compatibility: return current room name."""
        loc = self.map.get_location(*self.agent_pos)
        return loc.name if loc else "void"

    @agent_location.setter
    def agent_location(self, value: str):
        """Allow setting location by name if it exists in the map."""
        if value in self.room_coords:
            self.agent_pos = self.room_coords[value]

    # ------------------------------------------------------------------
    def clone(self):
        """Return a deep copy so imagination/reflection can simulate branches."""
        return copy.deepcopy(self)

    def _generate_layout(self):
        """Materialize the grid layout.

        Base Layout:
          Office (-1,0) -- Living Room (0,0) -- Bedroom (1,0)
                                 |
                            Kitchen (0,1)
        """
        # 1. Place Base Rooms
        base_layout = [
            ("living_room", (0, 0), "A cozy living room."),
            ("kitchen", (0, 1), "A functional kitchen."),
            ("bedroom", (1, 0), "A quiet bedroom."),
            ("office", (-1, 0), "A cluttered home office.")
        ]

        for name, coords, desc in base_layout:
            objs = copy.deepcopy(BASE_ROOMS[name])
            self.map.add_location(coords[0], coords[1], name, desc, objs)
            self.room_coords[name] = coords

        # 2. Place Optional Rooms
        optional_opportunities = [
            ("balcony", (0, -1), "living_room"), # South of Living Room
            ("bathroom", (1, 1), "bedroom"),     # North of Bedroom (also East of Kitchen)
            ("basement", (0, 2), "kitchen")      # North of Kitchen
        ]

        # Randomly select 1-2 optional rooms
        chosen_extras = self.random.sample(optional_opportunities, k=self.random.randint(1, 2))

        for name, coords, anchor_room in chosen_extras:
            if name not in OPTIONAL_ROOMS or self.map.get_location(coords[0], coords[1]):
                continue
            objs = copy.deepcopy(OPTIONAL_ROOMS[name])
            self.map.add_location(coords[0], coords[1], name, f"A {name}.", objs)
            self.room_coords[name] = coords

    def _choose_environment_theme(self):
        """Pick an ambience preset (lighting/temp/noise) as the starting mood."""
        theme = self.random.choice(list(ENVIRONMENT_PRESETS.values()))
        self.lighting = theme["lighting"]
        self.temperature = theme["temperature"]
        self.noise_level = theme["noise"]

    @staticmethod
    def _normalize_object(spec: Any) -> Dict:
        """Give a scenario object a state and affordances.

        Explicit `properties` win; otherwise they are derived from `type`.
        """
        obj = copy.deepcopy(spec) if isinstance(spec, dict) else {}
        obj.setdefault("state", "idle")
        if "properties" not in obj:
            obj["properties"] = list(TYPE_PROPERTIES.get(obj.get("type"), []))
        return obj

    def _load_from_scenario(self, config: Dict):
        """Build world from scenario config.

        Objects may be declared inside each room (`rooms[i]["objects"]`) or in
        `map_layout["objects"][coords]`; both are merged.
        """
        self.scenario_name = config.get("name")
        layout = config.get("map_layout", {})
        world_cfg = config.get("world", {})
        self.hunger_rate = float(world_cfg.get("hunger_rate", DEFAULT_HUNGER_RATE))
        self.random_events = bool(world_cfg.get("random_events", False))
        self.neighbor_visits = bool(world_cfg.get("neighbor_visits", False))
        self.lighting = world_cfg.get("lighting", self.lighting)
        self.temperature = float(world_cfg.get("temperature", self.temperature))
        self.noise_level = float(world_cfg.get("noise", self.noise_level))
        if world_cfg.get("neighbor_awaiting_help"):
            self.neighbor_state.update({"awaiting_help": True, "last_visit": 0, "request_cycle": 0})
            self.relationships["neighbor"]["last_request"] = 0

        # 1. Rooms
        coord_objects = layout.get("objects", {})
        for room in layout.get("rooms", []):
            x, y = room["coords"]
            name = room["name"]
            desc = room.get("desc", f"A {name}.")
            specs = {**coord_objects.get((x, y), {}), **room.get("objects", {})}
            objs = {k: self._normalize_object(v) for k, v in specs.items()}
            self.map.add_location(x, y, name, desc, objs)
            self.room_coords[name] = (x, y)

        # 2. Doors: one shared "door" object visible from both sides
        for door_cfg in layout.get("doors", []):
            a, b = (tuple(c) for c in door_cfg["between"])
            door = {
                "state": door_cfg.get("state", "closed"),
                "properties": ["openable", "lockable"],
                "key": door_cfg.get("key"),
            }
            self.map.add_door(a, b, door)
            for coords in (a, b):
                loc = self.map.get_location(*coords)
                if loc:
                    loc.objects[door_cfg.get("name", "door")] = door

        # 3. Agents
        for agent_id, data in config.get("agents", {}).items():
            self.add_agent(agent_id, **data)

    # ------------------------------------------------------------------
    # Goals
    @staticmethod
    def _parse_step(step: Any) -> Dict:
        if isinstance(step, dict):
            return {
                "action": normalize_verb(step.get("action") or step.get("verb")),
                "target": step.get("target"),
                "desc": step.get("desc", f"{step.get('action') or step.get('verb')} {step.get('target') or ''}".strip()),
            }
        parts = str(step).lower().split()
        if len(parts) >= 2:
            return {"action": normalize_verb(parts[0]), "target": parts[-1], "desc": str(step)}
        return {"action": normalize_verb(parts[0]) if parts else "wait", "target": None, "desc": str(step)}

    def set_goal(self, goal_name: str, steps: Optional[list] = None, agent_id: str = "adam1"):
        """Set the agent's goal, clearing progress. A goal without steps is open-ended."""
        if agent_id not in self.agents:
            return
        agent = self.agents[agent_id]
        agent["active_goal"] = {
            "name": goal_name,
            "steps": [self._parse_step(s) for s in (steps or [])],
            "set_at": self.world_time,
        }
        agent["goal_progress_index"] = 0
        agent["current_goal_steps_done"] = []

    def set_goal_plan(self, steps: list, agent_id: str = "adam1"):
        """Give the active goal a step-by-step plan, keeping its name."""
        agent = self.agents.get(agent_id)
        if agent and agent["active_goal"] and steps:
            self.set_goal(agent["active_goal"]["name"], steps=steps, agent_id=agent_id)

    def clear_goal(self, agent_id: str = "adam1", status: str = "completed"):
        """Close the active goal, recording how it ended."""
        agent = self.agents.get(agent_id)
        if not agent or not agent["active_goal"]:
            return
        agent["goal_history"].append({"goal": agent["active_goal"]["name"], "status": status, "cycle": self.world_time})
        agent["active_goal"] = None
        agent["goal_progress_index"] = 0
        agent["current_goal_steps_done"] = []

    def time_of_day(self):
        cycle = self.world_time % 24
        if 6 <= cycle < 12:
            return "morning"
        if 12 <= cycle < 18:
            return "afternoon"
        if 18 <= cycle < 22:
            return "evening"
        return "night"

    # ------------------------------------------------------------------
    def update(self):
        """Advance time and evolve the environment.

        - increments the internal clock
        - raises hunger and applies ambience mood effects to autonomous agents
        - gradually adjusts ambience (lighting, temperature, noise, cleanliness)
        - resolves cooldowns for examined/open objects
        - schedules periodic neighbor visits
        - triggers occasional random events
        - runs scripted agents
        - restocks consumables (e.g., fridge food) on a cadence

        Returns a list of narrative snippets describing notable events that
        occurred this tick.
        """
        self.world_time += 1
        events: List[str] = []

        # natural drift of environment (lighting tracks time, temp/nose/cleanliness adjust slowly)
        if self.lighting != "night" and self.time_of_day() == "night":
            self.lighting = "night"
        elif self.lighting != "day" and self.time_of_day() == "morning":
            self.lighting = "day"

        # temperature adjusts slowly
        target_temp = 20.0 if self.lighting in {"morning", "day"} else 18.0
        if self.temperature < target_temp:
            self.temperature = min(target_temp, self.temperature + 0.5)
        else:
            self.temperature = max(target_temp, self.temperature - 0.5)

        self.noise_level = max(0.0, min(1.0, self.noise_level * 0.9))
        self.cleanliness = max(0.0, min(1.0, self.cleanliness - 0.005))

        # Bodies: hunger rises and the ambience nudges mood
        _, mood_adjust = self._environment_summary()
        for agent in self.agents.values():
            if agent.get("control_type") == "scripted":
                continue
            agent["hunger"] = round(min(1.0, agent["hunger"] + self.hunger_rate), 4)
            if mood_adjust:
                agent["mood_intensity"] = max(0.0, min(1.0, agent["mood_intensity"] + mood_adjust))

        # manage examined-object cooldown
        cooldown = 3
        for agent in self.agents.values():
            examined = agent["recent_examined"]
            for obj in [o for o, t in examined.items() if self.world_time - t > cooldown]:
                examined.pop(obj, None)

        # auto close openables after a few ticks
        for loc in self.map.grid.values():
            for obj in loc.objects.values():
                if isinstance(obj, dict) and obj.get("state") == "open" and obj.get("opened_at") is not None:
                    if self.world_time - obj["opened_at"] >= 3:
                        obj["state"] = "closed"
                        obj.pop("opened_at", None)

        # scheduled neighbor visit every 12 ticks
        if self.neighbor_visits and self.world_time % 12 == 0 and not self.neighbor_state["awaiting_help"]:
            self.neighbor_state.update({"awaiting_help": True, "last_visit": self.world_time, "request_cycle": self.world_time})
            events.append("A neighbor knocked and asked for help with a package.")
            self.noise_level = min(1.0, self.noise_level + 0.2)
            self.relationships["neighbor"]["last_request"] = self.world_time

        req_cycle = self.neighbor_state.get("request_cycle")
        if self.neighbor_state.get("awaiting_help") and req_cycle is not None:
            if self.world_time - req_cycle > 5:
                self.relationships["neighbor"]["trust"] = max(0.1, self.relationships["neighbor"].get("trust", 0.5) - 0.05)
                self.neighbor_state["request_cycle"] = self.world_time
                if "adam1" in self.agents:
                    self.mood_intensity = min(1.0, self.mood_intensity + 0.05)

        # random events for variety (power flickers, drafts, etc.)
        if self.random_events and self.random.random() < 0.15:
            self._trigger_random_event(events)

        # Scripted agents act from their script, one line per tick
        for agent_id, agent_data in self.agents.items():
            if agent_data.get("control_type") != "scripted" or not agent_data.get("script"):
                continue
            verb, _, target = agent_data["script"].pop(0).partition(" ")
            self.process_action({"verb": verb, "target": target or None}, agent_id=agent_id)
            if verb == "say":
                events.append(f"{agent_id} says: '{target}'")

        # Reactive agents answer the latest thing said to them since the last tick
        for agent_id, agent_data in self.agents.items():
            if agent_data.get("control_type") != "reactive" or not agent_data["inbox"]:
                continue
            heard = agent_data["inbox"][-1]["content"]
            agent_data["inbox"].clear()
            reply = self._reactive_reply(agent_data, heard)
            if reply:
                self.process_action({"verb": "say", "target": reply}, agent_id=agent_id)
                events.append(f"{agent_id} says: '{reply}'")

        # restock fridge occasionally
        kitchen_loc = self.map.get_location(*self.room_coords.get("kitchen", (0, 1)))
        if kitchen_loc:
            fridge = kitchen_loc.objects.get("fridge")
            if fridge and self.world_time % 18 == 0:
                fridge.setdefault("contains", {})
                fridge["contains"]["food"] = fridge["contains"].get("food", 0) + 1

        return events

    @staticmethod
    def _reactive_reply(agent: Dict, heard: str) -> Optional[str]:
        """First matching keyword rule wins; rules marked `once` fire only one time."""
        text = heard.lower()
        for rule in agent.get("responses", []):
            if rule.get("used"):
                continue
            if any(re.search(rf"\b{re.escape(k.lower())}\b", text) for k in rule.get("keywords", [])):
                if rule.get("once"):
                    rule["used"] = True
                return rule["say"]
        return agent.get("default_response")

    def _trigger_random_event(self, events: List[str]):
        """Select and apply a stochastic micro-event (power flicker, draft, etc.)."""
        options = ["power_flicker", "radio_static", "draft", "plant_thirsty", "computer_error"]
        event = self.random.choice(options)

        living_room = self.map.get_location(*self.room_coords.get("living_room", (0, 0)))
        office = self.map.get_location(*self.room_coords.get("office", (-1, 0)))

        if event == "power_flicker":
            self.lighting = "evening"
            self.noise_level = min(1.0, self.noise_level + 0.2)
            events.append("The lights flicker, casting long shadows.")
        elif event == "radio_static":
            if living_room and "radio" in living_room.objects:
                living_room.objects["radio"]["state"] = "on_static"
                events.append("The radio bursts into static noise.")
                self.noise_level = min(1.0, self.noise_level + 0.3)
        elif event == "draft":
            if living_room and "window" in living_room.objects:
                living_room.objects["window"]["state"] = "open"
                living_room.objects["window"]["opened_at"] = self.world_time
                events.append("A chilly draft slips through the open window.")
                self.temperature = max(15.0, self.temperature - 1.5)
        elif event == "plant_thirsty":
            plant = office.objects.get("plant") if office else None
            if plant and plant.get("state") == "healthy":
                plant["state"] = "wilted"
                events.append("The office plant droops, thirsty for water.")
        elif event == "computer_error":
            comp = office.objects.get("computer") if office else None
            if comp:
                comp["state"] = "error"
                events.append("The computer displays a cryptic error message.")

    # ------------------------------------------------------------------
    def _environment_summary(self) -> Tuple[str, float]:
        """Summarize ambience using the SensoryCortex.

        Returns a tuple of (string summary, numeric delta) capturing how the
        environment should make Adam feel.
        """
        return SensoryCortex().transduce(
            self.temperature,
            self.noise_level,
            self.cleanliness,
            self.lighting
        )

    def apply_emotional_shift(self, agent_id: str, mood: Optional[str], level_delta: float = 0.0):
        """Apply a psyche-proposed mood change to an agent."""
        agent = self.agents.get(agent_id)
        if not agent:
            return
        agent["mood"] = normalize_mood(mood, default=agent["mood"])
        try:
            delta = float(level_delta or 0.0)
        except (TypeError, ValueError):
            delta = 0.0
        agent["mood_intensity"] = max(0.0, min(1.0, agent["mood_intensity"] + delta))

    def _visible_items(self, room_objects: Dict) -> Dict[str, str]:
        """Items that can be taken right now: item -> container holding it."""
        visible = {}
        for name, obj in room_objects.items():
            if not isinstance(obj, dict) or not obj.get("items"):
                continue
            closed = "openable" in obj.get("properties", []) and obj.get("state") != "open"
            if closed:
                continue
            for item in obj["items"]:
                visible.setdefault(item, name)
        return visible

    def available_targets(self, agent_id: str = "adam1") -> Dict[str, List[str]]:
        """Everything the agent could ground an action on right now."""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"objects": [], "items": [], "inventory": [], "exits": [], "agents": []}
        loc = self.map.get_location(*agent["pos"])
        room_objects = loc.objects if loc else {}
        return {
            "objects": list(room_objects.keys()),
            "items": list(self._visible_items(room_objects).keys()),
            "inventory": list(agent["inventory"]),
            "exits": self.map.get_exits(*agent["pos"]),
            "agents": [o for o, d in self.agents.items() if o != agent_id and d["pos"] == agent["pos"]],
        }

    def validate_action(self, action: Dict[str, Any], agent_id: str = "adam1") -> Tuple[bool, str]:
        """Check an action is in the vocabulary and grounded in what the agent can reach."""
        verb = normalize_verb((action or {}).get("verb"))
        target = (action or {}).get("target")
        target = None if target in NULL_TARGETS else str(target)
        instrument = (action or {}).get("instrument")
        if verb not in VERBS:
            return False, f"'{verb}' is not something I know how to do."
        if agent_id not in self.agents:
            return False, "Agent not found."
        reach = self.available_targets(agent_id)
        if instrument not in NULL_TARGETS and instrument not in reach["inventory"]:
            return False, f"I don't have a {instrument}."
        names = {name.lower() for name in reach["agents"] + ["neighbor"]}
        if verb == "say" and target and target.strip(" .,!?'\"").lower() in names:
            return False, f"To speak, the target must be the words I say, not a name like '{target}'."
        if verb in {"wait", "inventory", "say"}:
            return True, ""
        if verb == "go":
            if target and target.lower() in reach["exits"]:
                return True, ""
            return False, f"'{target}' is not an exit from here. Exits: {', '.join(reach['exits']) or 'none'}."
        if verb == "help":
            return (target == "neighbor", "" if target == "neighbor" else "I can only help the neighbor.")
        grounded = reach["objects"] + reach["items"] + reach["inventory"] + reach["agents"]
        if target not in grounded:
            return False, f"I don't see a {target} here."
        return True, ""

    def get_world_state(self, agent_id: str = "adam1"):
        """Produce the observation payload consumed by the cognition loop."""
        if agent_id not in self.agents:
            return {}
        agent = self.agents[agent_id]

        sensory_events = []
        # Current Location
        loc = self.map.get_location(*agent["pos"])
        room_objects = loc.objects if loc else {}
        room_name = loc.name if loc else "void"

        summary, _ = self._environment_summary()
        intro = f"I am in the {room_name}. {loc.description} {summary}".strip() if loc else summary
        sensory_events.append({"type": "ambience", "details": intro})

        notable_states = {
            "phone": ["ringing"],
            "door": ["knocking", "open", "locked"],
            "tv": ["on", "on_static"],
            "radio": ["on", "on_static"],
            "computer": ["error", "on"],
            "plant": ["wilted"],
            "window": ["open"],
        }

        for obj, properties in room_objects.items():
            if not isinstance(properties, dict):
                continue
            state = properties.get("state")
            if obj in notable_states and state in notable_states[obj]:
                if obj in agent["recent_examined"] and self.world_time - agent["recent_examined"][obj] <= 3:
                    continue
                sensory_events.append({"type": "sight/sound", "object": obj, "details": state})

        # Social Perception: See other agents
        for other_id, other_data in self.agents.items():
            if other_id != agent_id and other_data["pos"] == agent["pos"]:
                sensory_events.append({"type": "visual", "object": other_id, "details": "standing here"})

        # Occasionally an ordinary object catches the eye, so Adam moves on to other stimuli
        perceivable_objects = list(room_objects.keys())
        sensed = {evt.get("object") for evt in sensory_events}
        idle_candidates = [
            obj for obj in perceivable_objects
            if obj not in sensed and obj not in agent["recent_examined"]
        ]
        if idle_candidates and self.random.random() < 0.35:
            sensory_events.append({"type": "sight/sound", "object": self.random.choice(idle_candidates), "details": "idle"})

        if self.neighbor_state["awaiting_help"]:
            sensory_events.append({"type": "social", "object": "neighbor", "details": "awaiting_help"})

        # Consuming Inbox messages
        while agent["inbox"]:
            msg = agent["inbox"].pop(0)
            sensory_events.append({"type": "auditory", "object": msg["sender"], "details": f"said: '{msg['content']}'"})

        exits = self.map.get_exits(*agent["pos"])
        exit_doors = {}
        exit_details = {}
        for direction in exits:
            dx, dy = self.map.offsets[direction]
            dest = (agent["pos"][0] + dx, agent["pos"][1] + dy)
            door = self.map.door_between(agent["pos"], dest)
            if door:
                exit_doors[direction] = door.get("state")
            exit_details[direction] = {
                "room": self.map.get_location(*dest).name,
                "visited": dest in agent["visited"],
                "door": door.get("state") if door else None,
            }
        closed_containers = [
            name for name, obj in room_objects.items()
            if isinstance(obj, dict) and "openable" in obj.get("properties", [])
            and "lockable" not in obj.get("properties", []) and obj.get("state") != "open"
        ]
        people_here = [o for o, d in self.agents.items() if o != agent_id and d["pos"] == agent["pos"]]
        heard = [f"{e['object']} {e['details']}" for e in sensory_events if e.get("type") == "auditory"]
        goal = agent["active_goal"]

        return {
            "agent_location": room_name, # Backwards compat
            "agent_pos": agent["pos"],
            "time": self.world_time,
            "time_of_day": self.time_of_day(),
            "hunger": agent["hunger"],
            "mood": agent["mood"],
            "mood_intensity": agent["mood_intensity"],
            "sensory_events": sensory_events,
            "perceivable_objects": perceivable_objects,
            "visible_items": list(self._visible_items(room_objects).keys()),
            "available_exits": exits,
            "exit_doors": exit_doors,
            "exit_details": exit_details,
            "closed_containers": closed_containers,
            "people_here": people_here,
            "heard": heard,
            "inventory": list(agent["inventory"]),
            "goal": goal["name"] if goal else None,
            "goal_steps": [s.get("desc") for s in goal["steps"]] if goal else [],
            "goal_step": self._current_goal_step(agent_id),
            "goal_progress": list(agent["current_goal_steps_done"]),
            "goal_history": list(agent["goal_history"][-5:]),
            "relationships": {k: dict(v) for k, v in self.relationships.items()},
        }

    # ------------------------------------------------------------------
    def process_action(self, action: Dict[str, str], agent_id: str = "adam1"):
        """Execute an action in the world."""
        if agent_id not in self.agents:
            return {"success": False, "reason": "Agent not found."}

        agent = self.agents[agent_id]
        verb = normalize_verb(action.get("verb"))
        target = action.get("target")
        target = None if target in NULL_TARGETS else str(target)
        instrument = action.get("instrument") # Tool Use
        instrument = None if instrument in NULL_TARGETS else instrument

        ok, why = self.validate_action({"verb": verb, "target": target, "instrument": instrument}, agent_id)
        if not ok:
            agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
            return {"success": False, "reason": why}

        if verb == "wait":
            result = {"success": True, "reason": "Time passes."}
        elif verb == "inventory":
            result = {"success": True, "reason": f"I carry: {', '.join(agent['inventory']) if agent['inventory'] else 'nothing.'}"}
        elif verb == "say":
            result = self._act_say(target, agent_id)
        elif verb == "go":
            result = self._act_move(target, agent=agent)
        else:
            loc = self.map.get_location(*agent["pos"])
            room_objects = loc.objects if loc else {}
            obj = room_objects.get(target)
            props = obj.get("properties", []) if isinstance(obj, dict) else []
            state = obj.get("state") if isinstance(obj, dict) else None
            handler = getattr(self, f"_act_{verb}")
            result = handler(target, obj, props, state, instrument=instrument, agent=agent)
        if self._update_goal_progress(verb, target, result.get("success", False), agent_id):
            result["goal_advanced"] = True
        return result

    # ------------------------------------------------------------------
    def _act_say(self, target: Optional[str], agent_id: str) -> Dict:
        """Broadcast a message to everyone in the speaker's room."""
        speaker = self.agents[agent_id]
        message = target or "..."
        self.message_seq += 1
        for other_id, other_data in self.agents.items():
            if other_id != agent_id and other_data["pos"] == speaker["pos"]:
                msg = {
                    "sender": agent_id,
                    "content": message,
                    "timestamp": self.world_time,
                    "seq": self.message_seq,
                }
                other_data["inbox"].append(msg)
                other_data["heard_log"].append(dict(msg))
                del other_data["heard_log"][:-HEARD_LOG_LIMIT]
        return {"success": True, "reason": f"I said: '{message}'"}

    # Handlers accept 'agent' kwarg which is the mutable agent state dict

    def _act_move(self, target, agent, **kwargs):
        """Handle navigation between rooms via grid."""
        if not target:
            return {"success": False, "reason": "I need a direction to move (North, South, East, West)."}

        direction = target.lower()
        curr = agent["pos"]
        new_pos = self.map.move(curr[0], curr[1], direction)

        if new_pos:
            agent["pos"] = new_pos
            agent["visited"].add(new_pos)
            loc = self.map.get_location(*new_pos)
            return {"success": True, "reason": f"I walked {direction} into the {loc.name if loc else 'unknown'}."}

        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        if direction in self.map.offsets:
            return {"success": False, "reason": f"The door to the {direction} is locked."}
        return {"success": False, "reason": f"I can't go {direction} from here."}

    def _act_examine(self, target, obj, props, state, agent, **kwargs):
        """Inspect an object."""
        agent["recent_examined"][target] = self.world_time
        if obj:
            desc = state or "unchanged"
            if obj.get("items"):
                closed = "openable" in props and state != "open"
                desc += " (it is closed)" if closed else f" (contains {', '.join(obj['items'])})"
            return {"success": True, "reason": f"I looked at the {target}. State: {desc}"}
        return {"success": True, "reason": f"I looked closely at the {target}."}

    def _act_open(self, target, obj, props, state, agent, **kwargs):
        if obj and state == "locked":
            agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
            return {"success": False, "reason": f"The {target} is locked."}
        if "openable" in props and state != "open":
            obj["state"] = "open"
            obj["opened_at"] = self.world_time
            items = obj.get("items")
            inside = f" Inside: {', '.join(items)}." if items else ""
            return {"success": True, "reason": f"I opened the {target}.{inside}"}
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't open {target}."}

    def _act_close(self, target, obj, props, state, agent, **kwargs):
        if "openable" in props and state not in {"closed", "locked"}:
            obj["state"] = "closed"
            obj.pop("opened_at", None)
            return {"success": True, "reason": f"I closed the {target}."}
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't close {target}."}

    def _act_unlock(self, target, obj, props, state, agent, **kwargs):
        if "lockable" not in props:
            return {"success": False, "reason": f"The {target} has no lock."}
        if state != "locked":
            return {"success": False, "reason": f"The {target} is not locked."}
        key = obj.get("key")
        if key and key not in agent["inventory"]:
            agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
            return {"success": False, "reason": f"I need the {key} to unlock the {target}."}
        obj["state"] = "closed"
        return {"success": True, "reason": f"I unlocked the {target}."}

    def _act_toggle(self, target, obj, props, state, agent, **kwargs):
        if "toggleable" not in props:
            agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
            return {"success": False, "reason": f"I can't toggle {target}."}
        new = "on"
        if state in {"on", "on_static"} or (state not in {None, "off"} and target != "tv"):
            new = "off"
        if target == "tv" and state == "off":
            new = "on"
        obj["state"] = new
        return {"success": True, "reason": f"I set the {target} to {new}."}

    def _act_read(self, target, obj, props, state, agent, **kwargs):
        if "readable" in props or (obj and obj.get("items")) or target in agent["inventory"]:
            agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.1)
            return {"success": True, "reason": "Reading calms me.", "state_change": {"mood_intensity": -0.1}}
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't read {target}."}

    def _act_eat(self, target, obj, props, state, agent, **kwargs):
        if obj and "eatable" in props:
            contents = obj.setdefault("contains", {})
            if contents.get("food", 0) > 0:
                contents["food"] -= 1
                prev = agent["hunger"]
                agent["hunger"] = max(0.0, prev - 0.5)
                return {
                    "success": True,
                    "reason": "I ate a quick snack.",
                    "state_change": {"hunger": agent["hunger"] - prev}
                }
            hint = " Maybe I could cook the fresh ingredients." if contents.get("fresh_ingredients", 0) > 0 else ""
            return {"success": False, "reason": f"There is no ready-to-eat food in the {target}.{hint}"}
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't eat {target}."}

    def _act_sleep(self, target, obj, props, state, agent, **kwargs):
        if "sleepable" in props:
            prev_h, prev_m = agent["hunger"], agent["mood_intensity"]
            agent["hunger"] = min(1.0, agent["hunger"] + 0.1)
            agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.3)
            return {
                "success": True,
                "reason": "I slept and feel rested.",
                "state_change": {"hunger": agent["hunger"] - prev_h, "mood_intensity": agent["mood_intensity"] - prev_m},
            }
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't sleep on {target}."}

    def _act_water(self, target, obj, props, state, agent, **kwargs):
        if "waterable" in props:
            prev = obj.get("state")
            obj["state"] = "healthy"
            return {
                "success": True,
                "reason": "I watered the plant.",
                "state_change": {f"{target}_state": (prev, "healthy")},
            }
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't water {target}."}

    def _act_take(self, target, obj, props, state, agent, **kwargs):
        loc = self.map.get_location(*agent["pos"])
        room_objects = loc.objects if loc else {}
        # An item sitting in an open container
        if obj is None:
            container_name = self._visible_items(room_objects).get(target)
            if container_name:
                room_objects[container_name]["items"].remove(target)
                agent["inventory"].append(target)
                return {"success": True, "reason": f"I took the {target} from the {container_name}."}
            return {"success": False, "reason": f"I can't take {target}."}
        if obj.get("items"):
            if "openable" in props and state != "open":
                return {"success": False, "reason": f"The {target} is closed."}
            item = obj["items"].pop(0)
            agent["inventory"].append(item)
            return {"success": True, "reason": f"I took the {item} from the {target}."}
        if "takeable" in props:
            agent["inventory"].append(target)
            room_objects.pop(target, None)
            return {"success": True, "reason": f"I picked up the {target}."}
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't take {target}."}

    def _act_drop(self, target, obj, props, state, agent, **kwargs):
        if target not in agent["inventory"]:
            return {"success": False, "reason": f"I am not carrying {target}."}
        agent["inventory"].remove(target)
        loc = self.map.get_location(*agent["pos"])
        if loc:
            loc.objects[target] = {"state": "idle", "properties": ["takeable"]}
        return {"success": True, "reason": f"I placed the {target} down."}

    def _act_use(self, target, obj, props, state, agent, instrument=None, **kwargs):
        """Context-sensitive handler for `use` actions, supporting tools."""

        # Tool Use Logic
        if instrument:
            # Example: repair with toolkit
            if target == "computer" and instrument == "toolkit" and state == "error":
                obj["state"] = "repaired_by_tool"
                agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.2)
                return {"success": True, "reason": "I used the toolkit to repair the computer hardware."}
            if target in {"door"} and "lockable" in props and instrument == obj.get("key"):
                return self._act_unlock(target, obj, props, state, agent)
            return {"success": False, "reason": f"Using the {instrument} on the {target} had no effect."}

        # Original simple use logic
        if target == "kettle":
            obj["state"] = "boiling"
            return {"success": True, "reason": "The kettle whistles softly."}

        if target == "journal":
            if "journal" in agent['inventory'] and "pen" in agent['inventory']:
                agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.1)
                return {"success": True, "reason": "Writing helps clear my mind."}
            return {"success": False, "reason": "I need something to write with."}

        if target == "computer":
            if state == "error":
                return {"success": False, "reason": "The error persists. Maybe it needs repair (use toolkit?)."}
            obj["state"] = "on"
            return {"success": True, "reason": "The computer hums to life."}

        if target in agent['inventory']:
            return {"success": True, "reason": f"I examined the {target} closely."}

        return {"success": False, "reason": f"I can't figure out how to use the {target}."}

    def _act_clean(self, target, obj, props, state, agent, **kwargs):
        if "cleanable" in props:
            self.cleanliness = min(1.0, self.cleanliness + 0.1)
            agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.05)
            return {"success": True, "reason": "Tidying up feels satisfying."}
        return {"success": False, "reason": f"Cleaning the {target} has no effect."}

    def _act_help(self, target, obj, props, state, agent, **kwargs):
        if target == "neighbor" and self.neighbor_state.get("awaiting_help"):
            self.neighbor_state["awaiting_help"] = False
            self.neighbor_state["request_cycle"] = None
            self.relationships["neighbor"]["trust"] = min(1.0, self.relationships["neighbor"].get("trust", 0.5) + 0.1)
            agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.1)
            return {"success": True, "reason": "I helped the neighbor with the package."}
        return {"success": False, "reason": "I don't see anyone who needs help."}

    def _act_repair(self, target, obj, props, state, agent, **kwargs):
        if "repairable" in props:
            if "toolkit" not in agent['inventory']:
                return {"success": False, "reason": "I need tools to repair this."}
            obj["state"] = "repaired"
            return {"success": True, "reason": f"I repaired the {target}."}
        return {"success": False, "reason": f"I can't repair {target}."}

    def _act_fill(self, target, obj, props, state, agent, **kwargs):
        if target == "kettle":
            if "water" not in agent['inventory']:
                agent['inventory'].append("water")
                return {"success": True, "reason": "I filled the kettle with water."}
            return {"success": False, "reason": "The kettle is already filled."}
        if target == "plant":
            agent['inventory'].append("water")
            return {"success": True, "reason": "I collected water for the plant."}
        return {"success": False, "reason": f"I can't fill {target}."}

    def _act_cook(self, target, obj, props, state, agent, **kwargs):
        """Consume fresh ingredients from a fridge in the same room to reduce hunger."""
        loc = self.map.get_location(*agent['pos'])
        room_objects = loc.objects if loc else {}
        fridge = room_objects.get("fridge")
        if "stove" not in room_objects or not fridge:
            return {"success": False, "reason": "I need a stove and a fridge to cook."}
        contents = fridge.setdefault("contains", {})
        if contents.get("fresh_ingredients", 0) > 0:
            contents["fresh_ingredients"] -= 1
            prev = agent["hunger"]
            agent["hunger"] = max(0.0, prev - 0.6)
            self.cleanliness = max(0.0, self.cleanliness - 0.05)
            return {
                "success": True,
                "reason": "I cooked a hearty meal.",
                "state_change": {"hunger": agent["hunger"] - prev},
            }
        return {"success": False, "reason": "There are no ingredients to cook."}

    def _act_sit(self, target, obj, props, state, agent, **kwargs):
        if "sit" in props:
            agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.05)
            return {"success": True, "reason": f"I rest briefly on the {target}."}
        return {"success": False, "reason": f"I can't sit on {target}."}

    def _act_break(self, target, obj, props, state, agent, **kwargs):
        """Violent action: Break/Destroy an object."""
        if not obj:
            return {"success": False, "reason": f"I don't see a {target} here."}

        if "breakable" in props:
            if state == "broken":
                return {"success": False, "reason": f"The {target} is already broken."}

            obj["state"] = "broken"
            agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.2) # Violence excites/agitates
            self.noise_level = min(1.0, self.noise_level + 0.5) # Loud noise
            return {"success": True, "reason": f"I smashed the {target} into pieces!", "violent": True}

        return {"success": False, "reason": f"I cannot break the {target}."}

    def _act_play(self, target, obj, props, state, agent, **kwargs):
        if target == "telescope":
            if state == "covered":
                obj["state"] = "uncovered"
            agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.07)
            return {"success": True, "reason": "Stargazing soothes me."}
        if target == "radio" and state in {"on", "on_static"}:
            agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.03)
            return {"success": True, "reason": "I sway to the radio music."}
        return {"success": False, "reason": f"I can't play with the {target}."}

    # ------------------------------------------------------------------
    def _current_goal_step(self, agent_id: str) -> Optional[Dict]:
        """Return the current step (verb/target) for the active goal."""
        if agent_id not in self.agents:
            return None
        agent = self.agents[agent_id]

        if not agent["active_goal"]:
            return None
        if agent["goal_progress_index"] >= len(agent["active_goal"]["steps"]):
            return None
        return agent["active_goal"]["steps"][agent["goal_progress_index"]]

    def _step_matches(self, step: Dict, verb: str, target: Optional[str], agent: Dict) -> bool:
        if step["action"] != verb:
            return False
        want = str(step.get("target") or "").lower()
        if not want:
            return True
        if want == str(target or "").lower():
            return True
        # "say hello" is satisfied by any message containing "hello"
        if verb == "say":
            return bool(re.search(rf"\b{re.escape(want)}\b", str(target or "").lower()))
        # "go kitchen" is satisfied by arriving in the kitchen from any direction
        if verb == "go":
            loc = self.map.get_location(*agent["pos"])
            return bool(loc) and loc.name.lower() == want
        return False

    def _update_goal_progress(self, verb: str, target: Optional[str], success: bool, agent_id: str) -> bool:
        """Advance goal pointer when the expected verb/target succeeds. Returns True if a step was completed."""
        step = self._current_goal_step(agent_id)

        if not step or not success:
            return False

        agent = self.agents[agent_id]
        if self._step_matches(step, verb, target, agent):
            agent["goal_progress_index"] += 1
            agent["current_goal_steps_done"].append(step)
            agent["goal_history"].append({"goal": agent["active_goal"]["name"], "step": step, "cycle": self.world_time})
            if agent["goal_progress_index"] >= len(agent["active_goal"]["steps"]):
                agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.1)
                if agent["active_goal"]["name"] == "Assist the neighbor":
                    self.relationships["neighbor"]["trust"] = min(1.0, self.relationships["neighbor"].get("trust", 0.5) + 0.15)
                    self.neighbor_state["awaiting_help"] = False
                    self.neighbor_state["request_cycle"] = None
                self.clear_goal(agent_id, status="completed")
            return True
        return False
