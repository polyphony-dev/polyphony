from polyphony import testbench

def rom04(data:list):
    sum = 0
    for d in data:
        sum += d
    return sum

@testbench
def test():
    assert 8 == rom04([1] * 8)
    assert 16 == rom04([2] * 8)
    assert 24 == rom04([3] * 8)
test()
