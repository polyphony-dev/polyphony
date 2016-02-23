from .irvisitor import IRVisitor
from .ir import UNOP, BINOP, RELOP, CALL, SYSCALL, CONST, MREF, MSTORE, ARRAY, TEMP, EXPR, CJUMP, JUMP, RET, MOVE
from .scope import Scope
from .type import Type

import logging
logger = logging.getLogger(__name__)

builtin_return_type_table = {
    'print':Type.none_t,
    'range':Type.none_t,
    'len':Type.int_t,
    'assert':Type.none_t
}

class TypePropagation(IRVisitor):
    def __init__(self):
        super().__init__()
        self.check_error = True

    def propagate_global_function_type(self):
        self.check_error = False
        scopes = Scope.get_scopes(contain_global=True)
        for s in scopes:
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
        ret_t = ir.func_scope.return_type
        ir.func.sym.set_type(('func', ret_t, tuple([param.sym.typ for param in ir.func_scope.params])))
        for arg in ir.args:
            self.visit(arg)
        return ret_t

    def visit_SYSCALL(self, ir):
        for arg in ir.args:
            self.visit(arg)
        return builtin_return_type_table[ir.name]

    def visit_CONST(self, ir):
        return Type.int_t

    def visit_TEMP(self, ir):
        return ir.sym.typ

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        self.visit(ir.offset)
        if self.check_error:
            if not Type.is_list(mem_t) and not Type.is_phi(mem_t):
                raise TypeError('expects list')
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
        return isinstance(src, ARRAY) or isinstance(src, MSTORE) \
        or (isinstance(src, BINOP) and isinstance(src.left, ARRAY) and src.op == 'Mult') \
        or (isinstance(src, TEMP) and src.sym.is_param())

    def visit_MOVE(self, ir):
        src_typ = self.visit(ir.src)
        if isinstance(ir.dst, TEMP):
            ir.dst.sym.set_type(src_typ)
        elif isinstance(ir.dst, MREF):
            ir.dst.mem.sym.set_type(Type.list(src_typ, None))
        else:
            assert 0

    def visit_PHI(self, ir):
        pass

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
            raise TypeError('Unsupported operation {}'.format(ir.op))
        return l_t

    def visit_RELOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if not Type.is_commutable(l_t, r_t):
            raise TypeError('Unsupported operation {}'.format(ir.op))
        return Type.bool_t

    def visit_CALL(self, ir):
        ret_t = ir.func_scope.return_type
        assert len(ir.args) == len(ir.func.sym.typ[2])
        for arg, param_t in zip(ir.args, ir.func.sym.typ[2]):
            arg_t = self.visit(arg)
            if not Type.is_commutable(arg_t, param_t):
                raise TypeError('type missmatch')
        return ret_t

    def visit_SYSCALL(self, ir):
        if ir.name == 'len':
            if len(ir.args) != 1:
                raise TypeError('len() takes exactly one argument')
            mem = ir.args[0]
            if not isinstance(mem, TEMP) or not Type.is_list(mem.sym.typ):
                TypeError('len() takes list type argument')
        else:
            for arg in ir.args:
                self.visit(arg)
        return builtin_return_type_table[ir.name]

    def visit_CONST(self, ir):
        return Type.int_t

    def visit_TEMP(self, ir):
        return ir.sym.typ

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        if not Type.is_list(mem_t) and not Type.is_phi(mem_t):
            raise TypeError('type missmatch')
        offs_t = self.visit(ir.offset)
        if offs_t is not Type.int_t:
            raise TypeError('type missmatch')
        return Type.element(mem_t)

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        if not Type.is_list(mem_t) and not Type.is_phi(mem_t):
            raise TypeError('type missmatch')
        offs_t = self.visit(ir.offset)
        if offs_t is not Type.int_t:
            raise TypeError('type missmatch')
        exp_t = self.visit(ir.exp)
        elem_t = Type.element(mem_t)
        if elem_t != exp_t:
            if (elem_t is Type.int_t and exp_t is Type.bool_t) \
               or (elem_t is Type.bool_t and exp_t is Type.int_t):
                pass
            else:
                raise TypeError('assignment type missmatch')
        return mem_t

    def visit_ARRAY(self, ir):
        for item in ir.items:
            item_type = self.visit(item)
            if item_type is not Type.int_t:
                raise TypeError('list item must be integer')
        return Type.list(Type.int_t, None)

    def visit_EXPR(self, ir):
        typ = self.visit(ir.exp)
        if isinstance(ir.exp, CALL):
            if ir.exp.func_scope.return_type is Type.none_t:
                #TODO: warning
                pass
        elif isinstance(ir.exp, SYSCALL):
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
            raise TypeError('function return type is not missmatch')

    def visit_MOVE(self, ir):
        src_t = self.visit(ir.src)
        dst_t = self.visit(ir.src)

        if dst_t != src_t:
            if (src_t is Type.int_t and dst_t is Type.bool_t) \
               or (src_t is Type.bool_t and dst_t is Type.int_t):
                pass
            else:
                raise TypeError('assignment type missmatch')

    def visit_PHI(self, ir):
        # FIXME
        assert ir.var.sym.typ is not None
        assert all([arg is None or arg.sym.typ is not None for arg, blk in ir.args])


    
