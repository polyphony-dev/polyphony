#Port 'p' is not used at all
from polyphony import module
from polyphony.io import Port


@module
class port_is_not_used02:
    def __init__(self):
        self.p = Port(bool, 'out')
        self.q = Port(bool, 'out')
        self.append_worker(self.w, self.p, self.q)

    def w(self, p, q):
        q.wr(1)


m = port_is_not_used02()
