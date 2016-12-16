from polyphony import testbench

SIZE=256
class Stack:
    def __init__(self, size):
        self.mem = [None] * size
        self.idx = 0
        
    def push(self, x):
        self.mem[self.idx] = x
        self.idx += 1

    def pop(self):
        self.idx -= 1
        return self.mem[self.idx]

def stack_test():
    stack = Stack(SIZE)
    stack.push(0)
    stack.push(1)
    stack.push(2)
    stack.push(3)
    assert 3 == stack.pop()
    assert 2 == stack.pop()
    assert 1 == stack.pop()
    assert 0 == stack.pop()

@testbench
def test():
    stack_test()

test()
