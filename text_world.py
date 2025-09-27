import copy
import random
from typing import Dict, List, Optional, Tuple


# Core room templates that always exist; objects include properties to gate actions
BASE_ROOMS: Dict[str, Dict] = {
    "living_room": {
        "sofa": {"state": "tidy", "properties": ["sit", "rest"]},
        "window": {"state": "closed", "properties": ["openable"]},
        "tv": {"state": "off", "properties": ["toggleable", "watchable"]},
        "radio": {"state": "off", "properties": ["toggleable"]},
        "bookshelf": {"state": "arranged", "properties": ["readable", "takeable"], "items": ["mystery_novel"]},
        "exits": ["kitchen", "bedroom", "office"],
    },
    "kitchen": {
        "fridge": {
            "state": "closed",
            "contains": {"food": 2, "fresh_ingredients": 1},
            "properties": ["openable", "eatable", "takeable"]
        },
        "stove": {"state": "off", "properties": ["cookable", "toggleable"]},
        "kettle": {"state": "idle", "properties": ["useable", "fill", "heat"]},
        "sink": {"state": "clean", "properties": ["water_source", "cleanable"]},
        "exits": ["living_room"],
    },
    "bedroom": {
        "bed": {"state": "made", "properties": ["sleepable"]},
        "desk": {"state": "tidy", "properties": ["workable"], "items": ["journal", "pen"]},
        "wardrobe": {"state": "closed", "properties": ["openable", "takeable"], "items": ["blanket"]},
        "exits": ["living_room"],
    },
    "office": {
        "computer": {"state": "off", "properties": ["toggleable", "investigatable", "repairable"]},
        "plant": {"state": "healthy", "properties": ["waterable"]},
        "whiteboard": {"state": "blank", "properties": ["writeable", "cleanable"]},
        "exits": ["living_room"],
    },
}

# Optional rooms randomly grafted onto the base layout each run
OPTIONAL_ROOMS: Dict[str, Dict] = {
    "balcony": {
        "chair": {"state": "empty", "properties": ["sit"]},
        "telescope": {"state": "covered", "properties": ["useable", "openable"]},
        "exits": ["living_room"],
    },
    "bathroom": {
        "mirror": {"state": "clear", "properties": ["lookable", "cleanable"]},
        "shower": {"state": "off", "properties": ["useable"]},
        "cabinet": {"state": "closed", "properties": ["openable", "takeable"], "items": ["first_aid", "towel"]},
        "exits": ["bedroom"],
    },
    "basement": {
        "generator": {"state": "idle", "properties": ["repairable", "useable"]},
        "storage_box": {"state": "closed", "properties": ["openable", "takeable"], "items": ["toolkit", "spare_fuse"]},
        "exits": ["kitchen"],
    },
}

# High-level ambience presets to seed lighting/temperature/noise
ENVIRONMENT_PRESETS = {
    "calm_morning": {"lighting": "day", "temperature": 21.0, "noise": 0.1},
    "storm_night": {"lighting": "night", "temperature": 18.0, "noise": 0.4},
    "winter_evening": {"lighting": "evening", "temperature": 16.0, "noise": 0.2},
}

# Lightweight task definitions Adam can pursue; each step is verb/target
GOAL_LIBRARY = [
    {
        "name": "Brew calming tea",
        "steps": [
            {"room": "kitchen", "action": "fill", "target": "kettle"},
            {"room": "kitchen", "action": "use", "target": "kettle"},
            {"room": "living_room", "action": "sit", "target": "sofa"},
        ],
    },
    {
        "name": "Tend the office plant",
        "steps": [
            {"room": "kitchen", "action": "fill", "target": "kettle"},
            {"room": "office", "action": "water", "target": "plant"},
        ],
    },
    {
        "name": "Log thoughts",
        "steps": [
            {"room": "bedroom", "action": "take", "target": "journal"},
            {"room": "bedroom", "action": "take", "target": "pen"},
            {"room": "bedroom", "action": "use", "target": "journal"},
        ],
    },
]


class TextWorld:
    """Procedural apartment sandbox feeding Adam's cognition loop.

    The world is built from a set of base rooms and optional modules; each object
    carries properties that gate which actions are valid. State evolves through
    a mix of deterministic systems (lighting/temperature drift, auto-closing
    doors) and scheduled/random events (neighbor knocks, power flickers, plant
    thirst). An agent inventory, goal tracker, and environment summary expose
    richer stimuli for Adam while keeping a manageable action surface.

    Attributes track ambient conditions (temperature, noise, cleanliness),
    emotional nudges, currently active goal steps, and a per-object cooldown
    so curiosity stimuli don't spam the agent. The API surface mirrors the old
    text world: `get_world_state()` returns observations; `process_action()`
    mutates state and produces a success/failure dictionary; `update()` advances
    time.
    """

    def __init__(self, seed: Optional[int] = None):
        self.random = random.Random(seed)
        self.agent_location = "living_room"
        self.world_time = 0
        self.agent_inventory: List[str] = []
        self.hunger = 0.25
        self.mood_intensity = 0.4
        self.temperature = 21.0
        self.noise_level = 0.1
        self.lighting = "day"
        self.cleanliness = 0.8
        self.recent_examined: Dict[str, int] = {}
        self.active_events: Dict[str, Dict] = {}
        self.neighbor_state = {"awaiting_help": False, "last_visit": None}
        self.active_goal: Optional[Dict] = None
        self.goal_progress_index = 0
        self.world_state = self._generate_layout()
        self._choose_environment_theme()
        self._ensure_goal()

    # ------------------------------------------------------------------
    def clone(self):
        """Return a deep copy so imagination/reflection can simulate branches."""
        return copy.deepcopy(self)

    def _generate_layout(self) -> Dict[str, Dict]:
        """Materialize the initial room graph.

        Copies the base room templates and then samples a random subset of
        optional rooms, stitching exits to ensure bidirectional navigation.  A
        fresh dict is produced each run so the layout can vary per episode.
        """
        layout = copy.deepcopy(BASE_ROOMS)
        optional_keys = list(OPTIONAL_ROOMS.keys())
        selected_optional = self.random.sample(optional_keys, k=self.random.randint(1, len(optional_keys)))
        for key in selected_optional:
            layout[key] = copy.deepcopy(OPTIONAL_ROOMS[key])
            # ensure exit connectivity
            for room in layout[key].get("exits", []):
                layout.setdefault(room, {}).setdefault("exits", []).append(key)
        return layout

    def _choose_environment_theme(self):
        """Pick an ambience preset (lighting/temp/noise) as the starting mood."""
        theme = self.random.choice(list(ENVIRONMENT_PRESETS.values()))
        self.lighting = theme["lighting"]
        self.temperature = theme["temperature"]
        self.noise_level = theme["noise"]

    def _ensure_goal(self):
        """Populate `active_goal` if empty so the agent always has direction."""
        if not self.active_goal:
            goal = copy.deepcopy(self.random.choice(GOAL_LIBRARY))
            self.active_goal = goal
            self.goal_progress_index = 0

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
        - gradually adjusts ambience (lighting, temperature, noise, cleanliness)
        - resolves cooldowns for examined/open objects
        - schedules periodic neighbor visits
        - triggers occasional random events
        - restocks consumables (e.g., fridge food) on a cadence

        Returns a list of narrative snippets describing notable events that
        occurred this tick; the cognitive loop currently ignores it but the log
        feed or GUI could surface them.
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

        # manage open objects cooldown
        cooldown = 3
        stale = [obj for obj, t in self.recent_examined.items() if self.world_time - t > cooldown]
        for obj in stale:
            self.recent_examined.pop(obj, None)

        # auto close openables after a few ticks
        for room in self.world_state.values():
            for obj in room.values():
                if isinstance(obj, dict) and obj.get("state") == "open" and obj.get("opened_at") is not None:
                    if self.world_time - obj["opened_at"] >= 3:
                        obj["state"] = "closed"
                        obj.pop("opened_at", None)

        # scheduled neighbor visit every 12 ticks
        if self.world_time % 12 == 0 and not self.neighbor_state["awaiting_help"]:
            self.neighbor_state.update({"awaiting_help": True, "last_visit": self.world_time})
            events.append("A neighbor knocked and asked for help with a package.")
            self.noise_level = min(1.0, self.noise_level + 0.2)

        # random events for variety (power flickers, drafts, etc.)
        if self.random.random() < 0.15:
            self._trigger_random_event(events)

        # restock fridge occasionally
        fridge = self.world_state.get("kitchen", {}).get("fridge")
        if fridge and self.world_time % 18 == 0:
            fridge.setdefault("contains", {})
            fridge["contains"]["food"] = fridge["contains"].get("food", 0) + 1

        return events

    def _trigger_random_event(self, events: List[str]):
        """Select and apply a stochastic micro-event (power flicker, draft, etc.)."""
        options = ["power_flicker", "radio_static", "draft", "plant_thirsty", "computer_error"]
        event = self.random.choice(options)
        if event == "power_flicker":
            self.lighting = "evening"
            self.noise_level = min(1.0, self.noise_level + 0.2)
            events.append("The lights flicker, casting long shadows.")
        elif event == "radio_static":
            room = self.world_state.get("living_room", {})
            if "radio" in room:
                room["radio"]["state"] = "on_static"
                events.append("The radio bursts into static noise.")
                self.noise_level = min(1.0, self.noise_level + 0.3)
        elif event == "draft":
            room = self.world_state.get("living_room", {})
            if "window" in room:
                room["window"]["state"] = "open"
                room["window"]["opened_at"] = self.world_time
                events.append("A chilly draft slips through the open window.")
                self.temperature = max(15.0, self.temperature - 1.5)
        elif event == "plant_thirsty":
            plant = self.world_state.get("office", {}).get("plant")
            if plant and plant.get("state") == "healthy":
                plant["state"] = "wilted"
                events.append("The office plant droops, thirsty for water.")
        elif event == "computer_error":
            comp = self.world_state.get("office", {}).get("computer")
            if comp:
                comp["state"] = "error"
                events.append("The computer displays a cryptic error message.")

    # ------------------------------------------------------------------
    def _environment_summary(self) -> Tuple[str, float]:
        """Summarize ambience and compute a mood adjustment.

        Returns a tuple of (string summary, numeric delta) capturing how the
        environment should make Adam feel (e.g., cold room reduces comfort).
        The caller applies the delta to `mood_intensity` to keep mood tied to
        environmental factors.
        """
        mood_delta = 0.0
        notes = []
        if self.temperature < 18:
            mood_delta -= 0.05
            notes.append("It feels chilly.")
        elif self.temperature > 23:
            mood_delta -= 0.05
            notes.append("It feels stuffy.")
        else:
            mood_delta += 0.05
            notes.append("The temperature is comfortable.")

        if self.noise_level > 0.4:
            mood_delta -= 0.05
            notes.append("Persistent noise hums in the background.")
        elif self.noise_level < 0.15:
            mood_delta += 0.02
            notes.append("The apartment is peacefully quiet.")

        if self.cleanliness < 0.4:
            mood_delta -= 0.05
            notes.append("Clutter is building up.")
        elif self.cleanliness > 0.7:
            mood_delta += 0.02
            notes.append("Everything feels tidy.")

        return " ".join(notes), mood_delta

    def get_world_state(self):
        """Produce the observation payload consumed by the cognition loop.

        Includes ambient summary, notable object states, an occasional idle
        object prompt, social cues (neighbor awaiting help), the inventory, and
        goal metadata so the LLM can plan multi-step actions.
        """
        sensory_events = []
        room = self.world_state.get(self.agent_location, {})

        summary, mood_adjust = self._environment_summary()
        sensory_events.append({"type": "ambience", "details": summary.strip() or f"It is {self.time_of_day()}."})
        if mood_adjust:
            self.mood_intensity = max(0.0, min(1.0, self.mood_intensity + mood_adjust))

        notable_states = {
            "phone": ["ringing"],
            "door": ["knocking", "open"],
            "tv": ["on", "on_static"],
            "radio": ["on", "on_static"],
            "computer": ["error", "on"],
            "plant": ["wilted"],
            "window": ["open"],
        }

        for obj, properties in room.items():
            if obj == "exits":
                continue
            if not isinstance(properties, dict):
                continue
            state = properties.get("state")
            if obj in notable_states and state in notable_states[obj]:
                if obj in self.recent_examined and self.world_time - self.recent_examined[obj] <= 3:
                    continue
                sensory_events.append({"type": "sight/sound", "object": obj, "details": state})

        perceivable_objects = [obj for obj in room.keys() if obj != "exits"]
        if perceivable_objects:
            idle_candidates = [obj for obj in perceivable_objects if obj not in {evt.get("object") for evt in sensory_events}]
            if idle_candidates and self.random.random() < 0.35:
                idle_obj = self.random.choice(idle_candidates)
                sensory_events.append({"type": "sight/sound", "object": idle_obj, "details": "idle"})

        if self.neighbor_state["awaiting_help"]:
            sensory_events.append({"type": "social", "object": "neighbor", "details": "awaiting_help"})

        return {
            "agent_location": self.agent_location,
            "time": self.world_time,
            "time_of_day": self.time_of_day(),
            "hunger": self.hunger,
            "mood_intensity": self.mood_intensity,
            "sensory_events": sensory_events,
            "perceivable_objects": perceivable_objects,
            "available_exits": room.get("exits", []),
            "inventory": list(self.agent_inventory),
            "goal": self.active_goal["name"] if self.active_goal else None,
            "goal_step": self._current_goal_step(),
        }

    # ------------------------------------------------------------------
    def process_action(self, action: Dict[str, str]):
        """Execute an action in the world.

        Dispatches on verb, validates the target, updates world/agent state, and
        returns a dictionary describing success, narrative reason, and optional
        state deltas (e.g., hunger change). Unknown verbs degrade to a safe
        failure case that nudges mood intensity upward.
        """
        verb = action.get("verb")
        target = action.get("target")

        if verb == "wait":
            return {"success": True, "reason": "Time passes."}

        if verb == "go":
            return self._act_move(target)

        if verb == "inventory":
            return {"success": True, "reason": f"I carry: {', '.join(self.agent_inventory) if self.agent_inventory else 'nothing.'}"}

        room = self.world_state.get(self.agent_location)
        if not room:
            return {"success": False, "reason": "The surroundings feel undefined."}

        if target not in room and verb not in {"drop", "use", "inventory", "wait"}:
            return {"success": False, "reason": f"I don't see a {target} here."}

        obj = room.get(target)
        props = obj.get("properties", []) if isinstance(obj, dict) else []
        state = obj.get("state") if isinstance(obj, dict) else None

        handler_map = {
            "examine": self._act_examine,
            "investigate": self._act_examine,
            "open": self._act_open,
            "close": self._act_close,
            "toggle": self._act_toggle,
            "turn_on": self._act_toggle,
            "turn_off": self._act_toggle,
            "read": self._act_read,
            "eat": self._act_eat,
            "sleep": self._act_sleep,
            "water": self._act_water,
            "take": self._act_take,
            "drop": self._act_drop,
            "use": self._act_use,
            "clean": self._act_clean,
            "repair": self._act_repair,
            "fill": self._act_fill,
            "cook": self._act_cook,
            "sit": self._act_sit,
            "play": self._act_play,
        }

        if verb not in handler_map:
            self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            return {"success": False, "reason": f"I tried to {verb} the {target}, but nothing happened."}

        result = handler_map[verb](target, obj, props, state)
        self._update_goal_progress(verb, target, result.get("success", False))
        return result

    # ------------------------------------------------------------------
    def _act_move(self, target):
        """Handle navigation between rooms via exits."""
        room = self.world_state.get(self.agent_location, {})
        if target in room.get("exits", []):
            self.agent_location = target
            return {"success": True, "reason": f"I walked into the {target}."}
        self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
        return {"success": False, "reason": f"I can't go to the {target}."}

    def _act_examine(self, target, obj, props, state):
        """Inspect an object.

        Marks the object as recently examined (so it doesn't trigger curiosity
        immediately again) and returns a descriptive string, including visible
        contents when available.
        """
        if obj:
            self.recent_examined[target] = self.world_time
            desc = state or "unchanged"
            if isinstance(obj, dict) and obj.get("items"):
                items = ", ".join(obj["items"])
                desc += f" (contains {items})"
            return {"success": True, "reason": f"I looked at the {target}. State: {desc}"}
        return {"success": False, "reason": f"I can't see the {target}."}

    def _act_open(self, target, obj, props, state):
        if "openable" in props and state != "open":
            obj["state"] = "open"
            obj["opened_at"] = self.world_time
            return {"success": True, "reason": f"I opened the {target}."}
        self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
        return {"success": False, "reason": f"I can't open {target}."}

    def _act_close(self, target, obj, props, state):
        if "openable" in props and state != "closed":
            obj["state"] = "closed"
            obj.pop("opened_at", None)
            return {"success": True, "reason": f"I closed the {target}."}
        self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
        return {"success": False, "reason": f"I can't close {target}."}

    def _act_toggle(self, target, obj, props, state):
        if "toggleable" not in props:
            self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            return {"success": False, "reason": f"I can't toggle {target}."}
        new = "on"
        if state in {"on", "on_static"} or (state not in {None, "off"} and target != "tv"):
            new = "off"
        if target == "tv" and state == "off":
            new = "on"
        obj["state"] = new
        return {"success": True, "reason": f"I set the {target} to {new}."}

    def _act_read(self, target, obj, props, state):
        if "readable" in props or (obj and obj.get("items")):
            self.mood_intensity = max(0.0, self.mood_intensity - 0.1)
            return {"success": True, "reason": "Reading calms me.", "state_change": {"mood_intensity": -0.1}}
        self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
        return {"success": False, "reason": f"I can't read {target}."}

    def _act_eat(self, target, obj, props, state):
        if target == "fridge":
            contents = obj.setdefault("contains", {})
            if contents.get("food", 0) > 0:
                contents["food"] -= 1
                prev = self.hunger
                self.hunger = max(0.0, prev - 0.5)
                return {
                    "success": True,
                    "reason": "I ate a quick snack.",
                    "state_change": {"hunger": self.hunger - prev}
                }
            return {"success": False, "reason": "The fridge is empty."}
        self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
        return {"success": False, "reason": f"I can't eat {target}."}

    def _act_sleep(self, target, obj, props, state):
        if "sleepable" in props:
            prev_h, prev_m = self.hunger, self.mood_intensity
            self.hunger = min(1.0, self.hunger + 0.1)
            self.mood_intensity = max(0.0, self.mood_intensity - 0.3)
            return {
                "success": True,
                "reason": "I slept and feel rested.",
                "state_change": {"hunger": self.hunger - prev_h, "mood_intensity": self.mood_intensity - prev_m},
            }
        self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
        return {"success": False, "reason": f"I can't sleep on {target}."}

    def _act_water(self, target, obj, props, state):
        if "waterable" in props:
            prev = obj.get("state")
            obj["state"] = "healthy"
            return {
                "success": True,
                "reason": "I watered the plant.",
                "state_change": {f"{target}_state": (prev, "healthy")},
            }
        self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
        return {"success": False, "reason": f"I can't water {target}."}

    def _act_take(self, target, obj, props, state):
        if target == "drop":
            return {"success": False, "reason": "What should I take?"}
        if isinstance(obj, dict) and ("takeable" in props or obj.get("items")):
            if obj.get("items"):
                item = obj["items"].pop(0)
                self.agent_inventory.append(item)
                return {"success": True, "reason": f"I took the {item} from the {target}."}
            self.agent_inventory.append(target)
            room = self.world_state[self.agent_location]
            room.pop(target, None)
            return {"success": True, "reason": f"I picked up the {target}."}
        self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
        return {"success": False, "reason": f"I can't take {target}."}

    def _act_drop(self, target, obj, props, state):
        if target not in self.agent_inventory:
            return {"success": False, "reason": f"I am not carrying {target}."}
        self.agent_inventory.remove(target)
        room = self.world_state[self.agent_location]
        room[target] = {"state": "idle", "properties": ["takeable"]}
        return {"success": True, "reason": f"I placed the {target} down."}

    def _act_use(self, target, obj, props, state):
        """Context-sensitive handler for `use` actions (kettle/journal/computer/items)."""
        if target == "kettle":
            if "water" in self.agent_inventory:
                self.agent_inventory.remove("water")
                obj["state"] = "boiling"
                self.noise_level = min(1.0, self.noise_level + 0.05)
                return {"success": True, "reason": "The kettle whistles softly."}
            return {"success": False, "reason": "The kettle needs water first."}
        if target == "journal":
            if "journal" in self.agent_inventory and "pen" in self.agent_inventory:
                self.mood_intensity = max(0.0, self.mood_intensity - 0.1)
                return {"success": True, "reason": "Writing helps clear my mind."}
            return {"success": False, "reason": "I need something to write with."}
        if target == "computer":
            if state == "error":
                return {"success": False, "reason": "The error persists. Maybe it needs repair."}
            obj["state"] = "on"
            return {"success": True, "reason": "The computer hums to life."}
        if target in self.agent_inventory:
            return {"success": True, "reason": f"I examined the {target} closely."}
        return {"success": False, "reason": f"I can't figure out how to use the {target}."}

    def _act_clean(self, target, obj, props, state):
        if "cleanable" in props or target == "room":
            self.cleanliness = min(1.0, self.cleanliness + 0.1)
            return {"success": True, "reason": "Tidying up feels satisfying."}
        return {"success": False, "reason": f"Cleaning the {target} has no effect."}

    def _act_repair(self, target, obj, props, state):
        if "repairable" in props:
            toolkit = "toolkit" in self.agent_inventory
            if not toolkit:
                return {"success": False, "reason": "I need tools to repair this."}
            obj["state"] = "repaired"
            return {"success": True, "reason": f"I repaired the {target}."}
        return {"success": False, "reason": f"I can't repair {target}."}

    def _act_fill(self, target, obj, props, state):
        if target == "kettle":
            if "water" not in self.agent_inventory:
                self.agent_inventory.append("water")
                return {"success": True, "reason": "I filled the kettle with water."}
            return {"success": False, "reason": "The kettle is already filled."}
        if target == "plant":
            self.agent_inventory.append("water")
            return {"success": True, "reason": "I collected water for the plant."}
        return {"success": False, "reason": f"I can't fill {target}."}

    def _act_cook(self, target, obj, props, state):
        """Consume ingredients to reduce hunger; requires kitchen context."""
        stove = self.world_state.get("kitchen", {}).get("stove")
        fridge = self.world_state.get("kitchen", {}).get("fridge")
        if self.agent_location != "kitchen" or not stove or not fridge:
            return {"success": False, "reason": "I need to be in the kitchen to cook."}
        contents = fridge.setdefault("contains", {})
        if contents.get("fresh_ingredients", 0) > 0:
            contents["fresh_ingredients"] -= 1
            prev = self.hunger
            self.hunger = max(0.0, prev - 0.6)
            self.cleanliness = max(0.0, self.cleanliness - 0.05)
            return {
                "success": True,
                "reason": "I cooked a hearty meal.",
                "state_change": {"hunger": self.hunger - prev},
            }
        return {"success": False, "reason": "There are no ingredients to cook."}

    def _act_sit(self, target, obj, props, state):
        if "sit" in props:
            self.mood_intensity = max(0.0, self.mood_intensity - 0.05)
            return {"success": True, "reason": f"I rest briefly on the {target}."}
        return {"success": False, "reason": f"I can't sit on {target}."}

    def _act_play(self, target, obj, props, state):
        if target == "telescope":
            if state == "covered":
                obj["state"] = "uncovered"
            self.mood_intensity = max(0.0, self.mood_intensity - 0.07)
            return {"success": True, "reason": "Stargazing soothes me."}
        if target == "radio" and state in {"on", "on_static"}:
            self.mood_intensity = max(0.0, self.mood_intensity - 0.03)
            return {"success": True, "reason": "I sway to the radio music."}
        return {"success": False, "reason": f"I can't play with the {target}."}

    # ------------------------------------------------------------------
    def _current_goal_step(self) -> Optional[Dict]:
        """Return the current step (verb/target) for the active goal."""
        if not self.active_goal:
            return None
        if self.goal_progress_index >= len(self.active_goal["steps"]):
            return None
        return self.active_goal["steps"][self.goal_progress_index]

    def _update_goal_progress(self, verb: str, target: Optional[str], success: bool):
        """Advance goal pointer when the expected verb/target succeeds."""
        step = self._current_goal_step()
        if not step or not success:
            return
        if step["action"] == verb and step.get("target") == target:
            self.goal_progress_index += 1
            if self.goal_progress_index >= len(self.active_goal["steps"]):
                # complete
                self.mood_intensity = max(0.0, self.mood_intensity - 0.1)
                self.cleanliness = max(0.0, self.cleanliness - 0.02)
                self.active_goal = None
                self._ensure_goal()
