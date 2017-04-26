from polyphony import testbench
import sub3


def func1(x):
    return x + 10


def func2(x):
    return x + 20


def func3(x):
    return sub3.func1(x) + 30


class SubC:
    VALUE1 = 5678
    VALUE2 = (5, 6, 7, 8)

    def __init__(self, x):
        self.x = x * x * x

    def v(self):
        return self.x


@testbench
def sub_test():
    assert 10 == func1(0)


sub_test()
