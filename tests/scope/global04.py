from polyphony import testbench

g1 = (1111, 2222)
g2 = g1[0]
g3 = g1[1]

def global04():
    return g2 + g3

@testbench
def test():
    assert 3333 == global04()
