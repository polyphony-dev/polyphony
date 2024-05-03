from polyphony import testbench


class C:
    data = (1, 2, 3)

    def func(self, x):
        return func_a(x)


def func_a(x):
    return C.data[x]


def classfield04(x):
    c = C()
    return c.func(x)


@testbench
def test():
    assert 1 == classfield04(0)
    assert 2 == classfield04(1)
    assert 3 == classfield04(2)
