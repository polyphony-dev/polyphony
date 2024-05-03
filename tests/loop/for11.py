from polyphony import testbench

def for11(x):
    data = [x, 2, 3, 4]
    sum = 0
    for d in data:
        sum += d
    return sum

@testbench
def test():
    assert 9 == for11(0)
    assert 14 == for11(5)
    assert 19 == for11(10)
