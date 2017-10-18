#Reading from 'p' is conflicted
from polyphony import module
from polyphony.io import Queue


@module
class io_read_conflict02:
    def __init__(self):
        self.p = Queue(int, 'in')
        self.append_worker(self.w)
        self.append_worker(self.w)

    def w(self):
        data = self.p.rd()
        print(data)


m = io_read_conflict02()
