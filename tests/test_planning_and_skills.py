
import sys
import os
import unittest
from collections import deque

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from text_world import TextWorld
from loop.insight_engine import InsightEngine

class TestPlanningAndSkills(unittest.TestCase):
    def test_hierarchical_planning(self):
        world = TextWorld()
        world.add_agent("adam1")
        
        # 1. Set goal with steps
        steps = ["find toolkit", "go kitchen", "repair stove"]
        world.set_goal("Refurbish Kitchen", steps=steps, agent_id="adam1")
        
        # 2. Verify goal structure
        agent = world.agents["adam1"]
        self.assertEqual(agent["active_goal"]["name"], "Refurbish Kitchen")
        self.assertEqual(len(agent["active_goal"]["steps"]), 3)
        self.assertEqual(agent["active_goal"]["steps"][0]["action"], "find")
        self.assertEqual(agent["active_goal"]["steps"][0]["target"], "toolkit")
        
        # 3. Progress tracking
        # current step should be 0
        current = world._current_goal_step("adam1")
        self.assertEqual(current["action"], "find")
        
        # complete step 0
        world._update_goal_progress("find", "toolkit", True, "adam1")
        
        # current step should be 1
        current = world._current_goal_step("adam1")
        self.assertEqual(current["action"], "go")
        self.assertEqual(current["target"], "kitchen")

    def test_skill_acquisition(self):
        insight = InsightEngine()
        
        # 1. Fail initially
        self.assertEqual(insight.get_mastered_skills(min_success=3), [])
        
        # 2. Succeed multiple times
        action = {"verb": "run", "target": "marathon"}
        for _ in range(5):
            insight.add_cycle(
                action=action, 
                success=True, 
                impulses=[], 
                triggers=[], 
                mood="determined"
            )
            
        # 3. Verify mastery
        skills = insight.get_mastered_skills(min_success=3)
        self.assertIn("run marathon", skills)
        
        # 4. Verify distinct skills
        insight.add_cycle(action={"verb": "jump", "target": "rope"}, success=True, impulses=[], triggers=[], mood="fun")
        skills = insight.get_mastered_skills(min_success=3)
        self.assertNotIn("jump rope", skills)

if __name__ == "__main__":
    unittest.main()
