from collections import defaultdict
from .irvisitor import IRVisitor
from .ir import *
from .scope import Scope
from .type import Type
from .builtin import builtin_return_type_table
from .common import error_info
from .env import env
from .symbol import Symbol
import logging
logger = logging.getLogger(__name__)


def type_error(ir, msg):
    print(error_info(ir.block.scope, ir.lineno))
    raise TypeError(msg)


class RejectPropagation(Exception):
    pass


class TypePropagation(IRVisitor):
    def __init__(self):
        super().__init__()
        self.check_error = True

    def propagate_global_function_type(self):
        self.check_error = False
        scopes = Scope.get_scopes(bottom_up=False,
                                  with_global=True,
                                  with_class=True,
                                  with_lib=False)
        for s in scopes:
            if s.return_type is None:
                s.return_type = Type.none_t
        prev_untyped = []
        while True:
            untyped = []
            for s in scopes:
                try:
                    self.process(s)
                except RejectPropagation as r:
                    #print(r)
                    untyped.append(s)
                    continue
            if untyped:
                if len(prev_untyped) == len(untyped):
                    str_untypes = ', '.join([s.name[len('@top.'):] for s in untyped])
                    raise TypeError(
                        'BUG: can not complete the type inference process for ' +
                        str_untypes)
                prev_untyped = untyped[:]
                continue
            break
        for s in scopes:
            self.process(s)

    def visit_UNOP(self, ir):
        return self.visit(ir.exp)

    def visit_BINOP(self, ir):
        ltype = self.visit(ir.left)
        self.visit(ir.right)
        return ltype

    def visit_RELOP(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)
        return Type.bool_t

    def visit_CONDOP(self, ir):
        self.visit(ir.cond)
        ltype = self.visit(ir.left)
        self.visit(ir.right)
        return ltype

    def _convert_call(self, ir):
        clazz = ir.func.symbol().typ.get_scope()
        if clazz:
            if clazz.is_port():
                fun_name = 'wr' if ir.args else 'rd'
            else:
                fun_name = env.callop_name
            func_sym = clazz.find_sym(fun_name)
            assert func_sym.typ.is_function()
            ir.func_scope = func_sym.typ.get_scope()
            ir.func = ATTR(ir.func, clazz.symbols[fun_name], Ctx.LOAD)
            ir.func.attr_scope = clazz

    def visit_CALL(self, ir):
        self.visit(ir.func)

        if ir.func.is_a(TEMP):
            func_name = ir.func.symbol().orig_name()
            t = ir.func.symbol().typ
            if t.is_object() or t.is_port():
                self._convert_call(ir)
            elif t.is_function():
                sym = self.scope.find_sym(func_name)
                assert sym.typ.has_scope()
                scope = sym.typ.get_scope()
                ir.func_scope = scope
            else:
                raise RejectPropagation(str(ir))
        elif ir.func.is_a(ATTR):
            if not ir.func.attr_scope:
                raise RejectPropagation(str(ir))
            func_name = ir.func.symbol().orig_name()
            t = ir.func.symbol().typ
            if t.is_object() or t.is_port():
                self._convert_call(ir)
            else:
                func_sym = ir.func.attr_scope.find_sym(func_name)
                if func_sym.typ.is_function():
                    ir.func_scope = func_sym.typ.get_scope()
            if not ir.func_scope:
                raise RejectPropagation(str(ir))
            #assert ir.func_scope.is_method()
            if ir.func_scope.is_mutable():
                pass  # ir.func.exp.ctx |= Ctx.STORE
        else:
            assert False

        if not ir.func_scope:
            # we cannot specify the callee because it has not been evaluated yet.
            raise RejectPropagation(str(ir))

        if ir.func_scope.is_method():
            params = ir.func_scope.params[1:]
        else:
            params = ir.func_scope.params[:]
        self._fill_args_if_needed(ir.func_scope.orig_name, params, ir.args)
        arg_types = [self.visit(arg) for arg in ir.args]
        if any([atype.is_none() for atype in arg_types]):
            raise RejectPropagation(str(ir))

        ret_t = ir.func_scope.return_type
        if ir.func_scope.is_class():
            assert False
        else:
            for i, param in enumerate(params):
                if param.sym.typ.is_int() or Type.is_same(param.sym.typ, arg_types[i]):
                    self._set_type(param.sym, arg_types[i])
            funct = Type.function(ir.func_scope,
                                  ret_t,
                                  tuple([param.sym.typ for param in ir.func_scope.params]))
        self._set_type(ir.func.symbol(), funct)

        if (self.scope.is_testbench() and
                ir.func_scope.is_function() and not ir.func_scope.is_inlinelib()):
            ir.func_scope.add_tag('function_module')

        return ret_t

    def visit_SYSCALL(self, ir):
        for arg in ir.args:
            self.visit(arg)
        return builtin_return_type_table[ir.name]

    def visit_NEW(self, ir):
        ret_t = Type.object(ir.func_scope)
        ir.func_scope.return_type = ret_t
        ctor = ir.func_scope.find_ctor()
        self._fill_args_if_needed(ir.func_scope.orig_name, ctor.params[1:], ir.args)
        arg_types = [self.visit(arg) for arg in ir.args]
        for i, param in enumerate(ctor.params[1:]):
            if param.sym.typ.is_int() or Type.is_same(param.sym.typ, arg_types[i]):
                self._set_type(param.sym, arg_types[i])
        return ret_t

    def visit_CONST(self, ir):
        if isinstance(ir.value, int):
            return Type.int()
        elif isinstance(ir.value, str):
            return Type.str_t
        elif ir.value is None:
            return Type.int()
        else:
            type_error(self.current_stm, 'unsupported literal type {}'.format(repr(ir)))

    def visit_TEMP(self, ir):
        return ir.sym.typ

    def visit_ATTR(self, ir):
        exptyp = self.visit(ir.exp)
        if exptyp.is_object() or exptyp.is_class() or exptyp.is_namespace() or exptyp.is_port():
            attr_scope = exptyp.get_scope()
            ir.attr_scope = attr_scope

        if ir.attr_scope:
            assert ir.attr_scope.is_containable()
            if isinstance(ir.attr, str):
                if not ir.attr_scope.has_sym(ir.attr):
                    type_error(self.current_stm, 'unknown attribute name {}'.format(ir.attr))
                ir.attr = ir.attr_scope.find_sym(ir.attr)

            return ir.attr.typ

        raise RejectPropagation(str(ir))

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        self.visit(ir.offset)
        if self.check_error:
            if not mem_t.is_seq():
                type_error(self.current_stm, 'expects list')
        else:
            if not mem_t.is_seq():
                return Type.none_t
        return mem_t.get_element()

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        self.visit(ir.offset)
        self.visit(ir.exp)
        return mem_t

    def visit_ARRAY(self, ir):
        for item in ir.items:
            self.visit(item)
        if ir.is_mutable:
            return Type.list(Type.int(), None)
        else:
            return Type.tuple(Type.int(), None, len(ir.items))

    def _propagate_worker_arg_types(self, call):
        if len(call.args) == 0:
            type_error(self.current_stm,
                       "{}() missing required argument".format(call.func_scope.orig_name))
        func = call.args[0]
        if not func.symbol().typ.is_function():
            type_error(self.current_stm, "!!!")
        worker_scope = func.symbol().typ.get_scope()

        if worker_scope.is_method():
            params = worker_scope.params[1:]
        else:
            params = worker_scope.params[:]

        if len(call.args) > 1:
            arg = call.args[1]
            if arg.is_a(ARRAY):
                args = arg.items[:]
            else:
                args = call.args[1:]
        else:
            args = []
        self._fill_args_if_needed(worker_scope.orig_name, params, args)
        arg_types = [self.visit(arg) for arg in args]
        for i, param in enumerate(params):
            self._set_type(param.sym, arg_types[i])
            self._set_type(param.copy, arg_types[i])

        funct = Type.function(worker_scope,
                              Type.none_t,
                              tuple([param.sym.typ for param in worker_scope.params]))
        self._set_type(func.symbol(), funct)
        mod_sym = call.func.tail()
        assert mod_sym.typ.is_object()
        if not worker_scope.is_worker():
            worker_scope.add_tag('worker')

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

        if (ir.exp.is_a(CALL) and ir.exp.func_scope.is_method() and
                ir.exp.func_scope.parent.is_module()):
            if ir.exp.func_scope.orig_name == 'append_worker':
                self._propagate_worker_arg_types(ir.exp)

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        typ = self.visit(ir.exp)
        if self.scope.return_type.is_none() and not typ.is_none():
            self.scope.return_type = typ

    def _is_valid_list_type_source(self, src):
        return (src.is_a([ARRAY,  MSTORE])
                or src.is_a(BINOP) and src.left.is_a(ARRAY) and src.op == 'Mult'
                or src.is_a(TEMP) and src.sym.is_param())

    def visit_MOVE(self, ir):
        src_typ = self.visit(ir.src)
        if src_typ is Type.none_t:
            raise RejectPropagation(str(ir))
        dst_typ = self.visit(ir.dst)

        if ir.dst.is_a([TEMP, ATTR]):
            if not isinstance(ir.dst.symbol(), Symbol):
                # the type of object has not inferenced yet
                raise RejectPropagation(str(ir))
            self._set_type(ir.dst.symbol(), src_typ)
            if self.scope.is_method() and ir.dst.is_a(ATTR):
                receiver = ir.dst.tail()
                if receiver.typ.is_object():
                    sym = receiver.typ.get_scope().find_sym(ir.dst.symbol().name)
                    self._set_type(sym, src_typ)
        elif ir.dst.is_a(MREF):
            self._set_type(ir.dst.mem.symbol(), Type.list(src_typ, None))
        elif ir.dst.is_a(ARRAY):
            if src_typ.is_none():
                # the type of object has not inferenced yet
                raise RejectPropagation(str(ir))
            if not src_typ.is_tuple() or not dst_typ.is_tuple():
                raise RejectPropagation(str(ir))
            elem_t = src_typ.get_element()
            for item in ir.dst.items:
                assert item.is_a([TEMP, ATTR])
                self._set_type(item.symbol(), elem_t)
        else:
            assert False
        # check mutable method
        if (self.scope.is_method() and ir.dst.is_a(ATTR) and
                ir.dst.head().name == env.self_name and
                not self.scope.is_mutable()):
            self.scope.add_tag('mutable')

    def visit_PHI(self, ir):
        arg_types = [self.visit(arg) for arg in ir.args]
        for arg_t in arg_types:
            if not arg_t.is_none() and not ir.var.symbol().typ.is_freezed():
                self._set_type(ir.var.symbol(), arg_t)
                break

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)

    def _fill_args_if_needed(self, func_name, params, args):
        if len(args) < len(params):
            for i, param in enumerate(params):
                if i < len(args):
                    continue
                if param.defval:
                    args.append(param.defval)
                else:
                    type_error(self.current_stm,
                               "{}() missing required argument: '{}'".format(func_name,
                                                                             param.copy.name))

    def _set_type(self, sym, typ):
        if not sym.typ.is_freezed():
            sym.set_type(typ)


class InstanceTypePropagation(TypePropagation):
    def process_all(self):
        scopes = Scope.get_scopes(bottom_up=False, with_global=True)
        for s in scopes:
            self.process(s)

    def _set_type(self, sym, typ):
        if sym.typ.is_object() and sym.typ.get_scope().is_module():
            sym.set_type(typ)


class TypeChecker(IRVisitor):
    def __init__(self):
        super().__init__()

    def visit_UNOP(self, ir):
        return self.visit(ir.exp)

    def visit_BINOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if ir.op == 'Mult' and l_t.is_seq() and r_t.is_int():
            return l_t

        if not l_t.is_scalar() or not r_t.is_scalar():
            type_error(self.current_stm,
                       'unsupported operand type(s) for {}: \'{}\' and \'{}\''.
                       format(op2sym_map[ir.op], l_t, r_t))
        return l_t

    def visit_RELOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if not l_t.is_scalar() or not r_t.is_scalar():
            type_error(self.current_stm,
                       'unsupported operand type(s) for {}: \'{}\' and \'{}\''.
                       format(op2sym_map[ir.op], l_t, r_t))
        return Type.bool_t

    def visit_CONDOP(self, ir):
        self.visit(ir.cond)
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if not Type.is_commutable(l_t, r_t):
            type_error(ir, 'conditional expression type missmatch {} {}'.format(l_t, r_t))
        return l_t

    def visit_CALL(self, ir):
        func_sym = ir.func.symbol()
        arg_len = len(ir.args)
        if ir.func_scope.is_lib():
            return ir.func_scope.return_type
        if not ir.func_scope:
            type_error(self.current_stm, '{} is not callable'.format(ir.func.sym.name))
        elif ir.func_scope.is_method():
            param_len = len(ir.func_scope.params) - 1
        else:
            param_len = len(ir.func_scope.params)

        self._check_param_number(arg_len, param_len, ir)

        if ir.func_scope.is_method():
            param_typs = func_sym.typ.get_param_types()[1:]
        else:
            param_typs = func_sym.typ.get_param_types()
        self._check_param_type(param_typs, ir)

        return ir.func_scope.return_type

    def visit_SYSCALL(self, ir):
        if ir.name == 'len':
            if len(ir.args) != 1:
                type_error(self.current_stm, 'len() takes exactly one argument')
            mem = ir.args[0]
            if not mem.is_a([TEMP, ATTR]) or not mem.symbol().typ.is_seq():
                type_error(self.current_stm, 'len() takes sequence type argument')
        else:
            for arg in ir.args:
                self.visit(arg)
        return builtin_return_type_table[ir.name]

    def visit_NEW(self, ir):
        arg_len = len(ir.args)

        ctor = ir.func_scope.find_ctor()
        if not ctor and arg_len:
            type_error(self.current_stm,
                       '{}() takes 0 positional arguments but {} were given'.
                       format(ir.func_scope.orig_name, arg_len))
        param_len = len(ctor.params) - 1
        self._check_param_number(arg_len, param_len, ir)

        param_typs = tuple([param.sym.typ for param in ctor.params])[1:]
        self._check_param_type(param_typs, ir)

        if ir.func_scope.is_module() and not ir.func_scope.parent.is_global():
            type_error(self.current_stm,
                       '@top decorated class must be in the global scope')

        return Type.object(ir.func_scope)

    def visit_CONST(self, ir):
        if isinstance(ir.value, int):
            return Type.int()
        elif isinstance(ir.value, str):
            return Type.str_t
        elif ir.value is None:
            return Type.int()
        else:
            type_error(self.current_stm,
                       'unsupported literal type {}'.format(repr(ir)))

    def visit_TEMP(self, ir):
        if (ir.ctx == Ctx.LOAD and
                ir.sym.scope is not self.scope and
                self.scope.has_sym(ir.sym.name)):
            type_error(self.current_stm,
                       "local variable '{}' referenced before assignment".format(ir.sym.name))
        return ir.sym.typ

    def visit_ATTR(self, ir):
        return ir.attr.typ

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        if not mem_t.is_seq():
            type_error(self.current_stm, 'type missmatch')
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, 'type missmatch')
        return mem_t.get_element()

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        if not mem_t.is_seq():
            type_error(self.current_stm, 'type missmatch')
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, 'type missmatch')
        exp_t = self.visit(ir.exp)
        elem_t = mem_t.get_element()
        if not Type.is_commutable(exp_t, elem_t):
            type_error(self.current_stm,
                       'assignment type missmatch {} {}'.format(exp_t, elem_t))
        return mem_t

    def visit_ARRAY(self, ir):
        for item in ir.items:
            item_type = self.visit(item)
            if not item_type.is_int():
                type_error(self.current_stm,
                           'sequence item must be integer {}'.format(item_type[0]))
        if ir.is_mutable:
            return Type.list(Type.int(), None)
        else:
            return Type.tuple(Type.int(), None, len(ir.items))

    def visit_EXPR(self, ir):
        self.visit(ir.exp)
        if ir.exp.is_a(CALL):
            if ir.exp.func_scope.return_type is Type.none_t:
                #TODO: warning
                pass
            if ir.exp.func_scope.is_method() and ir.exp.func_scope.parent.is_module():
                if ir.exp.func_scope.orig_name == 'append_worker':
                    arg_types = [self.visit(arg) for arg in ir.exp.args[1:]]
                    if len(arg_types):
                        # TODO
                        pass

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        exp_t = self.visit(ir.exp)
        if not Type.is_commutable(exp_t, self.scope.return_type):
            type_error(ir, 'function return type is not missmatch')

    def visit_MOVE(self, ir):
        src_t = self.visit(ir.src)
        dst_t = self.visit(ir.dst)

        if not Type.is_commutable(dst_t, src_t):
            type_error(ir, 'assignment type missmatch {} {}'.format(src_t, dst_t))

    def visit_PHI(self, ir):
        # FIXME
        #assert ir.var.symbol().typ is not None
        #assert all([arg is None or arg.symbol().typ is not None for arg, blk in ir.args])
        pass

    def _check_param_number(self, arg_len, param_len, ir):
        if arg_len == param_len:
            pass
        elif arg_len < param_len:
            type_error(self.current_stm,
                       "{}() missing required argument: '{}'".
                       format(ir.func_scope.orig_name, param.sym.name))
        else:
            type_error(self.current_stm,
                       '{}() takes {} positional arguments but {} were given'.
                       format(ir.func_scope.orig_name, param_len, arg_len))

    def _check_param_type(self, param_typs, ir):
        assert len(ir.args) == len(param_typs)
        for arg, param_t in zip(ir.args, param_typs):
            arg_t = self.visit(arg)
            if not Type.is_commutable(arg_t, param_t):
                type_error(self.current_stm,
                           'type missmatch "{}" "{}"'.format(arg_t[0], param_t[0]))


class ModuleChecker(IRVisitor):
    def __init__(self):
        super().__init__()
        self.assigns = defaultdict(set)

    def process(self, scope):
        if not (scope.parent and scope.parent.is_module()):
            return
        super().process(scope)

    def visit_MOVE(self, ir):
        if not ir.dst.is_a(ATTR):
            return
        irattr = ir.dst
        if not irattr.exp.is_a(TEMP):
            return
        if irattr.exp.sym.name != env.self_name:
            return
        class_scope = self.scope.parent
        if self.scope.is_ctor():
            if irattr.symbol() not in self.assigns[class_scope]:
                self.assigns[class_scope].add(irattr.symbol())
            else:
                type_error(self.current_stm, 'Assignment to a module field can only be done once')
        else:
            type_error(self.current_stm,
                       'Assignment to a module field can only at the constructor or a function called from the constructor')

