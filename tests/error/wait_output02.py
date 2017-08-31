#Port direction of 'p' is conflicted
from polyphony import module
from polyphony.io import Port
from polyphony.timing import wait_rising


@module
class wait_output02:
    def __init__(self):
        self.p = Port(bool, 'in')
        self.append_worker(self.w, self.p)

    def w(self, p):
        wait_rising(p)
        p.wr(1)


m = wait_output02()