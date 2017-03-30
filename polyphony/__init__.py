import time
import types
import threading
import inspect
from collections import defaultdict
from . import io
from . import version

__version__ = version.__version__
__all__ = [
    'testbench',
    'module',
    'is_worker_running',
]


# @testbench decorator
def testbench(func):
    def _testbench_decorator(module_instance=None):
        if module_instance:
            if module_instance.__class__.__name__ not in module.module_instances:
                print(inspect.getsourcelines(func)[0][1])
                raise RuntimeError(
                    'The argument of testbench must be an instance of the module class'
                )
            module_instance._start()
            func(module_instance)
            module_instance._stop()
        else:
            func()
    return _testbench_decorator


_is_worker_running = False


def is_worker_running():
    '''
    Returns True if the worker is in the running state, False otherwise.

    Notes
    -----
    This function is provided to stop the worker function in the simulation with Python interpreter.
    In the course of compiling to HDL, this function is always replaced with True.
    '''
    return _is_worker_running


def _module_start(self):
    global _is_worker_running
    if _is_worker_running:
        return
    _is_worker_running = True
    io._enable()
    for w in self.__workers:
        w.start()
    time.sleep(0.001)


def _module_stop(self):
    global _is_worker_running
    if not _is_worker_running:
        return
    _is_worker_running = False
    for w in self.__workers:
        w.prejoin()
    io._disable()
    for w in self.__workers:
        w.join()


def _module_append_worker(self, fn, *args):
    self.__workers.append(_Worker(fn, *args))


class _ModuleDecorator(object):
    def __init__(self):
        self.module_instances = defaultdict(list)

    def __call__(self, cls):
        def _module_decorator(*args, **kwargs):
            instance = object.__new__(cls)
            instance._start = types.MethodType(_module_start, instance)
            instance._stop = types.MethodType(_module_stop, instance)
            instance.append_worker = types.MethodType(_module_append_worker, instance)
            io._enable()
            setattr(instance, '__workers', [])
            instance.__init__(*args, **kwargs)
            io._disable()
            self.module_instances[cls.__name__].append(instance)
            return instance
        _module_decorator.__dict__ = cls.__dict__.copy()
        return _module_decorator

    def abort(self):
        for instances in self.module_instances.values():
            for inst in instances:
                inst._stop()


# @module decorator
module = _ModuleDecorator()


class _Worker(threading.Thread):
    def __init__(self, func, *args):
        super().__init__()
        self.func = func
        self.args = args
        self.daemon = True

    def run(self):
        try:
            if self.args:
                self.func(*self.args)
            else:
                self.func()
        except io.PolyphonyIOException as e:
            module.abort()
        except Exception as e:
            module.abort()
            raise e

    def prejoin(self):
        super().join(0.01)
