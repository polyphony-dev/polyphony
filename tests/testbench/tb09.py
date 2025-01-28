from polyphony import testbench

@testbench
def test():
    xs = [10, 20, 30, 40]
    sum = 0
    for x in xs:
        sum += x
        print(sum)
    assert sum == 100
