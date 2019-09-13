import datetime
import types
import threading
import inspect
from collections import defaultdict, deque
from . import io
from . import version
from . import timing
from . import base

__version__ = version.__version__
__python__ = True


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
        sim = Simulator()
        if module_instance:
            if module_instance.__class__.__name__ not in module.module_instances:
                print(inspect.getsourcelines(func)[0][1])
                raise RuntimeError(
                    'The argument of testbench must be an instance of the module class'
                )
            sim.append_test(func, module_instance)
        else:
            sim.append_test(func, [])
        sim.run()
    _testbench_decorator.func = func
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


_module_registers = []
_module_register_arrays = []


class RegArray(object):
    def __init__(self, module, vs):
        self.module = module
        self.vs = vs

    def __setitem__(self, idx, v):
        stack = inspect.stack()
        if self.module._is_timed(stack[1]):
            if isinstance(v, (int, bool, str)):
                _module_register_arrays.append(lambda:self.vs.__setitem__(idx, v))
        else:
            self.vs[idx] = v

    def __getitem__(self, idx):
        return self.vs[idx]

    def __iter__(self):
        return self.vs.__iter__()

    def __next__(self):
        return self.vs.__next__()

    def __str__(self):
        return str(self.vs)


class _ModuleBase(object):
    _workers = []

    def append_worker(self, fn, *args, loop=False):
        w = _Worker(fn, args, loop)
        _ModuleBase._workers.append(w)
        if hasattr(self, 'timed_module'):
            if inspect.ismethod(fn):
                setattr(fn.__func__, 'timed_func', True)
            elif inspect.isfunction(fn):
                setattr(fn, 'timed_func', True)
        else:
            pass

    def _is_timed(self, finfo):
        if hasattr(self, 'timed_module'):
            return True
        if 'self' in finfo.frame.f_locals:
            if self is not finfo.frame.f_locals['self']:
                assert False
            f = self.__class__.__dict__[finfo.function]
            return hasattr(f, 'func') and hasattr(f.func, 'timed_func')
        else:
            raise TypeError('Module class variables cannot be accessed from outside the module')

    def _is_ctor(self, finfo):
        if 'self' in finfo.frame.f_locals:
            return self is finfo.frame.f_locals['self'] and finfo.function == '__init__'
        else:
            return False

    def __setattr__(self, k, v):
        stack = inspect.stack()
        if self._is_ctor(stack[1]):
            if isinstance(v, (list, tuple)) and not hasattr(self, k):
                v = RegArray(self, v)
            object.__setattr__(self, k, v)
        elif self._is_timed(stack[1]):
            if isinstance(v, (int, bool, str)):
                if not hasattr(self, k):
                    object.__setattr__(self, k, v)
                _module_registers.append(lambda:object.__setattr__(self, k, v))
        else:
            object.__setattr__(self, k, v)


class _ModuleDecorator(object):
    def __init__(self):
        self.module_instances = defaultdict(list)

    def __call__(self, cls):
        def _module_decorator(*args, **kwargs):
            if threading.get_ident() in base._worker_map:
                raise TypeError('Cannot instatiate module class in a worker thread')
            dic = cls.__dict__.copy()
            del dic['__dict__']
            new_cls = type(cls.__name__, (_ModuleBase, ), dic)
            instance = new_cls.__new__(new_cls)
            io._enable()
            instance.__init__(*args, **kwargs)
            io._disable()
            self.module_instances[new_cls.__name__].append(instance)
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
    def __init__(self, func, args, loop):
        super().__init__()
        self.func = func
        self.args = args
        self.loop = loop
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
                while True:
                    self.worker.func(*self.worker.args)
                    if not self.worker.loop:
                        break
                    timing.clkfence()
            else:
                while True:
                    self.worker.func()
                    if not self.worker.loop:
                        break
                    timing.clkfence()
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
            wrapper.func = func
            return wrapper

    def __call__(self, **kwargs):
        return _Rule._Stub(**kwargs)


rule = _Rule()


def pipelined(seq, ii=-1):
    return seq


def unroll(seq, factor='full'):
    return seq


class Channel_(object):
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


@timing.timed
@module
class Channel:
    '''
    Channel class is used to communicate between workers.

    *Parameters:*

        dtype : an immutable type class
            A data type of the channel.
            which of the below can be used.

                - int
                - bool
                - polyphony.typing.bit
                - polyphony.typing.int<n>
                - polyphony.typing.uint<n>

        capacity : int, optional
            The capacity of the internal queue

    *Examples:*
    ::

        @module
        class M:
            def __init__(self):
                self.ch = Channel(uint16, capacity=4)
    '''

    def __init__(self, dtype, capacity):
        self.din = 0
        self.write = False
        self.read = False
        self.length = capacity
        self.mem = [0] * capacity
        self.wp = 0
        self.rp = 0
        self.count = 0

        self._dout = Net(dtype, lambda:self.mem[self.rp])
        self._full = Net(bool, lambda:self.count >= self.length)
        self._empty = Net(bool, lambda:self.count == 0)
        self._will_full = Net(bool, lambda:self.write and not self.read and self.count == self.length - 1)
        self._will_empty = Net(bool, lambda:self.read and not self.write and self.count == 1)

        self.append_worker(self.write_worker, loop=True)
        self.append_worker(self.main_worker, loop=True)

    def put(self, v):
        timing.wait_until(lambda:not self.full() and not self.will_full())
        self.write = True
        self.din = v
        timing.clkfence()
        self.write = False

    def get(self):
        timing.wait_until(lambda:not self.empty() and not self.will_empty())
        self.read = True
        timing.clkfence()
        self.read = False
        return self._dout.rd()

    def full(self):
        return self._full.rd()

    def empty(self):
        return self._empty.rd()

    def will_full(self):
        return self._will_full.rd()

    def will_empty(self):
        return self._will_empty.rd()

    def write_worker(self):
        if self.write:
            self.mem[self.wp] = self.din

    def _inc_wp(self):
        self.wp = 0 if self.wp == self.length - 1 else self.wp + 1

    def _inc_rp(self):
        self.rp = 0 if self.rp == self.length - 1 else self.rp + 1

    def main_worker(self):
        if self.write and self.read:
            if self.count == self.length:
                self.count = self.count - 1
                self._inc_rp()
            elif self.count == 0:
                self.count = self.count + 1
                self._inc_wp()
            else:
                self.count = self.count
                self._inc_wp()
                self._inc_rp()
        elif self.write:
            if self.count < self.length:
                self.count = self.count + 1
                self._inc_wp()
        elif self.read:
            if self.count > 0:
                self.count = self.count - 1
                self._inc_rp()


def ptype2vcdtype(typ):
    if typ.__module__ == 'polyphony.typing':
        if typ.__name__.startswith('int'):
            return 'integer', int(typ.__name__[3:])
        elif typ.__name__.startswith('uint'):
            return 'integer', int(typ.__name__[4:])
        elif typ.__name__.startswith('bit'):
            return 'reg', int(typ.__name__[3:])
    if typ is int:
        return 'integer', 32
    elif typ is bool:
        return 'reg', 1
    return 'integer', 32


class Simulator(object):
    def __init__(self):
        self._workers = []
        self._worker_threads = []
        self._tests = []
        self._trace_callbacks = {}
        self._vcd_writer = None

    def append_test(self, fn, modules, args=None, **kwargs):
        if not isinstance(modules, (list, tuple)):
            modules = (modules,)
        if args and not isinstance(args, (list, tuple)):
            args = (args,)
        while True:
            if fn.__name__ == 'wrapper' and hasattr(fn, 'func'):
                fn = fn.func
            elif fn.__name__ == '_testbench_decorator' and hasattr(fn, 'func'):
                fn = fn.func
            else:
                break
        self._tests.append((fn, modules, args, kwargs))

    def _setup(self, modules):
        global _is_worker_running
        if _is_worker_running:
            return
        _is_worker_running = True

        io._enable()
        self._workers.clear()
        self._workers.extend(_ModuleBase._workers)
        for p in io.Port.instances:
            p._reset()

    def _trace(self, cycle, trace_ports):
        for name, p in trace_ports:
            if 'on_clock' in self._trace_callbacks:
                self._trace_callbacks['on_clock'](cycle, name, p)
            if p._changed:
                if 'on_change' in self._trace_callbacks:
                    self._trace_callbacks['on_change'](cycle, name, p)
        if self._vcd_writer:
            self._vcd_writer.change(self._name2vcdsym['clk'], cycle * 2, 1)
            for name, p in trace_ports:
                if p._changed:
                    self._vcd_writer.change(self._name2vcdsym[name], cycle * 2, p.rd())
            self._vcd_writer.change(self._name2vcdsym['clk'], cycle * 2 + 1, 0)

    def set_trace_callback(self, **kwargs):
        for k, v in kwargs.items():
            self._trace_callbacks[k] = v

    def _setup_vcd(self, vcd_file, trace_ports):
        if not vcd_file:
            return None
        try:
            import vcd
            vcdobj = open(vcd_file, 'w')
            self._vcd_writer = vcd.VCDWriter(vcdobj, timescale='1 ns')
        except Exception as e:
            print("pyvcd is required to use 'vcd_file' option, Please run 'pip install pyvcd'\n")
            raise e
        self._name2vcdsym = {}
        self._name2vcdsym['clk'] = self._vcd_writer.register_var('', 'clk', 'reg', size=1)
        for name, port in trace_ports:
            mod_name, port_name = name.rsplit('.', 1)
            vcd_t, sz = ptype2vcdtype(port._dtype)
            sym = self._vcd_writer.register_var(mod_name, port_name, vcd_t, size=sz)
            self._vcd_writer.change(sym, 0, port._init)
            self._name2vcdsym[name] = sym
        return vcdobj

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
        for fn in _module_registers:
            fn()
        _module_registers.clear()
        for fn in _module_register_arrays:
            fn()
        _module_register_arrays.clear()

    def _update_nets(self):
        update_count = 0
        while any([n._update() for n in Net.instances]):
            update_count += 1
            if update_count > len(Net.instances):
                print('Net value is not stable')
                break

    def run(self):
        for test_fn, modules, args, kwargs in self._tests:
            self._setup(modules)
            trace_ports = []
            if 'trace_ports' in kwargs:
                trace_ports = kwargs['trace_ports']
                if 'vcd_file' in kwargs:
                    vcdobj = self._setup_vcd(kwargs['vcd_file'], kwargs['trace_ports'])
            if args:
                test_worker = _Worker(test_fn, modules + args, loop=False)
            else:
                test_worker = _Worker(test_fn, modules, loop=False)
            self._workers.append(test_worker)

            self._start_all()
            self._update_assigned_ports()
            self._update_nets()
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
                self._update_nets()
                self._trace(cycle, trace_ports)
                for p in io.Port.instances:
                    p._clear_change_flag()
                cycle += 1
                base._simulation_time = cycle
            self._teardown()
            if self._vcd_writer:
                self._vcd_writer.close()
                self._vcd_writer = None
                vcdobj.close()
            if any([w.exception for w in self._workers]):
                break


Reg = base.Reg
Net = base.Net


class TimedRestrictChecker(object):
    pass
