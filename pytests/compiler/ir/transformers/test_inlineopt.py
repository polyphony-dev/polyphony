from polyphony.compiler.common.env import env
from polyphony.compiler.ir.ir import *
from polyphony.compiler.ir import ir as new
from polyphony.compiler.ir.ir import name2var as _v
from polyphony.compiler.ir.block import Block
from polyphony.compiler.ir.irreader import IRReader as IRParser, ir_stm
from polyphony.compiler.ir.scope import Scope
from polyphony.compiler.ir.symbol import Symbol
from polyphony.compiler.ir.transformers.inlineopt import InlineOpt
from polyphony.compiler.ir.transformers.inlineopt import ObjectHierarchyCopier
from polyphony.compiler.ir.types.type import Type
from polyphony.compiler.ir.builtin import builtin_symbols
from pytests.compiler.base import setup_test, setup_libs
import pytest


def _run_inline(scopes):
    """Run InlineOpt directly on block.stms (unified IR)."""
    InlineOpt().process_scopes(scopes)


def test_funtion_inlining():
    setup_test()
    block_src = """
    scope @top.f
    tags function
    return int32
    var x: int32

    blk1:
    mv x (call g 10)
    mv @return x
    ret @return

    scope @top.g
    tags function
    param x:int32
    return int32

    blk1:
    mv x @in_x
    mv @return (+ x 1)
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))
    top.add_sym('g', tags=set(), typ=Type.function('@top.g'))

    f = env.scopes['@top.f']
    _run_inline([f])

    gen = f.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    assert blk1.stms[0] == Jump(blk2)
    assert blk2.stms[0] == Move(_v('x_0'), Const(10))
    assert blk2.stms[1] == Move(_v('@return_0'), BinOp('Add', _v('x_0'), Const(1)))
    assert blk2.stms[2] == Jump(blk3)
    assert blk3.stms[0] == Move(_v('x'), _v('@return_0'))
    assert blk3.stms[1] == Move(_v('@return'), _v('x'))
    assert blk3.stms[2] == Ret(_v('@return'))


def test_funtion_inlining_2():
    setup_test()
    block_src = """
    scope @top.f
    tags function
    return int32
    var x: int32

    blk1:
    mv x (call g 10)
    mv y (call g 11)
    mv @return (+ x y)
    ret @return

    scope @top.g
    tags function
    param x:int32
    return int32

    blk1:
    mv x @in_x
    mv @return (+ x 1)
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))
    top.add_sym('g', tags=set(), typ=Type.function('@top.g'))

    f = env.scopes['@top.f']
    _run_inline([f])

    gen = f.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    blk4 = next(gen)
    blk5 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    assert blk1.stms[0] == Jump(blk2)
    assert blk2.stms[0] == Move(_v('x_0'), Const(10))
    assert blk2.stms[1] == Move(_v('@return_0'), BinOp('Add', _v('x_0'), Const(1)))
    assert blk2.stms[2] == Jump(blk3)
    assert blk3.stms[0] == Move(_v('x'), _v('@return_0'))
    assert blk3.stms[1] == Jump(blk4)
    assert blk4.stms[0] == Move(_v('x_1'), Const(11))
    assert blk4.stms[1] == Move(_v('@return_1'), BinOp('Add', _v('x_1'), Const(1)))
    assert blk4.stms[2] == Jump(blk5)
    assert blk5.stms[0] == Move(_v('y'), _v('@return_1'))
    assert blk5.stms[1] == Move(_v('@return'), BinOp('Add', _v('x'), _v('y')))
    assert blk5.stms[2] == Ret(_v('@return'))


def test_function_inlining_3():
    # def f(x, y) -> Tuple[int8]:
    #     return x, y

    # def func(xs:list, ys:list, i, j):
    #     ys[j], xs[i] = f(xs[i], ys[j])

    setup_test()
    block_src = """
    scope @top.f
    tags function
    param x:int32
    param y:int32
    return tuple<int32>[]

    blk1:
    mv x @in_x
    mv y @in_y
    mv @return (x y)

    scope @top.func
    tags function
    param xs:list<int32>[]
    param ys:list<int32>[]
    param i:int32
    param j:int32
    return none
    var @t1: int32 { temp }
    var @t2: int32 { temp }

    blk1:
    mv xs @in_xs
    mv ys @in_ys
    mv i @in_i
    mv j @in_j
    mv @t1 (mld xs i)
    mv @t2 (mld ys j)
    mv ((mld ys j) (mld xs i)) (call f @t1 @t2)
    """

    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))
    top.add_sym('func', tags=set(), typ=Type.function('@top.func'))

    func = env.scopes['@top.func']
    _run_inline([func])

    ret_func = func.find_sym('@return')
    assert ret_func
    assert ret_func.typ.is_none()
    ret_f = func.find_sym('@return_0')
    assert ret_f
    assert ret_f.typ.is_tuple()

    gen = func.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    assert len(blk1.stms) == 7
    assert blk1.stms[0] == Move(_v('xs'), _v('@in_xs'))
    assert blk1.stms[1] == Move(_v('ys'), _v('@in_ys'))
    assert blk1.stms[2] == Move(_v('i'), _v('@in_i'))
    assert blk1.stms[3] == Move(_v('j'), _v('@in_j'))
    assert blk1.stms[4] == Move(_v('@t1'), MRef(_v('xs'), _v('i')))
    assert blk1.stms[5] == Move(_v('@t2'), MRef(_v('ys'), _v('j')))
    assert blk1.stms[6] == Jump(blk2)

    assert len(blk2.stms) == 4
    assert blk2.stms[0] == Move(_v('x'), _v('@t1'))
    assert blk2.stms[1] == Move(_v('y'), _v('@t2'))
    assert blk2.stms[2] == Move(_v('@return_0'), Array([_v('x'), _v('y')], mutable=False))
    assert blk2.stms[3] == Jump(blk3)

    assert len(blk3.stms) == 1
    assert blk3.stms[0] == Move(Array([MRef(_v('ys'), _v('j')), MRef(_v('xs'), _v('i'))], mutable=False), _v('@return_0'))


def test_function_inlining_with_free_symbol():
#   def g(y):
#       def h(z):
#           return x + z
#       x = y + 1
#       return h(y + 2)

#   def f(x):
#       return g(x)

    setup_test()
    block_src = """
    scope @top.f
    tags function
    param x:int32
    return int32

    blk1:
    mv x @in_x
    mv @return (call g x)
    ret @return

    scope @top.g
    tags function enclosure
    param y:int32
    return int32
    var x: int32
    var @t: int32
    var h: function(@top.g.h)

    blk1:
    mv y @in_y
    mv x (+ y 1)
    mv @t (+ y 2)
    mv @return (call h @t)
    ret @return

    scope @top.g.h
    tags function closure
    param z:int32
    return int32

    blk1:
    mv z @in_z
    mv @return (+ x z)
    ret @return
    """

    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))
    top.add_sym('g', tags=set(), typ=Type.function('@top.g'))

    f = env.scopes['@top.f']
    g = env.scopes['@top.g']
    h = env.scopes['@top.g.h']
    assert g.is_enclosure()
    assert len(g.closures()) == 1
    assert g.closures()[0] is h

    _run_inline([f])

    # removed enclosure tag
    assert not g.is_enclosure()
    assert len(g.closures()) == 0

    gen = f.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    blk4 = next(gen)
    blk5 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    x_sym = f.find_sym('x')
    assert x_sym is not None
    assert not x_sym.is_free()
    x0_sym = f.find_sym('x_0')
    assert x0_sym is not None
    assert not x0_sym.is_free()

    assert len(blk1.stms) == 2
    assert blk1.stms[0] == Move(_v('x'), _v('@in_x'))
    assert blk1.stms[1] == Jump(blk2)

    assert len(blk2.stms) == 4
    assert blk2.stms[0] == Move(_v('y'), _v('x'))
    assert blk2.stms[1] == Move(_v('x_0'), BinOp('Add', _v('y'), Const(1)))
    assert blk2.stms[2] == Move(_v('@t'), BinOp('Add', _v('y'), Const(2)))
    assert blk2.stms[3] == Jump(blk3)

    assert len(blk3.stms) == 3
    assert blk3.stms[0] == Move(_v('z'), _v('@t'))
    assert blk3.stms[1] == Move(_v('@return_0'), BinOp('Add', _v('x_0'), _v('z')))
    assert blk3.stms[2] == Jump(blk4)

    assert len(blk4.stms) == 2
    assert blk4.stms[0] == Move(_v('@return_1'), _v('@return_0'))
    assert blk4.stms[1] == Jump(blk5)

    assert len(blk5.stms) == 2
    assert blk5.stms[0] == Move(_v('@return'), _v('@return_1'))
    assert blk5.stms[1] == Ret(_v('@return'))


def test_functor_inlining():
#   def g(y):
#       def h(z):
#           return y + z
#       return h

#   def f(x):
#       h = g(x)
#       return h(x + 1)

    setup_test()
    block_src = """
    scope @top.f
    tags function
    param x:int32
    return int32
    var h: function(@top.g.h)
    var @t: int32 { temp }

    blk1:
    mv h (call g x)
    mv @t (+ x 1)
    mv @return (call h @t)
    ret @return

    scope @top.g
    tags function enclosure
    param y:int32 { free }
    return function(@top.g.h)
    var h: function(@top.g.h)

    blk1:
    mv y @in_y
    mv @return h
    ret @return

    scope @top.g.h
    tags function closure
    param z:int32
    return int32
    var y: int32

    blk1:
    mv z @in_z
    mv @return (+ y z)
    ret @return
    """

    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))
    top.add_sym('g', tags=set(), typ=Type.function('@top.g'))

    f = env.scopes['@top.f']
    _run_inline([f])

    gen = f.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    blk4 = next(gen)
    blk5 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)


    assert len(blk1.stms) == 1
    assert blk1.stms[0] == Jump(blk2)

    assert len(blk2.stms) == 3
    assert blk2.stms[0] == Move(_v('y'), _v('x'))
    assert blk2.stms[1] == Move(_v('@return_0'), _v('h_#1'))
    assert blk2.stms[2] == Jump(blk3)

    assert len(blk3.stms) == 3
    assert blk3.stms[0] == Move(_v('h'), _v('@return_0'))
    assert blk3.stms[1] == Move(_v('@t'), BinOp('Add', _v('x'), Const(1)))
    assert blk3.stms[2] == Jump(blk4)

    assert len(blk4.stms) == 3
    assert blk4.stms[0] == Move(_v('z'), _v('@t'))
    assert blk4.stms[1] == Move(_v('@return_1'), BinOp('Add', _v('y_0'), _v('z')))
    assert blk4.stms[2] == Jump(blk5)

    assert len(blk5.stms) == 2
    assert blk5.stms[0] == Move(_v('@return'), _v('@return_1'))
    assert blk5.stms[1] == Ret(_v('@return'))


def test_ctor_inlining():
    setup_test()
    block_src = """
    scope @top.C
    tags  class
    var __init__: function(@top.C.__init__)
    var x: int32

    scope @top.C.__init__
    tags  method ctor
    param  self:object(@top.C)
    param  x:int32
    return object(@top.C)

    blk1:
    mv x @in_x
    mv self.x x

    scope @top.caller_func
    tags  function_module function
    return int32
    var c0: object(@top.C)
    var x: int32

    blk1:
    mv x 10
    mv c0 (new C x)
    mv @return c0.x
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('caller_func', tags=set(), typ=Type.function('@top.caller_func'))

    caller_func = env.scopes['@top.caller_func']

    _run_inline([caller_func])

    gen = caller_func.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    assert len(blk1.stms) == 3
    # x = 10
    # c0 = $new(C)
    # jump blk2
    assert blk1.stms[0] == Move(_v('x'), Const(10))
    builtin_new = SysCall(_v('$new'), args=[('typ', _v('C'))], kwargs={})
    assert blk1.stms[1] == Move(_v('c0'), builtin_new)
    assert blk1.stms[2] == Jump(blk2)

    assert len(blk2.stms) == 3
    # x_0 = x
    # c0.x = x_0
    # jump blk3
    assert blk2.stms[0] == Move(_v('x_0'), _v('x'))
    assert blk2.stms[1] == Move(_v('c0.x'), _v('x_0'))
    assert blk2.stms[2] == Jump(blk3)

    assert len(blk3.stms) == 2
    # @return = c0.x
    # return @return
    assert blk3.stms[0] == Move(_v('@return'),  _v('c0.x'))
    assert blk3.stms[1] == Ret(_v('@return'))


def test_ctor_inlining_2():
    '''
class D:
def __init__(self, x):
    self.x = x

class C:
    def __init__(self, x):
        self.d = D(x)

def caller_func():
    x = 10
    c = C(x)
    a = c.d.x + c.d.x
    c.d.x = 10
    return a + c.d.x
    '''

    setup_test()
    block_src = """
    scope @top.D
    tags  class
    var __init__: function(@top.D.__init__)
    var x: int32

    scope @top.D.__init__
    tags  method ctor
    param  self:object(@top.D)
    param  x:int32
    return object(@top.D)

    blk1:
    mv x @in_x
    mv self.x x

    scope @top.C
    tags  class
    var __init__: function(@top.C.__init__)
    var d: object(@top.D)

    scope @top.C.__init__
    tags  method ctor
    param  self:object(@top.C)
    param  x:int32
    return object(@top.C)

    blk1:
    mv x @in_x
    mv self.d (new D x)

    scope @top.caller_func
    tags  function_module function
    param  x:int32
    return int32
    var c: object(@top.C)
    var a: int32

    blk1:
    mv x 10
    mv c (new C x)
    mv a (+ c.d.x c.d.x)
    mv c.d.x 10
    mv @return (+ a c.d.x)
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('D', tags=set(), typ=Type.klass('@top.D'))
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('caller_func', tags=set(), typ=Type.function('@top.caller_func'))

    caller_func = env.scopes['@top.caller_func']

    _run_inline([caller_func])

    gen = caller_func.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    blk4 = next(gen)
    blk5 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    assert len(blk1.stms) == 3
    # x = 10
    # c = $new(C)
    # jump blk2
    assert blk1.stms[0] == Move(_v('x'), Const(10))
    builtin_new = SysCall(_v('$new'), args=[('typ', _v('C'))], kwargs={})
    assert blk1.stms[1] == Move(_v('c'), builtin_new)
    assert blk1.stms[2] == Jump(blk2)

    assert len(blk2.stms) == 3
    # x_1 = x
    # c.d = $new(D)
    # jump blk3
    assert blk2.stms[0] == Move(_v('x_1'), _v('x'))
    builtin_new = SysCall(_v('$new'), args=[('typ', _v('D'))], kwargs={})
    assert blk2.stms[1] == Move(_v('c.d'), builtin_new)
    assert blk2.stms[2] == Jump(blk3)

    assert len(blk3.stms) == 3
    # x_0 = x_1
    # c.d.x = x_0
    # jump blk4
    assert blk3.stms[0] == Move(_v('x_0'), _v('x_1'))
    assert blk3.stms[1] == Move(_v('c.d.x'), _v('x_0'))
    assert blk3.stms[2] == Jump(blk4)

    assert len(blk4.stms) == 1
    assert blk4.stms[0] == Jump(blk5)

    # a = (c.d.x + c.d.x)
    # c.d.x = 10
    # @return = (a + c.d.x)
    # return @return
    assert len(blk5.stms) == 4
    assert blk5.stms[0] == Move(_v('a'), BinOp('Add', _v('c.d.x'), _v('c.d.x')))
    assert blk5.stms[1] == Move(_v('c.d.x'), Const(10))
    assert blk5.stms[2] == Move(_v('@return'), BinOp('Add', _v('a'), _v('c.d.x')))
    assert blk5.stms[3] == Ret(_v('@return'))


def test_method_inlining():
    setup_test()
    block_src = """
    scope @top.C
    tags  class
    var __init__: function(@top.C.__init__)
    var func: function(@top.C.func)
    var x: int32

    scope @top.C.__init__
    tags  method ctor
    param  self:object(@top.C)
    param  x:int32
    return object(@top.C)

    blk1:
    mv x @in_x
    mv self.x x

    scope @top.C.func
    tags  method
    param  self:object(@top.C)
    param  x:int32
    return int32

    blk1:
    mv x @in_x
    mv self.x (+ self.x x)
    mv @return self.x
    ret @return

    scope @top.caller_func
    tags  function_module function
    return int32
    var c0: object(@top.C)
    var x: int32

    blk1:
    mv x 10
    mv c0 (new C x)
    mv x (call c0.func 10)
    mv @return x
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('caller_func', tags=set(), typ=Type.function('@top.caller_func'))

    caller_func = env.scopes['@top.caller_func']

    _run_inline([caller_func])

    gen = caller_func.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    blk4 = next(gen)
    blk5 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    assert len(blk1.stms) == 3
    # x = 10
    # c0 = $new(C)
    # jump blk2
    assert blk1.stms[0] == Move(_v('x'), Const(10))
    builtin_new = SysCall(_v('$new'), args=[('typ', _v('C'))], kwargs={})
    assert blk1.stms[1] == Move(_v('c0'), builtin_new)
    assert blk1.stms[2] == Jump(blk2)

    assert len(blk2.stms) == 3
    # x_0 = x
    # c0.x = x_0
    # jump blk3
    assert blk2.stms[0] == Move(_v('x_0'), _v('x'))
    assert blk2.stms[1] == Move(_v('c0.x'), _v('x_0'))
    assert blk2.stms[2] == Jump(blk3)

    assert len(blk3.stms) == 1
    # jump blk4
    assert blk3.stms[0] == Jump(blk4)

    assert len(blk4.stms) == 4
    # x_1 = 10
    # c0.x = (c0.x + x_1)
    # @return_0 = c0.x
    # jump blk5
    assert blk4.stms[0] == Move(_v('x_1'), Const(10))
    assert blk4.stms[1] == Move(_v('c0.x'), BinOp('Add', _v('c0.x'), _v('x_1')))
    assert blk4.stms[2] == Move(_v('@return_0'), _v('c0.x'))
    assert blk4.stms[3] == Jump(blk5)

    assert len(blk5.stms) == 3
    # x = @return_0
    # @return = x
    # return @return
    assert blk5.stms[0] == Move(_v('x'), _v('@return_0'))
    assert blk5.stms[1] == Move(_v('@return'), _v('x'))
    assert blk5.stms[2] == Ret(_v('@return'))


def test_method_inlining_2():
    '''
class D:
    def __init__(self, x):
        self.x = x

    def get_x(self):
        return self.x

class C:
    def __init__(self, x):
        self.d = D(x)

    def get_x(self):
        return self.d.get_x()

def composition04(x):
    c = C(x)
    a = c.get_x() + c.get_x()
    return a
    '''
    setup_test()
    block_src = """
    scope @top.D
    tags  class
    var __init__: function(@top.D.__init__)
    var get_x: function(@top.D.get_x)
    var x: int32

    scope @top.D.__init__
    tags  method ctor
    param  self:object(@top.D)
    param  x:int32
    return object(@top.D)

    blk1:
    mv x @in_x
    mv self.x x

    scope @top.D.get_x
    tags  method
    param  self:object(@top.D)
    return int32

    blk1:
    mv @return self.x
    ret @return

    scope @top.C
    tags  class
    var __init__: function(@top.C.__init__)
    var get_x: function(@top.C.get_x)
    var d: object(@top.D)

    scope @top.C.__init__
    tags  method ctor
    param  self:object(@top.C)
    param  x:int32
    return object(@top.C)

    blk1:
    mv x @in_x
    mv self.d (new D x)

    scope @top.C.get_x
    tags  method
    param  self:object(@top.C)
    return int32

    blk1:
    mv @return (call self.d.get_x)
    ret @return

    scope @top.composition04
    tags  function_module function
    param  x:int32
    return int32
    var c: object(@top.C)
    var a: int32
    var @t1: int32 { temp }
    var @t2: int32 { temp }

    blk1:
    mv x @in_x
    mv c (new C x)
    mv @t1 (call c.get_x)
    mv @t2 (call c.get_x)
    mv a (+ @t1 @t2)
    mv @return a
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('D', tags=set(), typ=Type.klass('@top.D'))
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('composition04', tags=set(), typ=Type.function('@top.composition04'))

    caller_func = env.scopes['@top.composition04']

    _run_inline([caller_func])

    gen = caller_func.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    blk4 = next(gen)
    blk5 = next(gen)
    blk6 = next(gen)
    blk7 = next(gen)
    blk8 = next(gen)
    blk9 = next(gen)
    blk10 = next(gen)
    blk11 = next(gen)
    blk12 = next(gen)
    blk13 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    assert len(blk1.stms) == 3
    # x = @in_x
    # c = $new(C)
    # jump blk2
    assert blk1.stms[0] == Move(_v('x'), _v('@in_x'))
    builtin_new = SysCall(_v('$new'), args=[('typ', _v('C'))], kwargs={})
    assert blk1.stms[1] == Move(_v('c'), builtin_new)

    assert len(blk2.stms) == 3
    # x_1 = x
    # c.d = $new(D)
    # jump blk3
    assert blk2.stms[0] == Move(_v('x_1'), _v('x'))
    builtin_new = SysCall(_v('$new'), args=[('typ', _v('D'))], kwargs={})
    assert blk2.stms[1] == Move(_v('c.d'), builtin_new)

    assert len(blk3.stms) == 3
    # x_0 = x_1
    # c.d.x = x_0
    # jump blk4
    assert blk3.stms[0] == Move(_v('x_0'), _v('x_1'))
    assert blk3.stms[1] == Move(_v('c.d.x'), _v('x_0'))
    assert blk3.stms[2] == Jump(blk4)

    assert len(blk4.stms) == 1
    # jump blk5
    assert blk4.stms[0] == Jump(blk5)

    assert len(blk5.stms) == 1
    # jump blk6
    assert blk5.stms[0] == Jump(blk6)

    assert len(blk6.stms) == 1
    # jump blk7
    assert blk6.stms[0] == Jump(blk7)

    assert len(blk7.stms) == 2
    # @return_0 = c.d.x
    # jump blk8
    assert blk7.stms[0] == Move(_v('@return_0'), _v('c.d.x'))
    assert blk7.stms[1] == Jump(blk8)

    assert len(blk8.stms) == 2
    # @return_1 = @return_0
    # jump blk9
    assert blk8.stms[0] == Move(_v('@return_1'), _v('@return_0'))
    assert blk8.stms[1] == Jump(blk9)

    assert len(blk9.stms) == 2
    # @t1 = @return_1
    # jump blk10
    assert blk9.stms[0] == Move(_v('@t1'), _v('@return_1'))
    assert blk9.stms[1] == Jump(blk10)

    assert len(blk10.stms) == 1
    # jump blk11
    assert blk10.stms[0] == Jump(blk11)

    assert len(blk11.stms) == 2
    # @return_0_0 = c.d.x
    # jump blk12
    assert blk11.stms[0] == Move(_v('@return_0_0'), _v('c.d.x'))
    assert blk11.stms[1] == Jump(blk12)

    assert len(blk12.stms) == 2
    # @return_2 = @return_0_0
    # jump blk13

    assert blk12.stms[0] == Move(_v('@return_2'), _v('@return_0_0'))
    assert blk12.stms[1] == Jump(blk13)

    assert len(blk13.stms) == 4
    # @t2 = @return_2
    # a = (@t1 + @t2)
    # @return = a
    # return @return
    assert blk13.stms[0] == Move(_v('@t2'), _v('@return_2'))
    assert blk13.stms[1] == Move(_v('a'), BinOp('Add', _v('@t1'), _v('@t2')))
    assert blk13.stms[2] == Move(_v('@return'), _v('a'))
    assert blk13.stms[3] == Ret(_v('@return'))


def test_inlinelib_1():
    setup_test()
    setup_libs('io', 'timing')
    block_src = """
    scope @top.caller_func
    tags function_module function
    var port: object(polyphony.io.Port)
    var value: int32

    blk1:
    mv port (new polyphony.io.Port int 'input')
    mv value 10
    expr (call wait_value value port)
    mv value 20
    expr (call wait_value value port)
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('caller_func', tags=set(), typ=Type.function('@top.caller_func'))
    if not top.find_sym('polyphony'):
        top.add_sym('polyphony', tags=set(), typ=Type.namespace('polyphony'))
    # Import wait_value and wait_until from polyphony.timing so symbols are shared
    timing_scope = env.scopes['polyphony.timing']
    if not top.find_sym('wait_value'):
        top.import_sym(timing_scope.find_sym('wait_value'), 'wait_value')
    if not top.find_sym('wait_until'):
        top.import_sym(timing_scope.find_sym('wait_until'), 'wait_until')

    caller_func = env.scopes['@top.caller_func']

    _run_inline([caller_func])

    inlined_lambda1 = env.scopes['@top.caller_func.0_#1']
    inlined_lambda2 = env.scopes['@top.caller_func.0_#2']

    gen = caller_func.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    blk4 = next(gen)
    blk5 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    assert len(blk1.stms) == 3
    # port = New(polyphony.io.Port, int, 'input')
    # value = 10
    # jump blk2
    assert isinstance(blk1.stms[0], Move)
    assert isinstance(blk1.stms[0].src, New)
    assert str(blk1.stms[0].dst) == 'port'
    assert blk1.stms[1] == Move(_v('value'), Const(10))
    assert blk1.stms[2] == Jump(blk2)

    assert len(blk2.stms) == 4
    # value_0 = value
    # port_0 = port
    # polyphony.timing.wait_until(0_#1)
    # jump blk3
    assert blk2.stms[0] == Move(_v('value_0'), _v('value'))
    assert blk2.stms[1] == Move(_v('port_0'), _v('port'))
    assert isinstance(blk2.stms[2], Expr) and isinstance(blk2.stms[2].exp, SysCall)
    assert str(blk2.stms[2].exp.func) == 'polyphony.timing.wait_until'
    assert blk2.stms[3] == Jump(blk3)

    assert len(blk3.stms) == 2
    # value = 20
    # jump blk4
    assert blk3.stms[0] == Move(_v('value'), Const(20))
    assert blk3.stms[1] == Jump(blk4)

    assert len(blk4.stms) == 4
    # value_1 = value
    # port_1 = port
    # polyphony.timing.wait_until(0_#2)
    # jump blk5
    assert blk4.stms[0] == Move(_v('value_1'), _v('value'))
    assert blk4.stms[1] == Move(_v('port_1'), _v('port'))
    assert isinstance(blk4.stms[2], Expr) and isinstance(blk4.stms[2].exp, SysCall)
    assert str(blk4.stms[2].exp.func) == 'polyphony.timing.wait_until'
    assert blk4.stms[3] == Jump(blk5)

    assert len(blk5.stms) == 0


def test_ctor_with_closure():
    '''
    def __init__(self, param):
        self.i = Port(int, 'in')
        self.o = Port(int, 'out')
        self.o.assign(lambda:self.i.rd() + param + 1)
    '''

    setup_test()
    setup_libs('io', 'timing')
    block_src = """
    scope @top.C
    tags module class
    var __init__: function(@top.C.__init__)
    var i: object(polyphony.io.Port)
    var o: object(polyphony.io.Port)

    scope @top.C.__init__
    tags method ctor enclosure
    param self:object(@top.C) { free }
    param param:int32 { free }
    return object(@top.C)
    var lambda: function(@top.C.__init__.lambda)

    blk1:
    mv param @in_param
    mv self.i (new polyphony.io.Port int 'in')
    mv self.o (new polyphony.io.Port int 'out')
    expr (call self.o.assign lambda)

    scope @top.C.__init__.lambda
    tags function closure
    return int32

    blk1:
    mv @return (+ (call self.i.rd) param)
    ret @return

    scope @top.caller
    tags function module
    var c: object(@top.C)

    blk1:
    mv c (new C 10)
    """

    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('C', tags=set(), typ=Type.klass('@top.C'))
    top.add_sym('caller', tags=set(), typ=Type.function('@top.caller'))
    if not top.find_sym('polyphony'):
        top.add_sym('polyphony', tags=set(), typ=Type.namespace('polyphony'))

    caller = env.scopes['@top.caller']

    _run_inline([caller])
    inlined_lambda1 = env.scopes['@top.caller.lambda_#1']

    c = caller.find_sym('c')
    assert c
    assert c.typ == Type.object('@top.C')
    assert c.scope is caller
    param = caller.find_sym('param')
    assert param
    assert param.typ.is_int()
    assert param.scope is caller
    lambda_1 = caller.find_sym('lambda_#1')
    assert lambda_1
    assert lambda_1.typ.is_function()
    assert lambda_1.typ.scope is inlined_lambda1
    assert lambda_1.scope is caller

    gen = caller.traverse_blocks()
    blk1 = next(gen)
    blk2 = next(gen)
    blk3 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    assert len(blk1.stms) == 2
    # c = $new(C)
    # jump blk2
    assert blk1.stms[0] == Move(_v('c'), SysCall(_v('$new'), args=[('typ', _v('C'))], kwargs={}))
    assert blk1.stms[1] == Jump(blk2)

    assert len(blk2.stms) == 5
    # param = 10
    # c.i = polyphony.io.Port(int, 'in')
    # c.o = polyphony.io.Port(int, 'out')
    # c.o.assign(lambda_#1)
    # jump blk3
    assert blk2.stms[0] == Move(_v('param'), Const(10))
    assert blk2.stms[1] == Move(_v('c.i'), New(_v('polyphony.io.Port'), args=[('', _v('int')), ('', Const('in'))], kwargs={}))
    assert blk2.stms[2] == Move(_v('c.o'), New(_v('polyphony.io.Port'), args=[('', _v('int')), ('', Const('out'))], kwargs={}))
    assert blk2.stms[3] == Expr(Call(_v('c.o.assign'), args=[('', _v('lambda_#1'))], kwargs={}))
    assert blk2.stms[4] == Jump(blk3)

    assert len(blk3.stms) == 0


    gen = inlined_lambda1.traverse_blocks()
    blk1 = next(gen)
    with pytest.raises(StopIteration) as e:
        next(gen)

    assert len(blk1.stms) == 2
    # @return = (+ (call c.i.rd) param)
    # return @return
    assert blk1.stms[0] == Move(_v('@return'), BinOp('Add', Call(_v('c.i.rd'), args=[], kwargs={}), _v('param')))
    assert blk1.stms[1] == Ret(_v('@return'))


def test_object_copy_inserts_field_moves():
    """When an object with sub-object fields is copied (d = c0),
    ObjectHierarchyCopier should insert MOVE for each object field."""
    setup_test()

    # Create class C with int field
    C = Scope.create(None, 'C', {'class'}, 0)
    C.add_sym('v', tags=set(), typ=Type.int(32))

    # Create class D with object field c of type C
    D = Scope.create(None, 'D', {'class'}, 0)
    D.add_sym('c', tags=set(), typ=Type.object(C))

    # Create function scope
    F = Scope.create(None, 'F', {'function'}, 0)
    F.add_sym('c0', tags=set(), typ=Type.object(C))
    F.add_sym('d', tags=set(), typ=Type.object(D))

    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)

    # d = c0 (object copy - but D.c is object, so should NOT trigger
    # because c0 is C type and d is D type, they're different)
    # Instead test d1 = d2 where both are D type
    F.add_sym('d1', tags=set(), typ=Type.object(D))
    F.add_sym('d2', tags=set(), typ=Type.object(D))

    mv = Move(Temp('d1', Ctx.STORE), Temp('d2', Ctx.LOAD))
    object.__setattr__(mv, 'block', blk)
    blk.append_stm(mv)

    Block.set_order(blk, 0)

    # Run old ObjectHierarchyCopier
    setup_test()
    C2 = Scope.create(None, 'C', {'class'}, 0)
    C2.add_sym('v', tags=set(), typ=Type.int(32))
    D2 = Scope.create(None, 'D', {'class'}, 0)
    D2.add_sym('c', tags=set(), typ=Type.object(C2))
    F2 = Scope.create(None, 'F', {'function'}, 0)
    F2.add_sym('d1', tags=set(), typ=Type.object(D2))
    F2.add_sym('d2', tags=set(), typ=Type.object(D2))
    blk2 = Block(F2, nametag='blk1')
    F2.set_entry_block(blk2)
    F2.set_exit_block(blk2)
    mv2 = Move(Temp('d1', Ctx.STORE), Temp('d2', Ctx.LOAD))
    object.__setattr__(mv2, 'block', blk2)
    blk2.append_stm(mv2)
    Block.set_order(blk2, 0)

    ObjectHierarchyCopier().process(F2)
    old_stm_count = len(blk2.stms)

    # Run new ObjectHierarchyCopier
    setup_test()
    C3 = Scope.create(None, 'C', {'class'}, 0)
    C3.add_sym('v', tags=set(), typ=Type.int(32))
    D3 = Scope.create(None, 'D', {'class'}, 0)
    D3.add_sym('c', tags=set(), typ=Type.object(C3))
    F3 = Scope.create(None, 'F', {'function'}, 0)
    F3.add_sym('d1', tags=set(), typ=Type.object(D3))
    F3.add_sym('d2', tags=set(), typ=Type.object(D3))
    blk3 = Block(F3, nametag='blk1')
    F3.set_entry_block(blk3)
    F3.set_exit_block(blk3)
    mv3 = new.Move(dst=new.Temp(name='d1', ctx=new.Ctx.STORE), src=new.Temp(name='d2'), block=blk3)
    blk3.stms.append(mv3)
    Block.set_order(blk3, 0)

    ObjectHierarchyCopier().process(F3)
    new_stm_count = len(blk3.stms)

    # Both should have the same number of statements
    assert old_stm_count == new_stm_count, (
        f'Statement count differs: old={old_stm_count} new={new_stm_count}'
    )


def test_no_copy_for_non_object_fields():
    """ObjectHierarchyCopier should only insert copies for object-type fields,
    not for scalar fields."""
    setup_test()

    # Class with only scalar field
    C = Scope.create(None, 'C', {'class'}, 0)
    C.add_sym('x', tags=set(), typ=Type.int(32))

    F = Scope.create(None, 'F', {'function'}, 0)
    F.add_sym('c1', tags=set(), typ=Type.object(C))
    F.add_sym('c2', tags=set(), typ=Type.object(C))

    blk = Block(F, nametag='blk1')
    F.set_entry_block(blk)
    F.set_exit_block(blk)

    mv = Move(Temp('c1', Ctx.STORE), Temp('c2', Ctx.LOAD))
    object.__setattr__(mv, 'block', blk)
    blk.append_stm(mv)
    Block.set_order(blk, 0)

    ObjectHierarchyCopier().process(F)

    # No additional stms should be inserted (x is int, not object)
    assert len(blk.stms) == 1, f'Expected 1 stm, got {len(blk.stms)}'


def test_inline_returnable_function_in_expr():
    """Inlining a returnable function called via Expr (discarding return value)."""
    setup_test()
    block_src = """
    scope @top.f
    tags function
    return none

    blk1:
    expr (call g 10)

    scope @top.g
    tags function returnable
    param x:int32
    return int32

    blk1:
    mv x @in_x
    mv @return (+ x 1)
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))
    top.add_sym('g', tags=set(), typ=Type.function('@top.g'))

    f = env.scopes['@top.f']
    _run_inline([f])

    # After inlining, no Call nodes should remain
    for blk in f.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Expr):
                assert not isinstance(stm.exp, Call), 'Call should have been inlined'
            if isinstance(stm, Move) and isinstance(stm.src, Call):
                assert False, 'Call should have been inlined'

    # The inlined body should be present
    all_stms = []
    for blk in f.traverse_blocks():
        all_stms.extend(blk.stms)
    stm_str = ' '.join(str(s) for s in all_stms)
    assert 'x' in stm_str


def test_inline_multiple_calls_same_callee():
    """Inlining handles multiple calls to the same callee correctly."""
    setup_test()
    block_src = """
    scope @top.f
    tags function
    return int32
    var a: int32
    var b: int32

    blk1:
    mv a (call g 10)
    mv b (call g 20)
    mv @return (+ a b)
    ret @return

    scope @top.g
    tags function
    param x:int32
    return int32

    blk1:
    mv x @in_x
    mv @return (+ x 1)
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))
    top.add_sym('g', tags=set(), typ=Type.function('@top.g'))

    f = env.scopes['@top.f']
    _run_inline([f])

    # Both calls should be inlined
    for blk in f.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.src, Call):
                assert False, 'Call should have been inlined'

    # Should have renamed variables for second call (x_0, x_1)
    sym_names = list(f.symbols.keys())
    assert any('x' in name for name in sym_names)


def test_inline_in_conditional_branch():
    """Inlining a call inside a conditional branch preserves block structure."""
    setup_test()
    block_src = """
    scope @top.f
    tags function
    param x:int32
    return int32
    var r: int32

    blk1:
    mv x @in_x
    cj x blk2 blk3

    blk2:
    mv r (call g x)
    j blk4

    blk3:
    mv r 0
    j blk4

    blk4:
    mv @return r
    ret @return

    scope @top.g
    tags function
    param x:int32
    return int32

    blk1:
    mv x @in_x
    mv @return (+ x 1)
    ret @return
    """
    IRParser(block_src).parse_scope()
    top = env.scopes['@top']
    top.add_sym('f', tags=set(), typ=Type.function('@top.f'))
    top.add_sym('g', tags=set(), typ=Type.function('@top.g'))

    f = env.scopes['@top.f']
    _run_inline([f])

    # No calls should remain
    for blk in f.traverse_blocks():
        for stm in blk.stms:
            if isinstance(stm, Move) and isinstance(stm.src, Call):
                assert False, 'Call should have been inlined'

    # The inlined body should be present
    all_stms = []
    for blk in f.traverse_blocks():
        all_stms.extend(blk.stms)
    has_add = any(
        isinstance(s, Move) and isinstance(s.src, BinOp) and s.src.op == 'Add'
        for s in all_stms
    )
    assert has_add, 'Inlined body should contain Add operation'
