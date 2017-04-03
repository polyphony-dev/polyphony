from collections import defaultdict, namedtuple
from copy import copy
from .block import Block
from .common import Tagged
from .env import env
from .symbol import Symbol
from .type import Type
from .irvisitor import IRVisitor
from .ir import JUMP, CJUMP, MCJUMP, PHI
from .signal import Signal

from logging import getLogger
logger = getLogger(__name__)


FunctionParam = namedtuple('FunctionParam', ('sym', 'copy', 'defval'))


class Scope(Tagged):
    ordered_scopes = []
    TAGS = {
        'global', 'function', 'class', 'method', 'ctor',
        'callable', 'returnable', 'mutable',
        'testbench',
        'module', 'worker',
        'lib', 'namespace', 'builtin',
        'port', 'typeclass',
        'function_module',
        'inlinelib',
    }

    @classmethod
    def create(cls, parent, name, tags, lineno=0):
        if name is None:
            name = "unnamed_scope" + str(len(env.scopes))
        s = Scope(parent, name, tags, lineno)
        assert s.name not in env.scopes
        env.append_scope(s)
        return s

    @classmethod
    def destroy(cls, scope):
        assert scope.name in env.scopes
        env.remove_scope(scope)
        if scope.parent:
            assert scope in scope.parent.children
            scope.parent.children.remove(scope)

    @classmethod
    def get_scopes(cls, bottom_up=True, with_global=False, with_class=False, with_lib=False):
        def ret_helper():
            scopes = cls.ordered_scopes[:]
            if not with_global:
                scopes.remove(Scope.global_scope())
            if not with_class:
                scopes = [s for s in scopes if not s.is_class()]
            if not with_lib:
                scopes = [s for s in scopes if not s.is_lib()]
            if bottom_up:
                scopes.reverse()
            return scopes

        cls.reorder_scopes()
        cls.ordered_scopes = sorted(env.scopes.values())

        return ret_helper()

    @classmethod
    def reorder_scopes(cls):
        def set_order(scope, order, ordered):
            if order > scope.order:
                scope.order = order
                ordered.add(scope)
            elif scope in ordered:
                return
            order += 1
            for s in scope.children:
                set_order(s, order, ordered)
            if env.call_graph:
                for s in env.call_graph.succs(scope):
                    set_order(s, order, ordered)
        top = cls.global_scope()
        top.order = 0
        ordered = set()
        for f in top.children:
            set_order(f, 1, ordered)

    @classmethod
    def get_class_scopes(cls, bottom_up=True):
        return [s for s in cls.get_scopes(bottom_up=bottom_up, with_class=True) if s.is_class()]

    @classmethod
    def global_scope(cls):
        return env.scopes['@top']

    @classmethod
    def is_unremoveable(cls, s):
        return s.is_global()

    def __init__(self, parent, name, tags, lineno):
        super().__init__(tags)
        self.name = name
        self.orig_name = name
        self.parent = parent
        if parent:
            self.name = parent.name + "." + name
            parent.append_child(self)

        self.lineno = lineno
        self.symbols = {}
        self.params = []
        self.return_type = None
        self.entry_block = None
        self.exit_block = None
        self.children = []
        self.bases = []
        self.usedef = None
        self.loop_nest_tree = None
        self.callee_instances = defaultdict(set)
        self.stgs = []
        self.order = -1
        self.module_info = None
        self.signals = {}
        self.block_count = 0
        self.paths = []
        self.workers = []
        self.worker_owner = None
        self.asap_latency = -1
        self.type_args = []

    def __str__(self):
        s = '\n================================\n'
        tags = ", ".join([att for att in self.tags])
        if self.parent:
            s += "Scope: {}, parent={} ({})\n".format(self.orig_name, self.parent.name, tags)
        else:
            s += "Scope: {} ({})\n".format(self.orig_name, tags)

        s += ", ".join([str(sym) for sym in self.symbols])
        s += "\n"
        s += '================================\n'
        s += 'Parameters\n'
        for p, _, val in self.params:
            if val:
                s += '{}:{} = {}\n'.format(p, repr(p.typ), val)
            else:
                s += '{}:{}\n'.format(p, repr(p.typ))
        s += "\n"
        s += 'Return\n'
        if self.return_type:
            s += '{}\n'.format(repr(self.return_type))
        else:
            s += 'None\n'
        s += '================================\n'
        for blk in self.traverse_blocks(longitude=True):
            s += str(blk)
        s += '================================\n'
        return s

    def __repr__(self):
        return self.name

    def __lt__(self, other):
        return (self.order, self.lineno) < (other.order, other.lineno)

    def clone_symbols(self, scope, postfix=''):
        symbol_map = {}

        for orig_sym in self.symbols.values():
            new_sym = orig_sym.clone(scope, postfix)
            assert new_sym.name not in scope.symbols
            scope.symbols[new_sym.name] = new_sym
            symbol_map[orig_sym] = new_sym
        return symbol_map

    def clone_blocks(self, scope):
        block_map = {}
        stm_map = {}
        for b in self.traverse_blocks(full=True):
            block_map[b] = b.clone(scope, stm_map)
        for b in self.traverse_blocks(full=True):
            b_clone = block_map[b]
            b_clone.reconnect(block_map)

        # jump target
        for stm in stm_map.values():
            if stm.is_a(JUMP):
                stm.target = block_map[stm.target]
            elif stm.is_a(CJUMP):
                stm.true = block_map[stm.true]
                stm.false = block_map[stm.false]
            elif stm.is_a(MCJUMP):
                stm.targets = [block_map[t] for t in stm.targets]
            elif stm.is_a(PHI):
                stm.defblks = [block_map[blk] for blk in stm.defblks]
        return block_map, stm_map

    def clone(self, prefix, postfix, parent=None):
        #if self.is_lib():
        #    return
        name = prefix + '_' if prefix else ''
        name += self.orig_name
        name = name + '_' + postfix if postfix else name
        parent = self.parent if parent is None else parent
        s = Scope(parent, name, set(self.tags), self.lineno)
        logger.debug('CLONE {} {}'.format(self.name, s.name))

        s.children = list(self.children)
        for child in s.children:
            child.parent = s

        s.bases = list(self.bases)
        s.type_args = list(self.type_args)

        symbol_map = self.clone_symbols(s)
        s.params = []
        for p, cp, defval in self.params:
            param = FunctionParam(symbol_map[p],
                                  symbol_map[cp],
                                  defval.clone() if defval else None)
            s.params.append(param)
        s.return_type = self.return_type
        block_map, stm_map = self.clone_blocks(s)
        s.entry_block = block_map[self.entry_block]
        s.exit_block = block_map[self.exit_block]

        s.usedef = None

        if self.is_function_module():
            new_callee_instances = defaultdict(set)
            for func_sym, inst_names in self.callee_instances.items():
                new_func_sym = symbol_map[func_sym]
                new_callee_instances[new_func_sym] = copy(inst_names)
            s.callee_instances = new_callee_instances
        s.order = self.order

        sym_replacer = SymbolReplacer(symbol_map)
        sym_replacer.process(s)

        s.parent.append_child(s)
        env.append_scope(s)
        s.clone_symbols = symbol_map
        s.clone_blocks = block_map
        s.clone_stms = stm_map
        return s

    def inherit(self, name, overrides):
        sub = Scope(self.parent, name, set(self.tags), self.lineno)
        sub.bases.append(self)
        sub.symbols = copy(self.symbols)
        sub.workers = copy(self.workers)
        sub.children = copy(self.children)
        sub.exit_block = sub.entry_block = Block(sub)
        sub.return_type = Type.object(sub)
        env.append_scope(sub)

        for method in overrides:
            sub.children.remove(method)
            sub_method = method.clone('', '', sub)
            _in_self_sym, self_sym, _ = sub_method.params[0]
            assert self_sym.name == 'self'
            assert self_sym.typ.get_scope() is self
            self_typ = Type.object(sub)
            _in_self_sym.set_type(self_typ)
            self_sym.set_type(self_typ)

            method_sym = sub.symbols[sub_method.orig_name]
            sub_method_sym = method_sym.clone(sub)
            sub_method_sym.typ.set_scope(sub_method)
            sub.symbols[sub_method.orig_name] = sub_method_sym
        return sub

    def find_child(self, name):
        for child in self.children:
            if child.orig_name == name:
                return child
        return None

    def find_parent_scope(self, name):
        if self.find_child(name):
            return self
        elif self.parent:
            return self.parent.find_parent_scope(name)
        else:
            return None

    def find_scope(self, name):
        if self.orig_name == name:
            return self
        child = self.find_child(name)
        if child:
            return child
        if self.parent:
            return self.parent.find_scope(name)
        return None

    def add_sym(self, name, tags=None):
        if name in self.symbols:
            raise RuntimeError("symbol '{}' is already registered ".format(name))
        sym = Symbol(name, self, tags)
        self.symbols[name] = sym
        return sym

    def add_temp(self, temp_name=None, tags=None):
        name = Symbol.unique_name(temp_name)
        if tags:
            tags.add('temp')
        else:
            tags = {'temp'}
        return self.add_sym(name, tags)

    def add_condition_sym(self):
        return self.add_temp(Symbol.condition_prefix, {'condition'})

    def add_param_sym(self, param_name):
        name = '{}_{}'.format(Symbol.param_prefix, param_name)
        return self.add_sym(name, ['param'])

    def add_return_sym(self):
        return self.add_sym(Symbol.return_prefix, ['return'])

    def del_sym(self, name):
        if name in self.symbols:
            del self.symbols[name]

    def import_sym(self, sym):
        if sym.name in self.symbols and sym is not self.symbols[sym.name]:
            raise RuntimeError("symbol '{}' is already registered ".format(sym.name))
        self.symbols[sym.name] = sym

    def find_sym(self, name):
        names = name.split('.')
        if len(names) > 1:
            return self.find_sym_r(names)
        if name in self.symbols:
            return self.symbols[name]
        elif self.parent:
            if self.parent.is_class():
                # look-up from bases
                for base in self.bases:
                    found = base.find_sym(name)
                    if found:
                        break
                else:
                    # otherwise, look-up from global
                    found = self.global_scope().find_sym(name)
            else:
                found = self.parent.find_sym(name)
            return found
        return None

    def find_sym_r(self, names):
        name = names[0]
        sym = self.find_sym(name)
        if sym and len(names) > 1:
            if sym.typ.is_containable():
                return sym.typ.get_scope().find_sym_r(names[1:])
            else:
                return None
        return sym

    def has_sym(self, name):
        return name in self.symbols

    def gen_sym(self, name):
        if self.has_sym(name):
            sym = self.symbols[name]
        else:
            sym = self.add_sym(name)
        return sym

    def rename_sym(self, old, new):
        assert old in self.symbols
        sym = self.symbols[old]
        del self.symbols[old]
        sym.name = new
        self.symbols[new] = sym
        return sym

    def inherit_sym(self, orig_sym, new_name):
        assert orig_sym.scope is self
        if self.has_sym(new_name):
            new_sym = self.symbols[new_name]
        else:
            new_sym = self.add_sym(new_name, set(orig_sym.tags))
            new_sym.typ = orig_sym.typ
            if orig_sym.ancestor:
                new_sym.ancestor = orig_sym.ancestor
            else:
                new_sym.ancestor = orig_sym
        return new_sym

    def qualified_name(self):
        n = ""
        if self.parent is not None:
            n = self.parent.qualified_name() + "_"
        n += self.name
        return n

    def set_entry_block(self, blk):
        assert self.entry_block is None
        self.entry_block = blk

    def set_exit_block(self, blk):
        assert self.exit_block is None
        self.exit_block = blk

    def traverse_blocks(self, full=False, longitude=False):
        assert len(self.entry_block.preds) == 0
        visited = set()
        yield from self.entry_block.traverse(visited, full, longitude)

    def append_child(self, child_scope):
        if child_scope not in self.children:
            self.children.append(child_scope)

    def add_param(self, sym, copy, defval):
        self.params.append(FunctionParam(sym, copy, defval))

    def has_param(self, sym):
        name = sym.name.split('#')[0]
        for p, _, _ in self.params:
            if p.name == name:
                return True
        return False

    def get_param_index(self, sym):
        name = sym.name.split('#')[0]
        for i, (p, _, _) in enumerate(self.params):
            if p.name == name:
                return i
        return -1

    def append_callee_instance(self, callee_scope, inst_name):
        self.callee_instances[callee_scope].add(inst_name)

    def dfgs(self, bottom_up=False):
        def collect_dfg(dfg, ds):
            ds.append(dfg)
            for c in dfg.children:
                collect_dfg(c, ds)
        ds = []
        collect_dfg(self.top_dfg, ds)
        return ds

    def find_ctor(self):
        assert self.is_class()
        for child in self.children:
            if child.is_ctor():
                return child
        return None

    def is_global(self):
        return self is Scope.global_scope()

    def is_containable(self):
        return self.is_namespace() or self.is_class()

    def is_subclassof(self, clazz):
        if self is clazz:
            return True
        for base in self.bases:
            if base is clazz:
                return True
            if base.is_subclassof(clazz):
                return True
        return False

    def find_stg(self, name):
        assert self.stgs
        for stg in self.stgs:
            if stg.name == name:
                return stg
        return None

    def get_main_stg(self):
        assert self.stgs
        for stg in self.stgs:
            if stg.is_main():
                return stg
        return None

    def gen_sig(self, name, width, tag=None):
        if name in self.signals:
            sig = self.signals[name]
            sig.width = width
            if tag:
                sig.add_tag(tag)
            return sig
        sig = Signal(name, width, tag)
        self.signals[name] = sig
        return sig

    def signal(self, name):
        if name in self.signals:
            return self.signals[name]
        for base in self.bases:
            found = base.signal(name)
            if found:
                return found
        return None

    def get_signals(self):
        signals_ = {}
        for base in self.bases:
            signals_.update(base.get_signals())
        signals_.update(self.signals)
        return signals_

    def rename_sig(self, old, new):
        assert old in self.signals
        sig = self.signals[old]
        del self.signals[old]
        sig.name = new
        self.signals[new] = sig
        return sig

    def class_fields(self):
        assert self.is_class()
        class_fields = {}
        if self.bases:
            for base in self.bases:
                fields = base.class_fields()
                class_fields.update(fields)
        class_fields.update(self.symbols)
        return class_fields

    def register_worker(self, worker_scope, worker_args):
        self.workers.append((worker_scope, worker_args))
        assert worker_scope.worker_owner is None
        worker_scope.worker_owner = self


class SymbolReplacer(IRVisitor):
    def __init__(self, sym_map):
        super().__init__()
        self.sym_map = sym_map

    def visit_TEMP(self, ir):
        if ir.sym in self.sym_map:
            ir.sym = self.sym_map[ir.sym]
        else:
            logger.debug('WARNING: not found {}'.format(ir.sym))

    def visit_ATTR(self, ir):
        self.visit(ir.exp)
        if ir.attr in self.sym_map:
            ir.attr = self.sym_map[ir.attr]
        else:
            logger.debug('WARNING: not found {}'.format(ir.attr))
