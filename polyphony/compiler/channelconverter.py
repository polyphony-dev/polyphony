from collections import defaultdict
from .common import fail, warn
from .env import env
from .errors import Errors, Warnings
from .scope import Scope
from .ir import CONST, TEMP, ATTR
from .irvisitor import IRVisitor, IRTransformer
from .type import Type
from .typecheck import TypePropagation


class ChannelTypeProp(TypePropagation):
    def visit_NEW(self, ir):
        if ir.func_scope().is_channel():
            assert self.scope.is_ctor() and self.scope.parent.is_module()
            attrs = {}
            ctor = ir.func_scope().find_ctor()
            for (_, a), p in zip(ir.args, ctor.params[1:]):
                if a.is_a(CONST):
                    attrs[p.copy.name] = a.value
                elif a.is_a(TEMP) and a.symbol().typ.is_class():
                    attrs[p.copy.name] = a.symbol().typ.name
                else:
                    fail(self.current_stm, Errors.PORT_PARAM_MUST_BE_CONST)
            assert len(ir.func_scope().type_args) == 1
            attrs['dtype'] = ir.func_scope().type_args[0]
            attrs['root_symbol'] = self.current_stm.dst.symbol()
            return Type.channel(ir.func_scope(), attrs)
        return None

    def visit_MOVE(self, ir):
        # Do not overwrite other than the type of Channel's ctor
        src_typ = self.visit(ir.src)
        if src_typ and ir.dst.is_a([TEMP, ATTR]):
            self._set_type(ir.dst.symbol(), src_typ.clone())


class ChannelConverter(IRTransformer):
    def __init__(self):
        super().__init__()
        self.writers = defaultdict(set)
        self.readers = defaultdict(set)

    def process_all(self):
        scopes = Scope.get_scopes(with_class=True)
        modules = [s for s in scopes if s.is_module()]
        if not modules:
            return
        #cleaner = UnusedPortCleaner()
        typeprop = ChannelTypeProp()
        for m in modules:
            if not m.is_instantiated():
                continue
            ctor = m.find_ctor()
            assert ctor
            #cleaner.process(ctor)
            typeprop.process(ctor)
            for w, args in m.workers:
                #cleaner.process(w)
                typeprop.process(w)
            for caller in env.depend_graph.preds(m):
                if caller.is_namespace():
                    continue
                #cleaner.process(caller)
                typeprop.process(caller)

            self.process(ctor)
            for w, args in m.workers:
                self.process(w)
            for caller in env.depend_graph.preds(m):
                if caller.is_namespace():
                    continue
                self.process(caller)

            # check for instance variable port
            for field in m.class_fields().values():
                if field.typ.is_channel() and field not in self.readers and field not in self.writers:
                    if not env.depend_graph.preds(m):
                        continue
                    assert ctor.usedef
                    stm = ctor.usedef.get_stms_defining(field).pop()
                    warn(stm, Warnings.CHANNEL_IS_NOT_USED,
                         [field.orig_name()])
            # check for local variable port
            for sym in ctor.symbols.values():
                if sym.typ.is_channel() and sym not in self.readers and sym not in self.writers:
                    assert ctor.usedef
                    stms = ctor.usedef.get_stms_defining(sym)
                    # This symbol might not be used (e.g. ancestor symbol),
                    # so we have to check if its definition statement exists.
                    if stms:
                        warn(list(stms)[0], Warnings.CHANNEL_IS_NOT_USED,
                             [sym.orig_name()])

    def _check_channel_direction(self, sym, func_scope):
        channel_typ = sym.typ
        rootsym = channel_typ.get_root_symbol()
        assert func_scope.name.startswith('polyphony.Channel')
        if func_scope.orig_name in ('put',):
            if self.writers[rootsym]:
                assert len(self.writers[rootsym]) == 1
                writer = list(self.writers[rootsym])[0]
                if writer is not self.scope and writer.worker_owner and writer.worker_owner is self.scope.worker_owner:
                    fail(self.current_stm, Errors.WRITING_IS_CONFLICTED,
                         [sym.orig_name()])
            else:
                assert self.scope.is_worker() or self.scope.parent.is_module()
                self.writers[rootsym].add(self.scope)
        elif func_scope.orig_name in ('get',):
            # read-read conflict
            if self.readers[rootsym]:
                assert len(self.readers[rootsym]) == 1
                reader = list(self.readers[rootsym])[0]
                if reader is not self.scope and reader.worker_owner is self.scope.worker_owner:
                    fail(self.current_stm, Errors.READING_IS_CONFLICTED,
                         [sym.orig_name()])
            else:
                assert self.scope.is_worker() or self.scope.parent.is_module()
                self.readers[rootsym].add(self.scope)

    def visit_CALL(self, ir):
        if not ir.func_scope().is_lib():
            return ir
        if ir.func_scope().is_method() and ir.func_scope().parent.is_channel():
            sym = ir.func.tail()
            assert sym.typ.is_channel()
            self._check_channel_direction(sym, ir.func_scope())
            if (self.current_stm.block.synth_params['scheduling'] == 'pipeline' and
                    self.scope.find_region(self.current_stm.block) is not self.scope.top_region()):
                root_sym = sym.typ.get_root_symbol()
                root_sym.add_tag('pipelined')
        return ir
