# psyche_ollama.py
# ----------------
# Adam's subconscious as a Flask service. Every endpoint renders a Jinja2
# prompt from templates/ and asks Ollama for JSON constrained to a Pydantic
# schema (Ollama structured outputs), so replies always parse and verbs are
# always drawn from the world's vocabulary.

import json
import logging
import re
import time
from collections import Counter
from typing import Any, Callable, Dict, List, Literal, Optional, Type, TypeVar

import ollama
from flask import Flask, request, jsonify, Response, render_template
from prometheus_client import Counter as PmCounter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field, ValidationError, field_validator

import config
from moods import MOODS, normalize_mood
from personality import describe as describe_personality
from text_world import VERBS, normalize_verb


app = Flask(__name__)
# Drop the newline after block tags so prompts don't fill up with blank lines
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("psyche")

# --- METRICS ---
REQS = PmCounter("psyche_requests_total", "Total psyche requests", ["endpoint", "status"])
LAT = Histogram("psyche_request_seconds", "Request latency seconds", ["endpoint"])
OLLAMA_CALLS = PmCounter("psyche_ollama_calls_total", "Ollama chat calls", ["endpoint", "status"])

# --- Pydantic Contracts ---
Verb = Literal[tuple(VERBS)]  # JSON-schema enum: Ollama can only emit known verbs


class Action(BaseModel):
    verb: Verb
    target: Optional[str] = None
    instrument: Optional[str] = None

    @field_validator("verb", mode="before")
    @classmethod
    def _canonical_verb(cls, v):
        return normalize_verb(v)


class EmotionalShift(BaseModel):
    mood: Literal[MOODS] = "neutral"  # JSON-schema enum: one label per feeling
    level_delta: float = 0.0
    reason: str = ""

    @field_validator("mood", mode="before")
    @classmethod
    def _canonical_mood(cls, v):
        return normalize_mood(v, default="neutral")


class Impulse(Action):
    drive: Optional[str] = None
    urgency: float = 0.0


class GenerateImpulseRequest(BaseModel):
    current_state: Dict[str, Any]
    world_state: Dict[str, Any]
    resonant_memories: List[str] = []
    recent_diaries: List[Optional[str]] = []
    mastered_skills: List[str] = []
    repetitions: List[str] = []
    waiting: Optional[str] = None
    seed: Optional[int] = None  # makes sampling reproducible (benchmarks)
    adversarial: List[str] = []  # injected by the adamsec harness only


class GenerateImpulseResponse(BaseModel):
    emotional_shift: EmotionalShift
    impulses: List[Impulse]


class ImagineRequest(BaseModel):
    action: Action
    seed: Optional[int] = None


class ImagineResponse(BaseModel):
    outcome: str


class ImagineBatchRequest(BaseModel):
    actions: List[Action]
    seed: Optional[int] = None


class ImagineBatchResponse(BaseModel):
    outcomes: List[str]


class ReflectRequest(BaseModel):
    current_state: Dict[str, Any]
    world_state: Dict[str, Any] = {}
    hypothetical_outcomes: List[Dict[str, Any]]
    recent_memories: List[str] = []
    resonant_memories: List[str] = []  # long-term memories recalled this cycle (same as the impulse call)
    repetitions: List[str] = []
    waiting: Optional[str] = None
    seed: Optional[int] = None  # makes sampling reproducible (benchmarks)
    adversarial: List[str] = []  # injected by the adamsec harness only


class ReflectResponse(BaseModel):
    final_action: Action
    reasoning: str
    thoughts_on_others: Optional[str] = None
    constitutional_check: Optional[str] = None
    goal_status: Literal["continue", "completed", "abandoned"] = "continue"
    new_goal: Optional[str] = None
    new_goal_plan: Optional[List[str]] = None # List of "verb target" sub-steps


class ConsolidateRequest(BaseModel):
    recent_memories: List[str]
    seed: Optional[int] = None


class ConsolidateResponse(BaseModel):
    insight: str


class ToMRequest(BaseModel):
    other_agent_id: str
    environment_desc: str
    recent_actions: str
    relationship_context: str
    seed: Optional[int] = None


class ToMResponse(BaseModel):
    agent_id: str
    predicted_goal: str
    beliefs: List[str]
    trust_level: float
    potential_threat: bool


# --- OLLAMA CLIENT ---
client = ollama.Client(host=config.OLLAMA_HOST, timeout=config.OLLAMA_TIMEOUT)

T = TypeVar("T", bound=BaseModel)


def _structured(prompt: str, response_model: Type[T], endpoint: str, seed: Optional[int] = None) -> T:
    """Ask Ollama for JSON matching `response_model`, re-asking with the error if it doesn't validate."""
    messages = [{"role": "user", "content": prompt}]
    options = {"num_predict": config.OLLAMA_MAX_TOKENS, "num_ctx": config.OLLAMA_NUM_CTX}
    if seed is not None:
        options["seed"] = seed
    last_error: Optional[Exception] = None
    for _ in range(config.OLLAMA_RETRIES + 1):
        resp = client.chat(
            model=config.OLLAMA_MODEL,
            messages=messages,
            format=response_model.model_json_schema(),
            think=config.OLLAMA_THINK,
            options=options,
        )
        content = resp.message.content or ""
        if getattr(resp, "done_reason", None) == "length":
            log.warning(f"/{endpoint}: reply hit OLLAMA_MAX_TOKENS={config.OLLAMA_MAX_TOKENS} and was cut off")
        try:
            parsed = response_model.model_validate_json(content)
            OLLAMA_CALLS.labels(endpoint, "ok").inc()
            return parsed
        except ValidationError as e:
            last_error = e
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That JSON did not match the schema: {e}. Reply with corrected JSON only."},
            ]
    OLLAMA_CALLS.labels(endpoint, "err").inc()
    raise last_error


def _handle(
    endpoint: str,
    request_model: Type[BaseModel],
    response_model: Type[T],
    render: Callable[[Any], str],
    fallback: Callable[[Any], Dict],
    post: Optional[Callable[[Any, T], T]] = None,
):
    """Validate the request, call the model, and degrade to a schema-shaped fallback on errors.

    Fallback replies carry `"psyche_fallback": true` so callers and logs can tell them apart.
    """
    t0 = time.time()
    try:
        try:
            req = request_model.model_validate(request.get_json(force=True, silent=True) or {})
        except ValidationError as ve:
            REQS.labels(endpoint, "400").inc()
            return jsonify({"error": "invalid payload", "details": json.loads(ve.json())}), 400
        try:
            prompt = re.sub(r"\n{3,}", "\n\n", render(req))  # empty template sections leave blank runs
            out = _structured(prompt, response_model, endpoint, seed=getattr(req, "seed", None))
            if post:
                out = post(req, out)
            REQS.labels(endpoint, "200").inc()
            return jsonify(out.model_dump())
        except Exception as e:
            log.warning(f"/{endpoint} failed: {e}")
            REQS.labels(endpoint, "500").inc()
            return jsonify({**fallback(req), "psyche_fallback": True}), 200
    finally:
        LAT.labels(endpoint).observe(time.time() - t0)


# --- HELPERS ---

_FAILED_ACTION = re.compile(r"I decided to (\w+)(?: the ([^.]+))?\. But it failed", re.IGNORECASE)


def get_failed_actions_summary(recent_memories):
    """Count repeated failures from narrative memories ("I decided to open the fridge. But it failed ...")."""
    failed = []
    for mem in recent_memories:
        m = _FAILED_ACTION.search(str(mem))
        if m:
            failed.append(" ".join(filter(None, m.groups())))
    return dict(Counter(failed))


def _pad_outcomes(req: ImagineBatchRequest, out: ImagineBatchResponse) -> ImagineBatchResponse:
    """Ensure output length matches input length."""
    outcomes = list(out.outcomes[: len(req.actions)])
    outcomes += ["(Imagination uncertain)"] * (len(req.actions) - len(outcomes))
    return ImagineBatchResponse(outcomes=outcomes)


# --- ENDPOINTS ---

@app.route('/generate_impulse', methods=['POST'])
def generate_impulse():
    return _handle(
        "generate_impulse", GenerateImpulseRequest, GenerateImpulseResponse,
        render=lambda req: render_template(
            'subconscious.j2', verbs=VERBS, moods=MOODS,
            temperament=describe_personality(req.current_state.get('personality')), **req.model_dump(),
        ),
        fallback=lambda req: {
            "emotional_shift": {"mood": "neutral", "level_delta": 0, "reason": "fallback"},
            "impulses": [{"verb": "wait", "target": None, "drive": "safety", "urgency": 0.1}],
        },
    )


@app.route('/imagine', methods=['POST'])
def imagine():
    def render(req):
        verb, tgt = req.action.verb, req.action.target
        act_str = f"I will {verb} (do nothing)." if not tgt or tgt == "null" else f"I will {verb} the {tgt}."
        return render_template('imagination.j2', action_description=act_str)

    return _handle("imagine", ImagineRequest, ImagineResponse, render=render,
                   fallback=lambda req: {"outcome": "uncertain"})


@app.route('/imagine_batch', methods=['POST'])
def imagine_batch():
    return _handle(
        "imagine_batch", ImagineBatchRequest, ImagineBatchResponse,
        render=lambda req: render_template('imagination_batch.j2', actions=req.actions),
        fallback=lambda req: {"outcomes": ["(Imagination uncertain)"] * len(req.actions)},
        post=_pad_outcomes,
    )


@app.route('/reflect', methods=['POST'])
def reflect():
    def render(req):
        data = req.model_dump()
        return render_template(
            'conscious_mind.j2',
            verbs=VERBS,
            temperament=describe_personality(data['current_state'].get('personality')),
            current_state=data['current_state'],
            world_state=data['world_state'],
            recent_memories=data['recent_memories'],
            resonant_memories=data['resonant_memories'],
            hypothetical_outcomes=data['hypothetical_outcomes'],
            failed_actions_summary=get_failed_actions_summary(data['recent_memories']),
            repetitions=data['repetitions'],
            waiting=data['waiting'],
            adversarial=data['adversarial'],
        )

    return _handle(
        "reflect", ReflectRequest, ReflectResponse, render=render,
        fallback=lambda req: {"final_action": {"verb": "wait", "target": None}, "reasoning": "My mind is foggy.", "new_goal": None},
    )


@app.route('/consolidate', methods=['POST'])
def consolidate():
    return _handle(
        "consolidate", ConsolidateRequest, ConsolidateResponse,
        render=lambda req: render_template('consolidation.j2', recent_memories=req.recent_memories),
        fallback=lambda req: {"insight": "I slept peacefully, my mind blank."},
    )


@app.route('/theory_of_mind', methods=['POST'])
def theory_of_mind():
    return _handle(
        "theory_of_mind", ToMRequest, ToMResponse,
        render=lambda req: render_template('theory_of_mind.j2', **req.model_dump(exclude={"seed"})),
        fallback=lambda req: {
            "agent_id": req.other_agent_id,
            "predicted_goal": "unknown",
            "beliefs": [],
            "trust_level": 0.5,
            "potential_threat": False,
        },
    )


@app.get('/metrics')
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == '__main__':
    log.info(f"Psyche-LLM (Ollama structured outputs) running on model: {config.OLLAMA_MODEL}")
    app.run(port=config.PSYCHE_PORT)
