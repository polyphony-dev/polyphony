from polyphony import testbench, module, is_worker_running
from polyphony.io import Port
from polyphony.timing import clkfence, wait_value


@module
class Port03:
    def __init__(self):
        self.in0       = Port(int, 'in')
        self.in_valid  = Port(bool, 'in')
        self.out0      = Port(int, 'out')
        self.out_valid = Port(bool, 'out', init=False)
        self.start     = Port(bool, 'out', init=False)
        self.append_worker(self.main)

    def main(self):
        self.start(True)
        while is_worker_running():
            self.out_valid(False)
            wait_value(True, self.in_valid)

            i = self.in0()
            self.out0(i * i)
            clkfence()
            self.out_valid(True)
            break


@testbench
def test(p):
    wait_value(True, p.start)

    p.in0(2)
    p.in_valid(True)
    print('wait out_valid')

    wait_value(True, p.out_valid)
    assert p.out0() == 4
    clkfence()
    print(p.out0())


p = Port03()
test(p)
