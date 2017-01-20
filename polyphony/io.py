__all__ = [
    'Bit',
    'Int',
]

class Bit:
    def __init__(self, init_v:int=0) -> object:
        self.__v = init_v

    def rd(self) -> int:
        return self.__v

    def wr(self, v):
        self.__v = v

    def __call__(self, v=None) -> int:
        if v:
            self.wr(v)
        else:
            return self.rd()

class Int:
    def __init__(self, width:int=32, init_v:int=0, protocol:int='none') -> object:
        self.__width = width
        self.__v = init_v
        self.__protocol = protocol
        if protocol == 'valid':
            self.valid = False
        elif protocol == 'ready_valid':
            self.ready = False
            self.valid = False

    def rd(self) -> int:
        return self.__v

    def wr(self, v):
        self.__v = v
        if self.__protocol == 'valid' or self.__protocol == 'ready_valid':
            self.valid = True

    def __call__(self, v=None) -> int:
        if v:
            self.wr(v)
        else:
            return self.rd()
        
