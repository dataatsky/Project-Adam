from queue import Queue, Empty
import tkinter as tk


class UiBus:
    """Thread-safe UI message bus for Tk main thread updates."""

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

