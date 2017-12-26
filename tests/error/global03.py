#Writing to a global object is not allowed
from polyphony import testbench

ram = [0] * 100


class C:
    def __init__(self):
        self.mem = ram


def global03():
    c = C()
    c.mem[0] = 123


@testbench
def test():
    global03()


test()
