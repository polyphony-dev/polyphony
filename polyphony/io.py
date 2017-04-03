import queue
import time
import sys
import threading
import inspect

__all__ = [
    'Port',
    'Queue',
]


def _init_io():
    if hasattr(sys, 'getswitchinterval'):
        if sys.getswitchinterval() > 0.005:
            sys.setswitchinterval(0.005)  # 5ms


_events = []
_conds = []
_io_enabled = False


def _create_event():
    ev = threading.Event()
    _events.append(ev)
    return ev


def _create_cond():
    cv = threading.Condition()
    _conds.append(cv)
    return cv


def _remove_cond(cv):
    _conds.remove(cv)


def _enable():
    global _io_enabled
    _io_enabled = True
    for ev in _events:
        ev.clear()


def _disable():
    global _io_enabled
    _io_enabled = False
    for ev in _events:
        ev.set()
    for cv in _conds:
        with cv:
            cv.notify_all()


class PolyphonyException(Exception):
    pass


class PolyphonyIOException(PolyphonyException):
    pass


def _portmethod(func):
    def _portmethod_decorator(*args, **kwargs):
        if not _io_enabled:
            raise PolyphonyIOException()
        return func(*args, **kwargs)
    return _portmethod_decorator


def _normalize_direction(di):
    if di == 'in' or di == 'input' or di == 'i':
        return 'in'
    elif di == 'out' or di == 'output' or di == 'o':
        return 'out'
    return 'any'


def _is_called_from_owner():
    # TODO:
    return False


class Port(object):
    '''
    Port class is used to an I/O port of a module class or a channel between workers.
    It can read or write a value of immutable type.

    Parameters
    ----------
    dtype : an immutable type class
        A data type of the port.
        which of the below can be used.
            * int
            * bool
            * polyphony.typing.bit
            * polyphony.typing.int<n>
            * polyphony.typing.uint<n>

    direction : {'any', 'input', in', 'i', 'output', 'out', 'o'}, optional
        A direction of the port.

    init : value of specified dtype parameter, optional
        An initial value of the port.
        If the direction is specified as input, this value is ignored.

    protocol : {'none', 'valid', 'ready_valid'}, optional
        A protocol of the port.

    '''
    def __init__(self, dtype, direction='any', init=None, protocol='none'):
        self.dtype = dtype
        if init:
            self.__v = init
        else:
            self.__v = dtype()
        self.__direction = _normalize_direction(direction)
        self.__oldv = dtype()
        self.__protocol = protocol
        self.__cv = []
        self.__cv_lock = threading.Lock()
        if protocol == 'valid':
            self.__valid_ev = _create_event()
            self.__valid_ev.clear()
        elif self.__protocol == 'ready_valid':
            self.__ready_ev = _create_event()
            self.__valid_ev = _create_event()
            self.__ready_ev.clear()
            self.__valid_ev.clear()
        elif self.__protocol == 'none':
            pass
        else:
            raise TypeError("'Unknown port protocol '{}'".format(self.__protocol))

    @_portmethod
    def rd(self):
        if self.__direction == 'out':
            if _is_called_from_owner():
                raise TypeError("Reading from 'out' Port is not allowed")
        if self.__protocol == 'valid' or self.__protocol == 'ready_valid':
            while _io_enabled and not self.__valid_ev.is_set():
                self.__valid_ev.wait()
            self.__valid_ev.clear()
            if self.__protocol == 'ready_valid':
                self.__ready_ev.set()
        if not isinstance(self.__v, self.dtype):
            raise TypeError("Incompatible value type, got {} expected {}".format(type(self.__v), self.dtype))
        return self.__v

    @_portmethod
    def wr(self, v):
        if not isinstance(v, self.dtype):
            raise TypeError("Incompatible value type, got {} expected {}".format(type(v), self.dtype))
        if self.__direction == 'in':
            if _is_called_from_owner():
                raise TypeError("Writing to 'in' Port is not allowed")
        if not self.__cv:
            self.__oldv = self.__v
            self.__v = v
        else:
            with self.__cv_lock:
                self.__oldv = self.__v
                self.__v = v
                for cv in self.__cv:
                    with cv:
                        cv.notify_all()
        if self.__protocol == 'valid' or self.__protocol == 'ready_valid':
            self.__valid_ev.set()
            if self.__protocol == 'ready_valid':
                while _io_enabled and not self.__ready_ev.is_set():
                    self.__ready_ev.wait()
                self.__ready_ev.clear()
        time.sleep(0.005)

    def __call__(self, v=None):
        if v is None:
            return self.rd()
        else:
            self.wr(v)

    def _add_cv(self, cv):
        with self.__cv_lock:
            self.__cv.append(cv)

    def _del_cv(self, cv):
        with self.__cv_lock:
            self.__cv.remove(cv)

    def _rd_old(self):
        return self.__oldv


class Queue(object):
    '''
    Queue port class is used to an I/O port of a module class or a channel between workers.
    It can used as FIFO(First-in First-out) buffer

    Parameters
    ----------
    dtype : an immutable type class
        A data type of the queue port.
        which of the below can be used.
            * int
            * bool
            * polyphony.typing.bit
            * polyphony.typing.int<n>
            * polyphony.typing.uint<n>

    direction : {'any', 'input', in', 'i', 'output', 'out', 'o'}, optional
        A direction of the queue port.

    maxsize : int, optional
        The capacity of the queue
    '''

    def __init__(self, dtype, direction='', maxsize=1):
        self.dtype = dtype
        self.__direction = _normalize_direction(direction)
        self.__q = queue.Queue(maxsize)
        self.__ev_put = _create_event()
        self.__ev_get = _create_event()

    @_portmethod
    def rd(self):
        while self.__q.empty():
            self.__ev_put.wait()
            if _io_enabled:
                self.__ev_put.clear()
            else:
                return 0
        d = self.__q.get(block=False)

        self.__ev_get.set()
        assert isinstance(d, self.dtype)
        return d

    @_portmethod
    def wr(self, v):
        assert isinstance(v, self.dtype)
        while self.__q.full():
            self.__ev_get.wait()
            if _io_enabled:
                self.__ev_get.clear()
            else:
                return
            #time.sleep(0.001)
        self.__q.put(v, block=False)
        self.__ev_put.set()

    def __call__(self, v=None):
        if v is None:
            return self.rd()
        else:
            self.wr(v)

    @_portmethod
    def empty(self):
        return self.__q.empty()

    @_portmethod
    def full(self):
        return self.__q.full()


_init_io()
