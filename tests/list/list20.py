from polyphony import testbench

def list20(x):
    if x == 0:
        d = [x + 1, 1]
    elif x == 1:
        d = [x + 2, 2]
    else:
        d = [x + 3, 3]
    return d[0]

@testbench
def test():
    assert 1 == list20(0)
    assert 3 == list20(1)
    assert 5 == list20(2)

test()
