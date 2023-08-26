from collections import defaultdict
from collections import deque
from .typeprop import TypePropagation, RejectPropagation
from ..block import Block
from ..scope import Scope
from ..ir import Ctx, CONST, TEMP, ATTR, CALL, NEW, RET, MOVE, EXPR
from ..irhelper import find_move_src
from ..irvisitor import IRVisitor, IRTransformer
from ..types.type import Type
from ...common.common import fail, warn
from ...common.env import env
from ...common.errors import Errors, Warnings
from logging import getLogger
logger = getLogger(__name__)

# port
#  dtype
#  direction ... in | out
#  init      ... initial value
#  assigned    ... True | False
#  root_symbol ... symbol
#
class PortTypeProp(TypePropagation):
    def process(self, scope):
        super().process(scope)

    def visit_NEW(self, ir):
        assert self.current_stm.is_a(MOVE)
        callee_scope = ir.callee_scope
        if callee_scope.is_port():
            assert self.scope.is_ctor() and self.scope.parent.is_module()
            attrs = {}
            ctor = callee_scope.find_ctor()
            for (_, a), name in zip(ir.args, ctor.param_names()):
                if a.is_a(CONST):
                    if name == 'direction':
                        di = self._normalize_direction(a.value)
                        if not di:
                            fail(self.current_stm,
                                 Errors.UNKNOWN_X_IS_SPECIFIED,
                                 ['direction', a.value])
                        attrs[name] = di
                    else:
                        attrs[name] = a.value
                elif a.is_a(TEMP) and a.symbol.typ.is_class():
                    attrs[name] = Type.from_ir(a)
                else:
                    fail(self.current_stm, Errors.PORT_PARAM_MUST_BE_CONST)
            assert 'dtype' in attrs
            assert 'direction' in attrs
            attrs['root_symbol'] = self.current_stm.dst.symbol
            attrs['assigned'] = False
            if 'init' not in attrs or attrs['init'] is None:
                attrs['init'] = 0

            port_t = Type.port(callee_scope, attrs)
            logger.debug(f'{self.current_stm.dst} {port_t}')
            return port_t
        else:
            return super().visit_NEW(ir)

    def _normalize_direction(self, di):
        if di == 'in' or di == 'input' or di == 'i':
            return 'input'
        elif di == 'out' or di == 'output' or di == 'o':
            return 'output'
        elif di == 'any' or not di:
            return 'any'
        return ''

    def visit_CALL(self, ir):
        callee_scope = ir.callee_scope
        if callee_scope.is_method() and callee_scope.parent.is_port():
            receiver = ir.func.tail()
            receiver_t = receiver.typ
            if not receiver_t.is_port():
                raise RejectPropagation(ir)
            if callee_scope.base_name == 'assign':
                receiver_t = receiver_t.clone(assigned=True)
                receiver.typ = receiver_t
            root = receiver_t.root_symbol
            port_owner = root.scope
            # if port is a local variable, we modify the port owner its parent
            if port_owner.is_method():
                port_owner = port_owner.parent
            return callee_scope.return_type
        elif callee_scope.is_lib():
            return self.visit_CALL_lib(ir)
        else:
            arg_types = [self.visit(arg) for _, arg in ir.args]
            for arg_t, param_sym in zip(arg_types, callee_scope.param_symbols()):
                self._propagate(param_sym, arg_t)
            self._add_scope(callee_scope)
            return callee_scope.return_type

    def visit_CALL_lib(self, ir):
        callee_scope = ir.callee_scope
        if callee_scope.base_name == 'append_worker':
            arg_t = ir.args[0][1].symbol.typ
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
            self._propagate(ir.args[0][1].symbol, funct)
            self._add_scope(worker)
        return callee_scope.return_type


def _collect_scopes(module):
    scopes = []
    ctor = module.find_ctor()
    assert ctor
    scopes.append(ctor)
    scopes.extend(ctor.children)
    for w, args in module.workers:
        scopes.append(w)
        scopes.extend(w.children)
    for caller in env.depend_graph.preds(module):
        if caller.is_namespace():
            continue
        if caller not in scopes:
            scopes.append(caller)
    return scopes


class FlippedTransformer(TypePropagation):
    def process(self, scope):
        self.worklist = []
        self.typed = []
        super().process(scope)

    def visit_SYSCALL(self, ir):
        ir.args = self._normalize_syscall_args(ir.symbol.name, ir.args, ir.kwargs)
        for _, arg in ir.args:
            self.visit(arg)
        sym_t = ir.symbol.typ
        if ir.symbol.name == 'polyphony.io.flipped':
            return self.visit_SYSCALL_flipped(ir)
        else:
            assert sym_t.is_function()
            return sym_t.return_type

    def visit_SYSCALL_flipped(self, ir):
        temp = ir.args[0][1]
        temp_t = temp.symbol.typ
        arg_scope = temp_t.scope
        assert arg_scope.is_class()
        if arg_scope.is_port():
            orig_new = find_move_src(temp.symbol, NEW)
            _, arg = orig_new.args[1]
            direction = 'in' if arg.value == 'out' else 'out'
            args = orig_new.args[0:1] + [('direction', CONST(direction))] + orig_new.args[2:]
            self.current_stm.src = NEW(orig_new.symbol, args, orig_new.kwargs)
            return self.visit(self.current_stm.src)
        else:
            flipped_scope = self._new_scope_with_flipped_ports(arg_scope)
            if self.current_stm.is_a(MOVE):
                orig_new = find_move_src(temp.symbol, NEW)
                sym = self.scope.find_sym(flipped_scope.base_name)
                if not sym:
                    sym = self.scope.add_sym(flipped_scope.base_name,
                                             orig_new.symbol.tags,
                                             Type.klass(flipped_scope))
                self.current_stm.src = NEW(sym, orig_new.args, orig_new.kwargs)
                return self.visit(self.current_stm.src)

    def _new_scope_with_flipped_ports(self, scope):
        name = scope.base_name + '_flipped'
        qualified_name = (scope.parent.name + '.' + name) if scope.parent else name
        if qualified_name in env.scopes:
            return env.scopes[qualified_name]
        new_scope = scope.instantiate('flipped', scope.children)
        new_ctor = new_scope.find_ctor()
        FlippedPortsBuilder().process(new_ctor)
        return new_scope


class FlippedPortsBuilder(IRVisitor):
    def visit_NEW(self, ir):
        sym_t = ir.symbol.typ
        if sym_t.scope.is_port():
            for name, arg in ir.args:
                if name == 'direction':
                    if arg.value == 'in':
                        arg.value = 'out'
                    elif arg.value == 'out':
                        arg.value = 'in'
                    break


class PortConnector(IRVisitor):
    def __init__(self):
        self.scopes = []

    def visit_SYSCALL(self, ir):
        if ir.symbol.name in ('polyphony.io.connect', 'polyphony.io.thru'):
            self.visit_SYSCALL_connect(ir)

    def _ports(self, scope):
        ports = []
        for sym in scope.symbols.values():
            sym_t = sym.typ
            if sym_t.has_valid_scope() and sym_t.scope.is_port():
                ports.append(sym)
        return sorted(ports)

    def visit_SYSCALL_connect(self, ir):
        if ir.symbol.name.endswith('connect'):
            func = 'connect'
        elif ir.symbol.name.endswith('thru'):
            func = 'thru'
        else:
            assert False
        a0 = ir.args[0][1]
        a1 = ir.args[1][1]
        a0_t = a0.symbol.typ
        a1_t = a1.symbol.typ
        scope0 = a0_t.scope
        scope1 = a1_t.scope
        assert scope0.is_class()
        assert scope1.is_class()
        if scope0.is_port():
            if not scope1.is_port():
                assert False
            self._connect_port(a0, a1, func)
        else:
            if scope1.is_port():
                assert False
            ports0 = self._ports(scope0)
            ports1 = self._ports(scope1)
            for port0, port1 in zip(ports0, ports1):
                p0 = ATTR(a0, port0, Ctx.LOAD, a0.symbol.scope)
                p1 = ATTR(a1, port1, Ctx.LOAD, a1.symbol.scope)
                self._connect_port(p0, p1, func)

    def _connect_port(self, p0, p1, func):
        p0_t = p0.symbol.typ
        p1_t = p1.symbol.typ
        port_scope0 = p0_t.scope
        port_scope1 = p1_t.scope
        init_param0 = port_scope0.find_ctor().params[3]
        init_param1 = port_scope1.find_ctor().params[3]
        dtype0 = init_param0.sym.typ
        dtype1 = init_param1.sym.typ
        if not dtype0.is_same(dtype1):
            assert False
        new0 = find_move_src(p0.symbol, NEW)
        new1 = find_move_src(p1.symbol, NEW)
        dir0 = new0.args[1][1]
        dir1 = new1.args[1][1]
        if func == 'connect':
            if dir0.value == 'in' and dir1.value == 'out':
                port_assign_call = self._make_assign_call(p0, p1)
            elif dir0.value == 'out' and dir1.value == 'in':
                port_assign_call = self._make_assign_call(p1, p0)
            else:
                assert False
        elif func == 'thru':
            if dir0.value == 'in' and dir1.value == 'in':
                port_assign_call = self._make_assign_call(p1, p0)
            elif dir0.value == 'out' and dir1.value == 'out':
                port_assign_call = self._make_assign_call(p0, p1)
            else:
                assert False
        self.current_stm.block.append_stm(EXPR(port_assign_call))

    def _make_assign_call(self, p0, p1):
        p0_t = p0.symbol.typ
        p1_t = p1.symbol.typ
        port_scope0 = p0_t.scope
        port_scope1 = p1_t.scope
        rd_sym = port_scope1.find_sym('rd')
        port_rd = ATTR(p1,
                       rd_sym,
                       Ctx.LOAD,
                       port_scope1)
        port_rd_call = CALL(port_rd, args=[], kwargs={})
        lambda_sym = self._make_lambda(port_rd_call)
        assign_sym = port_scope0.find_sym('assign')
        port_assign = ATTR(p0,
                           assign_sym,
                           Ctx.LOAD,
                           port_scope0)
        port_assign_call = CALL(port_assign,
                                args=[('fn', TEMP(lambda_sym, Ctx.LOAD))], kwargs={})
        return port_assign_call

    def _make_lambda(self, body):
        tags = {'function', 'returnable', 'comb'}
        lambda_scope = Scope.create(self.scope, None, tags, self.scope.lineno)
        lambda_scope.synth_params = self.scope.synth_params.copy()
        new_block = Block(lambda_scope)
        lambda_scope.set_entry_block(new_block)
        lambda_scope.set_exit_block(new_block)
        lambda_scope.return_type = Type.undef()
        ret_sym = lambda_scope.add_return_sym()
        new_block.append_stm(MOVE(TEMP(ret_sym, Ctx.STORE), body))
        new_block.append_stm(RET(TEMP(ret_sym, Ctx.LOAD)))
        scope_sym = self.scope.add_sym(lambda_scope.base_name, typ=Type.function(lambda_scope))

        self.scopes.append(lambda_scope)

        temps = body.find_irs(TEMP)
        for t in temps:
            if t.symbol not in self.scope.symbols:
                lambda_scope.add_free_sym(t.symbol)
        self.scope.add_tag('enclosure')
        self.scope.add_closure(lambda_scope)
        return scope_sym


class UnusedPortCleaner(IRTransformer):
    def __init__(self):
        self.port_syms = set()

    def process_all(self):
        scopes = Scope.get_scopes(with_class=True)
        modules = [s for s in scopes if s.is_module()]
        if not modules:
            return
        #typeprop = PortTypeProp()
        for m in modules:
            if not m.is_instantiated():
                continue
            scopes_ = _collect_scopes(m)
            for s in scopes_:
                self.process(s)

    def visit_TEMP(self, ir):
        if ir.ctx is Ctx.STORE:
            sym_t = ir.symbol.typ
            if sym_t.has_valid_scope() and sym_t.scope.is_port():
                assert self.current_stm.is_a(MOVE)
                self.port_syms.add(self.current_stm.dst.symbol)
        return ir

    def visit_NEW(self, ir):
        callee_scope = ir.callee_scope
        if callee_scope.is_port():
            assert self.current_stm.is_a(MOVE)
            self.port_syms.add(self.current_stm.dst.symbol)
        return ir

    def visit_CALL(self, ir):
        callee_scope = ir.callee_scope
        if callee_scope.is_method() and callee_scope.parent.is_port():
            sym = ir.func.tail()
            if sym not in self.port_syms:
                return None
        return ir

    def visit_MOVE(self, ir):
        src = self.visit(ir.src)
        if src is not None:
            self.new_stms.append(ir)
        self.visit(ir.dst)

    def visit_EXPR(self, ir):
        exp = self.visit(ir.exp)
        if exp is not None:
            self.new_stms.append(ir)
