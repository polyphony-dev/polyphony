from polyphony import testbench

def expr04(a):
    return +a & ~0xff00

@testbench
def test():
    assert 0 == expr04(0)
    assert 0 == expr04(0x1100)
    assert 0x20 == expr04(0x2020)
    assert 0x300030 == expr04(0x303030)

test()
