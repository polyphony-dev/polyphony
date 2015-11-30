from polyphony import testbench

def expr02(a):
    return -a+1-1

@testbench
def test():
    assert 0 == expr02(0)
    assert -1 == expr02(1)
    assert -2 == expr02(2)

test()
