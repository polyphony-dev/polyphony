'''
The class defined in polyphony.io provides the function for passing data between the module's I / O ports.
'''
import copy
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


def flipped(obj):
    def dflip(d):
        return 'in' if d == 'out' else 'out'

    if isinstance(obj, Port):
        return Port(obj._dtype, dflip(obj._direction), init=obj._init, rewritable=obj._rewritable)
    if not hasattr(obj, '__dict__') or not obj.__dict__:
        return obj
    if type(obj).__module__ == 'builtins':
        return obj
    _obj = copy.copy(obj)
    vs = vars(_obj)
    for k, v in vs.items():
        vs[k] = flipped(v)
    return _obj


def _connect_port(p0, p1):
    if p0._dtype != p1._dtype:
        raise TypeError(f"Incompatible port type, {p0._dtype} and {p1._dtype}")
    if p0._direction == 'in':
        assert p1._direction == 'out'
        p0.assign(lambda:p1.rd())
    else:
        assert p1._direction == 'in'
        p1.assign(lambda:p0.rd())


def connect(p0, p1):
    assert _ports(p0) == _ports(flipped(p1))
    assert type(p0) == type(p1)
    if isinstance(p0, Port):
        _connect_port(p0, p1)
        return
    for _p0, _p1 in zip(_ports(p0), _ports(p1)):
        _connect_port(_p0, _p1)


def _thru_port(parent, child):
    if parent._direction == 'in':
        assert child._direction == 'in'
        child.assign(lambda:parent.rd())
    else:
        assert child._direction == 'out'
        parent.assign(lambda:child.rd())


def thru(parent, child):
    assert _ports(parent) == _ports(child)
    assert type(parent) == type(child)
    if isinstance(parent, Port):
        _thru_port(parent, child)
        return
    for p, c in zip(_ports(parent), _ports(child)):
        _thru_port(p, c)


def _ports(obj):
    if isinstance(obj, Port):
        return [obj]
    if not hasattr(obj, '__dict__'):
        return []
    results = []
    for v in vars(obj).values():
        results.extend(_ports(v))
    return results


def ports(name, obj):
    if isinstance(obj, Port):
        return [(name, obj)]
    if not hasattr(obj, '__dict__'):
        return []
    results = []
    for k, v in vars(obj).items():
        results.extend(ports(f'{name}.{k}', v))
    return results


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
            raise RuntimeError("Cannot use Port.edge at the assigned port")
        return self.__old_v == old_v and self.__v == new_v

    def assign(self, exp):
        if self._direction == 'in':
            raise RuntimeError("Port.assign at 'in' Port is not allowed")
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

    def __eq__(self, other):
        return (self._dtype == other._dtype and
                self._direction == other._direction and
                self._init == other._init and
                self._rewritable == other._rewritable)

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

