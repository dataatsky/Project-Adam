"""State API and the thread-safe UI log handler (no Tk display needed)."""
import logging

from api import add_metrics_route, create_app


class Brain:
    cycle_counter = 7
    current_world_state = {"agent_location": "kitchen", "relationships": {"neighbor": {"trust": 0.6}}}
    last_impulses = [{"verb": "eat"}]
    recent_memories = ["m1", "m2"]
    diary_entries = [{"text": "d1"}]
    insight = None
    agent_status = {"emotional_state": {"mood": "calm", "level": 0.2}, "needs": {"hunger": 0.4}, "goal": "Eat"}


def _client(brain):
    app = create_app(lambda: brain)
    add_metrics_route(app, lambda: brain)
    return app.test_client()


def test_state_and_metrics_share_one_shape():
    client = _client(Brain())
    state = client.get("/get_state").get_json()
    metrics = client.get("/metrics").get_json()
    assert state["current_goal"] == metrics["current_goal"] == "Eat"
    assert state["location"] == metrics["location"] == "kitchen"
    assert state["recent_memories"] == ["m1", "m2"] and "recent_memories" not in metrics


def test_metrics_failure_is_an_error_not_a_fake_reset(caplog):
    class Broken(Brain):
        @property
        def agent_status(self):
            raise KeyError("mood_intensity")

    with caplog.at_level(logging.WARNING):
        resp = _client(Broken()).get("/metrics")
    assert resp.status_code == 500 and "error" in resp.get_json()
    assert any("State serialization failed" in r.getMessage() for r in caplog.records)


def test_tk_log_handler_only_touches_widgets_through_the_bus():
    from ui.log_handler import TkTextHandler

    class Bus:
        def __init__(self):
            self.posted = []

        def post(self, fn, *args):
            self.posted.append((fn, args))

    class Widget:
        def __getattr__(self, name):
            raise AssertionError(f"widget.{name} called from the logging thread")

    bus = Bus()
    handler = TkTextHandler(Widget(), bus)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None))
    fn, args = bus.posted[0]
    assert fn == handler._append and args == ("hello\n",)


def test_console_trimming_keeps_the_newest_lines():
    from ui.psyche_monitor import trim_text_widget

    class FakeText:
        def __init__(self, n):
            self.lines = [f"line {i}" for i in range(1, n + 1)]

        def index(self, _):
            return f"{len(self.lines)}.0"

        def delete(self, start, end):
            upto = int(end.split(".")[0])  # delete lines [1, upto)
            self.lines = self.lines[upto - 1:]

    text = FakeText(12)
    trim_text_widget(text, max_lines=5)
    assert text.lines == [f"line {i}" for i in range(8, 13)]
