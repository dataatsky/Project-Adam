class TextRedirector:
    """Bridge stdout/stderr to a Tkinter ScrolledText in a thread-safe way."""

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

