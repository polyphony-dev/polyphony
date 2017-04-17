#'C' has been redefined
from polyphony import testbench


class C:
    pass


class C:
    pass


@testbench
def test():
    pass


test()
