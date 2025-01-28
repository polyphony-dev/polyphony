from polyphony import testbench

SIZE=256
class FIFO:
    def __init__(self, size):
        self.mem = [None] * size
        self.ridx = 0
        self.widx = 0

    def push(self, x):
        self.mem[self.widx] = x
        self.widx += 1
        if self.widx == len(self.mem):
            self.widx = 0
    def pop(self):
        x = self.mem[self.ridx]
        self.ridx += 1
        if self.ridx == len(self.mem):
            self.ridx = 0
        return x

def fifo():
    fifo = FIFO(SIZE)
    fifo2 = FIFO(SIZE*2)
    fifo.push(0)
    fifo.push(1)
    fifo.push(2)
    fifo.push(3)

    fifo2.push(5)
    fifo2.push(6)
    fifo2.push(7)
    fifo2.push(8)

    assert 0 == fifo.pop()
    assert 1 == fifo.pop()
    assert 2 == fifo.pop()
    assert 3 == fifo.pop()

@testbench
def test():
    fifo()
