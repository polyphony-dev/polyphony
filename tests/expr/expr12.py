from polyphony import testbench

def expr12(a, b):
    return a >> b
    
@testbench
def test():
    assert 1 == expr12(0b0001, 0)
    assert 0 == expr12(0b0001, 1)
    assert 1 == expr12(0b1111, 3)

test()
