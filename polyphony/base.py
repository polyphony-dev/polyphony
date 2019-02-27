import threading

_worker_map = {}
_ident_map = {}


class Serializer:
    def __init__(self):
        self._events = {}
        self.n_waiters = 0

    def wait(self, ident):
        if ident not in self._events:
            self._events[ident] = threading.Event()
        self.n_waiters += 1
        self._events[ident].wait()
        self._events[ident].clear()
        self.n_waiters -= 1

    def notify(self, ident):
        assert ident in self._events
        self._events[ident].set()

    def destroy(self):
        self._events.clear()


_serializer = Serializer()
_cycle_update_cv = threading.Condition()


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
