from .irvisitor import IRVisitor
from .ir import *
from .scope import Scope
from .type import Type
from .builtin import builtin_return_type_table
from .common import error_info
from .env import env
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
        scopes = Scope.get_scopes(bottom_up=False, contain_global=True, contain_class=True)
        for s in scopes:
            if s.is_class():
                s.return_type = Type.object(None, s)
            else:
                s.return_type = Type.none_t

        prev_untyped = []
        while True:
            for s in scopes:
                self.process(s)
            untyped = [s for s in scopes if s.is_returnable() and s.return_type is Type.none_t]
            if untyped:
                if len(prev_untyped) == len(untyped):
                    str_untypes = ', '.join([s.name[len('@top.'):] for s in untyped])
                    raise TypeError('BUG: can not complete the type inference process for ' + str_untypes)
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

    def visit_CALL(self, ir):
        self.visit(ir.func)

        if ir.func.is_a(TEMP):
            func_name = ir.func.symbol().orig_name()
            if Type.is_object(ir.func.symbol().typ):
                clazz = Type.extra(ir.func.symbol().typ)
                if clazz:
                    ir.func_scope = clazz.find_scope(env.callop_name)
                    ir.func = ATTR(ir.func, clazz.symbols[env.callop_name], Ctx.LOAD)
            else:
                ir.func_scope = self.scope.find_scope(func_name)
        elif ir.func.is_a(ATTR):
            if not ir.func.class_scope:
                return Type.none_t
            func_name = ir.func.symbol().orig_name()
            ir.func_scope = ir.func.class_scope.find_child(func_name)
            assert ir.func_scope.is_method()
            if ir.func_scope.is_mutable():
                ir.func.exp.ctx |= Ctx.STORE
        else:
            assert False

        if not ir.func_scope:
            # we cannot specify the callee because it has not been evaluated yet.
            return Type.none_t

        self.scope.add_callee_scope(ir.func_scope)

        arg_types = [self.visit(arg) for arg in ir.args]

        ret_t = ir.func_scope.return_type
        if ir.func_scope.is_class():
            assert False
        else:
            if ir.func_scope.is_method():
                params = ir.func_scope.params[1:]
            else:
                params = ir.func_scope.params[:]
            for i, param in enumerate(params):
                if len(arg_types) > i:
                    param.sym.typ = arg_types[i]
            funct = Type.function(ret_t, tuple([param.sym.typ for param in ir.func_scope.params]))

        ir.func.symbol().set_type(funct)

        return ret_t

    def visit_SYSCALL(self, ir):
        for arg in ir.args:
            self.visit(arg)
        return builtin_return_type_table[ir.name]

    def visit_NEW(self, ir):
        self.scope.add_callee_scope(ir.func_scope)
        ret_t = ir.func_scope.return_type
        ctor = ir.func_scope.find_ctor()
        if not ctor and not ir.args:
            # TODO: we should create ctor scope implicitly when it is not defined
            return ret_t
        arg_types = [self.visit(arg) for arg in ir.args]
        for i, param in enumerate(ctor.params[1:]):
            if len(arg_types) > i:
                param.sym.typ = arg_types[i]
        funct = Type.function(ret_t, tuple([param.sym.typ for param in ctor.params[1:]]))

        return ret_t

    def visit_CONST(self, ir):
        return Type.int_t

    def visit_TEMP(self, ir):
        return ir.sym.typ

    def visit_ATTR(self, ir):
        exptyp = self.visit(ir.exp)
        if Type.is_object(exptyp) or Type.is_class(exptyp):
            class_scope = Type.extra(exptyp)
            ir.class_scope = class_scope

        if ir.class_scope:
            assert ir.class_scope.is_class()
            if isinstance(ir.attr, str):
                if not ir.class_scope.has_sym(ir.attr):
                    type_error(ir, 'unknown attribute name {}'.format(ir.attr))
                ir.attr = ir.class_scope.find_sym(ir.attr)

            if self.scope.parent is not ir.class_scope:
                self.scope.add_callee_scope(ir.class_scope)
            return ir.attr.typ

        return Type.none_t

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        self.visit(ir.offset)
        if self.check_error:
            if not Type.is_seq(mem_t):
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
        if ir.is_mutable:
            return Type.list(Type.int_t, None)
        else:
            return Type.tuple(Type.int_t, None, len(ir.items))

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
        if src_typ is Type.none_t:
            return
        dst_typ = self.visit(ir.dst)

        if ir.dst.is_a([TEMP, ATTR]):
            if not isinstance(ir.dst.symbol(), Symbol):
                # the type of object has not inferenced yet
                return
            ir.dst.symbol().set_type(src_typ)
            if self.scope.is_method() and ir.dst.is_a(ATTR):
                sym = self.scope.parent.find_sym(ir.dst.symbol().name)
                sym.set_type(src_typ)
        elif ir.dst.is_a(MREF):
            ir.dst.mem.symbol().set_type(Type.list(src_typ, None))
        elif ir.dst.is_a(ARRAY):
            if not Type.is_tuple(src_typ) or not Type.is_tuple(dst_typ):
                assert False
            elem_t = Type.element(src_typ)
            for item in ir.dst.items:
                assert item.is_a([TEMP, ATTR])
                item.symbol().set_type(elem_t)
        else:
            assert False
        # check mutable method
        if self.scope.is_method() and ir.dst.is_a(ATTR) and ir.dst.head().name == env.self_name and 'mutable' not in self.scope.attributes:
            self.scope.attributes.append('mutable')

    def visit_PHI(self, ir):
        arg_types = [self.visit(arg) for arg in ir.args]
        for arg_t in arg_types:
            if not Type.is_none(arg_t):
                ir.var.symbol().set_type(arg_t)
                break

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)

class ClassFieldChecker(IRVisitor):
    def __init__(self):
        super().__init__()

       
    def process_all(self):
        scopes = Scope.get_scopes(contain_global=False, contain_class=False)
        for s in scopes:
            if not s.is_ctor():
                continue
            self.process(s)

    def visit_MOVE(self, ir):
        if not ir.dst.is_a(ATTR):
            return
        irattr = ir.dst
        if not irattr.exp.is_a(TEMP):
            return
        if irattr.exp.sym.name != env.self_name:
            return
        class_scope = self.scope.parent
        assert class_scope.is_class()
        class_scope.add_class_field(irattr.attr, ir)


class TypeChecker(IRVisitor):
    def __init__(self):
        super().__init__()

    def visit_UNOP(self, ir):
        return self.visit(ir.exp)

    def visit_BINOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if ir.op == 'Mult' and Type.is_seq(l_t) and r_t is Type.int_t:
            return l_t
        if l_t != r_t:
            if (l_t is Type.int_t and r_t is Type.bool_t) \
               or (l_t is Type.bool_t and r_t is Type.int_t):
                return Type.int_t
            type_error(ir, 'unsupported operand type(s) for {}: \'{}\' and \'{}\''.format(op2sym_map[ir.op], l_t[0], r_t[0]))
        return l_t

    def visit_RELOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if not Type.is_commutable(l_t, r_t):
            type_error(ir, 'unsupported operand type(s) for {}: \'{}\' and \'{}\''.format(op2sym_map[ir.op], l_t[0], r_t[0]))
        return Type.bool_t

    def visit_CALL(self, ir):
        func_sym = ir.func.symbol()
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
            if not mem.is_a([TEMP, ATTR]) or not Type.is_seq(mem.symbol().typ):
                type_error(ir, 'len() takes sequence type argument')
        else:
            for arg in ir.args:
                self.visit(arg)
        return builtin_return_type_table[ir.name]

    def visit_NEW(self, ir):
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
        if not Type.is_seq(mem_t):
            type_error(ir, 'type missmatch')
        offs_t = self.visit(ir.offset)
        if offs_t is not Type.int_t:
            type_error(ir, 'type missmatch')
        return Type.element(mem_t)

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        if not Type.is_seq(mem_t):
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
                type_error(ir, 'sequence item must be integer {}'.format(item_type[0]))
        if ir.is_mutable:
            return Type.list(Type.int_t, None)
        else:
            return Type.tuple(Type.int_t, None, len(ir.items))

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
        #assert ir.var.symbol().typ is not None
        #assert all([arg is None or arg.symbol().typ is not None for arg, blk in ir.args])
        pass

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
                type_error(ir, 'type missmatch "{}" "{}"'.format(arg_t[0], param_t[0]))
