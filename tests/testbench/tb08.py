from polyphony import testbench

@testbench
def test():
    sum = 0
    for i in range(2, 5):
        sum += i-1
        print(sum)
    assert sum == 6
