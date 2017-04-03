#Port direction of 'p' is conflicted
from polyphony import module
from polyphony.io import Port


@module
class io_conflict01:
    def __init__(self):
        self.p = Port(bool)
        self.append_worker(self.w0, self.p)
        self.append_worker(self.w1, self.p)

    def w0(self, p):
        data = p.rd()

    def w1(self, p):
        p.wr(1)


m = io_conflict01()
