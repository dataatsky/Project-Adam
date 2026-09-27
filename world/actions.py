"""What each verb does to the world.

TextWorld inherits these handlers. Each `_act_<verb>` receives the target
name, the target object (or None), its properties and state, and the acting
agent's mutable state dict, and returns {"success": bool, "reason": str, ...}.
"""
from typing import Dict, Optional

from world.content import HEARD_LOG_LIMIT


class ActionHandlers:
    """Mixin with one handler per verb in world.vocab.VERBS (except wait/inventory/go routing)."""

    def _act_say(self, target: Optional[str], agent_id: str) -> Dict:
        """Broadcast a message to everyone in the speaker's room."""
        speaker = self.agents[agent_id]
        message = target or "..."
        self.message_seq += 1
        self.speech_log.append({"seq": self.message_seq, "sender": agent_id, "content": message, "time": self.world_time})
        del self.speech_log[:-20]
        listeners = [o for o_id, o in self.agents.items() if o_id != agent_id and o["pos"] == speaker["pos"]]
        if listeners:
            self._relieve(speaker, "loneliness", 0.3)
        for other_id, other_data in self.agents.items():
            if other_id != agent_id and other_data["pos"] == speaker["pos"]:
                self._relieve(other_data, "loneliness", 0.1)
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
            prev_h, prev_m, prev_f = agent["hunger"], agent["mood_intensity"], agent["fatigue"]
            agent["hunger"] = min(1.0, agent["hunger"] + 0.1)
            agent["mood_intensity"] = max(0.0, agent["mood_intensity"] - 0.3)
            self._relieve(agent, "fatigue", 0.7)
            return {
                "success": True,
                "reason": "I slept and feel rested.",
                "state_change": {"hunger": agent["hunger"] - prev_h, "mood_intensity": agent["mood_intensity"] - prev_m,
                                 "fatigue": agent["fatigue"] - prev_f},
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
        if target == "blanket":
            agent["wrapped"] = False
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

        if target == "blanket" and "blanket" in agent['inventory']:
            agent["wrapped"] = True
            agent["cold"] = self._coldness(agent)
            return {"success": True, "reason": "I wrap myself in the blanket. Much warmer."}

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
            self._relieve(agent, "loneliness", 0.4)
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
            self._relieve(agent, "fatigue", 0.05)
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
            self._relieve(agent, "loneliness", 0.1)  # voices on the radio are a little company
            return {"success": True, "reason": "I sway to the radio music."}
        return {"success": False, "reason": f"I can't play with the {target}."}
