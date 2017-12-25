#Reading from 'p' is conflicted
from polyphony import module
from polyphony.io import Port


@module
class io_read_conflict03:
    def __init__(self):
        self.p = Port(int, 'in', protocol='valid')
        self.append_worker(self.w)
        self.append_worker(self.w)

    def w(self):
        data = self.p.rd()
        print(data)


m = io_read_conflict03()
