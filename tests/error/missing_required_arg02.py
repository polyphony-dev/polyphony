#polyphony.timing.clksleep() missing required argument
from polyphony import testbench
from polyphony.timing import clksleep


def missing_required_arg02():
    clksleep()


@testbench
def test():
    missing_required_arg02()


test()
