from polyphony import module
from polyphony import testbench
from polyphony import is_worker_running
from polyphony.timing import clksleep


@module
class ModuleTest02:
    def __init__(self, mparam):
        self.append_worker(self.worker, 1 * mparam)
        self.append_worker(self.worker, 2 * mparam)
        self.append_worker(self.worker, 3 * mparam)

    def worker(self, param):
        while is_worker_running():
            print('worker', param)


@testbench
def test(m):
    clksleep(10)


m = ModuleTest02(10)
test(m)
