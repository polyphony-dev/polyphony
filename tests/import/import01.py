import polyphony
import polyphony.io
import polyphony.timing
import polyphony.typing


@polyphony.testbench
def test():
    assert polyphony.__name__ == 'polyphony'
    assert polyphony.io.__name__ == 'polyphony.io'
    assert polyphony.timing.__name__ == 'polyphony.timing'
    assert polyphony.typing.__name__ == 'polyphony.typing'


test()
