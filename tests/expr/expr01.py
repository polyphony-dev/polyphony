from polyphony import testbench

def expr01(a):
    return a+1+1

@testbench
def test():
    assert 2 == expr01(0)
    assert 3 == expr01(1)
    assert 4 == expr01(2)

test()
