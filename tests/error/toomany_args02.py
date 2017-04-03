#toomany_args02() takes 2 positional arguments but 3 were given
from polyphony import testbench


def toomany_args02(x=0, y=0):
    return x + y


@testbench
def test():
    toomany_args02(1, 2, 3)


test()
