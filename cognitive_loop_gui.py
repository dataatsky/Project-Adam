# cognitive_loop_gui.py
# -----------------------
# This new version integrates a simple Tkinter GUI to visualize Adam's state.
# It runs the cognitive loop in a separate thread to keep the GUI responsive.

import requests
import json
import time
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
import threading
import csv
import os
import sys # Needed to redirect stdout
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from text_world import TextWorld
from flask import Flask, jsonify


# --- CONFIGURATION ---
PSYCHE_LLM_API_URL = "http://127.0.0.1:5000/"
PINECONE_API_KEY = "pcsk_7TPuaD_F9vxgwazjRuEdRVvJpn6Hyv6H6HFz6gpVHrP5uYGMAVXq6we1UqBF2RG5vYvZnf" # Replace with your Pinecone API key
PINECONE_ENVIRONMENT = "us-east-1" # e.g., "us-west1-gcp"
PINECONE_INDEX_NAME = "project-adam-memory-text"
LOG_FILE = "adam_behavior_log.csv"

# --- LOG HEADERS ---
LOG_HEADERS = [
    "timestamp", "world_time", "location", "mood", "mood_intensity",
    "sensory_events", "resonant_memories", "impulses", "chosen_action", "action_result"
]


# --- INITIALIZATION ---
print("Initializing Cognitive Loop Server...")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model loaded.")

pc = Pinecone(api_key=PINECONE_API_KEY, environment=PINECONE_ENVIRONMENT)

if PINECONE_INDEX_NAME not in pc.list_indexes().names():
    print(f"Creating new Pinecone index: {PINECONE_INDEX_NAME}")
    pc.create_index(name=PINECONE_INDEX_NAME, dimension=384, metric='cosine')
index = pc.Index(PINECONE_INDEX_NAME)
print("Pinecone connection established.")

FOUNDATIONAL_MEMORIES = [
    "As a child, the sound of a phone ringing often meant bad news, making me feel anxious.",
    "I remember my mother humming a gentle tune while she worked in the kitchen. It always made me feel calm.",
    "A sudden knock on the door once led to an unpleasant surprise. I've been wary of unexpected visitors ever since.",
    "I enjoy the quiet solitude of reading. Books are a safe escape from a noisy world.",
    "Loud, chaotic noises like static on a TV have always been unsettling to me.",
    "I find the gentle sound of rain on a windowpane to be very soothing.",
    "I have a recurring dream about a locked door that I can't open, which fills me with a sense of unease and curiosity."
]

def pre_populate_foundational_memories():
    stats = index.describe_index_stats()
    if stats.get('total_vector_count', 0) == 0:
        print("--- Index is empty. Pre-populating with foundational memories... ---")
        vectors_to_upsert = []
        for i, memory_text in enumerate(FOUNDATIONAL_MEMORIES):
            vector = model.encode(memory_text).tolist()
            metadata = {"text": memory_text, "timestamp": time.time(), "type": "foundational"}
            vectors_to_upsert.append((str(i), vector, metadata))
        
        index.upsert(vectors=vectors_to_upsert)
        print(f"--- {len(vectors_to_upsert)} foundational memories have been added. ---")
    else:
        print("--- Index already contains memories. Skipping pre-population. ---")


class CognitiveLoop:
    def __init__(self, log_filename, log_headers):
        self.agent_status = {
            "emotional_state": {"mood": "neutral", "level": 0.1},
            "personality": {"curiosity": 0.8, "bravery": 0.6, "caution": 0.7},
            "needs": {"hunger": 0.1},
            "goal": "Find the source of the strange noises in the house."
        }
        try:
            self.memory_id_counter = index.describe_index_stats().get('total_vector_count', 0)
        except Exception as e:
            self.memory_id_counter = 0
        
        self.is_running = True
        self.last_resonant_memories = []
        self.recent_memories = []
        self.log_filename = log_filename
        self.log_headers = log_headers
        self.current_world_state = {}
        self.current_mood = "neutral"
        self.mood_intensity = 0.1

    def log_cycle_data(self, cycle_data):
        try:
            with open(self.log_filename, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.log_headers)
                writer.writerow(cycle_data)
        except Exception as e:
            print(f"Error writing to log file: {e}")
    
    def observe(self, world_state):
        print("\n--- 1. OBSERVING ---")
        print(f"Received world state: {json.dumps(world_state, indent=2)}")
        self.current_world_state = world_state
        return world_state

    def orient(self, world_state):
        print("\n--- 2. ORIENTING (Subconscious) ---")
        sensory_events = world_state.get('sensory_events', [])
        
        query_text = " ".join([f"{e['type']} of {e['object']} which is {e['details']}" for e in sensory_events if 'object' in e])
        
        if not query_text:
            print("No object-based sensory events to form a memory query.")
            self.last_resonant_memories = []
        else:
            query_vector = model.encode(query_text).tolist()
            print(f"Querying memory with: '{query_text}'")
            try:
                results = index.query(vector=query_vector, top_k=3, include_metadata=True)
                self.last_resonant_memories = [res['metadata']['text'] for res in results['matches']]
                print(f"Resonant Memories: {self.last_resonant_memories}")
            except Exception: 
                self.last_resonant_memories = []

        payload = {
            "current_state": self.agent_status,
            "world_state": world_state,
            "resonant_memories": self.last_resonant_memories
        }
        try:
            response = requests.post(f"{PSYCHE_LLM_API_URL}/generate_impulse", json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error communicating with Psyche-LLM's /generate_impulse: {e}")
            return None

    def imagine_and_reflect(self, initial_impulses, world):
        print("\n--- 2.5. IMAGINING & REFLECTING ---")
        
        hypothetical_outcomes = []
        top_impulses = sorted(initial_impulses.get('impulses', []), key=lambda x: x.get('urgency', 0), reverse=True)[:3]

        for impulse in top_impulses:
            if not isinstance(impulse, dict): continue
            action = {"verb": impulse.get("verb"), "target": impulse.get("target")}
            
            try:
                response = requests.post(f"{PSYCHE_LLM_API_URL}/imagine", json={"action": action})
                imagined_outcome = response.json().get("outcome", "I imagine nothing happens.")
            except Exception:
                imagined_outcome = "My imagination is fuzzy."
            
            cloned_world = world.clone()
            simulated_result = cloned_world.process_action(action)
            
            # DEFINITIVE FIX: Pass the action as a dictionary for clarity.
            hypothetical_outcomes.append({
                "action": action,
                "imagined": imagined_outcome,
                "simulated": simulated_result.get("reason")
            })

        payload = {
            "current_state": self.agent_status,
            "hypothetical_outcomes": hypothetical_outcomes,
            "recent_memories": self.recent_memories
        }
        try:
            response = requests.post(f"{PSYCHE_LLM_API_URL}/reflect", json=payload)
            response.raise_for_status()
            reflection_result = response.json()
            print(f"Reflection Result: {reflection_result.get('reasoning')}")
            return reflection_result
        except Exception as e:
            print(f"Error during reflection: {e}")
            return {"final_action": {"verb": "wait", "target": "null"}, "reasoning": "My mind is blank."}

    def decide(self, final_action, reasoning):
        print("\n--- 3. DECIDING ---")
        print(f"Final Chosen Action: {final_action}")
        return final_action, reasoning

    def act(self, world, action, reasoning, world_state, impulses):
        print("\n--- 4. ACTING ---")
        action_result = world.process_action(action)
        print(f"Action Result: {action_result}")
        
        if action_result.get('state_change'):
            if 'hunger' in action_result['state_change']:
                self.agent_status['needs']['hunger'] = max(0, self.agent_status['needs']['hunger'] + action_result['state_change']['hunger'])

        sensed_objects = [e['object'] for e in world_state.get('sensory_events', []) if 'object' in e]
        sensed_str = f"I sensed {', '.join(sensed_objects)}." if sensed_objects else "I sensed nothing out of the ordinary."
        decision_str = f"I decided to {action['verb']}." if action.get('target') == 'null' else f"I decided to {action['verb']} the {action['target']}."
        result_reason = action_result.get('reason', 'it just happened.')
        if action_result.get('success'):
            event_description = f"I was in the {world.agent_location}. {sensed_str} My emotional state became {self.current_mood}. {decision_str} The result was: {result_reason}"
        else:
            event_description = f"I was in the {world.agent_location}. {sensed_str} My emotional state became {self.current_mood}. {decision_str} But it failed because {result_reason}"

        self.recent_memories.append(event_description)
        if len(self.recent_memories) > 5: self.recent_memories.pop(0)

        print(f"Forming new memory: '{event_description}'")
        memory_vector = model.encode(event_description).tolist()
        metadata = {"text": event_description, "timestamp": time.time()}
        try:
            index.upsert(vectors=[(str(self.memory_id_counter), memory_vector, metadata)])
            self.memory_id_counter += 1
            print("Memory successfully stored.")
        except Exception as e:
            print(f"Could not store memory in Pinecone: {e}")
        
        cycle_data = {
            "timestamp": time.time(),
            "world_time": world.world_time,
            "location": world.agent_location,
            "mood": self.current_mood,
            "mood_intensity": self.mood_intensity,
            "sensory_events": json.dumps(world_state.get('sensory_events', [])),
            "resonant_memories": json.dumps(self.last_resonant_memories),
            "impulses": json.dumps(impulses.get('impulses', []) if impulses else []),
            "chosen_action": f"{action.get('verb')}_{action.get('target')}",
            "action_result": json.dumps(action_result)
        }
        self.log_cycle_data(cycle_data)

    def run_loop(self):
        text_world = TextWorld()
        while self.is_running:
            text_world.update()
            self.agent_status['needs']['hunger'] = min(1, self.agent_status['needs']['hunger'] + 0.005)

            world_state = text_world.get_world_state()
            full_world_state = self.observe(world_state)
            initial_impulses = self.orient(full_world_state)
            
            if initial_impulses:
                reflection = self.imagine_and_reflect(initial_impulses, text_world)
                final_action = reflection.get('final_action', {'verb': 'wait', 'target': 'null'})
                reasoning = reflection.get('reasoning', 'I am unsure.')
                
                emotional_shift = initial_impulses.get('emotional_shift', {})
                if emotional_shift:
                    self.agent_status['emotional_state']['mood'] = emotional_shift.get('mood', self.current_mood)
                    new_level = self.agent_status['emotional_state']['level'] + emotional_shift.get('level_delta', 0)
                    self.agent_status['emotional_state']['level'] = max(0, min(1, new_level))
                self.current_mood = self.agent_status['emotional_state']['mood']
                self.mood_intensity = self.agent_status['emotional_state']['level']

                action, reasoning = self.decide(final_action, reasoning)
                self.act(text_world, action, reasoning, full_world_state, initial_impulses)
            else:
                print("\nOrient phase failed or returned no impulses. Deciding to wait.")
                action = {"verb": "wait", "target": "null"}
                self.act(text_world, action, "No impulses", full_world_state, {})

            print("\n--- Cycle Complete. Waiting for next perception... ---")
            time.sleep(5)

# --- Flask Server for the Visualizer ---
app = Flask(__name__)
adam_brain = None

@app.route('/get_state', methods=['GET'])
def get_state():
    """Provides Adam's current state to the visualizer."""
    if adam_brain:
        return jsonify({
            "location": adam_brain.current_world_state.get('agent_location', 'unknown'),
            "mood": adam_brain.agent_status['emotional_state']['mood']
        })
    return jsonify({"error": "Cognitive loop not running"}), 500

def run_flask_app():
    app.run(port=8080)

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
            writer.writeheader()
        print(f"Created log file: {LOG_FILE}")
    
    pre_populate_foundational_memories()
    
    adam_brain = CognitiveLoop(LOG_FILE, LOG_HEADERS)
    
    loop_thread = threading.Thread(target=adam_brain.run_loop, daemon=True)
    loop_thread.start()
    
    print("--- Cognitive Loop Server is running. State available at http://127.0.0.1:8080/get_state ---")
    run_flask_app()
