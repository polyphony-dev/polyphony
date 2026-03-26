from unittest.mock import MagicMock
from polyphony.simulator import Simulator


class TestSimulatorContextManager:
    def test_enter_calls_begin(self):
        """__enter__ calls begin() and returns self."""
        sim = Simulator.__new__(Simulator)
        sim.begin = MagicMock()
        result = sim.__enter__()
        sim.begin.assert_called_once()
        assert result is sim

    def test_exit_calls_end(self):
        """__exit__ calls end()."""
        sim = Simulator.__new__(Simulator)
        sim.end = MagicMock()
        sim.__exit__(None, None, None)
        sim.end.assert_called_once()

    def test_exit_calls_end_on_exception(self):
        """__exit__ calls end() even when exception occurred."""
        sim = Simulator.__new__(Simulator)
        sim.end = MagicMock()
        sim.__exit__(ValueError, ValueError("test"), None)
        sim.end.assert_called_once()
