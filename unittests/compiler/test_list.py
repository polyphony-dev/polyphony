from polyphony.compiler.__main__ import earlytypeprop, objssa, hyperblock
from polyphony.compiler.ir.type import Type
from polyphony.compiler.ir.ir import *
from base import CompilerTestCase
import unittest


class test_list_type(CompilerTestCase):
    def setUp(self):
        super().setUp(earlytypeprop, order=0, before=False)

    test_list_arg_1_src = '''
def f(xs):
    return xs[0]

def test_list_arg():
    xs = [1, 2, 3]
    f(xs)

    ys = ['1', '2', '3']
    f(ys)

    zs = [1, 2, 3, 4]
    f(zs)

test_list_arg()
    '''

    def test_list_arg_1(self):
        self._run(self.test_list_arg_1_src)

        scope = self.scope('test_list_arg')
        xs = scope.find_sym('xs')
        ys = scope.find_sym('ys')
        zs = scope.find_sym('zs')
        self.assertTrue(xs.typ.is_list())
        self.assertTrue(xs.typ.get_element().is_int())
        self.assertTrue(xs.typ.get_length() == Type.ANY_LENGTH)
        self.assertTrue(ys.typ.is_list())
        self.assertTrue(ys.typ.get_element().is_str())
        self.assertTrue(ys.typ.get_length() == Type.ANY_LENGTH)
        self.assertTrue(zs.typ.is_list())
        self.assertTrue(zs.typ.get_element().is_int())
        self.assertTrue(zs.typ.get_length() == Type.ANY_LENGTH)

        param_name = Type.mangled_names([Type.list(Type.int())])
        f_i = self.scope(f'f_{param_name}')
        arg_t = f_i.param_types()[0]
        self.assertTrue(arg_t.is_list())
        self.assertTrue(arg_t.get_element().is_int())
        self.assertTrue(arg_t.get_length() == Type.ANY_LENGTH)

        param_name = Type.mangled_names([Type.list(Type.str())])
        f_s = self.scope(f'f_{param_name}')
        arg_t = f_s.param_types()[0]
        self.assertTrue(arg_t.is_list())
        self.assertTrue(arg_t.get_element().is_str())
        self.assertTrue(arg_t.get_length() == Type.ANY_LENGTH)


class test_list_ssa(CompilerTestCase):
    def setUp(self):
        super().setUp(objssa, order=0, before=False)

    test_list_ssa_1_src = '''
def test_list_ssa(p, q):
    xs = [1, 2, 3]
    ys = [4, 5, 6]

    if p:
        zs = xs
    else:
        zs = ys
    if q:
        idx = 0
    else:
        idx = 1
    return zs[idx]

test_list_ssa(True, True)
    '''

    def test_list_ssa_1(self):
        self._run(self.test_list_ssa_1_src)

        param_name = Type.mangled_names([Type.bool(), Type.bool()])
        scope = self.scope(f'test_list_ssa_{param_name}')
        xs = scope.find_sym('xs#1')
        ys = scope.find_sym('ys#1')
        zs1 = scope.find_sym('zs#1')
        zs2 = scope.find_sym('zs#2')
        self.assertIsNotNone(xs)
        self.assertIsNotNone(ys)
        self.assertIsNotNone(zs1)
        self.assertIsNotNone(zs2)
        stms = scope.usedef.get_stms_using(zs1)
        self.assertTrue(len(stms) == 1)
        uphi = list(stms)[0]
        self.assertTrue(uphi.is_a(UPHI))


class test_list_hyperblock(CompilerTestCase):
    def setUp(self):
        super().setUp(hyperblock, order=0, before=False)

    test_list_hyperblock_1_src = '''
def test_list_hyperblock(p, q):
    xs = [1, 2, 3]
    ys = [4, 5, 6]

    if p:
        zs = xs
    else:
        zs = ys
    if q:
        idx = 0
    else:
        idx = 1
    return zs[idx]

test_list_hyperblock(True, True)
    '''

    def test_list_hyperblock_1(self):
        self._run(self.test_list_hyperblock_1_src)
        
        param_name = Type.mangled_names([Type.bool(), Type.bool()])
        scope = self.scope(f'test_list_hyperblock_{param_name}')
        xs = scope.find_sym('xs#1')
        ys = scope.find_sym('ys#1')
        zs1 = scope.find_sym('zs#1')
        zs2 = scope.find_sym('zs#2')
        self.assertIsNotNone(xs)
        self.assertIsNotNone(ys)
        self.assertIsNotNone(zs1)
        self.assertIsNotNone(zs2)
        stms = scope.usedef.get_stms_using(zs1)
        self.assertTrue(len(stms) == 1)
        uphi = list(stms)[0]
        self.assertTrue(uphi.is_a(UPHI))


if __name__ == '__main__':
    unittest.main()
