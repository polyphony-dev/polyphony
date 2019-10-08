#missing_required_arg01() missing required argument 'x'
from polyphony import testbench


def missing_required_arg01(x):
    return x


@testbench
def test():
    missing_required_arg01()


test()
