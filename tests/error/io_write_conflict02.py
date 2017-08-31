#Writing to 'p' is conflicted
from polyphony import module
from polyphony.io import Port


@module
class io_write_conflict02:
    def __init__(self):
        self.p = Port(bool, 'out')
        self.append_worker(self.w)
        self.append_worker(self.w)

    def w(self):
        self.p.wr(1)


m = io_write_conflict02()
