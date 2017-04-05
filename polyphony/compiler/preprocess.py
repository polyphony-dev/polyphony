from .common import fail
from .constopt import ConstantOptBase, eval_binop
from .errors import Errors
from .env import env
from .ir import *
from ..io import PolyphonyIOException
import inspect
import os
import sys


def interpret(source, file_name):
    dir_name = os.path.dirname(file_name)
    code = compile(source, file_name, 'exec')
    globs = {}
    stdout = sys.stdout
    sys.stdout = None
    try:
        sys.path.append(dir_name)
        exec(code, globs)
    except PolyphonyIOException:
        pass
    except Exception as e:
        pass
    finally:
        sys.stdout = stdout

    for name, obj in globs.items():
        if not inspect.isfunction(obj):
            continue
        if obj.__name__ != '_preprocess_decorator':
            continue
        scope_name = '{}.{}'.format(env.global_scope_name, obj.func.__name__)
        scope = env.scopes[scope_name]
        assert scope.is_preprocess()
        scope.pyfunc = obj.func


class Preprocessor(ConstantOptBase):
    def _args2tuple(self, args):
        values = []
        for arg in args:
            a = self.visit(arg)
            if a.is_a(CONST):
                values.append(a.value)
            elif a.is_a(ARRAY):
                items = self._args2tuple(a.items)
                if not items:
                    return None
                values.append(items)
            else:
                return None
        return tuple(values)

    def _expr2ir(self, expr):
        if expr is None:
            return CONST(None)
        elif isinstance(expr, int):
            return CONST(expr)
        elif isinstance(expr, str):
            return CONST(expr)
        elif isinstance(expr, list):
            items = [self._expr2ir(e) for e in expr]
            return ARRAY(items)
        elif isinstance(expr, tuple):
            items = [self._expr2ir(e) for e in expr]
            return ARRAY(items, is_mutable=False)
        else:
            assert False

    def visit_CALL(self, ir):
        if not isinstance(ir.func.symbol(), Symbol):
            return ir
        if not ir.func.symbol().typ.is_function():
            return ir
        assert ir.func.symbol().typ.has_scope()
        scope = ir.func.symbol().typ.get_scope()
        if not scope.is_preprocess():
            return ir
        if not env.enable_preprocess:
            fail(self.current_stm, Errors.PREPROCESS_IS_DISABLED)
        if not scope.parent.is_global():
            fail(self.current_stm, Errors.PREPROCESS_MUST_BE_GLOBAL)
        assert scope.pyfunc
        args = self._args2tuple([arg for _, arg in ir.args])
        if args is None:
            fail(self.current_stm, Errors.PREPROCESS_ARGS_MUST_BE_CONST)
        expr = scope.pyfunc(*args)
        return self._expr2ir(expr)

    def visit_SYSCALL(self, ir):
        return super().visit_CALL(ir)

    def visit_NEW(self, ir):
        return super().visit_CALL(ir)

    def visit_BINOP(self, ir):
        ir.left = self.visit(ir.left)
        ir.right = self.visit(ir.right)
        if ir.left.is_a(CONST) and ir.right.is_a(CONST):
            return CONST(eval_binop(ir, self))
        if ir.left.is_a(ARRAY):
            if ir.op == 'Mult' and ir.right.is_a(CONST):
                array = ir.left
                array.items *= ir.right.value
                return array
        return ir