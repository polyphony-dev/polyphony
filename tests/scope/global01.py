from polyphony import testbench

g = 1111
g = 2222

def global01():
    return g

@testbench
def test():
    assert 2222 == global01()
