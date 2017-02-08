from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .irvisitor import IRVisitor
from .ir import *
from .scope import Scope
from .type import Type
from .builtin import builtin_return_type_table
import logging
logger = logging.getLogger(__name__)

class BitwidthReducer(AHDLVisitor):
    def process(self, scope):
        if not scope.module_info:
            return
        self.usedef = scope.ahdlusedef
        #print(self.usedef)
        for fsm in scope.module_info.fsms.values():
            for stg in fsm.stgs:
                for state in stg.states:
                    for code in state.codes:
                        self.visit(code)

    def visit_AHDL_CONST(self, ahdl):
        if isinstance(ahdl.value, int):
            if ahdl.value == 0:
                return 0
            elif ahdl.value > 0:
                return ahdl.value.bit_length()
            else:
                return ahdl.value.bit_length()+1
        elif isinstance(ahdl.value, str):
            return 1
        elif ir.value is None:
            return 1
        else:
            type_error(self.current_stm, 'unsupported literal type {}'.format(repr(ir)))

    def visit_AHDL_VAR(self, ahdl):
        return ahdl.sig.width

    def visit_AHDL_MEMVAR(self, ahdl):
        return ahdl.sig.width

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        return self.visit(ahdl.memvar)

    def visit_AHDL_OP(self, ahdl):
        if ahdl.is_relop():
            return 1
        widths = [self.visit(a) for a in ahdl.args]
        
        if ahdl.op == 'BitAnd':
            width = min(widths) + 1 # +1 means signbit for signed destination
        elif ahdl.op == 'Sub':
            width = widths[0]
        elif ahdl.op == 'LShift':
            assert len(ahdl.args)==2
            width = widths[0] + (1<<widths[1])-1
        elif ahdl.op == 'RShift':
            assert len(ahdl.args)==2
            width = widths[0]
            if ahdl.args[1].is_a(AHDL_CONST):
                width -= ahdl.args[1].value
        else:
            width = max(widths)
        if width < 0:
            width = 1
        elif width > 64: # TODO
            width = 64
        return width

    def visit_AHDL_SYMBOL(self, ahdl):
        return 1

    def visit_AHDL_CONCAT(self, ahdl):
        return sum([self.visit(var) for var in ahdl.varlist])

    def visit_AHDL_NOP(self, ahdl):
        pass

    def visit_AHDL_MOVE(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR):
            dst_sig = ahdl.dst.sig
        else:
            return
        if dst_sig.is_output():
            return
        stms = self.usedef.get_stm_defining(dst_sig)
        if len(stms) > 1:
            return
        srcw = self.visit(ahdl.src)
        if srcw is None:
            return
        if dst_sig.width > srcw:
            dst_sig.width = srcw
        
    def visit_AHDL_STORE(self, ahdl):
        pass

    def visit_AHDL_LOAD(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR):
            dst_sig = ahdl.dst.sig
        else:
            return
        if dst_sig.is_output():
            return
        stms = self.usedef.get_stm_defining(dst_sig)
        if len(stms) > 1:
            return
        srcw = self.visit(ahdl.mem)
        if srcw is None:
            return
        if dst_sig.width > srcw:
            dst_sig.width = srcw

    def visit_AHDL_FIELD_MOVE(self, ahdl):
        pass

    def visit_AHDL_FIELD_STORE(self, ahdl):
        pass

    def visit_AHDL_FIELD_LOAD(self, ahdl):
        pass

    def visit_AHDL_MODULECALL(self, ahdl):
        pass

    def visit_AHDL_FUNCALL(self, ahdl):
        pass

    def visit_AHDL_IF_EXP(self, ahdl):
        lw = self.visit(ahdl.lexp)
        rw = self.visit(ahdl.rexp)
        return lw if lw >= rw else rw


class _BitwidthPropagation(IRVisitor):
    def __init__(self):
        super().__init__()
        
    def visit_UNOP(self, ir):
        return self.visit(ir.exp)

    def visit_BINOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        return Type.wider_int(l_t, r_t)

    def visit_RELOP(self, ir):
        return Type.bool_t

    def visit_BINOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        return Type.wider_int(l_t, r_t)

    def visit_CALL(self, ir):
        if ir.func_scope.is_class():
            return ir.func_scope.return_type
        
        if ir.func_scope.is_method():
            params = ir.func_scope.params[1:]
        else:
            params = ir.func_scope.params[:]
        arg_types = [self.visit(arg) for arg in ir.args]
        for i, param in enumerate(params):
            if param.sym.typ.is_int():
                param.sym.typ = Type.wider_int(param.sym.typ, arg_types[i])
        funct = Type.function(ir.func_scope, ir.func_scope.return_type, tuple([param.sym.typ for param in ir.func_scope.params]))
        ir.func.symbol().set_type(funct)
        if ir.func.is_a(ATTR) and ir.func.attr_scope.is_port():
            pass
        return ir.func_scope.return_type

    def visit_SYSCALL(self, ir):
        return builtin_return_type_table[ir.name]

    def visit_NEW(self, ir):
        ctor = ir.func_scope.find_ctor()
        arg_types = [self.visit(arg) for arg in ir.args]
        for i, param in enumerate(ctor.params[1:]):
            if param.sym.typ.is_int():
                param.sym.typ = Type.wider_int(param.sym.typ, arg_types[i])
        return ir.func_scope.return_type

    def visit_CONST(self, ir):
        if isinstance(ir.value, int):
            return Type.int(ir.value.bit_length()+1)
        elif isinstance(ir.value, str):
            return Type.str_t
        elif ir.value is None:
            return Type.int(1)
        else:
            type_error(self.current_stm, 'unsupported literal type {}'.format(repr(ir)))

    def visit_TEMP(self, ir):
        return ir.sym.typ

    def visit_ATTR(self, ir):
        return ir.attr.typ

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        return mem_t.get_element()

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        return mem_t

    def visit_ARRAY(self, ir):
        item_types = [self.visit(item) for item in ir.items]
        t = Type.int()
        for item_t in item_types:
            t = Type.wider_int(t, item_t)
        if ir.is_mutable:
            return Type.list(t, None)
        else:
            return Type.tuple(t, None, len(ir.items))

    def _propagate_worker_arg_types(self, call):
        if len(call.args) == 0:
            type_error(self.current_stm, "{}() missing required argument".format(call.func_scope.orig_name))
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
        arg_types = [self.visit(arg) for arg in args]
        for i, param in enumerate(params):
            param.copy.typ = param.sym.typ = arg_types[i]
        funct = Type.function(worker_scope, Type.none_t, tuple([param.sym.typ for param in worker_scope.params]))
        func.symbol().set_type(funct)
        mod_sym = call.func.tail()
        assert mod_sym.typ.is_object()
        mod_scope = mod_sym.typ.get_scope()
        mod_scope.append_worker(call, worker_scope, args)
        
    def visit_EXPR(self, ir):
        self.visit(ir.exp)

        if ir.exp.is_a(CALL) and ir.exp.func_scope.is_method() and ir.exp.func_scope.parent.is_module():
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

    def visit_MOVE(self, ir):
        src_typ = self.visit(ir.src)
        dst_typ = self.visit(ir.dst)
        if dst_typ.is_int() and src_typ.is_int():
            dst_typ.set_width(src_typ.get_width())
            
    def visit_PHI(self, ir):
        arg_types = [self.visit(arg) for arg in ir.args]
        if arg_types[0].is_int():
            t = Type.int()
            for arg_t in arg_types:
                t = Type.wider_int(t, arg_t)
            ir.var.symbol().set_type(t)

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)

