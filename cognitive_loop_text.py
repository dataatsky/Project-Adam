# cognitive_loop_text.py
# -----------------------
# The central nervous system for the text-based version of "Adam".
# It interacts directly with the TextWorld instance.

import requests
import json
import time
from pinecone import Pinecone # Updated import
from sentence_transformers import SentenceTransformer
from text_world import TextWorld # Import the new text-based world

# --- CONFIGURATION ---
# Note: UNREAL_ENGINE_API_URL is removed.
PSYCHE_LLM_API_URL = "http://127.0.0.1:5000/generate_impulse"
PINECONE_API_KEY = "pcsk_7TPuaD_F9vxgwazjRuEdRVvJpn6Hyv6H6HFz6gpVHrP5uYGMAVXq6we1UqBF2RG5vYvZnf" # Replace with your Pinecone API key
PINECONE_ENVIRONMENT = "us-east-1" # e.g., "us-west1-gcp"
PINECONE_INDEX_NAME = "project-adam-memory-text"

# --- INITIALIZATION ---
print("Initializing Cognitive Loop (Text-Based)...")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model loaded.")

# Initialize Pinecone with the new class-based method
print("Connecting to Pinecone...")
pc = Pinecone(api_key=PINECONE_API_KEY, environment=PINECONE_ENVIRONMENT)

# Check if the index exists and create it if it doesn't
if PINECONE_INDEX_NAME not in pc.list_indexes().names():
    print(f"Creating new Pinecone index: {PINECONE_INDEX_NAME}")
    pc.create_index(
        name=PINECONE_INDEX_NAME, 
        dimension=384, 
        metric='cosine'
    )
index = pc.Index(PINECONE_INDEX_NAME)
print("Pinecone connection established.")

class CognitiveLoop:
    def __init__(self):
        self.agent_status = {
            "emotional_state": {"mood": "neutral", "level": 0.1},
            "personality": {"curiosity": 0.8, "bravery": 0.6, "caution": 0.7}
        }
        # Safely get the initial vector count
        try:
            self.memory_id_counter = index.describe_index_stats().get('total_vector_count', 0)
        except Exception as e:
            print(f"Warning: Could not get initial vector count from Pinecone. Starting at 0. Error: {e}")
            self.memory_id_counter = 0


    def observe(self, world_state):
        """Processes the raw sensory data from the TextWorld."""
        print("\n--- 1. OBSERVING ---")
        print(f"Received world state: {json.dumps(world_state, indent=2)}")
        return world_state.get('sensory_events', [])

    def orient(self, sensory_events):
        """Makes sense of the world by retrieving memories and generating impulses."""
        print("\n--- 2. ORIENTING ---")
        if not sensory_events:
            print("No sensory events to process.")
            return None

        query_text = " ".join([f"{event['type']} of {event['object']} which is {event['details']}" for event in sensory_events])
        query_vector = model.encode(query_text).tolist()
        
        print(f"Querying memory with: '{query_text}'")
        try:
            results = index.query(vector=query_vector, top_k=3, include_metadata=True)
            resonant_memories = [res['metadata']['text'] for res in results['matches']]
            print(f"Resonant Memories: {resonant_memories}")
        except Exception as e:
            print(f"Could not query Pinecone: {e}")
            resonant_memories = []

        payload = {
            "current_state": self.agent_status,
            "sensory_events": sensory_events,
            "resonant_memories": resonant_memories
        }
        
        print("Querying Psyche-LLM for impulses...")
        try:
            response = requests.post(PSYCHE_LLM_API_URL, json=payload)
            response.raise_for_status()
            impulses = response.json()
            print(f"Received Impulses: {json.dumps(impulses, indent=2)}")
            return impulses
        except requests.exceptions.RequestException as e:
            print(f"Error communicating with Psyche-LLM: {e}")
            return None

    def decide(self, impulses):
        """Chooses an action based on impulses and personality."""
        print("\n--- 3. DECIDING ---")
        if not impulses or not impulses.get('impulses'):
            print("No impulses to process. Deciding to 'wait'.")
            return {"verb": "wait", "target": "null"}, "No impulses received."

        emotional_shift = impulses.get('emotional_shift', {})
        if emotional_shift:
            self.agent_status['emotional_state']['mood'] = emotional_shift.get('mood', self.agent_status['emotional_state']['mood'])
            new_level = self.agent_status['emotional_state']['level'] + emotional_shift.get('level_delta', 0)
            self.agent_status['emotional_state']['level'] = max(0, min(1, new_level))
        
        best_action_str = "wait"
        max_utility = -1
        
        for impulse in impulses['impulses']:
            utility = impulse['urgency']
            if "Uncertainty" in impulse['drive']: utility *= self.agent_status['personality']['curiosity']
            if "Safety" in impulse['drive']: utility *= self.agent_status['personality']['caution']
            
            if utility > max_utility:
                max_utility = utility
                best_action_str = impulse['action']
        
        print(f"Chosen Action: {best_action_str} with utility {max_utility:.2f}")
        
        action_parts = best_action_str.split('_')
        formatted_action = {"verb": action_parts[0], "target": action_parts[1] if len(action_parts) > 1 else "null"}
        reasoning = f"Chose '{best_action_str}' with utility {max_utility:.2f}."
        
        return formatted_action, reasoning

    def act(self, world, action, reasoning, world_state):
        """Sends the chosen action to the TextWorld and forms a new memory."""
        print("\n--- 4. ACTING ---")
        
        # a) Send action to the TextWorld instance
        action_result = world.process_action(action)
        print(f"Action Result: {action_result}")

        # b) Form a new memory
        event_description = f"I was in the {world.agent_location}. I sensed {', '.join([e['object'] for e in world_state.get('sensory_events', [])])}. My emotional state became {self.agent_status['emotional_state']['mood']}. I decided to {action['verb']} the {action['target']}. The result was: {action_result}"
        
        print(f"Forming new memory: '{event_description}'")
        memory_vector = model.encode(event_description).tolist()
        metadata = {"text": event_description, "timestamp": time.time()}
        
        try:
            index.upsert(vectors=[(str(self.memory_id_counter), memory_vector, metadata)])
            self.memory_id_counter += 1
            print("Memory successfully stored.")
        except Exception as e:
            print(f"Could not store memory in Pinecone: {e}")

if __name__ == "__main__":
    adam_brain = CognitiveLoop()
    text_world = TextWorld()
    print("\n--- Adam's Cognitive Loop is now running in a Text-Based World. ---")
    
    try:
        while True:
            # 1. Update the world state (e.g., random events)
            text_world.update()

            # 2. Get the current state from the world for the agent
            world_state = text_world.get_world_state()
            
            # 3. Run one cycle of the OODA loop
            sensory_events = adam_brain.observe(world_state)
            impulses = adam_brain.orient(sensory_events)
            action, reasoning = adam_brain.decide(impulses)
            adam_brain.act(text_world, action, reasoning, world_state)
            
            # Wait before the next cycle
            print("\n--- Cycle Complete. Waiting for next perception... ---")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n--- Cognitive Loop shutting down. ---")