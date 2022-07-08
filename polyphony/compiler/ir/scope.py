import itertools
from collections import defaultdict, namedtuple
from copy import copy
from .block import Block
from .loop import LoopNestTree
from .symbol import Symbol
from .synth import make_synth_params
from .type import Type
from .irvisitor import IRVisitor
from .ir import CONST, JUMP, CJUMP, MCJUMP, EXPR
from ..common.common import Tagged, fail
from ..common.errors import Errors
from ..common.env import env
from ..common.graph import Graph
from logging import getLogger
logger = getLogger(__name__)


FunctionParam = namedtuple('FunctionParam', ('sym', 'copy', 'defval'))


class Scope(Tagged):
    ordered_scopes = []
    TAGS = {
        'global', 'function', 'class', 'method', 'ctor', 'enclosure', 'closure',
        'callable', 'returnable', 'mutable', 'inherited', 'predicate',
        'testbench', 'pure', 'timed', 'comb', 'assigned',
        'module', 'worker', 'loop_worker', 'instantiated', 'specialized',
        'lib', 'namespace', 'builtin', 'decorator',
        'port', 'typeclass',
        'function_module',
        'inlinelib', 'unflatten',
        'package', 'directory',
        'interface'
    }
    scope_id = 0
    unnamed_ids = defaultdict(int)
    instance_ids = defaultdict(int)
    @classmethod
    def create(cls, parent, name, tags, lineno=0, origin=None):
        if name is None:
            name = str(cls.unnamed_ids[parent])
            cls.unnamed_ids[parent] += 1
        s = Scope(parent, name, tags, lineno, cls.scope_id)
        if s.name in env.scopes:
            env.append_scope(s)
            fail((env.scope_file_map[s], lineno), Errors.REDEFINED_NAME, {name})
        env.append_scope(s)
        if origin:
            s.origin = origin
            s.orig_name = origin.orig_name
            env.scope_file_map[s] = env.scope_file_map[origin]
        cls.scope_id += 1
        return s

    @classmethod
    def create_namespace(cls, parent, name, tags, path=None):
        tags |= {'namespace'}
        namespace = Scope.create(parent, name, tags, lineno=1)
        namesym = namespace.add_sym('__name__', typ=Type.str())
        if namespace.is_global():
            namespace.constants[namesym] = CONST('__main__')
        else:
            namespace.constants[namesym] = CONST(namespace.name)
        if path:
            filesym = namespace.add_sym('__file__', typ=Type.str())
            namespace.constants[filesym] = CONST(path)
        return namespace

    @classmethod
    def destroy(cls, scope):
        assert scope.name in env.scopes
        env.remove_scope(scope)

    @classmethod
    def get_scopes(cls, bottom_up=True, with_global=False, with_class=False, with_lib=False):
        def ret_helper():
            scopes = cls.ordered_scopes[:]
            scopes = [s for s in scopes if not s.is_pure()]
            # Exclude an no code scope
            scopes = [s for s in scopes
                      if not (s.is_lib() and s.is_function())
                      and not (s.is_lib() and s.is_method())
                      and not s.is_builtin()
                      and not s.is_decorator()
                      and not s.is_typeclass()
                      and not s.is_directory()]
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
        # hierarchical order
        def set_h_order(scope, order):
            if order > scope.order[0]:
                scope.order = (order, -1)
            else:
                return
            order += 1
            for s in scope.children:
                set_h_order(s, order)
        for s in env.scopes.values():
            s.order = (-1, 0)
        for s in env.scopes.values():
            if s.is_namespace():
                s.order = (0, 0)
                for f in s.children:
                    set_h_order(f, 1)
        if env.depend_graph:
            nodes = env.depend_graph.bfs_ordered_nodes()
            for s in nodes:
                d_order = nodes.index(s)
                preds = env.depend_graph.preds(s)
                if preds:
                    preds_max_order = max([nodes.index(p) for p in preds])
                else:
                    preds_max_order = 0
                if d_order < preds_max_order:
                    s.order = (s.order[0], d_order)
                else:
                    s.order = (s.order[0], preds_max_order + 1)

    @classmethod
    def get_class_scopes(cls, bottom_up=True):
        return [s for s in cls.get_scopes(bottom_up=bottom_up, with_class=True) if s.is_class()]

    @classmethod
    def global_scope(cls):
        return env.scopes[env.global_scope_name]

    @classmethod
    def is_unremovable(cls, s):
        return s.is_instantiated() or (s.parent and s.parent.is_instantiated())

    def __init__(self, parent, name, tags, lineno, scope_id):
        super().__init__(tags)
        self.name = name
        self.base_name = name
        self.orig_name = name
        self.parent = parent
        if parent:
            self.name = parent.name + "." + name
            parent.append_child(self)

        self.lineno = lineno
        self.scope_id = scope_id
        self.symbols = {}
        self.free_symbols = set()
        self.params = []
        self.return_type = None
        self.entry_block = None
        self.exit_block = None
        self.children = []
        self.bases = []
        self.origin = None
        self.subs = []
        self.usedef = None
        self.field_usedef = None
        self.loop_tree = LoopNestTree()
        self.callee_instances = defaultdict(set)
        #self.stgs = []
        self.order = (-1, -1)
        self.block_count = 0
        self.workers = []
        self.worker_owner = None
        self.asap_latency = -1
        self.type_args = []
        self.synth_params = make_synth_params()
        self.constants = {}
        self.branch_graph = Graph()
        self.closures = set()

    def __str__(self):
        s = '\n================================\n'
        tags = ", ".join([att for att in self.tags])
        if self.parent:
            s += "Scope: {}, parent={} ({})\n".format(self.base_name, self.parent.name, tags)
        else:
            s += "Scope: {} ({})\n".format(self.base_name, tags)

        for sym in self.symbols.values():
            s += f'{sym} {sym.tags}\n'
        #s += ", ".join([str(sym) for sym in self.symbols])
        #s += "\n"
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
        s += 'Synthesis\n{}\n'.format(self.synth_params)
        s += '================================\n'
        for blk in self.traverse_blocks():
            s += str(blk)
        s += '================================\n'
        for r in self.loop_tree.traverse():
            s += str(r)
        s += '================================\n'
        return s

    def __repr__(self):
        return self.name

    def __lt__(self, other):
        if self.order < other.order:
            return True
        elif self.order > other.order:
            return False
        elif self.order == other.order:
            return self.lineno < other.lineno

    def param_types(self):
        if self.is_method():
            params = self.params[1:]
        else:
            params = self.params[:]
        return [p.sym.typ for p in params]

    def _mangled_names(self, types):
        ts = []
        for t in types:
            if t.is_list():
                elm = self._mangled_names([t.get_element()])
                s = f'l_{elm}'
            elif t.is_tuple():
                elm = self._mangled_names([t.get_element()])
                elms = ''.join([elm] * t.get_length())
                s = f't_{elms}'
            elif t.is_class():
                # TODO: we should avoid naming collision
                s = f'c_{t.get_scope().base_name}'
            elif t.is_int():
                s = f'i{t.get_width()}'
            elif t.is_bool():
                s = f'b'
            elif t.is_str():
                s = f's'
            elif t.is_object():
                # TODO: we should avoid naming collision
                s = f'o_{t.get_scope().base_name}'
            else:
                s = str(t)
            ts.append(s)
        return '_'.join(ts)

    def signature(self):
        param_signature = self._mangled_names(self.param_types())
        return (self.name, param_signature)

    def clone_symbols(self, scope, postfix=''):
        symbol_map = {}

        for orig_sym in self.symbols.values():
            new_sym = orig_sym.clone(scope, postfix)
            exprs = Type.find_expr(orig_sym.typ)
            if exprs:
                new_sym.typ = orig_sym.typ.with_clone_expr()
            assert new_sym.name not in scope.symbols
            scope.symbols[new_sym.name] = new_sym
            symbol_map[orig_sym] = new_sym
        return symbol_map

    def clone_blocks(self, scope):
        block_map = {}
        stm_map = {}
        for b in self.traverse_blocks():
            block_map[b] = b.clone(scope, stm_map)
        for b in self.traverse_blocks():
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
        return block_map, stm_map

    def clone(self, prefix, postfix, parent=None, sym_postfix=''):
        #if self.is_lib():
        #    return
        name = prefix + '_' if prefix else ''
        name += self.base_name
        name = name + '_' + postfix if postfix else name
        parent = self.parent if parent is None else parent
        s = Scope.create(parent, name, set(self.tags), self.lineno, origin=self)
        logger.debug('CLONE {} {}'.format(self.name, s.name))

        s.children = list(self.children)
        # TODO: should be reconsidered the owned policy
        #for child in s.children:
        #    child.parent = s

        s.bases = list(self.bases)
        s.subs = list(self.subs)
        s.type_args = list(self.type_args)

        symbol_map = self.clone_symbols(s, sym_postfix)
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

        for n in self.branch_graph.nodes:
            if n in stm_map:
                new_n = stm_map[n]
                s.branch_graph.add_node(new_n)
        for n0, n1, _ in self.branch_graph.edges:
            if n0 in stm_map and n1 in stm_map:
                new_n0 = stm_map[n0]
                new_n1 = stm_map[n1]
                if new_n0 < new_n1:
                    s.branch_graph.add_edge(new_n0, new_n1)
                else:
                    s.branch_graph.add_edge(new_n1, new_n0)

        if self.is_function_module():
            new_callee_instances = defaultdict(set)
            for func_sym, inst_names in self.callee_instances.items():
                new_func_sym = symbol_map[func_sym]
                new_callee_instances[new_func_sym] = copy(inst_names)
            s.callee_instances = new_callee_instances
        s.order = self.order

        if self.parent is parent.origin and hasattr(parent, 'cloned_symbols'):
            for sym in self.parent.symbols.values():
                symbol_map[sym] = parent.cloned_symbols[sym]

        sym_replacer = SymbolReplacer(symbol_map)
        sym_replacer.process(s)

        #s.parent.append_child(s)
        #env.append_scope(s)
        s.cloned_symbols = symbol_map
        s.cloned_blocks = block_map
        s.cloned_stms = stm_map

        s.synth_params = self.synth_params.copy()
        s.closures = self.closures.copy()
        for sym in self.free_symbols:
            if sym in symbol_map:
                s.add_free_sym(symbol_map[sym])
            else:
                s.add_free_sym(sym)
        # TODO:
        #s.loop_tree = None
        #s.constants
        return s

    def _clone_child(self, new_class, old_class, origin_child):
        _, new_parent = new_class.find_child(origin_child.name, True)
        new_parent.children.remove(origin_child)
        new_child = origin_child.clone('', '', new_parent)

        res = new_class.find_closure(origin_child.name)
        if res:
            _, clos_parent = res
            clos_parent.closures.remove(origin_child)
            clos_parent.closures.add(new_child)
        return new_child

    def inherit(self, name, overrides):
        sub = Scope.create(self.parent, name, set(self.tags), self.lineno, origin=self)
        sub.bases.append(self)
        sub.symbols = copy(self.symbols)
        sub.workers = copy(self.workers)
        sub.children = copy(self.children)
        sub.exit_block = sub.entry_block = Block(sub)
        sub.add_tag('inherited')
        #env.append_scope(sub)
        self.subs.append(sub)

        new_scopes = {self:sub}
        for method in overrides:
            new_method = self._clone_child(sub, self, method)
            new_scopes[method] = new_method

        for old, new in new_scopes.items():
            syms = sub.find_scope_sym(old)
            for sym in syms:
                if sym.scope in new_scopes.values():
                    sym.typ = sym.typ.with_scope(new)
            if new.parent.is_namespace():
                continue
            old_sym = new.parent.symbols[new.base_name]
            new_sym = old_sym.clone(new.parent)
            new_sym.typ = new_sym.typ.with_scope(new)
            new.parent.symbols[new.base_name] = new_sym
        return sub

    def instantiate(self, inst_name, children, with_tag=True):
        new_class = self.clone('', inst_name, self.parent)
        if with_tag:
            new_class.add_tag('instantiated')
        assert new_class.origin is self

        old_class_sym = new_class.parent.find_sym(self.base_name)
        if old_class_sym.typ.is_class():
            new_t = Type.klass(new_class)
        elif old_class_sym.typ.is_function():
            new_t = Type.function(new_class)
        else:
            assert False
        new_sym = new_class.parent.add_sym(new_class.base_name, tags=old_class_sym.tags, typ=new_t)
        if old_class_sym.ancestor:
            new_sym.ancestor = old_class_sym.ancestor
        else:
            new_sym.ancestor = old_class_sym
        new_scopes = {self:new_class}
        for child in children:
            new_child = self._clone_child(new_class, self, child)
            if with_tag:
                new_child.add_tag('instantiated')
            new_scopes[child] = new_child
        for old, new in new_scopes.items():
            syms = new_class.find_scope_sym(old)
            for sym in syms:
                if sym.scope in new_scopes.values():
                    sym.typ = sym.typ.with_scope(new)
            if new.parent.is_namespace():
                continue
            assert new.parent.symbols[new.base_name].typ.get_scope() is new
        return new_class

    def find_child(self, name, rec=False):
        for child in self.children:
            if rec:
                if child.name == name:
                    return child, self
                res = child.find_child(name, True)
                if res:
                    c, p = res
                    return c, p
            else:
                if child.base_name == name:
                    return child, self
        return None

    def find_closure(self, name):
        for clos in self.closures:
            if clos.name == name:
                return clos, self
        for child in self.children:
            res = child.find_closure(name)
            if res:
                c, p = res
                return c, p
        return None

    def find_parent_scope(self, name):
        if self.find_child(name):
            return self
        elif self.parent:
            return self.parent.find_parent_scope(name)
        else:
            return None

    def find_scope(self, name):
        if self.base_name == name:
            return self
        ret = self.find_child(name)
        if ret:
            child, _ = ret
            return child
        if self.parent:
            return self.parent.find_scope(name)
        return None

    def collect_scope(self):
        scopes = self.children[:]
        for c in self.children:
            scopes.extend(c.collect_scope())
        return scopes

    def add_sym(self, name, tags=None, typ=None):
        if typ is None:
            typ = Type.undef()
        if name in self.symbols:
            raise RuntimeError("symbol '{}' is already registered ".format(name))
        sym = Symbol(name, self, tags, typ)
        self.symbols[name] = sym
        return sym

    def add_temp(self, temp_name=None, tags=None, typ=None):
        name = Symbol.unique_name(temp_name)
        if tags:
            tags.add('temp')
        else:
            tags = {'temp'}
        return self.add_sym(name, tags, typ)

    def add_condition_sym(self):
        return self.add_temp(Symbol.condition_prefix, {'condition'}, typ=Type.bool())

    def add_param_sym(self, param_name, typ=None):
        name = '{}_{}'.format(Symbol.param_prefix, param_name)
        return self.add_sym(name, {'param'}, typ)

    def find_param_sym(self, param_name):
        name = '{}_{}'.format(Symbol.param_prefix, param_name)
        return self.find_sym(name)

    def add_return_sym(self):
        return self.add_sym(Symbol.return_prefix, ['return'])

    def add_free_sym(self, sym):
        sym.add_tag('free')
        self.free_symbols.add(sym)

    def del_free_sym(self, sym):
        self.free_symbols.discard(sym)

    def del_sym(self, name):
        if name in self.symbols:
            del self.symbols[name]

    def import_sym(self, sym):
        if sym.name in self.symbols and sym is not self.symbols[sym.name]:
            raise RuntimeError("symbol '{}' is already registered ".format(sym.name))
        self.symbols[sym.name] = sym

    def import_copy_sym(self, orig_sym, new_name):
        if self.has_sym(new_name):
            new_sym = self.symbols[new_name]
        else:
            new_sym = self.add_sym(new_name, set(orig_sym.tags), typ=orig_sym.typ)
            new_sym.import_from(orig_sym)
        return new_sym

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
                    found = env.outermost_scope().find_sym(name)
                    if not found:
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
        #assert orig_sym.scope is self
        if self.has_sym(new_name):
            new_sym = self.symbols[new_name]
        else:
            new_sym = self.add_sym(new_name, set(orig_sym.tags) | {'inherited'}, typ=orig_sym.typ)
            if orig_sym.ancestor:
                new_sym.ancestor = orig_sym.ancestor
            else:
                new_sym.ancestor = orig_sym
        return new_sym

    def find_scope_sym(self, obj, rec=True):
        results = []
        for sym in self.symbols.values():
            if sym.typ.has_scope() and sym.typ.get_scope() is obj:
                results.append(sym)
        if rec:
            for c in self.children:
                results.extend(c.find_scope_sym(obj, True))
        return results

    def qualified_name(self):
        if self.name.startswith(env.global_scope_name):
            name = self.name[len(env.global_scope_name) + 1:]
        else:
            name = self.name
        return name.replace('.', '_')

    def set_entry_block(self, blk):
        assert self.entry_block is None
        self.entry_block = blk

    def set_exit_block(self, blk):
        self.exit_block = blk

    def traverse_blocks(self):
        assert len(self.entry_block.preds) == 0
        yield from self.entry_block.traverse()

    def replace_block(self, old, new):
        new.preds = old.preds[:]
        new.preds_loop = old.preds_loop[:]
        new.succs = old.succs[:]
        new.succs_loop = old.succs_loop[:]
        for blk in self.traverse_blocks():
            if blk is old:
                for pred in old.preds:
                    pred.replace_succ(old, new)
                    pred.replace_succ_loop(old, new)
                for succ in old.succs:
                    succ.replace_pred(old, new)
                    succ.replace_pred_loop(old, new)

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
        return self.name == env.global_scope_name

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

    def is_assignable(self, other):
        if self is other:
            return True
        if self.origin and self.origin.is_assignable(other):
            return True
        if other.origin and self.is_assignable(other.origin):
            return True
        return False

    def outer_module(self):
        if self.is_module():
            return self
        else:
            if self.parent.is_namespace():
                return None
            else:
                return self.parent.outer_module()

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
        for i, (w, _) in enumerate(self.workers[:]):
            if w is worker_scope:
                self.workers.pop(i)
        self.workers.append((worker_scope, worker_args))
        assert worker_scope.worker_owner is None or worker_scope.worker_owner is self
        worker_scope.worker_owner = self

    def reset_loop_tree(self):
        self.loop_tree = LoopNestTree()

    def top_region(self):
        return self.loop_tree.root

    def parent_region(self, r):
        return self.loop_tree.get_parent_of(r)

    def child_regions(self, r):
        return self.loop_tree.get_children_of(r)

    def set_top_region(self, r):
        self.loop_tree.root = r
        self.loop_tree.add_node(r)

    def append_child_regions(self, parent, children):
        for child in children:
            self.loop_tree.add_edge(parent, child)

    def append_sibling_region(self, r, new_r):
        parent = self.loop_tree.get_parent_of(r)
        self.loop_tree.add_edge(parent, new_r)

    def remove_region(self, r):
        parent = self.loop_tree.get_parent_of(r)
        self.loop_tree.del_edge(parent, r, auto_del_node=False)
        self.loop_tree.del_node(r)

    def find_region(self, blk):
        for r in self.loop_tree.traverse():
            if blk in r.blocks():
                return r
        return None

    def remove_block_from_region(self, blk):
        if not self.loop_tree.root:
            return
        r = self.find_region(blk)
        r.remove_body(blk)

    def is_leaf_region(self, r):
        return self.loop_tree.is_leaf(r)

    def traverse_regions(self, reverse=False):
        return self.loop_tree.traverse(reverse)

    def add_branch_graph_edge(self, k, vs):
        assert isinstance(vs, list)
        self.branch_graph.add_node(k)
        for v in itertools.chain(*vs):
            if k < v:
                self.branch_graph.add_edge(k, v)
            else:
                self.branch_graph.add_edge(v, k)

    def has_branch_edge(self, stm0, stm1):
        if stm0 < stm1:
            return self.branch_graph.find_edge(stm0, stm1) is not None
        else:
            return self.branch_graph.find_edge(stm1, stm0) is not None

    def add_closure(self, closure):
        assert closure.free_symbols
        self.closures.add(closure)

    def instance_number(self):
        n = Scope.instance_ids[self]
        Scope.instance_ids[self] += 1
        return n


class SymbolReplacer(IRVisitor):
    def __init__(self, sym_map):
        super().__init__()
        self.sym_map = sym_map

    def visit_TEMP(self, ir):
        if ir.sym in self.sym_map:
            ir.sym = self.sym_map[ir.sym]
        else:
            logger.debug('WARNING: not found {}'.format(ir.sym))

        for expr in Type.find_expr(ir.sym.typ):
            assert expr.is_a(EXPR)
            old_stm = self.current_stm
            self.current_stm = expr
            self.visit(expr)
            self.current_stm = old_stm

    def visit_ATTR(self, ir):
        self.visit(ir.exp)
        if ir.attr in self.sym_map:
            ir.attr = self.sym_map[ir.attr]
        else:
            logger.debug('WARNING: not found {}'.format(ir.attr))

        if isinstance(ir.attr, str):
            return
        for expr in Type.find_expr(ir.attr.typ):
            assert expr.is_a(EXPR)
            old_stm = self.current_stm
            self.current_stm = expr
            self.visit(expr)
            self.current_stm = old_stm

    def visit_ARRAY(self, ir):
        if ir.sym in self.sym_map:
            ir.sym = self.sym_map[ir.sym]
        for item in ir.items:
            self.visit(item)
        self.visit(ir.repeat)


def write_dot(scope, tag):
    try:
        import pydot
    except ImportError:
        raise
    # force disable debug mode to simplify the caption
    debug_mode = env.dev_debug_mode
    env.dev_debug_mode = False

    name = scope.base_name + '_' + str(tag)
    g = pydot.Dot(name, graph_type='digraph')

    def get_text(blk):
        s = blk.name + '\n'
        for stm in blk.stms:
            s += str(stm).replace('\n', '\l') + '\l'
        s = s.replace(':', '_')
        return s

    blk_map = {blk: pydot.Node(get_text(blk), shape='box') for blk in scope.traverse_blocks()}
    for n in blk_map.values():
        g.add_node(n)

    for blk in blk_map.keys():
        from_node = blk_map[blk]
        for succ in blk.succs:
            to_node = blk_map[succ]
            if succ in blk.succs_loop:
                g.add_edge(pydot.Edge(from_node, to_node, color='red'))
            else:
                g.add_edge(pydot.Edge(from_node, to_node))
        #for pred in blk.preds:
        #    to_node = blk_map[pred]
        #    if pred in blk.preds_loop:
        #        g.add_edge(pydot.Edge(from_node, to_node, style='dashed', color='red'))
        #    else:
        #        g.add_edge(pydot.Edge(from_node, to_node, style='dashed'))
    g.write_png('{}/{}.png'.format(env.debug_output_dir, name))
    env.dev_debug_mode = debug_mode
