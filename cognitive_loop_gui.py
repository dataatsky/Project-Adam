
import json
import time
import csv
import os
import sys
import threading
from collections import deque, defaultdict
from queue import Queue, Empty

import requests
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from flask import Flask, jsonify
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

from text_world import TextWorld

# --------------------
# Configuration
# --------------------
load_dotenv(".env")
PSYCHE_LLM_API_URL = "http://127.0.0.1:5000/"
PPI_KEY = os.getenv("PINECONE")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
LOG_FILE = os.getenv("LOG_FILE")

LOG_HEADERS = [
    "timestamp", "cycle_num", "experiment_tag", "agent_id", "world_time", "location", "mood", "mood_intensity",
    "sensory_events", "resonant_memories", "impulses", "chosen_action", "action_result",
    "imagined_outcomes", "simulated_outcomes", "emotional_delta", "kpis", "snapshot"
]

# --------------------
# Vector memory bootstrap
# --------------------
print("Initializing Cognitive Loop Server…")
model = SentenceTransformer(os.getenv("SENTENCE_MODEL"))
print("Model loaded.")

pc = Pinecone(api_key=PPI_KEY, environment=PINECONE_ENVIRONMENT)
try:
    # New SDKs return a list directly
    try:
        indexes = pc.list_indexes().names()
    except Exception:
        indexes = pc.list_indexes()
    if PINECONE_INDEX_NAME not in indexes:
        print(f"Creating Pinecone index: {PINECONE_INDEX_NAME}")
        pc.create_index(name=PINECONE_INDEX_NAME, dimension=384, metric="cosine")
    index = pc.Index(PINECONE_INDEX_NAME)
    print("Pinecone connection established.")
except Exception as e:
    print(f"⚠️ Pinecone init failed: {e}")
    index = None


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
    if stats.get("total_vector_count", 0) == 0:
        print("— Pre-populating Pinecone with foundational memories …")
        vectors = []
        for i, text in enumerate(FOUNDATIONAL_MEMORIES):
            vec = model.encode(text).tolist()
            meta = {"text": text, "timestamp": time.time(), "type": "foundational"}
            vectors.append((str(i), vec, meta))
        index.upsert(vectors=vectors)
        print(f"— Added {len(vectors)} foundational memories.")
    else:
        print("— Found existing memories, skipping pre-population.")

# --------------------
# Thread-safe UI bus
# --------------------
class UiBus:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: Queue = Queue()

    def post(self, fn, *args, **kwargs):
        self.q.put((fn, args, kwargs))

    def pump(self):
        try:
            while True:
                fn, args, kwargs = self.q.get_nowait()
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    print(f"UI error: {e}")
        except Empty:
            pass

# --------------------
# Insight Engine (no LLM)
# --------------------
class InsightEngine:
    def __init__(self, history_len: int = 24):
        self.actions = deque(maxlen=history_len)         # {verb, target, success}
        self.impulses = deque(maxlen=history_len)        # [ {verb, target, urgency} ]
        self.triggers = deque(maxlen=history_len)        # ["phone: ringing", …]
        self.moods = deque(maxlen=history_len)           # ["calm", …]

    def add_cycle(self, *, action: dict, success: bool, impulses: list, triggers: list, mood: str):
        self.actions.append({"verb": action.get("verb"), "target": action.get("target"), "success": bool(success)})
        self.impulses.append(impulses or [])
        self.triggers.append(triggers or [])
        self.moods.append(mood or "")

    # KPI helpers
    def _frustration(self, n=10):
        recent = list(self.actions)[-n:]
        if not recent: return 0.0
        fails = sum(1 for a in recent if not a.get("success"))
        return round(fails/len(recent), 2)

    def _conflict(self):
        if not self.impulses or not self.actions: return 0.0
        last_imps = self.impulses[-1] or []
        chosen = self.actions[-1]
        highs = [imp for imp in last_imps if float(imp.get("urgency",0)) >= 0.7]
        if not highs: return 0.0
        suppressed = [imp for imp in highs if not (imp.get("verb") == chosen.get("verb") and imp.get("target") == chosen.get("target"))]
        return round(len(suppressed)/len(highs), 2)

    def _novelty(self, n=10):
        recent = list(self.triggers)[-n:]
        flat = [t for L in recent for t in L]
        if len(flat) <= 1: return 0.0
        return round(len(set(flat))/len(flat), 2)

    def _loop_score(self, n=10):
        recent = list(self.actions)[-n:]
        if not recent: return 0.0
        best = 0
        streak = 0
        last_pair = None
        for a in recent:
            pair = (a.get("verb"), a.get("target"))
            if pair == last_pair and not a.get("success"):
                streak += 1
            else:
                streak = 1 if not a.get("success") else 0
            last_pair = pair
            best = max(best, streak)
        return round(min(1.0, best/max(1, n/2)), 2)

    def _goal_progress(self, last_action):
        helpful = {"investigate", "answer", "go", "turn_on", "open"}
        detour = {"sleep", "read", "eat"}
        v = (last_action or {}).get("verb")
        t = (last_action or {}).get("target")
        if v in helpful:
            return 0.7 if t in {"door","phone","tv","radio","computer"} else 0.5
        if v in detour:
            return 0.2
        return 0.3

    def compute_kpis(self):
        last_action = self.actions[-1] if self.actions else {}
        return {
            "frustration": self._frustration(10),
            "conflict": self._conflict(),
            "novelty": self._novelty(10),
            "goal_progress": round(self._goal_progress(last_action), 2),
            "loop_score": self._loop_score(10)
        }

    def badges(self, kpis):
        out = []
        if kpis.get("loop_score",0) >= 0.6:
            out.append({"type":"Loop","text":"Repeating failed attempts"})
        if kpis.get("frustration",0) >= 0.6:
            out.append({"type":"Frustration","text":"Many recent failures"})
        if kpis.get("conflict",0) >= 0.6:
            out.append({"type":"Avoidance","text":"Strong impulses suppressed"})
        return out

    def threads(self):
        buckets = defaultdict(list)
        for a in self.actions:
            buckets[a.get("target")] += [a]
        threads = []
        for target, acts in buckets.items():
            if not target: continue
            succ = sum(1 for a in acts if a.get("success"))
            total = len(acts)
            threads.append({
                "name": f"{target.title()} storyline",
                "target": target,
                "progress": round(succ/max(1,total), 2),
                "recent": [f"{x.get('verb')} -> {'ok' if x.get('success') else 'fail'}" for x in acts[-2:]]
            })
        # sort by recency
        order = {t:i for i,t in enumerate([a.get("target") for a in self.actions][::-1])}
        threads.sort(key=lambda th: order.get(th["target"], 999))
        return threads

    def causal_line(self, *, triggers, impulses, action, imagined, simulated, emotional_delta):
        trig_txt = ", ".join((triggers or [])[:2]) or "none"
        top = None
        if impulses:
            top = sorted(impulses, key=lambda x: x.get("urgency",0), reverse=True)[0]
        top_txt = f"{top.get('verb')} {top.get('target')} ({top.get('urgency',0):.2f})" if top else "none"
        act_txt = f"{(action or {}).get('verb')} {(action or {}).get('target')}"
        out_txt = (simulated or "").split(".")[0]
        mood_txt = ""
        if emotional_delta:
            mood_txt = f" → mood {emotional_delta.get('mood','?')} ({emotional_delta.get('level_delta',0):+0.2f})"
        return f"[{trig_txt}] → [{top_txt}] → [{act_txt}] → [{out_txt}]{mood_txt}"

    def cards(self, *, triggers, kpis, chosen, imagined, simulated, emotional_delta):
        change = f"Mood {emotional_delta.get('mood','same')} ({emotional_delta.get('level_delta',0):+0.2f}); Frustration {kpis['frustration']}, Conflict {kpis['conflict']}"
        cause = "; ".join((triggers or [])[:2]) or "routine scan"
        why = f"{cause} → chose {chosen.get('verb')} {chosen.get('target')}"
        result = f"Imagined: {imagined[:60]}… | Simulated: {simulated[:60]}…"
        return [
            {"title":"What changed","body":change},
            {"title":"Why","body":why},
            {"title":"Result","body":result}
        ]

# --------------------
# Tkinter UI
# --------------------
class PsycheMonitor:
    def __init__(self, root: tk.Tk, ui_bus: UiBus):
        self.root = root
        self.ui_bus = ui_bus
        self.root.title("Adam's Psyche Monitor — Insights")
        self.root.geometry("1320x860")

        # CognitiveLoop reference (set later)
        self.brain = None

        # Controls toolbar
        controls = ttk.Labelframe(root, text="Controls", padding=6)
        controls.pack(fill="x", padx=6, pady=(6, 0))
        self.btn_pause = ttk.Button(controls, text="Pause", command=lambda: self._on_pause())
        self.btn_pause.pack(side="left")
        self.btn_resume = ttk.Button(controls, text="Resume", command=lambda: self._on_resume())
        self.btn_resume.pack(side="left", padx=(6, 0))
        self.btn_step = ttk.Button(controls, text="Step", command=lambda: self._on_step())
        self.btn_step.pack(side="left", padx=(6, 0))
        ttk.Label(controls, text="Cycle sec:").pack(side="left", padx=(12, 4))
        self.speed = tk.DoubleVar(value=5.0)
        self.speed_scale = ttk.Scale(controls, from_=0.2, to=10.0, orient="horizontal", variable=self.speed, command=self._on_speed)
        self.speed_scale.pack(side="left", fill="x", expand=True)
        self.cycle_var = tk.StringVar(value="Cycle: 0")
        ttk.Label(controls, textvariable=self.cycle_var).pack(side="right")

        main = ttk.PanedWindow(root, orient="horizontal")
        main.pack(fill="both", expand=True)

        left = ttk.PanedWindow(main, orient="vertical")
        right = ttk.PanedWindow(main, orient="vertical")
        main.add(left, weight=2)
        main.add(right, weight=1)

        # Vitals
        vitals = ttk.Labelframe(left, text="Vitals", padding=10)
        row1 = ttk.Frame(vitals)
        ttk.Label(row1, text="Mood:").pack(side="left")
        self.mood_text = ttk.Label(row1, text="neutral", width=16)
        self.mood_text.pack(side="left", padx=(6,12))
        ttk.Label(row1, text="Intensity:").pack(side="left")
        self.mood_bar = ttk.Progressbar(row1, orient="horizontal", mode="determinate", maximum=1.0, length=260)
        self.mood_bar.pack(side="left", fill="x", expand=True)
        row1.pack(fill="x", pady=4)

        row2 = ttk.Frame(vitals)
        ttk.Label(row2, text="Hunger:").pack(side="left")
        self.hunger_bar = ttk.Progressbar(row2, orient="horizontal", mode="determinate", maximum=1.0, length=320)
        self.hunger_bar.pack(side="left", fill="x", expand=True, padx=(8,0))
        self.hunger_val = ttk.Label(row2, text="0.00")
        self.hunger_val.pack(side="left", padx=8)
        row2.pack(fill="x", pady=4)

        vitals.pack(fill="x")
        left.add(vitals, weight=1)

        # KPI bars
        kpi = ttk.Labelframe(left, text="KPIs", padding=10)
        self.kpi_bars = {}
        for key in ("frustration", "conflict", "novelty", "goal_progress", "loop_score"):
            row = ttk.Frame(kpi)
            ttk.Label(row, text=f"{key}:").pack(side="left", padx=(0, 6))
            bar = ttk.Progressbar(row, orient="horizontal", mode="determinate", maximum=1.0, length=260)
            bar.pack(side="left", fill="x", expand=True)
            val = ttk.Label(row, text="0.00")
            val.pack(side="left", padx=8)
            row.pack(fill="x", pady=2)
            self.kpi_bars[key] = (bar, val)
        kpi.pack(fill="x")
        left.add(kpi, weight=1)

        # Mind notebook
        mind = ttk.Labelframe(left, text="Mind", padding=10)
        self.nb = ttk.Notebook(mind)
        self.tab_insights = ttk.Frame(self.nb)
        self.tab_sub = ttk.Frame(self.nb)
        self.tab_imag = ttk.Frame(self.nb)
        self.tab_dec = ttk.Frame(self.nb)
        self.nb.add(self.tab_insights, text="Insights")
        self.nb.add(self.tab_sub, text="Subconscious")
        self.nb.add(self.tab_imag, text="Imagination")
        self.nb.add(self.tab_dec, text="Decision")
        self.nb.pack(fill="both", expand=True)
        mind.pack(fill="both", expand=True)
        left.add(mind, weight=4)

        # Insights widgets
        top = ttk.Frame(self.tab_insights)
        top.pack(fill="x", padx=4, pady=4)
        self.causal_label = ttk.Label(top, text="Causal: —", anchor="w")
        self.causal_label.pack(fill="x")

        badge_row = ttk.Frame(self.tab_insights)
        badge_row.pack(fill="x", padx=4, pady=(0,4))
        self.badge_var = tk.StringVar(value="")
        self.badge_label = ttk.Label(badge_row, textvariable=self.badge_var, foreground="#933")
        self.badge_label.pack(anchor="w")

        self.cards_frame = ttk.Frame(self.tab_insights)
        self.cards_frame.pack(fill="both", expand=True, padx=6, pady=6)
        self.card_widgets = []
        for _ in range(3):
            frame = ttk.Labelframe(self.cards_frame, text="Card", padding=8)
            text = ScrolledText(frame, wrap="word", height=7, state="disabled")
            text.pack(fill="both", expand=True)
            frame.pack(side="left", fill="both", expand=True, padx=4)
            self.card_widgets.append((frame, text))

        # Right pane: Threads + Live Log
        threads_box = ttk.Labelframe(right, text="Storyline Threads", padding=10)
        right.add(threads_box, weight=1)
        self.threads = ttk.Treeview(threads_box, columns=("story","progress","recent"), show="headings", height=10)
        self.threads.heading("story", text="Storyline")
        self.threads.heading("progress", text="Progress")
        self.threads.heading("recent", text="Recent")
        self.threads.column("story", width=160)
        self.threads.column("progress", width=90, anchor="center")
        self.threads.column("recent", width=260)
        self.threads.pack(fill="both", expand=True)

        log_box = ttk.Labelframe(right, text="Live Console Log", padding=10)
        self.log_text = ScrolledText(log_box, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True)
        right.add(log_box, weight=2)

        # Sub/Imag/Dec raw panes
        self.sub_text = ScrolledText(self.tab_sub, wrap="word", height=12, state="disabled")
        self.sub_text.pack(fill="both", expand=True)
        self.imag_text = ScrolledText(self.tab_imag, wrap="word", height=12, state="disabled")
        self.imag_text.pack(fill="both", expand=True)
        self.dec_text = ScrolledText(self.tab_dec, wrap="word", height=12, state="disabled")
        self.dec_text.pack(fill="both", expand=True)

        # Status bar
        self.status = ttk.Label(root, text="Initializing…", anchor="w", relief="sunken")
        self.status.pack(side="bottom", fill="x")

    # ---------- UI updaters (to be called via UiBus) ----------
    def _status(self, txt):
        self.status.config(text=txt)

    def set_status(self, txt):
        self.ui_bus.post(self._status, txt)

    def _vitals(self, mood, mood_level, hunger):
        self.mood_text.config(text=mood)
        self.mood_bar["value"] = max(0.0, min(1.0, float(mood_level or 0)))
        h = max(0.0, min(1.0, float(hunger or 0)))
        self.hunger_bar["value"] = h
        self.hunger_val.config(text=f"{h:.2f}")

    def update_vitals(self, mood, mood_level, hunger):
        self.ui_bus.post(self._vitals, mood, mood_level, hunger)

    def _kpis(self, kpis):
        for key, (bar, label) in self.kpi_bars.items():
            v = float(kpis.get(key, 0) or 0)
            v = max(0.0, min(1.0, v))
            bar["value"] = v
            label.config(text=f"{v:.2f}")

    def update_kpis(self, kpis):
        self.ui_bus.post(self._kpis, kpis)

    def _subconscious(self, emotional_shift, impulses, resonant):
        self.sub_text.config(state="normal")
        self.sub_text.delete("1.0", "end")
        payload = {"emotional_shift": emotional_shift or {}, "impulses": impulses or [], "resonant_memories": resonant or []}
        self.sub_text.insert("end", json.dumps(payload, indent=2))
        self.sub_text.config(state="disabled")

    def set_subconscious(self, emotional_shift, impulses, resonant):
        self.ui_bus.post(self._subconscious, emotional_shift, impulses, resonant)

    def _imagination(self, hypothetical_outcomes):
        self.imag_text.config(state="normal")
        self.imag_text.delete("1.0", "end")
        self.imag_text.insert("end", json.dumps(hypothetical_outcomes or [], indent=2))
        self.imag_text.config(state="disabled")

    def set_imagination(self, hypothetical_outcomes):
        self.ui_bus.post(self._imagination, hypothetical_outcomes)

    def _decision(self, final_action, reasoning):
        self.dec_text.config(state="normal")
        self.dec_text.delete("1.0", "end")
        self.dec_text.insert("end", json.dumps({"final_action": final_action, "reasoning": reasoning}, indent=2))
        self.dec_text.config(state="disabled")

    def set_decision(self, final_action, reasoning):
        self.ui_bus.post(self._decision, final_action, reasoning)

    def _log(self, text):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def append_log(self, text):
        self.ui_bus.post(self._log, text)

    def _badges(self, badges):
        if not badges:
            self.badge_var.set("")
            return
        s = "  ".join([f"[{b['type']}: {b.get('text','')}]" for b in badges])
        self.badge_var.set(s)

    def _cards(self, cards):
        for (frame, text_widget), card in zip(self.card_widgets, cards):
            frame.config(text=card.get("title","Card"))
            text_widget.config(state="normal")
            text_widget.delete("1.0", "end")
            text_widget.insert("end", card.get("body",""))
            text_widget.config(state="disabled")

    def _causal(self, line):
        self.causal_label.config(text=f"Causal: {line}")

    def _threads(self, threads):
        for row in self.threads.get_children():
            self.threads.delete(row)
        for th in threads:
            prog = f"{int(th['progress']*100)}%"
            recent = "; ".join(th.get("recent", []))
            self.threads.insert("", "end", values=(th.get("name","—"), prog, recent))

    def set_insights(self, *, badges, cards, causal_line, threads):
        self.ui_bus.post(self._badges, badges)
        self.ui_bus.post(self._cards, cards)
        self.ui_bus.post(self._causal, causal_line)
        self.ui_bus.post(self._threads, threads)

    # Brain wiring and control callbacks
    def set_brain(self, brain):
        self.brain = brain
        try:
            self.speed.set(getattr(brain, "cycle_sleep", 5.0))
        except Exception:
            pass

    def set_cycle(self, n: int):
        self.cycle_var.set(f"Cycle: {n}")

    def _on_pause(self):
        if self.brain:
            self.brain.pause()

    def _on_resume(self):
        if self.brain:
            self.brain.resume()

    def _on_step(self):
        if self.brain:
            self.brain.step_once()

    def _on_speed(self, _):
        if self.brain:
            try:
                self.brain.set_cycle_sleep(float(self.speed.get()))
            except Exception:
                pass

# --------------------
# Flask tiny API (optional external viewers)
# --------------------
app = Flask(__name__)
adam_brain = None

@app.route("/get_state", methods=["GET"])
def get_state():
    if adam_brain:
        return jsonify({
            "location": adam_brain.current_world_state.get("agent_location","unknown"),
            "mood": adam_brain.agent_status['emotional_state']['mood']
        })
    return jsonify({"error":"Cognitive loop not running"}), 500

def run_flask_app():
    app.run(port=8080)

# --------------------
# Cognitive Loop
# --------------------
class CognitiveLoop:
    def __init__(self, log_filename, log_headers, ui: PsycheMonitor|None=None, experiment_tag="baseline", agent_id="adam1"):
        self.agent_status = {
            "emotional_state": {"mood":"neutral","level":0.1},
            "personality": {"curiosity":0.8,"bravery":0.6,"caution":0.7},
            "needs": {"hunger":0.1},
            "goal": "Find the source of the strange noises in the house."
        }
        try:
            self.memory_id_counter = index.describe_index_stats().get("total_vector_count",0)
        except Exception:
            self.memory_id_counter = 0
        self.is_running = True
        self.paused = False
        self._step_flag = False
        self.last_resonant_memories = []
        self.recent_memories = []
        self.log_filename = log_filename
        self.log_headers = log_headers
        self.current_world_state = {}
        self.current_mood = "neutral"
        self.mood_intensity = 0.1
        self.ui = ui
        self.insight = InsightEngine(history_len=24)
        self.experiment_tag = experiment_tag
        self.agent_id = agent_id
        self.cycle_counter = 0
        self.last_hypothetical = []
        # loop pacing
        try:
            self.cycle_sleep = float(os.getenv("CYCLE_SLEEP", "5"))
        except Exception:
            self.cycle_sleep = 5.0

    def log_cycle_data(self, cycle_data):
        try:
            with open(self.log_filename, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.log_headers)
                writer.writerow(cycle_data)
        except Exception as e:
            print(f"CSV write error: {e}")

    # helpers to touch UI
    def _ui_status(self, txt):
        if self.ui: self.ui.set_status(txt)

    def _ui_vitals(self):
        if self.ui:
            self.ui.update_vitals(
                self.agent_status['emotional_state']['mood'],
                self.agent_status['emotional_state']['level'],
                self.agent_status['needs']['hunger']
            )

    def _ui_log(self, text):
        if self.ui: self.ui.append_log(text)

    # Controls
    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def step_once(self):
        self._step_flag = True

    def set_cycle_sleep(self, sec: float):
        try:
            self.cycle_sleep = max(0.1, float(sec))
        except Exception:
            pass

    # OODA steps
    def observe(self, world_state):
        self._ui_status("Observing…")
        print("\n— 1. OBSERVING —")
        print(json.dumps(world_state, indent=2))
        self.current_world_state = world_state
        self._ui_vitals()
        return world_state

    def orient(self, world_state):
        self._ui_status("Orienting (Subconscious)…")
        print("\n— 2. ORIENTING —")
        sensory = world_state.get("sensory_events", [])
        query_text = " ".join([f"{e.get('type','')} of {e.get('object','')} which is {e.get('details','')}" for e in sensory if 'object' in e])
        if not query_text:
            print("No object-based sensory events for memory query.")
            self.last_resonant_memories = []
        else:
            try:
                vec = model.encode(query_text).tolist()
                res = index.query(vector=vec, top_k=3, include_metadata=True)
                self.last_resonant_memories = [m['metadata']['text'] for m in res.get('matches',[])]
                print(f"Resonant memories: {self.last_resonant_memories}")
            except Exception:
                self.last_resonant_memories = []
        payload = {
            "current_state": self.agent_status,
            "world_state": world_state,
            "resonant_memories": self.last_resonant_memories
        }
        try:
            r = requests.post(f"{PSYCHE_LLM_API_URL}/generate_impulse", json=payload)
            r.raise_for_status()
            impulses = r.json()
        except Exception as e:
            print(f"/generate_impulse error: {e}")
            impulses = None
        if impulses:
            self.ui and self.ui.set_subconscious(
                impulses.get("emotional_shift",{}),
                impulses.get("impulses",[]),
                self.last_resonant_memories
            )
        return impulses

    def imagine_and_reflect(self, initial_impulses, world):
        self._ui_status("Imagining & Reflecting…")
        print("\n— 2.5. IMAGINE & REFLECT —")
        hypothetical = []
        top = sorted(initial_impulses.get("impulses",[]), key=lambda x: x.get("urgency",0), reverse=True)[:3]
        for imp in top:
            if not isinstance(imp, dict):
                continue
            action = {"verb": imp.get("verb"), "target": imp.get("target")}
            try:
                resp = requests.post(f"{PSYCHE_LLM_API_URL}/imagine", json={"action": action})
                imagined = (resp.json() or {}).get("outcome", "I imagine nothing happens.")
            except Exception:
                imagined = "My imagination is fuzzy."
            sim = world.clone().process_action(action)
            hypothetical.append({
                "action": action,
                "imagined": imagined,
                "simulated": sim.get("reason")
            })
        self.last_hypothetical = hypothetical
        self.ui and self.ui.set_imagination(hypothetical)
        payload = {
            "current_state": self.agent_status,
            "hypothetical_outcomes": hypothetical,
            "recent_memories": self.recent_memories
        }
        try:
            r = requests.post(f"{PSYCHE_LLM_API_URL}/reflect", json=payload)
            r.raise_for_status()
            reflection = r.json() or {}
            print(f"Reflection: {reflection.get('reasoning')}")
            return reflection
        except Exception as e:
            print(f"/reflect error: {e}")
            return {"final_action":{"verb":"wait","target":"null"},"reasoning":"Mind is blank."}

    def decide(self, final_action, reasoning):
        self._ui_status("Deciding…")
        print("\n— 3. DECIDING —")
        print(f"Chosen: {final_action}")
        self.ui and self.ui.set_decision(final_action, reasoning)
        return final_action, reasoning

    def act(self, world, action, reasoning, world_state, impulses):
        self._ui_status("Acting…")
        print("\n— 4. ACTING —")
        result = world.process_action(action)
        print(f"Result: {result}")
        if result.get("state_change") and "hunger" in result["state_change"]:
            self.agent_status['needs']['hunger'] = max(0, self.agent_status['needs']['hunger'] + result['state_change']['hunger'])
        # Narrative memory
        sensed_objs = [e['object'] for e in world_state.get('sensory_events',[]) if 'object' in e]
        sensed_str = f"I sensed {', '.join(sensed_objs)}." if sensed_objs else "I sensed nothing unusual."
        decision_str = f"I decided to {action['verb']}" if action.get('target')=='null' else f"I decided to {action['verb']} the {action['target']}"
        reason = result.get('reason','it just happened.')
        event_desc = (
            f"I was in the {world.agent_location}. {sensed_str} My emotional state became {self.current_mood}. "
            f"{decision_str}. {'The result was: ' if result.get('success') else 'But it failed because '}"+reason
        )
        self.recent_memories.append(event_desc)
        if len(self.recent_memories) > 5: self.recent_memories.pop(0)
        # Store vector memory
        try:
            vec = model.encode(event_desc).tolist()
            index.upsert(vectors=[(str(self.memory_id_counter), vec, {"text":event_desc, "timestamp": time.time()})])
            self.memory_id_counter += 1
        except Exception as e:
            print(f"Pinecone upsert error: {e}")
        # --- Insights & snapshot ---
        triggers = [f"{e.get('object')} : {e.get('details')}" for e in world_state.get('sensory_events',[]) if 'object' in e]
        imps = impulses.get('impulses',[]) if impulses else []
        emotional_delta = (impulses or {}).get('emotional_shift',{})
        self.insight.add_cycle(action=action, success=bool(result.get('success')), impulses=imps, triggers=triggers, mood=self.agent_status['emotional_state']['mood'])
        kpis = self.insight.compute_kpis()
        causal = self.insight.causal_line(triggers=triggers, impulses=imps, action=action, imagined="; ", simulated=result.get('reason',''), emotional_delta=emotional_delta)
        cards = self.insight.cards(triggers=triggers, kpis=kpis, chosen=action, imagined="; ", simulated=result.get('reason',''), emotional_delta=emotional_delta)
        badges = self.insight.badges(kpis)
        threads = self.insight.threads()
        # Push to UI
        self.ui and self.ui.set_insights(badges=badges, cards=cards, causal_line=causal, threads=threads)
        # Log CSV with extended fields
        cycle_data = {
            "timestamp": time.time(),
            "cycle_num": self.cycle_counter,
            "experiment_tag": self.experiment_tag,
            "agent_id": self.agent_id,
            "world_time": world.world_time,
            "location": world.agent_location,
            "mood": self.current_mood,
            "mood_intensity": self.mood_intensity,
            "sensory_events": json.dumps(world_state.get('sensory_events', []), ensure_ascii=False),
            "resonant_memories": json.dumps(self.last_resonant_memories, ensure_ascii=False),
            "impulses": json.dumps(imps, ensure_ascii=False),
            "chosen_action": f"{action.get('verb')}_{action.get('target')}",
            "action_result": json.dumps(result, ensure_ascii=False),
            "imagined_outcomes": json.dumps([h.get("imagined","") for h in self.last_hypothetical], ensure_ascii=False),
            "simulated_outcomes": json.dumps([h.get("simulated","") for h in self.last_hypothetical], ensure_ascii=False),
            "emotional_delta": json.dumps(emotional_delta, ensure_ascii=False),
            "kpis": json.dumps(kpis, ensure_ascii=False),
            "snapshot": json.dumps({
                "triggers": triggers,
                "top_impulses": sorted(imps, key=lambda x: x.get('urgency',0), reverse=True)[:3],
                "chosen": action,
                "simulated": result.get('reason',''),
                "emotional_delta": emotional_delta,
                "kpis": kpis
            }, ensure_ascii=False)
        }
        self.log_cycle_data(cycle_data)
        self._ui_vitals()
        if self.ui:
            try:
                self.ui.update_kpis(kpis)
                self.ui.set_cycle(self.cycle_counter)
            except Exception:
                pass

    def run_loop(self):
        world = TextWorld()
        while self.is_running:
            if self.paused and not self._step_flag:
                time.sleep(0.1)
                continue
            self.cycle_counter += 1
            world.update()
            self.agent_status['needs']['hunger'] = min(1, self.agent_status['needs']['hunger'] + 0.005)
            ws = world.get_world_state()
            full = self.observe(ws)
            impulses = self.orient(full)
            if impulses:
                shift = impulses.get("emotional_shift", {})
                if shift:
                    mood = shift.get("mood")
                    if mood:
                        self.agent_status["emotional_state"]["mood"] = mood
                        self.current_mood = mood
                    d = shift.get("level_delta", 0)
                    lvl = self.agent_status["emotional_state"].get("level", 0.1)
                    lvl = max(0.0, min(1.0, lvl + d))
                    self.agent_status["emotional_state"]["level"] = lvl
                    self.mood_intensity = lvl

                reflection = self.imagine_and_reflect(impulses, world)
                final_action = reflection.get('final_action', {'verb':'wait','target':'null'})
                reasoning = reflection.get('reasoning','I am unsure.')
                emotional_shift = impulses.get('emotional_shift', {})
                if emotional_shift:
                    self.agent_status['emotional_state']['mood'] = emotional_shift.get('mood', self.current_mood)
                    new_level = self.agent_status['emotional_state']['level'] + emotional_shift.get('level_delta', 0)
                    self.agent_status['emotional_state']['level'] = max(0, min(1, new_level))
                self.current_mood = self.agent_status['emotional_state']['mood']
                self.mood_intensity = self.agent_status['emotional_state']['level']
                action, _ = self.decide(final_action, reasoning)
                self.act(world, action, reasoning, full, impulses)
            else:
                print("\nOrient failed or empty; waiting.")
                action = {"verb":"wait","target":"null"}
                self.act(world, action, "No impulses", full, {})
            print("\n— Cycle complete. Waiting … —")
            self._ui_status("Cycle complete. Waiting…")
            if self._step_flag:
                self._step_flag = False
                self.paused = True
            time.sleep(self.cycle_sleep)

# --------------------
# Stdout bridge → GUI
# --------------------
class TextRedirector:
    def __init__(self, widget):
        self.widget = widget

    def _append(self, s: str):
        self.widget.config(state="normal")
        self.widget.insert("end", s)
        self.widget.see("end")
        self.widget.config(state="disabled")

    def write(self, s: str):
        try:
            # Always update widgets on the Tk main thread
            self.widget.after(0, self._append, s)
        except Exception:
            pass

    def flush(self):  # needed by some streams
        pass

# --------------------
# Entrypoint
# --------------------
if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
            writer.writeheader()
        print(f"Created log file: {LOG_FILE}")

    pre_populate_foundational_memories()

    root = tk.Tk()
    ui_bus = UiBus(root)
    app_gui = PsycheMonitor(root, ui_bus)

    # Pump UI bus regularly
    def pump():
        ui_bus.pump()
        root.after(100, pump)
    root.after(100, pump)

    # Redirect stdout to GUI log
    sys.stdout = TextRedirector(app_gui.log_text)

    # Start cognitive loop
    adam_brain = CognitiveLoop(LOG_FILE, LOG_HEADERS, ui=app_gui)
    app_gui.set_brain(adam_brain)
    loop_thread = threading.Thread(target=adam_brain.run_loop, daemon=True)
    loop_thread.start()

    # Start Flask API (non-blocking)
    def run_flask():
        app.run(port=8080)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    print("— Psyche Monitor running. State API: http://127.0.0.1:8080/get_state —\n")
    root.mainloop()
