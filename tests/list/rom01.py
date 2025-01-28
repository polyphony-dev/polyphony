from polyphony import testbench

def rom01(x):
    sum = 0
    rom = [1, 3, 5]*3
    for i in range(9):
        sum += rom[i]*x
    return sum

@testbench
def test():
    assert 0 == rom01(0)
    assert 27 == rom01(1)
    assert 54 == rom01(2)
