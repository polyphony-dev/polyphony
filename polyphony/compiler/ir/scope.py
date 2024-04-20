import itertools
from collections import defaultdict, namedtuple
from copy import copy
import dataclasses
from typing import NamedTuple
from xml.dom.expatbuilder import Namespaces
from .builtin import builtin_symbols
from .block import Block
from .loop import LoopNestTree
from .symbol import Symbol
from .synth import make_synth_params
from .types.type import Type
from .types import typehelper
from .irvisitor import IRVisitor
from .ir import *
from .irhelper import qualified_symbols
from ..common.common import Tagged, fail
from ..common.errors import Errors
from ..common.env import env
from ..common.graph import Graph
from logging import getLogger
logger = getLogger(__name__)




class FunctionParam(NamedTuple):
    sym: Symbol
    defval: IRExp|None

class FunctionParams(object):
    def __init__(self, is_method=False):
        self._params:list[FunctionParam] = []
        self._is_method:bool = is_method

    def add_param(self, sym:Symbol, defval:IRExp|None):
        self._params.append(FunctionParam(sym, defval))

    def _explicit_params(self, with_self) -> list[FunctionParam]:
        if not with_self and self._is_method:
            return self._params[1:]
        else:
            return self._params[:]

    def symbols(self, with_self=False) -> tuple[Symbol, ...]:
        params = self._explicit_params(with_self)
        return tuple([sym for sym, _ in params])

    def default_values(self, with_self=False) -> tuple[IRExp|None, ...]:
        params = self._explicit_params(with_self)
        return tuple([defval for _, defval in params])

    def types(self, with_self=False) -> tuple[Type, ...]:
        params = self._explicit_params(with_self)
        return tuple([p.sym.typ for p in params])

    def _param_name(self, sym):
        l = len(Symbol.param_prefix + '_')
        return sym.name[l:]

    def param_names(self, with_self=False):
        names = []
        for s in self.symbols(with_self):
            names.append(self._param_name(s))
        return names

    def clear(self):
        self._params = []

    def remove(self, sym):
        params = []
        for s, v in self._params:
            if s is sym:
                continue
            elif self._param_name(s) == sym:
                continue
            params.append(FunctionParam(s, v))
        self._params = params

    def remove_by_indices(self, indices):
        for i in reversed(indices):
            if self._is_method:
                self._params.pop(i + 1)
            else:
                self._params.pop(i)

    def __str__(self):
        s = ''
        for p, val in self._params:
            if val:
                s += '{}:{} = {}\n'.format(p, repr(p.typ), val)
            else:
                s += '{}:{}\n'.format(p, repr(p.typ))
        return s

    def __len__(self):
        return len(self._params)


class SymbolTable(object):
    def __init__(self):
        self.symbols = {}

    def __str__(self):
        s = ''
        for name, sym in self.symbols.items():
            s += f'{name} - {sym}:{sym.typ} {sym.tags} {sym.scope.name}\n'
        #for sym in self.symbols.values():
        #    s += f'{sym}:{sym.typ} {sym.tags}\n'
        return s

    def add_sym(self, name: str, tags: set[str], typ: Type|None):
        if typ is None:
            typ = Type.undef()
        if name in self.symbols:
            raise RuntimeError("symbol '{}' is already registered ".format(name))
        sym = Symbol(name, self, tags, typ)
        self.symbols[name] = sym
        return sym

    def add_temp(self, temp_name: str='', tags: set[str]=set(), typ: Type|None=None):
        name = Symbol.unique_name(temp_name)
        if tags:
            tags.add('temp')
        else:
            tags = {'temp'}
        return self.add_sym(name, tags, typ)

    def add_condition_sym(self):
        return self.add_temp(Symbol.condition_prefix, {'condition'}, typ=Type.bool())

    def add_param_sym(self, param_name: str, tags: set[str], typ: Type|None=None):
        name = '{}_{}'.format(Symbol.param_prefix, param_name)
        return self.add_sym(name, tags|{'param'}, typ)

    def del_sym(self, name):
        if name in self.symbols:
            del self.symbols[name]

    def import_sym(self, sym, asname=None):
        if asname:
            name = asname
        else:
            name = sym.name
        if name in self.symbols and sym is not self.symbols[name]:
            raise RuntimeError(f"symbol '{sym}' is already registered as {name}")
        self.symbols[name] = sym
        sym.add_tag('imported')

    def find_sym(self, name):
        names = name.split('.')
        if len(names) > 1:
            return self.find_sym_r(names)
        if name in self.symbols:
            return self.symbols[name]
        return None

    def find_sym_r(self, names):
        name = names[0]
        sym = self.find_sym(name)
        if sym and len(names) > 1:
            sym_t = sym.typ
            if sym_t.is_containable():
                return sym_t.scope.find_sym_r(names[1:])
            else:
                return None
        return sym

    def find_syms_by_tags(self, tags: set[str]) -> set[Symbol]:
        syms = set()
        for sym in self.symbols.values():
            if sym.tags.issuperset(tags):
                syms.add(sym)
        return syms

    def has_sym(self, name: str) -> bool:
        return name in self.symbols

    def gen_sym(self, name):
        if self.has_sym(name):
            sym = self.symbols[name]
        else:
            sym = self.add_sym(name, tags=set(), typ=Type.undef())
        return sym

    def rename_sym(self, old: str, new: str):
        assert old in self.symbols
        sym = self.symbols[old]
        del self.symbols[old]
        sym.name = new
        self.symbols[new] = sym
        return sym

    def rename_sym_asname(self, old: str, new: str):
        assert old in self.symbols
        sym = self.symbols[old]
        del self.symbols[old]
        self.symbols[new] = sym
        return sym

    def inherit_sym(self, orig_sym, new_name):
        assert orig_sym.scope is self
        if orig_sym.is_imported():
            print(orig_sym)
        if self.has_sym(new_name):
            new_sym = self.symbols[new_name]
        else:
            orig_sym_t = orig_sym.typ
            new_sym = self.add_sym(new_name, set(orig_sym.tags) | {'inherited'}, typ=orig_sym_t)
            if orig_sym.ancestor:
                new_sym.ancestor = orig_sym.ancestor
            else:
                new_sym.ancestor = orig_sym
        return new_sym

    def find_scope_sym(self, obj):
        results = []
        for sym in self.symbols.values():
            sym_t = sym.typ
            if sym_t.has_scope() and sym_t.scope is obj:
                results.append(sym)
        return results

    def free_symbols(self):
        return [sym for sym in self.symbols.values() if sym.is_free()]


class Scope(Tagged, SymbolTable):
    TAGS = {
        'global', 'function', 'class', 'method', 'ctor', 'enclosure', 'closure',
        'callable', 'returnable', 'mutable', 'inherited', 'predicate',
        'testbench', 'pure', 'timed', 'comb', 'assigned',
        'module', 'top_module', 'worker', 'loop_worker', 'instantiated', 'specialized',
        'lib', 'namespace', 'builtin', 'decorator',
        'port', 'typeclass', 'object',
        'function_module',
        'inlinelib', 'unflatten',
        'package', 'directory',
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
            s.orig_base_name = origin.orig_base_name
            env.scope_file_map[s] = env.scope_file_map[origin]
        cls.scope_id += 1
        return s

    @classmethod
    def create_namespace(cls, parent, name, tags, path=None):
        tags |= {'namespace'}
        namespace = Scope.create(parent, name, tags, lineno=1)
        if not namespace.is_builtin():
            namesym = namespace.add_sym('__name__', tags=set(), typ=Type.str())
            if namespace.is_global():
                namespace.constants[namesym] = CONST('__main__')
            else:
                namespace.constants[namesym] = CONST(namespace.name)
            if path:
                filesym = namespace.add_sym('__file__', tags=set(), typ=Type.str())
                namespace.constants[filesym] = CONST(path)
        return namespace

    @classmethod
    def destroy(cls, scope):
        assert scope.name in env.scopes
        if scope.parent and not scope.parent.symbols[scope.base_name].is_imported():
            scope.parent.del_sym(scope.base_name)
            scope.parent.children.remove(scope)
            env.remove_scope(scope)

    @classmethod
    def is_normal_scope(cls, s):
        return (not (s.is_lib() and s.is_function())
            and not (s.is_lib() and s.is_method())
            and not s.is_builtin()
            and not s.is_decorator()
            and not s.is_typeclass()
            and not s.is_directory())

    @classmethod
    def get_scopes(cls, bottom_up=True, with_global=False, with_class=False, with_lib=False) -> list['Scope']:
        scopes:list[Scope] = sorted(env.scopes.values())
        scopes = [s for s in scopes if not s.is_pure()]
        # Exclude an no code scope
        scopes = [s for s in scopes if cls.is_normal_scope(s)]
        if not with_global:
            scopes.remove(Scope.global_scope())
        if not with_class:
            scopes = [s for s in scopes if not s.is_class()]
        if not with_lib:
            scopes = [s for s in scopes if not s.is_lib()]
        if bottom_up:
            scopes.reverse()
        return scopes

    @classmethod
    def get_class_scopes(cls, bottom_up=True):
        return [s for s in cls.get_scopes(bottom_up=bottom_up, with_class=True) if s.is_class()]

    @classmethod
    def global_scope(cls):
        return env.scopes[env.global_scope_name]

    @classmethod
    def is_unremovable(cls, s):
        return s.is_instantiated() or (s.parent and s.parent.is_instantiated())

    @property
    def name(self):
        if self.parent:
            return self.parent.name + "." + self.base_name
        return self.base_name

    def __init__(self, parent, name, tags, lineno, scope_id):
        Tagged.__init__(self, tags)
        SymbolTable.__init__(self)
        self.base_name: str = name
        self.parent: 'Scope' = parent
        if parent:
            parent.append_child(self)
        self.orig_name: str = self.name
        self.orig_base_name: str = name
        self.lineno: int = lineno
        self.scope_id: int = scope_id
        self.function_params = FunctionParams(self.is_method())
        self.return_type: Type = None
        self.entry_block: Block = None
        self.exit_block: Block = None
        self.children: list['Scope'] = []
        self.bases: list['Scope'] = []
        self.origin: 'Scope' = None
        self.usedef = None
        self.field_usedef = None
        self.loop_tree = LoopNestTree()
        self.block_count = 0
        self.workers: list['Scope'] = []
        self.worker_owner: 'Scope' = None
        self.asap_latency = -1
        self.synth_params = make_synth_params()
        self.constants = {}
        self.branch_graph = Graph()
        self.module_params = []
        self.module_param_vars = []
        self._bound_args = []

    def __str__(self):
        s = '================================\n'
        tags = ", ".join([f"'{att}'" for att in self.tags])
        s += 'Scope:\n'
        s += f'    name: {self.name}\n'
        s += f'    tags: {tags}\n'

        s += 'Symbols:\n'
        for line in SymbolTable.__str__(self).split('\n'):
            s += f'    {line}\n'

        if self.constants:
            s += 'Constants:\n'
            for sym, const in self.constants.items():
                s += f'    {sym}:{sym.typ} = {const}\n'

        if self.function_params:
            s += 'Parameters:\n'
            ss = ['    ' + line for line in str(self.function_params).split('\n') if line]
            s += '\n'.join(ss)
            s += '\n'
        s += 'Return:\n'
        if self.return_type:
            s += '    {}\n'.format(repr(self.return_type))
        else:
            s += '    None\n'

        s += 'Synthesis:\n'
        s += f'    {self.synth_params}\n'

        s += 'Blocks:\n'
        for blk in self.traverse_blocks():
            s += str(blk)
        if self.loop_tree:
            s += 'Loop Tree:\n'
            for r in self.loop_tree.traverse():
                s += f'    {r}'
        return s

    def dump(self):
        print(self)

    def __repr__(self):
        return self.name

    def __lt__(self, other):
        return self.scope_id < other.scope_id

    def __hash__(self):
        return hash(self.name)

    def _mangled_names(self, types):
        ts = []
        for t in types:
            if t.is_list():
                elm = self._mangled_names([t.element])
                s = f'l_{elm}'
            elif t.is_tuple():
                elm = self._mangled_names([t.element])
                elms = ''.join([elm] * t.length)
                s = f't_{elms}'
            elif t.is_class():
                # TODO: we should avoid naming collision
                s = f'c_{t.scope.base_name}'
            elif t.is_int():
                s = f'i{t.width}'
            elif t.is_bool():
                s = f'b'
            elif t.is_str():
                s = f's'
            elif t.is_object():
                # TODO: we should avoid naming collision
                s = f'o_{t.scope.base_name}'
            else:
                s = str(t)
            ts.append(s)
        return '_'.join(ts)

    def signature(self):
        param_signature = self._mangled_names(self.param_types())
        return (self.name, param_signature)

    def unique_name(self):
        return self.name.replace('@top.', '').replace('.', '_')

    def clone_symbols_by_name(self, scope):
        for asname, orig_sym in self.symbols.items():
            if orig_sym.scope is not self:
               scope.import_sym(orig_sym, asname)
               continue
            orig_name = f'{orig_sym.name}'
            if orig_name not in scope.symbols:
                new_sym = orig_sym.clone(scope, orig_name)
                scope.symbols[new_sym.name] = new_sym
                new_sym.typ = orig_sym.typ.clone()

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

    def clone(self, prefix, postfix, parent=None, recursive=False, rename_children=True):
        def clone_name(prefix: str, postfix: str, base_name: str) -> str:
            name = prefix + '_' if prefix else ''
            name += base_name
            name = name + '_' + postfix if postfix else name
            return name

        name = clone_name(prefix, postfix, self.base_name)
        parent = self.parent if parent is None else parent
        s = Scope.create(parent, name, set(self.tags), self.lineno, origin=self)

        self_sym = self.parent.find_sym(self.base_name)
        new_sym_typ = self_sym.typ.clone(scope=s)
        parent.add_sym(s.base_name, set(self_sym.tags), typ=new_sym_typ)
        logger.debug('CLONE {} {}'.format(self.name, s.name))

        if recursive:
            if rename_children:
                s.children = [child.clone(prefix, postfix, s, recursive, rename_children) for child in self.children]
            else:
                s.children = [child.clone('', '', s, recursive, rename_children) for child in self.children]
        else:
            s.children = list(self.children)

        s.bases = list(self.bases)

        self.clone_symbols_by_name(s)
        for p, defval in zip(self.param_symbols(with_self=True), self.param_default_values(with_self=True)):
            s.add_param(s.symbols[p.name], defval.clone() if defval else None)

        s.return_type = self.return_type
        block_map, stm_map = self.clone_blocks(s)
        s.entry_block = block_map[self.entry_block]
        s.exit_block = block_map[self.exit_block]
        s.usedef = None

        if recursive and rename_children:
            symbol_map = {}
            # We need to remove a symbol of original child scope
            for name, sym in s.symbols.copy().items():
                children_names = [child.base_name for child in self.children]
                if sym.name in children_names:
                    del s.symbols[name]
                    orig_sym = self.symbols[name]
                    if rename_children:
                        new_child_name = clone_name(prefix, postfix, name)
                    else:
                        new_child_name = name
                    symbol_map[name] = s.symbols[new_child_name]
            NameReplacer(symbol_map).process(s)

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

        s.synth_params = self.synth_params.copy()
        return s

    def instantiate(self, inst_name, parent=None):
        if parent is None:
            parent = self.parent
        new_class = self.clone('', inst_name, parent, recursive=True, rename_children=False)
        assert new_class.origin is self

        old_class_sym = self.parent.find_sym(self.base_name)
        new_sym = new_class.parent.find_sym(new_class.base_name)
        assert isinstance(new_sym, Symbol)
        if old_class_sym.ancestor:
            new_sym.ancestor = old_class_sym.ancestor
        else:
            new_sym.ancestor = old_class_sym
        new_scopes: dict['Scope', 'Scope'] = {self:new_class}
        for old_child, new_child in zip(self.children, new_class.children):
            new_scopes[old_child] = new_child
        for old, new in new_scopes.items():
            syms = new_class.find_scope_sym(old)
            for sym in syms:
                if sym.scope in new_scopes.values():
                    sym.typ = sym.typ.clone(scope=new)
            if new.parent.is_namespace():
                continue
            # sanity check
            new_t = new.parent.find_sym(new.base_name).typ
            assert new_t.scope is new
        # deal with type scope
        self._replace_type_scope(new_scopes)
        return new_class

    def _replace_type_scope(self, new_scopes: dict['Scope', 'Scope']):
        value_map = {old.name:new.name for old, new in new_scopes.items()}
        for new in new_scopes.values():
            for sym in new.symbols.values():
                d = dataclasses.asdict(sym.typ)
                dd = {}
                if typehelper.replace_type_dict(d, dd, 'scope_name', value_map):
                    sym.typ = sym.typ.__class__.from_dict(dd)

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

    def find_namespace(self):
        if self.is_namespace():
            return self
        else:
            return self.parent.find_namespace()

    def find_owner_scope(self, symbol: Symbol):
        if symbol in self.symbols.values():
            return self
        elif self.parent:
            return self.parent.find_owner_scope(symbol)
        else:
            return None

    def collect_scope(self):
        scopes = self.children[:]
        for c in self.children:
            scopes.extend(c.collect_scope())
        assert len(set(scopes)) == len(scopes)
        return scopes

    def param_names(self, with_self=False):
        return self.function_params.param_names(with_self)

    def param_symbols(self, with_self=False):
        return self.function_params.symbols(with_self)

    def param_default_values(self, with_self=False):
        return self.function_params.default_values(with_self)

    def param_types(self, with_self=False):
        return self.function_params.types(with_self)

    def clear_params(self):
        return self.function_params.clear()

    def remove_param(self, key:Symbol|list[int]):
        if isinstance(key, Symbol):
            return self.function_params.remove(key)
        elif isinstance(key, list):
            return self.function_params.remove_by_indices(key)

    def find_param_sym(self, param_name):
        name = '{}_{}'.format(Symbol.param_prefix, param_name)
        return self.find_sym(name)

    def add_return_sym(self, typ: Type=Type.undef()):
        return self.add_sym(Symbol.return_name, {'return'}, typ)

    def find_sym(self, name:str) -> Symbol | None:
        sym = SymbolTable.find_sym(self, name)
        if sym:
            return sym
        elif self.parent:
            parent = self.parent
            # Class scope is not included in Python's LEGB search
            while parent.is_class():
                parent = parent.parent
                assert parent
            found = parent.find_sym(name)
            return found
        else:
            if name in builtin_symbols:
                return builtin_symbols[name]
        return None

    def find_scope_sym(self, obj, rec=True):
        results = SymbolTable.find_scope_sym(self, obj)
        if rec:
            for c in self.children:
                results.extend(c.find_scope_sym(obj, True))
        return results

    def find_syms_by_tags(self, tags: set[str]) -> set[Symbol]:
        return SymbolTable.find_syms_by_tags(self, tags)

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
        if self.entry_block:
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

    def add_param(self, sym:Symbol, defval:IRExp|None):
        self.function_params.add_param(sym, defval)

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

    def is_descendants_of(self, other):
        if self.parent is None:
            return False
        elif self.parent is other:
            return True
        return self.parent.is_descendants_of(other)

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

    def register_worker(self, worker_scope):
        for i, w in enumerate(self.workers[:]):
            if w is worker_scope:
                self.workers.pop(i)
        self.workers.append(worker_scope)
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

    def closures(self):
        clos = []
        for child in self.children:
            if child.is_closure():
                clos.append(child)
            clos.extend(child.closures())
        return clos

    def instance_number(self):
        n = Scope.instance_ids[self]
        Scope.instance_ids[self] += 1
        return n

    def build_module_params(self, module_param_vars: list[tuple[str, IRExp]]):
        module_params = []
        ctor = self.find_ctor()
        assert ctor
        param_names = ctor.param_names(with_self=True)
        for i, name in enumerate(param_names):
            if name.isupper():
                module_params.append(ctor.function_params._params[i])
        for sym, _ in module_params:
            ctor.function_params.remove(sym)
        self.module_param_vars = module_param_vars
        self.module_params = module_params

    def set_bound_args(self, binding: list[tuple[int, IRExp]]):
        self._bound_args = [str(exp) for i, exp in binding]


class NameReplacer(IRVisitor):
    def __init__(self, name_sym_map: dict[str, Symbol]):
        super().__init__()
        self.name_sym_map = name_sym_map

    def visit_TEMP(self, ir):
        if ir.name in self.name_sym_map:
            ir.name = self.name_sym_map[ir.name].name

    def visit_ATTR(self, ir):
        self.visit(ir.exp)


def function2method(func_scope, class_scope):
    assert func_scope.is_function()
    assert class_scope.is_class()
    assert func_scope.parent is class_scope
    func_scope.add_tag('method')
    func_scope.del_tag('function')
    self_sym = func_scope.add_sym('self', {'self'}, typ=Type.object(class_scope.name))
    params = FunctionParams(True)
    params.add_param(self_sym, None)
    for psym, defval in zip(func_scope.param_symbols(), func_scope.param_default_values()):
        params.add_param(psym, defval)
    func_scope.function_params = params


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
            s += str(stm).replace('\n', r'\l') + r'\l'
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
