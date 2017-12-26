__all__ = [
    'Port',
    'Queue',
]


class Port:
    def __init__(self, dtype:generic, direction:str, init=None, protocol:str='none') -> object:
        pass

    def rd(self) -> generic:
        pass

    @mutable
    def wr(self, v:generic) -> None:
        pass

    def __call__(self, v=None) -> generic:
        pass


class Queue:
    def __init__(self, dtype:generic, direction:str, maxsize:int=1) -> object:
        pass

    def rd(self) -> generic:
        pass

    def wr(self, v:generic) -> None:
        pass

    def __call__(self, v=None) -> generic:
        pass

    @predicate
    def empty(self) -> bool:
        pass

    @predicate
    def full(self) -> bool:
        pass
