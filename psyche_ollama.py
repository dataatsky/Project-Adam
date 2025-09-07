# psyche_llm_ollama.py
# ---------------------
# Updated with a new /imagine endpoint for the Imagination Engine.

from flask import Flask, request, jsonify
import ollama
import json
import logging
import os
from dotenv import load_dotenv
from collections import Counter


app = Flask(__name__)

# --- CONFIGURATION ---
load_dotenv(".env")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")  # Change as needed

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- PROMPTS ---
SUBCONSCIOUS_PROMPT = """
You are the subconscious of an AI agent named Adam. Respond ONLY with JSON.

The JSON must have two keys:
- "emotional_shift": {"mood": str, "level_delta": float, "reason": str}
- "impulses": [ {"verb": str, "target": str, "drive": str, "urgency": float} ]

VERB TOOLBOX:
- "wait", "go", "examine", "open", "close", "read", "eat", "answer", "ignore", "turn_on", "turn_off", "investigate", "sleep"
"""

IMAGINATION_PROMPT = """
You are the imagination of Adam. Predict the most likely outcome of a hypothetical action.
Respond with JSON: {"outcome": "..."}.
"""

CONSCIOUS_MIND_PROMPT = """
You are the conscious mind of Adam. Reflect logically and choose ONE final action.

Respond ONLY with JSON:
- "final_action": {"verb": str, "target": str}
- "reasoning": str

If a plan has repeatedly failed in recent memories, avoid repeating it.
"""


def safe_json_loads(raw):
    """Tolerant JSON loader: extract first {...} if raw contains noise.
    Fixed to avoid recursion and to return a dict on failure."""
    if raw is None:
        return {}
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        # Try extracting object
        try:
            start = raw.index("{"); end = raw.rindex("}") + 1
            return json.loads(raw[start:end])
        except Exception:
            # Try extracting array
            try:
                start = raw.index("["); end = raw.rindex("]") + 1
                return json.loads(raw[start:end])
            except Exception:
                return {}
        
# --- HELPERS ---
        
def normalize_impulses(data: dict):
    """Normalize verbs to match TextWorld's physics."""
    impulses = data.get("impulses", [])
    for imp in impulses:
        v = imp.get("verb")
        if v == "investigate":
            imp["verb"] = "examine"
        elif v == "ignore":
            imp["verb"] = "wait"
        elif v in ("turn_on", "turn_off"):
            imp["verb"] = "toggle"
    data["impulses"] = impulses
    return data

def generate_user_prompt(data):
    """Builds the user prompt string for the subconscious."""
    world_state = data.get('world_state', {}) or {}
    current_state = data.get('current_state', {}) or {}
    resonant_memories = data.get('resonant_memories', []) or []

    prompt = "## Current Situation:\n"
    prompt += f"- Adam's current goal is: {str(current_state.get('goal', 'None'))}\n"
    prompt += f"- Adam's current hunger level is {float(current_state.get('needs', {}).get('hunger', 0)):.2f} (0=satiated, 1=starving).\n"
    prompt += f"- Adam is in the: {str(world_state.get('agent_location', 'unknown'))}\n"
    prompt += f"- PERCEIVABLE OBJECTS (Nouns): {str(world_state.get('perceivable_objects', []))}\n"
    prompt += f"- AVAILABLE EXITS (for 'go' verb): {str(world_state.get('available_exits', []))}\n"
    prompt += f"- Current sensory events are: {str(world_state.get('sensory_events', []))}\n"

    if resonant_memories:
        prompt += "\n## Resonant Memories (These past events feel relevant):\n"
        for mem in resonant_memories:
            prompt += f"- {str(mem)}\n"

    prompt += "\nBased on this situation and memories, generate the JSON response for Adam's subconscious."
    return prompt

def generate_reflection_prompt(data):
    """Builds the user prompt string for the conscious mind."""
    current_state = data.get('current_state', {}) or {}
    hypothetical_outcomes = data.get('hypothetical_outcomes', []) or []
    recent_memories = data.get('recent_memories', []) or []

    prompt = "## Reflection Task:\n"
    prompt += f"- Emotional state: {str(current_state.get('emotional_state', {}).get('mood', 'neutral'))}\n"
    prompt += f"- Goal: {str(current_state.get('goal', 'none'))}\n"

    if recent_memories:
        prompt += "\n## My Recent Memories (Last 5 actions):\n"
        for mem in recent_memories:
            prompt += f"- {str(mem)}\n"

        # 🔍 Loop-breaking hint: count repeated failed actions
        failed_actions = []
        for mem in recent_memories:
            if "failed" in str(mem).lower():
                # crude extraction: look for "to VERB the TARGET"
                tokens = str(mem).split()
                if "to" in tokens:
                    idx = tokens.index("to")
                    action = " ".join(tokens[idx+1:idx+3])  # e.g. "open door"
                    failed_actions.append(action)
        if failed_actions:
            counts = Counter(failed_actions)
            prompt += "\n## Important Observations:\n"
            for act, n in counts.items():
                if n >= 2:
                    prompt += f"- Note: The action '{act}' has failed {n} times recently. Consider trying something different.\n"

    prompt += "\n## Hypothetical Plans:\n"
    for outcome in hypothetical_outcomes:
        act = outcome.get("action", {}) or {}
        prompt += f"- Action: {str(act)}\n"
        prompt += f"  - Imagined: '{str(outcome.get('imagined', ''))}'\n"
        prompt += f"  - Simulated: '{str(outcome.get('simulated', ''))}'\n"

    prompt += "\nNow return my final decision in JSON."
    return prompt

# --- ENDPOINTS ---


@app.route('/generate_impulse', methods=['POST'])
def generate_impulse():
    try:
        data = request.json
        prompt = generate_user_prompt(data)
        logging.info("Subconscious prompt sent to Ollama.")
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SUBCONSCIOUS_PROMPT},
                {"role": "user", "content": prompt}
            ],
            options={"temperature": 0.8},
            format="json"
        )
        llm_json = safe_json_loads(response["message"]["content"])
        return jsonify(normalize_impulses(llm_json))
    except Exception as e:
        logging.warning(f"/generate_impulse failed: {e}")
        return jsonify({
            "emotional_shift": {"mood":"neutral","level_delta":0,"reason":"fallback"},
            "impulses":[{"verb":"wait","target":None,"drive":"safety","urgency":0.1}]
        })

@app.route('/imagine', methods=['POST'])
def imagine():
    try:
        data = request.json
        action = data.get("action", {}) or {}
        verb = str(action.get("verb", "wait"))
        tgt = action.get("target")
        if not tgt or tgt == "null":
            act_str = f"I will {verb} (do nothing)."
        else:
            act_str = f"I will {verb} the {str(tgt)}."
        user_prompt = f"Hypothetical action: {act_str} What is the most likely outcome?"
        logging.info("Imagination prompt sent to Ollama.")
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": IMAGINATION_PROMPT},
                {"role": "user", "content": str(user_prompt)}
            ],
            options={"temperature": 0.7},
            format="json"
        )
        llm_json = safe_json_loads(response["message"]["content"])
        return jsonify(llm_json or {"outcome":"uncertain"})
    except Exception as e:
        logging.warning(f"/imagine failed: {e}")
        return jsonify({"outcome":"uncertain"})

@app.route('/reflect', methods=['POST'])
def reflect():
    try:
        data = request.json
        prompt = generate_reflection_prompt(data)
        logging.info("Reflection prompt sent to Ollama.")
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": CONSCIOUS_MIND_PROMPT},
                {"role": "user", "content": str(prompt)}
            ],
            options={"temperature": 0.5},
            format="json"
        )
        llm_json = safe_json_loads(response["message"]["content"])
        return jsonify(llm_json or {
            "final_action":{"verb":"wait","target":None},
            "reasoning":"fallback"
        })
    except Exception as e:
        logging.warning(f"/reflect failed: {e}")
        return jsonify({
            "final_action":{"verb":"wait","target":None},
            "reasoning":"fallback"
        })


if __name__ == '__main__':
    logging.info(f"Psyche-LLM (Ollama) running on model: {OLLAMA_MODEL}")
    app.run(port=5000)
