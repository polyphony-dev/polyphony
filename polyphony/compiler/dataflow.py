import sys
#import pygraphviz as pgv
from collections import deque, defaultdict
from functools import reduce
from .common import error_info
from .block import Block, CompositBlock
from .ir import *
from .env import env
from .type import Type
from logging import getLogger
logger = getLogger(__name__)


class DFNode:
    def __init__(self, typ, tag):
        self.typ = typ #'Stm', 'Loop', 'Block'
        self.tag = tag
        self.priority = -1 # 0 is highest priority
        self.begin = -1
        self.end = -1
        if typ == 'Stm':
            self.stm_index = tag.block.stms.index(tag)
        else:
            self.stm_index = 0
        self.instance_num = 0

    def __str__(self):
        if self.typ == 'Stm':
            s = 'Node {} {} {}:{} {} {}'.format(hex(self.__hash__())[-4:], self.priority, self.begin, self.end, self.tag, self.tag.block.name)
        elif self.typ == 'Loop':
            s = 'Node {} {} {}:{} Loop {}'.format(hex(self.__hash__())[-4:], self.priority, self.begin, self.end, self.tag.name)
        elif self.typ == 'Block':
            s = 'Node {} {} {}:{} Block'.format(hex(self.__hash__())[-4:], self.priority, self.begin, self.end)
        else:
            assert False
        return s

    def __repr__(self):
        return str(self)

    def __lt__(self, other):
        return self.priority < other.priority


class DataFlowGraph:
    def __init__(self, name, blocks):
        self.name = name
        self.blocks = blocks
        self.nodes = []
        self.edges = set()
        self.src_nodes = set()
        self.succs_without_back_cache = {}
        self.preds_without_back_cache = {}
        self.parent = None
        self.children = []

    def __str__(self):
        return self.name

    def set_child(self, child):
        self.children.append(child)
        child.parent = self

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
        edge = (n1, n2, 'Seq', False)
        if edge not in self.edges:
            self.edges.add(edge)

    def add_edge(self, typ, n1, n2):
        assert n1 and n2 and n1.tag and n2.tag
        assert n1 is not n2
        back = self._is_back_edge(n1, n2)
        edge = (n1, n2, typ, back)
        if edge not in self.edges:
            self.edges.add(edge)

    def remove_edge(self, n1, n2):
        removes = []
        for edge in self.edges:
            if n1 is edge[0] and n2 is edge[1]:
                removes.append(edge)
        for rem in removes:
            self.edges.remove(rem)

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
        for n1, n2, _, _ in self.edges:
            if n1 is node:
                succs.append(n2)
        return succs

    def succs_without_back(self, node):
        if node in self.succs_without_back_cache:
            return self.succs_without_back_cache[node]

        succs = []
        for n1, n2, _, back in self.edges:
            if n1 is node and not back:
                succs.append(n2)
        return sorted(succs)

    def succs_typ(self, node, typ):
        succs = []
        for n1, n2, t, _ in self.edges:
            if (typ == t) and (n1 is node):
                succs.append(n2)
        return succs

    def preds(self, node):
        preds = []
        for n1, n2, _, _ in self.edges:
            if n2 is node:
                preds.append(n1)
        return preds

    def preds_without_back(self, node):
        if node in self.preds_without_back_cache:
            return self.preds_without_back_cache[node]

        preds = []
        for n1, n2, _, back in self.edges:
            if n2 is node and not back:
                preds.append(n1)
        return preds

    def preds_typ(self, node, typ):
        preds = []
        for n1, n2, t, _ in self.edges:
            if (typ == t) and (n2 is node):
                preds.append(n1)
        return preds

    def preds_typ_without_back(self, node, typ):
        preds = []
        for n1, n2, t, back in self.edges:
            if (typ == t) and (n2 is node) and (not back):
                preds.append(n1)
        return preds

    def create_edge_cache(self):
        self.succs_without_back_cache = {}
        self.preds_without_back_cache = {}
        for n in self.nodes:
            succs = self.succs_without_back(n)
            self.succs_without_back_cache[n] = succs
            preds = self.preds_without_back(n)
            self.preds_without_back_cache[n] = preds

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

    def remove_unconnected_node(self):
        pass
        #self.nodes = list(filter(lambda n: n.succs or n.preds, self.nodes))

    def traverse_nodes(self, siblings, visited):
        nodes = [n for n in siblings if n not in visited]
        for n in nodes:
            visited.append(n)
            yield n

        for n in nodes:
            for succ in self.traverse_nodes(self.succs(n), visited):
                yield succ

    def traverse_nodes_without_back(self, siblings):
        for n in siblings:
            yield n

        for n in siblings:
            succs = self.succs_without_back(n)
            if n in succs:
                succs.remove(n)
            for succ in self.traverse_nodes_without_back(succs):
                yield succ

    def dump(self):
        logger.debug('================================')
        logger.debug('DFG all nodes ==============')
        sources = self.find_src()
        for n in self.traverse_nodes(sources, []):
            logger.debug('  ' + str(n))
        logger.debug('DFG all edges ==============')
        for n1, n2, typ, back in self.edges:
            back_edge = "(back) " if back else ''
            if typ == 'DefUse':
                prefix1 = 'def '
                prefix2 = 'use -> '
            elif typ == 'UseDef':
                prefix1 = 'use '
                prefix2 = 'def -> '
            elif typ == 'Branch':
                prefix1 = 'pred blk '
                prefix2 = 'succ blk -> '
            elif typ == 'Seq':
                prefix1 = 'pred '
                prefix2 = 'succ -> '
            logger.debug(back_edge + prefix1 + ' ' + str(n1))
            logger.debug(back_edge + prefix2 + ' ' + str(n2))
        logger.debug('')

    def get_priority_ordered_nodes(self):
        return sorted(self.nodes, key=lambda n: n.priority)

    def get_highest_priority_nodes(self):
        return filter(lambda n: n.priority == 0, self.nodes)

    def get_lowest_timing(self):
        return max(lambda n: n.end, self.nodes)

    def get_scheduled_nodes(self):
        return sorted(self.nodes, key=lambda n: n.begin)

    def get_loop_nodes(self):
        return filter(lambda n: n.typ == 'Loop', self.nodes)

    def write_dot(self, name):
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
        for n1, n2, typ, back in self.edges:
            if typ == "DefUse":
                if back:
                    G.add_edge(get_node_tag_text(n1), get_node_tag_text(n2), color='red')
                else:
                    G.add_edge(get_node_tag_text(n1), get_node_tag_text(n2))
        logger.debug('drawing dot ...')
        G.draw('{}_{}_dfg.png'.format(name, self.name), prog='dot')
        logger.debug('drawing dot is done')

class DFGBuilder:
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        self.scope.top_dfg = self._process(scope.entry_block)

    def _root_blocks(self):
        inner_loop_region = set()
        for c in self.scope.loop_nest_tree.get_children_of(self.scope.entry_block):
            inner_loop_region = inner_loop_region.union(set(c.region))
        all_blks = set()
        self.scope.entry_block.collect_basic_blocks(all_blks)
        return all_blks.difference(inner_loop_region)

    def _process(self, blk):
        children = []
        for c in self.scope.loop_nest_tree.get_children_of(blk):
            children.append(self._process(c))

        if blk is self.scope.loop_nest_tree.root:
            blocks = sorted(list(self._root_blocks()), key=lambda b: b.order)
            dfg = self._make_graph(blk.name, blocks)
        else:
            blocks = [blk.head]
            for b in blk.bodies:
                if not isinstance(b, CompositBlock):
                    blocks.append(b)
            dfg = self._make_graph(blk.name, blocks)
        self._add_mem_edges(dfg)
        self._add_object_edges(dfg)
        self._add_special_seq_edges(dfg)
        for child in children:
            dfg.set_child(child)
        #self._dump_dfg(dfg)
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


    def _make_graph(self, name, blocks):
        logger.debug('make graph ' + name)
        dfg = DataFlowGraph(name, blocks)
        usedef = self.scope.usedef

        for b in blocks:
            for stm in b.stms:
                logger.log(0, 'loop head ' + name + ' :: ' + str(stm))
                usenode = dfg.add_stm_node(stm)
                
                # collect source nodes
                self._add_source_node(usenode, dfg, usedef, blocks)

                # add edges
                for v in usedef.get_use_vars_by_stm(stm):
                    defstms = usedef.get_def_stms_by_sym(v.symbol())
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

        if self.scope.is_testbench():
            self._add_edges_between_calls(blocks, dfg)
        return dfg


    def _add_source_node(self, node, dfg, usedef, blocks):
        stm = node.tag
        usevars = usedef.get_use_vars_by_stm(stm)
        if not usevars and stm.is_a(MOVE):
            dfg.src_nodes.add(node)
            return
        for v in usevars:
            if v.symbol().is_param():
                dfg.src_nodes.add(node)
                return
            defstms = usedef.get_def_stms_by_sym(v.symbol())
            for defstm in defstms:
                # this definition stm is in the out of the section
                if defstm.block not in blocks:
                    dfg.src_nodes.add(node)
                    return

        uses = usedef.get_use_consts_by_stm(stm)
        if uses:
            if self._is_constant_stm(stm):
                logger.log(0, 'add src: $use const ' + str(stm))
                dfg.src_nodes.add(node)
                return

        def has_mem_arg(args):
            for a in args:
                if a.is_a(TEMP) and Type.is_list(a.symbol().typ):
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


    def _is_constant_stm(self, stm):
        if stm.is_a(PHI):
            return True
        elif stm.is_a(MOVE):
            if stm.src.is_a([CONST, ARRAY, CALL]):
                return True
            elif stm.src.is_a(MSTORE) and stm.src.offset.is_a(CONST) and stm.src.exp.is_a(CONST):
                return True
            elif stm.src.is_a(MREF) and stm.src.offset.is_a(CONST):
                return True
            elif stm.src.is_a(SYSCALL):
                syscall = stm.src
                if syscall.name == 'read_reg':
                    return True
        elif stm.is_a(EXPR):
            if stm.exp.is_a([CALL, SYSCALL]):
                call = stm.exp
                return all(a.is_a(CONST) for a in call.args)
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
        return (node.tag.block.order, node.tag.block.stms.index(node.tag))

    def _add_mem_edges(self, dfg):
        node_groups = defaultdict(list)
        for node in dfg.nodes:
            if node.tag.is_a(MOVE):
                mv = node.tag
                if mv.src.is_a([MREF, MSTORE]):
                    mem_group = mv.src.mem.symbol().name
                    node_groups[mem_group].append(node)
                elif mv.src.is_a(CALL):
                    for arg in mv.src.args:
                        if arg.is_a(TEMP) and Type.is_list(arg.symbol().typ):
                            mem_group = arg.symbol().name
                            node_groups[mem_group].append(node)
            elif node.tag.is_a(EXPR):
                expr = node.tag
                if expr.exp.is_a(CALL):
                    for arg in expr.exp.args:
                        if arg.is_a(TEMP) and Type.is_list(arg.symbol().typ):
                            mem_group = arg.symbol().name
                            node_groups[mem_group].append(node)
        for nodes in node_groups.values():
            sorted_nodes = sorted(nodes, key=self._node_order_by_ctrl)
            for i in range(len(sorted_nodes)-1):
                n1 = sorted_nodes[i]
                n2 = sorted_nodes[i+1]
                dfg.add_seq_edge(n1, n2)


    def _add_edges_between_calls(self, blocks, dfg):
        """this function is used for testbench only"""
        all_stms_in_section = self._all_stms(blocks)
        all_calls = []
        for stm in all_stms_in_section:
            if stm.is_a(MOVE) and stm.src.is_a(CALL):
                all_calls.append(stm)
            elif stm.is_a(EXPR) and stm.exp.is_a(CALL):
                all_calls.append(stm)
        for stm in all_calls:
            callnode = dfg.add_stm_node(stm)
            for stm2 in all_calls:
                if stm is stm2:
                    continue
                blk = stm.block
                blk2 = stm2.block
                if ((blk is not blk2) and (blk.order < blk2.order)) or \
                ((blk is blk2) and (blk.stms.index(stm) < blk2.stms.index(stm2))):
                    othernode = dfg.add_stm_node(stm2)
                    dfg.add_seq_edge(callnode, othernode)

    def _add_object_edges(self, dfg):
        def add_node_group_if_needed(ir, node, node_groups):
            if ir.is_a(ATTR):
                node_groups[ir.symbol()].add(node)
                add_node_group_if_needed(ir.exp, node, node_groups)
            elif ir.is_a(TEMP) and Type.is_object(ir.symbol().typ):
                node_groups[ir.symbol()].add(node)

        node_groups = defaultdict(set)
        for node in dfg.nodes:
            if node.tag.is_a(MOVE) or node.tag.is_a(EXPR):
                stm = node.tag
                for kid in stm.kids():
                    add_node_group_if_needed(kid, node, node_groups)

        for nodes in node_groups.values():
            sorted_nodes = sorted(nodes, key=self._node_order_by_ctrl)
            for i in range(len(sorted_nodes)-1):
                n1 = sorted_nodes[i]
                n2 = sorted_nodes[i+1]
                dfg.add_seq_edge(n1, n2)

    # workaround
    def _add_special_seq_edges(self, dfg):
        for node in dfg.nodes:
            if node.tag.is_a([JUMP, CJUMP, MCJUMP]):
                stm = node.tag
                assert len(stm.block.stms) > 1
                assert stm.block.stms[-1] is stm
                idx = stm.block.stms.index(stm)
                for prev_stm in stm.block.stms[:-1]:
                    prev_node = dfg.find_node(prev_stm)
                    dfg.add_seq_edge(prev_node, node)
