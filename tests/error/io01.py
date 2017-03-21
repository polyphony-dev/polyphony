#Port object must created in the constructor of the module class
from polyphony import testbench
from polyphony.io import Bit


def io01():
    p = Bit()
    p.wr(0)


@testbench
def test():
    io01()


test()
