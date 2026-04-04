"""Port conversion passes using new IR (ir.py).

PortTypeProp: Propagates port types from NEW constructor calls.
FlippedTransformer: Handles flipped ports (reverses direction).
PortConnector: Connects ports between modules.
"""
from typing import cast
from .typeprop import TypePropagation, RejectPropagation, _get_callee_scope
from ..irvisitor import IrVisitor
from ..ir import (
    IrVariable, IrNameExp, Temp, Attr, Const, Call, SysCall, New,
    Move, Expr, Ret, Ctx,
)
from ..irhelper import qualified_symbols, irexp_type
from ..block import Block
from ..scope import Scope
from ..symbol import Symbol
from ..types.type import Type
from ..types.typehelper import type_from_ir
from ...common.common import fail
from ...common.env import env
from ...common.errors import Errors
from logging import getLogger
logger = getLogger(__name__)


class PortTypeProp(TypePropagation):
    """Propagate port types from NEW constructor calls.

    Extends TypePropagation to handle Port-specific NEW and CALL patterns.
    """

    def process(self, scope):
        super().process(scope)

    def visit_New(self, ir):  # type: ignore[override]
        callee_scope = _get_callee_scope(ir, self.scope)
        if callee_scope.is_port():
            assert self.scope.is_ctor() and self.scope.parent.is_module()
            attrs = {}
            ctor = callee_scope.find_ctor()
            for (_, a), name in zip(ir.args, ctor.param_names()):
                if isinstance(a, Const):
                    if name == 'direction':
                        di = self._normalize_direction(a.value)
                        if not di:
                            fail(self.current_stm,
                                 Errors.UNKNOWN_X_IS_SPECIFIED,
                                 ['direction', a.value])
                        attrs[name] = di
                    else:
                        attrs[name] = a.value
                elif isinstance(a, Temp) and irexp_type(a, self.scope).is_class():
                    # type_from_ir expects IR
                    attrs[name] = type_from_ir(self.scope, a)
                else:
                    fail(self.current_stm, Errors.PORT_PARAM_MUST_BE_CONST)
            assert 'dtype' in attrs
            assert 'direction' in attrs
            root_sym = qualified_symbols(
                cast(IrNameExp, cast(Move, self.current_stm).dst), self.scope)[-1]
            attrs['root_symbol'] = root_sym
            attrs['assigned'] = False
            if 'init' not in attrs or attrs['init'] is None:
                attrs['init'] = 0
            # Propagate thru tag set by PortConnector before PortTypeProp runs
            if isinstance(root_sym, Symbol) and root_sym.is_thru():
                attrs['thru'] = True

            port_t = Type.port(callee_scope, attrs)
            logger.debug(f'{cast(Move, self.current_stm).dst} {port_t}')
            return port_t
        else:
            return super().visit_New(ir)

    def _normalize_direction(self, di):
        if di == 'in' or di == 'input' or di == 'i':
            return 'input'
        elif di == 'out' or di == 'output' or di == 'o':
            return 'output'
        elif di == 'any' or not di:
            return 'any'
        return ''

    def _raise_stuck_error(self, rejected_scopes):
        """Emit a port-specific error when type propagation is stuck."""
        # Find the first port method call with unresolved receiver
        for scope in rejected_scopes:
            for sym in scope.symbols.values():
                sym_t = sym.typ
                if sym_t.has_scope() and sym_t.scope.is_port() and not sym_t.is_port():
                    info = (env.scope_file_map.get(scope, ''), scope.lineno)
                    fail(info, Errors.PORT_TYPE_UNRESOLVABLE, [sym.orig_name()])
                    return
        # Fallback to generic error
        super()._raise_stuck_error(rejected_scopes)

    def visit_Call(self, ir):
        callee_scope = _get_callee_scope(ir, self.scope)
        if callee_scope.is_method() and callee_scope.parent.is_port():
            qsym = qualified_symbols(ir.func, self.scope)
            receiver = qsym[-2]
            assert isinstance(receiver, Symbol)
            receiver_t = receiver.typ
            if not receiver_t.is_port():
                raise RejectPropagation(ir)
            if callee_scope.base_name == 'assign':
                receiver_t = receiver_t.clone(assigned=True)
                receiver.typ = receiver_t
            root = receiver_t.root_symbol
            port_owner = root.scope
            # If port is a local variable, modify the port owner to its parent
            if port_owner.is_method():
                port_owner = port_owner.parent
            return callee_scope.return_type
        elif callee_scope.is_lib():
            return self._visit_Call_lib(ir)
        else:
            arg_types = [self.visit(arg) for _, arg in ir.args]
            for arg_t, param_sym in zip(arg_types, callee_scope.param_symbols()):
                self._propagate(param_sym, arg_t)
            self._add_scope(callee_scope)
            return callee_scope.return_type

    def _visit_Call_lib(self, ir):
        callee_scope = _get_callee_scope(ir, self.scope)
        if callee_scope.base_name == 'append_worker':
            arg_t = irexp_type(ir.args[0][1], self.scope)
            if not arg_t.is_function():
                assert False
            worker = arg_t.scope
            assert worker.is_worker()

            param_syms = worker.param_symbols()
            arg_types = [self.visit(arg) for _, arg in ir.args[1:len(param_syms) + 1]]
            for arg_t, param_sym in zip(arg_types, param_syms):
                self._propagate(param_sym, arg_t)

            funct = Type.function(worker,
                                  Type.none(),
                                  tuple([p_t for p_t in worker.param_types()]))
            arg_sym = qualified_symbols(ir.args[0][1], self.scope)[-1]
            assert isinstance(arg_sym, Symbol)
            self._propagate(arg_sym, funct)
            self._add_scope(worker)
        return callee_scope.return_type


class FlippedTransformer(TypePropagation):
    """Handle flipped ports by reversing port direction."""

    def process(self, scope):
        from collections import deque
        self.worklist = deque()
        self.typed = []
        super().process(scope)

    def visit_SysCall(self, ir):
        new_args = self._normalize_syscall_args(ir.name, ir.args, ir.kwargs)
        if new_args is not ir.args:
            ir = ir.model_copy(update={'args': new_args})
            self._modified_exp = ir
        for _, arg in ir.args:
            self.visit(arg)
        sym_t = irexp_type(ir, self.scope)
        if ir.name == 'polyphony.io.flipped':
            return self._visit_SysCall_flipped(ir)
        else:
            assert sym_t.is_function()
            return sym_t.return_type

    def _visit_SysCall_flipped(self, ir):
        temp = ir.args[0][1]
        temp_t = irexp_type(temp, self.scope)
        arg_scope = temp_t.scope
        assert arg_scope.is_class()
        if arg_scope.is_port():
            orig_new = self._find_move_src_new(temp.name, New)
            assert isinstance(orig_new, New)
            _, arg = orig_new.args[1]
            assert isinstance(arg, Const)
            direction = 'in' if arg.value == 'out' else 'out'
            args = orig_new.args[0:1] + (('direction', Const(value=direction)),) + orig_new.args[2:]
            cast(Move, self.current_stm).src = New(
                func=orig_new.func.model_copy(deep=True),
                args=args,
                kwargs=orig_new.kwargs,
            )
            return self.visit(cast(Move, self.current_stm).src)
        else:
            flipped_scope = self._new_scope_with_flipped_ports(arg_scope)
            if isinstance(self.current_stm, Move):
                orig_new = self._find_move_src_new(temp.name, New)
                assert isinstance(orig_new, New)
                sym = self.scope.find_sym(flipped_scope.base_name)
                if not sym:
                    # Look up the original NEW's class symbol tags
                    orig_func_sym = qualified_symbols(orig_new.func, self.scope)[-1]
                    assert isinstance(orig_func_sym, Symbol)
                    sym = self.scope.add_sym(flipped_scope.base_name,
                                             orig_func_sym.tags,
                                             Type.klass(flipped_scope))
                self.current_stm.src = New(
                    func=Temp(name=sym.name, ctx=Ctx.LOAD),
                    args=orig_new.args,
                    kwargs=orig_new.kwargs,
                )
                return self.visit(self.current_stm.src)

    def _find_move_src_new(self, name, typ):
        """Find the source expression of a Move in stms that assigns to name with src of given type."""
        for block in self.scope.traverse_blocks():
            stms = block.stms
            for stm in stms:
                if isinstance(stm, Move) and isinstance(stm.src, typ):
                    if isinstance(stm.dst, IrVariable) and stm.dst.name == name:
                        return stm.src
        return None

    def _new_scope_with_flipped_ports(self, scope):
        name = scope.base_name + '_flipped'
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name]
        new_scope = scope.instantiate('flipped', scope.children)
        new_ctor = new_scope.find_ctor()
        FlippedPortsBuilder().process(new_ctor)
        return new_scope


class FlippedPortsBuilder(IrVisitor):
    """Flip direction of port NEW calls in a ctor."""

    def process(self, scope):
        self.scope = scope
        for blk in scope.traverse_blocks():
            for stm in blk.stms[:]:
                if isinstance(stm, Move) and isinstance(stm.src, New):
                    new_src = self._flip_direction(stm.src)
                    if new_src is not None:
                        blk.replace_stm(stm, stm.model_copy(update={'src': new_src}))

    def _flip_direction(self, ir):
        """Flip direction in NEW node. Returns new ir or None if unchanged."""
        func_sym = qualified_symbols(ir.func, self.scope)[-1]
        assert isinstance(func_sym, Symbol)
        sym_t = func_sym.typ
        if sym_t.has_scope() and sym_t.scope.is_port():
            for i, (name, arg) in enumerate(ir.args):
                if name == 'direction':
                    if arg.value == 'in':
                        new_args = list(ir.args)
                        new_args[i] = ('direction', Const(value='out'))
                        return ir.model_copy(update={'args': tuple(new_args)})
                    elif arg.value == 'out':
                        new_args = list(ir.args)
                        new_args[i] = ('direction', Const(value='in'))
                        return ir.model_copy(update={'args': tuple(new_args)})
                    break
        return None


class PortConnector(IrVisitor):
    """Connect ports between modules."""

    def __init__(self):
        self.scopes = []

    def visit_SysCall(self, ir):
        if ir.name in ('polyphony.io.connect', 'polyphony.io.thru'):
            self._visit_SysCall_connect(ir)

    def _ports(self, scope):
        ports = []
        for sym in scope.symbols.values():
            sym_t = sym.typ
            if sym_t.has_scope() and sym_t.scope.is_port():
                ports.append(sym)
        return sorted(ports)

    def _visit_SysCall_connect(self, ir):
        if ir.name.endswith('connect'):
            func = 'connect'
        elif ir.name.endswith('thru'):
            func = 'thru'
        else:
            assert False
        a0 = ir.args[0][1]
        a1 = ir.args[1][1]

        a0_sym = qualified_symbols(a0, self.scope)[-1]
        a1_sym = qualified_symbols(a1, self.scope)[-1]
        assert isinstance(a0_sym, Symbol)
        assert isinstance(a1_sym, Symbol)
        a0_t = a0_sym.typ
        a1_t = a1_sym.typ
        scope0 = a0_t.scope
        scope1 = a1_t.scope
        assert scope0.is_class()
        assert scope1.is_class()
        if scope0.is_port():
            if not scope1.is_port():
                assert False
            self._connect_port(a0_sym, a1_sym, func, a0, a1)
        else:
            if scope1.is_port():
                assert False
            ports0 = self._ports(scope0)
            ports1 = self._ports(scope1)
            for port0, port1 in zip(ports0, ports1):
                # Create Attr nodes for port access (new IR)
                p0 = Attr(name=port0.name, exp=a0, attr=port0, ctx=Ctx.LOAD)
                p1 = Attr(name=port1.name, exp=a1, attr=port1, ctx=Ctx.LOAD)
                self._connect_port(p0, p1, func)

    def _find_move_src_for_port(self, sym):
        """Find NEW source for a port symbol."""
        scope = sym.scope
        if scope.is_class():
            scope = scope.find_ctor()
        for block in scope.traverse_blocks():
            for stm in block.stms:
                if isinstance(stm, Move) and isinstance(stm.src, New):
                    if isinstance(stm.dst, IrVariable) and stm.dst.name == sym.name:
                        return stm.src
        return None

    def _connect_port(self, p0_sym, p1_sym, func, p0_exp=None, p1_exp=None):
        """Connect two ports with the given function ('connect' or 'thru').

        p0_exp and p1_exp are the original IR expressions for the ports (used when
        p0_sym/p1_sym are bare Symbols that lack scope context for the lambda body).
        """
        if isinstance(p0_sym, Symbol):
            p0_resolved = p0_sym
            # Use original expression if available, otherwise wrap symbol as Attr
            p0_ir = p0_exp if p0_exp is not None else Temp(p0_sym.name)
        else:
            p0_resolved = qualified_symbols(p0_sym, self.scope)[-1]
            p0_ir = p0_sym  # Attr node already has correct exp chain
        if isinstance(p1_sym, Symbol):
            p1_resolved = p1_sym
            p1_ir = p1_exp if p1_exp is not None else Temp(p1_sym.name)
        else:
            p1_resolved = qualified_symbols(p1_sym, self.scope)[-1]
            p1_ir = p1_sym  # Attr node already has correct exp chain
        assert isinstance(p0_resolved, Symbol)
        assert isinstance(p1_resolved, Symbol)
        p0_t = p0_resolved.typ
        p1_t = p1_resolved.typ
        port_scope0 = p0_t.scope
        port_scope1 = p1_t.scope
        dtype_sym0 = port_scope0.find_ctor().param_symbols()[0]
        dtype_sym1 = port_scope1.find_ctor().param_symbols()[0]
        dtype0 = dtype_sym0.typ
        dtype1 = dtype_sym1.typ
        if not dtype0.is_same(dtype1):
            assert False
        new0 = self._find_move_src_for_port(p0_resolved)
        new1 = self._find_move_src_for_port(p1_resolved)
        assert isinstance(new0, New) and isinstance(new1, New)
        dir0 = new0.args[1][1]
        dir1 = new1.args[1][1]
        # Check if either port is already thru-connected (write-protected)
        if p0_resolved.is_thru() and dir0.value == 'out':
            fail(self.current_stm, Errors.THRU_OUTPUT_WRITE_FORBIDDEN, [p0_resolved.orig_name()])
        if p1_resolved.is_thru() and dir1.value == 'out':
            fail(self.current_stm, Errors.THRU_OUTPUT_WRITE_FORBIDDEN, [p1_resolved.orig_name()])
        port_assign_call = None
        if func == 'connect':
            if dir0.value == 'in' and dir1.value == 'out':
                port_assign_call = self._make_assign_call(p0_resolved, p1_resolved, p0_ir, p1_ir)
            elif dir0.value == 'out' and dir1.value == 'in':
                port_assign_call = self._make_assign_call(p1_resolved, p0_resolved, p1_ir, p0_ir)
            else:
                fail(self.current_stm, Errors.CONNECT_DIRECTION_MISMATCH, [dir0.value, dir1.value])
        elif func == 'thru':
            if dir0.value == 'in' and dir1.value == 'in':
                port_assign_call = self._make_assign_call(p1_resolved, p0_resolved, p1_ir, p0_ir)
            elif dir0.value == 'out' and dir1.value == 'out':
                port_assign_call = self._make_assign_call(p0_resolved, p1_resolved, p0_ir, p1_ir)
                # Mark parent output port as thru-connected (read-only from parent side)
                self._mark_thru(p0_sym)
            else:
                fail(self.current_stm, Errors.THRU_DIRECTION_MISMATCH, [dir0.value, dir1.value])
        # Append to block
        self.scope.find_block(self.current_stm.block).append_stm(
            Expr(port_assign_call)
        )

    def _make_assign_call(self, p0_sym, p1_sym, p0_ir, p1_ir):
        """Create a port assign call: p0.assign(lambda: p1.rd()).

        p0_sym, p1_sym: resolved Symbol objects for type/scope lookup.
        p0_ir, p1_ir: IR expressions for the ports (Attr chains or Temp).
        """
        p0_t = p0_sym.typ
        p1_t = p1_sym.typ
        port_scope0 = p0_t.scope
        port_scope1 = p1_t.scope
        rd_sym = port_scope1.find_sym('rd')
        port_rd = Attr(p1_ir, rd_sym.name)
        port_rd_call = Call(func=port_rd, args=(), kwargs={})
        lambda_sym = self._make_lambda(port_rd_call)
        assign_sym = port_scope0.find_sym('assign')
        port_assign = Attr(p0_ir, assign_sym.name)
        port_assign_call = Call(func=port_assign,
                                    args=(('fn', Temp(lambda_sym.name)),), kwargs={})
        return port_assign_call

    def _make_lambda(self, body):
        """Create a lambda scope for port assignment."""
        tags = {'function', 'returnable', 'comb'}
        lambda_scope = Scope.create(self.scope, None, tags, self.scope.lineno)
        lambda_scope.synth_params = self.scope.synth_params.copy()
        new_block = Block(lambda_scope)
        lambda_scope.set_entry_block(new_block)
        lambda_scope.set_exit_block(new_block)
        lambda_scope.return_type = Type.undef()  # type: ignore[attr-defined]
        ret_sym = lambda_scope.add_return_sym()
        new_block.append_stm(Move(Temp(ret_sym.name), body))
        new_block.append_stm(Ret(Temp(ret_sym.name)))
        scope_sym = self.scope.add_sym(lambda_scope.base_name, tags=set(), typ=Type.function(lambda_scope))

        self.scopes.append(lambda_scope)

        temps = body.find_irs(Temp)
        for t in temps:
            sym = self.scope.find_sym(t.name)
            if sym and sym not in self.scope.symbols.values():
                lambda_scope.add_free_sym(sym)
        self.scope.add_tag('enclosure')
        return scope_sym

    def _mark_thru(self, port_sym):
        """Mark a port symbol as thru-connected.

        PortTypeProp has not yet run when PortConnector executes, so the symbol
        still carries ObjectType rather than PortType. We tag the symbol so that
        PortTypeProp can later propagate the thru flag into the PortType attrs.
        """
        if isinstance(port_sym, Symbol):
            sym = port_sym
        else:
            # port_sym is an Attr node from object-level thru
            sym = qualified_symbols(port_sym, self.scope)[-1]
        if isinstance(sym, Symbol):
            if sym.typ.is_port():
                # PortType already available — update it directly
                sym.typ = sym.typ.clone(thru=True)
            else:
                # ObjectType: tag the symbol so PortTypeProp picks it up later
                sym.add_tag('thru')
