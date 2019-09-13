import threading

_worker_map = {}
_ident_map = {}
_simulation_time = 0


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


class Reg(object):
    instances = []

    def __init__(self, initv=0):
        Reg.instances.append(self)
        object.__setattr__(self, '_new_v', 0)
        object.__setattr__(self, '_wrote', False)
        object.__setattr__(self, 'v', initv)

    def __setattr__(self, k, v):
        if k == 'v':
            if self._wrote:
                raise RuntimeError("It is not allowed to write to the register more than once in the same clock cycle")
            object.__setattr__(self, '_new_v', v)
            object.__setattr__(self, '_wrote', True)
        else:
            object.__setattr__(self, k, v)

    def _update(self):
        object.__setattr__(self, 'v', self._new_v)
        object.__setattr__(self, '_wrote', False)


class Net(object):
    instances = []

    def __init__(self, dtype, exp=None):
        Net.instances.append(self)
        self.v = 0
        self._dtype = dtype
        self.__pytype = _pytype_from_dtype(dtype)
        self.assign(exp)

    def _update(self):
        assert self.exp
        v = self.exp()
        if not isinstance(v, self.__pytype):
            raise TypeError(f"Incompatible value type, got {type(v)} expected {self._dtype}")
        changed = self.v != v
        self.v = v
        return changed

    def assign(self, exp):
        self.exp = exp

    def rd(self):
        return self.v
