import queue, time, sys
import threading

__all__ = [
    'Bit',
    'Int',
    'Uint'
]

def _polyphony_init_io():
    if sys.getswitchinterval() > 0.005:
        sys.setswitchinterval(0.005) # 5ms

_polyphony_events = []
_polyphony_conds = []
_polyphony_io_enabled = False

def _polyphony_create_event():
    ev = threading.Event()
    _polyphony_events.append(ev)
    return ev

def _polyphony_create_cond():
    cv = threading.Condition()
    _polyphony_conds.append(cv)
    return cv

def _polyphony_enable():
    global _polyphony_io_enabled
    _polyphony_io_enabled = True

def _polyphony_disable():
    global _polyphony_io_enabled
    _polyphony_io_enabled = False
    for ev in _polyphony_events:
        ev.set()
    for cv in _polyphony_conds:
        with cv:
            cv.notify_all()

class _polyphony_Exception(Exception):
    pass

class _polyphony_IOException(_polyphony_Exception):
    pass

def _polyphony_portmethod(func):
    def _portmethod_decorator(*args, **kwargs):
        if not _polyphony_io_enabled:
            raise _polyphony_IOException()
        return func(*args, **kwargs)
    return _portmethod_decorator

class Bit:
    def __init__(self, init_v:int=0, width:int=1, protocol:int='none') -> object:
        self.__v = init_v
        self.__oldv = 0
        self.__cv = _polyphony_create_cond()

    @_polyphony_portmethod
    def rd(self) -> int:
        return self.__v

    @_polyphony_portmethod
    def wr(self, v):
        with self.__cv:
            self.__oldv = self.__v
            self.__v = v
            self.__cv.notify_all()
        time.sleep(0.005)

    def __call__(self, v=None) -> int:
        if v is None:
            return self.rd()
        else:
            self.wr(v)

    @_polyphony_portmethod
    def wait_rising(self) -> bool:
        with self.__cv:
            while _polyphony_io_enabled:
                self.__cv.wait()
                if self.__oldv == 0 and self.__v == 1:
                    return

    @_polyphony_portmethod
    def wait_falling(self) -> bool:
        with self.__cv:
            while _polyphony_io_enabled:
                self.__cv.wait()
                if self.__oldv == 1 and self.__v == 0:
                    return

class Int:
    def __init__(self, width:int=32, init_v:int=0, protocol:int='none') -> object:
        self.__width = width
        self.__v = init_v
        self.__protocol = protocol

    @_polyphony_portmethod
    def rd(self) -> int:
        return self.__v

    @_polyphony_portmethod
    def wr(self, v):
        self.__v = v

    def __call__(self, v=None) -> int:
        if v is None:
            return self.rd()
        else:
            self.wr(v)


class Uint:
    def __init__(self, width:int=32, init_v:int=0, protocol:int='none') -> object:
        self.__width = width
        self.__v = init_v
        self.__protocol = protocol

    @_polyphony_portmethod
    def rd(self) -> int:
        return self.__v

    @_polyphony_portmethod
    def wr(self, v):
        self.__v = v

    def __call__(self, v=None) -> int:
        if v is None:
            return self.rd()
        else:
            self.wr(v)

        
class Queue:
    def __init__(self, width:int=32, max_size:int=0, name='') -> object:
        self.__width = width
        self.__q = queue.Queue(max_size)
        self.__ev_put = _polyphony_create_event()
        self.__ev_get = _polyphony_create_event()
        self.__name = name

    @_polyphony_portmethod
    def rd(self) -> int:
        while self.__q.empty():
            self.__ev_put.wait()
            if _polyphony_io_enabled:
                self.__ev_put.clear()
            else:
                return 0
        d = self.__q.get(block=False)

        self.__ev_get.set()
        return d

    @_polyphony_portmethod
    def wr(self, v):
        while self.__q.full():
            self.__ev_get.wait()
            if _polyphony_io_enabled:
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

    @_polyphony_portmethod
    def empty(self):
        return self.__q.empty()

    @_polyphony_portmethod
    def full(self):
        return self.__q.full()

_polyphony_init_io()
