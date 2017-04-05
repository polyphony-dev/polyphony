from polyphony import preprocess as pre
from polyphony import testbench


value = 12345


@pre
def f():
    return value


def preprocess05():
    return f()


@testbench
def test():
    assert value == preprocess05()


test()
