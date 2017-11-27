#'polyphony.pipelined' is incompatible type as a parameter of polyphony.pipelined()
from polyphony import testbench
from polyphony import pipelined


def pipeline05():
    s = 0
    for i in pipelined(pipelined(range(10))):
        if s > 10:
            break
        s += i
    return s


@testbench
def test():
    pipeline05()


test()
