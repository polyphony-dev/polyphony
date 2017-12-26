#Using the variable 'i' is restricted by polyphony's name scope rule
from polyphony import testbench


def loop_var01():
    for i in range(10):
        pass
    return i


@testbench
def test():
    loop_var01()


test()
