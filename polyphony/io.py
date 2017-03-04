import queue
import time
import sys
import threading

__all__ = [
    'Bit',
    'Int',
    'Uint'
]


def _init_io():
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


class _DataPort(object):
    def __init__(self, init:int=0, width:int=1, protocol:int='none') -> object:
        self.__v = init
        self.__oldv = 0
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
    def rd(self) -> int:
        if self.__protocol == 'valid' or self.__protocol == 'ready_valid':
            while _io_enabled and not self.__valid_ev.is_set():
                self.__valid_ev.wait()
            self.__valid_ev.clear()
            if self.__protocol == 'ready_valid':
                self.__ready_ev.set()
        return self.__v

    @_portmethod
    def wr(self, v):
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

    def __call__(self, v=None) -> int:
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


class Bit(_DataPort):
    def __init__(self, init:int=0, width:int=1, protocol:int='none') -> object:
        super().__init__(init, width, protocol)


class Int(_DataPort):
    def __init__(self, width:int=32, init:int=0, protocol:int='none') -> object:
        super().__init__(init, width, protocol)


class Uint(_DataPort):
    def __init__(self, width:int=32, init:int=0, protocol:int='none') -> object:
        super().__init__(init, width, protocol)


class Queue(object):
    def __init__(self, width:int=32, maxsize:int=0) -> object:
        self.__width = width
        self.__q = queue.Queue(maxsize)
        self.__ev_put = _create_event()
        self.__ev_get = _create_event()

    @_portmethod
    def rd(self) -> int:
        while self.__q.empty():
            self.__ev_put.wait()
            if _io_enabled:
                self.__ev_put.clear()
            else:
                return 0
        d = self.__q.get(block=False)

        self.__ev_get.set()
        return d

    @_portmethod
    def wr(self, v):
        while self.__q.full():
            self.__ev_get.wait()
            if _io_enabled:
                self.__ev_get.clear()
            else:
                return
            #time.sleep(0.001)
        self.__q.put(v, block=False)
        self.__ev_put.set()

    def __call__(self, v=None) -> int:
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
