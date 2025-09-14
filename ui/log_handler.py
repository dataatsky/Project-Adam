import logging


class TkTextHandler(logging.Handler):
    """Logging handler that writes records into a Tkinter Text-like widget."""

    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.autoscroll = True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record) + "\n"
            # schedule appending on the Tk main thread
            self.widget.after(0, self._append, msg)
        except Exception:
            pass

    def _append(self, s: str):
        try:
            self.widget.config(state="normal")
            self.widget.insert("end", s)
            if self.autoscroll:
                self.widget.see("end")
            self.widget.config(state="disabled")
        except Exception:
            pass

    def set_autoscroll(self, enabled: bool):
        self.autoscroll = bool(enabled)
