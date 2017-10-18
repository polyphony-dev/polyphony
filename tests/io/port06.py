from polyphony import testbench, module, is_worker_running, rule
from polyphony.io import Port
from polyphony.timing import clksleep


@module
class Port06:
    def __init__(self):
        self.out1 = Port(int, 'out', init=0)
        self.out2 = Port(int, 'out', init=0)
        self.out3 = Port(int, 'out', init=0)
        self.append_worker(self.main, self.out1, self.out2, self.out3)

    def main(self, out1, out2, out3):
        i = 0
        while is_worker_running():
            out1.wr(i)
            out2.wr(i)
            out3.wr(i)
            i += 1


@testbench
def test(p06):
    for i in range(8):
        x1_1 = p06.out1.rd()
        x1_2 = p06.out2.rd()
        x1_3 = p06.out3.rd()
        x2_1 = p06.out1.rd()
        x2_2 = p06.out2.rd()
        x2_3 = p06.out3.rd()
        x3_1 = p06.out1.rd()
        x3_2 = p06.out2.rd()
        x3_3 = p06.out3.rd()
        x4_1 = p06.out1.rd()
        x4_2 = p06.out2.rd()
        x4_3 = p06.out3.rd()
        print(x1_1, x2_1, x3_1, x4_1)
        assert x1_1 == x1_2 == x1_3
        assert x2_1 == x2_2 == x2_3
        assert x3_1 == x3_2 == x3_3
        assert x4_1 == x4_2 == x4_3
        assert x1_1 <= x2_1 <= x3_1 <= x4_1
        assert x1_2 <= x2_2 <= x3_2 <= x4_2
        assert x1_3 <= x2_3 <= x3_3 <= x4_3
    clksleep(2)


p06 = Port06()
test(p06)
