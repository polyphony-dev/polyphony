from polyphony import testbench

def expr09(a, b):
    return a ^ b

@testbench
def test():
    assert 1 == expr09(0b1000, 0b1001)
    assert 3 == expr09(0b1000, 0b1011)
    assert 1 == expr09(0b1010, 0b1011)
