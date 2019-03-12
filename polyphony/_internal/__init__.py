__version__ = '0.3.4'  # type: str


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
    def __init__(self) -> object:
        self.v = 0  # meta: symbol=register
