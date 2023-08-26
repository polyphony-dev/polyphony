__version__:str = '0.3.6'
__python__:bool = False


@decorator
def testbench(func) -> None:
    pass


@decorator
def pure(func) -> None:
    pass


@builtin
def is_worker_running() -> bool:
    pass


@decorator
def module() -> None:
    pass


@decorator
def rule(kwargs) -> None:
    pass


@builtin
def unroll(seq, factor='full') -> list:
    pass


@builtin
def pipelined(seq, ii=-1) -> list:
    pass


@unflatten
class Reg:
    @inlinelib
    def __init__(self, initv=0) -> object:
        self.v = initv  # meta: symbol=register


class Net:
    def __init__(self, dtype:generic, exp=None) -> object:
        pass

    def assign(self, exp:function) -> None:
        pass

    def rd(self) -> generic:
        pass


from . import timing
from . import typing

@timing.timed
@module
@inlinelib
class Channel:
    def __init__(self, dtype:generic, capacity=4):
        self.din:dtype = 0
        self.write = False
        self.read = False
        self.length = capacity
        self.mem:typing.List[dtype][capacity] = [0] * capacity
        self.wp = 0
        self.rp = 0
        self.count = 0
        self.append_worker(self.write_worker, loop=True)
        self.append_worker(self.main_worker, loop=True)

    def put(self, v):
        timing.wait_until(lambda:not self.full() and not self.will_full())
        self.write = True
        self.din = v
        timing.clkfence()
        self.write = False

    def get(self):
        timing.wait_until(lambda:not self.empty() and not self.will_empty())
        self.read = True
        timing.clkfence()
        self.read = False
        return self.mem[self.rp]

    def full(self):
        return self.count >= self.length

    def empty(self):
        return self.count == 0

    def will_full(self):
        return self.write and not self.read and self.count == self.length - 1

    def will_empty(self):
        return self.read and not self.write and self.count == 1

    def write_worker(self):
        if self.write:
            self.mem[self.wp] = self.din

    def _inc_wp(self):
        self.wp = 0 if self.wp == self.length - 1 else self.wp + 1

    def _inc_rp(self):
        self.rp = 0 if self.rp == self.length - 1 else self.rp + 1

    def main_worker(self):
        if self.write and self.read:
            if self.count == self.length:
                self.count = self.count - 1
                self._inc_rp()
            elif self.count == 0:
                self.count = self.count + 1
                self._inc_wp()
            else:
                self.count = self.count
                self._inc_wp()
                self._inc_rp()
        elif self.write:
            if self.count < self.length:
                self.count = self.count + 1
                self._inc_wp()
        elif self.read:
            if self.count > 0:
                self.count = self.count - 1
                self._inc_rp()
