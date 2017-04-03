from polyphony import testbench

@testbench
def test():
    sum = 0
    for i in range(4):
        sum += i
        print(sum)
    assert sum == 6

test()
