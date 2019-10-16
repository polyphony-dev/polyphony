#Invalid access to a module class object
from polyphony import module
from polyphony.io import Port


@module
class M:
    def __init__(self):
        self.i = Port(int, 'in')
        self.append_worker(self.w)

    def w(self):
        m.i.rd()


m = M()
