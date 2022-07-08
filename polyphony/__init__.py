import inspect
from . import version

__version__ = version.__version__
__python__ = True



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
def module(cls):
    def append_worker(self, fn, *args, loop=False):
        pass
    cls.append_worker = append_worker
    return cls


'''
A decorator to mark a testbench function.

This decorator can be used to define a testbench function.
The testbench function can also accept only one instance of a module class as an argument.

Usage::

    m = MyModule()

    @testbench(target=MyModule)
    def test(m):
        m.input0.wr(10)
        m.input1.wr(20)
        ...

    test(m)
::
'''
def testbench(target):
    from .compiler import from_python
    from .simulator import Simulator
    def _testbench(test):
        def _wrapper(module_instance=None):
            # Execution by exec() from inside from_python() ignores testbench
            if target.__module__ == 'polyphony_internal_imported_module':
                return
            source = inspect.getsourcefile(target)
            model = from_python(source, target.__name__, '', module_instance=module_instance)
            simu = Simulator(model)
            simu.begin()
            if module_instance:
                test(model)
            else:
                test.__globals__[target.__name__] = model
                test()
            simu.end()
        return _wrapper
    return _testbench


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



# TODO: remove
def is_worker_running():
    pass

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
    pass


def unroll(seq, factor='full'):
    pass

#class Reg:
#    pass

#class Net:
#    pass
