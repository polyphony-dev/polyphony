import polyphony
from polyphony import testbench
from polyphony.typing import int4, int8


class UserClass:
    def __init__(self, x):
        self.x = x  # type: int8
        self.y: int8 = x + 1  # This is legal in only Python3.6 or later


def func(c:UserClass):
    return c.x * c.y


def typing06(x:int4):
    c = UserClass(x)
    return func(c)


@testbench
def test():
    assert 2 == typing06(1)
    assert 6 == typing06(2)


test()