from polyphony import testbench
from polyphony.typing import bit64, bit128


def bitwidth04(hi:bit64, lo:bit64) -> bit128:
    result:bit128 = hi
    result = result << 64
    result = result | lo
    return result


@testbench
def test():
    result = bitwidth04(0x00000001, 0x00000002)
    expected:bit128 = (0x00000001 << 64) | 0x00000002
    assert result == expected
