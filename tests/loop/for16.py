from polyphony import testbench


def for16(start, stop, step):
    sum = 0
    for j in range(start, stop, step):
        sum1 = 0
        for i in range(0, stop):
            sum1 += i
            stop = 2
        step = 1
        sum += sum1
    print(sum)
    return sum


@testbench
def test():
    assert 0 == for16(0, 0, 1)
    assert 7 == for16(0, 4, 2)
    assert 47 == for16(3, 10, 3)
