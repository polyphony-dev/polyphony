from ..ir import *
from ..irhelper import reduce_relexp, qualified_symbols
from logging import getLogger
logger = getLogger(__name__)


class PHIInlining(object):
    def process(self, scope):
        for blk in scope.traverse_blocks():
            phis = {}
            for phi in blk.collect_stms([PHI, UPHI]):
                var_sym = qualified_symbols(phi.var, scope)[-1]
                assert isinstance(var_sym, Symbol)
                if not var_sym.is_induction():
                    phis[var_sym] = phi
            phis_ = list(phis.values())
            for phi in phis_:
                new_args = []
                new_ps   = []
                for i, (arg, p) in enumerate(zip(phi.args, phi.ps)):
                    if (arg.is_a(IRVariable) and
                            (arg_sym := qualified_symbols(arg, scope)[-1]) and
                            arg_sym in phis and
                            phi != phis[arg_sym]):
                        inline_phi = phis[arg_sym]
                        assert phi.block is inline_phi.block
                        new_args.extend(inline_phi.args)
                        for offs, ip in enumerate(inline_phi.ps):
                            new_p = reduce_relexp(RELOP('And', p, ip))
                            new_ps.append(new_p)
                    else:
                        new_args.append(arg)
                        new_ps.append(p)
                logger.debug('old ' + str(phi))
                phi.args = new_args
                phi.ps = new_ps
                logger.debug('new ' + str(phi))


class LPHIRemover(object):
    def process(self, scope):
        self.scope = scope
        for loop in scope.loop_tree.traverse():
            lphis = loop.head.collect_stms(LPHI)
            if not lphis:
                continue
            assert len(loop.head.preds_loop) == 1
            update_idx = loop.head.preds.index(loop.head.preds_loop[0])
            mstm = MSTM()
            for lphi in lphis:
                lphi.block.stms.remove(lphi)
                for i in range(len(lphi.args)):
                    if i == update_idx:
                        continue
                    init_blk = lphi.block.preds[i]
                    init_arg = lphi.args[i]
                    mv = MOVE(lphi.var.clone(), init_arg, loc=Loc(lphi.loc.filename, 0))
                    init_blk.insert_stm(-1, mv)
                update_arg = lphi.args[update_idx]
                mv = MOVE(lphi.var.clone(), update_arg, loc=lphi.loc)
                mstm.append(mv)
                mv.block = loop.head.preds_loop[0]
            loop.head.preds_loop[0].insert_stm(-1, mstm)
