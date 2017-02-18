from polyphony import module
from polyphony import testbench
from polyphony.timing import clksleep


@module
class WorkerTest01:
    def __init__(self, mparam):
        self.append_worker(self.worker0, 1 * mparam)
        self.append_worker(self.worker1, 2 * mparam)

    def worker0(self, param):
        print('worker0', param)

    def worker1(self, param):
        for i in range(10):
            print('worker1', param)


@testbench
def test0(wtest):
    clksleep(10)


@testbench
def test1(wtest):
    clksleep(30)


w0 = WorkerTest01(10)
w1 = WorkerTest01(20)
test0(w0)
test1(w1)
