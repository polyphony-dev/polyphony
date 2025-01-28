@builtin
class Port:
    def __init__(self, dtype:type, direction:str, init=None,
                 rewritable:bool=False) -> object:
        pass

    def rd(self) -> object:
        pass

    @mutable
    def wr(self, v) -> None:
        pass

    def assign(self, fn:function) -> None:
        pass

    def edge(self, old, new) -> bool:
        pass


from . import timing


@builtin
def flipped(obj:object) -> object:
    pass


@builtin
def connect(p0:object, p1:object) -> None:
    pass


@builtin
def thru(parent:object, child:object) -> None:
    pass
