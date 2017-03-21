#Cannot wait for the output port
from polyphony import module
from polyphony.io import Bit
from polyphony.timing import wait_rising


@module
class wait_output01:
    def __init__(self):
        self.p = Bit()
        self.append_worker(self.w, self.p)

    def w(self, p):
        p.wr(1)
        wait_rising(p)


m = wait_output01()