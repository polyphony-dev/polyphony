from collections import deque, defaultdict
from .varreplacer import VarReplacer
from .ir import *
from .symbol import Symbol, function_name
from .type import Type
from .irvisitor import IRTransformer, IRVisitor
from .env import env
from .scope import Scope
from logging import getLogger
logger = getLogger(__name__)


class MemRefNode:
    SRC  = 0x00000001
    WR   = 0x00000002

    id = 0
    def __init__(self, sym, scope):
        self.sym = sym
        self.scope = scope
        self.flags = 0
        self.width = 32 # TODO
        self.length = -1
        self.initstm = None
        self.param_index = -1
        self.preds = set()
        self.succs = set()
        self.object_sym = None

    def __str__(self):
        s = '{}{}:'.format(self.sym, self.scope.name)
        s += '[{}]:flags={}:ref={}:initstm={}\n'.format(self.length, self.flags, self.param_index, self.initstm)
        s += '\tpreds\n'
        s += '\t\t'+', '.join(['{}{}'.format(pred.sym, pred.scope.name) for pred in self.preds])
        s += '\n'
        s += '\tsuccs\n'
        s += '\t\t'+', '.join(['{}{}'.format(succ.sym, succ.scope.name) for succ in self.succs])
        s += '\n'
        return s

    def __repr__(self):
        return self.__str__()

    def __lt__(self, other):
        return self.sym < other.sym

    def add_pred(self, pred):
        self.preds.add(pred)
        max_length = max([p.length for p in self.preds])
        self.length = max_length

    def add_succ(self, succ):
        self.succs.add(succ)

    def propagate_preds(self, fn):
        fn(self)
        for s in self.preds:
            s.propagate_preds(fn)

    def propagate_succs(self, fn):
        fn(self)
        for s in self.succs:
            s.propagate_succs(fn)

    def set_initstm(self, initstm):
        assert initstm
        assert initstm.is_a(MOVE) and initstm.src.is_a(ARRAY)
        self.length = len(initstm.src.items)
        self.flags |= MemRefNode.SRC
        self.initstm = initstm

    def set_writable(self):
        self.flags |= MemRefNode.WR

    def is_source(self):
        return self.flags & MemRefNode.SRC

    def is_writable(self):
        return self.flags & MemRefNode.WR

    def is_joinable(self):
        return len(self.preds) > 1

    def is_forkable(self):
        return len(self.succs) > 1

    def set_param_index(self, index):
        self.param_index = index

    def is_param(self):
        return self.param_index != -1

        
class MemRefGraph:
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.instance_edges = {}

    def __str__(self):
        s = 'MemRefGraph\n'
        for node in self.nodes.values():
            s += str(node)
        for (src, dst), inst_name in self.instance_edges.items():
            s += '{} => {}:{}\n'.format(src, inst_name, dst)
        return s
        
    def add_node(self, node):
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

    def add_instance_edge(self, src, dst, inst_name):
        self.instance_edges[(src.sym, dst.sym)] = inst_name

    def remove_node(self, node):
        logger.debug('remove_node ' + str(node))
        for pred in node.preds:
            pred.succs.remove(node)
        for succ in node.succs:
            succ.preds.remove(node)
        del self.nodes[node.sym]

    def collect_roots(self):
        for node in self.nodes.values():
            if not node.preds:
                yield node

    def collect_node_roots(self, node):
        if not node.preds:
            yield node
        for pred in node.preds:
            for n in self.collect_node_roots(pred):
                yield n

    def collect_writable(self, scope):
        for node in filter(lambda n: n.scope is scope, self.nodes.values()):
            if node.is_writable():
                yield node

    def collect_readonly(self, scope):
        for node in filter(lambda n: n.scope is scope, self.nodes.values()):
            if not node.is_writable():
                yield node

    def collect_inst_succs(self, node):
        for (src, dst), inst_name in self.instance_edges.items():
            if src is node.sym:
                yield inst_name, self.node(dst)

    def collect_inst_preds(self, node):
        for (src, dst), inst_name in self.instance_edges.items():
            if dst is node.sym:
                yield inst_name, self.node(src)

    def collect_top_module_nodes(self):
        for node in self.nodes.values():
            if node.scope.is_testbench():
                for succ in node.succs:
                    yield succ

    def find_param_node(self, scope, param_index):
        assert len(scope.params) > param_index
        p, _, _ = scope.params[param_index]
        assert Type.is_list(p.typ)
        memnode = Type.extra(p.typ)
        assert memnode is not None
        return memnode

    def get_single_root(self, node):
        roots = [root for root in self.collect_node_roots(node)]
        if len(roots) > 1:
            return None
        return roots[0]

    def get_length(self, node):
        root = self.get_single_root(node)
        if root:
            return root.length
        else:
            return -1

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

    def process_all(self):
        scopes = Scope.get_scopes(bottom_up=True, contain_global=True, contain_class=True)
        for s in scopes:
            self.process(s)
        for sym, dst in self.edges:
            src = self.mrg.node(sym)
            self.mrg.add_edge(src, dst)
                
    def visit_CALL(self, ir):
        for i, arg in enumerate(ir.args):
            if arg.is_a(TEMP) and Type.is_list(arg.sym.typ):
                param_node = self.mrg.find_param_node(ir.func_scope, i)
                self.edges.append((arg.sym, param_node))

    def visit_MREF(self, ir):
        if ir.mem.is_a(TEMP):
            memsym = ir.mem.sym
        elif ir.mem.is_a(ATTR):
            memsym = ir.mem.attr

        if Type.is_list(memsym.typ):
            if memsym.scope.is_global() or memsym.scope.is_class():
                # we have to create a new list symbol for adding the memnode
                # because the list symbol in the global or a class (memsym) is
                # used for the source memnode
                memsym = self.scope.inherit_sym(memsym, memsym.name + '#0')
                self.mrg.add_node(MemRefNode(memsym, self.scope))
                memnode = self.mrg.node(memsym)
                self.edges.append((memsym.ancestor, memnode))
                memsym.typ = Type.list(Type.int_t, memnode)

                if ir.mem.is_a(TEMP):
                    ir.mem.sym = memsym
                elif ir.mem.is_a(ATTR):
                    ir.mem.attr = memsym
                    memnode.object_sym = ir.mem.tail()

    def visit_MSTORE(self, ir):
        if ir.mem.is_a(TEMP):
            memsym = ir.mem.sym
        elif ir.mem.is_a(ATTR):
            memsym = ir.mem.attr
        memnode = Type.extra(memsym.typ)
        memnode.set_writable()

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

    def visit_RET(self, ir):
        self.visit(ir.exp)

    def visit_MOVE(self, ir):
        self.visit(ir.src)
        self.visit(ir.dst)

        if ir.dst.is_a(TEMP):
            memsym = ir.dst.sym
        elif ir.dst.is_a(ATTR):
            memsym = ir.dst.attr

        if ir.src.is_a(ARRAY):
            assert Type.is_list(memsym.typ)
            self.mrg.add_node(MemRefNode(memsym, self.scope))
            memnode = self.mrg.node(memsym)
            memnode.set_initstm(ir)
            if not all(item.is_a(CONST) for item in ir.src.items):
                memnode.set_writable()
            memsym.set_type(Type.list(Type.int_t, memnode))
        elif ir.src.is_a(TEMP) and ir.src.sym.is_param() and Type.is_list(ir.src.sym.typ):
            param = ir.src.sym
            self.mrg.add_node(MemRefNode(memsym, self.scope))
            memnode = self.mrg.node(memsym)
            memnode.set_param_index(self.scope.get_param_index(param))
            param.set_type(Type.list(Type.int_t, memnode))
            memsym.set_type(Type.list(Type.int_t, memnode))
        elif ir.src.is_a(ATTR) and Type.is_list(ir.src.attr.typ):
            param = ir.src.sym
            self.mrg.add_node(MemRefNode(memsym, self.scope))
            memnode = self.mrg.node(memsym)
            memnode.set_param_index(self.scope.get_param_index(param))
            param.set_type(Type.list(Type.int_t, memnode))
            memsym.set_type(Type.list(Type.int_t, memnode))


    def visit_PHI(self, ir):
        if Type.is_list(ir.var.sym.typ):
            self.mrg.add_node(MemRefNode(ir.var.sym, self.scope))
            memnode = self.mrg.node(ir.var.sym)
            for arg, blk in ir.args:
                self.edges.append((arg.sym, memnode))
            ir.var.sym.set_type(Type.list(Type.int_t, memnode))


class MemRefEdgeColoring:
    def __init__(self):
        self.mrg = env.memref_graph

    def process(self, scope):
        self.scope = scope
        for dfg in scope.dfgs(bottom_up=False):
            for node in dfg.get_scheduled_nodes():
                if node.is_stm():
                    self.visit(node.tag, node)

    def visit_CALL(self, ir, node):
        if ir.func.is_a(TEMP):
            func_name = function_name(ir.func.sym)
        elif ir.func.is_a(ATTR):
            func_name = ir.func.attr.name
        inst_name = '{}_{}'.format(func_name, node.instance_num)
        
        for i, arg in enumerate(ir.args):
            assert arg.is_a([TEMP, CONST, UNOP, ARRAY])
            if arg.is_a(TEMP) and Type.is_list(arg.sym.typ):
                p, _, _ = ir.func_scope.params[i]
                assert Type.is_list(p.typ)
                param_memnode = Type.extra(p.typ)
                memnode = self.mrg.node(arg.sym)
                # param memnode might be removed in the rom elimination of ConstantFolding
                if self.mrg.is_live_node(param_memnode):
                    assert param_memnode in memnode.succs
                    self.mrg.add_instance_edge(memnode, param_memnode, inst_name)

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
        if ir.mem.is_a(TEMP):
            memnode = Type.extra(ir.mem.sym.typ)
        elif ir.mem.is_a(ATTR):
            memnode = Type.extra(ir.mem.attr.typ)
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
