import types
import threading
import inspect
from collections import defaultdict, deque
from . import io
from . import version
from . import timing
from . import base

__version__ = version.__version__
__all__ = [
    'testbench',
    'module',
    'pure',
    'timed',
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
            sim = Simulator()
            sim.append_test(func, module_instance)
            sim.run()
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


def _module_append_worker(self, fn, *args):
    w = _Worker(fn, args)
    self._workers.append(w)


def _module_deepcopy(self, memo):
    return self


class _ModuleDecorator(object):
    def __init__(self):
        self.module_instances = defaultdict(list)

    def __call__(self, cls):
        def _module_decorator(*args, **kwargs):
            if threading.get_ident() in base._worker_map:
                raise TypeError('Cannot instatiate module class in a worker thread')
            instance = object.__new__(cls)
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
            #setattr(instance, '_worker_threads', [])
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


# @module decorator
module = _ModuleDecorator()
'''
A decorator to mark Module class.

If you specify a class as Module class, append_worker() method is added so that it can be used.

Module class constructors can have arbitrary parameters. However, only constants can be passed as parameters.
By creating an instance of Module class in the global scope, that instance will be synthesized.


*Methods:*
    - append_worker(worker, *params)
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
        self.reset()
        self.exception = None

    def reset(self):
        self.cycle = 0
        self.finished = False


class _WorkerThread(threading.Thread):
    def __init__(self, w):
        super().__init__()
        self.worker = w
        self.daemon = True

    def run(self):
        try:
            assert self.ident is not None
            base._worker_map[self.ident] = self.worker
            base._ident_map[self.worker] = self.ident

            base._serializer.wait(self.ident)
            if self.worker.args:
                self.worker.func(*self.worker.args)
            else:
                self.worker.func()
            self.worker.exception = None
        except io.PolyphonyIOException as e:
            self.worker.exception = e
            pass
        except Exception as e:
            self.worker.exception = e
            raise e
        finally:
            with base._cycle_update_cv:
                self.worker.finished = True
                base._cycle_update_cv.notify()


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


# @timed decorator
def timed(func):
    # TODO: error check
    def _timed_decorator(*args, **kwargs):
        return func(*args, **kwargs)
    return _timed_decorator


class Channel(object):
    '''
    Channel class is used to communicate between workers.

    *Parameters:*

        dtype : an immutable type class
            A data type of the queue port.
            which of the below can be used.

                - int
                - bool
                - polyphony.typing.bit
                - polyphony.typing.int<n>
                - polyphony.typing.uint<n>

        maxsize : int, optional
            The capacity of the queue

    *Examples:*
    ::

        @module
        class M:
            def __init__(self):
                self.in_q = Channel(uint16, maxsize=4)
                self.out_q = Channel(uint16, maxsize=4)
    '''

    def __init__(self, dtype, maxsize=1):
        self._dtype = dtype
        self.__pytype = base._pytype_from_dtype(dtype)
        self._maxsize = maxsize
        self.__q = deque()
        self._changed = False
        self._will_get = False

    def get(self):
        '''
        Read the current value from the channel.
        '''
        while self.empty():
            timing.clkfence()
        d = self.__q.popleft()
        self._changed = True
        if not isinstance(d, self.__pytype):
            raise TypeError(f"Incompatible value type, got {type(self.__v)} expected {self._dtype}")
        return d

    def put(self, v):
        '''
        Write the value to the channel.
        '''
        if not isinstance(v, self.__pytype):
            raise TypeError(f"Incompatible value type, got {type(v)} expected {self._dtype}")
        while self.full():
            timing.clkfence()
        self.__q.append(v)
        self._changed = True

    def empty(self):
        return len(self.__q) == 0

    def full(self):
        return len(self.__q) == self._maxsize

    def _reset(self):
        self.__q.clear()
        self._changed = False

    def _late_update(self):
        self._changed = False


class Simulator(object):
    def __init__(self):
        self._workers = []
        self._worker_threads = []
        self._tests = []
        self._trace_callbacks = {}

    def append_test(self, fn, modules, args=None, trace_ports=None):
        if not isinstance(modules, (list, tuple)):
            modules = (modules,)
        if args and not isinstance(args, (list, tuple)):
            args = (args,)
        self._tests.append((fn, modules, args, trace_ports))

    def _setup(self, modules):
        def collect_worker(modules):
            for m in modules:
                self._workers.extend(m._workers)
                if m._submodules:
                    collect_worker(m._submodules)

        global _is_worker_running
        if _is_worker_running:
            return
        _is_worker_running = True

        io._enable()
        self._workers.clear()

        collect_worker(modules)
        for p in io.Port.instances:
            p._reset()

    def _setup_trace(self, trace_ports):
        if trace_ports:
            self._trace_ports = trace_ports
        else:
            self._trace_ports = []

    def _trace(self, cycle):
        for p, name in self._trace_ports:
            if 'on_clock' in self._trace_callbacks:
                self._trace_callbacks['on_clock'](cycle, p, name)
            if p._changed:
                if 'on_change' in self._trace_callbacks:
                    self._trace_callbacks['on_change'](cycle, p, name)

    def set_trace_callback(self, **kwargs):
        for k, v in kwargs.items():
            self._trace_callbacks[k] = v

    def _start_all(self):
        for w in self._workers:
            w.reset()
            th = _WorkerThread(w)
            self._worker_threads.append(th)
            th.start()

    def _teardown(self):
        global _is_worker_running
        if not _is_worker_running:
            return
        _is_worker_running = False
        io._disable()
        for th in self._worker_threads:
            base._serializer.notify(th.ident)
            th.join()
        self._worker_threads.clear()
        base._serializer.destroy()

    def _update_ports(self):
        for p in io.Port.instances:
            p._update()

    def _update_assigned_ports(self):
        update_count = 0
        while any([p._update_assigned() for p in io.Port.instances]):
            update_count += 1
            if update_count > len(io.Port.instances):
                print('Port value is not stable')
                break

    def _update_regs(self):
        for r in Reg.instances:
            r._update()

    def run(self):
        for test_fn, modules, args, trace_ports in self._tests:
            self._setup(modules)
            self._setup_trace(trace_ports)
            if args:
                test_worker = _Worker(test_fn, modules + args)
            else:
                test_worker = _Worker(test_fn, modules)
            self._workers.append(test_worker)

            self._start_all()
            self._update_assigned_ports()
            cycle = 0
            workers = self._workers[:]
            while workers:
                for w in workers:
                    #print(base._ident_map)
                    base._serializer.notify(base._ident_map[w])
                    with base._cycle_update_cv:
                        while w.cycle != cycle and not test_worker.finished:
                            continue
                        base._cycle_update_cv.wait()
                if any([w.finished for w in workers]):
                    workers = [w for w in workers if not w.finished]
                if test_worker.finished:
                    break

                assert all([w.cycle == cycle + 1 for w in workers])
                self._update_ports()
                self._update_regs()
                self._update_assigned_ports()
                self._trace(cycle)
                for p in io.Port.instances:
                    p._clear_change_flag()
                #print('CYCLE', cycle)
                cycle += 1
            self._teardown()
            if any([w.exception for w in self._workers]):
                break


Reg = base.Reg


class TimedRestrictChecker(object):
    pass
