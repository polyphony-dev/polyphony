import itertools
from collections import defaultdict, deque
from .common import fail, warn
from .dataflow import DFNode
from .errors import Errors, Warnings
from .graph import Graph
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

    def schedule(self, scope):
        if scope.is_namespace() or scope.is_class() or scope.is_lib():
            return
        self.scope = scope
        for dfg in self.scope.dfgs(bottom_up=True):
            if dfg.parent and dfg.synth_params['scheduling'] == 'pipeline':
                scheduler_impl = PipelineScheduler()
            else:
                scheduler_impl = BlockBoundedListScheduler()
            scheduler_impl.schedule(scope, dfg)


class SchedulerImpl(object):
    def __init__(self):
        self.res_tables = {}
        self.node_latency_map = {}  # {node:(max, min, actual)}
        self.node_seq_latency_map = {}
        self.all_paths = []
        self.res_extractor = None

    def schedule(self, scope, dfg):
        self.scope = scope
        logger.log(0, '_schedule dfg')
        sources = dfg.find_src()
        for src in sources:
            src.priority = -1

        self.res_extractor = ResourceExtractor()
        for node in sorted(dfg.traverse_nodes(dfg.succs, sources, [])):
            self.res_extractor.current_node = node
            self.res_extractor.visit(node.tag)

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
        resources = self.res_extractor.ops[node].keys()
        #TODO operator chaining?
        #logger.debug(node)
        #logger.debug(resources)
        assert len(resources) <= 1
        if resources:
            res = list(resources)[0]
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

    def _max_latency(self, paths):
        max_latency = 0
        for path in paths:
            path_latencies = []
            for n in path:
                m, _, _ = self.node_latency_map[n]
                path_latencies.append(m)
            path_latency = sum(path_latencies)
            if path_latency > max_latency:
                max_latency = path_latency
        return max_latency

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
    def _schedule(self, dfg):
        self._schedule_cycles(dfg)
        self._remove_alias_if_needed(dfg)

        block_nodes = self._group_nodes_by_block(dfg)
        longest_latency = 0
        for block, nodes in block_nodes.items():
            #latency = self._list_schedule(dfg, nodes)
            latency = self._list_schedule_with_block_bound(dfg, nodes, block, 0)
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

    def _list_schedule_with_block_bound(self, dfg, nodes, block, longest_latency):
        next_candidates = set()
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
            if longest_latency < n.end:
                longest_latency = n.end
        if next_candidates:
            return self._list_schedule_with_block_bound(dfg, next_candidates, block,
                                                        longest_latency)
        else:
            return longest_latency

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
                if node.tag.is_a([JUMP, CJUMP, MCJUMP]) or has_exclusive_function(node.tag):
                    latest_node = max(seq_preds, key=lambda p: p.end)
                    sched_time = latest_node.end
                else:
                    latest_node = max(seq_preds, key=lambda p: (p.begin, p.end))
                    seq_latency = self.node_seq_latency_map[latest_node]
                    sched_time = latest_node.begin + seq_latency
                sched_times.append(sched_time)
                logger.debug('latest_node of seq_preds ' + str(latest_node))
                logger.debug('schedtime ' + str(sched_time))
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
    def _schedule(self, dfg):
        self._schedule_cycles(dfg)
        self._schedule_ii(dfg)
        self._remove_alias_if_needed(dfg)
        self.d2c = {}
        block_nodes = self._group_nodes_by_block(dfg)
        longest_latency = 0
        for block, nodes in block_nodes.items():
            latency = self._list_schedule_for_pipeline(dfg, nodes, 0)
            conflict_res_table = self._make_conflict_res_table(nodes)
            if conflict_res_table:
                logger.debug('before rescheduling')
                for n in dfg.get_scheduled_nodes():
                    logger.debug(n)
                latency = self._reschedule_for_conflict(dfg, conflict_res_table, latency)
            if longest_latency < latency:
                longest_latency = latency
            self._fill_defuse_gap(dfg, nodes)
        logger.debug('II = ' + str(dfg.ii))
        return longest_latency

    def _make_conflict_res_table(self, nodes):
        conflict_res_table = defaultdict(list)
        self._extend_conflict_res_table(conflict_res_table, nodes, self.res_extractor.mems)
        self._extend_conflict_res_table(conflict_res_table, nodes, self.res_extractor.ports)
        self._extend_conflict_res_table(conflict_res_table, nodes, self.res_extractor.regarrays)
        return conflict_res_table

    def _extend_conflict_res_table(self, table, target_nodes, node_res_map):
        for node, res in node_res_map.items():
            if node not in target_nodes:
                continue
            for r in res:
                table[r].append(node)

    def max_cnode_num(self, cgraph):
        max_cnode = defaultdict(int)
        for cnode in cgraph.get_nodes():
            max_cnode[cnode.res] += 1
        if max_cnode:
            return max(list(max_cnode.values()))
        else:
            return 0

    def _schedule_ii(self, dfg):
        initiation_interval = int(dfg.synth_params['ii'])
        if not self.all_paths:
            for path in dfg.trace_all_paths(lambda n: dfg.succs_typ_without_back(n, 'DefUse')):
                self.all_paths.append(path)
        induction_paths = self._find_induction_paths(self.all_paths)
        if initiation_interval < 0:
            latency = self._max_latency(induction_paths)
            dfg.ii = latency if latency > 0 else 1
        else:
            ret, actual = self._adjust_latency(induction_paths, initiation_interval)
            if not ret:
                assert False, 'scheduling of II has failed'
            dfg.ii = actual

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

    def _get_using_resources(self, node):
        res = []
        if node in self.res_extractor.mems:
            res.extend(self.res_extractor.mems[node])
        if node in self.res_extractor.ports:
            res.extend(self.res_extractor.ports[node])
        if node in self.res_extractor.regarrays:
            res.extend(self.res_extractor.regarrays[node])
        return res

    def find_cnode(self, cgraph, stm):
        if cgraph is None:
            return None
        for cnode in cgraph.get_nodes():
            if isinstance(cnode, ConflictNode):
                if stm in cnode.items:
                    return cnode
            else:
                if stm is cnode:
                    return cnode
        return None

    def _list_schedule_for_pipeline(self, dfg, nodes, longest_latency):
        next_candidates = set()
        for n in sorted(nodes, key=lambda n: (n.priority, n.stm_index)):
            scheduled_time = self._node_sched_pipeline(dfg, n)
            _, _, latency = self.node_latency_map[n]
            #detect resource conflict
            # TODO:
            #scheduled_time = self._get_earliest_res_free_time(n, scheduled_time, latency)
            if scheduled_time > n.begin:
                n.begin = scheduled_time
                if n in self.d2c:
                    cnode = self.d2c[n]
                    for dnode in cnode.items:
                        if dnode is n:
                            continue
                        dnode.begin = n.begin
                        next_candidates.add(dnode)
            n.end = n.begin + latency
            #logger.debug('## SCHEDULED ## ' + str(n))
            succs = dfg.succs_without_back(n)
            next_candidates = next_candidates.union(succs)
            if longest_latency < n.end:
                longest_latency = n.end
        if next_candidates:
            return self._list_schedule_for_pipeline(dfg,
                                                    next_candidates,
                                                    longest_latency)
        else:
            return longest_latency

    def _reschedule_for_conflict(self, dfg, conflict_res_table, longest_latency):
        self.cgraph = ConflictGraphBuilder(self.scope, dfg).build(conflict_res_table)
        conflict_n = self.max_cnode_num(self.cgraph)
        if conflict_n == 0:
            return longest_latency
        request_ii = int(dfg.synth_params['ii'])
        if request_ii == -1:
            if dfg.ii < conflict_n:
                # TODO: show warnings
                dfg.ii = conflict_n
        elif request_ii < conflict_n:
            fail((self.scope, dfg.region.head.stms[0].lineno),
                 Errors.RULE_INVALID_II, [request_ii, conflict_n])

        for cnode in self.cgraph.get_nodes():
            for dnode in cnode.items:
                self.d2c[dnode] = cnode

        next_candidates = set()
        # sync stms in a cnode
        for cnode in self.cgraph.get_nodes():
            if len(cnode.items) == 1:
                continue
            cnode_begin = max([dnode.begin for dnode in cnode.items])
            for dnode in cnode.items:
                delta = cnode_begin - dnode.begin
                dnode.begin += delta
                dnode.end += delta
                if delta:
                    next_candidates.add(dnode)
        logger.debug('sync dnodes in cnode')
        logger.debug(self.cgraph.nodes)
        cnodes = sorted(self.cgraph.get_nodes(), key=lambda cn:(cn.items[0].begin, cn.items[0].priority))
        cnode_map = defaultdict(list)
        for cnode in cnodes:
            cnode_map[cnode.res].append(cnode)
        ii = dfg.ii
        while True:
            for res, nodes in cnode_map.items():
                remain_states = [i for i in range(ii)]
                for cnode in nodes:
                    cnode_begin = cnode.items[0].begin
                    state = cnode_begin % ii
                    if state in remain_states:
                        remain_states.remove(state)
                        cnode.state = state
                    else:
                        for i, s in enumerate(remain_states):
                            if state < s:
                                popi = i
                                break
                        else:
                            popi = 0
                        cnode.state = remain_states.pop(popi)
                        offs = ii - (cnode.state + 1)
                        new_begin = (cnode_begin + offs) // ii * ii + cnode.state
                        for dnode in cnode.items:
                            dnode.begin = new_begin
                            next_candidates.add(dnode)
            if next_candidates:
                longest_latency = self._list_schedule_for_pipeline(dfg,
                                                                   next_candidates,
                                                                   longest_latency)
                logger.debug(self.cgraph.nodes)
                next_candidates.clear()
            else:
                break
        return longest_latency

    def _node_sched_pipeline(self, dfg, node):
        preds = dfg.preds_without_back(node)
        if preds:
            defuse_preds = dfg.preds_typ_without_back(node, 'DefUse')
            usedef_preds = dfg.preds_typ_without_back(node, 'UseDef')
            seq_preds = dfg.preds_typ_without_back(node, 'Seq')
            sched_times = []
            if seq_preds:
                if node.tag.is_a([JUMP, CJUMP, MCJUMP]) or has_exclusive_function(node.tag):
                    latest_node = max(seq_preds, key=lambda p: p.end)
                    sched_times.append(latest_node.end)
                    logger.debug('latest_node of seq_preds ' + str(latest_node))
                else:
                    latest_node = max(seq_preds, key=lambda p: (p.begin, p.end))
                    seq_latency = self.node_seq_latency_map[latest_node]
                    sched_times.append(latest_node.begin + seq_latency)
                    logger.debug('latest_node of seq_preds ' + str(latest_node))
                    logger.debug('schedtime ' + str(latest_node.begin + seq_latency))
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
            if self._get_using_resources(node):
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
        self.ops = defaultdict(lambda: defaultdict(int))
        self.mems = defaultdict(list)
        self.ports = defaultdict(list)
        self.regarrays = defaultdict(list)

    def visit_BINOP(self, ir):
        self.ops[self.current_node][ir.op] += 1
        super().visit_BINOP(ir)

    def visit_CALL(self, ir):
        self.ops[self.current_node][ir.func_scope()] += 1
        func_name = ir.func_scope().name
        if (func_name.startswith('polyphony.io.Port') or
                func_name.startswith('polyphony.io.Queue')):
            inst_ = ir.func.tail()
            self.ports[self.current_node].append(inst_)
        super().visit_CALL(ir)

    def visit_MREF(self, ir):
        if ir.mem.symbol().typ.get_memnode().can_be_reg():
            self.regarrays[self.current_node].append(ir.mem.symbol())
        else:
            self.mems[self.current_node].append(ir.mem.symbol())
        super().visit_MREF(ir)

    def visit_MSTORE(self, ir):
        if ir.mem.symbol().typ.get_memnode().can_be_reg():
            self.regarrays[self.current_node].append(ir.mem.symbol())
        else:
            self.mems[self.current_node].append(ir.mem.symbol())
        super().visit_MSTORE(ir)


class ConflictNode(object):
    READ = 1
    WRITE = 2

    def __init__(self, access, items):
        self.res = ''
        self.access = access
        self.items = items

    @classmethod
    def create(self, dn):
        assert isinstance(dn, DFNode)
        access = ConflictNode.READ if dn.defs else ConflictNode.WRITE
        return ConflictNode(access, [dn])

    @classmethod
    def create_merge_node(self, n0, n1):
        assert isinstance(n0, ConflictNode)
        assert isinstance(n1, ConflictNode)
        return ConflictNode(n0.access | n1.access, n0.items + n1.items)

    @classmethod
    def create_split_node(self, n, items):
        assert isinstance(n, ConflictNode)
        assert set(items) & set(n.items) == set(items)
        for dn in n.items[:]:
            if dn in items:
                n.items.remove(dn)
        n.access = 0
        for dn in n.items:
            n.access |= ConflictNode.READ if dn.defs else ConflictNode.WRITE
        access = 0
        for dn in items:
            access |= ConflictNode.READ if dn.defs else ConflictNode.WRITE
        return ConflictNode(access, list(items))

    def __str__(self):
        access_str = ''
        if self.access & ConflictNode.READ:
            access_str += 'R'
        if self.access & ConflictNode.WRITE:
            access_str += 'W'
        s = '---- {}, {}, {}\n'.format(len(self.items), access_str, self.res)
        s += '\n'.join(['  ' + str(i) for i in self.items])
        s += '\n'
        return s

    def __repr__(self):
        return self.__str__()


class ConflictGraphBuilder(object):
    def __init__(self, scope, dfg):
        self.scope = scope
        self.dfg = dfg

    def build(self, conflict_res_table):
        cgraphs = self._build_conflict_graphs(conflict_res_table)
        cgraph = self._build_master_conflict_graph(cgraphs)
        return cgraph

    def _build_master_conflict_graph(self, cgraphs):
        master_cgraph = Graph()
        for res, graph in cgraphs.items():
            assert not graph.edges
            accs = []
            for cnode in graph.get_nodes():
                cnode.res = res
                master_cgraph.add_node(cnode)
                accs.append(cnode.access)
            if accs.count(accs[0]) == len(accs) and (accs[0] == ConflictNode.READ or accs[0] == ConflictNode.WRITE):
                pass
            else:
                warn(cnode.items[0].tag,
                     Warnings.RULE_PIPELINE_HAS_RW_ACCESS_IN_THE_SAME_RAM, [res])
        # for cnode in master_cgraph.get_nodes():
        #     for dnode in cnode.items:
        #         preds = self.dfg.collect_all_preds(dnode)
        #         if not preds:
        #             continue
        #         for cnode2 in master_cgraph.get_nodes():
        #             if cnode is cnode2:
        #                 continue
        #             if set(preds).intersection(set(cnode2.items)):
        #                 master_cgraph.add_edge(cnode2, cnode)
        logger.debug(master_cgraph.nodes)
        return master_cgraph

    def _build_conflict_graphs(self, conflict_res_table):
        cgraphs = {}
        for res, nodes in conflict_res_table.items():
            if len(nodes) == 1:
                continue
            cgraph = self._build_conflict_graph_per_res(res, nodes)
            cgraphs[res] = cgraph
        return cgraphs

    def _build_conflict_graph_per_res(self, res, conflict_nodes):
        graph = Graph()
        conflict_stms = [n.tag for n in conflict_nodes]
        stm2cnode = {}
        for n in conflict_nodes:
            stm2cnode[n.tag] = ConflictNode.create(n) 
        for dn in conflict_nodes:
            graph.add_node(stm2cnode[dn.tag])
        for n0, n1, _ in self.scope.branch_graph.edges:
            if n0 in conflict_stms and n1 in conflict_stms:
                graph.add_edge(stm2cnode[n0], stm2cnode[n1])

        self._merge_same_conditional_branch_nodes(graph, conflict_nodes, stm2cnode)

        logger.debug(graph.nodes)

        def edge_order(e):
            begin0 = max([item.begin for item in e.src.items])
            begin1 = max([item.begin for item in e.dst.items])
            begin = (begin0, begin1) if begin0 <= begin1 else (begin1, begin0)
            distance = (begin1 - begin0) if begin0 <= begin1 else (begin0 - begin1)
            lineno0 = min([item.tag.lineno for item in e.src.items])
            lineno1 = min([item.tag.lineno for item in e.dst.items])
            lineno = (lineno0, lineno1) if lineno0 <= lineno1 else (lineno1, lineno0)
            # In order to avoid crossover edge, 'begin' must be given priority
            return (distance, begin, lineno)

        logger.debug('merging nodes that connected with a branch edge...')
        while graph.edges:
            edges = sorted(graph.edges.orders(), key=edge_order)
            n0, n1, _ = edges[0]
            #logger.debug('merge node')
            #logger.debug(str(n0.items))
            #logger.debug(str(n1.items))
            #logger.debug(str(edges))
            if n0.items[0].begin != n1.items[0].begin and n0.access != n1.access:
                graph.del_edge(n0, n1, auto_del_node=False)
                continue
            cnode = ConflictNode.create_merge_node(n0, n1)
            living_nodes = set()
            for n in graph.nodes:
                adjacents = graph.succs(n).union(graph.preds(n))
                if n0 in adjacents and n1 in adjacents:
                    living_nodes.add(n)
            graph.add_node(cnode)
            graph.del_node(n0)
            graph.del_node(n1)
            for n in living_nodes:
                graph.add_edge(cnode, n)
        logger.debug('after merging')
        logger.debug(graph.nodes)
        return graph

    def _merge_same_conditional_branch_nodes(self, graph, conflict_nodes, stm2cnode):
        conflict_nodes = sorted(conflict_nodes, key=lambda dn:dn.begin)
        for begin, dnodes in itertools.groupby(conflict_nodes, key=lambda dn:dn.begin):
            merge_cnodes = defaultdict(set)
            for dn0, dn1 in itertools.permutations(dnodes, 2):
                stm0 = dn0.tag
                stm1 = dn1.tag
                if stm0 > stm1:
                    continue
                cn0 = stm2cnode[stm0]
                cn1 = stm2cnode[stm1]
                e = graph.find_edge(cn0, cn1)
                if e is not None:
                    continue
                if ((stm0.is_a(CMOVE) or stm0.is_a(CEXPR)) and
                        (stm1.is_a(CMOVE) or stm1.is_a(CEXPR))):
                    if stm0.cond == stm1.cond:
                        vs = stm0.cond.find_irs(TEMP)
                        syms = tuple(sorted([v.sym for v in vs]))
                        merge_cnodes[syms].add(cn0)
                        merge_cnodes[syms].add(cn1)
            for cnodes in merge_cnodes.values():
                cnodes = sorted(list(cnodes), key=lambda cn: cn.items[0].tag)
                cn0 = cnodes[0]
                for cn1 in cnodes[1:]:
                    assert cn0.items[0].tag < cn1.items[0].tag
                    mn = ConflictNode.create_merge_node(cn0, cn1)
                    graph.add_node(mn)
                    succs0 = graph.succs(cn0)
                    preds0 = graph.preds(cn0)
                    adjs0 = succs0.union(preds0)
                    succs1 = graph.succs(cn1)
                    preds1 = graph.preds(cn1)
                    adjs1 = succs1.union(preds1)
                    adjs = adjs0.intersection(adjs1)

                    graph.del_node(cn0)
                    graph.del_node(cn1)
                    for adj in adjs:
                        graph.add_edge(mn, adj)
                    cn0 = mn
