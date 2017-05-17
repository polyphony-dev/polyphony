
@builtin
def print(*args) -> None:
    pass


@builtin
def range(stop:int) -> None:
    pass


@builtin
def len() -> uint:
    pass


@builtin
def _assert(expr:bool) -> None:
    pass


@builtin
@typeclass
class int:
    def __init__(self, i:int=0) -> int:
        pass


@builtin
@typeclass
class bool:
    def __init__(self, b:bool=0) -> bool:
        pass
