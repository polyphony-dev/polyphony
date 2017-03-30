#The expression of assert always evaluates to False
from polyphony import testbench
from polyphony import __version__


@testbench
def test():
    assert __version__ == ''


test()