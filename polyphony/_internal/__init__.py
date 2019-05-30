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
