from polyphony import testbench, module, is_worker_running
from polyphony.io import Int, Bit
from polyphony.timing import clkfence, wait_rising, wait_value


@module
class Port01:
    def __init__(self):
        self.in0 = Int(8)
        self.out0 = Int(8)
        self.out_valid = Bit(0)
        self.in_valid = Bit(0)
        self.start = Bit(0)
        self.append_worker(self.main)

    def main(self):
        self.start(1)
        while is_worker_running():
            self.out_valid(0)
            # We have to wait the input data ...
            wait_value(1, self.in_valid)

            i = self.in0()
            self.out0(i * i)
            # clkfence() function guarantees that the writing to out_valid is executed in a next cycle
            clkfence()
            self.out_valid(1)
            break


@testbench
def test(p01):
    # wait to ensure the test starts after the worker is running
    wait_value(1, p01.start)

    p01.in0(2)
    p01.in_valid(1)
    print('wait_rising out_valid')

    wait_rising(p01.out_valid)
    assert p01.out0() == 4
    clkfence()
    print(p01.out0())


p01 = Port01()
test(p01)
