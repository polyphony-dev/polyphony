from ..irvisitor import IRVisitor
from ..ir import *
from ..type import Type
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
        if not Type.is_compatible(l_t, r_t):
            type_error(self.current_stm, Errors.INCOMPTIBLE_TYPES,
                       [l_t, r_t])
        return l_t

    def visit_CALL(self, ir):
        arg_len = len(ir.args)
        if ir.func_scope().is_lib():
            return ir.func_scope().return_type
        assert ir.func_scope()
        if ir.func_scope().is_pure():
            return Type.any()
        elif ir.func_scope().is_method():
            param_typs = tuple([sym.typ for sym, _, _ in ir.func_scope().params[1:]])
        else:
            param_typs = tuple([sym.typ for sym, _, _ in ir.func_scope().params])
        param_len = len(param_typs)
        with_vararg = param_len and param_typs[-1].has_vararg()
        self._check_param_number(arg_len, param_len, ir, ir.func_scope().orig_name, with_vararg)
        self._check_param_type(ir.func_scope(), param_typs, ir, ir.func_scope().orig_name, with_vararg)

        return ir.func_scope().return_type

    def visit_SYSCALL(self, ir):
        if ir.sym.name == 'len':
            if len(ir.args) != 1:
                type_error(self.current_stm, Errors.LEN_TAKES_ONE_ARG)
            _, mem = ir.args[0]
            if not mem.is_a([TEMP, ATTR]) or not mem.symbol().typ.is_seq():
                type_error(self.current_stm, Errors.LEN_TAKES_SEQ_TYPE)
        elif ir.sym.name == 'print':
            for _, arg in ir.args:
                arg_t = self.visit(arg)
                if not arg_t.is_scalar():
                    type_error(self.current_stm, Errors.PRINT_TAKES_SCALAR_TYPE)
        elif ir.sym.name == '$new':
            _, typ = ir.args[0]
            assert typ.symbol().typ.is_class()
            return Type.object(typ.symbol().typ.get_scope())
        elif ir.sym.name in env.all_scopes:
            scope = env.all_scopes[ir.sym.name]
            arg_len = len(ir.args)
            param_len = len(scope.params)
            param_typs = tuple([sym.typ for sym, _, _ in scope.params])
            with_vararg = len(param_typs) and param_typs[-1].has_vararg()
            self._check_param_number(arg_len, param_len, ir, ir.sym.name, with_vararg)
            self._check_param_type(scope, param_typs, ir, ir.sym.name, with_vararg)
        else:
            for _, arg in ir.args:
                self.visit(arg)
        assert ir.sym.typ.is_function()
        return ir.sym.typ.get_return_type()

    def visit_NEW(self, ir):
        arg_len = len(ir.args)

        ctor = ir.func_scope().find_ctor()
        if not ctor and arg_len:
            type_error(self.current_stm, Errors.TAKES_TOOMANY_ARGS,
                       [ir.func_scope().orig_name, 0, arg_len])
        param_len = len(ctor.params) - 1
        param_typs = tuple([param.sym.typ for param in ctor.params])[1:]
        with_vararg = len(param_typs) and param_typs[-1].has_vararg()
        self._check_param_number(arg_len, param_len, ir, ir.func_scope().orig_name, with_vararg)
        self._check_param_type(ir.func_scope(), param_typs, ir, ir.func_scope().orig_name, with_vararg)

        return Type.object(ir.func_scope())

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
        if (ir.ctx == Ctx.LOAD and
                ir.sym.scope is not self.scope and
                self.scope.has_sym(ir.sym.name) and
                not self.scope.find_sym(ir.sym.name).is_builtin()):
            type_error(self.current_stm, Errors.REFERENCED_BEFORE_ASSIGN,
                       [ir.sym.name])
        # sanity check
        if ir.sym.scope is not self.scope:
            if not (ir.sym.scope.is_namespace() or ir.sym.scope.is_lib()):
                assert ir.sym.is_free()
        return ir.sym.typ

    def visit_ATTR(self, ir):
        return ir.attr.typ

    def visit_MREF(self, ir):
        mem_t = self.visit(ir.mem)
        if mem_t.is_class():
            return mem_t
        assert mem_t.is_seq()
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, Errors.MUST_BE_X_TYPE,
                       [ir.offset, 'int', offs_t])
        return mem_t.get_element()

    def visit_MSTORE(self, ir):
        mem_t = self.visit(ir.mem)
        assert mem_t.is_seq()
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, Errors.MUST_BE_X_TYPE,
                       [ir.offset, 'int', offs_t])
        exp_t = self.visit(ir.exp)
        elem_t = mem_t.get_element()
        if not Type.is_assignable(elem_t, exp_t):
            type_error(self.current_stm, Errors.INCOMPATIBLE_TYPES,
                       [elem_t, exp_t])
        return mem_t

    def visit_ARRAY(self, ir):
        if self.current_stm.dst.is_a(TEMP) and self.current_stm.dst.symbol().name == '__all__':
            return ir.sym.typ
        for item in ir.items:
            item_type = self.visit(item)
            if not (item_type.is_int() or item_type.is_bool()):
                type_error(self.current_stm, Errors.SEQ_ITEM_MUST_BE_INT,
                           [item_type])
        return ir.sym.typ

    def visit_EXPR(self, ir):
        self.visit(ir.exp)
        if ir.exp.is_a(CALL):
            if ir.exp.func_scope().return_type and ir.exp.func_scope().return_type.is_none():
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
        if not Type.is_assignable(self.scope.return_type, exp_t):
            type_error(ir, Errors.INCOMPATIBLE_RETURN_TYPE,
                       [self.scope.return_type, exp_t])

    def visit_MOVE(self, ir):
        src_t = self.visit(ir.src)
        dst_t = self.visit(ir.dst)
        if ir.dst.is_a(TEMP) and ir.dst.symbol().is_return():
            assert not dst_t.is_undef()
            if not Type.is_same(dst_t, src_t):
                type_error(ir, Errors.INCOMPATIBLE_RETURN_TYPE,
                           [dst_t, src_t])
        else:
            if not Type.is_assignable(dst_t, src_t):
                type_error(ir, Errors.INCOMPATIBLE_TYPES,
                           [dst_t, src_t])
        if (dst_t.is_seq() and
                dst_t.has_length() and
                isinstance(dst_t.get_length(), int) and
                dst_t.get_length() != Type.ANY_LENGTH):
            if ir.src.is_a(ARRAY):
                if len(ir.src.items * ir.src.repeat.value) > dst_t.get_length():
                    type_error(self.current_stm, Errors.SEQ_CAPACITY_OVERFLOWED,
                               [])

    def visit_PHI(self, ir):
        assert ir.var.symbol().typ is not None
        #assert all([arg is None or arg.symbol().typ is not None for arg, blk in ir.args])
        arg_types = [self.visit(arg) for arg in ir.args]
        var_t = self.visit(ir.var)
        if ir.var.is_a(TEMP) and ir.var.symbol().is_return():
            assert not var_t.is_undef()
            for arg_t in arg_types:
                if not Type.is_same(var_t, arg_t):
                    type_error(ir, Errors.INCOMPATIBLE_RETURN_TYPE,
                               [var_t, arg_t])
        else:
            for arg_t in arg_types:
                if not Type.is_assignable(var_t, arg_t):
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
            if not Type.is_assignable(param_t, arg_t):
                type_error(self.current_stm, Errors.INCOMPATIBLE_PARAMETER_TYPE,
                           [arg.symbol().orig_name(), scope_name])


class EarlyTypeChecker(IRVisitor):
    def visit_CALL(self, ir):
        arg_len = len(ir.args)
        if ir.func_scope().is_lib():
            return ir.func_scope().return_type
        assert ir.func_scope()
        if ir.func_scope().is_pure():
            return Type.any()
        if ir.func_scope().is_method():
            param_typs = tuple([sym.typ for sym, _, _ in ir.func_scope().params[1:]])
        else:
            param_typs = tuple([sym.typ for sym, _, _ in ir.func_scope().params])
        param_len = len(param_typs)
        with_vararg = param_len and param_typs[-1].has_vararg()
        self._check_param_number(arg_len, param_len, ir, ir.func_scope().orig_name, with_vararg)
        return ir.func_scope().return_type

    def visit_SYSCALL(self, ir):
        if ir.sym.name in env.all_scopes:
            scope = env.all_scopes[ir.sym.name]
            arg_len = len(ir.args)
            param_len = len(scope.params)
            param_typs = tuple([sym.typ for sym, _, _ in scope.params])
            with_vararg = len(param_typs) and param_typs[-1].has_vararg()
            self._check_param_number(arg_len, param_len, ir, ir.sym.name, with_vararg)
        else:
            for _, arg in ir.args:
                self.visit(arg)
        assert ir.sym.typ.is_function()
        return ir.sym.typ.get_return_type()

    def visit_NEW(self, ir):
        arg_len = len(ir.args)
        ctor = ir.func_scope().find_ctor()
        if not ctor and arg_len:
            type_error(self.current_stm, Errors.TAKES_TOOMANY_ARGS,
                       [ir.func_scope().orig_name, 0, arg_len])
        param_len = len(ctor.params) - 1
        param_typs = tuple([param.sym.typ for param in ctor.params])[1:]
        with_vararg = len(param_typs) and param_typs[-1].has_vararg()
        self._check_param_number(arg_len, param_len, ir, ir.func_scope().orig_name, with_vararg)
        return Type.object(ir.func_scope())

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
        if ir.func_scope().parent.is_port() and ir.func_scope().base_name == 'assign':
            return True
        elif ir.func_scope().parent.name.startswith('polyphony.Net') and ir.func_scope().base_name == 'assign':
            return True
        return False

    def visit_CALL(self, ir):
        if self._is_assign_call(ir):
            assert len(ir.args) == 1
            assigned = ir.args[0][1].symbol().typ.get_scope()
            if (not (assigned.is_method() and assigned.parent.is_module()) and
                    not (assigned.parent.is_method() and assigned.parent.parent.is_module())):
                fail(self.current_stm, Errors.PORT_ASSIGN_CANNOT_ACCEPT)
            assigned.add_tag('assigned')
            assigned.add_tag('comb')

    def visit_NEW(self, ir):
        if ir.sym.typ.get_scope().name.startswith('polyphony.Net'):
            if len(ir.args) == 1:
                assigned = ir.args[0][1].symbol().typ.get_scope()
                if (not (assigned.is_method() and assigned.parent.is_module()) and
                        not (assigned.parent.is_method() and assigned.parent.parent.is_module())):
                    fail(self.current_stm, Errors.PORT_ASSIGN_CANNOT_ACCEPT)
                assigned.add_tag('assigned')
                assigned.add_tag('comb')


class EarlyRestrictionChecker(IRVisitor):
    def visit_SYSCALL(self, ir):
        if ir.sym.name in ('range', 'polyphony.unroll', 'polyphony.pipelined'):
            fail(self.current_stm, Errors.USE_OUTSIDE_FOR, [ir.sym.name])


class RestrictionChecker(IRVisitor):
    def visit_NEW(self, ir):
        if ir.func_scope().is_module():
            if not ir.func_scope().parent.is_namespace():
                fail(self.current_stm, Errors.MUDULE_MUST_BE_IN_GLOBAL)
            for i, (_, arg) in enumerate(ir.args):
                if (arg.is_a([TEMP, ATTR])):
                    typ = arg.symbol().typ
                    if typ.is_scalar() or typ.is_class():
                        continue
                    fail(self.current_stm, Errors.MODULE_ARG_MUST_BE_X_TYPE, [typ])
        if self.scope.is_global() and not ir.func_scope().is_module():
            fail(self.current_stm, Errors.GLOBAL_INSTANCE_IS_NOT_SUPPORTED)

    def visit_CALL(self, ir):
        self.visit(ir.func)
        if ir.func_scope().is_method() and ir.func_scope().parent.is_module():
            if ir.func_scope().parent.find_child(self.scope.name, rec=True):
                return
            if ir.func_scope().base_name == 'append_worker':
                if not (self.scope.is_ctor() and self.scope.parent.is_module()):
                    fail(self.current_stm, Errors.CALL_APPEND_WORKER_IN_CTOR)
                self._check_append_worker(ir)
            # if not (self.scope.is_method() and self.scope.parent.is_module()):
            #    fail(self.current_stm, Errors.CALL_MODULE_METHOD)

    def _check_append_worker(self, call):
        for i, (_, arg) in enumerate(call.args):
            if i == 0:
                func = arg
                assert func.symbol().typ.is_function()
                worker_scope = func.symbol().typ.get_scope()
                if worker_scope.is_method():
                    assert self.scope.is_ctor()
                    if not self.scope.parent.is_subclassof(worker_scope.parent):
                        fail(self.current_stm, Errors.WORKER_MUST_BE_METHOD_OF_MODULE)
                continue
            if arg.is_a(CONST):
                continue
            if (arg.is_a([TEMP, ATTR])):
                typ = arg.symbol().typ
                if typ.is_scalar():
                    continue
                elif typ.is_object():
                    continue
            type_error(self.current_stm, Errors.WORKER_ARG_MUST_BE_X_TYPE,
                       [typ])

    def visit_ATTR(self, ir):
        head = ir.head()
        if (head.scope is not self.scope and
                head.typ.is_object() and
                not self.scope.is_testbench() and
                not self.scope.is_assigned() and
                not self.scope.is_closure()):
            scope = head.typ.get_scope()
            if scope.is_module():
                fail(self.current_stm, Errors.INVALID_MODULE_OBJECT_ACCESS)


class LateRestrictionChecker(IRVisitor):
    def visit_ARRAY(self, ir):
        if not ir.repeat.is_a(CONST):
            fail(self.current_stm, Errors.SEQ_MULTIPLIER_MUST_BE_CONST)

    def visit_MSTORE(self, ir):
        if ir.mem.symbol().is_static():
            fail(self.current_stm, Errors.GLOBAL_OBJECT_CANT_BE_MUTABLE)

    def visit_NEW(self, ir):
        if ir.func_scope().is_port():
            if not (self.scope.is_ctor() and self.scope.parent.is_module()):
                fail(self.current_stm, Errors.PORT_MUST_BE_IN_MODULE)

    def visit_MOVE(self, ir):
        super().visit_MOVE(ir)
        reserved_port_name = ('clk', 'rst')
        if ir.src.is_a(NEW) and ir.src.func_scope().is_port():
            if ir.dst.symbol().name in reserved_port_name:
                fail(self.current_stm, Errors.RESERVED_PORT_NAME, [ir.dst.symbol().name])


class AssertionChecker(IRVisitor):
    def visit_SYSCALL(self, ir):
        if ir.sym.name != 'assert':
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
                if stm.is_a(MOVE) and stm.src.is_a(CALL) and stm.src.func.symbol().orig_name() == 'get':
                    readstms.append(stm)
            writestms = []
            for stm in usestms:
                if stm.is_a(EXPR) and stm.exp.is_a(CALL) and stm.exp.func.symbol().orig_name() == 'put':
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
        if not sym.typ.is_object():
            return False
        scp = sym.typ.get_scope()
        return scp.origin.name == 'polyphony.Channel'
