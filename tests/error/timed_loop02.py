#Only polyphony.timing.clkrange() can be used at for-in statement in 'timed' scheduling
from polyphony import testbench
from polyphony.timing import timed


@timed
@testbench
def test():
    for i in range(10):
        pass


test()
