import random
import time
import copy

class TextWorld:
    def __init__(self):
        """Initializes the state of the text-based world."""
        self.agent_location = "living_room"
        self.hunger = 0.2  # 0.0 (not hungry) to 1.0 (very hungry)
        self.world_time = 0
        self.mood_intensity = 0.4  # 0.0 (calm) to 1.0 (agitated)
        self.world_state = {
            "living_room": {
                "phone": {"state": "idle", "properties": ["answerable"]},
                "window": {"state": "day", "properties": ["lookable"]},
                "door": {"state": "closed", "properties": ["openable", "answerable"]},
                "tv": {"state": "off", "properties": ["toggleable"]},
                "radio": {"state": "off", "properties": ["toggleable"]},
                "exits": ["kitchen", "bedroom", "office"]
            },
            "kitchen": {
                "fridge": {"state": "closed", "contains": "food", "properties": ["openable", "eatable"]},
                "exits": ["living_room"]
            },
            "bedroom": {
                "bed": {"state": "made", "properties": ["sleepable"]},
                "book": {"state": "on_nightstand", "properties": ["readable"]},
                "exits": ["living_room"]
            },
            "office": {
                "computer": {"state": "off", "properties": ["toggleable", "investigatable"]},
                "plant": {"state": "healthy", "properties": ["waterable"]},
                "exits": ["living_room"]
            }
        }

    def clone(self):
        """Creates a deep copy of the world for simulations."""
        return copy.deepcopy(self)

    def update(self):
        """Simulates the passage of time and triggers random events."""
        self.world_time += 1
        
        if self.world_time % 10 == 0:
            current_state = self.world_state["living_room"]["window"]["state"]
            new_state = "night" if current_state == "day" else "day"
            self.world_state["living_room"]["window"]["state"] = new_state
            print(f"\n[WORLD EVENT] It is now {new_state}.")

        if random.random() < 0.1:
            event_type = random.choice(["phone", "door", "tv", "radio", "computer"])
            if event_type == "phone" and self.world_state["living_room"]["phone"]["state"] == "idle": self.world_state["living_room"]["phone"]["state"] = "ringing"
            elif event_type == "door" and self.world_state["living_room"]["door"]["state"] == "closed": self.world_state["living_room"]["door"]["state"] = "knocking"
            elif event_type == "tv" and self.world_state["living_room"]["tv"]["state"] == "off": self.world_state["living_room"]["tv"]["state"] = "on_static"
            elif event_type == "radio" and self.world_state["living_room"]["radio"]["state"] == "off": self.world_state["living_room"]["radio"]["state"] = "playing_music"
            elif event_type == "computer" and self.world_state["office"]["computer"]["state"] == "off": self.world_state["office"]["computer"]["state"] = "showing_error"

    def get_world_state(self):
        """Generates the sensory data for the agent based on its location."""
        sensory_events = []
        current_room_objects = self.world_state.get(self.agent_location, {})
        
        time_of_day = self.world_state["living_room"]["window"]["state"]
        sensory_events.append({"type": "ambience", "details": f"It is currently {time_of_day}."})

        for obj, properties in current_room_objects.items():
            if obj == "exits": continue
            state = properties["state"]
            if state not in ["idle", "closed", "off", "made", "on_nightstand", "day", "night", "healthy"]:
                 sensory_events.append({"type": "sight/sound", "object": obj, "details": state})
        
        perceivable_objects = [obj for obj in current_room_objects.keys() if obj != "exits"]

        return {
            "agent_location": self.agent_location,
            "sensory_events": sensory_events,
            "perceivable_objects": perceivable_objects,
            "available_exits": current_room_objects.get("exits", [])
        }

    def process_action(self, action):
        """A more robust physics engine for handling verb/target combinations."""
        verb = action.get("verb")
        target = action.get("target")

        if verb == "wait": return {"success": True, "reason": "Time passes."}
        if verb == "go":
            if target in self.world_state[self.agent_location].get("exits", []):
                self.agent_location = target
                return {"success": True, "reason": f"I walked into the {target}."}
            else:
                return {"success": False, "reason": f"I couldn't go to the {target} from here."}
        
        current_room_objects = self.world_state[self.agent_location]
        if target not in current_room_objects:
            return {"success": False, "reason": f"I couldn't see a {target} here."}

        # Verb-based logic
        if verb == "examine":
            return {"success": True, "reason": f"I looked closely at the {target}. Nothing seemed out of the ordinary."}
        if verb == "read":
            if "readable" in current_room_objects[target].get("properties", []):
                return {"success": True, "reason": "I sat down and read the book for a while."}
            else:
                return {"success": False, "reason": f"I can't read a {target}."}
        if verb == "eat":
             if "eatable" in current_room_objects[target].get("properties", []):
                if current_room_objects[target].get("contains") == "food":
                    current_room_objects[target]["contains"] = "empty"
                    return {"success": True, "reason": "I ate the food from the fridge and am no longer hungry.", "state_change": {"hunger": -0.8}}
                else:
                    return {"success": False, "reason": "it was empty."}
             else:
                return {"success": False, "reason": f"I can't eat a {target}."}
        
        # Default for unknown combinations
        return {"success": False, "reason": f"I tried to {verb} the {target}, but it didn't do anything."}
