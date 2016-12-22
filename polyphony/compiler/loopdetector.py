from collections import deque
from .dominator import DominatorTreeBuilder
from .ir import CONST, BINOP, RELOP, TEMP, MOVE, JUMP, CJUMP
from .varreplacer import VarReplacer
from .usedef import UseDefDetector
from .block import Block, CompositBlock
from logging import getLogger
logger = getLogger(__name__)

class LoopNestTree:
    def __init__(self):
        self.nodes = []
        self.edges = []
        self.root = None

    def set_root(self, n):
        self.root = n

    def add_node(self, n):
        if n not in self.nodes:
            self.nodes.append(n)
        return n

    def add_edge(self, n1, n2):
        edge = (n1, n2)
        if edge not in self.edges:
            self.edges.append(edge)

    def is_child(self, loop_head1, loop_head2):
        for h1, h2 in self.edges:
            if loop_head1 is h1 and loop_head2 is h2:
                return True
        return False

    def get_children_of(self, loop_head):
        children = []
        for h1, h2 in self.edges:
            if loop_head is h1:
                children.append(h2)
        return children

    def get_parent_of(self, loop_head):
        for h1, h2 in self.edges:
            if loop_head is h2:
                return h1
        return None

    def dump(self):
        logger.debug('loop nest tree')
        for n1, n2 in sorted(self.edges, key=lambda n: n[0].name):
            logger.debug(n1.name + ' --> ' + n2.name)

    def __str__(self):
        s = ''
        for n1, n2 in sorted(self.edges, key=lambda n: n[0].name):
            s += n1.name + ' --> ' + n2.name + '\n'
        return s

    def traverse(self):
        stack = []
        self._traverse_rec(self.root, stack)
        return stack

    def _traverse_rec(self, node, stack):
        children = self.get_children_of(node)
        for child in children:
            self._traverse_rec(child, stack)
        stack.append(node)


class LoopDetector:
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope
        scope.loop_nest_tree = LoopNestTree()

        ordered_blks = []
        visited = []
        head = scope.entry_block
        self._process_walk(head, ordered_blks, visited)
        assert head is ordered_blks[-1]

        lblks, blks = self._make_loop_block_bodies(ordered_blks)

        self._add_loop_tree_entry(head, lblks)
        self.scope.loop_nest_tree.set_root(head)

        ldd = LoopDependencyDetector()
        ldd.processs(scope)

        #lbd = LoopBlockDestructor()
        #lbd.process(scope)


    def _make_loop_block(self, head, loop_region):
        lblks, blks = self._make_loop_block_bodies(loop_region)
        bodies = sorted(lblks+blks, key=lambda b: b.order)
        lb = CompositBlock(self.scope, head, bodies, [head]+loop_region)

        self._add_loop_tree_entry(lb, lblks)

        return lb

    def _make_loop_block_bodies(self, blks):
        sccs = self._extract_sccs(blks)
        lblks = []
        for scc in sccs:
            head = scc.pop()
            loop_region = scc

            # shrink blocks
            blks = [b for b in blks if b is not head and b not in loop_region]
            assert blks

            lb = self._make_loop_block(head, loop_region)
            lblks.append(lb)

            # re-connect
            for p in lb.preds:
                p.replace_succ(lb.head, lb)
            for s in lb.succs:
                s.replace_pred([lb.head] + lb.bodies, lb)

        return lblks, blks

    def _extract_sccs(self, ordered_blks):
        sccs = []
        for scc in self._find_scc(ordered_blks[:]):
            if len(scc) > 1:
                # we have to keep the depth-first-search order
                blks = [b for b in ordered_blks if b in scc]
                sccs.append(blks)
        return sccs

    # 'scc' is 'strongly connected components'
    def _find_scc(self, blks):
        sccs = []
        visited = []
        while blks:
            blk = blks[-1]
            scc = []
            self._process_back_walk(blk, blks, visited, scc)
            sccs.append(scc)
        return sccs

    def _process_walk(self, blk, blks, visited):
        visited.append(blk)
        if blk.succs:
            for succ in blk.succs:
                if succ not in visited:
                    self._process_walk(succ, blks, visited)
        blks.append(blk)

    def _process_back_walk(self, blk, blks, visited, scc):
        scc.append(blk)
        visited.append(blk)
        blks.remove(blk)
        for pred in blk.preds:
            if pred not in visited and pred in blks:
                self._process_back_walk(pred, blks, visited, scc)

    def _add_loop_tree_entry(self, parent, children):
        self.scope.loop_nest_tree.add_node(parent)
        for child in children:
            self.scope.loop_nest_tree.add_edge(parent, child)

# hierarchize
class LoopDependencyDetector:
    def processs(self, scope):
        all_blks = set()
        scope.entry_block.collect_basic_blocks(all_blks)
        for lb in scope.loop_nest_tree.traverse():
            if lb is scope.loop_nest_tree.root:
                break
            outer_region = all_blks.difference(set(lb.region))
            inner_region = set(lb.region).difference(set([lb.head])).difference(set(lb.bodies))
            od, ou, id, iu = self._get_loop_block_dependency(scope.usedef, lb, outer_region, inner_region)
            lb.outer_defs = od
            lb.outer_uses = ou
            lb.inner_defs = id
            lb.inner_uses = iu

    def _get_loop_block_dependency(self, usedef, lb, outer_region, inner_region):
        outer_defs = set()
        outer_uses = set()
        inner_defs = set()
        inner_uses = set()
        blocks = [lb.head] + lb.bodies
        for blk in blocks:
            usesyms = usedef.get_use_syms_by_blk(blk)
            for sym in usesyms:
                defblks = usedef.get_def_blks_by_sym(sym)
                # Is this symbol used in the out of the loop?
                intersect = outer_region.intersection(defblks)
                if intersect:
                    outer_defs.add(sym)
                intersect = inner_region.intersection(defblks)
                if intersect:
                    inner_defs.add(sym)

            defsyms = usedef.get_def_syms_by_blk(blk)
            for sym in defsyms:
                useblks = usedef.get_use_blks_by_sym(sym)
                # Is this symbol used in the out of the loop?
                intersect = outer_region.intersection(useblks)
                if intersect:
                    outer_uses.add(sym)
                intersect = inner_region.intersection(useblks)
                if intersect:
                    inner_uses.add(sym)

        return (outer_defs, outer_uses, inner_defs, inner_uses)

class LoopBlockDestructor:
    def __init__(self):
        pass

    def process(self, scope):
        for lb in scope.loop_nest_tree.traverse():
            if lb is scope.loop_nest_tree.root:
                break
            lb.preds
            # re-connect
            for p in lb.preds:
                p.replace_succ(lb, lb.head)
            for s in lb.succs:
                for body in [lb.head]+lb.bodies:
                    if s in body.succs:
                        s.replace_pred(lb, body)
                        break
        scope.loop_nest_tree = None
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(scope.entry_block, 0)


class SimpleLoopUnroll:
    ''' simplyfied loop unrolling for testbench'''
    def __init__(self):
        pass

    def process(self, scope):
        self.scope = scope

        entry = scope.entry_block
        # reset ssa form
        for var in scope.usedef.get_all_vars():
            if var.symbol().ancestor:
                var.set_symbol(var.symbol().ancestor)
        udd = UseDefDetector()
        udd.process(scope)

        for c in self.scope.loop_nest_tree.get_children_of(entry):
            self._process(c)
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(entry, 0)

    def _process(self, blk):
        assert isinstance(blk, CompositBlock)
        blocks = blk.collect_basic_head_bodies()

        inductions, (loop_init, loop_limit, loop_step) = self._find_induction_and_loop_range(blocks)
        logger.debug(str(loop_init))
        logger.debug(str(loop_limit))
        logger.debug(str(loop_step))
        assert loop_init.is_a(CONST)
        assert loop_limit.is_a(CONST)
        assert loop_step.is_a(CONST)
        # should success unrolling if loop is exsisting in a testbench
        if not inductions:
            return False

        unroll_blocks = blocks[1:-1]
        if len(unroll_blocks) > 1:
            return False
        unroll_block = unroll_blocks[0]
        self._unroll(inductions, loop_init.value, loop_limit.value, loop_step.value, unroll_block)

        cjump = blk.head.stms[-1]
        assert cjump.is_a(CJUMP)
        # head jumps to true block always
        next_block = cjump.true
        jump = JUMP(next_block)
        jump.block = blk.head
        jump.lineno = cjump.lineno
        blk.head.stms[-1] = jump
        blk.head.succs = [next_block]
        if blk.head in cjump.false.preds:
            cjump.false.preds.remove(blk.head)

        loop_tails = [p for p in blk.head.preds if p in blk.bodies]
        for tail in loop_tails:
            blk.head.preds.remove(tail)
            cjump.false.preds = [tail]
            tail.succs = [cjump.false]
            tail.succs_loop = []
            jump = JUMP(cjump.false)
            jump.block = tail
            jump.lineno = cjump.lineno
            tail.stms = [jump]

        #re-order blocks
        return True

    def _find_induction_and_loop_range(self, blocks):
        usedef = self.scope.usedef
        # loop head should contain CJUMP which having the loop-continue test
        induction = None
        loop_init = None
        loop_limit = None
        loop_step = None
        head = blocks[0]
        tails = [p for p in head.preds if p in blocks]
        # find induction & limit
        for stm in head.stms:
            if stm.is_a(CJUMP):
                assert stm.exp.is_a(TEMP) and stm.exp.sym.is_condition()
                defstms = usedef.get_def_stms_by_sym(stm.exp.sym)
                assert len(defstms) == 1
                mv = defstms.pop()
                assert mv.is_a(MOVE)
                rel = mv.src
                assert rel.is_a(RELOP) and rel.op == 'Lt'
                induction = rel.left
                loop_limit = rel.right
                break
        # find init value
        if induction:
            defstms = usedef.get_def_stms_by_sym(induction.sym)
            for stm in defstms:
                if stm.block in head.preds and stm.block not in head.preds_loop:
                    assert stm.is_a(MOVE)
                    loop_init = stm.src
                    break
        # find step value
        for tail in tails:
            defstms = usedef.get_def_stms_by_sym(induction.sym)
            for stm in defstms:
                if stm.block is tail and stm.is_a(MOVE) and stm.src.is_a(BINOP):
                    binop = stm.src
                    assert binop.op == 'Add'
                    assert binop.left.sym is induction.sym
                    loop_step = binop.right
                    break
            else:
                continue
            break
        return [induction], (loop_init, loop_limit, loop_step)

    def _get_single_assignment_vars(self, block):
        usedef = self.scope.usedef
        usevars = usedef.get_use_vars_by_blk(block)
        use_result = []
        for var in usevars:
            if var.symbol().is_temp() or var.symbol().is_condition():
                use_result.append(var)
        return use_result

    def _unroll(self, inductions, start, count, step, block):
        use_temps = self._get_single_assignment_vars(block)
        new_stms = []
        for i in range(start, count, step):
            for stm in block.stms:
                if stm.is_a(JUMP):
                    continue
                copystm = stm.clone()
                # make ssa form by hand for @t and @cond
                for var in use_temps:
                    new_name = var.sym.name + '#' + str(i)
                    new_sym = self.scope.inherit_sym(var.sym, new_name)
                    replacer = VarReplacer(var, TEMP(new_sym, var.ctx), self.scope.usedef)
                    replacer.current_stm = copystm
                    replacer.visit(copystm)
                if copystm.is_a(MOVE):
                    if copystm.dst.sym.is_temp() or copystm.dst.sym.is_condition():
                        new_name = copystm.dst.sym.name + '#' + str(i)
                        new_sym = self.scope.inherit_sym(copystm.dst.sym, new_name)
                        copystm.dst.sym = new_sym
                # replace induction variables
                for induction in inductions:
                    c = CONST(i)
                    replacer = VarReplacer(induction, c, self.scope.usedef)
                    replacer.current_stm = copystm
                    replacer.visit(copystm)
                new_stms.append(copystm)
                copystm.block = block
        block.stms = new_stms
        jump = JUMP(block.succs[0])
        jump.lineno = 1
        block.append_stm(jump)

