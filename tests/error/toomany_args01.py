#toomany_args01() takes 1 positional arguments but 2 were given
from polyphony import testbench


def toomany_args01(x):
    return x


@testbench
def test():
    toomany_args01(1, 1)


test()
