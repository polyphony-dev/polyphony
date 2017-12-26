from polyphony import testbench
from polyphony.typing import List, bit8, bit16


def bitwidth01(a:bit16):
    buf:List[bit8] = [1, 2, 3, 4]
    buf[0] = a
    a = buf[0]
    return a


@testbench
def test():
    assert 0x34 == bitwidth01(0x1234)  # This should fail in Python interpreter


test()
