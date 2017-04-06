from polyphony import pure
from polyphony import testbench


value = 12345


@pure
def f():
    return value


def pure05():
    return f()


@testbench
def test():
    assert value == pure05()


test()
