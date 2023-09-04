from polyphony import testbench

data = (2, 4, 6, 8, 10)

def rom05(i):
    return data[i]

@testbench
def test():
    assert 2 == rom05(0)
    assert 4 == rom05(1)
    assert 6 == rom05(2)    
test()
