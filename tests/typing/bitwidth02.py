from polyphony import testbench
from polyphony.typing import Tuple, bit32, bit64


def _32to64(xs:Tuple[bit32]) -> bit64:
    tmp0:bit64 = xs[0]
    tmp1:bit64 = xs[1] << 32
    return tmp0 | tmp1


def bitwidth02(x, y) -> bit64:
    ret:bit64 = _32to64((x, y))
    return ret


@testbench
def test():
    assert 0x8765432112345678 == bitwidth02(0x12345678, 0x87654321)


test()
