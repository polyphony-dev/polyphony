"""Type checking and restriction analysis passes using new IR (ir.py)."""
from ..irvisitor import IrVisitor
from ..ir import (
    IrVariable, Temp, Attr, Const, Call, SysCall, New, Array, MRef, MStore,
    Move, Expr, Phi, UPhi, LPhi, Ret, CJump, MCJump, Jump,
    op2sym_map,
)
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


def _get_callee_scope(ir, scope):
    """Resolve callee scope from a Call/New/SysCall node."""
    qsyms = qualified_symbols(ir.func, scope)
    symbol = qsyms[-1]
    assert isinstance(symbol, Symbol)
    func_t = symbol.typ
    assert func_t.has_scope()
    return func_t.scope


class TypeChecker(IrVisitor):
    def __init__(self):
        super().__init__()

    def visit_UnOp(self, ir):
        return self.visit(ir.exp)

    def visit_BinOp(self, ir):
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

    def visit_RelOp(self, ir):
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        valid_l_t = l_t.is_scalar() or l_t.is_object()
        valid_r_t = r_t.is_scalar() or r_t.is_object()
        if not valid_l_t or not valid_r_t:
            type_error(self.current_stm, Errors.UNSUPPORTED_BINARY_OPERAND_TYPE,
                       [op2sym_map[ir.op], l_t, r_t])
        return Type.bool()

    def visit_CondOp(self, ir):
        self.visit(ir.cond)
        l_t = self.visit(ir.left)
        r_t = self.visit(ir.right)
        if not l_t.is_compatible(r_t):
            type_error(self.current_stm, Errors.INCOMPATIBLE_TYPES,
                       [l_t, r_t])
        return l_t

    def visit_Call(self, ir):
        arg_len = len(ir.args)
        callee_scope = _get_callee_scope(ir, self.scope)
        assert callee_scope
        if callee_scope.is_lib():
            return callee_scope.return_type

        if callee_scope.is_pure():
            return Type.any()
        param_typs = callee_scope.param_types()
        param_len = len(param_typs)
        # TODO:
        with_vararg = False
        self._check_param_number(arg_len, param_len, ir, callee_scope.orig_name, with_vararg)
        self._check_param_type(callee_scope, param_typs, ir, callee_scope.orig_name, with_vararg)
        return callee_scope.return_type

    def visit_SysCall(self, ir):
        name = ir.name
        if name == 'len':
            if len(ir.args) != 1:
                type_error(self.current_stm, Errors.LEN_TAKES_ONE_ARG)
            _, mem = ir.args[0]
            mem_t = irexp_type(mem, self.scope)
            if not isinstance(mem, IrVariable) or not mem_t.is_seq():
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
            param_typs = tuple(syscall_scope.param_types())  # type: ignore
            param_len = len(param_typs)
            # TODO:
            with_vararg = False
            self._check_param_number(arg_len, param_len, ir, name, with_vararg)
            self._check_param_type(syscall_scope, param_typs, ir, name, with_vararg)  # type: ignore
        else:
            for _, arg in ir.args:
                self.visit(arg)
        sym_t = irexp_type(ir, self.scope)
        assert sym_t.is_function()
        return sym_t.return_type

    def visit_New(self, ir):
        arg_len = len(ir.args)
        callee_scope = _get_callee_scope(ir, self.scope)
        if callee_scope.is_typeclass():
            return type_from_typeclass(callee_scope)

        ctor = callee_scope.find_ctor()
        if not ctor and arg_len:
            type_error(self.current_stm, Errors.TAKES_TOOMANY_ARGS,
                       [callee_scope.orig_name, 0, arg_len])
        param_typs = ctor.param_types()
        param_len = len(param_typs)
        # TODO:
        with_vararg = False
        self._check_param_number(arg_len, param_len, ir, callee_scope.orig_name, with_vararg)
        self._check_param_type(callee_scope, param_typs, ir, callee_scope.orig_name, with_vararg)
        return Type.object(callee_scope)

    def visit_Const(self, ir):
        match ir.value:
            case bool():
                return Type.bool()
            case int():
                return Type.int()
            case str():
                return Type.str()
            case None:
                # The value of 'None' is evaluated as int(0)
                return Type.int()
            case _:
                type_error(self.current_stm, Errors.UNSUPPORTED_LETERAL_TYPE,
                           [repr(ir)])

    def visit_Temp(self, ir):
        sym = self.scope.find_sym(ir.name)
        assert sym
        # sanity check
        if sym.scope is not self.scope:
            if not (sym.scope.is_namespace() or sym.scope.is_lib()):
                assert sym.is_free() or sym.is_imported()
        return sym.typ

    def visit_Attr(self, ir):
        return irexp_type(ir, self.scope)

    def visit_MRef(self, ir):
        mem_t = self.visit(ir.mem)
        if mem_t.is_class():
            return mem_t
        assert mem_t.is_seq()
        offs_t = self.visit(ir.offset)
        if not offs_t.is_int():
            type_error(self.current_stm, Errors.MUST_BE_X_TYPE,
                       [ir.offset, 'int', offs_t])
        return mem_t.element

    def visit_MStore(self, ir):
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

    def visit_Array(self, ir):
        if isinstance(self.current_stm, Move) and isinstance(self.current_stm.dst, Temp) and self.current_stm.dst.name == '__all__':
            return irexp_type(ir, self.scope)
        for item in ir.items:
            item_type = self.visit(item)
            if not (item_type.is_int() or item_type.is_bool()):
                type_error(self.current_stm, Errors.SEQ_ITEM_MUST_BE_INT,
                           [item_type])
        return irexp_type(ir, self.scope)

    def visit_Expr(self, ir):
        self.visit(ir.exp)
        if isinstance(ir.exp, Call):
            callee_scope = _get_callee_scope(ir.exp, self.scope)
            if callee_scope.return_type and callee_scope.return_type.is_none():
                # TODO: warning
                pass

    def visit_CJump(self, ir):
        self.visit(ir.exp)

    def visit_MCJump(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_Jump(self, ir):
        pass

    def visit_Ret(self, ir):
        exp_t = self.visit(ir.exp)
        if not self.scope.return_type.can_assign(exp_t):
            type_error(ir, Errors.INCOMPATIBLE_RETURN_TYPE,
                       [self.scope.return_type, exp_t])

    def visit_Move(self, ir):
        src_t = self.visit(ir.src)
        dst_t = self.visit(ir.dst)
        dst_sym = qualified_symbols(ir.dst, self.scope)[-1]
        assert isinstance(dst_sym, Symbol)
        if isinstance(ir.dst, Attr) and self._is_in_module_scope():
            self._check_module_object_field_immutability(ir)
        if isinstance(ir.dst, Temp) and dst_sym.is_return():
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
            if isinstance(ir.src, Array):
                if len(ir.src.items * ir.src.repeat.value) > dst_t.length:
                    type_error(self.current_stm, Errors.SEQ_CAPACITY_OVERFLOWED,
                               [])

    def _is_in_module_scope(self) -> bool:
        """Check whether the current scope is inside a module."""
        scope = self.scope
        if scope.is_module():
            return True
        parent = scope.parent
        return parent is not None and parent.is_module()

    def _check_module_object_field_immutability(self, ir):
        """Check that fields of module-typed objects are not written in a module scope.

        After flattening, a worker parameter like 'tgt' (module instance)
        becomes a subobject accessed via 'self.tgt'. The write pattern is:
            tgt = self.tgt
            tgt.value = 99
        The root 'tgt' has tag 'subobject' and its type is a module object.
        """
        dst_attr = ir.dst
        # Walk up the Attr chain to find the root variable
        root = dst_attr
        while isinstance(root, Attr):
            root = root.exp
        if not isinstance(root, Temp):
            return
        root_name = root.name
        # Skip writes to self fields (those are handled separately)
        if root_name == env.self_name:
            return
        root_sym = self.scope.find_sym(root_name)
        if root_sym is None:
            return
        if root_sym.typ.is_object() and root_sym.typ.scope.is_module():
            if root_sym.typ.scope.is_mutable_fields():
                return
            fail(self.current_stm, Errors.MODULE_OBJECT_FIELD_IS_IMMUTABLE, [dst_attr.attr])

    def visit_Phi(self, ir):
        var_sym = qualified_symbols(ir.var, self.scope)[-1]
        assert isinstance(var_sym, Symbol)
        assert var_sym.typ is not None
        arg_types = [self.visit(arg) for arg in ir.args]
        var_t = self.visit(ir.var)
        if isinstance(ir.var, Temp) and var_sym.is_return():
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


class EarlyTypeChecker(IrVisitor):
    def visit_Call(self, ir):
        arg_len = len(ir.args)
        callee_scope = _get_callee_scope(ir, self.scope)
        assert callee_scope
        if callee_scope.is_lib():
            return callee_scope.return_type
        if callee_scope.is_pure():
            return Type.any()

        param_typs = callee_scope.param_types()
        param_len = len(param_typs)
        # TODO:
        with_vararg = False
        self._check_param_number(arg_len, param_len, ir, callee_scope.orig_name, with_vararg)
        return callee_scope.return_type

    def visit_SysCall(self, ir):
        if ir.name in env.all_scopes:
            syscall_scope = env.all_scopes[ir.name]
            arg_len = len(ir.args)
            param_typs = tuple(syscall_scope.param_types())  # type: ignore
            param_len = len(param_typs)
            # TODO:
            with_vararg = False
            self._check_param_number(arg_len, param_len, ir, ir.name, with_vararg)
        else:
            for _, arg in ir.args:
                self.visit(arg)
        sym_t = irexp_type(ir, self.scope)
        assert sym_t.is_function()
        return sym_t.return_type

    def visit_New(self, ir):
        arg_len = len(ir.args)
        callee_scope = _get_callee_scope(ir, self.scope)
        ctor = callee_scope.find_ctor()
        if not ctor and arg_len:
            type_error(self.current_stm, Errors.TAKES_TOOMANY_ARGS,
                       [callee_scope.orig_name, 0, arg_len])
        param_typs = ctor.param_types()
        param_len = len(param_typs)
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


class PortAssignChecker(IrVisitor):
    def _is_assign_call(self, ir):
        callee_scope = _get_callee_scope(ir, self.scope)
        if callee_scope.parent.is_port() and callee_scope.base_name == 'assign':
            return True
        elif callee_scope.parent.name.startswith('polyphony.Net') and callee_scope.base_name == 'assign':
            return True
        return False

    def visit_Call(self, ir):
        if self._is_assign_call(ir):
            assert len(ir.args) == 1
            arg_t = irexp_type(ir.args[0][1], self.scope)
            assigned = arg_t.scope
            if (not (assigned.is_method() and assigned.parent.is_module()) and
                    not (assigned.parent.is_method() and assigned.parent.parent.is_module())):
                fail(self.current_stm, Errors.PORT_ASSIGN_CANNOT_ACCEPT)
            assigned.add_tag('assigned')
            assigned.add_tag('comb')

    def visit_New(self, ir):
        sym = qualified_symbols(ir, self.scope)[-1]
        assert isinstance(sym, Symbol)
        sym_t = sym.typ
        if sym_t.scope.name.startswith('polyphony.Net'):
            if len(ir.args) == 1:
                # Access the symbol for the argument
                arg_qsyms = qualified_symbols(ir.args[0][1], self.scope)
                arg_sym = arg_qsyms[-1]
                assert isinstance(arg_sym, Symbol)
                arg_t = arg_sym.typ
                assigned = arg_t.scope
                if (not (assigned.is_method() and assigned.parent.is_module()) and
                        not (assigned.parent.is_method() and assigned.parent.parent.is_module())):
                    fail(self.current_stm, Errors.PORT_ASSIGN_CANNOT_ACCEPT)
                assigned.add_tag('assigned')
                assigned.add_tag('comb')


class EarlyRestrictionChecker(IrVisitor):
    def visit_SysCall(self, ir):
        if ir.name in ('range', 'polyphony.unroll', 'polyphony.pipelined'):
            fail(self.current_stm, Errors.USE_OUTSIDE_FOR, [ir.name])


class RestrictionChecker(IrVisitor):
    def visit_New(self, ir):
        callee_scope = _get_callee_scope(ir, self.scope)
        if callee_scope.is_module():
            if not callee_scope.parent.is_namespace():
                fail(self.current_stm, Errors.MUDULE_MUST_BE_IN_GLOBAL)
            for i, (_, arg) in enumerate(ir.args):
                if isinstance(arg, IrVariable):
                    arg_t = irexp_type(arg, self.scope)
                    if arg_t.is_scalar() or arg_t.is_class() or arg_t.is_function() or arg_t.is_seq():
                        continue
                    if arg_t.is_object() and not arg_t.scope.is_module():
                        continue
                    if arg_t.is_object() and arg_t.scope.is_module():
                        continue
                    fail(self.current_stm, Errors.MODULE_ARG_MUST_BE_X_TYPE, [arg_t])
        if self.scope.is_global() and not callee_scope.is_module():
            fail(self.current_stm, Errors.GLOBAL_INSTANCE_IS_NOT_SUPPORTED)

    def visit_Move(self, ir):
        # Check for writes to object argument fields in module scope
        if isinstance(ir.dst, Attr) and self._is_in_module_scope():
            self._check_object_field_immutability(ir)
        super().visit_Move(ir)

    def _is_in_module_scope(self) -> bool:
        scope = self.scope
        if scope.is_module():
            return True
        parent = scope.parent
        return parent is not None and parent.is_module()

    def _check_object_field_immutability(self, ir):
        """Check that object arguments passed to module ctors are not mutated."""
        dst_attr = ir.dst
        # Walk up the Attr chain to find the root variable
        root = dst_attr
        while isinstance(root, Attr):
            root = root.exp
        if not isinstance(root, Temp):
            return
        root_name = root.name
        if root_name == env.self_name:
            # self.field = ... — check if field is an object param
            # After flattening, writes look like self.cfg_width = ...
            # But before flattening, writes look like self.cfg.width = ...
            # Check the intermediate attribute
            if not isinstance(dst_attr.exp, Attr):
                return
            inner_attr = dst_attr.exp
            if not isinstance(inner_attr.exp, Temp) or inner_attr.exp.name != env.self_name:
                return
            field_name = inner_attr.attr
            module_scope = self.scope.parent if not self.scope.is_module() else self.scope
            if module_scope is None:
                return
            field_sym = module_scope.find_sym(field_name)
            if field_sym is None:
                return
            if field_sym.typ.is_object():
                fail(self.current_stm, Errors.MODULE_OBJECT_FIELD_IS_IMMUTABLE, [dst_attr.attr])
        else:
            # Direct write to object param: cfg.width = ... (in ctor before self assignment)
            scope = self.scope
            module_scope = scope.parent if not scope.is_module() else scope
            if module_scope is None:
                return
            root_sym = scope.find_sym(root_name)
            if root_sym is None:
                return
            if root_sym.typ.is_object() and root_sym.is_param():
                if root_sym.typ.scope.is_mutable_fields():
                    return
                fail(self.current_stm, Errors.MODULE_OBJECT_FIELD_IS_IMMUTABLE, [dst_attr.attr])

    def visit_Call(self, ir):
        self.visit(ir.func)
        callee_scope = _get_callee_scope(ir, self.scope)
        if callee_scope.is_method() and callee_scope.parent.is_module():
            if callee_scope.parent.find_child(self.scope.name, rec=True):
                return
            if callee_scope.base_name == 'append_worker':
                if not (self.scope.is_ctor() and self.scope.parent.is_module()):
                    fail(self.current_stm, Errors.CALL_APPEND_WORKER_IN_CTOR)
                self._check_append_worker(ir)

    def _check_append_worker(self, call):
        for i, (_, arg) in enumerate(call.args):
            if i == 0:
                func = arg
                func_qsyms = qualified_symbols(func, self.scope)
                func_sym = func_qsyms[-1]
                assert isinstance(func_sym, Symbol)
                func_t = func_sym.typ
                assert func_t.is_function()
                worker_scope = func_t.scope
                if worker_scope.is_method():
                    assert self.scope.is_ctor()
                    if not self.scope.parent.is_subclassof(worker_scope.parent):
                        fail(self.current_stm, Errors.WORKER_MUST_BE_METHOD_OF_MODULE)
                continue
            if isinstance(arg, Const):
                continue
            if isinstance(arg, IrVariable):
                arg_t = irexp_type(arg, self.scope)
                if arg_t.is_scalar() or arg_t.is_object() or arg_t.is_function():
                    continue
                type_error(self.current_stm, Errors.WORKER_ARG_MUST_BE_X_TYPE,
                           [arg_t])

    def visit_Attr(self, ir):
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


class LateRestrictionChecker(IrVisitor):
    def visit_Array(self, ir):
        if not isinstance(ir.repeat, Const):
            fail(self.current_stm, Errors.SEQ_MULTIPLIER_MUST_BE_CONST)

    def visit_MStore(self, ir):
        mem_sym = qualified_symbols(ir.mem, self.scope)[-1]
        assert isinstance(mem_sym, Symbol)
        if mem_sym.is_static():
            fail(self.current_stm, Errors.GLOBAL_OBJECT_CANT_BE_MUTABLE)

    def visit_New(self, ir):
        callee_scope = _get_callee_scope(ir, self.scope)
        if callee_scope.is_port():
            if not (self.scope.is_ctor() and self.scope.parent.is_module()):
                fail(self.current_stm, Errors.PORT_MUST_BE_IN_MODULE)

    def visit_Move(self, ir):
        super().visit_Move(ir)
        reserved_port_name = ('clk', 'rst')
        if isinstance(ir.src, New):
            callee_scope = _get_callee_scope(ir.src, self.scope)
            if callee_scope.is_port() and ir.dst.name in reserved_port_name:
                dst_sym = qualified_symbols(ir.dst, self.scope)[-1]
                assert isinstance(dst_sym, Symbol)
                fail(self.current_stm, Errors.RESERVED_PORT_NAME, [dst_sym.name])


class AssertionChecker(IrVisitor):
    def visit_SysCall(self, ir):
        if ir.name != 'assert':
            return
        _, arg = ir.args[0]
        if isinstance(arg, Const) and not arg.value:
            warn(self.current_stm, Warnings.ASSERTION_FAILED)


class PortAccessChecker(IrVisitor):
    """Check port access control rules.

    - thru'd output ports cannot be written from parent side (wr, assign)
    - submodule's output ports cannot be written from parent (wr, assign)
    - submodule's input ports cannot be read from parent (rd)
    """

    def visit_Call(self, ir):
        callee_scope = _get_callee_scope(ir, self.scope)
        if not callee_scope.is_method():
            return
        parent_scope = callee_scope.parent
        if not parent_scope.is_port():
            return
        method_name = callee_scope.base_name
        if method_name not in ('wr', 'assign', 'rd'):
            return
        # Get the port symbol being accessed
        port_sym = self._get_port_sym(ir.func)
        if port_sym is None:
            return
        port_t = port_sym.typ
        if not port_t.is_port():
            return
        if method_name in ('wr', 'assign'):
            # Check thru'd output write
            if port_t.thru:
                fail(self.current_stm, Errors.THRU_OUTPUT_WRITE_FORBIDDEN, [port_sym.orig_name()])
            # Check private submodule port write
            if self._is_private_submodule_port(port_sym):
                fail(self.current_stm, Errors.SUBMODULE_PORT_WRITE_FORBIDDEN, [port_sym.orig_name()])
            # Direction checks only apply in individual (non-flatten) mode.
            # In flatten mode, submodule methods are inlined into the parent,
            # making it impossible to distinguish parent-originated accesses
            # from inlined child code.
            if not env.config.flatten_modules:
                if port_t.direction == 'output' and self._is_submodule_port(ir.func):
                    fail(self.current_stm, Errors.SUBMODULE_OUTPUT_PORT_WRITE, [port_sym.orig_name()])
        elif method_name == 'rd':
            if not env.config.flatten_modules:
                if port_t.direction == 'input' and self._is_submodule_port(ir.func):
                    fail(self.current_stm, Errors.SUBMODULE_INPUT_PORT_READ, [port_sym.orig_name()])

    def _is_submodule_port(self, func_ir):
        """Check if the port access is a direct submodule port access.

        After inlining, this method identifies whether a port method call
        targets a port owned by a direct submodule of the current module.
        Only direct submodule port accesses (exactly one non-protocol module
        in the chain) are subject to direction checks.  Deeper chains
        (module_count >= 2) originate from inlined submodule methods and
        should not be checked here — the intermediate module's own code
        was responsible for the access.
        """
        if not isinstance(func_ir, Attr):
            return False
        exp = func_ir.exp  # the expression before .wr()/.rd()
        qsyms = qualified_symbols(exp, self.scope)
        if not qsyms:
            return False
        # Count non-protocol module instances in the chain (excluding root)
        module_count = 0
        for i, s in enumerate(qsyms):
            if not isinstance(s, Symbol):
                continue
            if i == 0:
                continue  # skip root (self / testbench instance)
            if s.typ.is_object() and s.typ.scope and s.typ.scope.is_module():
                module_count += 1
        # Only flag direct submodule access (exactly 1 non-protocol module).
        # Chains with 2+ modules come from inlined submodule methods — the
        # access was valid in the original context before inlining.
        return module_count == 1

    def _is_private_submodule_port(self, port_sym):
        """Check if port is a private port of a different module."""
        port_name = port_sym.orig_name()
        if not port_name.startswith('_'):
            return False
        port_owner = port_sym.typ.port_owner()
        current_module = self.scope
        while current_module and not current_module.is_module():
            current_module = current_module.parent
        if port_owner is None or current_module is None:
            return False
        return port_owner is not current_module

    def _get_port_sym(self, func_ir):
        """Extract the port symbol from a method call like self.o.wr()."""
        if not isinstance(func_ir, Attr):
            return None
        exp = func_ir.exp
        qsyms = qualified_symbols(exp, self.scope)
        if not qsyms:
            return None
        last = qsyms[-1]
        if isinstance(last, Symbol) and last.typ.is_port():
            return last
        return None


class SynthesisParamChecker(object):
    """Synthesis parameter checker using new IR.

    This pass does not extend IrVisitor because it has custom traversal logic.
    It uses new IR types (ir.py) for isinstance checks on stms.
    """
    def process(self, scope):
        self.scope = scope
        from .usedef import UseDefDetector
        self.usedef = UseDefDetector().process(scope)
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
        syms = self.usedef.get_all_def_syms() | self.usedef.get_all_use_syms()
        for sym in syms:
            if not self._is_channel(sym):
                continue
            from ..irhelper import program_order
            usestms = sorted(self.usedef.get_stms_using(sym), key=lambda s: program_order(s, self.scope))
            loop_bids = [b.bid for b in loop.blocks()]
            usestms = [stm for stm in usestms if stm.block in loop_bids]
            readstms = []
            for stm in usestms:
                if isinstance(stm, Move) and isinstance(stm.src, Call):
                    # Check if the call is a 'get' method
                    call_qsyms = qualified_symbols(stm.src.func, scope)
                    call_sym = call_qsyms[-1]
                    if isinstance(call_sym, Symbol) and call_sym.orig_name() == 'get':
                        readstms.append(stm)
            writestms = []
            for stm in usestms:
                if isinstance(stm, Expr) and isinstance(stm.exp, Call):
                    call_qsyms = qualified_symbols(stm.exp.func, scope)
                    call_sym = call_qsyms[-1]
                    if isinstance(call_sym, Symbol) and call_sym.orig_name() == 'put':
                        writestms.append(stm)
            if len(readstms) > 1:
                sym = env.origin_registry.sym_origin_of(sym) or sym
                fail(readstms[1], Errors.RULE_READING_PIPELINE_IS_CONFLICTED, [sym])
            if len(writestms) > 1:
                sym = env.origin_registry.sym_origin_of(sym) or sym
                fail(writestms[1], Errors.RULE_WRITING_PIPELINE_IS_CONFLICTED, [sym])
            if len(readstms) >= 1 and len(writestms) >= 1:
                assert False

    def _is_channel(self, sym):
        sym_t = sym.typ
        if not sym_t.is_object():
            return False
        scp = sym_t.scope
        origin = env.origin_registry.scope_origin_of(scp)
        return origin is not None and origin.name == 'polyphony.Channel'
