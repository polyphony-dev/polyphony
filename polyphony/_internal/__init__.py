__version__ = '0.3.6'  # type: str
__python__ = False


@decorator
def testbench(func) -> None:
    pass


@decorator
def pure(func) -> None:
    pass


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


class Channel:
    def __init__(self, dtype:generic, maxsize:int=1) -> object:
        pass

    def get(self) -> generic:
        pass

    def put(self, v:generic) -> None:
        pass

    @predicate
    def empty(self) -> bool:
        pass

    @predicate
    def full(self) -> bool:
        pass
