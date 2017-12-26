#Cannot use range() function outside of for statememt
from polyphony import testbench


def range01():
    return range(10)


@testbench
def test():
    range01()


test()