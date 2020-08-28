#Port object must created in the constructor of the module class
from polyphony import testbench
from polyphony.io import Port


class C:
    def __init__(self):
        self.p = Port(bool, 'in')


def io02():
    c = C()
    c.p.wr(0)


@testbench
def test():
    io02()


test()
