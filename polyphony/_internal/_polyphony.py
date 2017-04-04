__version__ = '0.3.0'  # type: str
__all__ = [
    'testbench',
    'preprocess',
    'module',
    'is_worker_running',
]


@decorator
def testbench(func) -> None:
    pass


@decorator
def preprocess(func) -> None:
    pass


def is_worker_running() -> bool:
    pass


@decorator
def module() -> None:
    pass
