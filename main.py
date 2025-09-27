import csv
import os
import sys
import threading
import time
import argparse
import logging

import config
from services.memory_store import MemoryStore
from services.psyche_client import PsycheClient
from loop.cognitive_loop import CognitiveLoop
from api import create_app, add_metrics_route
from constants import LOG_HEADERS
from adamsec import get_runtime


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Run Adam's cognitive loop")
    parser.add_argument("--headless", action="store_true", help="Run without Tkinter UI")
    parser.add_argument("--api-port", type=int, default=8080, help="Flask API port (default: 8080)")
    parser.add_argument("--cycles", type=int, default=0, help="Headless: stop after N cycles (0 = run forever)")
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
        cloud=getattr(config, 'PINECONE_CLOUD', None),
        region=getattr(config, 'PINECONE_REGION', None),
        backend=getattr(config, 'MEMORY_BACKEND', 'chroma'),
        chroma_path=getattr(config, 'CHROMA_PATH', './chroma'),
        chroma_collection=getattr(config, 'CHROMA_COLLECTION', config.PINECONE_INDEX_NAME or 'adam-memory'),
        batch_size=getattr(config, 'MEMORY_UPSERT_BATCH', 5),
    )
    memory_store.ensure_foundational_memories()
    psyche = PsycheClient(
        getattr(config, 'PSYCHE_LLM_API_URL', 'http://127.0.0.1:5000/'),
        timeout=getattr(config, 'PSYCHE_TIMEOUT', 30),
        retries=getattr(config, 'PSYCHE_RETRIES', 2),
        backoff=getattr(config, 'PSYCHE_BACKOFF', 0.5),
    )

    # Configure logging level
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    # Headless or UI mode
    if args.headless:
        ui = None
        brain = CognitiveLoop(config.LOG_FILE, LOG_HEADERS, ui=ui, memory=memory_store, psyche=psyche)
        security = get_runtime(brain, psyche)
        if getattr(security, "enabled", False):
            brain.attach_security(security)
        loop_thread = threading.Thread(target=brain.run_loop, daemon=True)
        loop_thread.start()

        # Start Flask API (non-blocking)
        flask_app = create_app(lambda: brain)
        add_metrics_route(flask_app, lambda: brain)
        def run_flask():
            flask_app.run(port=args.api_port)
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
        logging.getLogger(__name__).info(f"Headless mode running. State API: http://127.0.0.1:{args.api_port}/get_state, Metrics: /metrics")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                if args.cycles and getattr(brain, "cycle_counter", 0) >= args.cycles:
                    logging.getLogger(__name__).info(f"Reached target cycles={args.cycles}. Exiting…")
                    break
                time.sleep(0.25)
        except KeyboardInterrupt:
            logging.getLogger(__name__).info("Exiting headless mode…")
    else:
        # Defer Tk-related imports to avoid loading Tk in headless
        import tkinter as tk
        from ui.ui_bus import UiBus
        from ui.psyche_monitor import PsycheMonitor
        from ui.log_handler import TkTextHandler

        # Tk + UI
        root = tk.Tk()
        ui_bus = UiBus(root)
        app_gui = PsycheMonitor(root, ui_bus)

        # Pump UI bus regularly
        def pump():
            ui_bus.pump()
            root.after(100, pump)
        root.after(100, pump)

        # Configure logging to a Tk text widget via handler
        logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
        tk_handler = TkTextHandler(app_gui.log_text)
        tk_handler.setLevel(log_level)
        tk_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
        logging.getLogger().addHandler(tk_handler)

        # Start cognitive loop
        brain = CognitiveLoop(config.LOG_FILE, LOG_HEADERS, ui=app_gui, memory=memory_store, psyche=psyche)
        security = get_runtime(brain, psyche)
        if getattr(security, "enabled", False):
            brain.attach_security(security)
        app_gui.set_brain(brain)
        loop_thread = threading.Thread(target=brain.run_loop, daemon=True)
        loop_thread.start()

        # Start Flask API (non-blocking)
        flask_app = create_app(lambda: brain)
        add_metrics_route(flask_app, lambda: brain)
        def run_flask():
            flask_app.run(port=args.api_port)
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        logging.getLogger(__name__).info(f"Psyche Monitor running. State API: http://127.0.0.1:{args.api_port}/get_state, Metrics: /metrics")
        root.mainloop()


if __name__ == "__main__":
    main()
