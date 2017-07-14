from polyphony import testbench

foo = 1


def f():
    def ff():
        print('ff.foo', foo)
        return foo == 2
    foo = 2
    return ff()


@testbench
def test():
    assert f() == True


test()
