#Writing to a global object is not allowed
from polyphony import testbench

ram = [0] * 100


def global01():
    ram[0] = 123


@testbench
def test():
    global01()


test()
