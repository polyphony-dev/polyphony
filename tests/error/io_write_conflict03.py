#Writing to 'p' is conflicted
from polyphony import module
from polyphony.io import Port


@module
class io_write_conflict03:
    def __init__(self):
        self.p = Port(int, 'out')
        self.append_worker(w, self.p)
        self.append_worker(w, self.p)


def w(p):
    p.wr(1)


m = io_write_conflict03()
