import abc


class GenericMeta(abc.ABCMeta):
    def __getitem__(self, i):
        cls = self.__class__(self.__name__, self.__bases__, dict(self.__dict__))
        cls.width = i
        return cls


class Bits(object, metaclass=GenericMeta):
    def __init__(self, init=0):
        mask = (1 << self.width) - 1
        self.value = init & mask

    def __getitem__(self, i):
        if isinstance(i, int):
            assert i >= 0
            assert i < self.width
            value = (self.value >> i) & 1
            cls = self.__class__[1]
            return cls(value)
        elif isinstance(i, slice):
            assert i.start >= 0 and i.start < i.stop
            assert i.stop <= self.width
            assert i.step is None
            w = i.stop - i.start
            mask = (1 << w) - 1
            value = (self.value >> i.start) & mask
            cls = self.__class__[w]
            return cls(value)
        else:
            raise TypeError(f'Bits indices must be int or slice, not {type(i).__name__}')

    def __int__(self):
        return self.value

    def __str__(self):
        fmt = f'#0{self.width+2}b'
        return format(self.value, fmt)

    def __len__(self):
        return self.width

    def __add__(self, rhs):
        cls = self.__class__[self.width + rhs.width]
        value = (rhs.value << self.width) | self.value
        return cls(value)

    def __and__(self, rhs):
        if isinstance(rhs, int):
            assert rhs >= 0
            value = self.value & rhs
            cls = self.__class__[self.width]
            return cls(value)
        elif isinstance(rhs, self.__class__):
            value = self.value & rhs.value
            cls = self.__class__[self.width]
            return cls(value)
        else:
            raise TypeError(f'unsupported operand type for &: {type(rhs).__name__}')

    def __or__(self, rhs):
        if isinstance(rhs, int):
            assert rhs >= 0
            value = self.value | rhs
            cls = self.__class__[self.width]
            return cls(value)
        elif isinstance(rhs, self.__class__):
            value = self.value | rhs.value
            cls = self.__class__[self.width]
            return cls(value)
        else:
            raise TypeError(f'unsupported operand type for |: {type(rhs).__name__}')

    def __xor__(self, rhs):
        if isinstance(rhs, int):
            assert rhs >= 0
            value = self.value ^ rhs
            cls = self.__class__[self.width]
            return cls(value)
        elif isinstance(rhs, self.__class__):
            value = self.value ^ rhs.value
            cls = self.__class__[self.width]
            return cls(value)
        else:
            raise TypeError(f'unsupported operand type for ^: {type(rhs).__name__}')


if __name__ == '__main__':
    bit4 = Bits[4]
    v = bit4(0b01100110)
    print(v)
    print(v[0], v[1], v[2], v[3])
    print(v[0] + v[1] + v[2] + v[3])
    print(int(v))
    print(len(v))

    v_ = v & 0b0101
    print(v_)
    v_ = v & bit4(0b0101)
    print(v_)

    v_ = v | 0b0101
    print(v_)
    v_ = v | bit4(0b0101)
    print(v_)

    v_ = v ^ 0b0101
    print(v_)
    v_ = v ^ bit4(0b0101)
    print(v_)

    b2 = v[2:4] + v[0:2]
    print(b2)
    print(v[1:3])
    print(v[2:4])
