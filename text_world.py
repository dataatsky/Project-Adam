import random
import copy

class TextWorld:
    def __init__(self):
        """Initializes the state of the text-based world."""
        self.agent_location = "living_room"
        self.hunger = 0.2  # 0.0 (not hungry) to 1.0 (very hungry)
        self.mood_intensity = 0.4  # 0.0 (calm) to 1.0 (agitated)
        self.world_time = 0  # ticks (1 = 1 hour for simplicity)

        self.world_state = {
            "living_room": {
                "phone": {"state": "idle", "properties": ["answerable"]},
                "window": {"state": "day", "properties": ["lookable"]},
                "door": {"state": "closed", "properties": ["openable", "answerable"]},
                "tv": {"state": "off", "properties": ["toggleable"]},
                "radio": {"state": "off", "properties": ["toggleable"]},
                "exits": ["kitchen", "bedroom", "office"],
            },
            "kitchen": {
                "fridge": {
                    "state": "closed",
                    "contains": "food",
                    "properties": ["openable", "eatable"],
                },
                "exits": ["living_room"],
            },
            "bedroom": {
                "bed": {"state": "made", "properties": ["sleepable"]},
                "book": {"state": "on_nightstand", "properties": ["readable"]},
                "exits": ["living_room"],
            },
            "office": {
                "computer": {
                    "state": "off",
                    "properties": ["toggleable", "investigatable"],
                },
                "plant": {"state": "healthy", "properties": ["waterable"]},
                "exits": ["living_room"],
            },
        }

    def clone(self):
        """Creates a deep copy of the world for simulations."""
        return copy.deepcopy(self)

    def time_of_day(self):
        """Return a human-readable time of day based on world_time."""
        cycle = self.world_time % 24
        if 6 <= cycle < 12:
            return "morning"
        elif 12 <= cycle < 18:
            return "afternoon"
        elif 18 <= cycle < 22:
            return "evening"
        else:
            return "night"

    def update(self):
        """Advance time and trigger random events."""
        self.world_time += 1
        events = []

        # Day/night cycle
        if self.world_time % 10 == 0:
            current_state = self.world_state["living_room"]["window"]["state"]
            new_state = "night" if current_state == "day" else "day"
            self.world_state["living_room"]["window"]["state"] = new_state
            events.append(f"It is now {new_state}.")

        # Random events (10% chance)
        if random.random() < 0.1:
            event_type = random.choice(["phone", "door", "tv", "radio", "computer"])
            if (
                event_type == "phone"
                and self.world_state["living_room"]["phone"]["state"] == "idle"
            ):
                self.world_state["living_room"]["phone"]["state"] = "ringing"
                events.append("The phone starts ringing.")
                self.mood_intensity = min(1.0, self.mood_intensity + 0.1)
            elif (
                event_type == "door"
                and self.world_state["living_room"]["door"]["state"] == "closed"
            ):
                self.world_state["living_room"]["door"]["state"] = "knocking"
                events.append("Someone knocks at the door.")
                self.mood_intensity = min(1.0, self.mood_intensity + 0.1)
            elif (
                event_type == "tv"
                and self.world_state["living_room"]["tv"]["state"] == "off"
            ):
                self.world_state["living_room"]["tv"]["state"] = "on_static"
                events.append("The TV turns on to static.")
                self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            elif (
                event_type == "radio"
                and self.world_state["living_room"]["radio"]["state"] == "off"
            ):
                self.world_state["living_room"]["radio"]["state"] = "playing_music"
                events.append("The radio starts playing music.")
            elif (
                event_type == "computer"
                and self.world_state["office"]["computer"]["state"] == "off"
            ):
                self.world_state["office"]["computer"]["state"] = "showing_error"
                events.append("The computer shows an error screen.")
                self.mood_intensity = min(1.0, self.mood_intensity + 0.05)

        return events

    def get_world_state(self):
        """Generate sensory data for the agent based on its location."""
        sensory_events = []
        current_room_objects = self.world_state.get(self.agent_location, {})

        # ambience
        sensory_events.append(
            {"type": "ambience", "details": f"It is {self.time_of_day()}."}
        )

        # Notable states
        notable_states = {
            "phone": ["ringing"],
            "door": ["knocking", "open"],
            "tv": ["on", "on_static"],
            "radio": ["playing_music"],
            "computer": ["on", "showing_error"],
            "fridge": ["open"],
        }

        for obj, properties in current_room_objects.items():
            if obj == "exits":
                continue
            state = properties["state"]
            if obj in notable_states and state in notable_states[obj]:
                sensory_events.append(
                    {"type": "sight/sound", "object": obj, "details": state}
                )

        perceivable_objects = [
            obj for obj in current_room_objects.keys() if obj != "exits"
        ]

        return {
            "agent_location": self.agent_location,
            "time": self.world_time,
            "time_of_day": self.time_of_day(),
            "hunger": self.hunger,
            "mood_intensity": self.mood_intensity,
            "sensory_events": sensory_events,
            "perceivable_objects": perceivable_objects,
            "available_exits": current_room_objects.get("exits", []),
        }

    def process_action(self, action):
        """Physics engine for handling verb/target combinations."""
        verb = action.get("verb")
        target = action.get("target")

        # --- Defaults ---
        if verb == "wait":
            return {"success": True, "reason": "Time passes."}

        if verb == "go":
            if target in self.world_state[self.agent_location].get("exits", []):
                self.agent_location = target
                return {"success": True, "reason": f"I walked into the {target}."}
            else:
                self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
                return {"success": False, "reason": f"I can't go to the {target}."}

        current_room_objects = self.world_state[self.agent_location]
        if target not in current_room_objects:
            self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            return {"success": False, "reason": f"I don't see a {target} here."}

        obj = current_room_objects[target]
        props = obj.get("properties", [])
        state = obj.get("state")

        # --- Action logic ---
        if verb in ("examine", "investigate"):
            return {"success": True, "reason": f"I looked at the {target}. State: {state}"}

        if verb == "read":
            if "readable" in props:
                self.mood_intensity = max(0.0, self.mood_intensity - 0.1)
                return {"success": True, "reason": "Reading calms me.", "state_change": {"mood_intensity": -0.1}}
            else:
                self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
                return {"success": False, "reason": f"I can't read {target}."}

        if verb == "open":
            if "openable" in props and state != "open":
                obj["state"] = "open"
                return {"success": True, "reason": f"I opened the {target}."}
            self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            return {"success": False, "reason": f"I can't open {target}."}

        if verb == "close":
            if "openable" in props and state != "closed":
                obj["state"] = "closed"
                return {"success": True, "reason": f"I closed the {target}."}
            self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            return {"success": False, "reason": f"I can't close {target}."}

        if verb == "answer":
            if "answerable" in props and state in ("ringing", "knocking", "idle"):
                obj["state"] = "idle"
                self.mood_intensity = max(0.0, self.mood_intensity - 0.05)
                return {"success": True, "reason": f"I answered the {target}.", "state_change": {"mood_intensity": -0.05}}
            self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            return {"success": False, "reason": f"I can't answer {target}."}

        if verb in ("toggle", "turn_on", "turn_off"):
            if "toggleable" in props:
                cur = obj.get("state", "off")
                cur_norm = "off" if cur == "off" else "on"
                if verb == "turn_on":
                    new = "on"
                elif verb == "turn_off":
                    new = "off"
                else:
                    new = "off" if cur_norm == "on" else "on"
                obj["state"] = new
                return {"success": True, "reason": f"I set the {target} to {new}."}
            self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            return {"success": False, "reason": f"I can't toggle {target}."}

        if verb == "eat":
            if "eatable" in props:
                if obj.get("contains") == "food":
                    obj["contains"] = "empty"
                    prev = self.hunger
                    self.hunger = max(0.0, prev - 0.6)
                    return {"success": True, "reason": "I ate the food.", "state_change": {"hunger": self.hunger - prev}}
                self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
                return {"success": False, "reason": "The fridge is empty."}
            self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            return {"success": False, "reason": f"I can't eat {target}."}

        if verb == "sleep":
            if "sleepable" in props:
                prev_h, prev_m = self.hunger, self.mood_intensity
                self.hunger = min(1.0, self.hunger + 0.1)
                self.mood_intensity = max(0.0, self.mood_intensity - 0.3)
                return {"success": True, "reason": "I slept and feel rested.", "state_change": {"hunger": self.hunger - prev_h, "mood_intensity": self.mood_intensity - prev_m}}
            self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            return {"success": False, "reason": f"I can't sleep on {target}."}

        if verb == "water":
            if "waterable" in props:
                prev = obj.get("state")
                obj["state"] = "healthy"
                return {"success": True, "reason": "I watered the plant.", "state_change": {f"{target}_state": (prev, "healthy")}}
            self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
            return {"success": False, "reason": f"I can't water {target}."}

        # fallback
        self.mood_intensity = min(1.0, self.mood_intensity + 0.05)
        return {"success": False, "reason": f"I tried to {verb} the {target}, but nothing happened."}