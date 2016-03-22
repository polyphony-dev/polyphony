from polyphony import testbench

def list20(x):
    if x:
        d = [x+1]
    else:
        d = [x]
    return d[0]

@testbench
def test():
    assert 0 == list20(0)
    assert 2 == list20(1)    
test()
