from collections import defaultdict, deque
from ..ir import *
from ..irhelper import is_port_method_call, has_exclusive_function, has_clkfence, qualified_symbols
from ..symbol import Symbol
from ..analysis.usedef import UseDefDetector
from ...common.env import env
from ...common import utils
from logging import getLogger
logger = getLogger(__name__)


def _find_stm_index(stm, scope=None):
    """Find index of stm in its block's stms list, handling MStm children."""
    from ...common.utils import find_id_index
    from ...common.env import env
    if scope:
        blk = scope.find_block(stm.block)
    else:
        # Search all scopes for the block
        for s in env.scopes.values():
            if stm.block in s.block_map:
                blk = s.block_map[stm.block]
                break
        else:
            return -1
    idx = find_id_index(blk.stms, stm)
    if idx == -1:
        for i, s in enumerate(blk.stms):
            if isinstance(s, MStm) and any(id(c) == id(stm) for c in s.stms):
                return i
    return idx


class DFNode(object):
    def __init__(self, typ, tag):
        self.typ = typ  # 'Stm', 'Loop', 'Block'
        self.tag = tag
        self._nid = -1  # assigned by DataFlowGraph.add_stm_node
        self.priority = -1  # 0 is highest priority
        self.begin = -1
        self.end = -1
        if typ == 'Stm':
            self.stm_index = _find_stm_index(tag)
        else:
            self.stm_index = 0
        self.instance_num = 0
        self.uses = []
        self.defs = []

    def __str__(self):
        if self.typ == 'Stm':
            s = '<{}> ({}) {} {}:{} {}'.format(
                self._nid,
                self.tag.loc.lineno if self.tag.loc else 0,
                self.priority,
                self.begin,
                self.end,
                self.tag
            )
            #s += ' ' + self.tag.block.name
        elif self.typ == 'Loop':
            s = 'Node {} {} {}:{} Loop {}'.format(
                self._nid,
                self.priority,
                self.begin,
                self.end,
                self.tag.name
            )
        elif self.typ == 'Block':
            s = 'Node {} {} {}:{} Block'.format(
                self._nid,
                self.priority,
                self.begin,
                self.end
            )
        else:
            assert False
        return s

    def __repr__(self):
        return str(self)

    def __lt__(self, other):
        if self.begin == other.begin:
            if self.priority == other.priority:
                return self._nid < other._nid
            return self.priority < other.priority
        return self.begin < other.begin

    def latency(self):
        return self.end - self.begin


class DataFlowGraph(object):
    def __init__(self, scope, name, parent, region):
        self.scope = scope
        self.name = name
        self.region = region
        #self.blocks = blocks
        self.nodes = []
        self.edges = {}
        self.succ_edges = defaultdict(set)
        self.pred_edges = defaultdict(set)
        self.src_nodes = set()
        self.parent = parent
        if parent:
            parent.set_child(self)
        self.children = []
        self.synth_params = region.head.synth_params

    def __str__(self):
        s = 'DFG all nodes ==============\n'
        for n in sorted(self.nodes, key=lambda n: n._nid):
            s += '  ' + str(n)
            s += '\n'
        s += 'DFG all edges ==============\n'
        for (n1, n2), (typ, back) in sorted(self.edges.items(), key=lambda e: (e[0][0]._nid, e[0][1]._nid)):
            back_edge = "(back) " if back else ''
            if typ == 'DefUse':
                prefix1 = 'def '
                prefix2 = '  -> use '
            elif typ == 'UseDef':
                prefix1 = 'use '
                prefix2 = '  -> def '
            elif typ == 'Seq':
                prefix1 = 'pred '
                prefix2 = '  -> succ '
            else:
                prefix1 = 'sync '
                prefix2 = '<- -> '
            s += '{}{} {}\n'.format(back_edge, prefix1, n1)
            s += '{}{} {}\n'.format(back_edge, prefix2, n2)
        return s

    def set_child(self, child):
        self.children.append(child)
        assert child.parent is self

    def add_stm_node(self, stm):
        n = self.find_node(stm)
        if not n:
            n = DFNode('Stm', stm)
            n._nid = len(self.nodes)
            self.nodes.append(n)
        return n

    def remove_node(self, n):
        self.nodes.remove(n)

    def add_defuse_edge(self, n1, n2):
        self.add_edge('DefUse', n1, n2)

    def add_usedef_edge(self, n1, n2):
        self.add_edge('UseDef', n1, n2)

    def add_seq_edge(self, n1, n2):
        assert n1 and n2 and n1.tag and n2.tag
        assert n1 is not n2
        assert not self.scope.has_branch_edge(n1.tag, n2.tag)

        if (n1, n2) not in self.edges:
            self._add_edge(n1, n2, 'Seq', False)
        else:
            _typ, _ = self.edges[(n1, n2)]
            if _typ != 'DefUse':
                # overwrite if existing edge type is 'UseDef'
                self._add_edge(n1, n2, 'Seq', False)

    def add_edge(self, typ, n1, n2):
        assert n1 and n2 and n1.tag and n2.tag
        assert n1 is not n2
        back = self._is_back_edge(n1, n2)
        if (n1, n2) not in self.edges:
            self._add_edge(n1, n2, typ, back)
        else:
            _typ, _back = self.edges[(n1, n2)]
            assert back is _back
            if typ == _typ or _typ == 'DefUse':
                return
            if typ == 'DefUse':
                self._add_edge(n1, n2, typ, back)

    def _add_edge(self, n1, n2, typ, back):
        self.edges[(n1, n2)] = (typ, back)
        edge = (n1, n2, typ, back)
        self.succ_edges[n1].add(edge)
        self.pred_edges[n2].add(edge)

    def remove_edge(self, n1, n2):
        typ, back = self.edges[n1, n2]
        del self.edges[(n1, n2)]
        edge = (n1, n2, typ, back)
        self.succ_edges[n1].remove(edge)
        self.pred_edges[n2].remove(edge)

    def _is_back_edge(self, n1, n2):
        return self._stm_order_gt(n1.tag, n2.tag)

    def _get_stm(self, node):
        return node.tag

    def _stm_order_gt(self, stm1, stm2):
        if stm1.block == stm2.block:
            return _find_stm_index(stm1, self.scope) > _find_stm_index(stm2, self.scope)
        else:
            return self.scope.find_block(stm1.block).order > self.scope.find_block(stm2.block).order

    def succs(self, node):
        succs = []
        for n1, n2, _, _ in self.succ_edges[node]:
            succs.append(n2)
        return succs

    def succs_without_back(self, node):
        succs = []
        for n1, n2, _, back in self.succ_edges[node]:
            if not back:
                succs.append(n2)
        return sorted(succs)

    def succs_typ(self, node, typ):
        succs = []
        for n1, n2, t, _ in self.succ_edges[node]:
            if typ == t:
                succs.append(n2)
        return succs

    def succs_typ_without_back(self, node, typ):
        succs = []
        for n1, n2, t, back in self.succ_edges[node]:
            if (typ == t) and (not back):
                succs.append(n2)
        return succs

    def preds(self, node):
        preds = []
        for n1, n2, _, _ in self.pred_edges[node]:
            preds.append(n1)
        return preds

    def preds_without_back(self, node):
        preds = []
        for n1, n2, _, back in self.pred_edges[node]:
            if not back:
                preds.append(n1)
        return preds

    def preds_typ(self, node, typ):
        preds = []
        for n1, n2, t, _ in self.pred_edges[node]:
            if typ == t:
                preds.append(n1)
        return preds

    def preds_typ_without_back(self, node, typ):
        preds = []
        for n1, n2, t, back in self.pred_edges[node]:
            if (typ == t) and (not back):
                preds.append(n1)
        return preds

    def find_node(self, stm):
        for node in self.nodes:
            if node.tag is stm:
                return node
        return None

    def find_src(self):
        return sorted(self.src_nodes, key=lambda n: n._nid)

    def find_sink(self):
        sink_nodes = []
        for node in self.nodes:
            if not self.succs(node):
                sink_nodes.append(node)
        return sink_nodes

    def trace_all_paths(self, trace_func):
        sources = [n for n in self.get_priority_ordered_nodes() if n.priority == 0]
        for src in sources:
            yield from self._trace_path(src, [], trace_func)

    def _trace_path(self, node, path, trace_func):
        path.append(node)
        next_nodes = utils.unique(trace_func(node))
        if not next_nodes:
            yield path
            return
        for nx in next_nodes:
            cur_path = path[:]
            yield from self._trace_path(nx, path, trace_func)
            path = cur_path

    def remove_unconnected_node(self):
        pass
        #self.nodes = list(filter(lambda n: n.succs or n.preds, self.nodes))

    def traverse_nodes(self, traverse_func, nodes, _):
        visited = set()
        queue = deque()
        queue.extend(nodes)
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            yield node
            next_nodes = utils.unique(traverse_func(node))
            queue.extend(next_nodes)

    def get_priority_ordered_nodes(self):
        return sorted(self.nodes, key=lambda n: n.priority)

    def get_highest_priority_nodes(self):
        return filter(lambda n: n.priority == 0, self.nodes)

    def get_lowest_timing(self):
        return max(self.nodes, key=lambda n: n.end)

    def get_scheduled_nodes(self):
        node_dict = defaultdict(list)
        for n in self.nodes:
            node_dict[self.scope.find_block(n.tag.block).num].append(n)
        result = []
        for ns in node_dict.values():
            result.extend(sorted(ns))
        return result

    def get_loop_nodes(self):
        return filter(lambda n: n.typ == 'Loop', self.nodes)

    def collect_all_preds(self, node):
        def collect_preds_rec(n, visited, results):
            preds = self.preds_without_back(n)
            for p in preds:
                if p in visited:
                    continue
                visited.add(p)
                results.append(p)
                collect_preds_rec(p, visited, results)
        visited = set()
        results = []
        collect_preds_rec(node, visited, results)
        return results

    def write_dot(self, name):
        try:
            import pydot  # type: ignore
        except ImportError:
            return
        # force disable debug mode to simplify the caption
        debug_mode = env.dev_debug_mode
        env.dev_debug_mode = False

        g = pydot.Dot(name, graph_type='digraph')

        def get_node_tag_text(node):
            s = str(node.tag)
            s = s.replace('\n', '\l') + '\l'
            s = s.replace(':', '_')
            #if len(s) > 50:
            #    return s[0:50]
            #else:
            return s

        node_map = {n: pydot.Node(get_node_tag_text(n), shape='box') for n in self.nodes}
        for n in node_map.values():
            g.add_node(n)

        for (n1, n2), (typ, back) in self.edges.items():
            dotn1 = node_map[n1]
            dotn2 = node_map[n2]
            if typ == "DefUse":
                if back:
                    if n1.tag.block == n2.tag.block:
                        latency = n1.end - n1.begin
                        g.add_edge(pydot.Edge(dotn1, dotn2, color='red', label=latency))
                    else:
                        g.add_edge(pydot.Edge(dotn1, dotn2, color='red'))
                else:
                    if n1.tag.block == n2.tag.block:
                        latency = n2.begin - n1.begin
                        g.add_edge(pydot.Edge(dotn1, dotn2, label=latency))
                    else:
                        g.add_edge(pydot.Edge(dotn1, dotn2))
            elif typ == "UseDef":
                if back:
                    g.add_edge(pydot.Edge(dotn1, dotn2, color='orange'))
                else:
                    g.add_edge(pydot.Edge(dotn1, dotn2, color='blue'))
            elif typ == "Seq":
                if back:
                    g.add_edge(pydot.Edge(dotn1, dotn2, style='dashed', color='red'))
                else:
                    g.add_edge(pydot.Edge(dotn1, dotn2, style='dashed'))
        if self.edges:
            g.write_png('{}/{}.png'.format(env.debug_output_dir, name))
            #g.write_svg(name+'.svg')
            #g.write(name+'.dot')
        env.dev_debug_mode = debug_mode

    def write_dot_pygraphviz(self, name):
        try:
            import pygraphviz as pgv  # type: ignore
        except ImportError:
            return
        G = pgv.AGraph(directed=True, strict=False, landscape='false')

        def get_node_tag_text(node):
            s = str(node.tag)
            if len(s) > 50:
                return s[0:50]
            else:
                return s

        for n in self.nodes:
            logger.debug('#### ' + str(n.tag))
            G.add_node(get_node_tag_text(n), shape='box')
        for (n1, n2), (typ, back) in self.edges.items():
            if typ == "DefUse":
                if back:
                    G.add_edge(get_node_tag_text(n1), get_node_tag_text(n2), color='red')
                else:
                    G.add_edge(get_node_tag_text(n1), get_node_tag_text(n2))
        logger.debug('drawing dot ...')
        G.draw('{}_{}_dfg.png'.format(name, self.name), prog='dot')
        logger.debug('drawing dot is done')




class RegArrayParallelizer(object):
    def __init__(self, scope):
        self.scope = scope
        self.usedef = UseDefDetector().process(scope)

    def can_be_parallel(self, msym, n1, n2):
        n1_offs = self.offset_expr(n1.tag, msym)
        n2_offs = self.offset_expr(n2.tag, msym)
        return self.is_inequality_value(n1_offs, n2_offs)

    @staticmethod
    def offset_expr(stm, msym):
        if stm.is_mem_read():
            m = stm.src
        elif stm.is_mem_write():
            m = stm.exp
        else:
            return None
        # assert msym is m.mem.symbol
        return m.offset

    @staticmethod
    def _get_const(binop):
        assert isinstance(binop, BinOp)
        if isinstance(binop.left, Const):
            return binop.left
        elif isinstance(binop.right, Const):
            return binop.right
        return None

    def _has_other_var_and_difference(self, v1, v2_stm):
        # We try to find v1 in the rhs of v2_stm.
        # And also we try to find a constant value in the rhs of v2_stm.
        # If both of them are found, we can detect that v2_stm.dst is different from v1
        # e.g.
        # v1 = ...
        # v2 = v1 + 1
        if not (isinstance(v2_stm, Move) and isinstance(v2_stm.src, BinOp)):
                return False
        rhs_syms = [qualified_symbols(e, self.scope)[-1] for e in v2_stm.src.kids() if isinstance(e, Temp)]
        if len(rhs_syms) != 1:
            return False
        rhs_const = self._get_const(v2_stm.src)
        if v1 is rhs_syms[0] and rhs_const:
            if ((v2_stm.src.op == 'Add' and rhs_const.value != 0) or
                    (v2_stm.src.op == 'Sub' and rhs_const.value != 0) or
                    (v2_stm.src.op == 'Mult' and rhs_const.value != 1)):
                return True
        return False

    def _has_same_var_and_difference(self, v1_stm, v2_stm):
        # We try to find the same var in the v2_stm.src and v1_stm.src.
        # And also we try to find a constant value in the v2_stm.src and v1_stm.src.
        # If both of them are found, we can detect that v1_stm.dst is different from v2_stm.dst
        # e.g.
        # v1 = x + 1
        # v2 = x + 2
        if not (isinstance(v1_stm, Move) and isinstance(v1_stm.src, BinOp)):
            return False
        if not (isinstance(v2_stm, Move) and isinstance(v2_stm.src, BinOp)):
            return False
        v1_rhs_syms = set([qualified_symbols(e, self.scope)[-1] for e in v1_stm.src.kids() if isinstance(e, Temp)])
        v2_rhs_syms = set([qualified_symbols(e, self.scope)[-1] for e in v2_stm.src.kids() if isinstance(e, Temp)])
        common_syms = v1_rhs_syms.intersection(v2_rhs_syms)
        if not common_syms:
            return False
        v1_rhs_const = self._get_const(v1_stm.src)
        v2_rhs_const = self._get_const(v2_stm.src)
        assert v1_rhs_const is not None and v2_rhs_const is not None
        return v1_stm.src.op == v2_stm.src.op and v1_rhs_const.value != v2_rhs_const.value

    def is_inequality_value(self, offs1, offs2):
        if not offs1 or not offs2:
            return False
        if isinstance(offs1, Const) and isinstance(offs2, Const) and offs1.value != offs2.value:
            return True
        elif isinstance(offs1, Temp) and isinstance(offs2, Temp):
            offs1_sym = self.scope.find_sym(offs1.name)
            offs2_sym = self.scope.find_sym(offs2.name)
            offs1_defstms = self.usedef.get_stms_defining(offs1_sym)
            offs2_defstms = self.usedef.get_stms_defining(offs2_sym)
            if len(offs1_defstms) != 1 and len(offs2_defstms) != 1:
                return False
            offs2_stm = list(offs2_defstms)[0]
            offs1_stm = list(offs1_defstms)[0]
            if len(offs2_defstms) == 1:
                if self._has_other_var_and_difference(offs1_sym, offs2_stm):
                    return True
            if len(offs1_defstms) == 1:
                if self._has_other_var_and_difference(offs2_sym, offs1_stm):
                    return True
            if len(offs2_defstms) == 1 and len(offs1_defstms) == 1:
                return self._has_same_var_and_difference(offs2_stm, offs1_stm)
        return False


# --- Type dispatchers ---

def _is_move(stm):
    return isinstance(stm, Move)


def _is_expr(stm):
    return isinstance(stm, Expr)


def _is_const(ir):
    return isinstance(ir, Const)


def _is_temp(ir):
    return isinstance(ir, Temp)


def _is_attr(ir):
    return isinstance(ir, Attr)


def _is_call(ir):
    return isinstance(ir, Call)


def _is_syscall(ir):
    return isinstance(ir, SysCall)


def _is_new(ir):
    return isinstance(ir, New)


def _is_array(ir):
    return isinstance(ir, Array)


def _is_mref(ir):
    return isinstance(ir, MRef)


def _is_mstore(ir):
    return isinstance(ir, MStore)


def _is_jump(stm):
    return isinstance(stm, Jump)


def _is_cjump(stm):
    return isinstance(stm, CJump)


def _is_mcjump(stm):
    return isinstance(stm, MCJump)


def _is_ctrl_stm(stm):
    return _is_jump(stm) or _is_cjump(stm) or _is_mcjump(stm)


def _is_phi(stm):
    return isinstance(stm, (Phi, UPhi))


def _is_mstm(stm):
    return isinstance(stm, MStm)


def _expand_stms(stms):
    """Expand MStm into child Moves for DFG node creation."""
    result = []
    for stm in stms:
        if _is_mstm(stm):
            result.extend(stm.stms)
        else:
            result.append(stm)
    return result


def _is_variable(ir):
    return isinstance(ir, IrVariable)


def _qualified_symbols(var, scope):
    return qualified_symbols(var, scope)


def _has_exclusive_function(stm, scope):
    return has_exclusive_function(stm, scope)


def _has_clkfence(stm):
    return has_clkfence(stm)


def _is_port_method_call(call, scope):
    return is_port_method_call(call, scope)


def _head_name(ir):
    if isinstance(ir, Attr):
        return ir.head_name()
    return ''


def _is_mem_read(stm):
    return _is_move(stm) and _is_mref(stm.src)


def _is_mem_write(stm):
    return _is_expr(stm) and _is_mstore(stm.exp)


def _program_order(stm, scope=None):
    if scope:
        blk = scope.find_block(stm.block)
    else:
        from ...common.env import env
        for s in env.scopes.values():
            if stm.block in s.block_map:
                blk = s.block_map[stm.block]
                break
        else:
            return (0, 0)
    return (blk.order, _find_stm_index(stm, scope))


class DFGBuilder(object):
    """Build Data Flow Graphs."""

    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        self.usedef = UseDefDetector().process(scope)
        self.scope.top_dfg = self._process(scope.top_region(), None)

    def _process(self, region, parent_dfg):
        dfg = self._make_graph(parent_dfg, region)
        for c in self.scope.loop_tree.get_children_of(region):
            self._process(c, dfg)
        return dfg

    def _make_graph(self, parent_dfg, region):
        logger.debug('make graph ' + region.name)
        dfg = DataFlowGraph(self.scope, region.name, parent_dfg, region)
        usedef = self.usedef

        blocks = region.blocks()
        # Pass 1: create all nodes in block/stm order so _nid reflects program order
        for b in blocks:
            for stm in _expand_stms(b.stms):
                dfg.add_stm_node(stm)
        # Pass 2: classify source nodes and add edges
        for b in blocks:
            for stm in _expand_stms(b.stms):
                logger.log(0, 'loop head ' + region.name + ' :: ' + str(stm))
                usenode = dfg.find_node(stm)
                self._add_source_node(usenode, dfg, usedef, blocks)
                self._add_defuse_edges(stm, usenode, dfg, usedef, blocks)
                self._add_usedef_edges(stm, usenode, dfg, usedef, blocks)
        if region.head.synth_params['scheduling'] == 'sequential':
            self._add_seq_edges(blocks, dfg)
        self._add_seq_edges_for_object(blocks, dfg)
        self._add_seq_edges_for_function(blocks, dfg)
        self._add_seq_edges_for_timed(blocks, dfg)
        self._add_mem_edges(dfg)
        self._remove_alias_cycle(dfg)
        if region.head.synth_params['scheduling'] == 'pipeline' and dfg.parent:
            self._tweak_loop_var_edges_for_pipeline(dfg)
            self._tweak_port_edges_for_pipeline(dfg)
        if region.head.synth_params['scheduling'] != 'pipeline' or not dfg.parent:
            self._add_seq_edges_for_ctrl_branch(dfg)
        return dfg

    def _add_source_node(self, node, dfg, usedef, blocks):
        stm = node.tag
        usevars = usedef.get_vars_used_at(stm)
        if not usevars and _is_move(stm):
            dfg.src_nodes.add(node)
            return
        for v in usevars:
            v_sym = _qualified_symbols(v, self.scope)[-1]
            assert isinstance(v_sym, Symbol)
            if v_sym.is_param():
                dfg.src_nodes.add(node)
                return
            if _is_attr(v) and _head_name(v) == env.self_name:
                dfg.src_nodes.add(node)
                return
            defstms = usedef.get_stms_defining(v_sym)
            for defstm in defstms:
                if defstm.block not in [b.bid for b in blocks]:
                    dfg.src_nodes.add(node)
                    return

        if self._is_constant_stm(stm):
            logger.log(0, 'add src: $use const ' + str(stm))
            dfg.src_nodes.add(node)
            return

        def has_mem_arg(args):
            for _, a in args:
                if _is_temp(a):
                    a_sym = self.scope.find_sym(a.name)
                    assert a_sym
                    if a_sym.typ.is_list():
                        return True
            return False

        call = None
        if _is_expr(stm):
            if _is_call(stm.exp) or _is_syscall(stm.exp):
                call = stm.exp
        elif _is_move(stm):
            if _is_call(stm.src) or _is_syscall(stm.src):
                call = stm.src
        if call:
            if len(call.args) == 0 or has_mem_arg(call.args):
                dfg.src_nodes.add(node)
        if _has_exclusive_function(stm, self.scope):
            dfg.src_nodes.add(node)

    def _add_defuse_edges(self, stm, usenode, dfg, usedef, blocks):
        for v in usedef.get_vars_used_at(stm):
            v_sym = _qualified_symbols(v, self.scope)[-1]
            assert isinstance(v_sym, Symbol)
            usenode.uses.append(v_sym)
            defstms = usedef.get_stms_defining(v_sym)
            for defstm in defstms:
                if stm is defstm:
                    continue
                if len(defstms) > 1 and (_program_order(stm, self.scope) <= _program_order(defstm, self.scope)):
                    continue
                if defstm.block not in [b.bid for b in blocks]:
                    continue
                defnode = dfg.add_stm_node(defstm)
                dfg.add_defuse_edge(defnode, usenode)

    def _add_usedef_edges(self, stm, defnode, dfg, usedef, blocks):
        for v in usedef.get_vars_defined_at(stm):
            v_sym = _qualified_symbols(v, self.scope)[-1]
            assert isinstance(v_sym, Symbol)
            defnode.defs.append(v_sym)
            usestms = usedef.get_stms_using(v_sym)
            for usestm in usestms:
                if stm is usestm:
                    continue
                if _program_order(stm, self.scope) <= _program_order(usestm, self.scope):
                    continue
                if usestm.block != stm.block:
                    continue
                usenode = dfg.add_stm_node(usestm)
                dfg.add_usedef_edge(usenode, defnode)
                visited = set()
                if v_sym.typ.is_scalar() and not v_sym.is_induction():
                    continue
                self._add_usedef_edges_for_alias(dfg, usenode, defnode, usedef, visited)

    def _is_constant_stm(self, stm):
        if _is_move(stm):
            src = stm.src
            if _is_const(src) or _is_array(src) or _is_call(src):
                return True
            if _is_mref(src) and _is_const(src.offset):
                return True
            if _is_new(src):
                return True
            if _is_syscall(src) and src.name == '$new':
                return True
        elif _is_expr(stm):
            exp = stm.exp
            if _is_call(exp) or _is_syscall(exp):
                return all(_is_const(a) for _, a in exp.args)
            if _is_mstore(exp) and _is_const(exp.offset) and _is_const(exp.exp):
                return True
        elif _is_cjump(stm):
            return _is_const(stm.exp)
        elif _is_mcjump(stm):
            if any(_is_const(c) for c in stm.conds[:-1]):
                return True
        return False

    def _node_order_by_ctrl(self, node):
        stm = node.tag
        return (self.scope.find_block(stm.block).order, self.scope.find_block(stm.block).num, _find_stm_index(stm, self.scope))

    def _add_mem_edges(self, dfg):
        node_groups_by_mem_sym = defaultdict(list)
        for node in dfg.nodes:
            stm = node.tag
            if _is_move(stm):
                mv = stm
                if _is_mref(mv.src):
                    mem_sym = _qualified_symbols(mv.src.mem, self.scope)[-1]
                    node_groups_by_mem_sym[mem_sym].append(node)
                elif _is_call(mv.src):
                    for _, arg in mv.src.args:
                        if _is_temp(arg) and (arg_sym := self.scope.find_sym(arg.name)) and arg_sym.typ.is_list():
                            node_groups_by_mem_sym[arg_sym].append(node)
                else:
                    assert _is_variable(mv.dst)
                    dst_sym = _qualified_symbols(mv.dst, self.scope)[-1]
                    assert isinstance(dst_sym, Symbol)
                    if dst_sym.typ.is_seq():
                        pass
            elif _is_expr(stm):
                expr = stm
                if _is_call(expr.exp):
                    for _, arg in expr.exp.args:
                        if _is_temp(arg) and (arg_sym := self.scope.find_sym(arg.name)) and arg_sym.typ.is_list():
                            node_groups_by_mem_sym[arg_sym].append(node)
                elif _is_mstore(expr.exp):
                    mem_sym = _qualified_symbols(expr.exp.mem, self.scope)[-1]
                    assert isinstance(mem_sym, Symbol)
                    node_groups_by_mem_sym[mem_sym].append(node)
        parallelizer = RegArrayParallelizer(self.scope)
        for mem_sym, nodes in node_groups_by_mem_sym.items():
            if mem_sym.typ.is_tuple():
                continue
            node_groups_by_blk = defaultdict(list)
            for n in nodes:
                node_groups_by_blk[n.tag.block].append(n)
            for ns in node_groups_by_blk.values():
                sorted_nodes = sorted(ns, key=self._node_order_by_ctrl)
                for i in range(len(sorted_nodes) - 1):
                    n1 = sorted_nodes[i]
                    for k in range(i + 1, len(sorted_nodes)):
                        n2 = sorted_nodes[k]
                        if parallelizer.can_be_parallel(mem_sym, n1, n2):
                            continue
                        if _is_mem_read(n1.tag):
                            if _is_mem_write(n2.tag):
                                dfg.add_usedef_edge(n1, n2)
                            continue
                        if self.scope.has_branch_edge(n1.tag, n2.tag):
                            continue
                        dfg.add_seq_edge(n1, n2)
                else:
                    for i in range(len(sorted_nodes) - 1):
                        n1 = sorted_nodes[i]
                        for j in range(i + 1, len(sorted_nodes)):
                            n2 = sorted_nodes[j]
                            if self.scope.has_branch_edge(n1.tag, n2.tag):
                                continue
                            dfg.add_seq_edge(n1, n2)

    def _add_seq_edges(self, blocks, dfg):
        for blk in blocks:
            prev_node = None
            for stm in _expand_stms(blk.stms):
                node = dfg.find_node(stm)
                if not node:
                    continue
                if prev_node:
                    dfg.add_seq_edge(prev_node, node)
                prev_node = node

    def _is_same_block_node(self, n0, n1):
        return n0.tag.block == n1.tag.block

    def _get_mutable_object_symbol(self, stm):
        if _is_move(stm):
            call = stm.src
        elif _is_expr(stm):
            call = stm.exp
        else:
            return None
        if not _is_call(call):
            return None
        func = call.func
        if not _is_attr(func):
            return None
        qsyms = _qualified_symbols(func, self.scope)
        receiver = qsyms[-2]
        assert isinstance(receiver, Symbol)
        if receiver.typ.is_object() or receiver.typ.is_port():
            callee_scope = call.get_callee_scope(self.scope)
            if callee_scope.is_mutable():
                return receiver
        return None

    def _add_seq_edges_for_object(self, blocks, dfg):
        for block in blocks:
            prevs = {}
            for stm in _expand_stms(block.stms):
                sym = self._get_mutable_object_symbol(stm)
                if not sym:
                    continue
                node = dfg.add_stm_node(stm)
                if sym in prevs:
                    prev = prevs[sym]
                    if self._is_same_block_node(prev, node):
                        if prev.tag.block == node.tag.block:
                            dfg.add_seq_edge(prev, node)
                prevs[sym] = node

    def _add_seq_edges_for_ctrl_branch(self, dfg):
        for node in dfg.nodes:
            stm = node.tag
            if _is_ctrl_stm(stm):
                assert self.scope.find_block(stm.block).stms[-1] is stm
                for prev_stm in _expand_stms(self.scope.find_block(stm.block).stms[:-1]):
                    prev_node = dfg.find_node(prev_stm)
                    if prev_node:
                        dfg.add_seq_edge(prev_node, node)

    def _add_seq_edges_for_function(self, blocks, dfg):
        for block in blocks:
            seq_func_node = None
            for stm in _expand_stms(block.stms):
                if _is_ctrl_stm(stm):
                    continue
                node = dfg.find_node(stm)
                if not node:
                    continue
                if seq_func_node:
                    if self.scope.has_branch_edge(seq_func_node.tag, node.tag):
                        continue
                    if not _has_exclusive_function(stm, self.scope):
                        continue
                    dfg.add_seq_edge(seq_func_node, node)
                if _has_exclusive_function(stm, self.scope):
                    seq_func_node = node
            seq_func_node = None
            for stm in reversed(_expand_stms(block.stms)):
                if _is_ctrl_stm(stm):
                    continue
                node = dfg.find_node(stm)
                if not node:
                    continue
                if seq_func_node:
                    if self.scope.has_branch_edge(node.tag, seq_func_node.tag):
                        continue
                    if not _has_exclusive_function(stm, self.scope):
                        continue
                    dfg.add_seq_edge(node, seq_func_node)
                if _has_exclusive_function(stm, self.scope):
                    seq_func_node = node

    def _add_seq_edges_for_timed(self, blocks, dfg):
        for block in blocks:
            if block.synth_params['scheduling'] != 'timed':
                continue
            prev_clksleep_node = None
            other_nodes = []
            for stm in _expand_stms(block.stms):
                node = dfg.find_node(stm)
                if not node:
                    continue
                if _has_clkfence(stm):
                    for n in other_nodes:
                        dfg.add_seq_edge(n, node)
                    if prev_clksleep_node:
                        dfg.add_seq_edge(prev_clksleep_node, node)
                    other_nodes.clear()
                    prev_clksleep_node = node
                else:
                    other_nodes.append(node)
                    if prev_clksleep_node:
                        dfg.add_seq_edge(prev_clksleep_node, node)

    def _add_usedef_edges_for_alias(self, dfg, usenode, defnode, usedef, visited):
        if (usenode, defnode) in visited:
            return
        visited.add((usenode, defnode))
        stm = usenode.tag
        if _is_move(stm):
            var = stm.dst
        elif _is_phi(stm):
            var = stm.var
        else:
            return
        var_sym = _qualified_symbols(var, self.scope)[-1]
        assert isinstance(var_sym, Symbol)
        if not var_sym.is_alias():
            return
        for u in usedef.get_stms_using(var_sym):
            if u is defnode.tag:
                continue
            if _program_order(defnode.tag, self.scope) <= _program_order(u, self.scope):
                continue
            if u.block != defnode.tag.block:
                continue
            unode = dfg.add_stm_node(u)
            if _has_exclusive_function(u, self.scope):
                dfg.add_seq_edge(unode, defnode)
            elif _is_mem_read(u) or _is_mem_write(u):
                dfg.add_usedef_edge(unode, defnode)
            else:
                dfg.add_usedef_edge(unode, defnode)
            self._add_usedef_edges_for_alias(dfg, unode, defnode, usedef, visited)

    def _remove_alias_cycle(self, dfg):
        backs = []
        for (n1, n2), (_, back) in dfg.edges.items():
            if back and (_is_move(n1.tag) or _is_phi(n1.tag)):
                var_sym = None
                if _is_move(n1.tag):
                    var_sym = _qualified_symbols(n1.tag.dst, self.scope)[-1]
                elif _is_phi(n1.tag):
                    var_sym = _qualified_symbols(n1.tag.var, self.scope)[-1]
                assert isinstance(var_sym, Symbol)
                if var_sym.is_alias():
                    backs.append((n1, n2))
        dones = set()
        for end, start in backs:
            if end in dones:
                continue
            self._remove_alias_cycle_rec(dfg, start, end, dones)

    def _remove_alias_cycle_rec(self, dfg, node, end, dones):
        if node is end:
            if end not in dones and end.defs[0].is_alias():
                end.defs[0].del_tag('alias')
                dones.add(end)
            return
        if (_is_move(node.tag) or _is_phi(node.tag)) and node.defs[0].is_alias():
            var = node.tag.dst if _is_move(node.tag) else node.tag.var
            var_sym = _qualified_symbols(var, self.scope)[-1]
            assert isinstance(var_sym, Symbol)
            if var_sym.is_alias():
                succs = dfg.succs_typ_without_back(node, 'DefUse')
                for s in succs:
                    self._remove_alias_cycle_rec(dfg, s, end, dones)

    def _tweak_loop_var_edges_for_pipeline(self, dfg):
        def remove_seq_pred(node, visited):
            if node in visited:
                return
            visited.add(node)
            for seq_pred in dfg.preds_typ(node, 'Seq'):
                dfg.remove_edge(seq_pred, node)
            for defnode in dfg.preds_typ(node, 'DefUse'):
                remove_seq_pred(defnode, visited)
        for node in dfg.nodes:
            stm = node.tag
            if _is_move(stm):
                sym = _qualified_symbols(stm.dst, self.scope)[-1]
                if isinstance(sym, Symbol) and sym.is_induction():
                    remove_seq_pred(node, set())

    def _get_port_sym_from_node(self, node):
        stm = node.tag
        if _is_move(stm):
            call = stm.src
        elif _is_expr(stm):
            call = stm.exp
        else:
            return None
        if not _is_port_method_call(call, self.scope):
            return None
        func = call.func
        if isinstance(func, Attr):
            return func.tail_name()
        return None

    def _tweak_port_edges_for_pipeline(self, dfg):
        def remove_port_seq_pred(node, port):
            for seq_pred in dfg.preds_typ(node, 'Seq'):
                pred = self._get_port_sym_from_node(seq_pred)
                if pred is None:
                    dfg.remove_edge(seq_pred, node)
            for seq_succ in dfg.succs_typ(node, 'Seq'):
                succ = self._get_port_sym_from_node(seq_succ)
                if succ is None:
                    dfg.remove_edge(node, seq_succ)

        for node in dfg.nodes:
            p = self._get_port_sym_from_node(node)
            if not p:
                continue
            remove_port_seq_pred(node, p)
