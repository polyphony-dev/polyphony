from polyphony import testbench
from polyphony.typing import int16


def annotated_func(a: int16, b: int16):
    return a + b


@testbench
def test():
    assert annotated_func(1, 2) == 3
