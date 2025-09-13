import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class PsycheMonitor:
    def __init__(self, root: tk.Tk, ui_bus):
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
        self.mood_text.pack(side="left", padx=(6, 12))
        ttk.Label(row1, text="Intensity:").pack(side="left")
        self.mood_bar = ttk.Progressbar(row1, orient="horizontal", mode="determinate", maximum=1.0, length=260)
        self.mood_bar.pack(side="left", fill="x", expand=True)
        row1.pack(fill="x", pady=4)

        row2 = ttk.Frame(vitals)
        ttk.Label(row2, text="Hunger:").pack(side="left")
        self.hunger_bar = ttk.Progressbar(row2, orient="horizontal", mode="determinate", maximum=1.0, length=320)
        self.hunger_bar.pack(side="left", fill="x", expand=True, padx=(8, 0))
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
        badge_row.pack(fill="x", padx=4, pady=(0, 4))
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
        self.threads = ttk.Treeview(threads_box, columns=("story", "progress", "recent"), show="headings", height=10)
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
            frame.config(text=card.get("title", "Card"))
            text_widget.config(state="normal")
            text_widget.delete("1.0", "end")
            text_widget.insert("end", card.get("body", ""))
            text_widget.config(state="disabled")

    def _causal(self, line):
        self.causal_label.config(text=f"Causal: {line}")

    def _threads(self, threads):
        for row in self.threads.get_children():
            self.threads.delete(row)
        for th in threads:
            prog = f"{int(th['progress'] * 100)}%"
            recent = "; ".join(th.get("recent", []))
            self.threads.insert("", "end", values=(th.get("name", "—"), prog, recent))

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

