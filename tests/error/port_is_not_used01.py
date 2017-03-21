#Port 'p' is not used at all
from polyphony import module
from polyphony.io import Bit


@module
class port_is_not_used01:
    def __init__(self):
        self.p = Bit()
        self.q = Bit()
        self.append_worker(self.w)

    def w(self):
        self.q.wr(1)


m = port_is_not_used01()
