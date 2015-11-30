from polyphony import testbench

def sysfunc02(x):
    print(x*2)
    return x

@testbench
def test():
    assert 0 == sysfunc02(0)
    assert 1 == sysfunc02(1)
    assert 2 == sysfunc02(2)

test()

