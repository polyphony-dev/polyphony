#The port class constructor accepts only constants
from polyphony import module
from polyphony.io import Port


@module
class io03:
    def __init__(self, x):
        d = [x] * 10
        self.p = Port(bool, 'in', init=d[0])
        self.append_worker(self.w)

    def w(self):
        d = self.p.rd()


m = io03(1)
