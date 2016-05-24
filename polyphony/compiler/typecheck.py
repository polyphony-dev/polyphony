from .irvisitor import IRVisitor
from .ir import *
from .scope import Scope
from .type import Type
from .builtin import builtin_return_type_table
from .symbol import function_name
from .common import error_info
import logging
logger = logging.getLogger(__name__)


def type_error(ir, msg):
    print(error_info(ir.lineno))
    raise TypeError(msg)

class TypePropagation(IRVisitor):
    def __init__(self):
        super().__init__()
        self.check_error = True

    def propagate_global_function_type(self):
        self.check_error = False
        scopes = Scope.get_scopes(contain_global=True, contain_class=True)
        for s in scopes:
            if s.is_class():
                s.return_type = Type.object(None, s)
            else:
                s.return_type = Type.none_t

        for s in scopes:
            self.process(s)
        #process all again for CALL.func.sym.type stabilizationi
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

    def visit_CALL(self, ir):
        self.visit(ir.func)

        if ir.func.is_a(TEMP):
            func_sym = ir.func.sym
            func_name = function_name(func_sym)
            ir.func_scope = self.scope.find_scope(func_name)
        elif ir.func.is_a(ATTR):
            func_sym = ir.func.attr
            ir.func_scope = ir.func.scope.find_child(ir.func.attr.name)
            assert ir.func_scope.is_method()
            if ir.func_scope.is_mutable():
                ir.func.exp.ctx |= Ctx.STORE
        self.scope.add_callee_scope(ir.func_scope)

        ret_t = ir.func_scope.return_type
        if ir.func_scope.is_class():
            assert False
        else:
            funct = Type.function(ret_t, tuple([param.sym.typ for param in ir.func_scope.params]))

        func_sym.set_type(funct)
        for arg in ir.args:
            self.visit(arg)
        return ret_t

    def visit_SYSCALL(self, ir):
        for arg in ir.args:
            self.visit(arg)
        return builtin_return_type_table[ir.name]

    def visit_CTOR(self, ir):
        self.scope.add_callee_scope(ir.func_scope)
        ret_t = ir.func_scope.return_type
        ctor = ir.func_scope.find_ctor()
        funct = Type.function(ret_t, tuple([param.sym.typ for param in ctor.params]))
        for arg in ir.args:
            self.visit(arg)
        return ret_t

    def visit_CONST(self, ir):
        return Type.int_t

    def visit_TEMP(self, ir):
        return ir.sym.typ

    def visit_ATTR(self, ir):
        exptyp = self.visit(ir.exp)
        if Type.is_object(exptyp) or Type.is_class(exptyp):
            scope = Type.extra(exptyp)
            assert isinstance(scope, Scope)
            ir.scope = scope

        if ir.scope:
            if isinstance(ir.attr, str):
                if not ir.scope.has_sym(ir.attr):
                    type_error(ir, 'unknown attribute name {}'.format(ir.attr))
                ir.attr = ir.scope.find_sym(ir.attr)
            if ir.scope.is_class() and self.scope.parent is not ir.scope:
                self.scope.add_callee_scope(ir.scope)
            return ir.attr.typ
        type_error(ir, 'unsupported attribute')

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        self.visit(ir.offset)
        if self.check_error:
            if not Type.is_list(mem_t) and not Type.is_phi(mem_t):
                type_error(ir, 'expects list')
        return Type.element(mem_t)

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        self.visit(ir.offset)
        self.visit(ir.exp)
        return mem_t

    def visit_ARRAY(self, ir):
        for item in ir.items:
            self.visit(item)
        return Type.list(Type.int_t, None)

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        typ = self.visit(ir.exp)
        self.scope.return_type = typ

    def _is_valid_list_type_source(self, src):
        return src.is_a([ARRAY,  MSTORE]) \
        or src.is_a(BINOP) and src.left.is_a(ARRAY) and src.op == 'Mult' \
        or src.is_a(TEMP) and src.sym.is_param()

    def visit_MOVE(self, ir):
        src_typ = self.visit(ir.src)
        dst_typ = self.visit(ir.dst)
        if Type.is_none(dst_typ):
            if ir.dst.is_a(TEMP):
                ir.dst.sym.set_type(src_typ)
            elif ir.dst.is_a(ATTR):
                ir.dst.attr.set_type(src_typ)
            elif ir.dst.is_a(MREF):
                ir.dst.mem.sym.set_type(Type.list(src_typ, None))
            else:
                assert 0
        # check mutable method
        if self.scope.is_method() and ir.dst.is_a(ATTR) and ir.dst.head().name == 'self':
            self.scope.attributes.append('mutable')

    def visit_PHI(self, ir):
        arg_types = [self.visit(arg) for arg, blk in ir.args]
        for arg_t in arg_types:
            if not Type.is_none(arg_t):
                ir.var.sym.set_type(arg_t)
                break

class TypeChecker(IRVisitor):
    def __init__(self):
        super().__init__()

    def visit_UNOP(self, ir):
        return self.visit(ir.exp)

    def visit_BINOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if ir.op == 'Mult' and Type.is_list(l_t) and r_t is Type.int_t:
            return ltype
        if l_t != r_t:
            if (l_t is Type.int_t and r_t is Type.bool_t) \
               or (l_t is Type.bool_t and r_t is Type.int_t):
                return Type.int_t
            type_error(ir, 'Unsupported operation {}'.format(ir.op))
        return l_t

    def visit_RELOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if not Type.is_commutable(l_t, r_t):
            type_error(ir, 'Unsupported operation {}'.format(ir.op))
        return Type.bool_t

    def visit_CALL(self, ir):
        if ir.func.is_a(TEMP):
            func_sym = ir.func.sym
        elif ir.func.is_a(ATTR):
            func_sym = ir.func.attr

        arg_len = len(ir.args)
        if not ir.func_scope:
            type_error(ir, '{} is not callable'.format(ir.func.sym.name))
        elif ir.func_scope.is_method():
            self.scope.add_callee_scope(ir.func_scope)
            param_len = len(ir.func_scope.params)-1
        else:
            self.scope.add_callee_scope(ir.func_scope)
            param_len = len(ir.func_scope.params)

        self._check_param_number(arg_len, param_len, ir)

        if ir.func_scope.is_method():
            param_typs = func_sym.typ[2][1:]
        else:
            param_typs = func_sym.typ[2]
        self._check_param_type(param_typs, ir)

        return ir.func_scope.return_type

    def visit_SYSCALL(self, ir):
        if ir.name == 'len':
            if len(ir.args) != 1:
                type_error(ir, 'len() takes exactly one argument')
            mem = ir.args[0]
            if not mem.is_a(TEMP) or not Type.is_list(mem.sym.typ):
                type_error(ir, 'len() takes list type argument')
        else:
            for arg in ir.args:
                self.visit(arg)
        return builtin_return_type_table[ir.name]

    def visit_CTOR(self, ir):
        arg_len = len(ir.args)

        ctor = ir.func_scope.find_ctor()
        if not ctor and arg_len:
            type_error(ir, '{}() takes 0 positional arguments but {} were given'.format(ir.func_scope.orig_name, arg_len))
        param_len = len(ctor.params)-1
        self._check_param_number(arg_len, param_len, ir)

        param_typs = tuple([param.sym.typ for param in ctor.params])[1:]
        self._check_param_type(param_typs, ir)

        return ir.func_scope.return_type

    def visit_CONST(self, ir):
        return Type.int_t

    def visit_TEMP(self, ir):
        return ir.sym.typ

    def visit_ATTR(self, ir):
        return ir.attr.typ

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        if not Type.is_list(mem_t) and not Type.is_phi(mem_t):
            type_error(ir, 'type missmatch')
        offs_t = self.visit(ir.offset)
        if offs_t is not Type.int_t:
            type_error(ir, 'type missmatch')
        return Type.element(mem_t)

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        if not Type.is_list(mem_t) and not Type.is_phi(mem_t):
            type_error(ir, 'type missmatch')
        offs_t = self.visit(ir.offset)
        if offs_t is not Type.int_t:
            type_error(ir, 'type missmatch')
        exp_t = self.visit(ir.exp)
        elem_t = Type.element(mem_t)
        if elem_t != exp_t:
            if (elem_t is Type.int_t and exp_t is Type.bool_t) \
               or (elem_t is Type.bool_t and exp_t is Type.int_t):
                pass
            else:
                type_error(ir, 'assignment type missmatch')
        return mem_t

    def visit_ARRAY(self, ir):
        for item in ir.items:
            item_type = self.visit(item)
            if item_type is not Type.int_t:
                type_error(ir, 'list item must be integer {}'.format(item_type))
        return Type.list(Type.int_t, None)

    def visit_EXPR(self, ir):
        typ = self.visit(ir.exp)
        if ir.exp.is_a(CALL):
            if ir.exp.func_scope.return_type is Type.none_t:
                #TODO: warning
                pass
        elif ir.exp.is_a(SYSCALL):
            #TODO
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
        if exp_t != self.scope.return_type:
            type_error(ir, 'function return type is not missmatch')

    def visit_MOVE(self, ir):
        src_t = self.visit(ir.src)
        dst_t = self.visit(ir.src)

        if dst_t != src_t:
            if (src_t is Type.int_t and dst_t is Type.bool_t) \
               or (src_t is Type.bool_t and dst_t is Type.int_t):
                pass
            else:
                type_error(ir, 'assignment type missmatch')

    def visit_PHI(self, ir):
        # FIXME
        assert ir.var.sym.typ is not None
        assert all([arg is None or arg.sym.typ is not None for arg, blk in ir.args])


    def _check_param_number(self, arg_len, param_len, ir):
        if arg_len == param_len:
            pass
        elif arg_len < param_len:
            for i, param in enumerate(ir.func_scope.params):
                if i >= arg_len:
                    if param.defval:
                        ir.args.append(param.defval)
                    else:
                        type_error(ir, "{}() missing required argument: '{}'".format(ir.func_scope.orig_name, param.sym.name))
        else:
            type_error(ir, '{}() takes {} positional arguments but {} were given'.format(ir.func_scope.orig_name, param_len, arg_len))

    def _check_param_type(self, param_typs, ir):
        assert len(ir.args) == len(param_typs)
        for arg, param_t in zip(ir.args, param_typs):
            arg_t = self.visit(arg)
            if not Type.is_commutable(arg_t, param_t):
                type_error(ir, 'type missmatch {} {}'.format(arg_t, param_t))
