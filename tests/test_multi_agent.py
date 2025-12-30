
import sys
import os
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from text_world import TextWorld

class TestMultiAgent(unittest.TestCase):
    def test_social_presence(self):
        world = TextWorld()
        world.add_agent("adam1")
        world.add_agent("eve")
        
        # Move eve to adam's location (living_room 0,0) implies default start
        # Both start at 0,0 by default in add_agent
        
        ws_adam = world.get_world_state("adam1")
        
        # Check if adam sees eve
        saw_eve = False
        for event in ws_adam["sensory_events"]:
            if event["type"] == "visual" and event["object"] == "eve":
                saw_eve = True
                break
        
        self.assertTrue(saw_eve, "Adam should see Eve in the same room.")

    def test_communication(self):
        world = TextWorld()
        world.add_agent("adam1")
        world.add_agent("eve")
        
        # Check initial state
        ws_adam = world.get_world_state("adam1")
        heard_msg = any(e["type"] == "auditory" for e in ws_adam["sensory_events"])
        self.assertFalse(heard_msg, "Adam should hear nothing initially.")
        
        # Eve speaks
        res = world.process_action({"verb": "say", "target": "Hello Adam"}, agent_id="eve")
        self.assertTrue(res["success"])
        
        # Adam should receive it in NEXT state retrieval
        ws_adam = world.get_world_state("adam1")
        
        heard_hello = False
        for event in ws_adam["sensory_events"]:
            if event["type"] == "auditory" and event["object"] == "eve" and "Hello Adam" in event.get("details", ""):
                heard_hello = True
                break
        
        self.assertTrue(heard_hello, "Adam should hear Eve's message.")
        
        # Check inbox cleared
        ws_adam_2 = world.get_world_state("adam1")
        heard_again = any("Hello Adam" in e.get("details", "") for e in ws_adam_2["sensory_events"])
        self.assertFalse(heard_again, "Message should be consumed after reading.")

if __name__ == "__main__":
    unittest.main()
