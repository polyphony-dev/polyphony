from polyphony import testbench

def if13(x):
    i = 1
    if x < 10:
        if x == 0:
            pass
        elif x == 1:
            i = 2
    else:
        i = 3
      
    return i


@testbench
def test():
    assert 1 == if13(0)
    assert 2 == if13(1)
    assert 1 == if13(2)
    assert 3 == if13(10)

test()
