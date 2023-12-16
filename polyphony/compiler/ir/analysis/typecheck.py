from ..irvisitor import IRVisitor
from ..ir import *
from ..irhelper import qualified_symbols, irexp_type
from ..symbol import Symbol
from ..types.type import Type
from ..types.typehelper import type_from_typeclass
from ...common.env import env
from ...common.common import fail, warn
from ...common.errors import Errors, Warnings
import logging
logger = logging.getLogger(__name__)


def type_error(ir, err_id, args=None):
    fail(ir, err_id, args)


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
            type_error(self.current_stm, Errors.UNSUPPORTED_BINARY_OPERAND_TYPE,
                       [op2sym_map[ir.op], l_t, r_t])
        if l_t.is_bool() and r_t.is_bool() and not ir.op.startswith('Bit'):
            return Type.int(2)
        return l_t

    def visit_RELOP(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        valid_l_t = l_t.is_scalar() or l_t.is_object()
        valid_r_t = r_t.is_scalar() or r_t.is_object()
        if not valid_l_t or not valid_r_t:
            type_error(self.current_stm, Errors.UNSUPPORTED_BINARY_OPERAND_TYPE,
                       [op2sym_map[ir.op], l_t, r_t])
        return Type.bool()

    def visit_CONDOP(self, ir):
        self.visit(ir.cond)
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if not l_t.is_compatible(r_t):
            type_error(self.current_stm, Errors.INCOMPTIBLE_TYPES,
                       [l_t, r_t])
        return l_t

    def visit_CALL(self, ir):
        arg_len = len(ir.args)
        callee_scope = ir.get_callee_scope(self.scope)
        assert callee_scope
        if callee_scope.is_lib():
            return callee_scope.return_type

        if callee_scope.is_pure():
            return Type.any()
        param_typs = callee_scope.param_types()
        param_len = len(param_typs)
        #with_vararg = param_len and param_typs[-1].has_vararg()
        # TODO:
        with_vararg = False
        self._check_param_number(arg_len, param_len, ir, callee_scope.orig_name, with_vararg)
        self._check_param_type(callee_scope, param_typs, ir, callee_scope.orig_name, with_vararg)

        return callee_scope.return_type

    def visit_SYSCALL(self, ir):
        name = ir.name
        if name == 'len':
            if len(ir.args) != 1:
                type_error(self.current_stm, Errors.LEN_TAKES_ONE_ARG)
            _, mem = ir.args[0]
            mem_t = irexp_type(mem, self.scope)
            if not mem.is_a(IRVariable) or not mem_t.is_seq():
                type_error(self.current_stm, Errors.LEN_TAKES_SEQ_TYPE)
        elif name == 'print':
            for _, arg in ir.args:
                arg_t = self.visit(arg)
                if not arg_t.is_scalar():
                    type_error(self.current_stm, Errors.PRINT_TAKES_SCALAR_TYPE)
        elif name == '$new':
            _, arg0 = ir.args[0]
            arg0_t = irexp_type(arg0, self.scope)
            assert arg0_t.is_class()
            return Type.object(arg0_t.scope)
        elif name in env.all_scopes:
            syscall_scope = env.all_scopes[ir.name]
            arg_len = len(ir.args)
            param_typs = tuple(syscall_scope.param_types())
            param_len = len(param_typs)
            #with_vararg = len(param_typs) and param_typs[-1].has_vararg()
            # TODO:
            with_vararg = False
            self._check_param_number(arg_len, param_len, ir, name, with_vararg)
            self._check_param_type(syscall_scope, param_typs, ir, name, with_vararg)
        else:
            for _, arg in ir.args:
                self.visit(arg)
        sym_t = irexp_type(ir, self.scope)
        assert sym_t.is_function()
        return sym_t.return_type

    def visit_NEW(self, ir):
        arg_len = len(ir.args)

        callee_scope = ir.get_callee_scope(self.scope)
        if callee_scope.is_typeclass():
            return type_from_typeclass(callee_scope)

        ctor = callee_scope.find_ctor()
        if not ctor and arg_len:
            type_error(self.current_stm, Errors.TAKES_TOOMANY_ARGS,
                       [callee_scope.orig_name, 0, arg_len])
        param_typs = ctor.param_types()
        param_len = len(param_typs)
        #with_vararg = len(param_typs) and param_typs[-1].has_vararg()
        # TODO:
        with_vararg = False
        self._check_param_number(arg_len, param_len, ir, callee_scope.orig_name, with_vararg)
        self._check_param_type(callee_scope, param_typs, ir, callee_scope.orig_name, with_vararg)

        return Type.object(callee_scope)

    def visit_CONST(self, ir):
        if isinstance(ir.value, bool):
            return Type.bool()
        elif isinstance(ir.value, int):
            return Type.int()
        elif isinstance(ir.value, str):
            return Type.str()
        elif ir.value is None:
            # The value of 'None' is evaluated as int(0)
            return Type.int()
        else:
            type_error(self.current_stm, Errors.UNSUPPORTED_LETERAL_TYPE,
                       [repr(ir)])

    def visit_TEMP(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        if (ir.ctx == Ctx.LOAD and
                sym.scope is not self.scope and
                self.scope.has_sym(sym.name) and
                not self.scope.find_sym(sym.name).is_builtin()):
            type_error(self.current_stm, Errors.REFERENCED_BEFORE_ASSIGN,
                       [sym.name])
        # sanity check
        if sym.scope is not self.scope:
            if not (sym.scope.is_namespace() or sym.scope.is_lib()):
                assert sym.is_free()
        return sym.typ

    def visit_ATTR(self, ir):
        return irexp_type(ir, self.scope)

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        if mem_t.is_class():
            return mem_t
        assert mem_t.is_seq()
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, Errors.MUST_BE_X_TYPE,
                       [ir.offset, 'int', offs_t])
        return mem_t.element

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        assert mem_t.is_seq()
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, Errors.MUST_BE_X_TYPE,
                       [ir.offset, 'int', offs_t])
        exp_t = self.visit(ir.exp)
        elem_t = mem_t.element
        if not elem_t.can_assign(exp_t):
            type_error(self.current_stm, Errors.INCOMPATIBLE_TYPES,
                       [elem_t, exp_t])
        return mem_t

    def visit_ARRAY(self, ir):
        if self.current_stm.dst.is_a(TEMP) and self.current_stm.dst.name == '__all__':
            return irexp_type(ir, self.scope)
        for item in ir.items:
            item_type = self.visit(item)
            if not (item_type.is_int() or item_type.is_bool()):
                type_error(self.current_stm, Errors.SEQ_ITEM_MUST_BE_INT,
                           [item_type])
        return irexp_type(ir, self.scope)

    def visit_EXPR(self, ir):
        self.visit(ir.exp)
        if ir.exp.is_a(CALL):
            callee_scope = ir.exp.get_callee_scope(self.scope)
            if callee_scope.return_type and callee_scope.return_type.is_none():
                #TODO: warning
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
        if not self.scope.return_type.can_assign(exp_t):
            type_error(ir, Errors.INCOMPATIBLE_RETURN_TYPE,
                       [self.scope.return_type, exp_t])

    def visit_MOVE(self, ir):
        src_t = self.visit(ir.src)
        dst_t = self.visit(ir.dst)
        dst_sym = qualified_symbols(ir.dst, self.scope)[-1]
        assert isinstance(dst_sym, Symbol)
        if ir.dst.is_a(TEMP) and dst_sym.is_return():
            assert not dst_t.is_undef()
            if not dst_t.is_same(src_t) and not dst_t.can_assign(src_t):
                type_error(ir, Errors.INCOMPATIBLE_RETURN_TYPE,
                           [dst_t, src_t])
        else:
            if not dst_t.can_assign(src_t):
                type_error(ir, Errors.INCOMPATIBLE_TYPES,
                           [dst_t, src_t])
        if (dst_t.is_seq() and
                isinstance(dst_t.length, int) and
                dst_t.length != Type.ANY_LENGTH):
            if ir.src.is_a(ARRAY):
                if len(ir.src.items * ir.src.repeat.value) > dst_t.length:
                    type_error(self.current_stm, Errors.SEQ_CAPACITY_OVERFLOWED,
                               [])

    def visit_PHI(self, ir):
        var_sym = qualified_symbols(ir.var, self.scope)[-1]
        assert isinstance(var_sym, Symbol)
        assert var_sym.typ is not None
        #assert all([arg is None or arg.symbol.typ is not None for arg, blk in ir.args])
        arg_types = [self.visit(arg) for arg in ir.args]
        var_t = self.visit(ir.var)
        if ir.var.is_a(TEMP) and var_sym.is_return():
            assert not var_t.is_undef()
            for arg_t in arg_types:
                if not var_t.is_same(arg_t):
                    type_error(ir, Errors.INCOMPATIBLE_RETURN_TYPE,
                               [var_t, arg_t])
        else:
            for arg_t in arg_types:
                if not var_t.can_assign(arg_t):
                    type_error(ir, Errors.INCOMPATIBLE_TYPES,
                               [var_t, arg_t])

    def _check_param_number(self, arg_len, param_len, ir, scope_name, with_vararg=False):
        if arg_len == param_len:
            pass
        elif arg_len < param_len:
            type_error(self.current_stm, Errors.MISSING_REQUIRED_ARG,
                       [scope_name])
        elif not with_vararg:
            type_error(self.current_stm, Errors.TAKES_TOOMANY_ARGS,
                       [scope_name, param_len, arg_len])

    def _check_param_type(self, scope, param_typs, ir, scope_name, with_vararg=False):
        if with_vararg:
            if len(ir.args) > len(param_typs):
                tails = tuple([param_typs[-1]] * (len(ir.args) - len(param_typs)))
                param_typs = param_typs + tails
        assert len(ir.args) == len(param_typs)
        for (name, arg), param_t in zip(ir.args, param_typs):
            arg_t = self.visit(arg)
            if not param_t.can_assign(arg_t):
                type_error(self.current_stm, Errors.INCOMPATIBLE_PARAMETER_TYPE,
                           [arg.name, scope_name])


class EarlyTypeChecker(IRVisitor):
    def visit_CALL(self, ir):
        arg_len = len(ir.args)
        callee_scope = ir.get_callee_scope(self.scope)
        assert callee_scope
        if callee_scope.is_lib():
            return callee_scope.return_type
        if callee_scope.is_pure():
            return Type.any()

        param_typs = callee_scope.param_types()
        param_len = len(param_typs)
        #with_vararg = param_len and param_typs[-1].has_vararg()
        # TODO:
        with_vararg = False
        self._check_param_number(arg_len, param_len, ir, callee_scope.orig_name, with_vararg)
        return callee_scope.return_type

    def visit_SYSCALL(self, ir):
        if ir.name in env.all_scopes:
            syscall_scope = env.all_scopes[ir.name]
            arg_len = len(ir.args)
            param_typs = tuple(syscall_scope.param_types())
            param_len = len(param_typs)
            # with_vararg = len(param_typs) and param_typs[-1].has_vararg()
            # TODO:
            with_vararg = False
            self._check_param_number(arg_len, param_len, ir, ir.name, with_vararg)
        else:
            for _, arg in ir.args:
                self.visit(arg)
        sym_t = irexp_type(ir, self.scope)
        assert sym_t.is_function()
        return sym_t.return_type

    def visit_NEW(self, ir):
        arg_len = len(ir.args)
        callee_scope = ir.get_callee_scope(self.scope)
        ctor = callee_scope.find_ctor()
        if not ctor and arg_len:
            type_error(self.current_stm, Errors.TAKES_TOOMANY_ARGS,
                       [callee_scope.orig_name, 0, arg_len])
        param_typs = ctor.param_types()
        param_len = len(param_typs)
        #with_vararg = len(param_typs) and param_typs[-1].has_vararg()
        # TODO:
        with_vararg = False
        self._check_param_number(arg_len, param_len, ir, callee_scope.orig_name, with_vararg)
        return Type.object(callee_scope)

    def _check_param_number(self, arg_len, param_len, ir, scope_name, with_vararg=False):
        if arg_len == param_len:
            pass
        elif arg_len < param_len:
            type_error(self.current_stm, Errors.MISSING_REQUIRED_ARG,
                       [scope_name])
        elif not with_vararg:
            type_error(self.current_stm, Errors.TAKES_TOOMANY_ARGS,
                       [scope_name, param_len, arg_len])


class PortAssignChecker(IRVisitor):
    def _is_assign_call(self, ir):
        callee_scope = ir.get_callee_scope(self.scope)
        if callee_scope.parent.is_port() and callee_scope.base_name == 'assign':
            return True
        elif callee_scope.parent.name.startswith('polyphony.Net') and callee_scope.base_name == 'assign':
            return True
        return False

    def visit_CALL(self, ir):
        if self._is_assign_call(ir):
            assert len(ir.args) == 1
            arg_t = irexp_type(ir.args[0][1], self.scope)
            assigned = arg_t.scope
            if (not (assigned.is_method() and assigned.parent.is_module()) and
                    not (assigned.parent.is_method() and assigned.parent.parent.is_module())):
                fail(self.current_stm, Errors.PORT_ASSIGN_CANNOT_ACCEPT)
            assigned.add_tag('assigned')
            assigned.add_tag('comb')

    def visit_NEW(self, ir):
        sym = qualified_symbols(ir, self.scope)[-1]
        assert isinstance(sym, Symbol)
        sym_t = sym.typ
        if sym_t.scope.name.startswith('polyphony.Net'):
            if len(ir.args) == 1:
                arg_t = ir.args[0][1].symbol.typ
                assigned = arg_t.scope
                if (not (assigned.is_method() and assigned.parent.is_module()) and
                        not (assigned.parent.is_method() and assigned.parent.parent.is_module())):
                    fail(self.current_stm, Errors.PORT_ASSIGN_CANNOT_ACCEPT)
                assigned.add_tag('assigned')
                assigned.add_tag('comb')


class EarlyRestrictionChecker(IRVisitor):
    def visit_SYSCALL(self, ir):
        if ir.name in ('range', 'polyphony.unroll', 'polyphony.pipelined'):
            fail(self.current_stm, Errors.USE_OUTSIDE_FOR, [ir.name])


class RestrictionChecker(IRVisitor):
    def visit_NEW(self, ir):
        callee_scope = ir.get_callee_scope(self.scope)
        if callee_scope.is_module():
            if not callee_scope.parent.is_namespace():
                fail(self.current_stm, Errors.MUDULE_MUST_BE_IN_GLOBAL)
            for i, (_, arg) in enumerate(ir.args):
                if arg.is_a(IRVariable):
                    arg_t = irexp_type(arg, self.scope)
                    if arg_t.is_scalar() or arg_t.is_class():
                        continue
                    fail(self.current_stm, Errors.MODULE_ARG_MUST_BE_X_TYPE, [arg_t])
        if self.scope.is_global() and not callee_scope.is_module():
            fail(self.current_stm, Errors.GLOBAL_INSTANCE_IS_NOT_SUPPORTED)

    def visit_CALL(self, ir):
        self.visit(ir.func)
        callee_scope = ir.get_callee_scope(self.scope)
        if callee_scope.is_method() and callee_scope.parent.is_module():
            if callee_scope.parent.find_child(self.scope.name, rec=True):
                return
            if callee_scope.base_name == 'append_worker':
                if not (self.scope.is_ctor() and self.scope.parent.is_module()):
                    fail(self.current_stm, Errors.CALL_APPEND_WORKER_IN_CTOR)
                self._check_append_worker(ir)
            # if not (self.scope.is_method() and self.scope.parent.is_module()):
            #    fail(self.current_stm, Errors.CALL_MODULE_METHOD)

    def _check_append_worker(self, call):
        for i, (_, arg) in enumerate(call.args):
            if i == 0:
                func = arg
                func_t = func.symbol.typ
                assert func_t.is_function()
                worker_scope = func_t.scope
                if worker_scope.is_method():
                    assert self.scope.is_ctor()
                    if not self.scope.parent.is_subclassof(worker_scope.parent):
                        fail(self.current_stm, Errors.WORKER_MUST_BE_METHOD_OF_MODULE)
                continue
            if arg.is_a(CONST):
                continue
            if arg.is_a(IRVariable):
                arg_t = irexp_type(arg, self.scope)
                if arg_t.is_scalar() or arg_t.is_object():
                    continue
                type_error(self.current_stm, Errors.WORKER_ARG_MUST_BE_X_TYPE,
                        [arg_t])

    def visit_ATTR(self, ir: ATTR):
        syms = qualified_symbols(ir, self.scope)
        head = syms[0]
        assert isinstance(head, Symbol)
        head_t = head.typ
        if (head.scope is not self.scope and
                head_t.is_object() and
                not self.scope.is_testbench() and
                not self.scope.is_assigned() and
                not self.scope.is_closure()):
            scope = head_t.scope
            if scope.is_module():
                fail(self.current_stm, Errors.INVALID_MODULE_OBJECT_ACCESS)


class LateRestrictionChecker(IRVisitor):
    def visit_ARRAY(self, ir):
        if not ir.repeat.is_a(CONST):
            fail(self.current_stm, Errors.SEQ_MULTIPLIER_MUST_BE_CONST)

    def visit_MSTORE(self, ir):
        mem_sym = qualified_symbols(ir.mem, self.scope)[-1]
        assert isinstance(mem_sym, Symbol)
        if mem_sym.is_static():
            fail(self.current_stm, Errors.GLOBAL_OBJECT_CANT_BE_MUTABLE)

    def visit_NEW(self, ir):
        callee_scope = ir.get_callee_scope(self.scope)
        if callee_scope.is_port():
            if not (self.scope.is_ctor() and self.scope.parent.is_module()):
                fail(self.current_stm, Errors.PORT_MUST_BE_IN_MODULE)

    def visit_MOVE(self, ir):
        super().visit_MOVE(ir)
        reserved_port_name = ('clk', 'rst')
        if ir.src.is_a(NEW):
            callee_scope = ir.src.get_callee_scope(self.scope)
            if callee_scope.is_port() and ir.dst.name in reserved_port_name:
                fail(self.current_stm, Errors.RESERVED_PORT_NAME, [ir.dst.symbol.name])


class AssertionChecker(IRVisitor):
    def visit_SYSCALL(self, ir):
        if ir.name != 'assert':
            return
        _, arg = ir.args[0]
        if arg.is_a(CONST) and not arg.value:
            warn(self.current_stm, Warnings.ASSERTION_FAILED)


class SynthesisParamChecker(object):
    def process(self, scope):
        self.scope = scope
        if scope.synth_params['scheduling'] == 'pipeline':
            if scope.is_worker() or (scope.is_closure() and scope.parent.is_worker()):
                pass
            else:
                fail((env.scope_file_map[scope], scope.lineno),
                     Errors.RULE_FUNCTION_CANNOT_BE_PIPELINED)
        for blk in scope.traverse_blocks():
            if blk.is_loop_head():
                if blk.synth_params['scheduling'] == 'pipeline':
                    loop = scope.find_region(blk)
                    self._check_channel_conflict_in_pipeline(loop, scope)

    def _check_channel_conflict_in_pipeline(self, loop, scope):
        syms = scope.usedef.get_all_def_syms() | scope.usedef.get_all_use_syms()
        for sym in syms:
            if not self._is_channel(sym):
                continue
            usestms = sorted(scope.usedef.get_stms_using(sym), key=lambda s: s.program_order())
            usestms = [stm for stm in usestms if stm.block in loop.blocks()]
            readstms = []
            for stm in usestms:
                if stm.is_a(MOVE) and stm.src.is_a(CALL) and stm.src.func.symbol.orig_name() == 'get':
                    readstms.append(stm)
            writestms = []
            for stm in usestms:
                if stm.is_a(EXPR) and stm.exp.is_a(CALL) and stm.exp.func.symbol.orig_name() == 'put':
                    writestms.append(stm)
            if len(readstms) > 1:
                sym = sym.ancestor if sym.ancestor else sym
                fail(readstms[1], Errors.RULE_READING_PIPELINE_IS_CONFLICTED, [sym])
            if len(writestms) > 1:
                sym = sym.ancestor if sym.ancestor else sym
                fail(writestms[1], Errors.RULE_WRITING_PIPELINE_IS_CONFLICTED, [sym])
            if len(readstms) >= 1 and len(writestms) >= 1:
                assert False

    def _is_channel(self, sym):
        sym_t = sym.typ
        if not sym_t.is_object():
            return False
        scp = sym_t.scope
        return scp.origin.name == 'polyphony.Channel'
