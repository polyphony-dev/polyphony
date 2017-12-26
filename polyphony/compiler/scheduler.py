from collections import defaultdict, deque
from .common import fail, warn
from .errors import Errors, Warnings
from .latency import get_latency
from .irvisitor import IRVisitor
from .ir import *
from .irhelper import has_exclusive_function
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
        if scope.is_namespace() or scope.is_class() or scope.is_lib():
            return
        self.scope = scope
        for dfg in self.scope.dfgs(bottom_up=True):
            self.res_tables = {}
            if dfg.parent and dfg.synth_params['scheduling'] == 'pipeline':
                scheduler_impl = PipelineScheduler(self.res_tables)
            else:
                scheduler_impl = BlockBoundedListScheduler(self.res_tables)
            scheduler_impl.schedule(scope, dfg)


class SchedulerImpl(object):
    def __init__(self, res_tables):
        self.res_tables = res_tables
        self.node_latency_map = {}  # {node:(max, min, actual)}
        self.node_seq_latency_map = {}
        self.all_paths = []

    def schedule(self, scope, dfg):
        logger.log(0, '_schedule dfg')
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
        longest_latency = self._schedule(dfg)
        if longest_latency > CALL_MINIMUM_STEP:
            scope.asap_latency = longest_latency
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
                latest_node = max(seq_preds, key=lambda p: p.end)
                sched_times.append(latest_node.end)
            if defuse_preds:
                latest_node = max(defuse_preds, key=lambda p: p.end)
                sched_times.append(latest_node.end)
            if usedef_preds:
                preds = usedef_preds
                latest_node = max(preds, key=lambda p: p.begin)
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

    def _find_latest_alias(self, dfg, node):
        stm = node.tag
        if not stm.is_a([MOVE, PHIBase]):
            return node
        var = node.tag.dst.symbol() if node.tag.is_a(MOVE) else node.tag.var.symbol()
        if not var.is_alias():
            return node
        succs = dfg.succs_typ_without_back(node, 'DefUse')
        if not succs:
            return node
        nodes = [self._find_latest_alias(dfg, s) for s in succs]
        latest_node = max(nodes, key=lambda p: p.end)
        return latest_node

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

    def _calc_latency(self, dfg):
        is_minimum = dfg.synth_params['cycle'] == 'minimum'
        for node in dfg.get_priority_ordered_nodes():
            def_l, seq_l = get_latency(node.tag)
            if def_l == 0:
                if is_minimum:
                    self.node_latency_map[node] = (0, 0, 0)
                else:
                    if node.tag.is_a([MOVE, PHIBase]):
                        var = node.tag.dst.symbol() if node.tag.is_a(MOVE) else node.tag.var.symbol()
                        if var.is_condition():
                            self.node_latency_map[node] = (0, 0, 0)
                        else:
                            self.node_latency_map[node] = (1, 0, 1)
                    else:
                        self.node_latency_map[node] = (0, 0, 0)
            else:
                self.node_latency_map[node] = (def_l, def_l, def_l)
            self.node_seq_latency_map[node] = seq_l

    def _adjust_latency(self, paths, expected):
        for path in paths:
            path_latencies = []
            for n in path:
                m, _, _ = self.node_latency_map[n]
                path_latencies.append(m)
            path_latency = sum(path_latencies)
            if expected > path_latency:
                # we don't have to adjust latency
                continue
            diff = path_latency - expected
            fixed = set()
            succeeded = True
            # try to reduce latency
            while diff:
                for i, n in enumerate(path):
                    if n in fixed:
                        continue
                    max_l, min_l, _ = self.node_latency_map[n]
                    if min_l < path_latencies[i]:
                        path_latencies[i] -= 1
                        self.node_latency_map[n] = (max_l, min_l, path_latencies[i])
                        diff -= 1
                    else:
                        fixed.add(n)
                if len(fixed) == len(path):
                    # scheduling has failed
                    succeeded = False
                    break
            if not succeeded:
                return False, expected + diff
        return True, expected

    def _try_adjust_latency(self, dfg, expected):
        for path in dfg.trace_all_paths(lambda n: dfg.succs_typ_without_back(n, 'DefUse')):
            self.all_paths.append(path)
        ret, actual = self._adjust_latency(self.all_paths, expected)
        if not ret:
            assert False, 'scheduling has failed. the cycle must be greater equal {}'.format(actual)

    def _remove_alias_if_needed(self, dfg):
        for n in dfg.nodes:
            if n not in self.node_latency_map:
                continue
            _, min_l, actual = self.node_latency_map[n]
            if min_l == 0 and actual > 0:
                for d in n.defs:
                    if d.is_alias():
                        d.del_tag('alias')

    def _group_nodes_by_block(self, dfg):
        block_nodes = defaultdict(list)
        for node in dfg.get_priority_ordered_nodes():
            block_nodes[node.tag.block].append(node)
        return block_nodes

    def _schedule_cycles(self, dfg):
        self._calc_latency(dfg)
        synth_cycle = dfg.synth_params['cycle']
        if synth_cycle == 'any' or synth_cycle == 'minimum':
            pass
        elif synth_cycle.startswith('less:'):
            extected_latency = int(synth_cycle[len('less:'):])
            self._try_adjust_latency(dfg, extected_latency)
        elif synth_cycle.startswith('greater:'):
            assert False, 'Not Implement Yet'
        else:
            assert False


class BlockBoundedListScheduler(SchedulerImpl):
    def __init__(self, res_tables):
        super().__init__(res_tables)

    def _schedule(self, dfg):
        self._schedule_cycles(dfg)
        self._remove_alias_if_needed(dfg)

        block_nodes = self._group_nodes_by_block(dfg)
        longest_latency = 0
        for block, nodes in block_nodes.items():
            #latency = self._list_schedule(dfg, nodes)
            latency = self._list_schedule_with_block_bound(dfg, nodes, block)
            if longest_latency < latency:
                longest_latency = latency
        return longest_latency

    def _list_schedule(self, dfg, nodes):
        next_candidates = set()
        latency = 0
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
            latency = n.end
        if next_candidates:
            return self._list_schedule(dfg, next_candidates)
        else:
            return latency

    def _list_schedule_with_block_bound(self, dfg, nodes, block):
        next_candidates = set()
        latency = 0
        for n in sorted(nodes, key=lambda n: (n.priority, n.stm_index)):
            if n.tag.block is not block:
                continue
            scheduled_time = self._node_sched_with_block_bound(dfg, n, block)
            _, _, latency = self.node_latency_map[n]
            #detect resource conflict
            scheduled_time = self._get_earliest_res_free_time(n, scheduled_time, latency)
            n.begin = scheduled_time
            n.end = n.begin + latency
            #logger.debug('## SCHEDULED ## ' + str(n))
            succs = dfg.succs_without_back(n)
            next_candidates = next_candidates.union(succs)
            latency = n.end
        if next_candidates:
            return self._list_schedule_with_block_bound(dfg, next_candidates, block)
        else:
            return latency

    def _node_sched_with_block_bound(self, dfg, node, block):
        preds = dfg.preds_without_back(node)
        preds = [p for p in preds if p.tag.block is block]
        logger.debug('scheduling for ' + str(node))
        if preds:
            defuse_preds = dfg.preds_typ_without_back(node, 'DefUse')
            defuse_preds = [p for p in defuse_preds if p.tag.block is block]
            usedef_preds = dfg.preds_typ_without_back(node, 'UseDef')
            usedef_preds = [p for p in usedef_preds if p.tag.block is block]
            seq_preds = dfg.preds_typ_without_back(node, 'Seq')
            seq_preds = [p for p in seq_preds if p.tag.block is block]
            sched_times = []
            if seq_preds:
                latest_node = max(seq_preds, key=lambda p: p.end)
                logger.debug('latest_node of seq_preds ' + str(latest_node))
                if node.tag.is_a([JUMP, CJUMP, MCJUMP]) or has_exclusive_function(node.tag):
                    sched_times.append(latest_node.end)
                else:
                    seq_latency = self.node_seq_latency_map[latest_node]
                    sched_times.append(latest_node.begin + seq_latency)
                    logger.debug('schedtime ' + str(latest_node.begin + seq_latency))
            if defuse_preds:
                latest_node = max(defuse_preds, key=lambda p: p.end)
                logger.debug('latest_node of defuse_preds ' + str(latest_node))
                sched_times.append(latest_node.end)
                logger.debug('schedtime ' + str(latest_node.end))
            if usedef_preds:
                preds = [self._find_latest_alias(dfg, pred) for pred in usedef_preds]
                latest_node = max(preds, key=lambda p: p.begin)
                logger.debug('latest_node(begin) of usedef_preds ' + str(latest_node))
                sched_times.append(latest_node.begin)
                logger.debug('schedtime ' + str(latest_node.begin))
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


class PipelineScheduler(SchedulerImpl):
    def __init__(self, res_tables):
        super().__init__(res_tables)

    def _schedule(self, dfg):
        self._schedule_cycles(dfg)
        self._schedule_ii(dfg)
        self._remove_alias_if_needed(dfg)

        block_nodes = self._group_nodes_by_block(dfg)
        longest_latency = 0
        for block, nodes in block_nodes.items():
            latency = self._list_schedule_for_pipeline(dfg, nodes)
            if longest_latency < latency:
                longest_latency = latency
            self._fill_defuse_gap(dfg, nodes)
        return longest_latency

    def _schedule_ii(self, dfg):
        initiation_interval = int(dfg.synth_params['ii'])
        if not self.all_paths:
            for path in dfg.trace_all_paths(lambda n: dfg.succs_typ_without_back(n, 'DefUse')):
                self.all_paths.append(path)
        induction_paths = self._find_induction_paths(self.all_paths)
        ret, actual = self._adjust_latency(induction_paths, initiation_interval)
        if not ret:
            assert False, 'scheduling of II has failed'

    def _find_induction_paths(self, paths):
        induction_paths = []
        for path in paths:
            last_node = path[-1]
            if not last_node.defs:
                continue
            d = last_node.defs[0]
            if not d.is_induction():
                continue
            for i, p in enumerate(path):
                if d in p.uses:
                    induction_paths.append(path[i:])
                    break
        return induction_paths

    def _list_schedule_for_pipeline(self, dfg, nodes):
        next_candidates = set()
        latency = 0
        for n in sorted(nodes, key=lambda n: (n.priority, n.stm_index)):
            scheduled_time = self._node_sched_pipeline(dfg, n)
            _, _, latency = self.node_latency_map[n]
            #detect resource conflict
            # TODO:
            #scheduled_time = self._get_earliest_res_free_time(n, scheduled_time, latency)
            n.begin = scheduled_time
            n.end = n.begin + latency
            #logger.debug('## SCHEDULED ## ' + str(n))
            succs = dfg.succs_without_back(n)
            next_candidates = next_candidates.union(succs)
            latency = n.end
        if next_candidates:
            return self._list_schedule_for_pipeline(dfg, next_candidates)
        else:
            return latency

    def _node_sched_pipeline(self, dfg, node):
        preds = dfg.preds_without_back(node)
        if preds:
            defuse_preds = dfg.preds_typ_without_back(node, 'DefUse')
            usedef_preds = dfg.preds_typ_without_back(node, 'UseDef')
            seq_preds = dfg.preds_typ_without_back(node, 'Seq')
            sched_times = []
            if seq_preds:
                latest_node = max(seq_preds, key=lambda p: p.end)
                sched_times.append(latest_node.end)
            if defuse_preds:
                latest_node = max(defuse_preds, key=lambda p: p.end)
                sched_times.append(latest_node.end)
            if usedef_preds:
                if any([d.is_induction() for d in node.defs]):
                    pass
                else:
                    preds = usedef_preds
                    latest_node = max(preds, key=lambda p: p.end)
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

    def _fill_defuse_gap(self, dfg, nodes):
        for node in reversed(sorted(nodes, key=lambda n: (n.priority, n.stm_index))):
            succs = dfg.succs_without_back(node)
            succs = [s for s in succs if s.begin >= 0]
            if not succs:
                continue
            nearest_node = min(succs, key=lambda p: p.begin)
            sched_time = nearest_node.begin
            if sched_time > node.end:
                gap = sched_time - node.end
                node.begin += gap
                node.end += gap


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
        #TODO:
        #self.results.append(ir.op)

    def visit_CONDOP(self, ir):
        #TODO:
        #self.visit(ir.cond)
        self.visit(ir.left)
        self.visit(ir.right)

    def visit_args(self, args):
        for _, arg in args:
            self.visit(arg)

    def visit_CALL(self, ir):
        self.results.append(ir.func_scope())
        self.visit_args(ir.args)

    def visit_SYSCALL(self, ir):
        self.visit_args(ir.args)

    def visit_NEW(self, ir):
        self.visit_args(ir.args)

    def visit_EXPR(self, ir):
        self.visit(ir.exp)

    def visit_CJUMP(self, ir):
        self.visit(ir.exp)

    def visit_MCJUMP(self, ir):
        for cond in ir.conds:
            self.visit(cond)

    def visit_MOVE(self, ir):
        self.visit(ir.src)
        self.visit(ir.dst)
