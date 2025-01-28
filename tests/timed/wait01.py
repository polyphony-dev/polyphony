from polyphony import module, testbench
from polyphony.timing import timed, clkfence, clktime, wait_rising
from polyphony.io import Port


@module
class wait01:
    def __init__(self):
        self.i = Port(int, 'in')
        self.i_ready = Port(bool, 'out', False)
        self.i_valid = Port(bool, 'in')
        self.o = Port(int, 'out', -1)
        self.t1 = 0
        self.t2 = 0
        self.append_worker(self.untimed_worker, loop=True)

    @timed
    def timed_func(self):
        self.i_ready.wr(True)
        clkfence()

        self.t1 = clktime()
        # Rule 1) If the condition is already met,
        #         the next statements of wait funtion will continue to execute without clkfence
        # Rule 2) If the condition is not met, it will enter a wait state.
        #         (No statements other than clkfence are executed while waiting)
        # Rule 3) In the wait state, if the condition is met,
        #         Execute the next statements of wait funtion in the same clock cycle
        wait_rising(self.i_valid)
        self.t2 = clktime()

        self.i_ready.wr(False)
        data = self.i.rd()
        clkfence()
        print(self.t1, self.t2, clktime())

        self.o.wr(data)
        #clkfence()

    def untimed_worker(self):
        self.timed_func()


@testbench
@timed
def test():
    m = wait01()
    wait_rising(m.i_ready)
    clkfence()
    clkfence()

    m.i.wr(111)
    m.i_valid.wr(True)
    # we can get the value written after 3 clock cycles
    assert -1 == m.o.rd()
    clkfence()

    m.i_valid.wr(False)
    assert -1 == m.o.rd()
    clkfence()

    assert -1 == m.o.rd()
    #assert False == m.i_ready.rd()
    clkfence()

    m.i.wr(222)
    m.i_valid.wr(True)  # Make 'i_valid' preceded to 'i_ready'
    assert 111 == m.o.rd()
    clkfence()

    #m.i_valid.wr(False)
    assert 111 == m.o.rd()
    clkfence()

    assert 111 == m.o.rd()
    clkfence()
    assert 222 == m.o.rd()
    clkfence()
    assert 222 == m.o.rd()
