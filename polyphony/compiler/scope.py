import itertools
from collections import defaultdict, namedtuple
from copy import copy
from .block import Block
from .common import Tagged, fail
from .errors import Errors
from .env import env
from .graph import Graph
from .loop import LoopNestTree
from .symbol import Symbol
from .synth import make_synth_params
from .type import Type
from .irvisitor import IRVisitor
from .ir import CONST, JUMP, CJUMP, MCJUMP, PHIBase
from .signal import Signal
from logging import getLogger
logger = getLogger(__name__)


FunctionParam = namedtuple('FunctionParam', ('sym', 'copy', 'defval'))


class Scope(Tagged):
    ordered_scopes = []
    TAGS = {
        'global', 'function', 'class', 'method', 'ctor',
        'callable', 'returnable', 'mutable', 'inherited', 'predicate',
        'testbench', 'pure',
        'module', 'worker', 'instantiated',
        'lib', 'namespace', 'builtin', 'decorator',
        'port', 'typeclass',
        'function_module',
        'inlinelib',
    }
    scope_id = 0

    @classmethod
    def create(cls, parent, name, tags, lineno=0, origin=None):
        if name is None:
            name = "unnamed_scope" + str(cls.scope_id)
        s = Scope(parent, name, tags, lineno, cls.scope_id)
        if s.name in env.scopes:
            env.append_scope(s)
            fail((s, lineno), Errors.REDEFINED_NAME, {name})
        env.append_scope(s)
        if origin:
            s.origin = origin
            env.scope_file_map[s] = env.scope_file_map[origin]
        cls.scope_id += 1
        return s

    @classmethod
    def create_namespace(cls, parent, name, tags):
        tags |= {'namespace'}
        namespace = Scope.create(parent, name, tags, lineno=1)
        namesym = namespace.add_sym('__name__', typ=Type.str_t)
        if namespace.is_global():
            namespace.constants[namesym] = CONST('__main__')
        else:
            namespace.constants[namesym] = CONST(namespace.name)
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
        self.orig_name = name
        self.parent = parent
        if parent:
            self.name = parent.name + "." + name
            parent.append_child(self)

        self.lineno = lineno
        self.scope_id = scope_id
        self.symbols = {}
        self.params = []
        self.return_type = None
        self.entry_block = None
        self.exit_block = None
        self.children = []
        self.bases = []
        self.origin = None
        self.subs = []
        self.usedef = None
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

    def clone(self, prefix, postfix, parent=None):
        #if self.is_lib():
        #    return
        name = prefix + '_' if prefix else ''
        name += self.orig_name
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

        sym_replacer = SymbolReplacer(symbol_map)
        sym_replacer.process(s)

        #s.parent.append_child(s)
        #env.append_scope(s)
        s.cloned_symbols = symbol_map
        s.cloned_blocks = block_map
        s.cloned_stms = stm_map

        s.synth_params = self.synth_params.copy()
        # TODO:
        #s.loop_tree = None
        #s.constants
        return s

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

    def add_sym(self, name, tags=None, typ=Type.undef_t):
        if name in self.symbols:
            raise RuntimeError("symbol '{}' is already registered ".format(name))
        sym = Symbol(name, self, tags, typ)
        self.symbols[name] = sym
        return sym

    def add_temp(self, temp_name=None, tags=None, typ=Type.undef_t):
        name = Symbol.unique_name(temp_name)
        if tags:
            tags.add('temp')
        else:
            tags = {'temp'}
        return self.add_sym(name, tags, typ)

    def add_condition_sym(self):
        return self.add_temp(Symbol.condition_prefix, {'condition'}, typ=Type.bool_t)

    def add_param_sym(self, param_name, typ=Type.undef_t):
        name = '{}_{}'.format(Symbol.param_prefix, param_name)
        return self.add_sym(name, {'param'}, typ)

    def find_param_sym(self, param_name):
        name = '{}_{}'.format(Symbol.param_prefix, param_name)
        return self.find_sym(name)

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
            new_sym = self.add_sym(new_name, set(orig_sym.tags), typ=orig_sym.typ.clone())
            if orig_sym.ancestor:
                new_sym.ancestor = orig_sym.ancestor
            else:
                new_sym.ancestor = orig_sym
        return new_sym

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
        visited = set()
        yield from self.entry_block.traverse(visited)

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

    name = scope.orig_name + '_' + str(tag)
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
