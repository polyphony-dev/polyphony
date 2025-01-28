from polyphony import testbench

g = 1111
g = 2222
g = 3333

def global02():
    def inner():
        return g
    return inner()

@testbench
def test():
    assert 3333 == global02()
