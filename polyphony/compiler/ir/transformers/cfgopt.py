"""CFG optimizations using new IR (ir.py)."""
from collections import deque
from ..block import Block
from ..ir import Loc
from ..ir import (
    Const, Temp, Attr, Move, Expr, CExpr, CMove, Jump, CJump, MCJump,
    Phi, UPhi, LPhi, RelOp, UnOp, Ctx, SysCall, MRef, MStore,
)
from ..irhelper import reduce_relexp, irexp_type
from ..analysis.dominator import DominatorTreeBuilder
from ..analysis.usedef import UseDefDetector
from ..types.type import Type
from ...common.utils import remove_except_one, unique
from logging import getLogger
logger = getLogger(__name__)


def can_merge_synth_params(params1, params2):
    return params1['scheduling'] == params2['scheduling']


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

    def _order_blocks(self, scope):
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(scope.entry_block, 0)

    def _merge_duplicate_paths(self, scope):
        for block in scope.traverse_blocks():
            if not block.stms:
                continue
            stm = block.stms[-1]
            if isinstance(stm, CJump) and stm.true == stm.false:
                block.stms.pop()
                jmp = Jump(target=stm.true, block=block.bid)
                block.stms.append(jmp)
                true_blk = self.scope.find_block(stm.true)
                block.succs = [true_blk]
                true_blk.preds = remove_except_one(true_blk.preds, block)
                assert 1 == true_blk.preds.count(block)
            elif isinstance(stm, MCJump) and len(set(stm.targets)) == 1:
                block.stms.pop()
                jmp = Jump(target=stm.targets[0], block=block.bid)
                block.stms.append(jmp)
                tgt_blk = self.scope.find_block(stm.targets[0])
                block.succs = [tgt_blk]
                tgt_blk.preds = remove_except_one(tgt_blk.preds, block)
                assert 1 == tgt_blk.preds.count(block)

    def _merge_unidirectional_block(self, scope):
        for block in scope.traverse_blocks():
            if (len(block.preds) == 1 and
                    len(block.preds[0].succs) == 1 and
                    can_merge_synth_params(block.synth_params, block.preds[0].synth_params)):
                if self._merge_unidir_block(block):
                    logger.debug('remove unidirectional block ' + str(block.name))
                    self._remove_block(block)

    def _merge_unidir_block(self, block):
        pred = block.preds[0]
        assert isinstance(pred.stms[-1], Jump)
        assert pred.succs[0] is block
        assert not pred.succs_loop

        pred.stms.pop()  # remove useless jump
        for stm in block.stms:
            object.__setattr__(stm, 'block', pred.bid)
            pred.stms.append(stm)
        for succ in block.succs:
            succ.replace_pred(block, pred)
            succ.replace_pred_loop(block, pred)
        pred.succs = block.succs
        pred.succs_loop = block.succs_loop
        if block is block.scope.exit_block:
            block.scope.exit_block = pred
        if not pred.is_hyperblock:
            pred.is_hyperblock = block.is_hyperblock
        return True

    def _remove_empty_block(self, block):
        if len(block.stms) > 1:
            return False
        if block is block.scope.entry_block:
            return False
        if block.preds_loop or block.succs_loop:
            return False
        if (block.synth_params['scheduling'] == 'timed' and
                len(block.succs) and
                block.succs[0].nametag == 'fortest'):
            return False
        if block.stms and isinstance(block.stms[0], Jump):
            assert len(block.succs) == 1
            succ = block.succs[0]
            idx = succ.preds.index(block)
            succ.remove_pred(block)
            for pred in block.preds:
                succ.preds.insert(idx, pred)
                idx += 1
                pred.replace_succ(block, succ)
            logger.debug('remove empty block ' + block.name)
            return True
        return False

    def _remove_empty_blocks(self, scope):
        for block in scope.traverse_blocks():
            if self._remove_empty_block(block):
                self._remove_block(block)

    def _remove_block(self, blk):
        self.removed_blks.append(blk)
        func = self.scope.as_function()
        if func:
            func.remove_block_from_region(blk)


class PathExpTracer(object):
    def process(self, scope):
        self.scope = scope
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(scope.entry_block, 0)
        self.tree_builder = DominatorTreeBuilder(scope)
        self.tree = self.tree_builder.process()
        self.tree.dump()
        self.worklist = deque()
        self.worklist.extend(sorted([blk for blk in self.scope.traverse_blocks()]))
        while self.worklist:
            blk = self.worklist.popleft()
            if not blk.stms:
                continue
            if not blk.preds or not blk.succs:
                blk.path_exp = Const(value=1)
                continue
            parent = self.tree.get_parent_of(blk)
            self._make_path_exp(blk, parent)

    def _make_path_exp(self, blk, parent):
        parent_path = parent.path_exp
        blk.path_exp = parent_path
        if len(parent.succs) > 1 and len(blk.preds) == 1:
            r = self.scope.find_region(parent)
            if r.head is parent and r is not self.scope.top_region() and blk not in r.bodies:
                if parent_path:
                    blk.path_exp = parent_path.model_copy(deep=True)
            else:
                assert parent is blk.preds[0]
                exp = _merge_path_exp_new(parent, blk)
                blk.path_exp = self._insert_named_exp(exp, blk, 0)
        else:
            r = self.scope.find_region(blk)
            if r is not self.scope.top_region():
                assert len(r.head.preds_loop) == 1
                exit_block = r.head.preds_loop[0]
            else:
                exit_block = self.scope.exit_block
            if blk in self.tree_builder.dominators[exit_block]:
                pass
            elif len(blk.preds) > 1:
                exps = []
                for pred in unique(blk.preds):
                    e = _merge_path_exp_new(pred, blk)
                    if not e:
                        self.worklist.append(blk)
                        return
                    else:
                        exps.append(e)
                exp = self._insert_named_exp(exps[0], blk, 0)
                i = 1
                for e in exps[1:]:
                    named = self._insert_named_exp(e, blk, i)
                    if named is not e:
                        i += 1
                    exp = RelOp(op='Or', left=exp, right=named)
                blk.path_exp = exp

    def _insert_named_exp(self, exp, blk, insert_pos):
        if isinstance(exp, Temp):
            return exp
        csym = self.scope.add_condition_sym()
        mv = Move(dst=Temp(name=csym.name, ctx=Ctx.STORE), src=exp,
                 loc=Loc('', 0), block=blk.bid)
        blk.stms.insert(insert_pos, mv)
        return Temp(name=csym.name)


def _merge_path_exp_new(pred, blk, idx_hint=-1):
    """Merge path expression using stms for jump analysis."""
    if not pred.stms:
        return pred.path_exp
    jump = pred.stms[-1]
    pred_path = pred.path_exp
    exp = pred_path
    if isinstance(jump, CJump):
        if blk.bid == jump.true:
            exp = _rel_and_exp_new(pred_path, jump.exp)
        elif blk.bid == jump.false:
            exp = _rel_and_exp_new(pred_path, UnOp(op='Not', exp=jump.exp))
    elif isinstance(jump, MCJump):
        if blk.bid in jump.targets:
            if 1 == jump.targets.count(blk.bid):
                idx = jump.targets.index(blk.bid)
                exp = _rel_and_exp_new(pred_path, jump.conds[idx])
            elif idx_hint >= 0:
                exp = _rel_and_exp_new(pred_path, jump.conds[idx_hint])
            else:
                indices = [i for i, t in enumerate(jump.targets) if t == blk.bid]
                exp = _rel_and_exp_new(pred_path, jump.conds[indices[0]])
                for idx in indices[1:]:
                    rexp = _rel_and_exp_new(pred_path, jump.conds[idx])
                    exp = RelOp(op='Or', left=exp, right=rexp)
    return exp


def _rel_and_exp_new(exp1, exp2):
    if exp1 is None:
        return exp2
    elif exp2 is None:
        return exp1
    exp1 = reduce_relexp(exp1)
    exp2 = reduce_relexp(exp2)
    if isinstance(exp1, Const) and exp1.value:
        exp = exp2
    elif isinstance(exp2, Const) and exp2.value:
        exp = exp1
    else:
        exp = RelOp(op='And', left=exp1, right=exp2)
    return exp


class HyperBlockBuilder(object):
    DEBUG = False

    def process(self, scope):
        self.scope = scope
        self.uddetector = UseDefDetector()
        self.uddetector.scope = scope
        self.usedef = UseDefDetector().process(scope)
        self.uddetector.table = self.usedef
        self.reducer = BlockReducer()
        self.reducer.scope = self.scope
        self.diamond_nodes = deque()
        self._visited_heads = set()
        if HyperBlockBuilder.DEBUG:
            self.count = 0
            from .scope import write_dot  # type: ignore[import]
            write_dot(self.scope, f'{self.count}')
            self.count += 1
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

    def _find_branch_paths(self, blk):
        tails = []
        branches = []
        for succ in blk.succs:
            path = []
            to_convergence = self._walk_to_convergence(succ, path)
            if not to_convergence:
                return None, None
            tails.append(path[-1])
            branches.append(path)
        return branches, tails

    def _find_diamond_nodes(self):
        self._update_domtree()
        for blk in self.scope.traverse_blocks():
            if len(blk.succs) <= 1:
                continue
            if blk in self._visited_heads:
                continue
            branches, tails = self._find_branch_paths(blk)
            if branches is None or tails is None or not branches:
                continue
            if all([tails[0] is b for b in tails[1:]]):
                if len(blk.succs) == len(tails):
                    return (blk, tails[0], branches)
            else:
                for tail in tails:
                    if tails.count(tail) > 1:
                        indices = [idx for idx, path in enumerate(branches) if path[-1] is tail]
                        if all([(indices[i + 1] - indices[i]) == 1 for i in range(len(indices) - 1)]):
                            return self._duplicate_head(blk, branches, indices)
        return None

    def _duplicate_head(self, head, branches, indices):
        new_head = Block(self.scope)
        old_mj = head.stms[-1]
        conds = []
        targets = []
        for idx in indices:
            path = branches[idx]
            br = path[0]
            assert br in head.succs
            assert old_mj.targets[idx] == br.bid
            cond = old_mj.conds[idx]
            conds.append(cond)
            targets.append(br)
        mj = MCJump(conds=conds, targets=[t.bid for t in targets], loc=old_mj.loc, block=new_head.bid)
        if all([mj.targets[0] == t for t in mj.targets[1:]]):
            return
        for idx in indices:
            path = branches[idx]
            br = path[0]
            br.replace_pred(head, new_head)
            new_head.succs.append(br)
        new_cond = old_mj.conds[indices[0]]
        for idx in indices[1:]:
            new_cond = RelOp(op='Or', left=new_cond, right=old_mj.conds[idx])
        new_conds = list(old_mj.conds)
        new_targets = list(old_mj.targets)
        new_conds[indices[0]] = new_cond
        new_targets[indices[0]] = new_head.bid
        head.succs[indices[0]] = new_head
        for idx in reversed(indices[1:]):
            del new_conds[idx]
            del new_targets[idx]
            head.succs.pop(idx)
        old_mj = old_mj.model_copy(update={'conds': tuple(new_conds), 'targets': tuple(new_targets)})
        head.replace_stm(head.stms[-1], old_mj)
        if len(old_mj.targets) == 2:
            cj = CJump(exp=old_mj.conds[0], true=old_mj.targets[0], false=old_mj.targets[1], loc=old_mj.loc, block=head.bid)
            if not isinstance(cj.exp, Temp):
                new_sym = self.scope.add_condition_sym()
                new_sym.typ = Type.bool()
                mv = Move(dst=Temp(name=new_sym.name, ctx=Ctx.STORE), src=cj.exp, loc=old_mj.loc, block=head.bid)
                head.stms.insert(-1, mv)
                object.__setattr__(cj, 'exp', Temp(name=new_sym.name))
            head.replace_stm(head.stms[-1], cj)
        if len(mj.targets) == 2:
            cj = CJump(exp=mj.conds[0], true=mj.targets[0], false=mj.targets[1], loc=mj.loc, block=new_head.bid)
            new_head.stms.append(cj)
        else:
            new_head.stms.append(mj)
        new_head.preds = [head]
        new_head.path_exp = _merge_path_exp_new(head, new_head)
        Block.set_order(new_head, head.order + 1)
        self._update_domtree()
        sub_branches = [branches[idx] for idx in indices]
        tail = sub_branches[0][-1]
        return (new_head, tail, sub_branches)

    def _convert(self, diamond_nodes):
        while diamond_nodes:
            head, tail, branches = diamond_nodes
            if self.tree.get_parent_of(tail) is head:
                self._merge_diamond_blocks(head, tail, branches)
                for path in branches:
                    for blk in path[:-1]:
                        self.reducer._remove_empty_block(blk)
                self.reducer._remove_empty_block(tail)
                self._visited_heads.add(head)
            else:
                self._do_phi_reduction(head, tail, branches)
            diamond_nodes = self._find_diamond_nodes()
            if HyperBlockBuilder.DEBUG:
                from .scope import write_dot  # type: ignore[import]
                write_dot(self.scope, f'{self.count}')
                self.count += 1

    def _do_phi_reduction(self, head, tail, branches):
        new_tail = Block(self.scope)
        head_path = head.path_exp
        if head_path:
            new_tail.path_exp = head_path
        else:
            new_tail.path_exp = Const(value=1)
        removes = []
        indices = []
        for path in branches:
            if len(path) > 1:
                br = path[-2]
            else:
                br = head
            removes.append(br)
        br = removes[0]
        first_idx = tail.preds.index(br)
        indices = list(range(first_idx, first_idx + len(removes)))
        for idx, br in zip(indices, removes):
            assert tail.preds[idx] is br
        for stm in tail.stms:
            if isinstance(stm, (Phi, UPhi, LPhi)) and len(stm.args) == len(tail.preds):
                new_args = []
                new_ps = []
                old_args = []
                old_ps = []
                for idx in range(len(stm.args)):
                    if idx in indices:
                        new_args.append(stm.args[idx])
                        new_ps.append(stm.ps[idx])
                    else:
                        old_args.append(stm.args[idx])
                        old_ps.append(stm.ps[idx])
                if all([new_args[0].name == arg.name for arg in new_args[1:]]):
                    newsym = self.scope.add_temp()
                    newsym.typ = irexp_type(stm.var, self.scope)
                    mv = Move(dst=Temp(name=newsym.name, ctx=Ctx.STORE), src=new_args[0], loc=Loc('', 0), block=new_tail)
                    new_tail.stms.append(mv)
                    self.uddetector.visit(mv)
                else:
                    new_phi = stm.model_copy(deep=True)
                    object.__setattr__(new_phi, 'args', tuple(new_args))
                    object.__setattr__(new_phi, 'ps', tuple(new_ps))
                    newsym = self.scope.add_temp()
                    newsym.typ = irexp_type(stm.var, self.scope)
                    object.__setattr__(new_phi, 'var', Temp(name=newsym.name, ctx=Ctx.STORE))
                    object.__setattr__(new_phi, 'block', new_tail.bid)
                    new_tail.stms.append(new_phi)
                    self.uddetector.visit(new_phi)
                arg = Temp(name=newsym.name)
                old_args.insert(first_idx, arg)
                old_ps.insert(first_idx, new_tail.path_exp)
                object.__setattr__(stm, 'args', tuple(old_args))
                object.__setattr__(stm, 'ps', tuple(old_ps))
                self.uddetector.visit(stm)
        for br in removes:
            old_jmp = br.stms[-1]
            if isinstance(old_jmp, Jump):
                object.__setattr__(old_jmp, 'target', new_tail.bid)
            elif isinstance(old_jmp, CJump):
                if old_jmp.true == tail.bid:
                    object.__setattr__(old_jmp, 'true', new_tail.bid)
                if old_jmp.false == tail.bid:
                    object.__setattr__(old_jmp, 'false', new_tail.bid)
            elif isinstance(old_jmp, MCJump):
                new_targets = tuple(new_tail.bid if t == tail.bid else t for t in old_jmp.targets)
                new_jmp = old_jmp.model_copy(update={'targets': new_targets})
                br.replace_stm(old_jmp, new_jmp)
            assert br in tail.preds
            tail.preds.remove(br)
            new_tail.preds.append(br)
            br.replace_succ(tail, new_tail)
        jmp = Jump(target=tail.bid, block=new_tail.bid)
        new_tail.stms.append(jmp)
        new_tail.succs = [tail]
        tail.preds.insert(first_idx, new_tail)
        Block.set_order(new_tail, tail.order)

    def _has_timing_function(self, stm):
        if isinstance(stm, Move):
            call = stm.src
        elif isinstance(stm, Expr):
            call = stm.exp
        else:
            return False
        if isinstance(call, SysCall):
            wait_funcs = [
                'polyphony.timing.clksleep',
                'polyphony.timing.wait_rising',
                'polyphony.timing.wait_falling',
                'polyphony.timing.wait_value',
                'polyphony.timing.wait_edge',
                'polyphony.timing.wait_until'
            ]
            return call.name in wait_funcs
        return False

    def _has_mem_access(self, stm):
        if isinstance(stm, Move) and isinstance(stm.src, MRef):
            return True
        if isinstance(stm, Expr) and isinstance(stm.exp, MStore):
            return True
        return False

    def _has_instance_var_modification(self, stm):
        if isinstance(stm, Move) and isinstance(stm.dst, Attr):
            return True
        return False

    def _select_stms_for_speculation(self, head, blk):
        moves = []
        remains = []
        for idx, stm in enumerate(blk.stms[:-1]):
            if (isinstance(stm, Expr) or isinstance(stm, CExpr) or isinstance(stm, CMove) or self._has_timing_function(stm) or self._has_mem_access(stm) or self._has_instance_var_modification(stm)):
                remains.append((idx, stm))
                continue
            else:
                skip = False
                usesyms = self.usedef.get_syms_used_at(stm)
                for sym in usesyms:
                    defstms = self.usedef.get_stms_defining(sym)
                    remains_ = [s for _, s in remains]
                    intersection = defstms & set(remains_)
                    if intersection:
                        remains.append((idx, stm))
                        skip = True
                        break
                if skip:
                    continue
            moves.append((idx, stm))
        return moves, remains

    def _transform_special_stms_for_speculation(self, head, path_exp, path_remain_stms):
        all_cstms = []
        path_cstms = []
        cstms = []
        for idx, stm in path_remain_stms:
            match stm:
                case CMove() | CExpr():
                    cstm = stm
                case Move():
                    cstm = CMove(cond=path_exp.model_copy(deep=True), dst=stm.dst.model_copy(deep=True), src=stm.src.model_copy(deep=True), loc=stm.loc, block=stm.block)
                case Expr():
                    cstm = CExpr(cond=path_exp.model_copy(deep=True), exp=stm.exp.model_copy(deep=True), loc=stm.loc, block=stm.block)
                case Phi() | UPhi() | LPhi():
                    cstm = stm
                case _:
                    assert False
            if stm.block:
                stm_blk = self.scope.find_block(stm.block)
                if stm in stm_blk.stms:
                    stm_blk.stms.remove(stm)
            self.usedef.remove_stm(self.scope, stm)
            object.__setattr__(cstm, 'loc', stm.loc)
            cstms.append(cstm)
            all_cstms.append((idx, cstm))
            self.uddetector.visit(cstm)
        path_cstms.append(cstms)
        if len(path_cstms) > 1:
            for i, cstms in enumerate(path_cstms):
                nested_other_cstms = path_cstms[:i] + path_cstms[i + 1:]
                for cstm in cstms:
                    self.scope.add_branch_graph_edge(cstm, nested_other_cstms)
        return all_cstms

    def _merge_diamond_blocks(self, head, tail, branches):
        visited_path = set()
        for idx, path in enumerate(branches):
            assert tail is path[-1]
            if path[0] in visited_path:
                continue
            visited_path.add(path[0])
            if len(path) == 1:
                continue
            for blk in path[:-1]:
                if (len(blk.preds) == 1 and len(blk.preds[0].succs) == 1):
                    if self.reducer._merge_unidir_block(blk):
                        path.remove(blk)
            branch_blk = path[0]
            assert len(branch_blk.succs) == 1
            stms_, remains_ = self._select_stms_for_speculation(head, branch_blk)
            for _, stm in sorted(stms_, key=lambda _: _[0]):
                object.__setattr__(stm, 'block', head.bid)
                head.stms.insert(-1, stm)
            for _, stm in stms_:
                branch_blk.stms.remove(stm)
            if (remains_ and (head.synth_params['scheduling'] == 'pipeline' or head.synth_params['scheduling'] == 'timed' or self.scope.is_comb())):
                path_exp = branch_blk.path_exp
                cstms_ = self._transform_special_stms_for_speculation(head, path_exp, remains_)
                for _, stm in sorted(cstms_, key=lambda _: _[0]):
                    object.__setattr__(stm, 'block', head.bid)
                    head.stms.insert(-1, stm)
        head.is_hyperblock = True
