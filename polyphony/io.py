'''
The class defined in polyphony.io provides the function for passing data between the module's I / O ports or workers.
The following classes are provided. In Polyphony these classes are called Port classes.

    - polyphony.io.Port
    - polyphony.io.Queue
'''
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
_monitoring_ports = {}


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


def _pytype_from_dtype(dtype):
    if dtype is bool or dtype is int or dtype is str:
        return dtype
    elif hasattr(dtype, 'base_type'):
        return dtype.base_type
    else:
        print(dtype)
        assert False


def _pyvalue_from_dtype(dtype):
    if dtype is bool or dtype is int or dtype is str:
        return dtype()
    elif hasattr(dtype, 'base_type'):
        return dtype.base_type()
    else:
        print(dtype)
        assert False


class Port(object):
    '''
    Port class is used to an I/O port of a module class or a channel between workers.
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

        direction : {'any', 'input', in', 'i', 'output', 'out', 'o'}, optional
            A direction of the port.

        init : value of specified dtype parameter, optional
            An initial value of the port.
            If the direction is specified as input, this value is ignored.

        protocol : {'none', 'valid', 'ready_valid'}, optional
            A protocol of the port.

    *Examples:*
    ::

        @module
        class M:
            def __init__(self):
                self.din = Port(int16, direction='in', protocol='valid')
                self.dout = Port(int32, direction='out', init=0, protocol='ready_valid')
    '''
    def __init__(self, dtype, direction, init=None, protocol='none'):
        self._dtype = dtype
        self.__pytype = _pytype_from_dtype(dtype)
        if init:
            self._init = init
        else:
            self._init = _pyvalue_from_dtype(dtype)
        self.__v = self._init
        self._direction = _normalize_direction(direction)
        self.__oldv = _pyvalue_from_dtype(dtype)
        self._protocol = protocol
        self.__cv = []
        self.__cv_lock = threading.Lock()
        if protocol == 'valid':
            self.__valid_ev = _create_event()
            self.__valid_ev.clear()
        elif self._protocol == 'ready_valid':
            self.__ready_ev = _create_event()
            self.__valid_ev = _create_event()
            self.__ready_ev.clear()
            self.__valid_ev.clear()
        elif self._protocol == 'none':
            pass
        else:
            raise TypeError("'Unknown port protocol '{}'".format(self._protocol))

    @_portmethod
    def rd(self):
        '''
        Read the current value from the port.
        '''
        if self._direction == 'out':
            if _is_called_from_owner():
                raise TypeError("Reading from 'out' Port is not allowed")
        if self._protocol == 'valid' or self._protocol == 'ready_valid':
            while _io_enabled and not self.__valid_ev.is_set():
                self.__valid_ev.wait()
            self.__valid_ev.clear()
            if self._protocol == 'ready_valid':
                self.__ready_ev.set()
        if not isinstance(self.__v, self.__pytype):
            raise TypeError("Incompatible value type, got {} expected {}".format(type(self.__v), self._dtype))
        return self.__v

    @_portmethod
    def wr(self, v):
        '''
        Write the value to the port.
        '''
        if not isinstance(v, self.__pytype):
            raise TypeError("Incompatible value type, got {} expected {}".format(type(v), self._dtype))
        if self._direction == 'in':
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
        if self._protocol == 'valid' or self._protocol == 'ready_valid':
            self.__valid_ev.set()
            if self._protocol == 'ready_valid':
                while _io_enabled and not self.__ready_ev.is_set():
                    self.__ready_ev.wait()
                self.__ready_ev.clear()
        time.sleep(0.005)

    def __call__(self, v=None):
        if v is None:
            return self.rd()
        else:
            self.wr(v)

    def __deepcopy__(self, memo):
        return self

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

    *Parameters:*

        dtype : an immutable type class
            A data type of the queue port.
            which of the below can be used.

                - int
                - bool
                - polyphony.typing.bit
                - polyphony.typing.int<n>
                - polyphony.typing.uint<n>

        direction : {'any', 'input', in', 'i', 'output', 'out', 'o'}, optional
            A direction of the queue port.

        maxsize : int, optional
            The capacity of the queue

    *Examples:*
    ::

        @module
        class M:
            def __init__(self):
                self.in_q = Queue(uint16, direction='in', maxsize=4)
                self.out_q = Queue(uint16, direction='out', maxsize=4)
                tmp_q = Queue(uint16, maxsize=4)

    '''

    def __init__(self, dtype, direction, maxsize=1):
        self._dtype = dtype
        self.__pytype = _pytype_from_dtype(dtype)
        self._direction = _normalize_direction(direction)
        self._maxsize = maxsize
        self.__q = queue.Queue(maxsize)
        self.__ev_put = _create_event()
        self.__ev_get = _create_event()

    @_portmethod
    def rd(self):
        """Read the current value from the port."""
        while self.__q.empty():
            self.__ev_put.wait()
            if _io_enabled:
                self.__ev_put.clear()
            else:
                return 0
        d = self.__q.get(block=False)

        self.__ev_get.set()
        if not isinstance(d, self.__pytype):
            raise TypeError("Incompatible value type, got {} expected {}".format(type(self.__v), self._dtype))

        if self in _monitoring_ports:
            print(_monitoring_ports[self], 'rd', d)
        return d

    @_portmethod
    def wr(self, v):
        '''
        Write the value to the port.
        '''
        if not isinstance(v, self.__pytype):
            raise TypeError("Incompatible value type, got {} expected {}".format(type(v), self._dtype))
        while self.__q.full():
            self.__ev_get.wait()
            if _io_enabled:
                self.__ev_get.clear()
            else:
                return
            #time.sleep(0.001)
        self.__q.put(v, block=False)
        self.__ev_put.set()
        if self in _monitoring_ports:
            print(_monitoring_ports[self], 'wr', v)

    def __call__(self, v=None):
        if v is None:
            return self.rd()
        else:
            self.wr(v)

    def __deepcopy__(self, memo):
        return self

    @_portmethod
    def empty(self):
        return self.__q.empty()

    @_portmethod
    def full(self):
        return self.__q.full()


def add_port_monitor(name, obj):
    _monitoring_ports[obj] = name


_init_io()
