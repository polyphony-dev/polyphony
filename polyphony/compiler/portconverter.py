from collections import defaultdict
from .block import Block
from .common import fail, warn
from .env import env
from .errors import Errors, Warnings
from .scope import Scope
from .ir import Ctx, CONST, TEMP, ATTR, CALL, NEW, RET, MOVE, EXPR
from .irhelper import find_move_src
from .irvisitor import IRVisitor, IRTransformer
from .type import Type
from .typecheck import TypePropagation, RejectPropagation


class PortTypeProp(TypePropagation):
    def visit_NEW(self, ir):
        if ir.func_scope().is_port():
            assert self.scope.is_ctor() and self.scope.parent.is_module()
            attrs = {}
            ctor = ir.func_scope().find_ctor()
            for (_, a), p in zip(ir.args, ctor.params[1:]):
                if a.is_a(CONST):
                    if p.copy.name == 'direction':
                        di = self._normalize_direction(a.value)
                        if not di:
                            fail(self.current_stm,
                                 Errors.UNKNOWN_X_IS_SPECIFIED,
                                 ['direction', a.value])
                        attrs[p.copy.name] = di
                    else:
                        attrs[p.copy.name] = a.value
                elif a.is_a(TEMP) and a.symbol().typ.is_class():
                    attrs[p.copy.name] = a.symbol().typ.name
                else:
                    fail(self.current_stm, Errors.PORT_PARAM_MUST_BE_CONST)
            init_param = ctor.params[3]
            assert 'direction' in attrs
            attrs['dtype'] = init_param.sym.typ
            attrs['root_symbol'] = self.current_stm.dst.symbol()
            attrs['assigned'] = False
            if self.current_stm.is_a(MOVE) and self.current_stm.dst.is_a(TEMP):
                attrs['port_kind'] = 'internal'
            else:
                if self.current_stm.dst.symbol().name.startswith('_'):
                    attrs['port_kind'] = 'internal'
                    attrs['direction'] = 'inout'
                else:
                    attrs['port_kind'] = 'external'
            if 'init' not in attrs or attrs['init'] is None:
                attrs['init'] = 0
            return Type.port(ir.func_scope(), attrs)
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
        if ir.func_scope().is_method() and ir.func_scope().parent.is_port():
            sym = ir.func.tail()
            if not sym.typ.is_port():
                raise RejectPropagation(ir)
            if ir.func.symbol().typ.get_scope().base_name == 'assign':
                sym.typ = sym.typ.with_assigned(True)
            kind = sym.typ.get_port_kind()
            root = sym.typ.get_root_symbol()
            port_owner = root.scope
            # if port is a local variable, we modify the port owner its parent
            if port_owner.is_method():
                port_owner = port_owner.parent
            if self.scope.is_worker():
                scope = self.scope.worker_owner
            elif self.scope.is_method():
                scope = self.scope.parent
            else:
                scope = self.scope
            if (kind == 'internal'
                    and not scope.is_subclassof(port_owner)
                    and not port_owner.find_child(scope.name, rec=True)):
                fail(self.current_stm, Errors.PORT_ACCESS_IS_NOT_ALLOWED)
            return ir.func_scope().return_type
        elif ir.func_scope().is_lib():
            return self.visit_CALL_lib(ir)
        else:
            if ir.func_scope().is_method():
                params = ir.func_scope().params[1:]
            else:
                params = ir.func_scope().params[:]
            arg_types = [self.visit(arg) for _, arg in ir.args]
            for i, param in enumerate(params):
                self._propagate(param.sym, arg_types[i])
            self._add_scope(ir.func_scope())
            return ir.func_scope().return_type

    def visit_CALL_lib(self, ir):
        if ir.func_scope().base_name == 'append_worker':
            if not ir.args[0][1].symbol().typ.is_function():
                assert False
            worker = ir.args[0][1].symbol().typ.get_scope()
            assert worker.is_worker()

            if worker.is_method():
                params = worker.params[1:]
            else:
                params = worker.params[:]
            arg_types = [self.visit(arg) for _, arg in ir.args[1:len(params) + 1]]
            for i, param in enumerate(params):
                # we should not set the same type here.
                # because the type of 'sym' and 'copy' might be have different objects(e.g. memnode)
                self._propagate(param.sym, arg_types[i].clone())
                #self._propagate_param(worker, param.copy, arg_types[i].clone())

            funct = Type.function(worker,
                                  Type.none(),
                                  tuple([param.sym.typ for param in worker.params]))
            self._propagate(ir.args[0][1].symbol(), funct)
            self._add_scope(worker)
        return ir.func_scope().return_type


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


class PortConverter(IRTransformer):
    def __init__(self):
        super().__init__()
        self.writers = defaultdict(set)

    def process_all(self):
        UnusedPortCleaner().process_all()

        scopes = Scope.get_scopes(with_class=True)
        modules = [s for s in scopes if s.is_module()]
        if not modules:
            return
        PortTypeProp().process_all()
        for m in modules:
            if not m.is_instantiated():
                continue
            scopes_ = _collect_scopes(m)
            self.union_ports = defaultdict(set)
            for s in scopes_:
                self.process(s)

            ctor = m.find_ctor()
            # check for instance variable port
            for field in m.class_fields().values():
                if field.typ.is_port() and field not in self.writers:
                    if not env.depend_graph.preds(m):
                        continue
                    assert ctor.usedef
                    stm = ctor.usedef.get_stms_defining(field).pop()
                    warn(stm, Warnings.PORT_IS_NOT_USED,
                         [field.orig_name()])
            # check for local variable port
            for sym in ctor.symbols.values():
                if sym.typ.is_port() and sym not in self.writers:
                    assert ctor.usedef
                    stms = ctor.usedef.get_stms_defining(sym)
                    # This symbol might not be used (e.g. ancestor symbol),
                    # so we have to check if its definition statement exists.
                    if stms:
                        warn(list(stms)[0], Warnings.PORT_IS_NOT_USED,
                             [sym.orig_name()])

    def _get_port_owner(self, sym):
        assert sym.typ.is_port()
        root = sym.typ.get_root_symbol()
        if root.scope.is_ctor():
            return root.scope.parent
        else:
            return root.scope

    def _is_access_from_external(self, sym):
        port_owner = self._get_port_owner(sym)
        for w, _ in port_owner.workers:
            if self.scope is w:
                return False
        if port_owner.find_child(self.scope.name, rec=True):
            return False
        for subclass in port_owner.subs:
            for w, _ in subclass.workers:
                if self.scope is w:
                    return False
            if subclass.find_child(self.scope.name, rec=True):
                return False
        return True

    def _check_port_direction(self, sym, func_scope):
        assert func_scope.name.startswith('polyphony.io.Port')
        port_typ = sym.typ
        di = port_typ.get_direction()
        kind = port_typ.get_port_kind()
        from_external = self._is_access_from_external(sym)
        exclusive_write = False
        if from_external:
            assert kind == 'external'
            if func_scope.base_name in ('wr', 'assign'):
                valid_direction = {'input'}
                exclusive_write = True
            else:
                valid_direction = {'output'}
        else:
            if kind == 'external':
                if func_scope.base_name in ('wr', 'assign'):
                    valid_direction = {'output'}
                    exclusive_write = True
                else:
                    valid_direction = {'input', 'output'}
            else:
                if func_scope.base_name in ('wr', 'assign'):
                    exclusive_write = True
                valid_direction = {'output', 'input'}
        if di != 'inout' and di != 'any' and di not in valid_direction:
            fail(self.current_stm, Errors.DIRECTION_IS_CONFLICTED,
                 [sym.orig_name()])
        if not exclusive_write:
            return
        if sym in self.union_ports:
            assert False
            for s in self.union_ports[sym]:
                self._set_and_check_port_direction(s)
        else:
            self._set_and_check_port_direction(sym)

    def _set_and_check_port_direction(self, sym):
        port_typ = sym.typ
        rootsym = port_typ.get_root_symbol()
        kind = port_typ.get_port_kind()
        # write-write conflict
        if self.writers[rootsym]:
            assert len(self.writers[rootsym]) == 1
            writer = list(self.writers[rootsym])[0]
            if writer is not self.scope and writer.worker_owner and writer.worker_owner is self.scope.worker_owner:
                fail(self.current_stm, Errors.WRITING_IS_CONFLICTED,
                        [sym.orig_name()])
        else:
            if kind == 'internal':
                assert self.scope.is_worker() or self.scope.parent.is_module()
            self.writers[rootsym].add(self.scope)

    def visit_CALL(self, ir):
        if not ir.func_scope().is_lib():
            return ir
        if ir.func_scope().is_method() and ir.func_scope().parent.is_port():
            sym = ir.func.tail()
            assert sym.typ.is_port()
            self._check_port_direction(sym, ir.func_scope())
            if (self.current_stm.block.synth_params['scheduling'] == 'pipeline' and
                    self.scope.find_region(self.current_stm.block) is not self.scope.top_region()):
                root_sym = sym.typ.get_root_symbol()
                root_sym.add_tag('pipelined')
        return ir

    def visit_SYSCALL(self, ir):
        if ir.sym.name.startswith('polyphony.timing.wait_'):
            if ir.sym.name == 'polyphony.timing.wait_until':
                return ir
            elif (ir.sym.name == 'polyphony.timing.wait_rising' or
                    ir.sym.name == 'polyphony.timing.wait_falling'):
                ports = ir.args
            elif ir.sym.name == 'polyphony.timing.wait_edge':
                ports = ir.args[2:]
            elif ir.sym.name == 'polyphony.timing.wait_value':
                ports = ir.args[1:]
            for _, p in ports:
                port = p.symbol().typ
                assert port.is_port()
                di = port.get_direction()
                kind = port.get_port_kind()
                if kind == 'external':
                    port_owner = self._get_port_owner(p.symbol())
                    #port.set_direction('input')
                    if ((self.scope.is_worker() and not self.scope.worker_owner.is_subclassof(port_owner)) or
                            not self.scope.is_worker()):
                        if di == 'input':
                            fail(self.current_stm, Errors.CANNOT_WAIT_INPUT)
                    else:
                        if di == 'output':
                            fail(self.current_stm, Errors.CANNOT_WAIT_OUTPUT)
        return ir

    def visit_PHI(self, ir):
        if ir.var.symbol().typ.is_port():
            for arg in ir.args:
                self.union_ports[ir.var.symbol()].add(arg.symbol())
        super().visit_PHI(ir)


class FlattenPortList(IRTransformer):
    def visit_MREF(self, ir):
        memsym = ir.mem.symbol()
        memtyp = memsym.typ
        assert memtyp.is_seq()
        elm_t = memtyp.get_element()
        if not elm_t.is_object():
            return ir
        if not elm_t.get_scope().is_port():
            return ir
        if not ir.offset.is_a(CONST):
            return ir
        portname = '{}_{}'.format(memsym.name, ir.offset.value)
        scope = ir.mem.symbol().scope
        portsym = scope.find_sym(portname)
        assert portsym
        ir.mem.set_symbol(portsym)
        return ir.mem


class FlippedTransformer(TypePropagation):
    def process(self, scope):
        self.worklist = []
        self.typed = []
        super().process(scope)

    def visit_SYSCALL(self, ir):
        ir.args = self._normalize_syscall_args(ir.sym.name, ir.args, ir.kwargs)
        for _, arg in ir.args:
            self.visit(arg)
        if ir.sym.name == 'polyphony.io.flipped':
            return self.visit_SYSCALL_flipped(ir)
        else:
            assert ir.sym.typ.is_function()
            return ir.sym.typ.get_return_type()

    def visit_SYSCALL_flipped(self, ir):
        temp = ir.args[0][1]
        arg_scope = temp.symbol().typ.get_scope()
        assert arg_scope.is_class()
        if arg_scope.is_port():
            orig_new = find_move_src(temp.symbol(), NEW)
            _, arg = orig_new.args[1]
            direction = 'in' if arg.value == 'out' else 'out'
            args = orig_new.args[0:1] + [('direction', CONST(direction))] + orig_new.args[2:]
            self.current_stm.src = NEW(orig_new.sym, args, orig_new.kwargs)
            return self.visit(self.current_stm.src)
        else:
            flipped_scope = self._new_scope_with_flipped_ports(arg_scope)
            if self.current_stm.is_a(MOVE):
                orig_new = find_move_src(temp.symbol(), NEW)
                sym = self.scope.find_sym(flipped_scope.base_name)
                if not sym:
                    sym = self.scope.add_sym(flipped_scope.base_name,
                                             orig_new.sym.tags,
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
        if ir.sym.typ.get_scope().is_port():
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
        if ir.sym.name in ('polyphony.io.connect', 'polyphony.io.thru'):
            self.visit_SYSCALL_connect(ir)

    def _ports(self, scope):
        ports = []
        for sym in scope.symbols.values():
            if sym.typ.has_scope() and sym.typ.get_scope().is_port():
                ports.append(sym)
        return sorted(ports)

    def visit_SYSCALL_connect(self, ir):
        if ir.sym.name.endswith('connect'):
            func = 'connect'
        elif ir.sym.name.endswith('thru'):
            func = 'thru'
        else:
            assert False
        a0 = ir.args[0][1]
        a1 = ir.args[1][1]
        scope0 = a0.symbol().typ.get_scope()
        scope1 = a1.symbol().typ.get_scope()
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
                p0 = ATTR(a0, port0, Ctx.LOAD, a0.symbol().scope)
                p1 = ATTR(a1, port1, Ctx.LOAD, a1.symbol().scope)
                self._connect_port(p0, p1, func)

    def _connect_port(self, p0, p1, func):
        port_scope0 = p0.symbol().typ.get_scope()
        port_scope1 = p1.symbol().typ.get_scope()
        init_param0 = port_scope0.find_ctor().params[3]
        init_param1 = port_scope1.find_ctor().params[3]

        dtype0 = init_param0.sym.typ  # port_scope0.type_args[0]
        dtype1 = init_param1.sym.typ  # port_scope1.type_args[0]
        if not Type.is_same(dtype0, dtype1):
            assert False
        new0 = find_move_src(p0.symbol(), NEW)
        new1 = find_move_src(p1.symbol(), NEW)
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
        port_scope0 = p0.symbol().typ.get_scope()
        port_scope1 = p1.symbol().typ.get_scope()
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
            if t.symbol() not in self.scope.symbols:
                lambda_scope.add_free_sym(t.symbol())
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
            if ir.symbol().typ.has_scope() and ir.symbol().typ.get_scope().is_port():
                assert self.current_stm.is_a(MOVE)
                self.port_syms.add(self.current_stm.dst.symbol())
        return ir

    def visit_NEW(self, ir):
        if ir.func_scope().is_port():
            assert self.current_stm.is_a(MOVE)
            self.port_syms.add(self.current_stm.dst.symbol())
        return ir

    def visit_CALL(self, ir):
        if ir.func_scope().is_method() and ir.func_scope().parent.is_port():
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
