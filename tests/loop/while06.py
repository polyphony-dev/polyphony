from polyphony import testbench

def while06(x):
    i = 1
    j = 0
    while i: 
        if j == x:
            i = 0
        j += 1            
    return j

@testbench
def test():
    assert 1 == while06(0)
    assert 2 == while06(1)
    assert 3 == while06(2)

test()
