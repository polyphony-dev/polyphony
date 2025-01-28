from polyphony import testbench

g1 = 1111
g2 = 1111 + g1
g1 = g2 + g2

def global03():
    def inner1():
        return g1
    def inner2():
        return g2

    return inner1() + inner2()

@testbench
def test():
    assert 6666 == global03()
