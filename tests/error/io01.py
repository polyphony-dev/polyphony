#Port object must created in the constructor of the module class
from polyphony import testbench
from polyphony.io import Port


def io01():
    p = Port(bool, 'in')
    p.wr(0)


@testbench
def test():
    io01()


test()
