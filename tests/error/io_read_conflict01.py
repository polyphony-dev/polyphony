#Reading from 'p' is conflicted
from polyphony import module
from polyphony.io import Queue


@module
class io_read_conflict01:
    def __init__(self):
        p = Queue(int, 'in')
        self.append_worker(self.w, p)
        self.append_worker(self.w, p)

    def w(self, p):
        data = p.rd()
        print(data)


m = io_read_conflict01()
