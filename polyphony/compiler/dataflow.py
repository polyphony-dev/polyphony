from collections import defaultdict
from .ir import *
from .irhelper import is_port_method_call, has_exclusive_function
from .env import env
from . import utils
from logging import getLogger
logger = getLogger(__name__)


class DFNode(object):
    def __init__(self, typ, tag):
        self.typ = typ  # 'Stm', 'Loop', 'Block'
        self.tag = tag
        self.priority = -1  # 0 is highest priority
        self.begin = -1
        self.end = -1
        if typ == 'Stm':
            self.stm_index = tag.block.stms.index(tag)
        else:
            self.stm_index = 0
        self.instance_num = 0
        self.uses = []
        self.defs = []

    def __str__(self):
        if self.typ == 'Stm':
            s = '<{}> ({}) {} {}:{} {}'.format(
                hex(self.__hash__())[-4:],
                self.tag.lineno,
                self.priority,
                self.begin,
                self.end,
                self.tag
            )
            #s += ' ' + self.tag.block.name
        elif self.typ == 'Loop':
            s = 'Node {} {} {}:{} Loop {}'.format(
                hex(self.__hash__())[-4:],
                self.priority,
                self.begin,
                self.end,
                self.tag.name
            )
        elif self.typ == 'Block':
            s = 'Node {} {} {}:{} Block'.format(
                hex(self.__hash__())[-4:],
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
        sources = self.find_src()
        for n in sorted(self.traverse_nodes(self.succs, sources, [])):
            s += '  ' + str(n)
            s += '\n'
        s += 'DFG all edges ==============\n'
        for (n1, n2), (typ, back) in self.edges.items():
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
        if stm1.block is stm2.block:
            return stm1.block.stms.index(stm1) > stm2.block.stms.index(stm2)
        else:
            return stm1.block.order > stm2.block.order

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
        return self.src_nodes

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

    def traverse_nodes(self, traverse_func, nodes, visited):
        if visited is not None:
            nodes = [n for n in nodes if n not in visited]
        for n in nodes:
            if visited is not None:
                visited.append(n)
            yield n

        for n in nodes:
            next_nodes = utils.unique(traverse_func(n))
            yield from self.traverse_nodes(traverse_func, next_nodes, visited)

    def get_priority_ordered_nodes(self):
        return sorted(self.nodes, key=lambda n: n.priority)

    def get_highest_priority_nodes(self):
        return filter(lambda n: n.priority == 0, self.nodes)

    def get_lowest_timing(self):
        return max(lambda n: n.end, self.nodes)

    def get_scheduled_nodes(self):
        node_dict = defaultdict(list)
        for n in self.nodes:
            node_dict[n.tag.block.num].append(n)
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
            import pydot
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
                    if n1.tag.block is n2.tag.block:
                        latency = n1.end - n1.begin
                        g.add_edge(pydot.Edge(dotn1, dotn2, color='red', label=latency))
                    else:
                        g.add_edge(pydot.Edge(dotn1, dotn2, color='red'))
                else:
                    if n1.tag.block is n2.tag.block:
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
            import pygraphviz
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


class DFGBuilder(object):
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        self.scope.top_dfg = self._process(scope.top_region(), None)

    def _process(self, region, parent_dfg):
        dfg = self._make_graph(parent_dfg, region)
        for c in self.scope.loop_tree.get_children_of(region):
            self._process(c, dfg)
        return dfg

    def _dump_dfg(self, dfg):
        for n in dfg.nodes:
            logger.debug('---------------------------')
            logger.debug(n)
            logger.debug('DefUse preds')
            preds = dfg.preds_typ(n, 'DefUse')
            for pred in preds:
                logger.debug(pred)
            logger.debug('DefUse succs')
            succs = dfg.succs_typ(n, 'DefUse')
            for succ in succs:
                logger.debug(succ)

            logger.debug('Seq preds')
            preds = dfg.preds_typ(n, 'Seq')
            for pred in preds:
                logger.debug(pred)
            logger.debug('Seq succs')
            succs = dfg.succs_typ(n, 'Seq')
            for succ in succs:
                logger.debug(succ)

    def _make_graph(self, parent_dfg, region):
        logger.debug('make graph ' + region.name)
        dfg = DataFlowGraph(self.scope, region.name, parent_dfg, region)
        usedef = self.scope.usedef

        blocks = region.blocks()
        for b in blocks:
            for stm in b.stms:
                logger.log(0, 'loop head ' + region.name + ' :: ' + str(stm))
                usenode = dfg.add_stm_node(stm)
                # collect source nodes
                self._add_source_node(usenode, dfg, usedef, blocks)
                # add def-use edges
                self._add_defuse_edges(stm, usenode, dfg, usedef, blocks)
                # add use-def edges
                self._add_usedef_edges(stm, usenode, dfg, usedef, blocks)
        if region.head.synth_params['scheduling'] == 'sequential':
            self._add_seq_edges(blocks, dfg)
        self._add_seq_edges_for_object(blocks, dfg)
        self._add_seq_edges_for_function(blocks, dfg)
        self._add_seq_edges_for_io(blocks, dfg)
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
        if not usevars and stm.is_a(MOVE):
            dfg.src_nodes.add(node)
            return
        for v in usevars:
            if v.symbol().is_param():
                dfg.src_nodes.add(node)
                return
            if v.is_a(ATTR) and v.head().name == env.self_name:
                dfg.src_nodes.add(node)
                return
            defstms = usedef.get_stms_defining(v.symbol())
            for defstm in defstms:
                # this definition stm is in the out of the section
                if defstm.block not in blocks:
                    dfg.src_nodes.add(node)
                    return

        uses = usedef.get_consts_used_at(stm)
        if uses:
            if self._is_constant_stm(stm):
                logger.log(0, 'add src: $use const ' + str(stm))
                dfg.src_nodes.add(node)
                return

        def has_mem_arg(args):
            for _, a in args:
                if a.is_a(TEMP) and a.symbol().typ.is_list():
                    return True
            return False
        call = None
        if stm.is_a(EXPR):
            if stm.exp.is_a(CALL) or stm.exp.is_a(SYSCALL):
                call = stm.exp
        elif stm.is_a(MOVE):
            if stm.src.is_a(CALL) or stm.src.is_a(SYSCALL):
                call = stm.src
        if call:
            if len(call.args) == 0 or has_mem_arg(call.args):
                dfg.src_nodes.add(node)

    def _add_defuse_edges(self, stm, usenode, dfg, usedef, blocks):
        for v in usedef.get_vars_used_at(stm):
            usenode.uses.append(v.symbol())
            defstms = usedef.get_stms_defining(v.symbol())
            logger.log(0, v.symbol().name + ' defstms ')
            for defstm in defstms:
                logger.log(0, str(defstm))

                if stm is defstm:
                    continue
                if len(defstms) > 1 and (stm.program_order() <= defstm.program_order()):
                    continue
                # this definition stm is in the out of the section
                if defstm.block not in blocks:
                    continue
                defnode = dfg.add_stm_node(defstm)
                dfg.add_defuse_edge(defnode, usenode)

    def _add_usedef_edges(self, stm, defnode, dfg, usedef, blocks):
        for v in usedef.get_vars_defined_at(stm):
            defnode.defs.append(v.symbol())
            usestms = usedef.get_stms_using(v.symbol())
            for usestm in usestms:
                if stm is usestm:
                    continue
                if stm.program_order() <= usestm.program_order():
                    continue
                # this definition stm is in the out of the section
                if usestm.block is not stm.block:
                    continue
                usenode = dfg.add_stm_node(usestm)
                dfg.add_usedef_edge(usenode, defnode)
                visited = set()
                if v.symbol().typ.is_scalar() and not v.symbol().is_induction():
                    continue
                self._add_usedef_edges_for_alias(dfg, usenode, defnode, usedef, visited)

    def _is_constant_stm(self, stm):
        if stm.is_a(PHIBase):
            return True
        elif stm.is_a(MOVE):
            if stm.src.is_a([CONST, ARRAY, CALL]):
                return True
            elif stm.src.is_a(MREF) and stm.src.offset.is_a(CONST):
                return True
            elif stm.src.is_a(NEW):
                return True
        elif stm.is_a(EXPR):
            if stm.exp.is_a([CALL, SYSCALL]):
                call = stm.exp
                return all(a.is_a(CONST) for _, a in call.args)
            elif stm.exp.is_a(MSTORE) and stm.exp.offset.is_a(CONST) and stm.exp.exp.is_a(CONST):
                return True
        elif stm.is_a(CJUMP) and stm.exp.is_a(CONST):
            return True
        elif stm.is_a(MCJUMP):
            if any(c.is_a(CONST) for c in stm.conds[:-1]):
                return True
        return False

    def _all_stms(self, blocks):
        all_stms_in_section = []
        for b in blocks:
            all_stms_in_section.extend(b.stms)
        return all_stms_in_section

    def _node_order_by_ctrl(self, node):
        return (node.tag.block.order, node.tag.block.num, node.tag.block.stms.index(node.tag))

    def _add_mem_edges(self, dfg):
        '''
        add the memory-to-memory edges
        if both of them are in the same block
        '''
        # grouping by memory
        node_groups_by_mem = defaultdict(list)
        for node in dfg.nodes:
            if node.tag.is_a(MOVE):
                mv = node.tag
                if mv.src.is_a(MREF):
                    mem_group = mv.src.mem.symbol()
                    node_groups_by_mem[mem_group].append(node)
                elif mv.src.is_a(CALL):
                    for _, arg in mv.src.args:
                        if arg.is_a(TEMP) and arg.symbol().typ.is_list():
                            mem_group = arg.symbol()
                            node_groups_by_mem[mem_group].append(node)
                elif mv.dst.is_a([TEMP, ATTR]):
                    if mv.dst.symbol().typ.is_seq():
                        memnode = mv.dst.symbol().typ.get_memnode()
                        if not memnode.can_be_reg():
                            node_groups_by_mem[mv.dst.symbol()].append(node)
            elif node.tag.is_a(EXPR):
                expr = node.tag
                if expr.exp.is_a(CALL):
                    for _, arg in expr.exp.args:
                        if arg.is_a(TEMP) and arg.symbol().typ.is_list():
                            mem_group = arg.symbol()
                            node_groups_by_mem[mem_group].append(node)
                elif expr.exp.is_a(MSTORE):
                    mem_group = expr.exp.mem.symbol()
                    node_groups_by_mem[mem_group].append(node)
        parallelizer = RegArrayParallelizer(self.scope)
        for group, nodes in node_groups_by_mem.items():
            memnode = group.typ.get_memnode()
            if memnode.is_immutable():  # or memnode.can_be_reg():
                continue
            is_reg_array = memnode.can_be_reg()
            node_groups_by_blk = defaultdict(list)
            # grouping by block
            for n in nodes:
                node_groups_by_blk[n.tag.block].append(n)
            for ns in node_groups_by_blk.values():
                sorted_nodes = sorted(ns, key=self._node_order_by_ctrl)
                if is_reg_array:
                    for i in range(len(sorted_nodes) - 1):
                        n1 = sorted_nodes[i]
                        for k in range(i + 1, len(sorted_nodes)):
                            n2 = sorted_nodes[k]
                            if parallelizer.can_be_parallel(group, n1, n2):
                                continue
                            if n1.tag.is_mem_read():
                                if n2.tag.is_mem_write():
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

    def _add_edges_between_func_modules(self, blocks, dfg):
        """this function is used for testbench only"""
        all_stms_in_section = self._all_stms(blocks)
        prev_node = None
        for stm in all_stms_in_section:
            node = None
            if stm.is_a(MOVE) and stm.src.is_a(CALL) and stm.src.func_scope().is_function_module():
                node = dfg.add_stm_node(stm)
            elif stm.is_a(EXPR) and stm.exp.is_a(CALL) and stm.exp.func_scope().is_function_module():
                node = dfg.add_stm_node(stm)
            if node:
                if prev_node:
                    if prev_node.tag.block is node.tag.block:
                        dfg.add_seq_edge(prev_node, node)
                prev_node = node

    def _add_seq_edges(self, blocks, dfg):
        for blk in blocks:
            prev_node = None
            for stm in blk.stms:
                node = dfg.add_stm_node(stm)
                if prev_node:
                    dfg.add_seq_edge(prev_node, node)
                prev_node = node

    def _is_same_block_node(self, n0, n1):
        return n0.tag.block is n1.tag.block

    def _get_mutable_object_symbol(self, stm):
        if stm.is_a(MOVE):
            call = stm.src
        elif stm.is_a(EXPR):
            call = stm.exp
        else:
            return None
        if not call.is_a(CALL):
            return None
        if not call.func.is_a(ATTR):
            return None
        receiver = call.func.tail()
        if receiver.typ.is_object() or receiver.typ.is_port():
            if call.func_scope().is_mutable():
                return receiver
        return None

    def _add_seq_edges_for_object(self, blocks, dfg):
        for block in blocks:
            prevs = {}
            for stm in block.stms:
                sym = self._get_mutable_object_symbol(stm)
                if not sym:
                    continue
                node = dfg.add_stm_node(stm)
                if sym in prevs:
                    prev = prevs[sym]
                    if self._is_same_block_node(prev, node):
                        if prev.tag.block is node.tag.block:
                            dfg.add_seq_edge(prev, node)
                prevs[sym] = node

    # workaround
    def _add_seq_edges_for_ctrl_branch(self, dfg):
        for node in dfg.nodes:
            stm = node.tag
            if stm.is_a([JUMP, CJUMP, MCJUMP]):
                #assert len(stm.block.stms) > 1
                assert stm.block.stms[-1] is stm
                for prev_stm in stm.block.stms[:-1]:
                    prev_node = dfg.find_node(prev_stm)
                    dfg.add_seq_edge(prev_node, node)

    def _add_seq_edges_for_function(self, blocks, dfg):
        '''make sequence edges between functions that are executed in an exclusive state'''
        for block in blocks:
            seq_func_node = None
            for stm in block.stms:
                if stm.is_a([JUMP, CJUMP, MCJUMP]):
                    continue
                node = dfg.find_node(stm)
                if seq_func_node:
                    if self.scope.has_branch_edge(seq_func_node.tag, node.tag):
                        continue
                    dfg.add_seq_edge(seq_func_node, node)
                if has_exclusive_function(stm):
                    seq_func_node = node
            seq_func_node = None
            for stm in reversed(block.stms):
                if stm.is_a([JUMP, CJUMP, MCJUMP]):
                    continue
                node = dfg.find_node(stm)
                if seq_func_node:
                    if self.scope.has_branch_edge(node.tag, seq_func_node.tag):
                        continue
                    dfg.add_seq_edge(node, seq_func_node)
                if has_exclusive_function(stm):
                    seq_func_node = node

    def _add_seq_edges_for_io(self, blocks, dfg):
        '''make sequence edges between ports'''
        for block in blocks:
            port_node = None
            for stm in block.stms:
                if stm.is_a(MOVE):
                    call = stm.src
                elif stm.is_a(EXPR):
                    call = stm.exp
                else:
                    continue
                if is_port_method_call(call):
                    node = dfg.find_node(stm)
                    if port_node:
                        dfg.add_seq_edge(port_node, node)
                    port_node = node

    @staticmethod
    def get_memnode(stm):
        if stm.is_mem_read():
            m = stm.src
        elif stm.is_mem_write():
            m = stm.exp
        else:
            return None
        return m.mem.symbol().typ.get_memnode()

    def _add_usedef_edges_for_alias(self, dfg, usenode, defnode, usedef, visited):
        if (usenode, defnode) in visited:
            return
        visited.add((usenode, defnode))
        stm = usenode.tag
        if stm.is_a(MOVE):
            var = stm.dst
        elif stm.is_a(PHIBase):
            var = stm.var
        else:
            return
        if not var.symbol().is_alias():
            return
        for u in usedef.get_stms_using(var.symbol()):
            if u is defnode.tag:
                continue
            if defnode.tag.program_order() <= u.program_order():
                continue
            if u.block is not defnode.tag.block:
                continue
            unode = dfg.add_stm_node(u)
            if has_exclusive_function(u):
                dfg.add_seq_edge(unode, defnode)
            elif unode.tag.is_mem_read() or unode.tag.is_mem_write():
                memnode = self.get_memnode(unode.tag)
                if not memnode.can_be_reg():
                    dfg.add_seq_edge(unode, defnode)
                else:
                    dfg.add_usedef_edge(unode, defnode)
            else:
                dfg.add_usedef_edge(unode, defnode)
            self._add_usedef_edges_for_alias(dfg, unode, defnode, usedef, visited)

    def _remove_alias_cycle(self, dfg):
        backs = []
        for (n1, n2), (_, back) in dfg.edges.items():
            if back and n1.tag.is_a([MOVE, PHIBase]):
                var = n1.tag.dst.symbol() if n1.tag.is_a(MOVE) else n1.tag.var.symbol()
                if var.is_alias():
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
        if node.tag.is_a([MOVE, PHIBase]) and node.defs[0].is_alias():
            var = node.tag.dst.symbol() if node.tag.is_a(MOVE) else node.tag.var.symbol()
            if var.is_alias():
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
            if stm.is_a(MOVE) and stm.dst.symbol().is_induction():
                remove_seq_pred(node, set())

    def _get_port_sym_from_node(self, node):
        stm = node.tag
        if stm.is_a(MOVE):
            call = stm.src
        elif stm.is_a(EXPR):
            call = stm.exp
        else:
            return None
        if not is_port_method_call(call):
            return None
        return call.func.tail()

    def _tweak_port_edges_for_pipeline(self, dfg):
        def remove_port_seq_pred(node, port):
            for seq_pred in dfg.preds_typ(node, 'Seq'):
                pred = self._get_port_sym_from_node(seq_pred)
                if pred is None:  # or pred is not port:
                    dfg.remove_edge(seq_pred, node)
            for seq_succ in dfg.succs_typ(node, 'Seq'):
                succ = self._get_port_sym_from_node(seq_succ)
                if succ is None:  # or succ is not port:
                    dfg.remove_edge(node, seq_succ)

        for node in dfg.nodes:
            p = self._get_port_sym_from_node(node)
            if not p:
                continue
            remove_port_seq_pred(node, p)


class RegArrayParallelizer(object):
    def __init__(self, scope):
        self.scope = scope

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
        assert msym is m.mem.symbol()
        return m.offset

    @staticmethod
    def _get_const(binop):
        assert binop.is_a(BINOP)
        if binop.left.is_a(CONST):
            return binop.left
        elif binop.right.is_a(CONST):
            return binop.right
        return None

    def _has_other_var_and_difference(self, v1, v2_stm):
        # We try to find v1 in the rhs of v2_stm.
        # And also we try to find a constant value in the rhs of v2_stm.
        # If both of them are found, we can detect that v2_stm.dst is different from v1
        # e.g.
        # v1 = ...
        # v2 = v1 + 1
        if not (v2_stm.is_a(MOVE) and v2_stm.src.is_a(BINOP)):
                return False
        rhs_syms = [e.symbol() for e in v2_stm.src.kids() if e.is_a(TEMP)]
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
        if not (v1_stm.is_a(MOVE) and v1_stm.src.is_a(BINOP)):
            return False
        if not (v2_stm.is_a(MOVE) and v2_stm.src.is_a(BINOP)):
            return False
        v1_rhs_syms = set([e.symbol() for e in v1_stm.src.kids() if e.is_a(TEMP)])
        v2_rhs_syms = set([e.symbol() for e in v2_stm.src.kids() if e.is_a(TEMP)])
        common_syms = v1_rhs_syms.intersection(v2_rhs_syms)
        if not common_syms:
            return False
        v1_rhs_const = self._get_const(v1_stm.src)
        v2_rhs_const = self._get_const(v2_stm.src)
        return v1_stm.src.op == v2_stm.src.op and v1_rhs_const.value != v2_rhs_const.value

    def is_inequality_value(self, offs1, offs2):
        if not offs1 or not offs2:
            return False
        if offs1.is_a(CONST) and offs2.is_a(CONST) and offs1.value != offs2.value:
            return True
        elif offs1.is_a(TEMP) and offs2.is_a(TEMP):
            offs1_defstms = self.scope.usedef.get_stms_defining(offs1.symbol())
            offs2_defstms = self.scope.usedef.get_stms_defining(offs2.symbol())
            if len(offs1_defstms) != 1 and len(offs2_defstms) != 1:
                return False
            offs2_stm = list(offs2_defstms)[0]
            offs1_stm = list(offs1_defstms)[0]
            if len(offs2_defstms) == 1:
                if self._has_other_var_and_difference(offs1.symbol(), offs2_stm):
                    return True
            if len(offs1_defstms) == 1:
                if self._has_other_var_and_difference(offs2.symbol(), offs1_stm):
                    return True
            if len(offs2_defstms) == 1 and len(offs1_defstms) == 1:
                return self._has_same_var_and_difference(offs2_stm, offs1_stm)
        return False
