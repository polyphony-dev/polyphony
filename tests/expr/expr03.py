from polyphony import testbench

def expr03(a):
    return -a*1 + a*-1

@testbench
def test():
    assert 0 == expr03(0)
    assert -2 == expr03(1)
    assert -4 == expr03(2)

test()
