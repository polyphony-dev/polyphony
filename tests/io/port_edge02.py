from polyphony import module, testbench
from polyphony.io import Port
from polyphony.timing import timed, clkfence, clkrange, wait_rising, wait_falling, clktime
from polyphony.typing import bit


@module
class edge02:
    def __init__(self):
        self.sub_clk = Port(bit, 'out', 0)
        self.sub_clk_posedge = Port(bit, 'out', 0)
        self.sub_clk_posedge.assign(lambda:self.sub_clk.edge(0, 1))
        self.append_worker(self.clk_divider)

    @timed
    def clk_divider(self):
        for i in clkrange():
            self.sub_clk.wr(1)
            clkfence()
            self.sub_clk.wr(0)


m = edge02()


@timed
@testbench
def test(m):
    for i in clkrange(15):
        wait_rising(m.sub_clk)
        print(clktime())
        assert clktime() % 2 == 0
        assert m.sub_clk_posedge.rd() == True
    for i in clkrange(15):
        wait_falling(m.sub_clk)
        print(clktime())
        assert clktime() % 2 == 1
        assert m.sub_clk_posedge.rd() == False
    assert clktime() == 62


test(m)
