from collections import defaultdict
from .ir import *
from .synth import make_synth_params
from .utils import replace_item, remove_except_one
from logging import getLogger
logger = getLogger(__name__)


class Block(object):
    @classmethod
    def set_order(cls, block, order):
        order += 1
        if order > block.order:
            logger.debug(block.name + ' order ' + str(order))
            block.order = order

            succs = [succ for succ in block.succs if succ not in block.succs_loop]
            for succ in succs:
                cls.set_order(succ, order)

    def __init__(self, scope, nametag='b'):
        self.nametag = nametag
        self.stms = []
        self.succs = []
        self.preds = []
        self.succs_loop = []
        self.preds_loop = []
        self.order = -1
        self.scope = scope
        if nametag == 'tmp':
            self.num = -1
            self.name = '{}_{}'.format(scope.name, self.nametag)
        else:
            scope.block_count += 1
            self.num = scope.block_count
            self.name = '{}_{}{}'.format(scope.name, self.nametag, self.num)
        self.path_exp = None
        self.synth_params = make_synth_params()
        self.is_hyperblock = False

    def _str_connection(self):
        s = ''
        bs = []
        s += ' # preds: {'
        for blk in self.preds:
            if blk in self.preds_loop:
                bs.append(blk.name + '$LOOP')
            else:
                bs.append(blk.name)
        s += ', '.join([b for b in bs])
        s += '}\n'

        bs = []
        s += ' # succs: {'
        for blk in self.succs:
            if blk in self.succs_loop:
                bs.append(blk.name + '$LOOP')
            else:
                bs.append(blk.name)
        s += ', '.join([b for b in bs])
        s += '}\n'
        s += ' # synthesis params {}\n'.format(self.synth_params)

        return s

    def __str__(self):
        s = 'Block: (' + str(self.order) + ') ' + str(self.name) + '\n'
        s += self._str_connection()
        if self.path_exp:
            s += ' # path exp: '
            s += str(self.path_exp) + '\n'
        s += ' # code\n'
        s += '\n'.join(['  ' + str(stm) for stm in self.stms])
        s += '\n\n'
        return s

    def __repr__(self):
        return self.name

    def __lt__(self, other):
        return self.order < other.order

    def connect(self, next_block):
        self.succs.append(next_block)
        next_block.preds.append(self)

    def connect_loop(self, next_block):
        self.connect(next_block)
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
        replace_item(self.succs, old, new, all=True)
        if self.stms:
            jmp = self.stms[-1]
            if jmp.is_a(JUMP):
                jmp.target = new
            elif jmp.is_a(CJUMP):
                if jmp.true is old:
                    jmp.true = new
                elif jmp.false is old:
                    jmp.false = new
                self._convert_if_unidirectional(jmp)
            elif jmp.is_a(MCJUMP):
                for i, t in enumerate(jmp.targets):
                    if t is old:
                        jmp.targets[i] = new
                self._convert_if_unidirectional(jmp)

    def replace_succ_loop(self, old, new):
        replace_item(self.succs_loop, old, new, all=True)

    def replace_pred(self, old, new):
        replace_item(self.preds, old, new, all=True)

    def replace_pred_loop(self, old, new):
        replace_item(self.preds_loop, old, new, all=True)

    def remove_pred(self, pred):
        assert pred in self.preds
        self.preds.remove(pred)
        if pred in self.preds_loop:
            self.preds_loop.remove(pred)

    def remove_succ(self, succ):
        assert succ in self.succs
        self.succs.remove(succ)
        if succ in self.succs_loop:
            self.succs_loop.remove(succ)

    def traverse(self, visited):
        if self in visited:
            return
        if self not in visited:
            visited.add(self)
            yield self
        for succ in [succ for succ in self.succs if succ not in self.succs_loop]:
            yield from succ.traverse(visited)

    def clone(self, scope, stm_map, nametag=None):
        if nametag:
            b = Block(scope, nametag)
        else:
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
        b.synth_params = self.synth_params.copy()
        b.is_hyperblock = self.is_hyperblock
        if self.path_exp:
            b.path_exp = self.path_exp.clone()
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

    def _convert_if_unidirectional(self, jmp):
        if not self.scope.usedef:
            return
        if jmp.is_a(CJUMP):
            conds = [jmp.exp]
            targets = [jmp.true, jmp.false]
        elif jmp.is_a(MCJUMP):
            conds = jmp.conds[:]
            targets = jmp.targets[:]
        else:
            return

        if all([targets[0] is target for target in targets[1:]]):
            newjmp = JUMP(targets[0])
            newjmp.block = self
            self.stms[-1] = newjmp
            self.succs = [targets[0]]
            targets[0].preds = remove_except_one(targets[0].preds, self)
            targets[0].path_exp = self.path_exp
        else:
            return

        if self.is_hyperblock:
            return
        usedef = self.scope.usedef
        for cond in conds:
            if cond.is_a(CONST):
                continue
            defstms = usedef.get_stms_defining(cond.symbol())
            assert len(defstms) == 1
            stm = defstms.pop()
            usestms = usedef.get_stms_using(cond.symbol())
            if len(usestms) > 1:
                continue
            stm.block.stms.remove(stm)

    def is_loop_head(self):
        r = self.scope.find_region(self)
        return r and r is not self.scope.top_region() and r.head is self
