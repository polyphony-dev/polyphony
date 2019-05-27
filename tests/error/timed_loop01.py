#While statement is not allowed in 'timed' scheduling
from polyphony import testbench
from polyphony.timing import timed


@timed
@testbench
def test():
    while True:
        pass


test()
