'''
The class defined in polyphony.io provides the function for passing data between the module's I / O ports or workers.
The following classes are provided. In Polyphony these classes are called Port classes.

    - polyphony.io.Port
    - polyphony.io.Queue
'''
from . import base
from . import timing


_io_enabled = False


def _enable():
    global _io_enabled
    _io_enabled = True


def _disable():
    global _io_enabled
    _io_enabled = False


class PolyphonyException(Exception):
    pass


class PolyphonyIOException(PolyphonyException):
    pass


def _is_called_from_owner():
    # TODO:
    return False


class Port(object):
    '''
    Port class is used to an I/O port of a module class.
    It can read or write a value of immutable type.

    *Parameters:*
        dtype : an immutable type class
            A data type of the port.
            which of the below can be used.

                - int
                - bool
                - polyphony.typing.bit
                - polyphony.typing.int<n>
                - polyphony.typing.uint<n>

        direction : {'in', 'out'}
            A direction of the port.

    *Examples:*
    ::

        @module
        class M:
            def __init__(self):
                self.din = Port(int16, 'in')
                self.dout = Port(int32, 'out')
    '''
    instances = []
    In = 0
    Out = ~In

    def __init__(self, dtype, direction, init=None, **kwargs):
        self._dtype = dtype
        self.__pytype = base._pytype_from_dtype(dtype)
        self._direction = direction
        self._exp = None
        if init:
            self._init = init
        else:
            self._init = base._pyvalue_from_dtype(dtype)
        self._reset()
        Port.instances.append(self)
        self._rewritable = False
        if 'rewritable' in kwargs:
            self._rewritable = kwargs['rewritable']

    def rd(self):
        '''
        Read the current value from the port.
        '''
        if self._direction == 'out':
            if _is_called_from_owner():
                raise RuntimeError("Reading from 'out' Port is not allowed")
        return self.__v

    def wr(self, v):
        '''
        Write the value to the port.
        '''
        if self._exp:
            raise RuntimeError("Cannot write to the assigned port")
        if not isinstance(v, self.__pytype):
            raise TypeError(f"Incompatible value type, got {type(v)} expected {self._dtype}")
        if self._direction == 'in':
            if _is_called_from_owner():
                raise RuntimeError("Writing to 'in' Port is not allowed")
        if not self._rewritable and self.__written:
            raise RuntimeError("It is not allowed to write to the port more than once in the same clock cycle")
        self.__new_v = v
        self.__written = True

    def edge(self, old_v, new_v):
        if self._exp:
            return False
        return self.__old_v == old_v and self.__v == new_v

    def assign(self, exp):
        self._exp = exp

    def __lshift__(self, other):
        if self._direction == 'in' and other._direction == 'out':
            self._exp = lambda:other.rd()
        else:
            raise RuntimeError("The operator '<<' must be used like 'in << out'")

    def __rshift__(self, other):
        if self._direction == 'out' and other._direction == 'in':
            other._exp = lambda:self.rd()
        else:
            raise RuntimeError("The operator '>>' must be used like 'out >> in'")

    def _reset(self):
        self.__v = self._init
        self.__new_v = self._init
        self.__old_v = self._init
        self.__written = False
        self._changed = False

    def _update(self):
        if self._exp:
            return
        if self.__v != self.__new_v:
            self._changed = True
        else:
            self._changed = False
        self.__old_v = self.__v
        self.__v = self.__new_v
        self.__written = False

    def _update_assigned(self):
        if not self._exp:
            return
        self.__new_v = self._exp()
        if self.__v != self.__new_v:
            changed = True
        else:
            changed = False
        self.__v = self.__new_v
        self._changed |= changed
        return changed

    def _clear_change_flag(self):
        self._changed = False


class In(Port):
    def __init__(self, dtype):
        super().__init__(dtype, 'in')


class Out(Port):
    def __init__(self, dtype, init=None):
        super().__init__(dtype, 'out', init)


@timing.timed
class Handshake:
    def __init__(self, dtype, direction, init=None):
        self.data = Port(dtype, direction, init)
        if direction == 'in':
            self.ready = Port(bool, 'out', 0, rewritable=True)
            self.valid = Port(bool, 'in', rewritable=True)
        else:
            self.ready = Port(bool, 'in', rewritable=True)
            self.valid = Port(bool, 'out', 0, rewritable=True)

    def rd(self):
        '''
        Read the current value from the port.
        '''
        self.ready.wr(True)
        timing.clkfence()
        while self.valid.rd() is not True:
            timing.clkfence()
        self.ready.wr(False)
        return self.data.rd()

    def wr(self, v):
        '''
        Write the value to the port.
        '''
        self.data.wr(v)
        self.valid.wr(True)
        timing.clkfence()
        while self.ready.rd() is not True:
            timing.clkfence()
        self.valid.wr(False)


class FIFOPort:
    def __init__(self, dtype, direction):
        self._dtype = dtype
        self._direction = direction
        if direction == 'in':
            self.dout = Port(dtype, 'in')
            self.empty = Port(bool, 'in')
            self.read = Port(bool, 'out', False)
        else:
            self.din = Port(dtype, 'out', 0)
            self.full = Port(bool, 'in')
            self.write = Port(bool, 'out', False)

    def rd(self):
        timing.wait_value(False, self.empty)
        self.read.wr(True)
        timing.clkfence()
        self.read.wr(False)
        timing.clkfence()
        return self.dout.rd()

    def wr(self, v):
        timing.wait_value(False, self.full)
        self.write.wr(True)
        self.din.wr(v)
        timing.clkfence()
        self.write.wr(False)
        timing.clkfence()
