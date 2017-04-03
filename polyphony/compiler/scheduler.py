from collections import defaultdict, deque
from .latency import get_latency
from .irvisitor import IRVisitor
from .ir import *
from .latency import CALL_MINIMUM_STEP
from .utils import unique
from .scope import Scope
from logging import getLogger
logger = getLogger(__name__)

MAX_FUNC_UNIT = 10


class Scheduler(object):
    def __init__(self):
        self.done_blocks = []
        self.res_tables = {}

    def schedule(self, scope):
        self.scope = scope
        self._node_sched = self._node_sched_default
        for dfg in self.scope.dfgs(bottom_up=True):
            self.res_tables = {}
            self._schedule(scope, dfg)

    def _schedule(self, scope, dfg):
        logger.log(0, '_schedule dfg')
        dfg.create_edge_cache()
        sources = dfg.find_src()
        for src in sources:
            src.priority = -1

        worklist = deque()
        worklist.append((sources, 0))

        while worklist:
            nodes, prio = worklist.popleft()
            for n in nodes:
                succs, nextprio = self._set_priority(n, prio, dfg)
                if succs:
                    succs = unique(succs)
                    worklist.append((succs, nextprio))
        nodes = dfg.get_highest_priority_nodes()
        latency = self._list_schedule(dfg, nodes)
        if latency > CALL_MINIMUM_STEP:
            scope.asap_latency = latency
        else:
            scope.asap_latency = CALL_MINIMUM_STEP

    def _set_priority(self, node, prio, dfg):
        if prio > node.priority:
            node.priority = prio
            logger.debug('update priority ... ' + str(node))
            return (dfg.succs_without_back(node), prio + 1)
        return (None, None)

    def _node_sched_default(self, dfg, node):
        preds = dfg.preds_without_back(node)
        if preds:
            defuse_preds = dfg.preds_typ_without_back(node, 'DefUse')
            usedef_preds = dfg.preds_typ_without_back(node, 'UseDef')
            seq_preds = dfg.preds_typ_without_back(node, 'Seq')
            sched_times = []
            if seq_preds:
                earliest_node = min(seq_preds, key=lambda p: p.begin)
                latest_node = max(seq_preds, key=lambda p: p.end)
                if earliest_node.begin == latest_node.end:
                    sched_times.append(latest_node.end + 1)
                else:
                    sched_times.append(latest_node.end)
            if defuse_preds:
                latest_node = max(defuse_preds, key=lambda p: p.end)
                sched_times.append(latest_node.end)
            if usedef_preds:
                latest_node = max(usedef_preds, key=lambda p: p.end)
                sched_times.append(latest_node.begin)
            if not sched_times:
                latest_node = max(preds, key=lambda p: p.begin)
                sched_times.append(latest_node.begin)
            scheduled_time = max(sched_times)
            if scheduled_time < 0:
                scheduled_time = 0
        else:
            # source node
            scheduled_time = 0
        return scheduled_time

    def _list_schedule(self, dfg, nodes):
        next_candidates = set()
        last_latency = 0
        for n in sorted(nodes, key=lambda n: (n.priority, n.stm_index)):
            scheduled_time = self._node_sched(dfg, n)
            latency = get_latency(n.tag)
            #detect resource conflict
            scheduled_time = self._get_earliest_res_free_time(n, scheduled_time, latency)
            n.begin = scheduled_time
            n.end = n.begin + latency
            #logger.debug('## SCHEDULED ## ' + str(n))
            succs = dfg.succs_without_back(n)
            next_candidates = next_candidates.union(succs)
            last_latency = n.end
        if next_candidates:
            return self._list_schedule(dfg, next_candidates)
        else:
            return last_latency

    def _is_resource_full(self, res, scheduled_resources):
        # TODO:
        if isinstance(res, str):
            return len(scheduled_resources) >= MAX_FUNC_UNIT
        elif isinstance(res, Scope):
            return len(scheduled_resources) >= MAX_FUNC_UNIT
        return 0

    def _str_res(self, res):
        if isinstance(res, str):
            return res
        elif isinstance(res, Scope):
            return res.name

    def _get_earliest_res_free_time(self, node, time, latency):
        resources = self._get_needed_resources(node.tag)
        #TODO operator chaining?
        #logger.debug(node)
        #logger.debug(resources)
        assert len(resources) <= 1
        if resources:
            res = resources[0]
            if res not in self.res_tables:
                table = defaultdict(list)
                self.res_tables[res] = table
            else:
                table = self.res_tables[res]

            scheduled_resources = table[time]
            if node in scheduled_resources:
                #already scheduled
                return time

            while self._is_resource_full(res, scheduled_resources):
                logger.debug("!!! resource {}'s slot '{}' is full !!!".
                             format(self._str_res(res), time))
                time += 1
                scheduled_resources = table[time]

            node.instance_num = len(scheduled_resources)
            #logger.debug("{} is scheduled to {}, instance_num {}".
            #             format(node, time, node.instance_num))

            # fill scheduled_resources table
            n = latency if latency != 0 else 1
            for i in range(n):
                scheduled_resources = table[time + i]
                scheduled_resources.append(node)

        return time

    def _get_needed_resources(self, stm):
        res_extractor = ResourceExtractor()
        res_extractor.visit(stm)
        return res_extractor.results


class ResourceExtractor(IRVisitor):
    def __init__(self):
        super().__init__()
        self.results = []

    def visit_UNOP(self, ir):
        self.visit(ir.exp)
        #TODO:
        #self.results.append(ir.op)

    def visit_BINOP(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)
        self.results.append(ir.op)

    def visit_RELOP(self, ir):
        self.visit(ir.left)
        self.visit(ir.right)
        self.results.append(ir.op)

    def visit_CONDOP(self, ir):
        self.visit(ir.cond)
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_args(self, args):
        for _, arg in args:
            self.visit(arg)

    def visit_CALL(self, ir):
        self.results.append(ir.func_scope)
        self.visit_args(ir.args)

    def visit_SYSCALL(self, ir):
        self.visit_args(ir.args)

    def visit_NEW(self, ir):
        self.visit_args(ir.args)

    def visit_CONST(self, ir):
        pass

    def visit_MREF(self, ir):
        assert ir.mem.is_a(TEMP) or ir.mem.is_a(ATTR)
        assert ir.offset.is_a([TEMP, CONST, UNOP])

    def visit_MSTORE(self, ir):
        assert ir.mem.is_a(TEMP) or ir.mem.is_a(ATTR)
        assert ir.offset.is_a([TEMP, CONST])
        assert ir.exp.is_a([TEMP, CONST])

    def visit_ARRAY(self, ir):
        for item in ir.items:
            assert item.is_a([TEMP, CONST])

    def visit_TEMP(self, ir):
        pass

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_JUMP(self, ir):
        pass

    def visit_RET(self, ir):
        pass

    def visit_MOVE(self, ir):
        self.visit(ir.src)
        self.visit(ir.dst)

    def visit_PHI(self, ir):
        pass
