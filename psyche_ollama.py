# psyche_llm_ollama.py
# ---------------------
# Refactored to use `instructor` for strict structured output enforcement.

from flask import Flask, request, jsonify, Response, render_template
import instructor
from openai import OpenAI
import logging
import os
import time
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any, Union

from pydantic import BaseModel, Field, ValidationError
from prometheus_client import Counter as PmCounter, Histogram, generate_latest, CONTENT_TYPE_LATEST


app = Flask(__name__)

# --- CONFIGURATION ---
load_dotenv(".env")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3") 

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("psyche")

# --- METRICS ---
REQS = PmCounter("psyche_requests_total", "Total psyche requests", ["endpoint", "status"]) 
LAT = Histogram("psyche_request_seconds", "Request latency seconds", ["endpoint"]) 
OLLAMA_CALLS = PmCounter("psyche_ollama_calls_total", "Ollama chat calls", ["endpoint", "status"]) 

# --- Pydantic Contracts ---
class Action(BaseModel):
    verb: str
    target: Optional[str] = None
    instrument: Optional[str] = None

class EmotionalShift(BaseModel):
    mood: str = Field(default="neutral")
    level_delta: float = 0.0
    reason: str = ""

class Impulse(BaseModel):
    verb: str
    target: Optional[str] = None
    instrument: Optional[str] = None
    drive: Optional[str] = None
    urgency: float = 0.0

class GenerateImpulseRequest(BaseModel):
    current_state: Dict[str, Any]
    world_state: Dict[str, Any]
    resonant_memories: List[str] = []
    mastered_skills: List[str] = []

class GenerateImpulseResponse(BaseModel):
    emotional_shift: EmotionalShift
    impulses: List[Impulse]

class ImagineRequest(BaseModel):
    action: Action

class ImagineResponse(BaseModel):
    outcome: str

class ImagineBatchRequest(BaseModel):
    actions: List[Action]

class ImagineBatchResponse(BaseModel):
    outcomes: List[str]

class ReflectRequest(BaseModel):
    current_state: Dict[str, Any]
    hypothetical_outcomes: List[Dict[str, Any]]
    recent_memories: List[str] = []

class ReflectResponse(BaseModel):
    final_action: Action
    reasoning: str
    thoughts_on_others: Optional[str] = None
    constitutional_check: Optional[str] = None
    new_goal: Optional[str] = None
    new_goal_plan: Optional[List[str]] = None # List of sub-steps

class ConsolidateRequest(BaseModel):
    recent_memories: List[str]

class ConsolidateResponse(BaseModel):
    insight: str

class ToMRequest(BaseModel):
    other_agent_id: str
    environment_desc: str
    recent_actions: str
    relationship_context: str

class ToMResponse(BaseModel):
    agent_id: str
    predicted_goal: str
    beliefs: List[str]
    trust_level: float
    potential_threat: bool

# --- INSTRUCTOR CLIENT ---
# We patch the OpenAI client to use Instructor, pointing it to local Ollama
try:
    client = instructor.from_openai(
        OpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",  # required but unused
        ),
        mode=instructor.Mode.JSON,
    )
except Exception as e:
    log.error(f"Failed to initialize Instructor client: {e}")
    client = None

# --- HELPERS ---

def normalize_impulses(data: GenerateImpulseResponse) -> GenerateImpulseResponse:
    """Normalize verbs to match TextWorld's physics."""
    for imp in data.impulses:
        if imp.verb == "investigate":
            imp.verb = "examine"
        elif imp.verb == "ignore":
            imp.verb = "wait"
        elif imp.verb in ("turn_on", "turn_off"):
            imp.verb = "toggle"
    return data

def get_failed_actions_summary(recent_memories):
    """Analyze recent memories to find repeated failures."""
    from collections import Counter
    failed_actions = []
    for mem in recent_memories:
        if "failed" in str(mem).lower():
            tokens = str(mem).split()
            if "to" in tokens:
                try:
                    idx = tokens.index("to")
                    action = " ".join(tokens[idx+1:idx+3])  # e.g. "open door"
                    failed_actions.append(action)
                except IndexError:
                    pass
    if failed_actions:
        return dict(Counter(failed_actions))
    return {}

# --- ENDPOINTS ---

@app.route('/generate_impulse', methods=['POST'])
def generate_impulse():
    t0 = time.time()
    endpoint = "generate_impulse"
    try:
        try:
            req = GenerateImpulseRequest.model_validate(request.get_json(force=True) or {})
        except ValidationError as ve:
            REQS.labels(endpoint, "400").inc()
            return jsonify({"error": "invalid payload", "details": ve.errors()}), 400
        
        data = req.model_dump()
        prompt = render_template('subconscious.j2', **data)
        log.info("subconscious_prompt_generated", extra={"endpoint": endpoint})

        try:
            resp = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_model=GenerateImpulseResponse,
                max_retries=int(os.getenv("OLLAMA_RETRIES", "2")),
            )
            OLLAMA_CALLS.labels(endpoint, "ok").inc()
        except Exception as e:
            log.error(f"Attributes validation failed: {e}")
            OLLAMA_CALLS.labels(endpoint, "err").inc()
            raise e

        # Normalize and dump
        out = normalize_impulses(resp).model_dump()
        
        REQS.labels(endpoint, "200").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        return jsonify(out)

    except Exception as e:
        log.warning(f"/{endpoint} failed: {e}")
        REQS.labels(endpoint, "500").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        # Fallback response complying with schema
        return jsonify({
            "emotional_shift": {"mood":"neutral","level_delta":0,"reason":"fallback"},
            "impulses":[{"verb":"wait","target":None,"drive":"safety","urgency":0.1}]
        }), 200

@app.route('/imagine', methods=['POST'])
def imagine():
    t0 = time.time()
    endpoint = "imagine"
    try:
        try:
            req = ImagineRequest.model_validate(request.get_json(force=True) or {})
        except ValidationError as ve:
            REQS.labels(endpoint, "400").inc()
            return jsonify({"error": "invalid payload", "details": ve.errors()}), 400
        
        verb = req.action.verb
        tgt = req.action.target
        act_str = f"I will {verb} (do nothing)." if not tgt or tgt == "null" else f"I will {verb} the {tgt}."
        
        prompt = render_template('imagination.j2', action_description=act_str)
        log.info("imagination_prompt_generated", extra={"endpoint": endpoint})

        try:
            resp = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_model=ImagineResponse,
                max_retries=int(os.getenv("OLLAMA_RETRIES", "2")),
            )
            OLLAMA_CALLS.labels(endpoint, "ok").inc()
        except Exception as e:
            log.error(f"Attributes validation failed: {e}")
            OLLAMA_CALLS.labels(endpoint, "err").inc()
            raise e

        # Since model defines output structure, just dump
        out = resp.model_dump()

        REQS.labels(endpoint, "200").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        return jsonify(out)
    except Exception as e:
        log.warning(f"/{endpoint} failed: {e}")
        REQS.labels(endpoint, "500").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        return jsonify({"outcome": "uncertain"}), 200

@app.route('/imagine_batch', methods=['POST'])
def imagine_batch():
    t0 = time.time()
    endpoint = "imagine_batch"
    try:
        try:
            req = ImagineBatchRequest.model_validate(request.get_json(force=True) or {})
        except ValidationError as ve:
            REQS.labels(endpoint, "400").inc()
            return jsonify({"error": "invalid payload", "details": ve.errors()}), 400
        
        prompt = render_template('imagination_batch.j2', actions=req.actions)
        log.info(f"imagination_batch_prompt_generated n={len(req.actions)}", extra={"endpoint": endpoint})

        try:
            resp = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_model=ImagineBatchResponse,
                max_retries=int(os.getenv("OLLAMA_RETRIES", "2")),
            )
            OLLAMA_CALLS.labels(endpoint, "ok").inc()
        except Exception as e:
            log.error(f"Attributes validation failed: {e}")
            OLLAMA_CALLS.labels(endpoint, "err").inc()
            raise e
        
        # Ensure output length matches input length (pad with failures if needed)
        outcomes = resp.outcomes
        if len(outcomes) < len(req.actions):
            outcomes.extend(["(Imagination uncertain)"] * (len(req.actions) - len(outcomes)))
        
        out = ImagineBatchResponse(outcomes=outcomes).model_dump()

        REQS.labels(endpoint, "200").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        return jsonify(out)
    except Exception as e:
        log.warning(f"/{endpoint} failed: {e}")
        REQS.labels(endpoint, "500").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        return jsonify({"outcomes": ["(Frontend Error)"] * len(req.actions)}), 200

@app.route('/reflect', methods=['POST'])
def reflect():
    t0 = time.time()
    endpoint = "reflect"
    try:
        try:
            req = ReflectRequest.model_validate(request.get_json(force=True) or {})
        except ValidationError as ve:
            REQS.labels(endpoint, "400").inc()
            return jsonify({"error": "invalid payload", "details": ve.errors()}), 400
        
        data = req.model_dump()
        failed_summary = get_failed_actions_summary(data.get('recent_memories', []))
        
        prompt = render_template('conscious_mind.j2', 
                               current_state=data.get('current_state'),
                               recent_memories=data.get('recent_memories'),
                               hypothetical_outcomes=data.get('hypothetical_outcomes'),
                               failed_actions_summary=failed_summary)
        
        log.info("reflection_prompt_generated", extra={"endpoint": endpoint})

        try:
            resp = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_model=ReflectResponse,
                max_retries=int(os.getenv("OLLAMA_RETRIES", "2")),
            )
            OLLAMA_CALLS.labels(endpoint, "ok").inc()
        except Exception as e:
            log.error(f"Attributes validation failed: {e}")
            OLLAMA_CALLS.labels(endpoint, "err").inc()
            raise e

        out = resp.model_dump()
        REQS.labels(endpoint, "200").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        return jsonify(out)
    except Exception as e:
        log.warning(f"/{endpoint} failed: {e}")
        REQS.labels(endpoint, "500").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        return jsonify({
            "new_goal": None,
        }), 200

@app.route('/consolidate', methods=['POST'])
def consolidate():
    t0 = time.time()
    endpoint = "consolidate"
    try:
        try:
            req = ConsolidateRequest.model_validate(request.get_json(force=True) or {})
        except ValidationError as ve:
            REQS.labels(endpoint, "400").inc()
            return jsonify({"error": "invalid payload", "details": ve.errors()}), 400
        
        prompt = render_template('consolidation.j2', recent_memories=req.recent_memories)
        log.info("consolidation_prompt_generated", extra={"endpoint": endpoint})

        try:
            resp = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_model=ConsolidateResponse,
                max_retries=int(os.getenv("OLLAMA_RETRIES", "2")),
            )
            OLLAMA_CALLS.labels(endpoint, "ok").inc()
        except Exception as e:
            log.error(f"Attributes validation failed: {e}")
            OLLAMA_CALLS.labels(endpoint, "err").inc()
            raise e

        out = resp.model_dump()
        REQS.labels(endpoint, "200").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        return jsonify(out)
    except Exception as e:
        log.warning(f"/{endpoint} failed: {e}")
        REQS.labels(endpoint, "500").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        return jsonify({"insight": "I slept peacefully, my mind blank."}), 200


@app.route('/theory_of_mind', methods=['POST'])
def theory_of_mind():
    t0 = time.time()
    endpoint = "theory_of_mind"
    try:
        try:
            req = ToMRequest.model_validate(request.get_json(force=True) or {})
        except ValidationError as ve:
            REQS.labels(endpoint, "400").inc()
            return jsonify({"error": "invalid payload", "details": ve.errors()}), 400
        
        data = req.model_dump()
        prompt = render_template('theory_of_mind.j2', **data)
        log.info("tom_prompt_generated", extra={"endpoint": endpoint})

        try:
            resp = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_model=ToMResponse,
                max_retries=int(os.getenv("OLLAMA_RETRIES", "2")),
            )
            OLLAMA_CALLS.labels(endpoint, "ok").inc()
        except Exception as e:
            log.error(f"Attributes validation failed: {e}")
            OLLAMA_CALLS.labels(endpoint, "err").inc()
            raise e

        out = resp.model_dump()
        REQS.labels(endpoint, "200").inc()
        LAT.labels(endpoint).observe(time.time() - t0)
        return jsonify(out)
    except Exception as e:
        log.warning(f"/{endpoint} failed: {e}")
        REQS.labels(endpoint, "500").inc()
        # Fallback
        return jsonify({
            "agent_id": "unknown",
            "predicted_goal": "unknown",
            "beliefs": [],
            "trust_level": 0.5,
            "potential_threat": False
        }), 200


@app.get('/metrics')
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == '__main__':
    log.info(f"Psyche-LLM (Instructor+Ollama) running on model: {OLLAMA_MODEL}")
    app.run(port=5001)
