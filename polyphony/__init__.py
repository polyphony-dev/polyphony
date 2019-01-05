import time
import types
import threading
import inspect
from collections import defaultdict
from . import io
from . import version
from . import timing
from . import typing


__version__ = version.__version__
__all__ = [
    'testbench',
    'module',
    'pure',
    'is_worker_running',
]


# @testbench decorator
def testbench(func):
    '''
    A decorator to mark a testbench function.

    This decorator can be used to define a testbench function.

    Usage::

        @testbench
        def test():
            ...


    The testbench function can also accept only one instance of a module class as an argument.

    ::

        m = MyModule()

        @testbench
        def test(m):
            m.input0.wr(10)
            m.input1.wr(20)
            ...

        test(m)
    '''
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


# @pure decorator
def pure(func):
    '''
    A decorator to mark a pure Python function.

    This decorator can be used to define a pure Python function.
    Within the pure function you can execute any Python code at compile time.

    *Restrictions:*
        The pure function has the following restrictions.
            - It must be a function defined in global scope
            - The call argument must be a constant
            - The return value (if any) must be compilable with the Polyphony compiler
              (e.g. int, list of int, ...)

    *Examples:*
    ::

        @pure
        def py_func():
            # You can write any python code here
            ...

        @module
        class M:
            @pure
            def __init__(self):
                # Also Module class constructor can be @pure function
                ...
    '''
    def _pure_decorator(*args, **kwargs):
        return func(*args, **kwargs)
    _pure_decorator.func = func
    return _pure_decorator


_is_worker_running = False


def is_worker_running():
    '''
    Returns True if the worker is in the running state, False otherwise.

    *Examples:*
    ::

        def my_worker(arg1, arg2):
            while is_worker_running():
                ...


    *Notes:*
        This function is provided to stop the worker function in the simulation with Python interpreter.
        While compiling to HDL, this function is always replaced with True.
    '''
    return _is_worker_running


def _module_start(self, reentrance=False):
    global _is_worker_running
    if not reentrance:
        if _is_worker_running:
            return
        _is_worker_running = True
        io._enable()
    for w in self._workers:
        th = _WorkerThread(w)
        self._worker_threads.append(th)
        th.start()
    for sub in self._submodules:
        sub._start(True)
    time.sleep(0.001)


def _module_stop(self, reentrance=False):
    global _is_worker_running
    if not reentrance:
        if not _is_worker_running:
            return
        _is_worker_running = False
    for th in self._worker_threads:
        th.prejoin()
    for sub in self._submodules:
        sub._stop()
    if not reentrance:
        io._disable()
    for th in self._worker_threads:
        th.join()
    self._worker_threads.clear()


def _module_append_worker(self, fn, *args):
    self._workers.append(_Worker(fn, args))


def _module_deepcopy(self, memo):
    return self


class _ModuleDecorator(object):
    def __init__(self):
        self.module_instances = defaultdict(list)

    def __call__(self, cls):
        def _module_decorator(*args, **kwargs):
            instance = object.__new__(cls)
            instance._start = types.MethodType(_module_start, instance)
            instance._stop = types.MethodType(_module_stop, instance)
            instance.__deepcopy__ = types.MethodType(_module_deepcopy, instance)
            if instance.__init__.__name__ == '_pure_decorator':
                ctor = types.MethodType(instance.__init__.func, instance)
            else:
                ctor = instance.__init__
            instance._ctor = ctor
            instance.append_worker = types.MethodType(_module_append_worker, instance)
            instance._module_decorator = self
            io._enable()
            setattr(instance, '_workers', [])
            setattr(instance, '_worker_threads', [])
            setattr(instance, '_submodules', [])
            instance.__init__(*args, **kwargs)
            io._disable()
            self.module_instances[cls.__name__].append(instance)
            for name, obj in instance.__dict__.items():
                if obj in self.module_instances[obj.__class__.__name__]:
                    instance._submodules.append(obj)
            return instance
        _module_decorator.__dict__ = cls.__dict__.copy()
        _module_decorator.cls = cls
        return _module_decorator

    def abort(self):
        for instances in self.module_instances.values():
            for inst in instances:
                inst._stop()


# @module decorator
module = _ModuleDecorator()
'''
A decorator to mark Module class.

If you specify a class as Module class, append_worker() method is added so that it can be used.

Module class constructors can have arbitrary parameters. However, only constants can be passed as parameters.
By creating an instance of Module class in the global scope, that instance will be synthesized.


*Methods:*
    - append_worker(worker, \*params)
        To the first argument 'worker', specify a function to act as a worker.
        This can be a method of a module class or a normal function.
        For the second and subsequent arguments, specify the arguments to pass to the worker function.


*Restrictions:*
    Module class and Worker has the following restrictions. (In future versions this limit may change)

        - Module class must be defined in global scope
        - Assignment to the instance field of the module class can only be done in the constructor (__init__() method)
        - Calling methods from outside the module class is not allowed
          (Only Port instance generated as an instance field of Module class can be accessed from outside)
        - It is only constants that can be passed as arguments to __init__() method
        - append_worker() method can only be used within the __init__() method of the module class
        - Only Port or constant can be passed to the argument of the worker function


*Examples:*

::

    def my_worker(din, dout):
        data = din.rd()
        ...
        dout.wr(data)

    @module
    class MyModule:
        def __init__(self, param0, param1):
            self.param0 = param0
            self.param1 = param1
            self.din = Port(int)
            self.dout = Port(int)
            self.append_worker(my_worker, self.din, self.dout)

    m1 = MyModule(100, 1)
    m2 = MyModule(200, 2)

'''


class _Worker(object):
    def __init__(self, func, args):
        super().__init__()
        self.func = func
        self.args = args


class _WorkerThread(threading.Thread):
    def __init__(self, w):
        super().__init__()
        self.worker = w
        self.daemon = True

    def run(self):
        try:
            if self.worker.args:
                self.worker.func(*self.worker.args)
            else:
                self.worker.func()
        except io.PolyphonyIOException as e:
            module.abort()
        except Exception as e:
            module.abort()
            raise e

    def prejoin(self):
        super().join(0.01)


class _Rule(object):
    class _Stub(object):
        def __init__(self, **kwargs):
            self.rules = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def __call__(self, func):
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper

    def __call__(self, **kwargs):
        return _Rule._Stub(**kwargs)


rule = _Rule()


def pipelined(seq, ii=-1):
    return seq


def unroll(seq, factor='full'):
    return seq
