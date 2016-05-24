from polyphony import testbench

gs = [1111, 2222, 3333]

def global05():
    sum = 0
    for g in gs:
        sum += g
    return sum

@testbench
def test():
    assert 6666 == global05()

test()
