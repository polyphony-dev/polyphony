from polyphony import testbench

def list_multiplier(x):
    l = [1, 2, 3] * x
    return 0

@testbench
def test():
    list_multiplier(5)
test()

