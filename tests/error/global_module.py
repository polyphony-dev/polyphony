#Invalid access to a module class object
from polyphony import module
from polyphony.io import Queue


@module
class M:
    def __init__(self):
        self.in_q = Queue(int, 'in')
        self.append_worker(self.w)

    def w(self):
        m.in_q.rd()


m = M()
