from polyphony import testbench

def for12(s, e, step):
    sum = 0
    for i in range(s, e, step):
        sum += i
    return sum

@testbench
def test():
    assert 45 == for12(0, 10, 1)
    assert 20 == for12(0, 10, 2)
    # assert 55 == for12(10, 0, -1)
    # assert 45 == for12(9, -1, -1)
    # assert 25 == for12(9, -1, -2)
