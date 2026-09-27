import logging


class TkTextHandler(logging.Handler):
    """Logging handler that writes records into a Tkinter Text-like widget.

    Records arrive from any thread (cognitive loop, Flask); they are handed to the
    thread-safe UiBus, which applies them on the Tk main thread.
    """

    def __init__(self, widget, ui_bus, max_lines: int = 5000):
        super().__init__()
        self.widget = widget
        self.ui_bus = ui_bus
        self.max_lines = max_lines
        self.autoscroll = True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.ui_bus.post(self._append, self.format(record) + "\n")
        except Exception:
            self.handleError(record)

    def _append(self, s: str):
        from ui.psyche_monitor import trim_text_widget

        self.widget.config(state="normal")
        self.widget.insert("end", s)
        trim_text_widget(self.widget, self.max_lines)
        if self.autoscroll:
            self.widget.see("end")
        self.widget.config(state="disabled")

    def set_autoscroll(self, enabled: bool):
        self.autoscroll = bool(enabled)
