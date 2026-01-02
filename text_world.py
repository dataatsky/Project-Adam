import copy
import random
from typing import Dict, List, Optional, Tuple, Any

from grid_map import GridMap
from sensory import SensoryCortex

# Core room templates that always exist; objects include properties to gate actions
BASE_ROOMS: Dict[str, Dict] = {
    "living_room": {
        "sofa": {"state": "tidy", "properties": ["sit", "rest"]},
        "window": {"state": "closed", "properties": ["openable"]},
        "tv": {"state": "off", "properties": ["toggleable", "watchable"]},
        "radio": {"state": "off", "properties": ["toggleable"]},
        "bookshelf": {"state": "arranged", "properties": ["readable", "takeable"], "items": ["mystery_novel"]},
        # Exits removed from template, layout is defined by GridMap
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
    },
    "bedroom": {
        "bed": {"state": "made", "properties": ["sleepable"]},
        "desk": {"state": "tidy", "properties": ["workable"], "items": ["journal", "pen"]},
        "wardrobe": {"state": "closed", "properties": ["openable", "takeable"], "items": ["blanket"]},
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
        "cabinet": {"state": "closed", "properties": ["openable", "takeable"], "items": ["first_aid", "towel"]},
    },
    "basement": {
        "generator": {"state": "idle", "properties": ["repairable", "useable"]},
        "storage_box": {"state": "closed", "properties": ["openable", "takeable"], "items": ["toolkit", "spare_fuse"]},
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
    {
        "name": "Assist the neighbor",
        "steps": [
            {"room": "living_room", "action": "help", "target": "neighbor"},
        ],
    },
]


class TextWorld:
    """Procedural apartment sandbox feeding Adam's cognition loop.

    The world is built from a set of base rooms and optional modules mapped to
    a 2D GridMap. This enables cardinal navigation (N/S/E/W) and spatial
    relationships.
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
        self.active_events: Dict[str, Dict] = {}
        self.neighbor_state = {"awaiting_help": False, "last_visit": None}
        self.relationships = {"neighbor": {"trust": 0.5, "last_request": None}}
           
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
        """Register a new agent in the world."""
        start_pos = (0, 0) # Living Room
        if agent_id not in self.agents:
            self.agents[agent_id] = {
                "id": agent_id,
                "pos": start_pos,
                "inventory": [],
                "hunger": 0.25,
                "mood_intensity": 0.4,
                "mood_intensity": 0.4,
                "active_goal": None,
                "goal_progress_index": 0,
                "current_goal_steps_done": [],
                "goal_history": [],
                "recent_examined": {},
                "inbox": [],
                "script": kwargs.get("script", []), 
                "control_type": kwargs.get("control_type", "autonomous") 
            }
            # Initial goal setup
            self._ensure_goal(agent_id)

    @property
    def agent_pos(self) -> Tuple[int, int]:
        """Backward compatibility: adam1 pos."""
        return self.agents["adam1"]["pos"]
    
    @agent_pos.setter
    def agent_pos(self, value):
        self.agents["adam1"]["pos"] = value

    @property
    def agent_inventory(self) -> List[str]:
        return self.agents["adam1"]["inventory"]
    
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
        # Logic: find an open spot adjacent to a compatible base room
        # For simplicity in this iteration, we map them purely additively
        optional_opportunities = [
            ("balcony", (0, -1), "living_room"), # South of Living Room
            ("bathroom", (1, 1), "bedroom"),     # North of Bedroom (also East of Kitchen)
            ("basement", (0, 2), "kitchen")      # North of Kitchen
        ]
        
        # Randomly select 1-2 optional rooms
        chosen_extras = self.random.sample(optional_opportunities, k=self.random.randint(1, 2))
        
        for name, coords, anchor_room in chosen_extras:
            if name not in OPTIONAL_ROOMS: continue
            
            # Simple check if spot is taken (unlikely with this hardcoded set but good practice)
            if self.map.get_location(coords[0], coords[1]):
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

    def _load_from_scenario(self, config: Dict):
        """Build world from scenario config."""
        layout = config.get("map_layout", {})
        
        # 1. Rooms
        for room in layout.get("rooms", []):
            x, y = room["coords"]
            name = room["name"]
            desc = room.get("desc", f"A {name}.")
            objs = layout.get("objects", {}).get((x, y), {})
            # Ensure proper dict format for objects if defined as simple dict
            final_objs = {}
            for k, v in objs.items():
                if isinstance(v, dict) and "type" in v:
                    final_objs[k] = v
                else: 
                     # fallback
                     final_objs[k] = {"state": "exist", "properties": []}
            
            self.map.add_location(x, y, name, desc, final_objs)
            self.room_coords[name] = (x, y)

        # 2. Doors (Optional explicit locks)
        # TODO: Implement door locks in GridMap if needed, for now ignored or handled via object logic

        # 3. Agents
        agents = config.get("agents", {})
        for agent_id, data in agents.items():
            self.add_agent(agent_id)
            # Override defaults
            self.agents[agent_id]["pos"] = data.get("pos", (0, 0))
            self.agents[agent_id]["hunger"] = data.get("hunger", 0.0)
            self.agents[agent_id]["inventory"] = data.get("inventory", [])
            self.agents[agent_id]["script"] = data.get("script", [])
            self.agents[agent_id]["control_type"] = data.get("control_type", "autonomous")

    def set_goal(self, goal_name: str, steps: list[str] = None, agent_id: str = "adam1"):
        """Manually set the agent's goal, clearing progress."""
        if agent_id not in self.agents: return
        agent = self.agents[agent_id]
        
        parsed_steps = []
        if steps:
            for s in steps:
                # Naive parsing into verb/target for tracking
                parts = s.lower().split()
                if len(parts) >= 2:
                    parsed_steps.append({"action": parts[0], "target": parts[-1], "desc": s})
                else:
                    parsed_steps.append({"action": "wait", "target": "null", "desc": s})
        else:
             # Fallback dummy steps
             parsed_steps = [
                {"action": "examine", "target": "environment"},
                {"action": "explore", "target": "house"},
             ]

        agent["active_goal"] = {
            "name": goal_name,
            "steps": parsed_steps
        }
        agent["goal_progress_index"] = 0
        agent["current_goal_steps_done"] = []
    
    def _ensure_goal(self, agent_id: str = "adam1"):
        """Populate `active_goal` if empty so the agent always has direction.
           NOW OPTIONAL: We want to allow 'None' goals so the agent can propose them.
        """
        # DISABLED AUTO-ASSIGNMENT for Phase 3 Agency
        pass 
        # if agent_id not in self.agents: return
        # agent = self.agents[agent_id]
        # if not agent["active_goal"]:
        #     goal = copy.deepcopy(self.random.choice(GOAL_LIBRARY))
        #     agent["active_goal"] = goal
        #     agent["goal_progress_index"] = 0
        #     agent["current_goal_steps_done"] = []

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
        for loc in self.map.grid.values():
            for obj in loc.objects.values():
                if isinstance(obj, dict) and obj.get("state") == "open" and obj.get("opened_at") is not None:
                    if self.world_time - obj["opened_at"] >= 3:
                        obj["state"] = "closed"
                        obj.pop("opened_at", None)

        # scheduled neighbor visit every 12 ticks
        if self.world_time % 12 == 0 and not self.neighbor_state["awaiting_help"]:
            self.neighbor_state.update({"awaiting_help": True, "last_visit": self.world_time, "request_cycle": self.world_time})
            events.append("A neighbor knocked and asked for help with a package.")
            self.noise_level = min(1.0, self.noise_level + 0.2)
            self.relationships["neighbor"]["last_request"] = self.world_time

        req_cycle = self.neighbor_state.get("request_cycle")
        if self.neighbor_state.get("awaiting_help") and req_cycle:
            if self.world_time - req_cycle > 5:
                self.relationships["neighbor"]["trust"] = max(0.1, self.relationships["neighbor"].get("trust", 0.5) - 0.05)
                self.neighbor_state["request_cycle"] = self.world_time
                self.mood_intensity = min(1.0, self.mood_intensity + 0.05)

        # random events for variety (power flickers, drafts, etc.)
        if self.random.random() < 0.15:
            self._trigger_random_event(events)

        # Process Agents
        for agent_id, agent_data in self.agents.items():
            # Scripted Agents
            if agent_data.get("control_type") == "scripted":
                script = agent_data.get("script", [])
                if script:
                    # Pop first action
                    action_str = script.pop(0)
                    # Parse simple "verb target" or "verb"
                    parts = action_str.split(" ", 1)
                    verb = parts[0]
                    target = parts[1] if len(parts) > 1 else None
                    target = parts[1] if len(parts) > 1 else None
                    # Execute
                    # Found signature: process_action(self, action: Dict[str, str], agent_id: str = "adam1")
                    action_payload = {"verb": verb, "target": target or ""}
                    result = self.process_action(action_payload, agent_id=agent_id)
                    
                    # Append events if observable by main agent
                    if verb == "say":
                         events.append(f"{agent_id} says: '{target}'")
                else:
                    # Loop script? Or stop. Default loop for annoyance.
                    pass 


        # restock fridge occasionally
        kitchen_loc = self.map.get_location(*self.room_coords.get("kitchen", (0, 1)))
        if kitchen_loc:
            fridge = kitchen_loc.objects.get("fridge")
            if fridge and self.world_time % 18 == 0:
                fridge.setdefault("contains", {})
                fridge["contains"]["food"] = fridge["contains"].get("food", 0) + 1

        return events

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
        # Instantiate strictly for this call (stateless usage pattern) or could be a member
        cortex = SensoryCortex()
        return cortex.transduce(
            self.temperature, 
            self.noise_level, 
            self.cleanliness, 
            self.lighting
        )

    def get_world_state(self, agent_id: str = "adam1"):
        """Produce the observation payload consumed by the cognition loop."""
        if agent_id not in self.agents: return {}
        agent = self.agents[agent_id]
        
        sensory_events = []
        # Current Location
        loc = self.map.get_location(*agent["pos"])
        room_objects = loc.objects if loc else {}
        room_name = loc.name if loc else "void"

        summary, mood_adjust = self._environment_summary()
        intro = f"I am in the {room_name}. {loc.description}" if loc else summary
        sensory_events.append({"type": "ambience", "details": intro})
        if mood_adjust:
            agent["mood_intensity"] = max(0.0, min(1.0, agent["mood_intensity"] + mood_adjust))

        notable_states = {
            "phone": ["ringing"],
            "door": ["knocking", "open"],
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

        perceivable_objects = list(room_objects.keys())
        if perceivable_objects:
            idle_candidates = [obj for obj in perceivable_objects if obj not in {evt.get("object") for evt in sensory_events}]
            # TODO: restore random idle object perception logic if needed
            pass

        if self.neighbor_state["awaiting_help"]:
            sensory_events.append({"type": "social", "object": "neighbor", "details": "awaiting_help"})
        
        # Consuming Inbox messages
        if "inbox" in agent:
            while agent["inbox"]:
                msg = agent["inbox"].pop(0)
                sensory_events.append({"type": "auditory", "object": msg["sender"], "details": f"said: '{msg['content']}'"})

        perceivable_objects = list(room_objects.keys())
        exits = self.map.get_exits(*agent["pos"])

        return {
            "agent_location": room_name, # Backwards compat
            "agent_pos": agent["pos"],
            "time": self.world_time,
            "time_of_day": self.time_of_day(),
            "hunger": agent["hunger"],
            "mood_intensity": agent["mood_intensity"],
            "sensory_events": sensory_events,
            "perceivable_objects": perceivable_objects,
            "available_exits": exits,
            "inventory": list(agent["inventory"]),
            "goal": agent["active_goal"]["name"] if agent["active_goal"] else None,
            "goal_step": self._current_goal_step(agent_id),
            "goal_progress": list(agent["current_goal_steps_done"]),
            "goal_history": list(agent["goal_history"][-5:]),
            "relationships": {k: dict(v) for k, v in self.relationships.items()},
        }

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    def process_action(self, action: Dict[str, str], agent_id: str = "adam1"):
        """Execute an action in the world."""
        if agent_id not in self.agents:
            return {"success": False, "reason": "Agent not found."}
        
        agent = self.agents[agent_id]
        
        verb = action.get("verb")
        target = action.get("target")
        instrument = action.get("instrument") # Tool Use

        if verb == "wait":
            return {"success": True, "reason": "Time passes."}

        if verb == "say":
             # Broadcast to others in room
             message = target or "..."
             for other_id, other_data in self.agents.items():
                 if other_id != agent_id and other_data["pos"] == agent["pos"]:
                     other_data.setdefault("inbox", []).append({
                         "sender": agent_id,
                         "content": message,
                         "timestamp": self.world_time
                     })
             return {"success": True, "reason": f"I said: '{message}'"}

        if verb == "go":
            return self._act_move(target, agent=agent)

        if verb == "inventory":
            return {"success": True, "reason": f"I carry: {', '.join(agent['inventory']) if agent['inventory'] else 'nothing.'}"}

        # Context: Current Room
        loc = self.map.get_location(*agent["pos"])
        if not loc:
             return {"success": False, "reason": "The surroundings feel undefined."}
        
        room_objects = loc.objects

        if target not in room_objects and verb not in {"drop", "use", "inventory", "wait", "help", "say"}:
            return {"success": False, "reason": f"I don't see a {target} here."}

        obj = room_objects.get(target)
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
            "help": self._act_help,
            "break": self._act_break,
            "smash": self._act_break,
            "destroy": self._act_break,
        }

        if verb not in handler_map:
            agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
            return {"success": False, "reason": f"I tried to {verb} the {target}, but nothing happened."}
        
        result = handler_map[verb](target, obj, props, state, instrument=instrument, agent=agent)
        self._update_goal_progress(verb, target, result.get("success", False), agent_id)
        return result

    # ------------------------------------------------------------------
    # Handlers now accept 'agent' kwarg which is the mutable agent state dict
    
    def _act_move(self, target, agent, **kwargs):
        """Handle navigation between rooms via grid."""
        if not target:
            return {"success": False, "reason": "I need a direction to move (North, South, East, West)."}
            
        direction = target.lower()
        curr = agent["pos"]
        new_pos = self.map.move(curr[0], curr[1], direction)
        
        if new_pos:
            agent["pos"] = new_pos
            loc = self.map.get_location(*new_pos)
            return {"success": True, "reason": f"I walked {direction} into the {loc.name if loc else 'unknown'}."}
        
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't go {direction} from here."}

    def _act_examine(self, target, obj, props, state, agent, **kwargs):
        """Inspect an object."""
        if obj:
            agent["recent_examined"][target] = self.world_time
            desc = state or "unchanged"
            if isinstance(obj, dict) and obj.get("items"):
                items = ", ".join(obj["items"])
                desc += f" (contains {items})"
            return {"success": True, "reason": f"I looked at the {target}. State: {desc}"}
        return {"success": False, "reason": f"I can't see the {target}."}

    def _act_open(self, target, obj, props, state, agent, **kwargs):
        if "openable" in props and state != "open":
            obj["state"] = "open"
            obj["opened_at"] = self.world_time
            return {"success": True, "reason": f"I opened the {target}."}
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't open {target}."}

    def _act_close(self, target, obj, props, state, agent, **kwargs):
        if "openable" in props and state != "closed":
            obj["state"] = "closed"
            obj.pop("opened_at", None)
            return {"success": True, "reason": f"I closed the {target}."}
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't close {target}."}

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
        if "readable" in props or (obj and obj.get("items")):
            agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.1)
            return {"success": True, "reason": "Reading calms me.", "state_change": {"mood_intensity": -0.1}}
        agent["mood_intensity"] = min(1.0, agent["mood_intensity"] + 0.05)
        return {"success": False, "reason": f"I can't read {target}."}

    def _act_eat(self, target, obj, props, state, agent, **kwargs):
        if target == "fridge":
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
            return {"success": False, "reason": "The fridge is empty."}
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
        if target == "drop":
            return {"success": False, "reason": "What should I take?"}
        if isinstance(obj, dict) and ("takeable" in props or obj.get("items")):
            if obj.get("items"):
                item = obj["items"].pop(0)
                agent["inventory"].append(item)
                return {"success": True, "reason": f"I took the {item} from the {target}."}
            agent["inventory"].append(target)
            loc = self.map.get_location(*agent["pos"])
            if loc:
                loc.objects.pop(target, None)
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
            if instrument not in agent['inventory']:
                 return {"success": False, "reason": f"I don't have a {instrument}."}

            # Example: repair with toolkit
            if target == "computer" and instrument == "toolkit":
                 if state == "error":
                     obj["state"] = "repaired_by_tool"
                     agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.2)
                     return {"success": True, "reason": "I used the toolkit to repair the computer hardware."}
            
            return {"success": False, "reason": f"Using the {instrument} on the {target} had no effect."}
        
        # Original simple use logic
        if target == "kettle":
            # Simplified logic: kettle fills itself if at sink, or abstractly
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
        if "cleanable" in props or target == "room":
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
            # Check for toolkit either in inventory OR as instrument
            toolkit = "toolkit" in agent['inventory']
            if not toolkit:
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
        """Consume ingredients to reduce hunger; requires kitchen context."""
        kitchen_loc = self.map.get_location(*self.room_coords.get("kitchen", (0, 1)))
        if not kitchen_loc:
             return {"success": False, "reason": "Kitchen not found."}
        
        stove = kitchen_loc.objects.get("stove")
        fridge = kitchen_loc.objects.get("fridge")
        
        # Check current location name via map to ensure agent is IN kitchen
        current_loc = self.map.get_location(*agent['pos'])
        if not current_loc or current_loc.name != "kitchen" or not stove or not fridge:
            return {"success": False, "reason": "I need to be in the kitchen to cook."}
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
        if agent_id not in self.agents: return None
        agent = self.agents[agent_id]
        
        if not agent["active_goal"]:
            return None
        if agent["goal_progress_index"] >= len(agent["active_goal"]["steps"]):
            return None
        return agent["active_goal"]["steps"][agent["goal_progress_index"]]

    def _update_goal_progress(self, verb: str, target: Optional[str], success: bool, agent_id: str):
        """Advance goal pointer when the expected verb/target succeeds."""
        step = self._current_goal_step(agent_id)

        if not step or not success:
            return
        
        agent = self.agents[agent_id]
        if step["action"] == verb and step.get("target") == target:
            agent["goal_progress_index"] += 1
            agent["current_goal_steps_done"].append(step)
            agent["goal_history"].append({"goal": agent["active_goal"]["name"], "step": step, "cycle": self.world_time})
            if agent["goal_progress_index"] >= len(agent["active_goal"]["steps"]):
                # complete
                agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.1)
                self.cleanliness = max(0.0, self.cleanliness - 0.02)
                if agent["active_goal"]["name"] == "Assist the neighbor":
                    self.relationships["neighbor"]["trust"] = min(1.0, self.relationships["neighbor"].get("trust", 0.5) + 0.15)
                    self.neighbor_state["awaiting_help"] = False
                    self.neighbor_state["request_cycle"] = None
                agent["active_goal"] = None
                # self._ensure_goal(agent_id) # Disable auto-renew
