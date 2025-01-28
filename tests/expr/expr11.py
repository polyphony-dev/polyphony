from polyphony import testbench

def expr11(a, b):
    return a << b

@testbench
def test():
    assert 1 == expr11(0b0001, 0)
    assert 2 == expr11(0b0001, 1)
    assert 24 == expr11(0b0011, 3)
