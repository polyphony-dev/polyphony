from __future__ import annotations
from collections import deque
from typing import TYPE_CHECKING
from .ir import *
from .synth import make_synth_params
from ..common.utils import replace_item, remove_except_one
from logging import getLogger
logger = getLogger(__name__)
if TYPE_CHECKING:
    from .scope import Scope


class Block(object):
    @classmethod
    def set_order(cls, block, order):
        block.order = order + 1
        logger.debug(block.name + ' order ' + str(block.order))
        queue = deque([block])
        while queue:
            blk = queue.popleft()
            for succ in blk.succs:
                if succ in blk.succs_loop:
                    continue
                if succ.order < blk.order + 1:
                    succ.order = blk.order + 1
                    logger.debug(succ.name + ' order ' + str(succ.order))
                if succ in queue:
                    continue
                queue.append(succ)

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
        if hasattr(scope, 'block_map'):
            scope.block_map[self.bid] = self

    @property
    def bid(self) -> str:
        """Block identifier, unique within a scope (e.g., 'b1', 'loop3', 'tmp')."""
        if self.num < 0:
            return self.nametag
        return f'{self.nametag}{self.num}'

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
        s += ' # path exp: '
        s += str(self.path_exp) + '\n'
        s += ' # code\n'
        str_stms = []
        for stm in self.stms:
            type_str_fn = getattr(stm, 'type_str', None)
            if type_str_fn and type_str_fn(self.scope):
                str_stms.append(f'  {stm}  # {type_str_fn(self.scope)}')
            else:
                str_stms.append(f'  {stm}')
        s += '\n'.join(str_stms)
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
        if stm.block != self.bid:
            stm = stm.model_copy(update={'block': self.bid})
        self.stms.append(stm)
        return stm

    def insert_stm(self, idx, stm):
        if stm.block != self.bid:
            stm = stm.model_copy(update={'block': self.bid})
        self.stms.insert(idx, stm)
        return stm

    def replace_stm(self, old_stm, new_stm):
        if new_stm.block != self.bid:
            new_stm = new_stm.model_copy(update={'block': self.bid})
        replace_item(self.stms, old_stm, new_stm)
        return new_stm

    def stm(self, idx):
        if len(self.stms):
            return self.stms[idx]
        else:
            return None

    def replace_succ(self, old, new):
        replace_item(self.succs, old, new, all=True)
        if self.stms:
            jmp = self.stms[-1]
            if isinstance(jmp, Jump):
                if jmp.target == old.bid:
                    self.stms[-1] = jmp.model_copy(update={'target': new.bid})
            elif isinstance(jmp, CJump):
                updates = {}
                if jmp.true == old.bid:
                    updates['true'] = new.bid
                if jmp.false == old.bid:
                    updates['false'] = new.bid
                if updates:
                    self.stms[-1] = jmp.model_copy(update=updates)
                self._convert_if_unidirectional(self.stms[-1])
            elif isinstance(jmp, MCJump):
                new_targets = [new.bid if t == old.bid else t for t in jmp.targets]
                if new_targets != list(jmp.targets):
                    self.stms[-1] = jmp.model_copy(update={'targets': new_targets})
                self._convert_if_unidirectional(self.stms[-1])

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

    def traverse(self):
        visited = set()
        stack = [self]
        while stack:
            blk = stack.pop()
            yield blk
            visited.add(blk)
            for succ in reversed(blk.succs):
                if (succ in blk.succs_loop or
                        succ in visited or
                        succ in stack):
                    continue
                stack.append(succ)

    def clone(self, scope: Scope, stm_map: dict[IrStm, IrStm], nametag=None):
        if nametag:
            b = Block(scope, nametag)
        else:
            b = Block(scope, self.nametag)
        for stm in self.stms:
            new_stm = stm.clone()
            new_stm = new_stm.model_copy(update={'block': b.bid})
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
        if isinstance(typs, list):
            typs = tuple(typs)
        return [stm for stm in self.stms if isinstance(stm, typs)]


    def _convert_if_unidirectional(self, jmp):
        if isinstance(jmp, CJump):
            targets = [jmp.true, jmp.false]
        elif isinstance(jmp, MCJump):
            targets = jmp.targets[:]
        else:
            return

        if all(targets[0] == t for t in targets[1:]):
            newjmp = Jump(target=targets[0], block=self.bid)
            self.stms[-1] = newjmp
            target_block = self.scope.find_block(targets[0])
            self.succs = [target_block]
            target_block.preds = remove_except_one(target_block.preds, self)
            target_block.path_exp = self.path_exp

    def is_loop_head(self):
        r = self.scope.find_region(self)
        return r and r is not self.scope.top_region() and r.head is self
