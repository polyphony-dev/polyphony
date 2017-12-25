#Nothing is generated because any module or function didn't called in global scope.
from polyphony import module
from polyphony.io import Port


@module
class Sub:
    def __init__(self):
        self.p = Port(int, 'in')
        self.append_worker(self.w)

    def w(self):
        x = self.p.rd()