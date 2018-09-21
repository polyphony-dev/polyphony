from collections import deque, defaultdict
from .ir import *
from .type import Type
from .irvisitor import IRVisitor
from .env import env
from .scope import Scope
from .utils import replace_item
from logging import getLogger
logger = getLogger(__name__)


class RefNode(object):
    PARAM = 0x00000001

    def __init__(self, sym, scope):
        self.sym = sym
        self.scope = scope
        self.preds = []
        self.succs = []
        self.order = -1
        self.flags = 0
        self.ancestor = None

    def __str__(self):
        scope_name = self.scope.name
        s = '{}: {} {} {}\n'.format(self.__class__.__name__,
                                    self.sym.name,
                                    scope_name,
                                    self._str_properties())
        s += '\tpreds\n'
        s += '\t\t' + ', '.join(['{}'.format(pred.sym) for pred in self.preds])
        s += '\n'
        s += '\tsuccs\n'
        s += '\t\t' + ', '.join(['{}'.format(succ.sym) for succ in self.succs])
        s += '\n'
        return s

    def __repr__(self):
        return self.sym.name

    def __lt__(self, other):
        return self.sym < other.sym

    def __eq__(self, other):
        if self is other:
            return True
        return self.is_clone_of(other) or other.is_clone_of(self)

    def __hash__(self):
        return super().__hash__()

    def name(self):
        if self.scope.is_worker() or self.scope.is_method():
            return self.scope.orig_name + '_' + self.sym.hdl_name()
        else:
            return self.sym.hdl_name()

    def _str_properties(self):
        return ''

    def add_pred(self, pred):
        if not self.preds:
            self.preds.append(pred)

    def add_succ(self, succ):
        if not self.succs:
            self.succs.append(succ)

    def propagate_preds(self, fn):
        fn(self)
        for s in self.preds:
            s.propagate_preds(fn)

    def propagate_succs(self, fn):
        fn(self)
        for s in self.succs:
            s.propagate_succs(fn)

    def pred_ref_nodes(self):
        pass

    def succ_ref_nodes(self):
        pass

    def pred_branch(self):
        if not self.preds:
            return None
        if len(self.preds) > 1:
            return self
        else:
            return self.preds[0].pred_branch()

    def is_source(self):
        return not self.preds

    def is_sink(self):
        return not self.succs

    def is_joinable(self):
        branch = self.pred_branch()
        if branch is None:
            return False
        if self.scope in set([p.scope for p in branch.preds]):
            return True
        return False

    def is_successor(self, node):
        if node in self.succs:
            return True
        else:
            for succ in self.succs:
                if succ.is_successor(node):
                    return True
        return False

    def is_in_scope(self, scope):
        return scope is self.scope

    def is_clone_of(self, node):
        return self.ancestor is node

    def sources(self):
        if not self.preds:
            yield self
        for pred in self.preds:
            yield from pred.sources()

    def sinks(self):
        if not self.succs:
            yield self
        for succ in self.succs:
            yield from succ.sinks()

    def single_source(self):
        sources = [source for source in self.sources()]
        if len(sources) > 1:
            return None
        return sources[0]

    def update(self):
        pass

    def add_flag(self, f):
        self.flags |= f

    def clone(self, orig_scope, new_scope):
        assert self.sym.scope is orig_scope
        new_sym = new_scope.cloned_symbols[self.sym]
        new_node = self.__class__(new_sym, new_scope)
        self._clone_data(new_node)
        new_node.ancestor = self
        return new_node

    def _clone_data(self, new_node):
        new_node.preds = self.preds[:]
        new_node.succs = self.succs[:]
        new_node.flags = self.flags
        new_node.order = self.order


class JointNode(RefNode):
    def __init__(self, sym, scope):
        super().__init__(sym, scope)

    def __hash__(self):
        return super().__hash__()

    def add_pred(self, pred):
        if pred not in self.preds:
            self.preds.append(pred)

    def add_succ(self, succ):
        if succ not in self.succs:
            self.succs.append(succ)

    def pred_ref_nodes(self):
        preds = []
        for pred in self.preds:
            if isinstance(pred, JointNode):
                preds.extend(pred.pred_ref_nodes())
            else:
                preds.append(pred)
        return preds

    def succ_ref_nodes(self):
        succs = []
        for succ in self.succs:
            if isinstance(succ, JointNode):
                succs.extend(succ.succ_ref_nodes())
            else:
                succs.append(succ)
        return succs


class N2OneNode(JointNode):
    def __init__(self, sym, succ):
        super().__init__(sym, sym.scope)
        if succ:
            self.succs = [succ]

    def __hash__(self):
        return super().__hash__()

    def pred_ref_nodes(self):
        assert len(self.preds) > 1
        return super().pred_ref_nodes()

    def succ_ref_nodes(self):
        assert len(self.succs) == 1
        return super().succ_ref_nodes()

    def is_in_scope(self, scope):
        return scope in [p.scope for p in self.preds]

    def clone(self, orig_scope, new_scope):
        assert self.sym.scope is orig_scope
        new_sym = new_scope.cloned_symbols[self.sym]
        new_node = self.__class__(new_sym, None)
        self._clone_data(new_node)
        new_node.ancestor = self
        return new_node


class One2NNode(JointNode):
    def __init__(self, sym, pred):
        super().__init__(sym, sym.scope)
        if pred:
            self.preds = [pred]

    def __hash__(self):
        return super().__hash__()

    def pred_ref_nodes(self):
        assert len(self.preds) == 1
        return super().pred_ref_nodes()

    def succ_ref_nodes(self):
        assert len(self.succs) > 1
        return super().succ_ref_nodes()

    def clone(self, orig_scope, new_scope):
        assert self.sym.scope is orig_scope
        new_sym = new_scope.cloned_symbols[self.sym]
        new_node = self.__class__(new_sym, None)
        self._clone_data(new_node)
        new_node.ancestor = self
        return new_node


class MemTrait(object):
    WR      = 0x00010000
    IM      = 0x00020000
    PURE    = 0x00040000
    ALIAS   = 0x00080000
    USELESS = 0x00100000
    SWITCH  = 0x00200000

    def __init__(self):
        self.length = -1

    def set_writable(self):
        self.flags |= MemTrait.WR

    def set_immutable(self):
        self.flags |= MemTrait.IM

    def set_pure(self):
        self.flags |= MemTrait.PURE

    def set_alias(self):
        self.flags |= MemTrait.ALIAS

    def set_useless(self):
        self.flags |= MemTrait.USELESS

    def set_switch(self):
        self.flags |= MemTrait.SWITCH

    def set_length(self, length):
        self.length = length

    def is_writable(self):
        return self.flags & MemTrait.WR

    def is_immutable(self):
        return self.flags & MemTrait.IM

    def is_pure(self):
        return self.flags & MemTrait.PURE

    def is_alias(self):
        return self.flags & MemTrait.ALIAS

    def is_useless(self):
        return self.flags & MemTrait.USELESS

    def is_switch(self):
        return self.flags & MemTrait.SWITCH

    def data_width(self):
        if self.sym.typ.has_element():
            elem_t = self.sym.typ.get_element()
            if elem_t.has_width():
                return elem_t.get_width()
        return env.config.default_int_width

    def addr_width(self):
        return (self.length - 1).bit_length() + 1  # +1 means sign bit

    def can_be_reg(self):
        if self.length == -1:
            src = self.single_source()
            if src:
                self.length = src.length
        if self.is_useless():
            return False
        assert self.length > 0
        if not self.is_writable():
            return False
        if self.is_immutable():
            return False
        return (self.data_width() * self.length) < env.config.internal_ram_threshold_size


class MemRefNode(RefNode, MemTrait):
    def __init__(self, sym, scope):
        RefNode.__init__(self, sym, scope)
        MemTrait.__init__(self)
        self.initstm = None

    def __hash__(self):
        return super().__hash__()

    def _str_properties(self):
        s = ' <{}>[{}] '.format(self.data_width(), self.length)
        s += 'wr ' if self.is_writable() else 'ro '
        s += 'alias ' if self.is_alias() else ''
        s += 'useless ' if self.is_useless() else ''
        if self.initstm:
            s += 'initstm={} '.format(self.initstm)
        return s

    def set_initstm(self, initstm):
        assert initstm
        assert initstm.is_a(MOVE) and initstm.src.is_a(ARRAY)
        self.initstm = initstm

    def is_source(self):
        return self.initstm

    def is_param(self):
        return False

    def is_direct_accessor(self):
        return len(self.preds) == 1 and isinstance(self.preds[0], MemRefNode)

    def pred_ref_nodes(self):
        if self.preds:
            assert len(self.preds) == 1
            pred = self.preds[0]
            if isinstance(pred, MemRefNode):
                return [pred]
            else:
                return pred.pred_ref_nodes()
        else:
            return []

    def succ_ref_nodes(self):
        if self.succs:
            assert len(self.succs) == 1
            succ = self.succs[0]
            if isinstance(succ, MemRefNode):
                return [succ]
            else:
                return succ.succ_ref_nodes()
        else:
            return []

    def update(self):
        if self.initstm:
            assert self.initstm.is_a(MOVE) and self.initstm.src.is_a(ARRAY)
            self.length = self.initstm.src.getlen()

        if self.preds and self.length < self.preds[0].length:
            self.length = self.preds[0].length

        if self.preds and self.preds[0].is_immutable():
            self.set_immutable()

    def clone(self, orig_scope, new_scope):
        c = super().clone(orig_scope, new_scope)
        c.initstm = self.initstm
        c.length = self.length
        return c


class MemParamNode(RefNode, MemTrait):
    def __init__(self, sym, scope):
        RefNode.__init__(self, sym, scope)
        MemTrait.__init__(self)

    def __hash__(self):
        return super().__hash__()

    def _str_properties(self):
        s = ' <{}>[{}] '.format(self.data_width(), self.length)
        s += 'wr ' if self.is_writable() else 'ro '
        return s

    def is_source(self):
        return False

    def is_param(self):
        return True

    def is_direct_accessor(self):
        return len(self.preds) == 1 and isinstance(self.preds[0], MemRefNode)

    def pred_ref_nodes(self):
        if self.preds:
            assert len(self.preds) == 1
            pred = self.preds[0]
            if isinstance(pred, MemRefNode):
                return [pred]
            else:
                return pred.pred_ref_nodes()
        else:
            return []

    def succ_ref_nodes(self):
        if self.succs:
            assert len(self.succs) == 1
            succ = self.succs[0]
            if isinstance(succ, MemRefNode):
                return [succ]
            else:
                return succ.succ_ref_nodes()
        else:
            return []

    def update(self):
        if self.preds and self.length < self.preds[0].length:
            self.length = self.preds[0].length

        if self.preds[0].is_immutable():
            self.set_immutable()


class N2OneMemNode(N2OneNode, MemTrait):
    def __init__(self, sym, succ):
        N2OneNode.__init__(self, sym, succ)
        MemTrait.__init__(self)

    def __hash__(self):
        return super().__hash__()

    def _str_properties(self):
        s = ' <{}>[{}] '.format(self.data_width(), self.length)
        s += 'wr ' if self.is_writable() else 'ro '
        return s

    def update(self):
        self.length = max([p.length for p in self.preds])
        self.preds = sorted(self.preds)

        if self.preds[0].is_immutable():
            self.set_immutable()


class One2NMemNode(One2NNode, MemTrait):
    def __init__(self, sym, pred):
        One2NNode.__init__(self, sym, pred)
        MemTrait.__init__(self)

    def __hash__(self):
        return super().__hash__()

    def _str_properties(self):
        s = ' <{}>[{}] '.format(self.data_width(), self.length)
        s += 'wr ' if self.is_writable() else 'ro '
        return s

    def update(self):
        self.succs = sorted(self.succs)

        if self.preds and self.length < self.preds[0].length:
            self.length = self.preds[0].length

        if self.preds[0].is_immutable():
            self.set_immutable()


class MemRefGraph(object):
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.param_node_instances = defaultdict(set)
        self.removed_nodes = {}

    def __str__(self):
        s = 'MemRefGraph\n'
        for node in self.sorted_nodes():
            s += str(node)
        for param_node, inst_names in self.param_node_instances.items():
            assert len(param_node.preds) == 1
            pred = param_node.preds[0]
            for inst_name in inst_names:
                s += '{} => {}:{}\n'.format(pred.sym, inst_name, param_node.sym)
        return s

    def sorted_nodes(self):
        def set_order(node, order):
            if order > node.order:
                node.order = order
            order += 1
            for succ in [succ for succ in node.succs]:
                set_order(succ, order)

        for node in self.nodes.values():
            node.order = -1
        for source in self.collect_sources():
            set_order(source, 0)
        return sorted(self.nodes.values(), key=lambda n: n.order)

    def add_node(self, node):
        if isinstance(node, list):
            for n in node:
                self.add_node(n)
        else:
            logger.debug('add_node ' + str(node))
            self.nodes[node.sym] = node

    def node(self, sym):
        if sym in self.nodes:
            return self.nodes[sym]
        return None

    def add_edge(self, src, dst):
        assert src and dst
        assert src is not dst
        src.add_succ(dst)
        dst.add_pred(src)
        self.edges[(src.sym, dst.sym)] = (src, dst)

    def add_param_node_instance(self, param_node, inst_name):
        self.param_node_instances[param_node].add(inst_name)

    def remove_node(self, node):
        if node.sym in self.removed_nodes:
            return
        if isinstance(node, list):
            for n in node:
                self.remove_node(n)
        else:
            logger.debug('remove_node ' + str(node.sym))
            for pred in node.preds:
                pred.succs.remove(node)
                if not pred.succs:
                    self.remove_node(pred)
                elif isinstance(pred, One2NMemNode) and len(pred.succs) == 1:
                    pred.preds[0].succs.append(pred.succs[0])
                    pred.succs[0].preds.append(pred.preds[0])
                    self.remove_node(pred)
            for succ in node.succs:
                succ.preds.remove(node)
                if not succ.preds:
                    self.remove_node(suc)
                elif isinstance(succ, N2OneMemNode) and len(succ.preds) == 1:
                    succ.preds[0].succs.append(succ.succs[0])
                    succ.succs[0].preds.append(succ.preds[0])
                    self.remove_node(pred)
            del self.nodes[node.sym]
            self.removed_nodes[node.sym] = node

    def collect_sources(self):
        for node in self.nodes.values():
            if node.is_source():
                assert not node.preds
                assert isinstance(node, MemRefNode)
                yield node

    def scope_nodes(self, scope):
        return filter(lambda n: n.is_in_scope(scope), self.nodes.values())

    def scope_nodes_with_removed(self, scope):
        nodes = set(self.nodes.values()) | set(self.removed_nodes.values())
        return filter(lambda n: n.is_in_scope(scope), nodes)

    def collect_ram(self, scope):
        for node in self.scope_nodes(scope):
            if node.is_writable() and not node.is_immutable():
                yield node

    def collect_immutable(self, scope):
        for node in self.scope_nodes(scope):
            if node.is_immutable():
                yield node

    def is_readonly_sink(self, node):
        return isinstance(node, MemRefNode) and not node.is_writable() and node.is_sink() and not node.is_useless()

    def collect_joint(self, scope):
        for node in self.scope_nodes(scope):
            if isinstance(node, JointNode):
                yield node

    def collect_top_module_nodes(self):
        for node in self.nodes.values():
            if node.scope.is_testbench():
                for succ in node.succ_ref_nodes():
                    yield succ

    def find_nearest_single_source(self, node):
        def _find_pred_single_out(n):
            if isinstance(n, N2OneNode):
                return n
            if len(n.succs) == 1:
                return n
            if len(n.preds) == 1:
                return _find_pred_single_out(n.preds[0])
            return None
        return _find_pred_single_out(node)

    def verify_nodes(self):
        for node in self.nodes.values():
            assert node.scope

    def is_path_exist(self, frm, to):
        for succ in frm.succs:
            if succ is to:
                return True
            if self.is_path_exist(succ, to):
                return True
        return False

    def is_live_node(self, node):
        return node.sym in self.nodes

    def clone_subgraph(self, orig, new):
        def replace_connection(new_node, nodes, node_map, with_edge, is_succ=True):
            for i, n in enumerate(nodes.copy()):
                if n in node_map:
                    new_n = node_map[n]
                    nodes[i] = new_n
                    n = new_n
                if with_edge:
                    if is_succ:
                        self.edges[(new_node.sym, n.sym)] = (new_node, n)
                    else:
                        self.edges[(n.sym, new_node.sym)] = (n, new_node)

        #assert new.cloned_symbols
        new_nodes = []
        node_map = {}
        for node in self.scope_nodes(orig):
            if node.sym.scope is orig:
                new_node = node.clone(orig, new)
                assert new_node.sym is not node.sym
                assert new_node.sym.name == node.sym.name
                new_nodes.append(new_node)
                node_map[node] = new_node
            else:
                # The node might be a shared (in global or class scope) node
                node_map[node] = node
        for new_node in new_nodes:
            if isinstance(new_node, MemRefNode) and new_node.initstm:
                new_node.initstm = new.cloned_stms[new_node.initstm]
            self.add_node(new_node)
            replace_connection(new_node, new_node.succs, node_map, True, is_succ=True)
            replace_connection(new_node, new_node.preds, node_map, True, is_succ=False)
        return node_map


class MemRefGraphBuilder(IRVisitor):
    def __init__(self):
        super().__init__()
        if env.memref_graph is None:
            env.memref_graph = MemRefGraph()
        self.mrg = env.memref_graph
        self.edges = []
        self.edge_srcs = defaultdict(set)

    def _collect_def_mem_stms(self, scope):
        stms = []
        for block in scope.traverse_blocks():
            for stm in block.stms:
                if stm.is_a(MOVE):
                    if stm.src.is_a(ARRAY):
                        stms.append(stm)
                    elif (stm.src.is_a(TEMP) and
                          stm.src.sym.is_param() and
                          stm.src.sym.typ.is_seq()):
                        stms.append(stm)
        for block in scope.traverse_blocks():
            for stm in block.stms:
                # phi is always
                if stm.is_a(MOVE):
                    if (stm.dst.is_a([TEMP, ATTR]) and
                            stm.dst.symbol().typ.is_seq() and
                            stm not in stms):
                        stms.append(stm)
                elif stm.is_a(PHIBase):
                    if stm.var.is_a(TEMP) and stm.var.sym.typ.is_seq():
                        stms.append(stm)
        return stms

    def process_all(self, driver):
        scopes = Scope.get_scopes(bottom_up=False, with_global=True, with_class=True)
        worklist = deque()
        #usedefs = [s.usedef for s in scopes]
        for s in scopes:
            if s.is_ctor():
                listtypes = [f for f in s.parent.class_fields().values() if f.typ.is_seq()]
                if listtypes:
                    pass

            usedef = s.usedef
            if not usedef:
                continue
            # collect the access to a local list variable
            stms = self._collect_def_mem_stms(s)
            worklist.extend(stms)
            for stm in stms:
                logger.debug('!!! mem def stm ' + str(stm))
                if stm.is_a(MOVE):
                    memsym = stm.dst.symbol()
                elif stm.is_a(PHIBase):
                    memsym = stm.var.sym

                uses = usedef.get_stms_using(memsym)
                uses = uses.difference(set(worklist))
                worklist.extend(list(uses))
            # collect the access to a global list variable
            for sym in usedef.get_all_use_syms():
                if (sym.scope.is_namespace() or sym.scope.is_class()) and sym.typ.is_seq():
                    uses = usedef.get_stms_using(sym)
                    worklist.extend(list(uses))

        while worklist:
            stm = worklist.popleft()
            self.scope = stm.block.scope
            self.visit(stm)

        self._reconnect_alias_edge()
        # create joint node
        n2one_node_map = {}
        one2n_node_map = {}
        for src_sym, dst_sym in reversed(self.edges):
            src = self.mrg.node(src_sym)
            dst = self.mrg.node(dst_sym)
            if dst not in n2one_node_map:
                n2one_node_map[dst] = self._make_n2o(dst)
            n2one_node_map[dst].add_pred(src)

            if src not in one2n_node_map:
                one2n_node_map[src] = self._make_o2n(src)
            one2n_node_map[src].add_succ(dst)

        # connect nodes
        for src, one2n in one2n_node_map.items():
            if len(one2n.succs) == 1:
                # this src is unidirectional
                dst = one2n.succs.pop()
                n2one = n2one_node_map[dst]
                if len(n2one.preds) == 1:
                    # direct connect
                    dst.add_pred(src)
                    src.add_succ(dst)
                else:
                    dst.add_pred(n2one)
                    src.add_succ(n2one)
                    self.mrg.add_node(n2one)
            else:
                # this src is multidirectional
                for dst in one2n.succs:
                    n2one = n2one_node_map[dst]
                    if len(n2one.preds) == 1:
                        dst.add_pred(one2n)
                        src.add_succ(one2n)
                        self.mrg.add_node(one2n)
                    else:
                        dst.add_pred(n2one)
                        src.add_succ(one2n)
                        replace_item(one2n.succs, dst, n2one)
                        replace_item(n2one.preds, src, one2n)
                        self.mrg.add_node(n2one)
                        self.mrg.add_node(one2n)
        self._propagate_info()
        self._mark_useless_node()
        self._reduce_useless_node()
        # do a ref-to-ref node branching
        self._do_ref_2_ref_node_branching()
        self.mrg.verify_nodes()
        self._propagate_info()

    def _make_n2o(self, succ):
        sym = succ.scope.add_temp('n2o_' + succ.sym.hdl_name())
        return N2OneMemNode(sym, succ)

    def _make_o2n(self, pred):
        sym = pred.scope.add_temp('o2n_' + pred.sym.hdl_name())
        return One2NMemNode(sym, pred)

    def _reconnect_alias_edge(self):
        # TODO: fix alias reference cycle
        prev_new_edges = []
        while True:
            dst2src_map = defaultdict(list)
            for src, dst in self.edges:
                dst2src_map[dst].append(src)

            new_edges = []
            removed_indices = []
            for i, (src, dst) in enumerate(self.edges):
                src_node = self.mrg.node(src)
                if not isinstance(src_node, MemRefNode):
                    continue
                if not src_node.is_alias():
                    continue
                srcsrcs = dst2src_map[src]
                removed_indices.append(i)
                for srcsrc in srcsrcs:
                    if srcsrc is dst:
                        continue
                    srcsrc_node = self.mrg.node(srcsrc)
                    if isinstance(srcsrc_node, MemRefNode) and srcsrc_node.is_alias():
                        continue
                    new_edges.append((srcsrc, dst))
            for i in reversed(removed_indices):
                self.edges.pop(i)
            if new_edges and (set(new_edges) - set(prev_new_edges)):
                self.edges = list(set(self.edges) | set(new_edges))
                prev_new_edges = new_edges.copy()
            else:
                break

    def _mark_useless_node(self):
        for node in self.mrg.sorted_nodes():
            if not isinstance(node, MemRefNode):
                continue
            if node.is_source():
                continue
            if len(node.preds) == 1 and node.preds[0].is_source():
                continue
            if len(node.preds) == 1 and isinstance(node.preds[0], MemParamNode):
                continue
            if node.sym.is_static():
                continue
            if node.is_switch():
                continue
            usestms = node.scope.usedef.get_stms_using(node.sym)
            for usestm in usestms:
                if usestm.is_mem_read() or usestm.is_mem_write():
                    break
                if usestm.is_a(MOVE) and usestm.src.is_a(SYSCALL) and usestm.src.sym.name == 'len':
                    break
            else:
                node.set_useless()

    def _reduce_useless_node(self):
        for node in self.mrg.sorted_nodes():
            if node.is_useless():
                for p in node.preds:
                    p.succs.extend(node.succs)
                for s in node.succs:
                    s.preds.extend(node.preds)
                self.mrg.remove_node(node)

    def _do_ref_2_ref_node_branching(self):
        new_nodes = []
        for node in self.mrg.sorted_nodes():
            if (isinstance(node, MemRefNode) and
                    not node.is_source() and
                    not node.is_param() and
                    not node.is_useless() and
                    node.succs):
                assert len(node.preds) == 1
                assert len(node.succs) == 1

                if isinstance(node.succs[0], One2NMemNode):
                    o2n = node.succs[0]
                    o2n.add_succ(node)
                    replace_item(o2n.preds, node, node.preds[0])
                    replace_item(node.preds[0].succs, node, o2n)
                else:
                    pred = node.preds[0]
                    o2n = self._make_o2n(pred)
                    o2n.add_succ(node)
                    for succ in node.succs:
                        o2n.add_succ(succ)
                        replace_item(succ.preds, node, o2n)
                    replace_item(pred.succs, node, o2n)
                    new_nodes.append(o2n)
                node.preds[0] = o2n
                node.succs = []
                assert node.is_sink()
        for n in new_nodes:
            self.mrg.add_node(n)

    def _propagate_info(self):
        for source in [s for s in self.mrg.collect_sources()]:
            source.propagate_succs(lambda n: n.update())

    def _append_edge(self, src, dst):
        assert src
        assert dst
        self.edge_srcs[dst].add(src)
        if (src, dst) not in self.edges:
            self.edges.append((src, dst))

    def _set_type(self, sym, typ):
        if not sym.typ.is_freezed():
            sym.set_type(typ)
        else:
            sym.typ = typ

    def _set_memnode(self, typ, memnode):
        if typ.get_memnode() is None:
            typ.set_memnode(memnode)
        else:
            assert typ.get_memnode() is memnode
        typ.freeze()

    def visit_CALL(self, ir):
        for i, (_, arg) in enumerate(ir.args):
            if arg.is_a(TEMP) and arg.sym.typ.is_seq():
                p, _, _ = ir.func_scope().params[i]
                self._append_edge(arg.sym, p)
                if ir.func_scope().is_pure():
                    purenode = MemParamNode(p, ir.func_scope())
                    self.mrg.add_node(purenode)
                    purenode.set_pure()

    def visit_TEMP(self, ir):
        if not ir.sym.typ.is_seq():
            return
        self._visit_seq_var(ir.sym)

    def visit_ATTR(self, ir):
        if not ir.attr.typ.is_seq():
            return
        self._visit_seq_var(ir.attr)

    def _visit_seq_var(self, memsym):
        if memsym.is_param():
            self.mrg.add_node(MemParamNode(memsym, memsym.scope))
            memnode = self.mrg.node(memsym)
            memnode.set_switch()
            self._set_memnode(memsym.typ, memnode)
        else:
            memnode = self.mrg.node(memsym)
            if not memnode:
                memnode = MemRefNode(memsym, memsym.scope)
                self.mrg.add_node(memnode)
                self._set_memnode(memsym.typ, memnode)
            if memsym.is_static():
                root = memsym.root_sym()
                if root and root.scope is not memsym.scope:
                    rootnode = self.mrg.node(root)
                    if not rootnode:
                        rootnode = MemRefNode(root, root.scope)
                        self.mrg.add_node(rootnode)
                        self._set_memnode(root.typ, rootnode)
                    self._append_edge(root, memsym)

    def visit_ARRAY(self, ir):
        memnode = MemRefNode(ir.sym, ir.sym.scope)
        self.mrg.add_node(memnode)
        memnode.set_initstm(self.current_stm)
        if not all(item.is_a(CONST) for item in ir.items):
            memnode.set_writable()
        if not ir.is_mutable:
            memnode.set_immutable()
        self._set_memnode(ir.sym.typ, memnode)

    def visit_MSTORE(self, ir):
        memsym = ir.mem.symbol()
        memnode = self.mrg.node(memsym)
        if memnode:
            memnode.set_writable()
        else:
            assert False

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

    def visit_RET(self, ir):
        self.visit(ir.exp)

    def visit_MOVE(self, ir):
        self.visit(ir.src)
        self.visit(ir.dst)

        memsym = ir.dst.symbol()
        if memsym.typ.is_seq():
            memnode = self.mrg.node(memsym)
            assert memnode
            if ir.src.is_a(TEMP):
                self._append_edge(ir.src.sym, memsym)
                if not ir.src.sym.is_param():
                    memnode.set_alias()
                    memnode.set_switch()
            elif ir.src.is_a(ARRAY):
                self._append_edge(ir.src.sym, memsym)
            elif ir.src.is_a(CONDOP):
                self._append_edge(ir.src.left.symbol(), memsym)
                self._append_edge(ir.src.right.symbol(), memsym)
            elif ir.src.is_a(ATTR) and ir.src.attr.typ.is_seq():
                assert 0

            if ir.src.is_a(CALL) and ir.src.func_scope().is_pure():
                ret_sym = ir.src.func_scope().add_temp('@pure_return')
                ret_sym.set_type(memsym.typ.clone())
                self._append_edge(ret_sym, ir.dst.symbol())
                # this node is for inlining sequence values
                # hence the scope must be self.scope
                purenode = MemRefNode(ret_sym, ret_sym.scope)
                self.mrg.add_node(purenode)
                purenode.set_pure()
                assert memsym.typ.has_length()
                purenode.length = memsym.typ.get_length()
                purenode.is_source = lambda : True

    def visit_PHI(self, ir):
        if ir.var.sym.typ.is_seq():
            memnode = self.mrg.node(ir.var.sym)
            if not memnode:
                memnode = MemRefNode(ir.var.sym, ir.var.sym.scope)
                self.mrg.add_node(memnode)
            for arg in ir.args:
                self.visit(arg)
                self._append_edge(arg.sym, ir.var.sym)
            memnode.set_alias()
            self._set_memnode(ir.var.sym.typ, memnode)

    def visit_UPHI(self, ir):
        self.visit_PHI(ir)

    def visit_LPHI(self, ir):
        self.visit_PHI(ir)
        memnode = self.mrg.node(ir.var.sym)
        memnode.set_switch()


class MemInstanceGraphBuilder(object):
    def __init__(self):
        self.mrg = env.memref_graph

    def process(self, scope):
        self.scope = scope
        for dfg in scope.dfgs(bottom_up=False):
            for node in dfg.get_scheduled_nodes():
                self.visit(node.tag, node)

    def visit_CALL(self, ir, node):
        func_name = ir.func.symbol().orig_name()
        inst_name = '{}_{}'.format(func_name, node.instance_num)

        for i, (_, arg) in enumerate(ir.args):
            assert arg.is_a([TEMP, ATTR, CONST, UNOP, ARRAY])
            if arg.is_a(TEMP) and arg.sym.typ.is_seq():
                p, _, _ = ir.func_scope().params[i]
                assert p.typ.is_seq()
                param_node = p.typ.get_memnode()
                # param memnode might be removed in the rom elimination of ConstantFolding
                if self.mrg.is_live_node(param_node):
                    self.mrg.add_param_node_instance(param_node, inst_name)

    def visit_EXPR(self, ir, node):
        self.visit(ir.exp, node)

    def visit_CJUMP(self, ir, node):
        self.visit(ir.exp, node)

    def visit_JUMP(self, ir, node):
        pass

    def visit_MCJUMP(self, ir, node):
        for i, c in enumerate(ir.conds):
            self.visit(c, node)

    def visit_RET(self, ir, node):
        pass

    def visit_MOVE(self, ir, node):
        self.visit(ir.src, node)

    def visit_PHI(self, ir, node):
        pass

    def visit(self, ir, node):
        method = 'visit_' + ir.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(ir, node)
