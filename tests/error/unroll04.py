#Cannot use polyphony.unroll() function outside of for statememt
from polyphony import testbench
from polyphony import unroll


def unroll04():
    u = unroll([1, 2, 3], 4)


@testbench
def test():
    unroll04()


test()