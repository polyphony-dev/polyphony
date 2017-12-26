from collections import deque, defaultdict
from .ir import *
from .irvisitor import IRVisitor
from .env import env
from logging import getLogger
logger = getLogger(__name__)


class RomDetector(object):
    def _propagate_writable_flag(self):
        for node in self.mrg.collect_top_module_nodes():
            node.set_writable()
            src = node.single_source()
            if src:
                src.set_writable()
        worklist = deque()
        for source in self.mrg.collect_sources():
            if source.is_writable():
                source.propagate_succs(lambda n: n.set_writable())
            else:
                worklist.append(source)

        checked = set()
        while worklist:
            node = worklist.popleft()
            if node not in checked and node.is_writable():
                checked.add(node)
                sources = set([source for source in node.sources()])
                unchecked_sources = sources.difference(checked)
                for s in unchecked_sources:
                    s.propagate_succs(lambda n: n.set_writable() or checked.add(n))
            else:
                unchecked_succs = set(node.succ_ref_nodes()).difference(checked)
                worklist.extend(unchecked_succs)

    def _propagate_info(self):
        for source in self.mrg.collect_sources():
            source.propagate_succs(lambda n: n.update())

    def process_all(self):
        self.mrg = env.memref_graph
        self._propagate_info()
        self._propagate_writable_flag()
