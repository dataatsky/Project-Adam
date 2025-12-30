import pytest
from sensory import SensoryCortex

def test_transduce_cold():
    cortex = SensoryCortex()
    narrative, delta = cortex.transduce(5.0, 0.1, 0.8, "day")
    assert "bone-chilling" in narrative
    assert delta < 0  # Should be negative mood impact

def test_transduce_hot():
    cortex = SensoryCortex()
    narrative, delta = cortex.transduce(35.0, 0.1, 0.8, "day")
    assert "suffocating" in narrative
    assert delta < 0

def test_transduce_noise():
    cortex = SensoryCortex()
    narrative, delta = cortex.transduce(20.0, 0.9, 0.8, "day")
    assert "deafening" in narrative
    assert delta < -0.1

def test_transduce_silence():
    cortex = SensoryCortex()
    narrative, delta = cortex.transduce(20.0, 0.05, 0.8, "day")
    assert "silence" in narrative
    assert delta > 0 # Calm

def test_transduce_filth():
    cortex = SensoryCortex()
    narrative, delta = cortex.transduce(20.0, 0.1, 0.1, "day")
    assert "Filth" in narrative
    assert delta < -0.1
