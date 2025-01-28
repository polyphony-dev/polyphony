from polyphony import module, testbench
from polyphony.timing import timed, clktime, wait_value, wait_until, clksleep
from polyphony.io import Port


@module
class AGeneric:
    def __init__(self, dtype:type):
        self.v:dtype = 0

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


@module
class module_param01:
    def __init__(self):
        self.port = Port(bool, 'out', init=False)
        self.generic = AGeneric(bool)
        self.append_worker(self.setter)
        self.append_worker(self.getter)

    @timed
    def setter(self):
        clksleep(10)
        self.generic.set(True)

    def func(self, v):
        return v

    def getter(self):
        wait_until(lambda:self.generic.get() == True)
        v = self.func(self.generic.get())
        self.port.wr(v)

# @timed
@testbench
def test():
    c = module_param01()
    wait_value(True, c.port)
    assert clktime() == 12

