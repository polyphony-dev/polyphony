#Writing to 'p' is conflicted
from polyphony import module
from polyphony.io import Port


@module
class io_write_conflict01:
    def __init__(self):
        self.p = Port(bool, 'out')
        self.append_worker(self.w, self.p)
        self.append_worker(self.w, self.p)

    def w(self, p):
        p.wr(1)


m = io_write_conflict01()
