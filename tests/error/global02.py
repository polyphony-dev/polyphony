#A global instance is not supported
from polyphony import testbench


class C:
    def __init__(self, v):
        self.v = v

c = C(100)


def global02():
    return c.v


@testbench
def test():
    global02()


test()
