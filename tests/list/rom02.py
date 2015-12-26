from polyphony import testbench

def rom02(x):
    sum = 0
    a = 2
    rom = [a, a*2, a*3]*3
    for i in range(9):
        sum += rom[i]*x
    return sum

@testbench
def test():
    assert 0 == rom02(0)
    assert 36 == rom02(1)
    assert 72 == rom02(2)

test()
