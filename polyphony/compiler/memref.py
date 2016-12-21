from collections import deque, defaultdict
from .varreplacer import VarReplacer
from .ir import *
from .symbol import Symbol
from .type import Type
from .irvisitor import IRTransformer, IRVisitor
from .env import env
from .scope import Scope
from .utils import replace_item
from logging import getLogger
logger = getLogger(__name__)
import pdb

class RefNode:
    PARAM = 0x00000001

    def __init__(self, sym, scope):
        self.sym = sym
        self.scopes = set()
        if scope:
            self.scopes.add(scope)
        self.preds = []
        self.succs = []
        self.order = -1
        self.flags = 0

    def __str__(self):
        scope_names = ', '.join([s.name for s in self.scopes])
        s = '{}: {} {} {}\n'.format(self.__class__.__name__, self.sym.name, scope_names, self._str_properties())
        s += '\tpreds\n'
        s += '\t\t'+', '.join(['{}'.format(pred.sym) for pred in self.preds])
        s += '\n'
        s += '\tsuccs\n'
        s += '\t\t'+', '.join(['{}'.format(succ.sym) for succ in self.succs])
        s += '\n'
        return s

    def __repr__(self):
        return self.sym.name

    def __lt__(self, other):
        return self.sym < other.sym

    def name(self):
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

    def sibling_nodes(self):
        siblings = []
        for pred in self.preds:
            siblings.extend([s for s in pred.succs if s is not self])
        return siblings

    def pred_branch(self):
        if not self.preds:
            return None
        if len(self.preds) > 1:
            return self
        else:
            return self.preds[0].pred_branch()

    def succ_branch(self):
        if not self.succs:
            return None
        if len(self.succs) > 1:
            return self
        else:
            return self.suucs[0].succ_branch()

    def find_in_preds(self, node):
        for i, p in enumerate(self.preds):
            if p is node:
                return i
            if p.find_in_preds(node) >= 0:
                return i
        return -1

    def is_source(self):
        return not self.preds

    def is_sink(self):
        return not self.succs

    def is_joinable(self):
        branch = self.pred_branch()
        if branch is None:
            return False
        if self.scopes.intersection(branch.scopes):
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
        return scope in self.scopes

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


class JointNode(RefNode):
    def __init__(self, sym, scope):
        super().__init__(sym, scope)
        self.orig_preds = []
        self.orig_succs = []

    def add_pred(self, pred):
        if pred not in self.preds:
            self.preds.append(pred)
        if pred not in self.orig_preds:
            self.orig_preds.append(pred)

    def add_succ(self, succ):
        if succ not in self.succs:
            self.succs.append(succ)
        if succ not in self.orig_succs:
            self.orig_succs.append(succ)

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
    def __init__(self, succ):
        super().__init__(Symbol.new('n2o_' + succ.sym.hdl_name(), None), None)
        self.succs = [succ]
        self.orig_succs = [succ]

    def pred_ref_nodes(self):
        assert len(self.preds) > 1
        return super().pred_ref_nodes()

    def succ_ref_nodes(self):
        assert len(self.succs) == 1
        return super().succ_ref_nodes()


class One2NNode(JointNode):
    def __init__(self, pred):
        super().__init__(Symbol.new('o2n_' + pred.sym.hdl_name(), None), None)
        self.preds = [pred]
        self.orig_preds = [pred]

    def pred_ref_nodes(self):
        assert len(self.preds) == 1
        return super().pred_ref_nodes()

    def succ_ref_nodes(self):
        assert len(self.succs) > 1
        return super().succ_ref_nodes()


class MemTrait:
    WR    = 0x00010000
    IM    = 0x00020000

    def __init__(self):
        self.width = 32 # TODO
        self.length = -1

    def set_writable(self):
        self.flags |= MemTrait.WR

    def set_immutable(self):
        self.flags |= MemTrait.IM

    def set_length(self, length):
        self.length = length

    def is_writable(self):
        return self.flags & MemTrait.WR

    def is_immutable(self):
        return self.flags & MemTrait.IM

    def addr_width(self):
        return (self.length-1).bit_length()+1 # +1 means sign bit


class MemRefNode(RefNode, MemTrait):
    def __init__(self, sym, scope):
        RefNode.__init__(self, sym, scope)
        MemTrait.__init__(self)
        self.initstm = None

    def _str_properties(self):
        s = ' <{}>[{}] '.format(self.width, self.length)
        s += 'wr ' if self.is_writable() else 'ro '
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

class MemParamNode(RefNode, MemTrait):
    def __init__(self, sym, scope):
        RefNode.__init__(self, sym, scope)
        MemTrait.__init__(self)

    def _str_properties(self):
        s = ' <{}>[{}] '.format(self.width, self.length)
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
    def __init__(self, succ):
        N2OneNode.__init__(self, succ)
        MemTrait.__init__(self)

    def _str_properties(self):
        s = ' <{}>[{}] '.format(self.width, self.length)
        s += 'wr ' if self.is_writable() else 'ro '
        return s

    def update(self):
        self.length = max([p.length for p in self.preds])
        for p in self.preds:
            self.scopes = p.scopes.union(self.scopes)

        if self.preds[0].is_immutable():
            self.set_immutable()

class One2NMemNode(One2NNode, MemTrait):
    def __init__(self, pred):
        One2NNode.__init__(self, pred)
        MemTrait.__init__(self)

    def _str_properties(self):
        s = ' <{}>[{}] '.format(self.width, self.length)
        s += 'wr ' if self.is_writable() else 'ro '
        return s

    def update(self):
        if self.preds and self.length < self.preds[0].length:
            self.length = self.preds[0].length
        self.scopes = self.preds[0].scopes.union(self.scopes)

        if self.preds[0].is_immutable():
            self.set_immutable()

class MemRefGraph:
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.param_node_instances = defaultdict(set)

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
        if isinstance(node, list):
            for n in node:
                self.remove_node(n)
        else:
            logger.debug('remove_node ' + str(node.sym))
            for pred in node.preds:
                pred.succs.remove(node)
            for succ in node.succs:
                succ.preds.remove(node)
            del self.nodes[node.sym]

    def collect_sources(self):
        for node in self.nodes.values():
            if node.is_source():
                assert not node.preds
                assert isinstance(node, MemRefNode)
                yield node

    def scope_nodes(self, scope):
        return filter(lambda n: n.is_in_scope(scope), self.nodes.values())

    def collect_ram(self, scope):
        for node in self.scope_nodes(scope):
            if node.is_writable() and not node.is_immutable():
                yield node

    def collect_immutable(self, scope):
        for node in self.scope_nodes(scope):
            if node.is_immutable():
                yield node

    def collect_readonly_sink(self, scope):
        for node in self.scope_nodes(scope):
            if isinstance(node, MemRefNode) and not node.is_writable() and node.is_sink():
                yield node

    def collect_joint(self, scope):
        for node in self.scope_nodes(scope):
            if isinstance(node, JointNode):
                yield node

    def collect_top_module_nodes(self):
        for node in self.nodes.values():
            for s in node.scopes:
                if s.is_testbench():
                    for succ in node.succ_ref_nodes():
                        yield succ

    def verify_nodes(self):
        for node in self.nodes.values():
            assert node.scopes

    def is_path_exist(self, frm, to):
        for succ in frm.succs:
            if succ is to:
                return True
            if self.is_path_exist(succ, to):
                return True
        return False

    def is_live_node(self, node):
        return node.sym in self.nodes


class MemRefGraphBuilder(IRVisitor):
    def __init__(self):
        super().__init__()
        self.mrg = env.memref_graph = MemRefGraph()
        self.edges = []
        self.edge_srcs = defaultdict(set)

    def _collect_def_mem_stms(self, scope):
        stms = []
        for block in scope.traverse_blocks():
            for stm in block.stms:
                if stm.is_a(MOVE):
                    if stm.src.is_a(ARRAY):
                        stms.append(stm)
                    elif stm.src.is_a(TEMP) and stm.src.sym.is_param() and Type.is_seq(stm.src.sym.typ):
                        stms.append(stm)

        for block in scope.traverse_blocks():
            for stm in block.stms:
                # phi is always
                if stm.is_a(MOVE):
                    if stm.dst.is_a([TEMP, ATTR]) and Type.is_seq(stm.dst.symbol().typ) and stm not in stms:
                        stms.append(stm)
                elif stm.is_a(PHI):
                    if stm.var.is_a(TEMP) and Type.is_seq(stm.var.sym.typ):
                        stms.append(stm)
        return stms

    def process_all(self):
        scopes = Scope.get_scopes(bottom_up=True, contain_global=True, contain_class=True)
        worklist = deque()
        #usedefs = [s.usedef for s in scopes]
        for s in scopes:
            if s.is_ctor():
                listtypes = [f for f, init_stm in s.parent.class_fields.items() if Type.is_seq(f.typ)]
                if listtypes:
                    pass

            usedef = s.usedef
            # collect the access to a local list variable
            stms = self._collect_def_mem_stms(s)
            worklist.extend(stms)
            for stm in stms:
                logger.debug('!!! mem def stm ' + str(stm))
                if stm.is_a(MOVE):
                    memsym = stm.dst.symbol()
                elif stm.is_a(PHI):
                    memsym = stm.var.sym
                
                uses = usedef.get_use_stms_by_sym(memsym)
                uses = uses.difference(set(worklist))
                worklist.extend(list(uses))
            # collect the access to a global list variable
            for sym in usedef.get_all_use_syms():
                if (sym.scope.is_global() or sym.scope.is_class()) and Type.is_seq(sym.typ):
                    uses = usedef.get_use_stms_by_sym(sym)
                    worklist.extend(list(uses))

        while worklist:
            stm = worklist.popleft()
            self.scope = stm.block.scope
            self.current_stm = stm
            self.visit(stm)

        # create joint node
        n2one_node_map = {}
        one2n_node_map = {}
        for src_sym, dst_sym in reversed(self.edges):
            src = self.mrg.node(src_sym)
            dst = self.mrg.node(dst_sym)

            if dst not in n2one_node_map:
                n2one_node_map[dst] = N2OneMemNode(dst)
            n2one_node_map[dst].add_pred(src)

            if src not in one2n_node_map:
                one2n_node_map[src] = One2NMemNode(src)
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
        # do a ref-to-ref node branching
        self._do_ref_2_ref_node_branching()

        self._propagate_info()
        self.mrg.verify_nodes()

    def _do_ref_2_ref_node_branching(self):
        new_nodes = []
        for node in self.mrg.sorted_nodes():
            if isinstance(node, MemRefNode) and not node.is_source() and not node.is_param() and node.succs:
                assert len(node.preds) == 1
                assert len(node.succs) == 1
                if isinstance(node.succs[0], One2NMemNode):
                    o2n = node.succs[0]
                    o2n.add_succ(node)
                    replace_item(o2n.preds, node, node.preds[0])
                    replace_item(node.preds[0].succs, node, o2n)
                else:
                    pred = node.preds[0]
                    o2n = One2NMemNode(pred)
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
        srcnode = self.mrg.node(src)
        self.edge_srcs[dst].add(src)
        if (src, dst) not in self.edges:
            self.edges.append((src, dst))

    def visit_CALL(self, ir):
        for i, arg in enumerate(ir.args):
            if arg.is_a(TEMP) and Type.is_seq(arg.sym.typ):
                p, _, _ = ir.func_scope.params[i]
                self._append_edge(arg.sym, p)

    def visit_TEMP(self, ir):
        if ir.sym.is_param():
            if Type.is_seq(ir.sym.typ):
                memsym = ir.sym
                self.mrg.add_node(MemParamNode(memsym, self.scope))
                memnode = self.mrg.node(memsym)
                if Type.is_list(ir.sym.typ):
                    memsym.set_type(Type.list(Type.int_t, memnode))
                else:
                    memsym.set_type(Type.tuple(Type.int_t, memnode, Type.length(ir.sym.typ)))
       
    def visit_ARRAY(self, ir):
        ir.sym = self.scope.add_temp('array')
        self.mrg.add_node(MemRefNode(ir.sym, self.scope))
        memnode = self.mrg.node(ir.sym)
        memnode.set_initstm(self.current_stm)

        if not all(item.is_a(CONST) for item in ir.items):
            memnode.set_writable()
        # TODO: element type
        if ir.is_mutable:
            ir.sym.set_type(Type.list(Type.int_t, memnode))
        else:
            memnode.set_immutable()
            ir.sym.set_type(Type.tuple(Type.int_t, memnode, len(ir.items)))

    def visit_MREF(self, ir):
        memsym = ir.mem.symbol()
        if Type.is_seq(memsym.typ):
            if memsym.scope.is_global() or (ir.mem.is_a(ATTR) and Type.is_class(ir.mem.head().typ)):
                # we have to create a new list symbol for adding the memnode
                # because the list symbol in the global or a class (memsym) is
                # used for the source memnode
                memsym = self.scope.inherit_sym(memsym, memsym.orig_name() + '#0')
                self.mrg.add_node(MemRefNode(memsym, self.scope))
                self._append_edge(memsym.ancestor, memsym)
                memsym.typ = Type.list(Type.int_t, self.mrg.node(memsym))
                ir.mem.set_symbol(memsym)
        
        memnode = self.mrg.node(memsym)
        if not memnode and memsym.is_ref():
            self.mrg.add_node(MemRefNode(memsym, self.scope))
            self._append_edge(memsym.ancestor, memsym)
            memsym.typ = Type.list(Type.int_t, self.mrg.node(memsym))

    def visit_MSTORE(self, ir):
        memsym = ir.mem.symbol()
        memnode = self.mrg.node(memsym)
        if memnode:
            memnode.set_writable()
        elif memsym.is_ref():
            self.mrg.add_node(MemRefNode(memsym, self.scope))
            self._append_edge(memsym.ancestor, memsym)
            memsym.typ = Type.list(Type.int_t, self.mrg.node(memsym))
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
        if ir.src.is_a(ARRAY):
            self.mrg.add_node(MemRefNode(memsym, self.scope))
            memnode = self.mrg.node(memsym)
            elem_t = Type.element(memsym.typ)
            if Type.is_list(memsym.typ):
                memsym.set_type(Type.list(elem_t, memnode))
            else:
                memsym.set_type(Type.tuple(elem_t, memnode, Type.length(memsym.typ)))
            self._append_edge(ir.src.sym, memsym)
        elif ir.src.is_a(TEMP) and ir.src.sym.is_param() and Type.is_seq(ir.src.sym.typ):
            self.mrg.add_node(MemRefNode(memsym, self.scope))
            memnode = self.mrg.node(memsym)
            elem_t = Type.element(memsym.typ)
            if Type.is_list(memsym.typ):
                memsym.set_type(Type.list(elem_t, memnode))
            else:
                memsym.set_type(Type.tuple(elem_t, memnode, Type.length(memsym.typ)))
            self._append_edge(ir.src.sym, memsym)
        elif ir.src.is_a(ATTR) and Type.is_seq(ir.src.attr.typ):
            assert 0


    def visit_PHI(self, ir):
        if Type.is_seq(ir.var.sym.typ):
            self.mrg.add_node(MemRefNode(ir.var.sym, self.scope))
            for arg in ir.args:
                self._append_edge(arg.sym, ir.var.sym)
            memnode = self.mrg.node(ir.var.sym)
            elem_t = Type.element(ir.var.sym.typ)
            if Type.is_list(ir.var.sym.typ):
                ir.var.sym.set_type(Type.list(elem_t, memnode))
            else:
                ir.var.sym.set_type(Type.tuple(elem_t, memnode, Type.length(ir.var.sym.typ)))

class MemInstanceGraphBuilder:
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
        
        for i, arg in enumerate(ir.args):
            assert arg.is_a([TEMP, CONST, UNOP, ARRAY])
            if arg.is_a(TEMP) and Type.is_seq(arg.sym.typ):
                p, _, _ = ir.func_scope.params[i]
                assert Type.is_seq(p.typ)
                param_node = Type.extra(p.typ)
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

#TODO
class NodeEliminator(IRVisitor):
    def __init__(self):
        self.mrg = env.memref_graph
        self.used_memnodes = set()

    def process(self, scope):
        if scope.is_testbench():
            return
        super().process(scope)
        if env.compile_phase >= env.PHASE_3:
            self._remove_unused_readonly_memnode()

    def visit_CALL(self, ir):
        for arg in ir.args:
            if arg.is_a(TEMP) and Type.is_list(arg.sym.typ):
                memnode = self.mrg.node(arg.sym)
                self.used_memnodes.add(memnode)

    def visit_MREF(self, ir):
        memnode = Type.extra(ir.mem.symbol().typ)
        self.used_memnodes.add(memnode)

    def visit_MSTORE(self, ir):
        memnode = Type.extra(ir.mem.sym.typ)
        self.used_memnodes.add(memnode)


    def visit_TEMP(self, ir):
        if Type.is_list(ir.sym.typ) and self.scope.is_class():
            memnode = Type.extra(ir.sym.typ)
            assert memnode
            self.used_memnodes.add(memnode)

    def _remove_unused_readonly_memnode(self):
        self_readonly_memnodes = set([n for n in self.mrg.nodes.values() if n.scope is self.scope and not n.is_writable()])
        for unused in self_readonly_memnodes.difference(self.used_memnodes):
            for used in self.used_memnodes:
                if self.mrg.is_path_exist(unused, used):
                    break
            else:
                self.mrg.remove_node(unused)
                if unused in self.array_inits:
                    stm = self.array_inits[unused]
                    stm.block.stms.remove(stm)

