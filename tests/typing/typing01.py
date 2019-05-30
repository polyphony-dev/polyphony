import polyphony
from polyphony import testbench, __python__
from polyphony.typing import bit, bit2


def typing01_a(a:bit, b:polyphony.typing.bit) -> bit2:
    return a + b


def typing01_b(a:bit, b:polyphony.typing.bit) -> bit:
    return a + b


@testbench
def test():
    assert 0 == typing01_a(0, 0)
    assert 1 == typing01_a(0, 1)
    assert 1 == typing01_a(1, 0)
    assert 2 == typing01_a(1, 1)

    assert 0 == typing01_b(0, 0)
    assert 1 == typing01_b(0, 1)
    assert 1 == typing01_b(1, 0)
    if not __python__:
        assert 0 == typing01_b(1, 1)  # This should fail in Python interpreter


test()
