from polyphony import testbench

foo = 1


class C:
    foo = 2

    def __init__(self):
        print('foo', foo)
        a = foo == 1
        print('self.foo', self.foo)
        b = self.foo == 2
        print('C.foo', C.foo)
        c = C.foo == 2
        self.result = a and b and c


def f():
    c = C()
    return c.result


@testbench
def test():
    assert f() == True
