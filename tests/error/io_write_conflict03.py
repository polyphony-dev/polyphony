#Writing to 'p' is conflicted
from polyphony import module
from polyphony.io import Port


@module
class io_write_conflict03:
    def __init__(self):
        p = Port(int)
        self.append_worker(self.w, p)
        self.append_worker(self.w, p)

    def w(self, p):
        p.wr(1)


m = io_write_conflict03()
