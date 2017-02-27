__all__ = [
    'Bit',
    'Int',
    'Uint'
]


class _DataPort:
    def __init__(self, init:int=0, width:int=1, protocol:int='none') -> object:
        pass

    def rd(self) -> int:
        pass

    @mutable
    def wr(self, v:int) -> None:
        pass

    def __call__(self, v=None) -> int:
        pass


class Bit(_DataPort):
    def __init__(self, init:int=0, width:int=1, protocol:int='none') -> object:
        pass


class Int(_DataPort):
    def __init__(self, width:int=32, init:int=0, protocol:int='none') -> object:
        pass


class Uint(_DataPort):
    def __init__(self, width:uint=32, init:int=0, protocol:int='none') -> object:
        pass

    def rd(self) -> uint:
        pass

    @mutable
    def wr(self, v:uint) -> None:
        pass


class Queue:
    def __init__(self, width:int=32, maxsize:int=0) -> object:
        pass

    def rd(self) -> int:
        pass

    def wr(self, v) -> None:
        pass

    def __call__(self, v=None) -> int:
        pass

    def empty(self) -> bool:
        pass

    def full(self) -> bool:
        pass
