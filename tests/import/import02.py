import polyphony
from polyphony import io as io_
from polyphony import timing as ti_
from polyphony import typing as ty_


@polyphony.testbench
def test():
    assert io_.__name__ == 'polyphony.io'
    assert ti_.__name__ == 'polyphony.timing'
    assert ty_.__name__ == 'polyphony.typing'


test()
