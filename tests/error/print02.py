#print() takes only scalar type (e.g. int, str, ...) argument
from polyphony import testbench
from polyphony import module
from polyphony.io import Queue


@module
class M:
    def __init__(self):
        self.in_q = Queue(int, 'in')
        self.append_worker(self.w)

    def w(self):
        self.func(self.in_q)

    def func(self, q):
        print(q)


@testbench
def test(m):
    print([1, 2, 3])


if __name__ == '__main__':
    m = M()
    test(m)
