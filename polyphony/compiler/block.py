from .ir import *
from .dominator import DominatorTreeBuilder
from .utils import replace_item
from logging import getLogger
logger = getLogger(__name__)

class Block:
    @classmethod
    def set_order(cls, block, order):
        order += 1
        if order > block.order:
            logger.debug(block.name + ' order ' + str(order))
            block.order = order

            succs = [succ for succ in block.succs if succ not in block.succs_loop]
            for succ in succs:
                cls.set_order(succ, order)

    def __init__(self, scope, nametag = 'b'):
        self.nametag = nametag
        self.stms = []
        self.succs = []
        self.preds = []
        self.succs_loop = []
        self.preds_loop = []
        self.order = -1
        self.scope = scope
        scope.block_count += 1
        self.num = scope.block_count
        self.name = '{}_{}{}'.format(scope.name, self.nametag, self.num)
        self.path_exp = None

    def _str_connection(self):
        s = ''
        bs = []
        s += ' # preds: {'
        for blk in self.preds:
            if blk in self.preds_loop:
                bs.append(blk.name+'$LOOP')
            else:
                bs.append(blk.name)
        s += ', '.join([b for b in bs])
        s += '}\n'

        bs = []
        s += ' # succs: {'
        for blk in self.succs:
            if blk in self.succs_loop:
                bs.append(blk.name+'$LOOP')
            else:
                bs.append(blk.name)
        s += ', '.join([b for b in bs])
        s += '}\n'
        return s

    def __str__(self):
        s = 'Block: (' + str(self.order) + ') ' + str(self.name) + '\n'
        s += self._str_connection()
        if self.path_exp:
            s += ' # path exp: '
            s += str(self.path_exp) + '\n'
        s += ' # code\n'
        s += '\n'.join(['  '+str(stm) for stm in self.stms])
        s += '\n\n'
        return s

    def __repr__(self):
        return self.name

    def __lt__(self, other):
        return int(self.order) < int(other.order)

    def connect(self, next_block):
        self.succs.append(next_block)
        next_block.preds.append(self)

    def connect_loop(self, next_block):
        self.succs.append(next_block)
        next_block.preds.append(self)

        self.succs_loop.append(next_block)
        next_block.preds_loop.append(self)

    def append_stm(self, stm):
        stm.block = self
        self.stms.append(stm)

    def insert_stm(self, idx, stm):
        stm.block = self
        self.stms.insert(idx, stm)

    def replace_stm(self, old_stm, new_stm):
        replace_item(self.stms, old_stm, new_stm)
        new_stm.block = self

    def stm(self, idx):
        if len(self.stms):
            return self.stms[idx]
        else:
            return None

    def replace_succ(self, old, new):
        replace_item(self.succs, old, new)
        if isinstance(new, CompositBlock):
            return
        if self.stms:
            jmp = self.stms[-1]
            if jmp.is_a(JUMP):
                jmp.target = new
            elif jmp.is_a(CJUMP):
                if jmp.true is old:
                    jmp.true = new
                else:
                    jmp.false = new
            elif jmp.is_a(MCJUMP):
                for i, t in enumerate(jmp.targets):
                    if t is old:
                       jmp.targets[i] = new
 
    def replace_succ_loop(self, old, new):
        replace_item(self.succs_loop, old, new)

    def replace_pred(self, old, new):
        replace_item(self.preds, old, new)

    def replace_pred_loop(self, old, new):
        replace_item(self.preds_loop, old, new)

    def collect_basic_blocks(self, blocks):
        if self in blocks:
            return
        blocks.add(self)
        for succ in [succ for succ in self.succs]:
            succ.collect_basic_blocks(blocks)

    def traverse(self, visited, full=False, longitude=False):
        if self in visited:
            return
        if self not in visited:
            visited.add(self)
            yield self
        for succ in [succ for succ in self.succs if succ not in self.succs_loop]:
            yield from succ.traverse(visited, full, longitude)

    def clone(self, scope, stm_map):
        b = Block(scope, self.nametag)
        for stm in self.stms:
            new_stm = stm.clone()
            new_stm.block = b
            b.stms.append(new_stm)
            stm_map[stm] = new_stm
        b.order = self.order
        b.succs      = list(self.succs)
        b.succs_loop = list(self.succs_loop)
        b.preds      = list(self.preds)
        b.preds_loop = list(self.preds_loop)
        return b

    def reconnect(self, blk_map):
        for i, succ in enumerate(self.succs):
            self.succs[i] = blk_map[succ]
        for i, succ in enumerate(self.succs_loop):
            self.succs_loop[i] = blk_map[succ]
        for i, pred in enumerate(self.preds):
            self.preds[i] = blk_map[pred]
        for i, pred in enumerate(self.preds_loop):
            self.preds_loop[i] = blk_map[pred]

    def collect_stms(self, typs):
         return [stm for stm in self.stms if stm.is_a(typs)]

class CompositBlock(Block):
    def __init__(self, scope, head, bodies, region):
        super().__init__(scope, 'composit')
        assert all([head.order < b.order for b in bodies])
        assert head.preds_loop
        self.head = head
        self.bodies = bodies
        self.region = region
        self.preds = [p for p in head.preds if p not in head.preds_loop]
        self.succs = self._find_succs([head] + bodies)
        self.order = head.order
        self.num = head.num
        self.name = '{}_{}{}'.format(scope.name, self.nametag, self.num)
        self.outer_defs = None
        self.outer_uses = None
        self.inner_defs = None
        self.inner_uses = None

    def __str__(self):
        s = 'CompositBlock: (' + str(self.order) + ') ' + str(self.name) + '\n'
        s += self._str_connection()

        s += ' # head: ' + self.head.name + '\n'
        s += ' # bodies: {'
        s += ', '.join([blk.name for blk in self.bodies])
        s += '}\n'
        if self.outer_defs:
            s += ' # outer_defs: {'
            s += ', '.join([str(d) for d in self.outer_defs])
            s += '}\n'
        if self.outer_uses:
            s += ' # outer_uses: {'
            s += ', '.join([str(u) for u in self.outer_uses])
            s += '}\n'
        if self.inner_defs:
            s += ' # inner_defs: {'
            s += ', '.join([str(d) for d in self.inner_defs])
            s += '}\n'
        if self.inner_uses:
            s += ' # inner_uses: {'
            s += ', '.join([str(u) for u in self.inner_uses])
            s += '}\n'
        bs = str(self.head)
        bs += ''.join([str(b) for b in self.bodies])
        bs = '    ' + bs.replace('\n', '\n    ')
        bs = bs[:-4] # remove last indent
        return s + bs

    def _find_succs(self, region):
        succs = []
        for b in region:
            for succ in b.succs:
                if succ not in region:
                    succs.append(succ)
        return succs

    def collect_basic_blocks(self, blocks):
        for blk in self.region:
            blocks.add(blk)
        for succ in self.succs:
            succ.collect_basic_blocks(blocks)

    def traverse(self, visited, full=False, longitude=False):
        if longitude:
            yield from super().traverse(visited, full, longitude)
        else:
            if full:
                if self not in visited:
                    visited.add(self)
                    yield self
            yield from self.head.traverse(visited, longitude)

    def collect_basic_head_bodies(self):
        blocks = [self.head]
        for b in self.bodies:
            if not isinstance(b, CompositBlock):
                blocks.append(b)
        return blocks

    def clone(self, scope, stm_map):
        b = CompositBlock(scope, self.nametag)
        b.order = self.order
        b.succs = list(self.succs)
        b.preds = list(self.succs)
        b.head = self.head
        b.bodies = list(self.bodies)
        b.region = list(self.region)
        return b

    def reconnect(self, blk_map):
        self.head = blk_map[self.head]
        for i, b in enumerate(self.bodies):
            self.bodies[i] = blk_map[b]
        for i, b in enumerate(self.region):
            self.region[i] = blk_map[b]
        for i, succ in enumerate(self.succs):
            self.succs[i] = blk_map[succ]
        for i, pred in enumerate(self.preds):
            self.preds[i] = blk_map[pred]

class BlockReducer:
    def process(self, scope):
        if scope.is_class():
            return
        self.removed_blks = []
        self._merge_unidirectional_block(scope)
        self._remove_empty_block(scope)
        for blk in scope.traverse_blocks():
            blk.order = -1
        Block.set_order(scope.entry_block, 0)

        # update scope's paths
        if self.removed_blks:
            for r in self.removed_blks:
                for p in scope.paths:
                    if r in p:
                        p.remove(r)

    def _merge_unidirectional_block(self, scope):
        for block in scope.traverse_blocks():
            #check unidirectional
            # TODO: any jump.typ
            if len(block.preds) == 1 and len(block.preds[0].succs) == 1 and not block.preds[0].stms[-1].typ == 'C':
                pred = block.preds[0]
                assert pred.stms[-1].is_a(JUMP)
                assert pred.succs[0] is block
                assert not pred.succs_loop

                pred.stms.pop() # remove useless jump
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

    def _remove_empty_block(self, scope):
        for block in scope.traverse_blocks():
            if len(block.stms) > 1:
                continue
            if not block.stms:
                assert not block.succs
                for pred in block.preds:
                    if block in pred.succs:
                        pred.succs.remove(block)
                logger.debug('remove empty block ' + block.name)

            elif block.stms[0].is_a(JUMP):
                succ = block.succs[0]
                if succ in block.succs_loop:
                    # do not remove a loopback block
                    continue
                else:
                    succ.preds.remove(block)
                    for pred in block.preds:
                        pred.replace_succ(block, succ)
                        succ.preds.append(pred)

                logger.debug('remove empty block ' + block.name)
                if block is scope.entry_block:
                    scope.entry_block = succ
                self.removed_blks.append(block)

class PathExpTracer:
    def process(self, scope):
        tree = DominatorTreeBuilder(scope).process()
        tree.dump()
        self.tree = tree
        self.traverse_dtree(scope.entry_block)

    def traverse_dtree(self, blk):
        if not blk.stms:
            return
        children = self.tree.get_children_of(blk)
        jump = blk.stms[-1]
        if jump.is_a(JUMP):
            if blk.path_exp:
                for c in children:
                    c.path_exp = blk.path_exp.clone()
        elif jump.is_a(CJUMP):
            if blk.path_exp:
                for c in children:
                    if c is jump.true:
                        c.path_exp = BINOP('And', blk.path_exp.clone(), jump.exp.clone())
                    elif c is jump.false:
                        c.path_exp = BINOP('And', blk.path_exp.clone(), UNOP('Not', jump.exp.clone()))
                    else:
                        c.path_exp = blk.path_exp.clone()
            else:
                jump.true.path_exp = jump.exp.clone()
                jump.false.path_exp = UNOP('Not', jump.exp.clone())
        elif jump.is_a(MCJUMP):
            if blk.path_exp:
                for c in children:
                    if c in jump.targets:
                        idx = jump.targets.index(c)
                        c.path_exp = BINOP('And', blk.path_exp.clone(), jump.conds[idx].clone())
                    else:
                        c.path_exp = blk.path_exp.clone()
            else:
                for t, cond in zip(jump.targets, jump.conds):
                    t.path_exp = cond.clone()
        for child in children:
            self.traverse_dtree(child)


