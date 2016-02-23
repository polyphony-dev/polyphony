from collections import defaultdict
from .latency import get_latency
from .irvisitor import IRVisitor
from .ir import CONST, TEMP, UNOP
from logging import getLogger, INFO, DEBUG
logger = getLogger(__name__)
#logger.setLevel(INFO)

MAX_FUNC_UNIT = 10

class Scheduler:
    def __init__(self):
        self.done_blocks = []
        self.res_tables = {}

    def schedule(self, scope):
        self.scope = scope
        for dfg in self.scope.dfgs(bottom_up=True):
            self._schedule(scope, dfg)

    def _schedule(self, scope, dfg):
        logger.log(0, '_schedule dfg')
        dfg.create_edge_cache()
        sources = dfg.find_src()
        for src in sources:
            src.priority = -1
        for src in sources:
            self._set_priority(src, 0, dfg)

        nodes = dfg.get_highest_priority_nodes()
        self._list_schedule(dfg, nodes)


    def _set_priority(self, node, prio, dfg):
        updated = False
        if prio > node.priority:
            node.priority = prio
            updated = True
            #logger.debug('update priority ... ' + str(node))
        if updated:
            for succ in dfg.succs_without_back(node):
                self._set_priority(succ, prio+1, dfg)


    def _list_schedule(self, dfg, nodes):
        next_candidates = set()
        for n in sorted(nodes, key=lambda n: (n.priority, n.stm_index)):
            preds = dfg.preds_without_back(n)
            if preds:
                latest_node = max(preds, key=lambda p: p.end)
                scheduled_time = latest_node.end
                if scheduled_time < 0:
                    scheduled_time = 0
            else:
                scheduled_time = 0

            latency = get_latency(n.tag)
            #detect resource conflict
            scheduled_time = self._get_earliest_res_free_time(n, scheduled_time, latency)
            n.begin = scheduled_time
            n.end = n.begin + latency
            #logger.debug('## SCHEDULED ## ' + str(n))
            succs = dfg.succs_without_back(n)
            next_candidates = next_candidates.union(succs)

        if next_candidates:
            self._list_schedule(dfg, next_candidates)


    def _get_earliest_res_free_time(self, node, time, latency):
        if not node.is_stm():
            return time

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

            scheduled_funcs = table[time]
            if node in scheduled_funcs:
                #already scheduled
                return time

            while len(scheduled_funcs) >= MAX_FUNC_UNIT:
                logger.debug("!!! resource {}'s slot '{}' is full !!!".format(res, time))
                time += 1
                scheduled_funcs = table[time]
                if len(scheduled_funcs) < MAX_FUNC_UNIT:
                    break

            node.instance_num = len(scheduled_funcs)
            #logger.debug("{} is scheduled to {}, instance_num {}".format(node, time, node.instance_num))

            #fill scheduled_funcs table
            n = latency if latency != 0 else 1
            for i in range(n):
                scheduled_funcs = table[time+i]
                scheduled_funcs.append(node)

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

    def visit_CALL(self, ir):
        self.results.append(ir.func.sym.name)
        for arg in ir.args:
            self.visit(arg)

    def visit_SYSCALL(self, ir):
        for arg in ir.args:
            self.visit(arg)

    def visit_CONST(self, ir):
        pass

    def visit_MREF(self, ir):
        assert isinstance(ir.mem, TEMP)
        assert isinstance(ir.offset, TEMP) or isinstance(ir.offset, CONST) or isinstance(ir.offset, UNOP)

    def visit_MSTORE(self, ir):
        assert isinstance(ir.mem, TEMP)
        assert isinstance(ir.offset, TEMP) or isinstance(ir.offset, CONST)
        assert isinstance(ir.exp, TEMP) or isinstance(ir.exp, CONST)

    def visit_ARRAY(self, ir):
        for item in ir.items:
            assert isinstance(item, TEMP) or isinstance(item, CONST)

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


