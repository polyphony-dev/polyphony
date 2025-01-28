from polyphony import testbench

def param01(x, y = 10, z = 20):
    return x + y + z

@testbench
def test():
    assert 3 == param01(0, 1, 2)
    assert 21 == param01(0, 1)
    assert 30 == param01(0)
