from polyphony import module
from polyphony import testbench
#import sub4
from sub4 import sub4


@module
class import12:
    def __init__(self):
        self.sub4 = sub4()
        self.append_worker(self.w)

    def w(self):
        d = self.sub4.i.rd()
        self.sub4.o.wr(d)


@testbench
def test(m):
    m.sub4.i.wr(0)


m = import12()
test(m)
