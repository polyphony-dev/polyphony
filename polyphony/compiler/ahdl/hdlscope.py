from collections import defaultdict, OrderedDict
from ..common.env import env
from ..ir.symbol import Symbol
from .signal import Signal
from logging import getLogger
logger = getLogger(__name__)


class HDLScope(object):
    def __init__(self, scope, name, qualified_name):
        self.scope = scope
        self.name = name
        self.qualified_name = qualified_name
        self.signals = {}
        self.sig2sym = {}
        self.sym2sigs = defaultdict(list)
        self.subscopes:dict[Signal, 'HDLScope'] = {}

    def __str__(self):
        s = '---------------------------------\n'
        s += 'HDLScope {}\n'.format(self.name)
        s += self.str_signals()
        return s

    def str_signals(self):
        s = '-- signals --\n'
        for sig in self.signals.values():
            s += f'{sig}\n'
            if sig.is_subscope():
                subscope = self.subscopes[sig]
                ss = subscope.str_signals()
                lines = ss.split('\n')
                s += '\n'.join(['  ' + line for line in lines if line])
                s += '\n'
        return s

    def gen_sig(self, name, width, tag=None, sym=None):
        if name in self.signals:
            sig = self.signals[name]
            sig.width = width
            if tag:
                sig.add_tag(tag)
            return sig
        sig = Signal(self, name, width, tag, sym)
        self.signals[name] = sig
        if sym:
            self.sig2sym[sig] = sym
            self.sym2sigs[sym].append(sig)
        logger.debug(f'{self.name}.gen_sig {sig}')
        return sig

    def signal(self, key) -> Signal|None:
        if isinstance(key, str):
            if key in self.signals:
                return self.signals[key]
        elif isinstance(key, Symbol):
            if key in self.sym2sigs and len(self.sym2sigs[key]) == 1:
                return self.sym2sigs[key][0]
        for base in self.scope.bases:
            basemodule = env.hdlscope(base)
            found = basemodule.signal(key)
            if found:
                return found
        return None

    def find_scope(self, sig:Signal):
        if self.signal(sig.name):
            return self
        else:
            for subscope in self.subscopes.values():
                if subscope.signal(sig.name):
                    return subscope
        return None

    def get_signals(self, include_tags=None, exclude_tags=None, with_base=False):
        if include_tags:
            assert isinstance(include_tags, set)
        if exclude_tags:
            assert isinstance(exclude_tags, set)
        sigs = []
        if with_base:
            for base in self.scope.bases:
                basemodule = env.hdlscope(base)
                sigs.extend(basemodule.get_signals(include_tags, exclude_tags, True))
        for sig in sorted(self.signals.values(), key=lambda sig: sig.name):
            if exclude_tags and exclude_tags & sig.tags:
                continue
            if include_tags:
                ret = include_tags & sig.tags
                if ret:
                    sigs.append(sig)
            else:
                sigs.append(sig)
        return sigs

    def rename_sig(self, old, new):
        assert old in self.signals
        sig = self.signals[old]
        del self.signals[old]
        sig.name = new
        self.signals[new] = sig
        return sig

    def remove_sig(self, sig):
        assert sig.name in self.signals
        del self.signals[sig.name]

    def add_subscope(self, signal:Signal, hdlscope:'HDLScope'):
        self.subscopes[signal] = hdlscope

