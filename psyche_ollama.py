# psyche_llm_ollama.py
# ---------------------
# Updated with a new /imagine endpoint for the Imagination Engine.

from flask import Flask, request, jsonify
import ollama
import json

app = Flask(__name__)

# --- CONFIGURATION ---
OLLAMA_MODEL = "qwen3:1.7b"

# --- PROMPTS ---
SUBCONSCIOUS_PROMPT = """
You are the subconscious of an AI agent named Adam. Your sole purpose is to generate raw, unfiltered emotional and behavioral impulses based on his current situation. You must respond ONLY with a single, valid JSON object and nothing else. Do not include markdown formatting like ```json.

The JSON object must contain two keys: "emotional_shift" and "impulses".
- "emotional_shift" must be an object with a "mood" (string), a "level_delta" (float between -1.0 and 1.0), and a "reason" (string).
- "impulses" must be a list of objects, where each object has a "verb" (string), a "target" (string), a "drive" (string), and an "urgency" (float between 0.0 and 1.0).

Combine a verb from the VERB TOOLBOX with a noun from the PERCEIVABLE OBJECTS list to form an action. Be creative.

VERB TOOLBOX:
- "wait", "go", "examine", "open", "close", "read", "eat", "answer", "ignore", "turn_on", "turn_off", "investigate", "sleep"
"""

IMAGINATION_PROMPT = """
You are the imagination of an AI agent named Adam. Your task is to predict the most likely outcome of a hypothetical action. Respond with a single, valid JSON object containing one key: "outcome". The value should be a brief, first-person narrative sentence describing what you imagine will happen.
"""

CONSCIOUS_MIND_PROMPT = """
You are the conscious, rational mind of an AI agent named Adam. Your purpose is to reflect on a series of hypothetical plans and make a final, logical decision. You must respond ONLY with a single, valid JSON object and nothing else. Do not include markdown formatting like ```json.

The JSON object must contain two keys: "final_action" (an object with "verb" and "target" keys) and "reasoning" (string).
- "final_action" must be ONE of the actions from the hypothetical plans.
- "reasoning" must be a brief, first-person explanation for your choice, considering your long-term goal and current emotional state.

Analyze the situation provided. For each potential action, you have an "imagined" outcome (what you thought would happen) and a "simulated" outcome (what the world's physics say would actually happen).

**Crucially, if you see that a hypothetical action has repeatedly failed in your recent memories, you must acknowledge this pattern. Your reasoning should reflect this frustration, and you should choose a *different* action to try and break the loop.** Choose the action with the best outcome that aligns with your goals.
"""

def generate_user_prompt(data):
    """Builds the user prompt string for the subconscious."""
    world_state = data.get('world_state', {})
    current_state = data.get('current_state', {})
    resonant_memories = data.get('resonant_memories', [])
    
    prompt = "## Current Situation:\n"
    prompt += f"- Adam's current goal is: {current_state.get('goal', 'None')}\n"
    prompt += f"- Adam's current hunger level is {current_state.get('needs', {}).get('hunger', 0):.2f} (0=satiated, 1=starving).\n"
    prompt += f"- Adam is in the: {world_state.get('agent_location')}\n"
    prompt += f"- PERCEIVABLE OBJECTS (Nouns): {world_state.get('perceivable_objects')}\n"
    prompt += f"- AVAILABLE EXITS (for 'go' verb): {world_state.get('available_exits')}\n"
    prompt += f"- Current sensory events are: {world_state.get('sensory_events')}\n"
    
    if resonant_memories:
        prompt += "\n## Resonant Memories (These past events feel relevant):\n"
        for i, mem in enumerate(resonant_memories):
            prompt += f"- {mem}\n"
    
    prompt += "\nBased on this situation and memories, generate the JSON response for Adam's subconscious."
    return prompt

def generate_reflection_prompt(data):
    """Builds the user prompt string for the conscious mind."""
    current_state = data.get('current_state', {})
    hypothetical_outcomes = data.get('hypothetical_outcomes', [])
    recent_memories = data.get('recent_memories', [])
    
    prompt = "## Reflection Task:\n"
    prompt += f"- My current emotional state is: {current_state.get('emotional_state', {}).get('mood')}\n"
    prompt += f"- My long-term goal is: {current_state.get('goal')}\n"
    
    if recent_memories:
        prompt += "\n## My Recent Memories (Last 5 actions):\n"
        for i, mem in enumerate(recent_memories):
            prompt += f"- {mem}\n"

    prompt += "\n## Hypothetical Plans:\n"
    for outcome in hypothetical_outcomes:
        prompt += f"- Action: {outcome['action']}\n"
        prompt += f"  - I imagined: '{outcome['imagined']}'\n"
        prompt += f"  - The simulation said: '{outcome['simulated']}'\n"

    prompt += "\nNow, reflect on this and provide the JSON for my final decision."
    return prompt

@app.route('/generate_impulse', methods=['POST'])
def generate_impulse():
    try:
        data = request.json
        user_prompt = generate_user_prompt(data)
        
        print("--- Sending prompt to Ollama (Subconscious) ---")
        
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SUBCONSCIOUS_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            options={"temperature": 0.8},
            format="json"
        )
        
        llm_json_output = json.loads(response['message']['content'])
        
        print("--- Received JSON from Ollama (Subconscious) ---")
        return jsonify(llm_json_output)

    except Exception as e:
        print(f"An error occurred in /generate_impulse: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/imagine', methods=['POST'])
def imagine():
    try:
        data = request.json
        action = data.get('action', {})
        user_prompt = f"Hypothetical action: I will {action.get('verb')} the {action.get('target')}. What is the most likely outcome?"
        
        print("--- Sending prompt to Ollama (Imagination) ---")
        
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": IMAGINATION_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            options={"temperature": 0.7},
            format="json"
        )
        
        llm_json_output = json.loads(response['message']['content'])
        
        print("--- Received JSON from Ollama (Imagination) ---")
        return jsonify(llm_json_output)

    except Exception as e:
        print(f"An error occurred in /imagine: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/reflect', methods=['POST'])
def reflect():
    try:
        data = request.json
        user_prompt = generate_reflection_prompt(data)
        
        print("--- Sending prompt to Ollama (Conscious Mind) ---")
        
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": CONSCIOUS_MIND_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            options={"temperature": 0.5},
            format="json"
        )
        
        llm_json_output = json.loads(response['message']['content'])
        
        print("--- Received JSON from Ollama (Conscious Mind) ---")
        return jsonify(llm_json_output)

    except Exception as e:
        print(f"An error occurred in /reflect: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("--- Psyche-LLM (Ollama Edition with Imagination Engine) is running ---")
    print(f"--- Using model: {OLLAMA_MODEL} ---")
    app.run(port=5000)
