from polyphony import testbench

foo = 1


class C:
    foo = 2
    def __init__(self):
        print('foo', foo)
        assert foo == 1
        print('self.foo', self.foo)
        assert self.foo == 2
        print('C.foo', C.foo)
        assert C.foo == 2


def f():
    c = C()
    return 0


@testbench
def test():
    f()


test()

