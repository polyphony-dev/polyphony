from collections import deque
from .block import Block
from .dominator import DominatorTreeBuilder
from .ir import *
from .usedef import UseDefDetector
from .utils import remove_except_one
from logging import getLogger
logger = getLogger(__name__)


def can_merge_synth_params(params1, params2):
    # TODO
    return params1 == params2


class BlockReducer(object):
    def process(self, scope):
        self.scope = scope
        if scope.is_class():
            return
        self.removed_blks = []
        while True:
            self._merge_unidirectional_block(scope)
            self._remove_empty_blocks(scope)
            if not self.removed_blks:
                break
            else:
                self._merge_duplicate_paths(scope)
                self.removed_blks = []
        self._order_blocks(scope)
        self._reconstruct_phi(scope)


    def _order_blocks(self, scope):
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(scope.entry_block, 0)

    def _merge_duplicate_paths(self, scope):
        for block in scope.traverse_blocks():
            if not block.stms:
                continue
            stm = block.stms[-1]
            if stm.is_a(CJUMP) and stm.true is stm.false:
                block.stms.pop()
                block.append_stm(JUMP(stm.true))
                block.succs = [stm.true]
                # leave only first mathced item
                stm.true.preds = remove_except_one(stm.true.preds, block)
                assert 1 == stm.true.preds.count(block)
            elif stm.is_a(MCJUMP) and len(set(stm.targets)) == 1:
                block.stms.pop()
                block.append_stm(JUMP(stm.targets[0]))
                block.succs = [stm.targets[0]]
                stm.targets[0].preds = remove_except_one(stm.targets[0].preds, block)
                assert 1 == stm.targets[0].preds.count(block)

    def _merge_unidirectional_block(self, scope):
        for block in scope.traverse_blocks():
            #check unidirectional
            # TODO: any jump.typ
            if (len(block.preds) == 1 and
                    len(block.preds[0].succs) == 1 and
                    not block.preds[0].stms[-1].typ == 'C' and
                    can_merge_synth_params(block.synth_params, block.preds[0].synth_params)):
                pred = block.preds[0]
                assert pred.stms[-1].is_a(JUMP)
                assert pred.succs[0] is block
                assert not pred.succs_loop

                pred.stms.pop()  # remove useless jump
                # merge stms
                for stm in block.stms:
                    pred.append_stm(stm)

                #deal with block links
                for succ in block.succs:
                    succ.replace_pred(block, pred)
                    succ.replace_pred_loop(block, pred)
                pred.succs = block.succs
                pred.succs_loop = block.succs_loop
                if block is scope.exit_block:
                    scope.exit_block = pred

                self.removed_blks.append(block)
                if not pred.is_hyperblock:
                    pred.is_hyperblock = block.is_hyperblock

    def remove_empty_block(self, block):
        if len(block.stms) > 1:
            return False
        if block is block.scope.entry_block:
            return False
        if block.stms and block.stms[0].is_a(JUMP):
            assert len(block.succs) == 1
            succ = block.succs[0]
            if succ in block.succs_loop:
                return False
            phis = block.collect_stms(PHIBase)
            if phis:
                return False
            idx = succ.preds.index(block)
            succ.remove_pred(block)
            for pred in block.preds:
                succ.preds.insert(idx, pred)
                idx += 1
                if pred in block.preds_loop:
                    succ.preds_loop.append(pred)
                pred.replace_succ(block, succ)
                pred.replace_succ_loop(block, succ)

            logger.debug('remove empty block ' + block.name)
            return True
        return False

    def _remove_empty_blocks(self, scope):
        for block in scope.traverse_blocks():
            if self.remove_empty_block(block):
                self.removed_blks.append(block)

    def _reconstruct_phi(self, scope):
        phis = []
        for block in scope.traverse_blocks():
            if block.is_hyperblock:
                continue
            phis.extend(block.collect_stms([PHI, LPHI]))
        if not phis:
            return
        udd = UseDefDetector()
        udd.process(scope)
        usedef = scope.usedef
        tree = DominatorTreeBuilder(scope).process()

        for phi in phis:
            block = phi.block
            preds = block.preds[:]
            # search again for the arg reaching definition block
            for idx, arg in enumerate(phi.args):
                if not arg or arg.is_a(CONST):
                    continue
                phi.defblks[idx] = None
                defstms = usedef.get_stms_defining(arg.symbol())
                assert len(defstms) == 1
                defstm = list(defstms)[0]
                # phi.arg and arg definition are in the same block
                if block is defstm.block:
                    phi.defblks[idx] = defstm.block
                    continue
                else:
                    for pred in preds[:]:
                        if tree.is_dominator(defstm.block, pred):
                            phi.defblks[idx] = pred
                            preds.remove(pred)
                            break
                assert phi.defblks[idx]

            if len(phi.defblks) != len(block.preds):
                for defblk in phi.defblks[:]:
                    if defblk in block.preds:
                        continue
                    else:
                        idx = phi.defblks.index(defblk)
                        phi.defblks.pop(idx)
                        phi.ps.pop(idx)
                        phi.args.pop(idx)
            if len(phi.args) == 1:
                mv = MOVE(phi.var, phi.args[0])
                mv.lineno = phi.args[0].lineno
                phi.defblks[0].insert_stm(-1, mv)
                block.stms.remove(phi)
            else:
                indices = []
                for pred in block.preds:
                    if pred in phi.defblks:
                        indices.append(phi.defblks.index(pred))
                phi.reorder_args(indices)


class PathExpTracer(object):
    def process(self, scope):
        self.scope = scope
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(scope.entry_block, 0)
        tree = DominatorTreeBuilder(scope).process()
        tree.dump()
        self.tree = tree
        self.worklist = deque()
        self.worklist.append(scope.entry_block)
        while self.worklist:
            blk = self.worklist.popleft()
            self.traverse_dtree(blk)

    def make_path_exp(self, blk, parent):
        blk.path_exp = parent.path_exp
        if len(parent.succs) > 1 and len(blk.preds) == 1:
            blk.path_exp = merge_path_exp(parent, blk)

    def traverse_dtree(self, blk):
        if not blk.stms:
            return
        parent = self.tree.get_parent_of(blk)
        if parent:
            self.make_path_exp(blk, parent)
        children = self.tree.get_children_of(blk)
        for child in children:
            self.traverse_dtree(child)


def merge_path_exp(prev, blk):
    jump = prev.stms[-1]
    exp = None
    if jump.is_a(CJUMP):
        if blk is jump.true:
            exp = rel_and_exp(blk.path_exp, jump.exp)
        elif blk is jump.false:
            exp = rel_and_exp(blk.path_exp, UNOP('Not', jump.exp))
    elif jump.is_a(MCJUMP):
        if blk in jump.targets:
            assert 1 == jump.targets.count(blk)
            idx = jump.targets.index(blk)
            exp = rel_and_exp(blk.path_exp, jump.conds[idx])
    return exp


def rel_and_exp(exp1, exp2):
    exp = reduce_And_exp(exp1, exp2)
    if not exp:
        exp = RELOP('And', exp1, exp2)
    return exp


def reduce_And_exp(exp1, exp2):
    if exp1 is None:
        return exp2
    elif exp2 is None:
        return exp1
    if exp1.is_a(CONST):
        if exp1.value != 0 or exp1.value is True:
            return exp2
        else:
            return exp1
    elif exp2.is_a(CONST):
        if exp2.value != 0 or exp2.value is True:
            return exp1
        else:
            return exp2
    if exp1.is_a(TEMP) and exp2.is_a(UNOP) and exp1.sym is exp2.exp.sym:
        return CONST(0)
    elif exp2.is_a(TEMP) and exp1.is_a(UNOP) and exp1.exp.sym is exp2.sym:
        return CONST(0)
    return None


class HyperBlockBuilder(object):
    def process(self, scope):
        self.scope = scope
        self.diamond_nodes = deque()
        self._visited_heads = set()
        diamond_nodes = self._find_diamond_nodes()
        self._convert(diamond_nodes)

    def _update_domtree(self):
        self.tree = DominatorTreeBuilder(self.scope).process()

    def _walk_to_convergence(self, blk, path):
        b = blk
        while b:
            path.append(b)
            if len(b.preds) > 1:
                return True
            if not b.succs:
                return False
            if len(b.succs) > 1:
                return False
            if b.succs[0] in b.succs_loop:
                return False
            b = b.succs[0]

    def _find_diamond_nodes(self):
        self._update_domtree()
        for blk in self.scope.traverse_blocks():
            if len(blk.succs) <= 1:
                continue
            if blk in self._visited_heads:
                continue
            tails = []
            branches = []
            for succ in blk.succs:
                path = []
                if not self._walk_to_convergence(succ, path):
                    continue
                tails.append(path[-1])
                branches.append(path)
            if len(blk.succs) == len(tails) and all([tails[0] is b for b in tails[1:]]):
                return (blk, tails[0], branches)
        return None

    def _convert(self, diamond_nodes):
        reducer = BlockReducer()
        while diamond_nodes:
            head, tail, branches = diamond_nodes
            if self.tree.get_parent_of(tail) is head:
                # pure diamond nodes
                self._merge_diamond_blocks(head, tail, branches)
                for path in branches:
                    for blk in path[:-1]:
                        reducer.remove_empty_block(blk)
                reducer.remove_empty_block(tail)
            else:
                # TODO: phi-reduction
                # with side edges on the tail

                pass
            self._visited_heads.add(head)

            diamond_nodes = self._find_diamond_nodes()

    def _emigrate_to_diamond_head(self, head, blk):
        unmoves = []
        for stm in blk.stms[:-1]:
            if stm.is_a(MOVE):
                if stm.src.is_a(CALL):
                    unmoves.append(stm)
                else:
                    head.insert_stm(-1, stm)
            elif stm.is_a(EXPR):
                if stm.exp.is_a(CALL):
                    unmoves.append(stm)
                else:
                    cstm = CSTM(blk.path_exp, stm)
                    cstm.lineno = stm.lineno
                    head.insert_stm(-1, cstm)
            else:
                head.insert_stm(-1, stm)
        return unmoves

    def _merge_diamond_blocks(self, head, tail, branches):
        visited_path = set()
        for path in branches:
            if path[0] in visited_path:
                continue
            else:
                visited_path.add(path[0])
            assert tail is path[-1]
            for blk in path[:-1]:
                assert len(blk.succs) == 1
                unmoves = self._emigrate_to_diamond_head(head, blk)

                for stm in blk.stms[:-1]:
                    if stm not in unmoves:
                        blk.stms.remove(stm)
        head.is_hyperblock = True
