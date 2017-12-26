#Type of return value must be bool, not int
from polyphony import testbench


def return_type(p):
    if p:
        return True
    else:
        return 1


@testbench
def test():
    return_type(True)


test()
