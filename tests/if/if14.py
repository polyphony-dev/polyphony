from polyphony import testbench

def if14(x):
    i = 1
    if x < 10:
        if x ==  0:
            pass
        elif x == 1:
            pass
        i = 2
    else:
        pass
      
    return i


@testbench
def test():
    assert 2 == if14(0)
    assert 2 == if14(1)
    assert 2 == if14(2)
    assert 1 == if14(10)

test()
