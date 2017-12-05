from .ir import *
from .irhelper import reduce_relexp


class PHIInlining(object):
    def process(self, scope):
        self.phis = {}
        for blk in scope.traverse_blocks():
            for phi in blk.collect_stms([PHI, UPHI]):
                if not phi.var.symbol().is_induction():
                    self.phis[phi.var.symbol()] = phi
        phis_ = list(self.phis.values())
        for phi in phis_:
            for i, arg in enumerate(phi.args):
                if arg.is_a([TEMP, ATTR]) and arg.symbol() in self.phis and phi != self.phis[arg.symbol()]:
                    phi.args.pop(i)
                    phi.defblks.pop(i)
                    p = phi.ps.pop(i)
                    inline_phi = self.phis[arg.symbol()]
                    for offs, ia in enumerate(inline_phi.args):
                        phi.args.insert(i + offs, ia)
                    for offs, iblk in enumerate(inline_phi.defblks):
                        phi.defblks.insert(i + offs, iblk)
                    for offs, ip in enumerate(inline_phi.ps):
                        new_p = reduce_relexp(RELOP('And', p, ip))
                        phi.ps.insert(i + offs, new_p)
