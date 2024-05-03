from polyphony import testbench

def special02(x):
    def inner(a):
        def inner2(b):
            return b
        def inner3(b):
            return b
        return inner2(a) + inner3(0)

    return inner(x) + inner(1)

@testbench
def test():
    assert 2 == special02(1)
