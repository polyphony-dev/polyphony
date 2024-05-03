from polyphony import testbench

def rom04(d):
    data = [d] * 8
    sum = 0
    for d in data:
        sum += d
    return sum

@testbench
def test():
    assert 8 == rom04(1)
    assert 16 == rom04(2)
    assert 24 == rom04(3)
