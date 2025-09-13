import csv
import os
import sys
import threading
import time
import argparse

import config
from services.memory_store import MemoryStore
from services.psyche_client import PsycheClient
from loop.cognitive_loop import CognitiveLoop
from api import create_app
from constants import LOG_HEADERS


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Run Adam's cognitive loop")
    parser.add_argument("--headless", action="store_true", help="Run without Tkinter UI")
    parser.add_argument("--api-port", type=int, default=8080, help="Flask API port (default: 8080)")
    args = parser.parse_args(argv)
    log_file = config.LOG_FILE
    if not os.path.exists(log_file):
        with open(log_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
            writer.writeheader()
        print(f"Created log file: {log_file}")

    # Initialize memory store and foundational memories
    memory_store = MemoryStore(
        api_key=config.PINECONE_API_KEY,
        environment=config.PINECONE_ENVIRONMENT,
        index_name=config.PINECONE_INDEX_NAME,
        model_name=config.SENTENCE_MODEL,
    )
    memory_store.ensure_foundational_memories()
    psyche = PsycheClient(getattr(config, 'PSYCHE_LLM_API_URL', 'http://127.0.0.1:5000/'))

    # Headless or UI mode
    if args.headless:
        ui = None
        brain = CognitiveLoop(config.LOG_FILE, LOG_HEADERS, ui=ui, memory=memory_store, psyche=psyche)
        loop_thread = threading.Thread(target=brain.run_loop, daemon=True)
        loop_thread.start()

        # Start Flask API (non-blocking)
        flask_app = create_app(lambda: brain)
        def run_flask():
            flask_app.run(port=args.api_port)
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        print(f"— Headless mode running. State API: http://127.0.0.1:{args.api_port}/get_state —")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Exiting headless mode…")
    else:
        # Defer Tk-related imports to avoid loading Tk in headless
        import tkinter as tk
        from ui.ui_bus import UiBus
        from ui.psyche_monitor import PsycheMonitor
        from ui.text_redirector import TextRedirector

        # Tk + UI
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
        brain = CognitiveLoop(config.LOG_FILE, LOG_HEADERS, ui=app_gui, memory=memory_store, psyche=psyche)
        app_gui.set_brain(brain)
        loop_thread = threading.Thread(target=brain.run_loop, daemon=True)
        loop_thread.start()

        # Start Flask API (non-blocking)
        flask_app = create_app(lambda: brain)
        def run_flask():
            flask_app.run(port=args.api_port)
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        print(f"— Psyche Monitor running. State API: http://127.0.0.1:{args.api_port}/get_state —\n")
        root.mainloop()


if __name__ == "__main__":
    main()
