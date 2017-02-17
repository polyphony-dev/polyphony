from polyphony import testbench

foo = 1


def f():
    def ff():
        print('ff.foo', foo)
        assert foo == 2
    foo = 2
    ff()
    return 0


@testbench
def test():
    f()


test()
