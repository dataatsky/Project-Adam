import json
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from collections import deque
import logging


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
        ttk.Button(controls, text="Clear Filter", command=lambda: self._set_filter(None)).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Save Snapshot", command=self._on_save_snapshot).pack(side="left", padx=(6,0))
        ttk.Button(controls, text="Copy Metrics", command=self._on_copy_metrics).pack(side="left", padx=(6,0))
        ttk.Label(controls, text="Cycle sec:").pack(side="left", padx=(12, 4))
        self.speed = tk.DoubleVar(value=5.0)
        self.speed_scale = ttk.Scale(controls, from_=0.2, to=10.0, orient="horizontal", variable=self.speed, command=self._on_speed)
        self.speed_scale.pack(side="left", fill="x", expand=True)
        # Log level dropdown
        ttk.Label(controls, text="Log:").pack(side="left", padx=(12, 4))
        self.log_level = tk.StringVar(value=logging.getLevelName(logging.getLogger().level))
        self.log_level_cb = ttk.Combobox(controls, width=8, textvariable=self.log_level, values=["DEBUG","INFO","WARNING","ERROR","CRITICAL"], state="readonly")
        self.log_level_cb.bind("<<ComboboxSelected>>", lambda e: self._on_log_level())
        self.log_level_cb.pack(side="left")
        # Font scale
        ttk.Label(controls, text="Font:").pack(side="left", padx=(12, 4))
        self.font_scale = tk.DoubleVar(value=10.0)
        scale = ttk.Scale(controls, from_=8.0, to=16.0, orient="horizontal", variable=self.font_scale, command=lambda _=None: self._apply_font_scale())
        scale.pack(side="left", padx=(0,6))
        self.cycle_var = tk.StringVar(value="Cycle: 0")
        ttk.Label(controls, textvariable=self.cycle_var).pack(side="right")
        # Dark mode toggle
        self.dark_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Dark", variable=self.dark_mode, command=self._apply_dark).pack(side="right", padx=(0,6))

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
        self.kpi_vals = {}
        self.kpi_hist = {k: deque(maxlen=20) for k in ("frustration", "conflict", "novelty", "goal_progress", "loop_score")}
        for key in ("frustration", "conflict", "novelty", "goal_progress", "loop_score"):
            row = ttk.Frame(kpi)
            ttk.Label(row, text=f"{key}:").pack(side="left", padx=(0, 6))
            bar = ttk.Progressbar(row, orient="horizontal", mode="determinate", maximum=1.0, length=260)
            bar.pack(side="left", fill="x", expand=True)
            # sparkline canvas
            canvas = tk.Canvas(row, width=80, height=18, highlightthickness=0, bg=self.root.cget("background"))
            canvas.pack(side="left", padx=6)
            val = ttk.Label(row, text="0.00")
            val.pack(side="left", padx=8)
            row.pack(fill="x", pady=2)
            self.kpi_bars[key] = (bar, val, canvas)
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
        # Simple mode toggle
        self.simple_mode = tk.BooleanVar(value=False)
        sm = ttk.Checkbutton(mind, text="Simple mode", variable=self.simple_mode, command=self._apply_simple_mode)
        sm.pack(anchor="e")

        # Insights widgets
        top = ttk.Frame(self.tab_insights)
        top.pack(fill="x", padx=4, pady=4)
        self.causal_label = ttk.Label(top, text="Causal: —", anchor="w")
        self.causal_label.pack(fill="x")
        # Timeline strip canvas
        self.timeline = tk.Canvas(top, height=40, highlightthickness=0)
        self.timeline.pack(fill="x", pady=(2, 0))
        # Tooltip window for timeline hover
        self._tip = None

        badge_row = ttk.Frame(self.tab_insights)
        badge_row.pack(fill="x", padx=4, pady=(0, 4))
        self.badge_var = tk.StringVar(value="")
        self.badge_label = ttk.Label(badge_row, textvariable=self.badge_var, foreground="#933")
        self.badge_label.pack(anchor="w")

        # Optional per-target sparkline (shown when a filter is active)
        spark_row = ttk.Frame(self.tab_insights)
        spark_row.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Label(spark_row, text="Target trend:").pack(side="left")
        self.card_spark = tk.Canvas(spark_row, width=200, height=20, highlightthickness=0)
        self.card_spark.pack(side="left", padx=6)
        self.card_spark_row = spark_row
        # Hidden by default
        self.card_spark_row.pack_forget()

        self.cards_frame = ttk.Frame(self.tab_insights)
        self.cards_frame.pack(fill="both", expand=True, padx=6, pady=6)
        self.card_widgets = []
        # Use grid with equal-weight columns so all three cards get the same width
        for i in range(3):
            frame = ttk.Labelframe(self.cards_frame, text="Card", padding=8)
            text = ScrolledText(frame, wrap="word", height=7, state="disabled")
            text.pack(fill="both", expand=True)
            frame.grid(row=0, column=i, sticky="nsew", padx=4)
            self.cards_frame.grid_columnconfigure(i, weight=1, minsize=160)
            self.card_widgets.append((frame, text))
        self.cards_frame.grid_rowconfigure(0, weight=1)
        # cache for filter-aware re-rendering of cards
        self.last_cards = []

        # Right pane: Threads + Live Log
        threads_box = ttk.Labelframe(right, text="Storyline Threads", padding=10)
        right.add(threads_box, weight=1)
        # Include a hidden 'target' column to carry the canonical target key
        self.threads = ttk.Treeview(threads_box, columns=("story", "progress", "recent", "target"), show="headings", height=10)
        self.threads.heading("story", text="Storyline")
        self.threads.heading("progress", text="Progress")
        self.threads.heading("recent", text="Recent")
        # Do not create a heading for 'target' to keep it visually hidden
        self.threads.column("story", width=160)
        self.threads.column("progress", width=90, anchor="center")
        self.threads.column("recent", width=260)
        # Hide target column
        self.threads.column("target", width=0, stretch=False)
        self.threads.pack(fill="both", expand=True)
        self.threads.bind("<<TreeviewSelect>>", self._on_thread_select)

        log_box = ttk.Labelframe(right, text="Live Console Log", padding=6)
        # Controls for log search and autoscroll
        lrow = ttk.Frame(log_box)
        ttk.Label(lrow, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(lrow, textvariable=self.search_var, width=18)
        self.search_entry.pack(side="left", padx=4)
        ttk.Button(lrow, text="Find", command=self._on_search).pack(side="left")
        self.autoscroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(lrow, text="Autoscroll", variable=self.autoscroll, command=self._on_autoscroll).pack(side="right")
        lrow.pack(fill="x", pady=(0,4))

        self.log_text = ScrolledText(log_box, wrap="word", state="disabled", height=12)
        self.log_text.pack(fill="both", expand=True)
        right.add(log_box, weight=2)

        # Sub/Imag/Dec raw panes and filter state
        self.filter_target = None
        self.last_sub_payload = None
        self.last_imagination = None
        self.last_decision = None
        self.sub_text_cache = ""
        self.imag_text_cache = ""
        self.dec_text_cache = ""
        self.sub_text = ScrolledText(self.tab_sub, wrap="word", height=12, state="disabled")
        self.sub_text.pack(fill="both", expand=True)
        self.imag_text = ScrolledText(self.tab_imag, wrap="word", height=12, state="disabled")
        self.imag_text.pack(fill="both", expand=True)
        self.dec_text = ScrolledText(self.tab_dec, wrap="word", height=12, state="disabled")
        self.dec_text.pack(fill="both", expand=True)

        # Status bar
        self.status = ttk.Label(root, text="Initializing…", anchor="w", relief="sunken")
        self.status.pack(side="bottom", fill="x")

        # Load persisted UI state
        self._load_ui_prefs()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
        for key, widgets in self.kpi_bars.items():
            bar, label, canvas = widgets
            v = float(kpis.get(key, 0) or 0)
            v = max(0.0, min(1.0, v))
            prev = self.kpi_vals.get(key, None)
            # Update only if changed meaningfully
            if prev is None or abs(v - prev) > 0.001:
                bar["value"] = v
                delta = 0.0 if prev is None else v - prev
                label.config(text=f"{v:.2f} ({delta:+.2f})", foreground=self._kpi_color(v))
                self.kpi_vals[key] = v
                # update history and redraw sparkline
                self.kpi_hist[key].append(v)
                self._draw_sparkline(canvas, list(self.kpi_hist[key]))

    def update_kpis(self, kpis):
        self.ui_bus.post(self._kpis, kpis)

    def _subconscious(self, emotional_shift, impulses, resonant):
        self.last_sub_payload = {"emotional_shift": emotional_shift or {}, "impulses": impulses or [], "resonant_memories": resonant or []}
        payload = self._maybe_filter_sub(self.last_sub_payload)
        text = json.dumps(payload, indent=2)
        if text != self.sub_text_cache:
            self.sub_text_cache = text
            self.sub_text.config(state="normal")
            self.sub_text.delete("1.0", "end")
            self.sub_text.insert("end", text)
            self.sub_text.config(state="disabled")

    def set_subconscious(self, emotional_shift, impulses, resonant):
        self.ui_bus.post(self._subconscious, emotional_shift, impulses, resonant)

    def _imagination(self, hypothetical_outcomes):
        self.last_imagination = hypothetical_outcomes or []
        text = json.dumps(self._maybe_filter_imagination(self.last_imagination), indent=2)
        if text != self.imag_text_cache:
            self.imag_text_cache = text
            self.imag_text.config(state="normal")
            self.imag_text.delete("1.0", "end")
            self.imag_text.insert("end", text)
            self.imag_text.config(state="disabled")

    def set_imagination(self, hypothetical_outcomes):
        self.ui_bus.post(self._imagination, hypothetical_outcomes)

    def _decision(self, final_action, reasoning):
        self.last_decision = {"final_action": final_action, "reasoning": reasoning}
        text = json.dumps(self._maybe_filter_decision(self.last_decision), indent=2)
        if text != self.dec_text_cache:
            self.dec_text_cache = text
            self.dec_text.config(state="normal")
            self.dec_text.delete("1.0", "end")
            self.dec_text.insert("end", text)
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
        # If a filter target is active, adapt the cards content for clarity
        ft = (self.filter_target or "").lower()
        if ft:
            filtered = []
            for c in cards:
                title = c.get("title", "Card")
                body = str(c.get("body", ""))
                if title.lower() == "result":
                    # Build from imagination list for the filtered target
                    items = [x for x in (self.last_imagination or []) if str((x.get('action') or {}).get('target', '')).lower() == ft]
                    if items:
                        body = "; ".join([
                            f"{(it.get('action') or {}).get('verb','?')}→ {it.get('imagined','')} | {it.get('simulated','')}" for it in items
                        ])
                    else:
                        body = f"No imagined/simulated outcomes for '{self.filter_target}' this cycle."
                elif title.lower() == "why":
                    # Keep only the portion that references the target, otherwise keep as note
                    if ft not in body.lower():
                        body = f"Viewing storyline: '{self.filter_target}'. {body}"
                filtered.append({"title": title, "body": body})
            cards = filtered
        for (frame, text_widget), card in zip(self.card_widgets, cards):
            frame.config(text=card.get("title", "Card"))
            text_widget.config(state="normal")
            text_widget.delete("1.0", "end")
            text_widget.insert("end", card.get("body", ""))
            text_widget.config(state="disabled")

    def _causal(self, line):
        self.causal_label.config(text=f"Causal: {line}")

    def _threads(self, threads):
        # Diff update rows for performance
        existing = self.threads.get_children()
        for row in existing:
            self.threads.delete(row)
        for th in threads:
            prog = f"{int(th['progress'] * 100)}%"
            recent = "; ".join(th.get("recent", []))
            tgt = th.get("target", "")
            self.threads.insert("", "end", values=(th.get("name", "—"), prog, recent, tgt))

    def set_insights(self, *, badges, cards, causal_line, threads):
        # cache cards for later re-render when filter changes
        try:
            self.last_cards = cards or []
        except Exception:
            self.last_cards = []
        self.ui_bus.post(self._badges, badges)
        self.ui_bus.post(self._cards, cards)
        self.ui_bus.post(self._causal, causal_line)
        self.ui_bus.post(self._threads, threads)
        # update per-target sparkline if applicable
        try:
            self._update_card_spark()
        except Exception:
            pass
        # draw timeline soon after insight update
        try:
            self._draw_timeline()
        except Exception:
            pass

    # ---------- helpers ----------
    def _kpi_color(self, v: float) -> str:
        if v >= 0.6:
            return "#b00"
        if v >= 0.3:
            return "#b60"
        return "#070"

    def _draw_sparkline(self, canvas: tk.Canvas, values):
        canvas.delete("all")
        if not values:
            return
        w = int(canvas.cget("width"))
        h = int(canvas.cget("height"))
        n = max(2, len(values))
        step = w / (n - 1)
        pts = []
        for i, v in enumerate(values):
            x = i * step
            y = h - (h * max(0.0, min(1.0, float(v))))
            pts.append((x, y))
        # draw line
        for i in range(1, len(pts)):
            x1, y1 = pts[i-1]
            x2, y2 = pts[i]
            canvas.create_line(x1, y1, x2, y2, fill="#357", width=2)

    def _update_card_spark(self):
        tgt = (self.filter_target or "").lower()
        if not tgt or not self.brain or not getattr(self.brain, 'insight', None):
            # hide row when no filter
            try:
                self.card_spark_row.pack_forget()
            except Exception:
                pass
            return
        # Build binary success series for the selected target
        series = []
        try:
            for a in list(self.brain.insight.actions)[-30:]:
                if str(a.get('target','')).lower() == tgt:
                    series.append(1.0 if a.get('success') else 0.0)
        except Exception:
            series = []
        if not series:
            # still show, but empty with message
            try:
                self.card_spark_row.pack(fill="x", padx=6, pady=(0,4))
                self.card_spark.delete("all")
                self.card_spark.create_text(80, 10, text="No recent data", fill="#666")
            except Exception:
                pass
            return
        # Ensure visible
        try:
            self.card_spark_row.pack(fill="x", padx=6, pady=(0,4))
            # Normalize length to at least 2 points
            vals = series[-20:]
            self._draw_sparkline(self.card_spark, vals)
        except Exception:
            pass

    def _maybe_filter_sub(self, payload):
        tgt = self.filter_target
        if not tgt:
            return payload
        out = {"emotional_shift": payload.get("emotional_shift", {})}
        out["impulses"] = [i for i in payload.get("impulses", []) if str(i.get("target", "")).lower() == tgt]
        out["resonant_memories"] = [m for m in payload.get("resonant_memories", []) if tgt in str(m).lower()]
        return out

    def _maybe_filter_imagination(self, items):
        tgt = self.filter_target
        if not tgt:
            return items
        return [x for x in items if str((x.get('action') or {}).get('target', '')).lower() == tgt]

    def _maybe_filter_decision(self, payload):
        tgt = self.filter_target
        if not tgt:
            return payload
        act = (payload or {}).get('final_action') or {}
        if str(act.get('target', '')).lower() == tgt:
            return payload
        return {"final_action": act, "reasoning": payload.get('reasoning')}

    def _draw_timeline(self):
        try:
            # Ensure canvas exists
            if not hasattr(self, 'timeline'):
                return
            self.timeline.delete("all")
            if not self.brain or not getattr(self.brain, 'insight', None):
                return
            actions = list(self.brain.insight.actions)
            triggers = list(self.brain.insight.triggers)
            n = min(12, len(actions))
            if n == 0:
                return
            w = max(200, int(self.timeline.winfo_width() or 600))
            h = int(self.timeline.cget('height'))
            pad = 4
            box_w = max(40, (w - pad*(n+1)) // n)
            x = pad
            start = len(actions) - n
            for i in range(n):
                a = actions[start + i]
                trig = ", ".join((triggers[start + i] or [])[:1]) if start + i < len(triggers) else ''
                success = bool(a.get('success'))
                fill = '#5a5' if success else '#c55'
                rect = self.timeline.create_rectangle(x, 5, x+box_w, h-5, fill=fill, outline='')
                label = f"{a.get('verb','?')}:{a.get('target','?')}"
                self.timeline.create_text(x+box_w/2, h/2, text=label, fill='white')
                # Click -> update causal label
                def cb(evt, t=trig, l=label, s=success):
                    self.causal_label.config(text=f"Causal: {t} → {l} → {'ok' if s else 'fail'}")
                self.timeline.tag_bind(rect, '<Button-1>', cb)
                # Hover tooltip
                tip_text = f"{trig} → {label} → {'ok' if success else 'fail'}"
                self.timeline.tag_bind(rect, '<Enter>', lambda e, txt=tip_text: self._show_timeline_tip(e, txt))
                self.timeline.tag_bind(rect, '<Leave>', lambda e: self._hide_timeline_tip())
                self.timeline.tag_bind(rect, '<Motion>', lambda e, txt=tip_text: self._move_timeline_tip(e, txt))
                x += box_w + pad
        except Exception:
            pass

    # ---- timeline tooltip helpers ----
    def _ensure_tip(self):
        if self._tip is None:
            t = tk.Toplevel(self.root)
            t.overrideredirect(True)
            t.withdraw()
            lbl = tk.Label(t, text="", background="#333", foreground="#eee", padx=6, pady=2, relief="solid", borderwidth=1)
            lbl.pack()
            self._tip = (t, lbl)
        return self._tip

    def _show_timeline_tip(self, event, text: str):
        t, lbl = self._ensure_tip()
        lbl.config(text=text)
        x = event.x_root + 10
        y = event.y_root + 10
        t.geometry(f"+{x}+{y}")
        t.deiconify()

    def _move_timeline_tip(self, event, text: str):
        if self._tip is None:
            return
        t, lbl = self._tip
        lbl.config(text=text)
        x = event.x_root + 10
        y = event.y_root + 10
        t.geometry(f"+{x}+{y}")

    def _hide_timeline_tip(self):
        if self._tip is None:
            return
        t, _ = self._tip
        t.withdraw()

    def _apply_font_scale(self):
        try:
            size = int(float(self.font_scale.get()))
        except Exception:
            size = 10
        font = ("TkDefaultFont", size)
        for w in (self.sub_text, self.imag_text, self.dec_text, self.log_text):
            try:
                w.configure(font=font)
            except Exception:
                pass
        self._persist_ui_prefs()

    def _on_log_level(self):
        lvl = getattr(logging, self.log_level.get(), logging.INFO)
        logging.getLogger().setLevel(lvl)
        self._persist_ui_prefs()

    def _on_search(self):
        term = self.search_var.get()
        if not term:
            return
        try:
            self.log_text.tag_remove('search', '1.0', 'end')
            start = '1.0'
            while True:
                idx = self.log_text.search(term, start, nocase=True, stopindex='end')
                if not idx:
                    break
                lastidx = f"{idx}+{len(term)}c"
                self.log_text.tag_add('search', idx, lastidx)
                start = lastidx
            self.log_text.tag_config('search', background='yellow')
        except Exception:
            pass

    def _on_autoscroll(self):
        enabled = bool(self.autoscroll.get())
        # find TkTextHandler handler and toggle
        for h in logging.getLogger().handlers:
            if h.__class__.__name__ == 'TkTextHandler':
                try:
                    h.set_autoscroll(enabled)
                except Exception:
                    pass
        self._persist_ui_prefs()

    def _on_thread_select(self, _):
        # Placeholder: in future, could filter panes by selected thread
        sel = self.threads.focus()
        if not sel:
            return
        vals = self.threads.item(sel, 'values')
        story = vals[0] if vals else ''
        target = (vals[3] if len(vals) >= 4 else '').lower()
        self.status.config(text=f"Selected thread: {story}")
        # Highlight in log and apply precise target filter
        if story:
            self.search_var.set(story)
            self._on_search()
        self._set_filter(target or None)

    def _set_filter(self, target):
        self.filter_target = target
        # re-render current panes with filter applied
        try:
            if self.last_sub_payload is not None:
                self._subconscious(self.last_sub_payload.get('emotional_shift'),
                                   self.last_sub_payload.get('impulses'),
                                   self.last_sub_payload.get('resonant_memories'))
            if self.last_imagination is not None:
                self._imagination(self.last_imagination)
            if self.last_decision is not None:
                self._decision(self.last_decision.get('final_action'), self.last_decision.get('reasoning'))
            # re-render cards to respect filter
            if isinstance(self.last_cards, list) and self.last_cards:
                self._cards(self.last_cards)
            self._update_card_spark()
        except Exception:
            pass

    def _apply_simple_mode(self):
        simple = bool(self.simple_mode.get())
        if simple:
            try:
                self.nb.hide(self.tab_sub)
                self.nb.hide(self.tab_imag)
                self.nb.hide(self.tab_dec)
            except Exception:
                pass
        else:
            try:
                self.nb.add(self.tab_sub, text="Subconscious")
                self.nb.add(self.tab_imag, text="Imagination")
                self.nb.add(self.tab_dec, text="Decision")
            except Exception:
                pass
        self._persist_ui_prefs()

    def _on_save_snapshot(self):
        try:
            import time, json
            brain = getattr(self, 'brain', None)
            data = {
                'cycle': getattr(brain, 'cycle_counter', None),
                'status': getattr(brain, 'agent_status', {}),
                'kpis': brain.insight.compute_kpis() if getattr(brain, 'insight', None) else {},
                'last_hypothetical': getattr(brain, 'last_hypothetical', []),
            }
            path = f"snapshot_{int(time.time())}.json"
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.status.config(text=f"Saved snapshot to {path}")
        except Exception as e:
            self.status.config(text=f"Snapshot failed: {e}")

    def _on_copy_metrics(self):
        try:
            brain = getattr(self, 'brain', None)
            kpis = brain.insight.compute_kpis() if getattr(brain, 'insight', None) else {}
            txt = json.dumps(kpis, indent=2)
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
            self.status.config(text="KPIs copied to clipboard")
        except Exception as e:
            self.status.config(text=f"Copy failed: {e}")

    # ---- persist UI prefs ----
    def _prefs_path(self):
        import os
        return os.path.join(os.getcwd(), '.psyche_ui.json')

    def _persist_ui_prefs(self):
        try:
            import json
            prefs = {
                'geometry': self.root.geometry(),
                'font': float(self.font_scale.get()),
                'log_level': self.log_level.get(),
                'autoscroll': bool(self.autoscroll.get()),
                'simple_mode': bool(self.simple_mode.get()),
                'dark_mode': bool(self.dark_mode.get()),
            }
            with open(self._prefs_path(), 'w', encoding='utf-8') as f:
                json.dump(prefs, f)
        except Exception:
            pass

    def _load_ui_prefs(self):
        try:
            import json, os
            p = self._prefs_path()
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    prefs = json.load(f)
                self.root.geometry(prefs.get('geometry', self.root.geometry()))
                self.font_scale.set(float(prefs.get('font', 10.0)))
                self._apply_font_scale()
                lvl = prefs.get('log_level', 'INFO')
                self.log_level.set(lvl)
                self._on_log_level()
                self.autoscroll.set(bool(prefs.get('autoscroll', True)))
                self._on_autoscroll()
                self.simple_mode.set(bool(prefs.get('simple_mode', False)))
                self._apply_simple_mode()
                self.dark_mode.set(bool(prefs.get('dark_mode', False)))
                self._apply_dark()
        except Exception:
            pass

    def _on_close(self):
        self._persist_ui_prefs()
        try:
            self.root.destroy()
        except Exception:
            pass

    def _apply_dark(self):
        dark = bool(self.dark_mode.get())
        try:
            fg = '#e0e0e0' if dark else 'black'
            bg = '#1e1e1e' if dark else 'white'
            for w in (self.sub_text, self.imag_text, self.dec_text, self.log_text):
                w.config(fg=fg, bg=bg, insertbackground=fg)
        except Exception:
            pass
        self._persist_ui_prefs()

    # Brain wiring and control callbacks
    def set_brain(self, brain):
        self.brain = brain
        try:
            self.speed.set(getattr(brain, "cycle_sleep", 5.0))
        except Exception:
            pass
        # kick off periodic timeline refresh
        try:
            self.root.after(1000, self._draw_timeline)
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
