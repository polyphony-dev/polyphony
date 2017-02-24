from polyphony import testbench, module
from polyphony.io import Int


@module
class Protocol02:
    def __init__(self):
        self.i = Int(8, 0, 'ready_valid')
        self.o = Int(8, 0, 'ready_valid')
        self.append_worker(self.main)

    def main(self):
        t = self.i.rd()
        self.o.wr(t * t)


@testbench
def test(p02):
    p02.i.wr(2)
    assert p02.o() == 4


p02 = Protocol02()
test(p02)
