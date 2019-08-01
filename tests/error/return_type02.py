#Type of return value must be bool, not int
from polyphony import testbench


def return_type02(p):
    if p:
        return 1
    else:
        return True


@testbench
def test():
    return_type02(True)


test()
