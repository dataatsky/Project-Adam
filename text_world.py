import copy
import random
import re
from typing import Dict, List, Optional, Tuple, Any

from grid_map import GridMap
from moods import normalize_mood
from sensory import SensoryCortex
from world.actions import ActionHandlers
# Re-exported so `from text_world import VERBS, NEEDS, ...` keeps working
from world.content import (  # noqa: F401
    BASE_ROOMS, DEFAULT_FATIGUE_RATE, DEFAULT_HUNGER_RATE, DEFAULT_LONELINESS_RATE, ENVIRONMENT_PRESETS,
    HEARD_LOG_LIMIT, NEEDS, OPTIONAL_ROOMS,
)
from world.vocab import NULL_TARGETS, TYPE_PROPERTIES, VERB_ALIASES, VERBS, normalize_verb  # noqa: F401


class TextWorld(ActionHandlers):
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
        self.fatigue_rate = DEFAULT_FATIGUE_RATE
        self.loneliness_rate = DEFAULT_LONELINESS_RATE
        self.random_events = True
        self.neighbor_visits = True
        self.active_events: Dict[str, Dict] = {}
        self.neighbor_state = {"awaiting_help": False, "last_visit": None}
        self.relationships = {"neighbor": {"trust": 0.5, "last_request": None}}
        self.scenario_name: Optional[str] = None
        # Global order of spoken messages, so conversations can be checked turn by turn
        self.message_seq = 0
        # Everything said recently, heard or not (for viewers)
        self.speech_log: List[Dict] = []

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
            "fatigue": float(kwargs.get("fatigue", 0.2)),
            "loneliness": float(kwargs.get("loneliness", 0.2)),
            "cold": 0.0,  # derived from the temperature every tick
            "wrapped": False,  # wrapped in a blanket
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
        self.fatigue_rate = float(world_cfg.get("fatigue_rate", DEFAULT_FATIGUE_RATE))
        self.loneliness_rate = float(world_cfg.get("loneliness_rate", DEFAULT_LONELINESS_RATE))
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
            agent["fatigue"] = round(min(1.0, agent["fatigue"] + self.fatigue_rate), 4)
            company = any(o is not agent and o["pos"] == agent["pos"] for o in self.agents.values())
            if not company:
                agent["loneliness"] = round(min(1.0, agent["loneliness"] + self.loneliness_rate), 4)
            agent["cold"] = self._coldness(agent)
            if agent["fatigue"] >= 0.8 or agent["cold"] >= 0.6:
                agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.02)
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

    def update_relationship(self, other: str, trust: Optional[float] = None, threat: Optional[bool] = None,
                            predicted_goal: Optional[str] = None):
        """Record Adam's judgement of another agent. Trust moves halfway toward each new estimate."""
        rel = self.relationships.setdefault(other, {"trust": 0.5})
        if trust is not None:
            try:
                estimate = max(0.0, min(1.0, float(trust)))
                rel["trust"] = round(0.5 * rel.get("trust", 0.5) + 0.5 * estimate, 2)
            except (TypeError, ValueError):
                pass
        if threat is not None:
            rel["threat"] = bool(threat)
        if predicted_goal:
            rel["predicted_goal"] = str(predicted_goal)

    def _coldness(self, agent: Dict) -> float:
        """0 at 19°C or warmer, 1 at 13°C or colder; a blanket cuts it by 60%."""
        cold = max(0.0, min(1.0, (19.0 - self.temperature) / 6.0))
        if agent.get("wrapped"):
            cold *= 0.4
        return round(cold, 2)

    @staticmethod
    def _relieve(agent: Dict, need: str, amount: float):
        agent[need] = round(max(0.0, agent[need] - amount), 4)

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
            "needs": {need: agent[need] for need in NEEDS},
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

        room_before = self.map.get_location(*agent["pos"])
        contents_before = {
            name: list(obj.get("items", [])) for name, obj in (room_before.objects if room_before else {}).items()
            if isinstance(obj, dict)
        }
        inventory_before = list(agent["inventory"])

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
        if result.get("success"):
            facts = self._learned_facts(verb, target, agent, room_before, contents_before, inventory_before)
            if facts:
                result["facts"] = facts
        return result

    def _learned_facts(self, verb, target, agent, room_before, contents_before, inventory_before) -> List[str]:
        """Short, durable facts an action revealed (worth keeping in long-term memory).

        e.g. "The nightstand in the bedroom contains: silver_key." or
             "Going east from the hall leads to the bedroom."
        """
        facts = []
        room = room_before.name if room_before else "void"
        if verb == "go":
            here = self.map.get_location(*agent["pos"])
            if here and room_before and here is not room_before:
                facts.append(f"Going {target} from the {room} leads to the {here.name}.")
        if verb in {"open", "examine"} and room_before:
            obj = room_before.objects.get(target)
            if isinstance(obj, dict) and obj.get("state") == "open" or (verb == "examine" and isinstance(obj, dict) and "openable" not in obj.get("properties", [])):
                items = obj.get("items") if isinstance(obj, dict) else None
                if items:
                    facts.append(f"The {target} in the {room} contains: {', '.join(items)}.")
                elif items is not None and verb == "open":
                    facts.append(f"The {target} in the {room} is empty.")
        for item in agent["inventory"]:
            if item in inventory_before:
                continue
            source = next((c for c, before in contents_before.items()
                           if item in before and item not in (room_before.objects.get(c) or {}).get("items", [])), None)
            where = f"the {source} in the {room}" if source else f"the {room}"
            facts.append(f"I found the {item} in {where}.")
        return facts

    # ------------------------------------------------------------------
    def snapshot(self) -> Dict:
        """The whole world as plain JSON-able data (for the 3D viewer and other observers)."""
        rooms = []
        for (x, y), loc in self.map.grid.items():
            objects = [
                {"name": name, "state": obj.get("state"), "type": obj.get("type"),
                 "properties": list(obj.get("properties", [])), "items": list(obj.get("items", []))}
                for name, obj in loc.objects.items() if isinstance(obj, dict) and "lockable" not in obj.get("properties", [])
            ]
            rooms.append({"x": x, "y": y, "name": loc.name, "description": loc.description, "objects": objects})
        doors = []
        for edge, door in self.map.doors.items():
            a, b = sorted(edge)
            doors.append({"a": list(a), "b": list(b), "state": door.get("state")})
        agents = []
        for agent_id, a in self.agents.items():
            goal = a["active_goal"]
            step = self._current_goal_step(agent_id)
            agents.append({
                "id": agent_id, "pos": list(a["pos"]), "mood": a["mood"], "mood_intensity": a["mood_intensity"],
                "needs": {need: a.get(need, 0.0) for need in NEEDS}, "inventory": list(a["inventory"]),
                "goal": goal["name"] if goal else None, "goal_step": step.get("desc") if step else None,
                "control_type": a["control_type"], "wrapped": bool(a.get("wrapped")),
                "visited": [list(p) for p in a.get("visited", ())],
            })
        return {
            "time": self.world_time, "time_of_day": self.time_of_day(), "lighting": self.lighting,
            "temperature": round(self.temperature, 1), "noise": round(self.noise_level, 2),
            "neighbor_awaiting_help": bool(self.neighbor_state.get("awaiting_help")),
            "relationships": {k: dict(v) for k, v in self.relationships.items()},
            "scenario": self.scenario_name, "rooms": rooms, "doors": doors, "agents": agents,
            "messages": list(self.speech_log[-10:]),
        }

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
