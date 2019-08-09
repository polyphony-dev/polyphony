from polyphony.compiler.__main__ import earlytypeprop, typeprop, evaltype
from polyphony.compiler.env import env
from polyphony.compiler.type import Type
from polyphony.compiler.typecheck import TypePropagation
from polyphony.compiler.typecheck import TypeEvalVisitor
from base import CompilerTestCase
import unittest


class test_typeprop(CompilerTestCase):
    def setUp(self):
        super().setUp(earlytypeprop, order=1, before=True)

    test_implicit_1_src = '''
def test_implicit_1():
    a = 0
    b = True
    c = 'a'
    '''

    def test_implicit_1(self):
        self._run(self.test_implicit_1_src)
        scope = self.scope('test_implicit_1')
        a = scope.find_sym('a')
        b = scope.find_sym('b')
        c = scope.find_sym('c')

        self.assertTrue(a.typ.is_undef())
        self.assertTrue(b.typ.is_undef())
        self.assertTrue(c.typ.is_undef())
        self.assertTrue(not a.typ.is_explicit())
        self.assertTrue(not b.typ.is_explicit())
        self.assertTrue(not c.typ.is_explicit())

        typeprop = TypePropagation()
        typeprop.process(scope)

        self.assertTrue(a.typ.is_int())
        self.assertTrue(a.typ.get_width() == 32)
        self.assertTrue(a.typ.get_signed() is True)

        self.assertTrue(b.typ.is_bool())
        self.assertTrue(c.typ.is_str())

        self.assertTrue(not a.typ.is_explicit())
        self.assertTrue(not b.typ.is_explicit())
        self.assertTrue(not c.typ.is_explicit())

    test_implicit_2_src = '''
def test_implicit_2():
    a = [1, 2, 3]
    b = [True, False]
    c = ['a', 'b']
    '''

    def test_implicit_2(self):
        self._run(self.test_implicit_2_src)
        scope = self.scope('test_implicit_2')
        a = scope.find_sym('a')
        b = scope.find_sym('b')
        c = scope.find_sym('c')
        typeprop = TypePropagation()
        typeprop.process(scope)

        self.assertTrue(a.typ.is_list())
        self.assertTrue(a.typ.get_element().is_int())
        self.assertTrue(a.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(b.typ.is_list())
        self.assertTrue(b.typ.get_element().is_bool())
        self.assertTrue(b.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(c.typ.is_list())
        self.assertTrue(c.typ.get_element().is_str())
        self.assertTrue(c.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(not a.typ.is_explicit())
        self.assertTrue(not b.typ.is_explicit())
        self.assertTrue(not c.typ.is_explicit())

    test_implicit_3_src = '''
def test_implicit_3():
    a = (1, 2, 3)
    b = (True, False)
    c = ('a', 'b') * 2
    '''

    def test_implicit_3(self):
        self._run(self.test_implicit_3_src)
        scope = self.scope('test_implicit_3')
        a = scope.find_sym('a')
        b = scope.find_sym('b')
        c = scope.find_sym('c')
        typeprop = TypePropagation()
        typeprop.process(scope)

        self.assertTrue(a.typ.is_tuple())
        self.assertTrue(a.typ.get_element().is_int())
        self.assertTrue(a.typ.get_length() == 3)

        self.assertTrue(b.typ.is_tuple())
        self.assertTrue(b.typ.get_element().is_bool())
        self.assertTrue(b.typ.get_length() == 2)

        self.assertTrue(c.typ.is_tuple())
        self.assertTrue(c.typ.get_element().is_str())
        self.assertTrue(c.typ.get_length() == 4)

        self.assertTrue(not a.typ.is_explicit())
        self.assertTrue(not b.typ.is_explicit())
        self.assertTrue(not c.typ.is_explicit())

    test_explicit_1_src = '''
def test_explicit_1():
    a:int = 0
    b:bool = True
    c:str = 'a'
    '''

    def test_explicit_1(self):
        self._run(self.test_explicit_1_src)
        scope = self.scope('test_explicit_1')
        a = scope.find_sym('a')
        b = scope.find_sym('b')
        c = scope.find_sym('c')

        self.assertTrue(a.typ.is_int())
        self.assertTrue(a.typ.get_width() == 32)
        self.assertTrue(a.typ.get_signed())
        self.assertTrue(b.typ.is_bool())
        self.assertTrue(c.typ.is_str())
        self.assertTrue(a.typ.is_explicit())
        self.assertTrue(b.typ.is_explicit())
        self.assertTrue(c.typ.is_explicit())

        typeprop = TypePropagation()
        typeprop.process(scope)

        self.assertTrue(a.typ.is_int())
        self.assertTrue(a.typ.get_width() == 32)
        self.assertTrue(a.typ.get_signed())
        self.assertTrue(b.typ.is_bool())
        self.assertTrue(c.typ.is_str())
        self.assertTrue(a.typ.is_explicit())
        self.assertTrue(b.typ.is_explicit())
        self.assertTrue(c.typ.is_explicit())

    test_explicit_2_src = '''
def test_explicit_2(n):
    a:list = [1, 2, 3]
    b:list = [True, False]
    c:list = ['a', 'b'] * 2
    d:list = ['a', 'b'] * n
    '''

    def test_explicit_2(self):
        self._run(self.test_explicit_2_src)
        scope = self.scope('test_explicit_2')
        a = scope.find_sym('a')
        b = scope.find_sym('b')
        c = scope.find_sym('c')
        d = scope.find_sym('d')

        self.assertTrue(a.typ.is_list())
        self.assertTrue(a.typ.get_element().is_undef())
        self.assertTrue(a.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(b.typ.is_list())
        self.assertTrue(b.typ.get_element().is_undef())
        self.assertTrue(b.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(c.typ.is_list())
        self.assertTrue(c.typ.get_element().is_undef())
        self.assertTrue(c.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(d.typ.is_list())
        self.assertTrue(d.typ.get_element().is_undef())
        self.assertTrue(d.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(a.typ.is_explicit())
        self.assertTrue(not a.typ.get_element().is_explicit())
        self.assertTrue(b.typ.is_explicit())
        self.assertTrue(not b.typ.get_element().is_explicit())
        self.assertTrue(c.typ.is_explicit())
        self.assertTrue(not c.typ.get_element().is_explicit())
        self.assertTrue(d.typ.is_explicit())
        self.assertTrue(not d.typ.get_element().is_explicit())

        typeprop = TypePropagation()
        typeprop.process(scope)

        self.assertTrue(a.typ.is_list())
        self.assertTrue(a.typ.get_element().is_int())
        self.assertTrue(a.typ.get_element().get_width() == 32)
        self.assertTrue(a.typ.get_element().get_signed() is True)
        self.assertTrue(a.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(b.typ.is_list())
        self.assertTrue(b.typ.get_element().is_bool())
        self.assertTrue(b.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(c.typ.is_list())
        self.assertTrue(c.typ.get_element().is_str())
        self.assertTrue(c.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(d.typ.is_list())
        self.assertTrue(d.typ.get_element().is_str())
        self.assertTrue(d.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(a.typ.is_explicit())
        self.assertTrue(not a.typ.get_element().is_explicit())
        self.assertTrue(b.typ.is_explicit())
        self.assertTrue(not b.typ.get_element().is_explicit())
        self.assertTrue(c.typ.is_explicit())
        self.assertTrue(not c.typ.get_element().is_explicit())
        self.assertTrue(d.typ.is_explicit())
        self.assertTrue(not d.typ.get_element().is_explicit())

    test_explicit_3_src = '''
def test_explicit_3(n):
    a:tuple = (1, 2, 3)
    b:tuple = (True, False)
    c:tuple = ('a', 'b') * 2
    d:tuple = ('a', 'b') * n
    '''

    def test_explicit_3(self):
        self._run(self.test_explicit_3_src)
        scope = self.scope('test_explicit_3')
        a = scope.find_sym('a')
        b = scope.find_sym('b')
        c = scope.find_sym('c')
        d = scope.find_sym('d')

        self.assertTrue(a.typ.is_tuple())
        self.assertTrue(a.typ.get_element().is_undef())
        self.assertTrue(a.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(b.typ.is_tuple())
        self.assertTrue(b.typ.get_element().is_undef())
        self.assertTrue(b.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(c.typ.is_tuple())
        self.assertTrue(c.typ.get_element().is_undef())
        self.assertTrue(c.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(d.typ.is_tuple())
        self.assertTrue(d.typ.get_element().is_undef())
        self.assertTrue(d.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(a.typ.is_explicit())
        self.assertTrue(not a.typ.get_element().is_explicit())
        self.assertTrue(b.typ.is_explicit())
        self.assertTrue(not b.typ.get_element().is_explicit())
        self.assertTrue(c.typ.is_explicit())
        self.assertTrue(not c.typ.get_element().is_explicit())
        self.assertTrue(d.typ.is_explicit())
        self.assertTrue(not d.typ.get_element().is_explicit())

        typeprop = TypePropagation()
        typeprop.process(scope)

        self.assertTrue(a.typ.is_tuple())
        self.assertTrue(a.typ.get_element().is_int())
        self.assertTrue(a.typ.get_element().get_width() == 32)
        self.assertTrue(a.typ.get_element().get_signed() is True)
        self.assertTrue(a.typ.get_length() == 3)

        self.assertTrue(b.typ.is_tuple())
        self.assertTrue(b.typ.get_element().is_bool())
        self.assertTrue(b.typ.get_length() == 2)

        self.assertTrue(c.typ.is_tuple())
        self.assertTrue(c.typ.get_element().is_str())
        self.assertTrue(c.typ.get_length() == 4)

        self.assertTrue(d.typ.is_tuple())
        self.assertTrue(d.typ.get_element().is_str())
        self.assertTrue(d.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(a.typ.is_explicit())
        self.assertTrue(not a.typ.get_element().is_explicit())
        self.assertTrue(b.typ.is_explicit())
        self.assertTrue(not b.typ.get_element().is_explicit())
        self.assertTrue(c.typ.is_explicit())
        self.assertTrue(not c.typ.get_element().is_explicit())
        self.assertTrue(d.typ.is_explicit())
        self.assertTrue(not d.typ.get_element().is_explicit())

    test_explicit_4_src = '''
from polyphony.typing import List

def test_explicit_4(n):
    a:List[int] = [1, 2, 3]
    b:List[bool] = [True, False]
    c:List[str] = ['a', 'b'] * 2
    d:List[str] = ['a', 'b'] * n
    '''

    def test_explicit_4(self):
        self._run(self.test_explicit_4_src)
        scope = self.scope('test_explicit_4')
        a = scope.find_sym('a')
        b = scope.find_sym('b')
        c = scope.find_sym('c')
        d = scope.find_sym('d')

        self.assertTrue(a.typ.is_list())
        self.assertTrue(a.typ.get_element().is_int())
        self.assertTrue(a.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(b.typ.is_list())
        self.assertTrue(b.typ.get_element().is_bool())
        self.assertTrue(b.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(c.typ.is_list())
        self.assertTrue(c.typ.get_element().is_str())
        self.assertTrue(c.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(d.typ.is_list())
        self.assertTrue(d.typ.get_element().is_str())
        self.assertTrue(d.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(a.typ.is_explicit())
        self.assertTrue(a.typ.get_element().is_explicit())
        self.assertTrue(b.typ.is_explicit())
        self.assertTrue(b.typ.get_element().is_explicit())
        self.assertTrue(c.typ.is_explicit())
        self.assertTrue(c.typ.get_element().is_explicit())
        self.assertTrue(d.typ.is_explicit())
        self.assertTrue(d.typ.get_element().is_explicit())

        typeprop = TypePropagation()
        typeprop.process(scope)

        self.assertTrue(a.typ.is_list())
        self.assertTrue(a.typ.get_element().is_int())
        self.assertTrue(a.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(b.typ.is_list())
        self.assertTrue(b.typ.get_element().is_bool())
        self.assertTrue(b.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(c.typ.is_list())
        self.assertTrue(c.typ.get_element().is_str())
        self.assertTrue(c.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(d.typ.is_list())
        self.assertTrue(d.typ.get_element().is_str())
        self.assertTrue(d.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(a.typ.is_explicit())
        self.assertTrue(a.typ.get_element().is_explicit())
        self.assertTrue(b.typ.is_explicit())
        self.assertTrue(b.typ.get_element().is_explicit())
        self.assertTrue(c.typ.is_explicit())
        self.assertTrue(c.typ.get_element().is_explicit())
        self.assertTrue(d.typ.is_explicit())
        self.assertTrue(d.typ.get_element().is_explicit())

    test_explicit_5_src = '''
from polyphony.typing import Tuple

def test_explicit_5(n):
    a:Tuple[int, ...] = (1, 2, 3)
    b:Tuple[bool, ...] = (True, False)
    c:Tuple[str, ...] = ('a', 'b') * 2
    d:Tuple[str, ...] = ('a', 'b') * n
    '''

    def test_explicit_5(self):
        self._run(self.test_explicit_5_src)
        scope = self.scope('test_explicit_5')
        a = scope.find_sym('a')
        b = scope.find_sym('b')
        c = scope.find_sym('c')
        d = scope.find_sym('d')

        self.assertTrue(a.typ.is_tuple())
        self.assertTrue(a.typ.get_element().is_int())
        self.assertTrue(a.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(b.typ.is_tuple())
        self.assertTrue(b.typ.get_element().is_bool())
        self.assertTrue(b.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(c.typ.is_tuple())
        self.assertTrue(c.typ.get_element().is_str())
        self.assertTrue(c.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(d.typ.is_tuple())
        self.assertTrue(d.typ.get_element().is_str())
        self.assertTrue(d.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(a.typ.is_explicit())
        self.assertTrue(a.typ.get_element().is_explicit())
        self.assertTrue(b.typ.is_explicit())
        self.assertTrue(b.typ.get_element().is_explicit())
        self.assertTrue(c.typ.is_explicit())
        self.assertTrue(c.typ.get_element().is_explicit())
        self.assertTrue(d.typ.is_explicit())
        self.assertTrue(d.typ.get_element().is_explicit())

        typeprop = TypePropagation()
        typeprop.process(scope)

        self.assertTrue(a.typ.is_tuple())
        self.assertTrue(a.typ.get_element().is_int())
        self.assertTrue(a.typ.get_length() == 3)

        self.assertTrue(b.typ.is_tuple())
        self.assertTrue(b.typ.get_element().is_bool())
        self.assertTrue(b.typ.get_length() == 2)

        self.assertTrue(c.typ.is_tuple())
        self.assertTrue(c.typ.get_element().is_str())
        self.assertTrue(c.typ.get_length() == 4)

        self.assertTrue(d.typ.is_tuple())
        self.assertTrue(d.typ.get_element().is_str())
        self.assertTrue(d.typ.get_length() == Type.ANY_LENGTH)

        self.assertTrue(a.typ.is_explicit())
        self.assertTrue(a.typ.get_element().is_explicit())
        self.assertTrue(b.typ.is_explicit())
        self.assertTrue(b.typ.get_element().is_explicit())
        self.assertTrue(c.typ.is_explicit())
        self.assertTrue(c.typ.get_element().is_explicit())
        self.assertTrue(d.typ.is_explicit())
        self.assertTrue(d.typ.get_element().is_explicit())

    test_call_1_src = '''
def f(x):
    return x

def test_call_1():
    a = f(True)
    '''

    def test_call_1(self):
        self._run(self.test_call_1_src)
        scope = self.scope('test_call_1')
        scope_f = self.scope('f')
        a = scope.find_sym('a')
        f = scope.find_sym('f')
        f_x = scope_f.find_sym('x')

        self.assertTrue(a.typ.is_undef())
        self.assertTrue(not a.typ.is_explicit())

        self.assertTrue(f.typ.is_function())
        self.assertTrue(f.typ.get_return_type().is_undef())
        pts = f.typ.get_param_types()
        self.assertTrue(len(pts) == 0)

        self.assertTrue(f_x.typ.is_int())
        self.assertTrue(not f_x.typ.is_explicit())

        typeprop = TypePropagation()
        typeprop.process(scope)
        self.assertTrue(len(typeprop.untyped) == 1)
        typeprop.untyped.clear()
        self.assertTrue(a.typ.is_undef())
        self.assertTrue(f.typ.is_function())
        self.assertTrue(f.typ.get_return_type().is_undef())
        pts = f.typ.get_param_types()
        self.assertTrue(len(pts) == 1)
        self.assertTrue(pts[0].is_bool())
        self.assertTrue(not pts[0].is_explicit())

        typeprop.process(scope_f)
        typeprop.process(scope)
        self.assertTrue(len(typeprop.untyped) == 0)

        self.assertTrue(a.typ.is_bool())

        self.assertTrue(f.typ.is_function())
        self.assertTrue(f.typ.get_return_type().is_bool())
        pts = f.typ.get_param_types()
        self.assertTrue(len(pts) == 1)
        self.assertTrue(pts[0].is_bool())
        self.assertTrue(not pts[0].is_explicit())

        self.assertTrue(f_x.typ.is_bool())
        self.assertTrue(not f_x.typ.is_explicit())


class test_typeexpr_static(CompilerTestCase):
    def setUp(self):
        super().setUp(evaltype, order=0, before=True)

    test_expr_1_src = '''
from polyphony.typing import List

size = 3
xs:List[int][size] = [0, 1, 2]
    '''

    def test_expr_1(self):
        self._run(self.test_expr_1_src)
        scope = env.scopes['@top']
        xs = scope.find_sym('xs')

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(xs.typ.get_length().is_expr())

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

        typeeval = TypeEvalVisitor()
        typeeval.process(scope)

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(isinstance(xs.typ.get_length(), int))
        self.assertTrue(xs.typ.get_length() == 3)

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

    test_expr_2_src = '''
from polyphony.typing import List

class C:
    size = 3
    xs:List[int][size] = [0, 1, 2]
    '''

    def test_expr_2(self):
        self._run(self.test_expr_2_src)
        scope = self.scope('C')
        xs = scope.find_sym('xs')

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(xs.typ.get_length().is_expr())

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

        typeeval = TypeEvalVisitor()
        typeeval.process(scope)

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(isinstance(xs.typ.get_length(), int))
        self.assertTrue(xs.typ.get_length() == 3)

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())


class test_typeexpr(CompilerTestCase):
    def setUp(self):
        super().setUp(evaltype, order=1, before=True)
        #super().setUp(typeprop, order=4, before=True)

    test_expr_1_src = '''
from polyphony.typing import List

def test_expr_1():
    size = 3
    xs:List[int][size] = [0, 1, 2]

test_expr_1()
    '''

    def test_expr_1(self):
        self._run(self.test_expr_1_src)
        scope = self.scope('test_expr_1')
        xs = scope.find_sym('xs')

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(xs.typ.get_length().is_expr())

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

        typeeval = TypeEvalVisitor()
        typeeval.process(scope)

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(isinstance(xs.typ.get_length(), int))
        self.assertTrue(xs.typ.get_length() == 3)

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

    test_expr_2_src = '''
from polyphony.typing import List


size = 2
class C:
    size = 3

def test_expr_2():
    xs:List[int][size] = [0, 1]
    ys:List[int][C.size] = [0, 1, 2]

test_expr_2()
    '''

    def test_expr_2(self):
        self._run(self.test_expr_2_src)
        scope = self.scope('test_expr_2')
        xs = scope.find_sym('xs')
        ys = scope.find_sym('ys')

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(xs.typ.get_length().is_expr())

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

        self.assertTrue(ys.typ.is_list())
        self.assertTrue(ys.typ.get_element().is_int())
        self.assertTrue(ys.typ.get_length().is_expr())

        self.assertTrue(ys.typ.is_explicit())
        self.assertTrue(ys.typ.get_element().is_explicit())

        typeeval = TypeEvalVisitor()
        typeeval.process(scope)

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(isinstance(xs.typ.get_length(), int))
        self.assertTrue(xs.typ.get_length() == 2)

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

        self.assertTrue(ys.typ.is_list())
        self.assertTrue(ys.typ.get_element().is_int())
        self.assertTrue(isinstance(ys.typ.get_length(), int))
        self.assertTrue(ys.typ.get_length() == 3)

        self.assertTrue(ys.typ.is_explicit())
        self.assertTrue(ys.typ.get_element().is_explicit())

    test_expr_3_src = '''
from polyphony.typing import List

def f(size):
    xs:List[int][size] = [0] * size
    return xs[0]

def test_expr_3():
    return f(3)

test_expr_3()
    '''

    def test_expr_3(self):
        self._run(self.test_expr_3_src)
        scope = self.scope('test_expr_3')
        xs = self.find_symbol(scope, 'xs')

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(xs.typ.get_length().is_expr())

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

        typeeval = TypeEvalVisitor()
        typeeval.process(scope)

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(isinstance(xs.typ.get_length(), int))
        self.assertTrue(xs.typ.get_length() == 3)

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

    test_expr_4_src = '''
from polyphony.typing import List

class C:
    def __init__(self, size):
        self.size = size

    def f(self, idx):
        xs:List[int][self.size] = [0] * self.size
        return xs[idx]

class D:
    def f(self, idx, size):
        ys:List[int][size] = [0] * size
        return ys[idx]


def test_expr_4():
    c = C(4)
    x = c.f(0)
    d = D()
    y = d.f(0, 5)
    return x + y

test_expr_4()
    '''

    def test_expr_4(self):
        self._run(self.test_expr_4_src)
        scope = self.scope('test_expr_4')
        xs = self.find_symbol(scope, 'xs')
        ys = self.find_symbol(scope, 'ys')

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(xs.typ.get_length().is_expr())

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

        self.assertTrue(ys.typ.is_list())
        self.assertTrue(ys.typ.get_element().is_int())
        self.assertTrue(ys.typ.get_length().is_expr())

        self.assertTrue(ys.typ.is_explicit())
        self.assertTrue(ys.typ.get_element().is_explicit())

        typeeval = TypeEvalVisitor()
        typeeval.process(scope)

        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(isinstance(xs.typ.get_length(), int))
        self.assertTrue(xs.typ.get_length() == 4)

        self.assertTrue(xs.typ.is_explicit())
        self.assertTrue(xs.typ.get_element().is_explicit())

        self.assertTrue(ys.typ.is_list())
        self.assertTrue(ys.typ.get_element().is_int())
        self.assertTrue(isinstance(ys.typ.get_length(), int))
        self.assertTrue(ys.typ.get_length() == 5)

        self.assertTrue(ys.typ.is_explicit())
        self.assertTrue(ys.typ.get_element().is_explicit())

    test_expr_5_src = '''
from polyphony import module
from polyphony.typing import List

@module
class test_expr_5:
    def __init__(self, size):
        self.mem:List[int][size] = [None] * size

m = test_expr_5(10)
    '''

    def test_expr_5(self):
        self._run(self.test_expr_5_src)
        scope = self.scope('test_expr_5_m')
        self.assertTrue(scope.is_module())
        self.assertTrue(scope.is_instantiated())
        mem = self.find_symbol(scope, 'mem')

        self.assertTrue(mem.typ.is_list())
        self.assertTrue(mem.typ.get_element().is_int())
        self.assertTrue(mem.typ.get_length().is_expr())

        self.assertTrue(mem.typ.is_explicit())
        self.assertTrue(mem.typ.get_element().is_explicit())

        typeeval = TypeEvalVisitor()
        typeeval.process(scope.find_ctor())

        self.assertTrue(mem.typ.is_list())
        self.assertTrue(mem.typ.get_element().is_int())
        self.assertTrue(isinstance(mem.typ.get_length(), int))
        self.assertTrue(mem.typ.get_length() == 10)

        self.assertTrue(mem.typ.is_explicit())
        self.assertTrue(mem.typ.get_element().is_explicit())

    test_expr_6_src = '''
from polyphony import module
from polyphony.typing import List
from polyphony.io import Port


@module
class test_expr_6:
    def __init__(self, size):
        self.size = size
        self.append_worker(self.func)
        self.p = Port(int, 'out')

    def func(self):
        mem:List[int][self.size] = [None] * self.size
        self.p.wr(mem[0])

m = test_expr_6(10)
    '''

    def test_expr_6(self):
        self._run(self.test_expr_6_src)
        scope = self.scope('test_expr_6_m')
        self.assertTrue(scope.is_module())
        self.assertTrue(scope.is_instantiated())
        func_scope, _ = scope.workers[0]
        mem = self.find_symbol(func_scope, 'mem')

        self.assertTrue(mem.typ.is_list())
        self.assertTrue(mem.typ.get_element().is_int())
        self.assertTrue(mem.typ.get_length().is_expr())

        self.assertTrue(mem.typ.is_explicit())
        self.assertTrue(mem.typ.get_element().is_explicit())

        typeeval = TypeEvalVisitor()
        typeeval.process(func_scope)

        self.assertTrue(mem.typ.is_list())
        self.assertTrue(mem.typ.get_element().is_int())
        self.assertTrue(isinstance(mem.typ.get_length(), int))
        self.assertTrue(mem.typ.get_length() == 10)

        self.assertTrue(mem.typ.is_explicit())
        self.assertTrue(mem.typ.get_element().is_explicit())

    test_expr_7_src = '''
from polyphony import module
from polyphony.typing import List
from polyphony.io import Port


def worker(p, sz):
    mem:List[int][sz] = [None] * sz
    p.wr(mem[0])

@module
class test_expr_7:
    def __init__(self, size0, size1):
        self.p0 = Port(int, 'out')
        self.p1 = Port(int, 'out')
        self.append_worker(worker, self.p0, size0)
        self.append_worker(worker, self.p1, size1)

m = test_expr_7(11, 12)
    '''

    def test_expr_7(self):
        self._run(self.test_expr_7_src)
        scope = self.scope('test_expr_7_m')
        self.assertTrue(scope.is_module())
        self.assertTrue(scope.is_instantiated())
        w0, _ = scope.workers[0]
        w1, _ = scope.workers[1]

        if w0.orig_name.endswith('11'):
            mem0 = self.find_symbol(w0, 'mem')
            mem1 = self.find_symbol(w1, 'mem')
        else:
            mem0 = self.find_symbol(w1, 'mem')
            mem1 = self.find_symbol(w0, 'mem')

        self.assertTrue(mem0.typ.is_list())
        self.assertTrue(mem0.typ.get_element().is_int())
        self.assertTrue(mem0.typ.get_length().is_expr())

        self.assertTrue(mem0.typ.is_explicit())
        self.assertTrue(mem0.typ.get_element().is_explicit())

        self.assertTrue(mem1.typ.is_list())
        self.assertTrue(mem1.typ.get_element().is_int())
        self.assertTrue(mem1.typ.get_length().is_expr())

        self.assertTrue(mem1.typ.is_explicit())
        self.assertTrue(mem1.typ.get_element().is_explicit())

        typeeval = TypeEvalVisitor()
        typeeval.process(w0)
        typeeval.process(w1)

        self.assertTrue(mem0.typ.is_list())
        self.assertTrue(mem0.typ.get_element().is_int())
        self.assertTrue(isinstance(mem0.typ.get_length(), int))
        self.assertTrue(mem0.typ.get_length() == 11)

        self.assertTrue(mem0.typ.is_explicit())
        self.assertTrue(mem0.typ.get_element().is_explicit())

        self.assertTrue(mem1.typ.is_list())
        self.assertTrue(mem1.typ.get_element().is_int())
        self.assertTrue(isinstance(mem1.typ.get_length(), int))
        self.assertTrue(mem1.typ.get_length() == 12)

        self.assertTrue(mem1.typ.is_explicit())
        self.assertTrue(mem1.typ.get_element().is_explicit())


class test_alias_type(CompilerTestCase):
    def setUp(self):
        # super().setUp(evaltype, order=1, before=True)
        super().setUp(earlytypeprop, order=0, before=True)

    test_alias_1_src = '''
from polyphony.typing import Type, int8

int_t1 = int8
int_t2:Type[int8] = int8

i1:int_t1 = 0
i2:int_t2 = 0
    '''

    def test_alias_1(self):
        self._run(self.test_alias_1_src)
        top = env.scopes['@top']
        int_t1 = top.find_sym('int_t1')
        int_t2 = top.find_sym('int_t2')
        i1 = top.find_sym('i1')
        i2 = top.find_sym('i2')
        self.assertTrue(int_t1.typ.is_undef())
        self.assertTrue(i1.typ.is_expr())

        self.assertTrue(int_t2.typ.is_class())
        self.assertTrue(int_t2.typ.get_scope().is_typeclass())
        self.assertTrue(int_t2.typ.get_scope().name == '__builtin__.int')
        self.assertTrue(i2.typ.is_int())
        self.assertTrue(i2.typ.get_width() == 8)

        TypePropagation().process(top)

        self.assertTrue(int_t1.typ.is_class())
        self.assertTrue(int_t1.typ.get_scope().is_typeclass())
        self.assertTrue(int_t1.typ.get_scope().name == '__builtin__.int')
        self.assertTrue(i1.typ.is_expr())
        self.assertTrue(int_t2.typ.is_class())
        self.assertTrue(int_t2.typ.get_scope().is_typeclass())
        self.assertTrue(int_t2.typ.get_scope().name == '__builtin__.int')

        TypeEvalVisitor().process(top)

        self.assertTrue(i1.typ.is_int())
        self.assertTrue(i1.typ.get_width() == 8)

        self.assertTrue(i2.typ.is_int())
        self.assertTrue(i2.typ.get_width() == 8)

    test_alias_2_src = '''
from polyphony.typing import Type, List, int8

vec_t1 = List[int8]
vec_t2:Type[List[int8]] = List[int8]

v1:vec_t1 = [0]
v2:vec_t2 = [0]
    '''

    def test_alias_2(self):
        self._run(self.test_alias_2_src)
        top = env.scopes['@top']
        vec_t1 = top.find_sym('vec_t1')
        vec_t2 = top.find_sym('vec_t2')
        v1 = top.find_sym('v1')
        v2 = top.find_sym('v2')
        self.assertTrue(vec_t1.typ.is_undef())
        self.assertTrue(v1.typ.is_expr())

        self.assertTrue(vec_t2.typ.is_class())
        self.assertTrue(vec_t2.typ.get_scope().is_typeclass())
        self.assertTrue(vec_t2.typ.get_scope().name == '__builtin__.list')
        self.assertTrue('element' in vec_t2.typ.get_typeargs())
        self.assertTrue(vec_t2.typ.get_typeargs()['element'].is_int())
        self.assertTrue(v2.typ.is_list())
        self.assertTrue(v2.typ.get_element().is_int())
        self.assertTrue(v2.typ.get_element().get_width() == 8)

        TypePropagation().process(top)
        self.assertTrue(vec_t1.typ.is_class())
        self.assertTrue(vec_t1.typ.get_scope().is_typeclass())
        self.assertTrue(vec_t1.typ.get_scope().name == '__builtin__.list')
        self.assertTrue(vec_t2.typ.is_class())
        self.assertTrue(vec_t2.typ.get_scope().is_typeclass())
        self.assertTrue(vec_t2.typ.get_scope().name == '__builtin__.list')

        TypeEvalVisitor().process(top)

        self.assertTrue(v1.typ.is_list())
        self.assertTrue(v1.typ.get_element().is_int())
        self.assertTrue(v1.typ.get_element().get_width() == 8)

        self.assertTrue(v2.typ.is_list())
        self.assertTrue(v2.typ.get_element().is_int())
        self.assertTrue(v2.typ.get_element().get_width() == 8)

    test_alias_3_src = '''
from polyphony.typing import Type, List, int8

vec_t1 = List[int8][3]
vec_t2:Type[List[int8][3]] = List[int8][3]

v1:vec_t1 = [0, 1, 2]
v2:vec_t2 = [0, 1, 2]
    '''

    def test_alias_3(self):
        self._run(self.test_alias_3_src)
        top = env.scopes['@top']
        vec_t1 = top.find_sym('vec_t1')
        vec_t2 = top.find_sym('vec_t2')
        v1 = top.find_sym('v1')
        v2 = top.find_sym('v2')
        self.assertTrue(vec_t1.typ.is_undef())
        self.assertTrue(v1.typ.is_expr())

        self.assertTrue(vec_t2.typ.is_class())
        self.assertTrue(vec_t2.typ.get_scope().is_typeclass())
        self.assertTrue(vec_t2.typ.get_scope().name == '__builtin__.list')
        self.assertTrue('element' in vec_t2.typ.get_typeargs())
        self.assertTrue(vec_t2.typ.get_typeargs()['element'].is_int())
        self.assertTrue(v2.typ.is_list())
        self.assertTrue(v2.typ.get_element().is_int())
        self.assertTrue(v2.typ.get_element().get_width() == 8)
        self.assertTrue(v2.typ.get_length() == 3)

        TypePropagation().process(top)
        self.assertTrue(vec_t1.typ.is_class())
        self.assertTrue(vec_t1.typ.get_scope().is_typeclass())
        self.assertTrue(vec_t1.typ.get_scope().name == '__builtin__.list')
        self.assertTrue(vec_t2.typ.is_class())
        self.assertTrue(vec_t2.typ.get_scope().is_typeclass())
        self.assertTrue(vec_t2.typ.get_scope().name == '__builtin__.list')

        TypeEvalVisitor().process(top)

        self.assertTrue(v1.typ.is_list())
        self.assertTrue(v1.typ.get_element().is_int())
        self.assertTrue(v1.typ.get_element().get_width() == 8)
        self.assertTrue(v1.typ.get_length() == 3)

        self.assertTrue(v2.typ.is_list())
        self.assertTrue(v2.typ.get_element().is_int())
        self.assertTrue(v2.typ.get_element().get_width() == 8)
        self.assertTrue(v2.typ.get_length() == 3)

    test_alias_4_src = '''
from polyphony.typing import Type, Int

byte_t1 = Int[8]
byte_t2:Type[Int[8]] = Int[8]

b1:byte_t1 = 0
b2:byte_t2 = 0
    '''

    def test_alias_4(self):
        self._run(self.test_alias_4_src)
        top = env.scopes['@top']
        byte_t1 = top.find_sym('byte_t1')
        byte_t2 = top.find_sym('byte_t2')
        b1 = top.find_sym('b1')
        b2 = top.find_sym('b2')
        self.assertTrue(byte_t1.typ.is_undef())
        self.assertTrue(b1.typ.is_expr())

        self.assertTrue(byte_t2.typ.is_class())
        self.assertTrue(byte_t2.typ.get_scope().is_typeclass())
        self.assertTrue(byte_t2.typ.get_scope().name == '__builtin__.int')
        self.assertTrue('width' in byte_t2.typ.get_typeargs())
        self.assertTrue(byte_t2.typ.get_typeargs()['width'] == 8)
        self.assertTrue(b2.typ.is_int())
        self.assertTrue(b2.typ.get_width() == 8)

        TypePropagation().process(top)
        self.assertTrue(byte_t1.typ.is_class())
        self.assertTrue(byte_t1.typ.get_scope().is_typeclass())
        self.assertTrue(byte_t1.typ.get_scope().name == '__builtin__.int')
        self.assertTrue('width' in byte_t1.typ.get_typeargs())
        self.assertTrue(byte_t1.typ.get_typeargs()['width'] == 8)

        self.assertTrue(byte_t2.typ.is_class())
        self.assertTrue(byte_t2.typ.get_scope().is_typeclass())
        self.assertTrue(byte_t2.typ.get_scope().name == '__builtin__.int')
        self.assertTrue('width' in byte_t2.typ.get_typeargs())
        self.assertTrue(byte_t2.typ.get_typeargs()['width'] == 8)

        TypeEvalVisitor().process(top)

        self.assertTrue(b1.typ.is_int())
        self.assertTrue(b1.typ.get_width() == 8)

        self.assertTrue(b2.typ.is_int())
        self.assertTrue(b2.typ.get_width() == 8)


if __name__ == '__main__':
    unittest.main()
