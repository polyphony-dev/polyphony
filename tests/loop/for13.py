from polyphony import testbench

def for13(x):
    sum = 0
    for d in [1+x, 3+x, 5+x, 7+x, 9+x]:
        sum += d
    return sum

@testbench
def test():
    assert 1+3+5+7+9 == for13(0)
    assert 1+3+5+7+9+10 == for13(2)
