
import json
import time
import csv
import os
import sys
import threading
from collections import deque, defaultdict

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from loop.cognitive_loop import CognitiveLoop
from ui.ui_bus import UiBus
from ui.psyche_monitor import PsycheMonitor
from ui.log_handler import TkTextHandler
from services.memory_store import MemoryStore
import config
from api import create_app
from services.psyche_client import PsycheClient
from constants import LOG_HEADERS

# --------------------
# Configuration
# --------------------
PSYCHE_LLM_API_URL = getattr(config, 'PSYCHE_LLM_API_URL', "http://127.0.0.1:5000/")
LOG_FILE = config.LOG_FILE

"""CSV headers moved to constants.LOG_HEADERS"""

# --------------------
# Vector memory now handled by services.MemoryStore
# --------------------

# --------------------
# Thread-safe UI bus (moved to ui/ui_bus.py)
# See: ui/ui_bus.py

"""InsightEngine moved to loop/insight_engine.py"""

# --------------------
# Tkinter UI
# --------------------
"""PsycheMonitor moved to ui/psyche_monitor.py"""

# --------------------
# Flask tiny API (optional external viewers)
# --------------------
# Flask state API moved to api.create_app

# --------------------
# Cognitive Loop
# --------------------
"""CognitiveLoop moved to loop/cognitive_loop.py"""

# --------------------
# Stdout bridge → GUI
# --------------------
"""TextRedirector moved to ui/text_redirector.py"""

# --------------------
# Entrypoint
# --------------------
if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
            writer.writeheader()
        print(f"Created log file: {LOG_FILE}")

    # Initialize memory store and foundational memories
    memory_store = MemoryStore(
        api_key=config.PINECONE_API_KEY,
        environment=config.PINECONE_ENVIRONMENT,
        index_name=config.PINECONE_INDEX_NAME,
        model_name=config.SENTENCE_MODEL,
    )
    memory_store.ensure_foundational_memories()
    psyche = PsycheClient(PSYCHE_LLM_API_URL)

    root = tk.Tk()
    ui_bus = UiBus(root)
    app_gui = PsycheMonitor(root, ui_bus)

    # Pump UI bus regularly
    def pump():
        ui_bus.pump()
        root.after(100, pump)
    root.after(100, pump)

    # Configure logging to GUI log
    import logging
    logging.basicConfig(level=getattr(config, 'LOG_LEVEL', 'INFO'), format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    tk_handler = TkTextHandler(app_gui.log_text)
    tk_handler.setLevel(getattr(config, 'LOG_LEVEL', 'INFO'))
    tk_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    logging.getLogger().addHandler(tk_handler)

    # Start cognitive loop
    adam_brain = CognitiveLoop(LOG_FILE, LOG_HEADERS, ui=app_gui, memory=memory_store, psyche=psyche)
    app_gui.set_brain(adam_brain)
    loop_thread = threading.Thread(target=adam_brain.run_loop, daemon=True)
    loop_thread.start()

    # Start Flask API (non-blocking)
    flask_app = create_app(lambda: adam_brain)
    def run_flask():
        flask_app.run(port=8080)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    print("— Psyche Monitor running. State API: http://127.0.0.1:8080/get_state —\n")
    root.mainloop()
