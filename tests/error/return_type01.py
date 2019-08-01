#Type of return value must be int, not bool
from polyphony import testbench


def return_type01(p):
    if p:
        return True
    else:
        return 1


@testbench
def test():
    return_type01(True)


test()
