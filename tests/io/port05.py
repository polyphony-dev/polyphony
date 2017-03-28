from polyphony import testbench, module, is_worker_running
from polyphony.io import Port
from polyphony.timing import clkfence, wait_value


@module
class Port05:
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
def test(p05):
    wait_value(True, p05.start)

    p05.in0(2)
    p05.in_valid(True)
    print('wait out_valid')

    wait_value(True, p05.out_valid)
    assert p05.out0() == 4
    clkfence()
    print(p05.out0())


p05 = Port05()
test(p05)
