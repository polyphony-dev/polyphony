import polyphony
from polyphony import testbench
from polyphony.typing import int8


print(polyphony.__version__)

class UserClass:
    def __init__(self, x):
        self.x = x  # #type: int8


def func(c:UserClass):
    return c.x * c.x


def typing06(x):
    c = UserClass(x)
    return func(c)


@testbench
def test():
    assert 1 == typing06(1)
    assert 4 == typing06(2)


test()