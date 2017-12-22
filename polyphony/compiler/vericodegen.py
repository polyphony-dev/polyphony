import functools
from .ahdl import *
from .ahdlvisitor import AHDLVisitor
from .env import env
from .hdlinterface import *
from .ir import Ctx
from .memref import One2NMemNode, N2OneMemNode
from .signal import Signal
from .stg import State, PipelineState
from .verilog_common import pyop2verilogop, is_verilog_keyword
from logging import getLogger
logger = getLogger(__name__)


class VerilogCodeGen(AHDLVisitor):
    def __init__(self, hdlmodule):
        self.codes = []
        self.indent = 0
        self.hdlmodule = hdlmodule
        self.mrg = env.memref_graph

    def result(self):
        return ''.join(self.codes)

    def emit(self, code, with_indent=True, newline=True):
        if with_indent:
            self.codes.append((' ' * self.indent) + code)
        else:
            self.codes.append(code)
        if newline:
            self.codes.append('\n')

    def tab(self):
        return ' ' * self.indent

    def set_indent(self, val):
        self.indent += val

    def generate(self):
        """Output verilog module format:

           module {module_name}
           {params}
           {portdefs}
           {localparams}
           {internal_regs}
           {internal_nets}
           {functions}
           {fsm}
           endmodule
        """

        self.set_indent(2)
        for fsm in self.hdlmodule.fsms.values():
            self._generate_process(fsm)
        self.set_indent(-2)
        main_code = self.result()
        self.codes = []

        self._generate_include()
        self._generate_module()
        self.emit(main_code)
        self.emit('endmodule\n')

    def _generate_process(self, fsm):
        self.emit('always @(posedge clk) begin')
        self.set_indent(2)
        self.emit('if (rst) begin')
        self.set_indent(2)

        for stm in sorted(fsm.reset_stms, key=lambda s: str(s)):
            if stm.dst.is_a(AHDL_VAR) and stm.dst.sig.is_net():
                continue
            self.visit(stm)
        if not fsm.stgs:
            self.set_indent(-2)
            self.emit('end')  # end if (READY)
            self.set_indent(-2)
            self.emit('end')
            self.emit('')
            return
        for stg in fsm.stgs:
            if stg.is_main():
                main_stg = stg
        assert main_stg

        self.current_state_sig = fsm.state_var
        self.emit('{} <= {};'.format(self.current_state_sig.name, main_stg.init_state.name))
        self.set_indent(-2)
        self.emit('end else begin //if (rst)')
        self.set_indent(2)

        self.emit('case({})'.format(self.current_state_sig.name))

        for stg in sorted(fsm.stgs, key=lambda s: s.name):
            for i, state in enumerate(stg.states):
                self._process_State(state)

        self.emit('endcase')
        self.set_indent(-2)
        self.emit('end')  # end if (READY)
        self.set_indent(-2)
        self.emit('end')
        self.emit('')

    def _generate_include(self):
        pass
        # self.emit('`include "SinglePortRam.v"')

    def _generate_module(self):
        self._generate_module_header()
        self.set_indent(2)
        self._generate_localparams()
        self._generate_decls()
        self._generate_sub_module_instances()
        self._generate_edge_detector()
        self._generate_net_monitor()
        self.set_indent(-2)

    def _generate_module_header(self):
        self.emit('module {}'.format(self.hdlmodule.qualified_name))

        self.set_indent(2)
        self.emit('(')
        self.set_indent(2)

        self._generate_io_port()
        self.set_indent(-2)
        self.emit(');')
        self.set_indent(-2)
        self.emit('')

    def _generate_io_port(self):
        ports = []
        if self.hdlmodule.scope.is_module() or self.hdlmodule.scope.is_function_module():
            ports.append('input wire clk')
            ports.append('input wire rst')
        for interface in self.hdlmodule.interfaces.values():
            ports.extend(self._get_io_names_from(interface))
        self.emit((',\n' + self.tab()).join(ports))

    def _generate_signal(self, sig):
        name = self._safe_name(sig)
        if sig.width == 1:
            return name
        else:
            sign = 'signed' if sig.is_int() else ''
            return '{:<6} [{}:0] {}'.format(sign, sig.width - 1, name)

    def _generate_localparams(self):
        constants = self.hdlmodule.constants + self.hdlmodule.state_constants
        if not constants:
            return
        self.emit('//localparams')
        for name, val in constants:
            self.emit('localparam {0} = {1};'.format(name, val))
        self.emit('')

    def _generate_net_monitor(self):
        if env.hdl_debug_mode and not self.hdlmodule.scope.is_testbench():
            self.emit('always @(posedge clk) begin')
            self.emit('if (rst==0 && {}!={}) begin'.format(self.current_state_sig.name, 0))
            for tag, nets in self.hdlmodule.get_net_decls(with_array=False):
                for net in nets:
                    if net.sig.is_onehot():
                        self.emit(
                            '$display("%8d:WIRE  :{}      {} = 0b%b", $time, {});'.
                            format(self.hdlmodule.name, net.sig, net.sig))
                    else:
                        self.emit(
                            '$display("%8d:WIRE  :{}      {} = 0x%2h (%1d)", $time, {}, {});'.
                            format(self.hdlmodule.name, net.sig, net.sig, net.sig))
            self.emit('end')
            self.emit('end')
            self.emit('')

        self.emit('')

    def _generate_decls(self):
        for tag, decls in sorted(self.hdlmodule.decls.items(), key=lambda t: str(t)):
            decls = [decl for decl in decls if isinstance(decl, AHDL_SIGNAL_DECL)]
            if decls:
                self.emit('//signals: {}'.format(tag))
                for decl in sorted(decls, key=lambda d: str(d)):
                    self.visit(decl)
        for tag, decls in sorted(self.hdlmodule.decls.items()):
            decls = [decl for decl in decls if not isinstance(decl, AHDL_SIGNAL_DECL)]
            if decls:
                self.emit('//combinations: {}'.format(tag))
                for decl in sorted(decls, key=lambda d: str(d)):
                    self.visit(decl)

    def _get_io_names_from(self, interface):
        in_names = []
        out_names = []
        for port in interface.regs():
            if port.dir == 'in':
                assert False
            else:
                io_name = self._to_io_name(port.width, 'reg', 'output', port.signed,
                                           interface.port_name(port))
                out_names.append(io_name)
        for port in interface.nets():
            if port.dir == 'in':
                io_name = self._to_io_name(port.width, 'wire', 'input', port.signed,
                                           interface.port_name(port))
                in_names.append(io_name)
            else:
                io_name = self._to_io_name(port.width, 'wire', 'output', port.signed,
                                           interface.port_name(port))
                out_names.append(io_name)
        return in_names + out_names

    def _to_io_name(self, width, typ, io, signed, port_name):
        if is_verilog_keyword(port_name):
            port_name = port_name + '_'
        if width == 1:
            ioname = '{} {} {}'.format(io, typ, port_name)
        else:
            if signed:
                ioname = '{} {} signed [{}:0] {}'.format(io,
                                                         typ, width - 1,
                                                         port_name)
            else:
                ioname = '{} {} [{}:0] {}'.format(io,
                                                  typ,
                                                  width - 1,
                                                  port_name)
        return ioname

    def _to_sub_module_connect(self, instance_name, inf, acc, port):
        port_name = inf.port_name(port)
        if is_verilog_keyword(port_name):
            port_name = port_name + '_'
        accessor_name = acc.port_name(port)
        connection = '.{}({})'.format(port_name, accessor_name)
        return connection

    def _generate_sub_module_instances(self):
        if not self.hdlmodule.sub_modules:
            return
        self.emit('//sub modules')
        for name, sub_module, connections, param_map in sorted(self.hdlmodule.sub_modules.values(),
                                                         key=lambda n: str(n)):
            ports = []
            ports.append('.clk(clk)')
            ports.append('.rst(rst)')
            conns = connections['']
            for inf, acc in sorted(conns, key=lambda c: str(c)):
                for p in inf.ports:
                    ports.append(self._to_sub_module_connect(name, inf, acc, p))
            conns = connections['ret']
            for inf, acc in sorted(conns, key=lambda c: str(c)):
                for p in inf.ports:
                    ports.append(self._to_sub_module_connect(name, inf, acc, p))
            self.emit('//{} instance'.format(name))
            #for port, signal in port_map.items():
            #    ports.append('.{}({})'.format(port, signal))
            if param_map:
                params = []
                for param_name, value in param_map.items():
                    params.append('.{}({})'.format(param_name, value))

                self.emit('{}#('.format(sub_module.qualified_name))
                self.set_indent(2)
                self.emit('{}'.format((',\n' + self.tab()).join(params)))
                self.emit(')')
                self.emit('{}('.format(name))
                self.set_indent(2)
                self.emit('{}'.format((',\n' + self.tab()).join(ports)))
                self.set_indent(-2)
                self.emit(');')
                self.set_indent(-2)
            else:
                self.emit('{} {}('.format(sub_module.qualified_name, name))
                self.set_indent(2)
                self.emit('{}'.format((',\n' + self.tab()).join(ports)))
                self.set_indent(-2)
                self.emit(');')
        self.emit('')

    def _generate_edge_detector(self):
        if not self.hdlmodule.edge_detectors:
            return
        regs = set([sig for sig, _, _ in self.hdlmodule.edge_detectors])
        self.emit('//edge detectors')
        for sig in regs:
            delayed_name = '{}_d'.format(sig.name)
            self.emit('reg {};'.format(delayed_name))
            self.emit('always @(posedge clk) {} <= {};'.format(delayed_name, sig.name))
            #self.set_indent(2)
            #self.emit()
            #self.set_indent(-2)
            #self.emit('end')
            #self.emit('')

        detect_var_names = set()
        for sig, old, new in self.hdlmodule.edge_detectors:
            delayed_name = '{}_d'.format(sig.name)
            detect_var_name = 'is_{}_change_{}_to_{}'.format(sig.name, old, new)
            if detect_var_name in detect_var_names:
                continue
            detect_var_names.add(detect_var_name)
            self.emit('wire {};'.format(detect_var_name))
            self.emit('assign {} = ({}=={} && {}=={});'.
                      format(detect_var_name,
                             delayed_name,
                             old,
                             sig.name,
                             new))

    def _process_State(self, state):
        self.current_state = state
        code = '{0}: begin'.format(state.name)
        self.emit(code)
        self.set_indent(2)
        if env.hdl_debug_mode:
            self.emit('$display("%8d:STATE:{}  {}", $time);'.
                      format(self.hdlmodule.name,
                             state.name))
        # this is workaround
        if isinstance(state, PipelineState):
            for stage in state.stages:
                self.emit('/*** {} ***/'.format(stage.name))
                for code in stage.codes:
                    self.visit(code)
                if stage.enable:
                    self.visit(stage.enable)
                self.emit('')
        elif isinstance(state, State):
            for code in state.codes:
                self.visit(code)

        self.set_indent(-2)
        self.emit('end')

    def visit_AHDL_CONST(self, ahdl):
        if ahdl.value is None:
            return "'bx"
        elif isinstance(ahdl.value, bool):
            return str(int(ahdl.value))
        elif isinstance(ahdl.value, str):
            s = repr(ahdl.value)
            return '"' + s[1:-1] + '"'
        return str(ahdl.value)

    def _safe_name(self, sig):
        if sig.is_reserved():
            return sig.name
        if is_verilog_keyword(sig.name):
            return sig.name + '_'
        return sig.name

    def visit_AHDL_VAR(self, ahdl):
        return self._safe_name(ahdl.sig)

    def visit_AHDL_MEMVAR(self, ahdl):
        return self._safe_name(ahdl.sig)

    def visit_AHDL_SUBSCRIPT(self, ahdl):
        return '{}[{}]'.format(self.visit(ahdl.memvar), self.visit(ahdl.offset))

    def visit_AHDL_SYMBOL(self, ahdl):
        if is_verilog_keyword(ahdl.name):
            return ahdl.name + '_'
        return ahdl.name

    def visit_AHDL_CONCAT(self, ahdl):
        if ahdl.op:
            code = PYTHON_OP_2_HDL_OP_MAP[ahdl.op].join([str(v) for v in ahdl.varlist])
        else:
            code = '{'
            code += ', '.join([self.visit(var) for var in ahdl.varlist])
            code += '}'
        return code

    def visit_AHDL_OP(self, ahdl):
        if len(ahdl.args) > 1:
            op = ' ' + pyop2verilogop(ahdl.op) + ' '
            return '({})'.format(op.join([self.visit(a) for a in ahdl.args]))
        elif ahdl.is_unop():
            exp = self.visit(ahdl.args[0])
            return '{}{}'.format(pyop2verilogop(ahdl.op), exp)
        else:
            exp = self.visit(ahdl.args[0])
            return '{}'.format(exp)

    def visit_AHDL_SLICE(self, ahdl):
        v = self.visit(ahdl.var)
        hi = self.visit(ahdl.hi)
        lo = self.visit(ahdl.lo)
        return '{}[{}:{}]'.format(v, hi, lo)

    def visit_AHDL_NOP(self, ahdl):
        if isinstance(ahdl.info, AHDL):
            self.emit('/*')
            self.visit(ahdl.info)
            self.emit('*/')
        else:
            self.emit('/*' + str(ahdl.info) + '*/')

    def visit_AHDL_INLINE(self, ahdl):
        self.emit(ahdl.code)

    def visit_AHDL_MOVE(self, ahdl):
        if ahdl.dst.is_a(AHDL_VAR) and ahdl.dst.sig.is_net():
            self.hdlmodule.add_static_assignment(AHDL_ASSIGN(ahdl.dst, ahdl.src))
            self.emit('/* {} <= {}; */'.format(self.visit(ahdl.dst), self.visit(ahdl.src)))
        elif ahdl.dst.is_a(AHDL_MEMVAR) and ahdl.src.is_a(AHDL_MEMVAR):
            assert False
        else:
            src = self.visit(ahdl.src)
            dst = self.visit(ahdl.dst)
            if env.hdl_debug_mode:
                self.emit('$display("%8d:REG  :{}      {} <= 0x%2h (%1d)", $time, {}, {});'.
                          format(self.hdlmodule.name, dst, src, src))
            self.emit('{} <= {};'.format(dst, src))

    def visit_AHDL_MEM(self, ahdl):
        name = ahdl.name.hdl_name()
        offset = self.visit(ahdl.offset)
        return '{}[{}]'.format(name, offset)

    def visit_AHDL_IF(self, ahdl):
        blocks = 0
        for i, (cond, codes) in enumerate(zip(ahdl.conds, ahdl.codes_list)):
            if not codes:
                continue
            blocks += 1
            if cond and not (cond.is_a(AHDL_CONST) and cond.value == 1) or i == 0:
                cond = self.visit(cond)
                if cond[0] != '(':
                    cond = '(' + cond + ')'
                if i == 0:
                    self.emit('if {} begin'.format(cond))
                else:
                    self.emit('end else if {} begin'.format(cond))
                self.set_indent(2)
                for code in codes:
                    self.visit(code)
                self.set_indent(-2)
            else:
                self.emit('end else begin')
                self.set_indent(2)
                for code in ahdl.codes_list[-1]:
                    self.visit(code)
                self.set_indent(-2)
        if blocks:
            self.emit('end')

    def visit_AHDL_IF_EXP(self, ahdl):
        cond = self.visit(ahdl.cond)
        lexp = self.visit(ahdl.lexp)
        rexp = self.visit(ahdl.rexp)
        return '{} ? {} : {}'.format(cond, lexp, rexp)

    def visit_AHDL_FUNCALL(self, ahdl):
        return '{}({})'.format(self.visit(ahdl.name), ', '.join([self.visit(arg) for arg in ahdl.args]))

    def visit_AHDL_PROCCALL(self, ahdl):
        args = []
        for arg in ahdl.args:
            a = self.visit(arg)
            args.append(a)

        if ahdl.name == '!hdl_print':
            fmts = ['%s' if a[0] == '"' else '%1d' for a in args]
            self.emit('$display("{}", {});'.format(' '.join(fmts), ', '.join(args)))
        elif ahdl.name == '!hdl_verilog_display':
            self.emit('$display({});'.format(', '.join(args)))
        elif ahdl.name == '!hdl_verilog_write':
            self.emit('$write({});'.format(', '.join(args)))
        elif ahdl.name == '!hdl_assert':
            #expand condtion expression for the assert message
            exp = ahdl.args[0]
            exp_str = args[0]
            if exp.is_a(AHDL_VAR) and exp.sig.is_condition():
                for tag, assign in self.hdlmodule.get_static_assignment():
                    if assign.dst.is_a(AHDL_VAR) and assign.dst.sig == exp.sig:
                        remove_assign = (tag, assign)
                        self.hdlmodule.remove_internal_net(exp.sig)
                        exp_str = self.visit(assign.src)
                        self.hdlmodule.remove_decl(*remove_assign)
                        break
            exp_str = exp_str.replace('==', '===').replace('!=', '!==')
            code = 'if (!{}) begin'.format(exp_str)
            self.emit(code)
            code = '  $display("ASSERTION FAILED {}"); $finish;'.format(exp_str)
            self.emit(code)
            self.emit('end')
        else:
            self.emit('{}({});'.format(ahdl.name, ', '.join(args)))

    def visit_AHDL_SIGNAL_DECL(self, ahdl):
        nettype = 'reg' if ahdl.sig.is_reg() else 'wire'
        self.emit('{} {};'.format(nettype, self._generate_signal(ahdl.sig)))

    def visit_AHDL_SIGNAL_ARRAY_DECL(self, ahdl):
        nettype = 'reg' if ahdl.sig.is_regarray() else 'wire'
        name = self._safe_name(ahdl.sig)
        if ahdl.sig.width == 1:
            self.emit('{} {}[0:{}];'.format(nettype,
                                            name,
                                            ahdl.size - 1))
        else:
            sign = 'signed' if ahdl.sig.is_int() else ''
            self.emit('{} {:<6} [{}:0] {} [0:{}];'.format(nettype,
                                                          sign,
                                                          ahdl.sig.width - 1,
                                                          name,
                                                          ahdl.size - 1))

    def visit_AHDL_ASSIGN(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit('assign {} = {};'.format(dst, src))

    def visit_AHDL_EVENT_TASK(self, ahdl):
        evs = []
        for v, e in ahdl.events:
            var = self.visit(v)
            if e == 'rising':
                ev = 'posedge '
            elif e == 'falling':
                ev = 'negedge '
            else:
                ev = ''
            evs.append('{}{}'.format(ev, var))
        events = ', '.join(evs)
        self.emit('always @({}) begin'.format(events))
        self.set_indent(2)
        self.visit(ahdl.stm)
        self.set_indent(-2)
        self.emit('end')

    def visit_AHDL_CONNECT(self, ahdl):
        src = self.visit(ahdl.src)
        dst = self.visit(ahdl.dst)
        self.emit('{} = {};'.format(dst, src))

    def visit_MEM_SWITCH(self, ahdl):
        prefix = ahdl.args[0]
        dst_node = ahdl.args[1]
        src_node = ahdl.args[2]
        n2o = dst_node.pred_branch()
        src_root = self.mrg.find_nearest_single_source(src_node)
        assert isinstance(n2o, N2OneMemNode)
        for p in n2o.preds:
            assert isinstance(p, One2NMemNode)
        preds = []
        roots = []
        for p in n2o.preds:
            if (self.hdlmodule.scope is p.scope or
                    p.scope.is_worker() and self.hdlmodule.scope.is_subclassof(p.scope.parent)):
                preds.append(p)
                pred_root = self.mrg.find_nearest_single_source(p)
                roots.append(pred_root)
        width = len(preds)
        if width < 2:
            return
        if prefix:
            cs_name = '{}_{}_cs'.format(prefix, dst_node.name())
        else:
            cs_name = '{}_cs'.format(dst_node.name())
        cs = self.hdlmodule.signal(cs_name)
        if not cs:
            cs = self.hdlmodule.gen_sig(cs_name, width, {'reg'})
            self.hdlmodule.add_internal_reg(cs)
        assert cs.is_reg() and not cs.is_net()
        if isinstance(src_node.preds[0], One2NMemNode):
            assert src_root in roots
            idx = roots.index(src_root)
            one_hot_mask = format(1 << idx, '#0{}b'.format(width + 2))[2:]
            self.visit(AHDL_MOVE(AHDL_VAR(cs, Ctx.STORE),
                                 AHDL_SYMBOL('\'b' + one_hot_mask)))
        elif src_node.is_alias():
            srccs_name = src_node.name()
            if prefix:
                srccs = self.hdlmodule.gen_sig('{}_{}_cs'.format(prefix, srccs_name), width, {'reg'})
            else:
                srccs_name = '{}_cs'.format(srccs_name)
                srccs = self.hdlmodule.signal(srccs_name)
                assert srccs
                #srccs = self.hdlmodule.gen_sig('{}_cs'.format(srccs_name), width)
            self.visit(AHDL_MOVE(AHDL_VAR(cs, Ctx.STORE),
                                 AHDL_VAR(srccs, Ctx.LOAD)))

    def visit_MEM_MUX(self, ahdl):
        prefix = ahdl.args[0]
        dst = ahdl.args[1]
        srcs = ahdl.args[2]
        conds = ahdl.args[3]
        n2o = dst.memnode.pred_branch()
        assert isinstance(n2o, N2OneMemNode)
        preds = []
        roots = []
        for p in n2o.preds:
            if (self.hdlmodule.scope is p.scope or
                    p.scope.is_worker() and self.hdlmodule.scope.is_subclassof(p.scope.parent)):
                preds.append(p)
                pred_root = self.mrg.find_nearest_single_source(p)
                roots.append(pred_root)
        width = len(preds)
        if width < 2:
            return
        if prefix:
            cs_name = '{}_{}_cs'.format(prefix, dst.memnode.name())
        else:
            cs_name = '{}_cs'.format(dst.memnode.name())
        cs = self.hdlmodule.signal(cs_name)
        if not cs:
            cs = self.hdlmodule.gen_sig(cs_name, width, {'net'})
            self.hdlmodule.add_internal_net(cs)
        assert cs.is_net() and not cs.is_reg()
        args = []
        for src in srcs:
            if isinstance(src.memnode.preds[0], One2NMemNode):
                assert isinstance(src.memnode.preds[0], One2NMemNode)
                src_root = self.mrg.find_nearest_single_source(src.memnode)
                assert src_root in roots
                idx = roots.index(src_root)
                one_hot_mask = format(1 << idx, '#0{}b'.format(width + 2))[2:]
                args.append(AHDL_SYMBOL('\'b' + one_hot_mask))
            elif src.memnode.is_alias():
                srccs_name = src.memnode.name()
                if prefix:
                    srccs = self.hdlmodule.gen_sig('{}_{}_cs'.format(prefix, srccs_name), width)
                else:
                    srccs = self.hdlmodule.gen_sig('{}_cs'.format(srccs_name), width)
                args.append(AHDL_MEMVAR(srccs, src.memnode, Ctx.LOAD))

        arg_p = list(zip(args, conds))
        rexp, cond = arg_p[-1]
        if cond.is_a(AHDL_CONST) and cond.value:
            pass
        else:
            rexp = AHDL_IF_EXP(cond, rexp,
                               AHDL_SYMBOL("{}'b0".format(width)))
        for arg, p in arg_p[-2::-1]:
            lexp = arg
            if_exp = AHDL_IF_EXP(p, lexp, rexp)
            rexp = if_exp
        self.visit(AHDL_MOVE(AHDL_VAR(cs, Ctx.STORE),
                             if_exp))

    def visit_AHDL_META(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_WAIT_EDGE(self, ahdl):
        old, new = ahdl.args[0], ahdl.args[1]
        detect_vars = []
        for var in ahdl.args[2:]:
            detect_var_name = 'is_{}_change_{}_to_{}'.format(var.sig.name,
                                                             self.visit(old),
                                                             self.visit(new))
            detect_vars.append(AHDL_SYMBOL(detect_var_name))
        if len(detect_vars) > 1:
            conds = [AHDL_OP('And', *detect_vars)]
        else:
            conds = [detect_vars[0]]
        if ahdl.codes:
            codes = ahdl.codes[:]
        else:
            codes = []
        if ahdl.transition:
            codes.append(ahdl.transition)
        ahdl_if = AHDL_IF(conds, [codes])
        self.visit(ahdl_if)

    def visit_WAIT_VALUE(self, ahdl):
        eqs = [AHDL_OP('Eq', port, value) for value, port in ahdl.args]
        cond = functools.reduce(lambda a, b: AHDL_OP('And', a, b), eqs)
        conds = [cond]
        if ahdl.codes:
            codes = ahdl.codes[:]
        else:
            codes = []
        if ahdl.transition:
            codes.append(ahdl.transition)
        ahdl_if = AHDL_IF(conds, [codes])
        self.visit(ahdl_if)

    def visit_AHDL_META_WAIT(self, ahdl):
        method = 'visit_' + ahdl.metaid
        visitor = getattr(self, method, None)
        return visitor(ahdl)

    def visit_AHDL_FUNCTION(self, ahdl):
        self.emit('function [{}:0] {} ('.format(ahdl.output.sig.width - 1,
                                                self.visit(ahdl.output)))
        self.set_indent(2)
        last_idx = len(ahdl.inputs) - 1
        for idx, input in enumerate(ahdl.inputs):
            if idx == last_idx:
                self.emit('input [{}:0] {}'.format(input.sig.width - 1, self.visit(input)))
            else:
                self.emit('input [{}:0] {},'.format(input.sig.width - 1, self.visit(input)))
        #self.emit(',\n'.join([str(i) for i in ahdl.inputs]))
        self.set_indent(-2)
        self.emit(');')
        self.emit('begin')
        self.set_indent(2)
        for stm in ahdl.stms:
            self.visit(stm)
        self.set_indent(-2)
        self.emit('end')
        self.emit('endfunction')

    def visit_AHDL_CASE(self, ahdl):
        self.emit('case ({})'.format(self.visit(ahdl.sel)))
        self.set_indent(2)
        for item in ahdl.items:
            self.visit(item)
        self.set_indent(-2)
        self.emit('endcase')

    def visit_AHDL_CASE_ITEM(self, ahdl):
        self.emit("{}:".format(ahdl.val), newline=False)
        self.visit(ahdl.stm)

    def visit_AHDL_MUX__unused(self, ahdl):
        self.emit('function [{}:0] {} ('.format(ahdl.output.width - 1, ahdl.name))
        self.set_indent(2)
        self.emit('input [{}:0] {},'.format(ahdl.selector.sig.width - 1, self.visit(ahdl.selector)))

        last_idx = len(ahdl.inputs) - 1
        for idx, input in enumerate(ahdl.inputs):
            if idx == last_idx:
                self.emit('input [{}:0] {}'.format(input.width - 1, input.name))
            else:
                self.emit('input [{}:0] {},'.format(input.width - 1, input.name))

        self.set_indent(-2)
        self.emit(');')
        self.emit('begin')
        self.set_indent(2)

        self.emit('case (1\'b1)')
        self.set_indent(2)
        for i, input in enumerate(ahdl.inputs):
            self.emit("{}[{}]: {} = {};".format(ahdl.selector.sig.name,
                                                i,
                                                ahdl.name,
                                                input.name))
        self.set_indent(-2)
        self.emit('endcase')
        self.set_indent(-2)
        self.emit('end')
        self.emit('endfunction')

        params = self.visit(ahdl.selector) + ', '
        params += ', '.join([input.name for input in ahdl.inputs])
        self.emit('assign {} = {}({});'.format(ahdl.output.name, ahdl.name, params))

    def visit_AHDL_MUX(self, ahdl):
        if len(ahdl.inputs) > 1:
            if isinstance(ahdl.output, Signal):
                output_name = ahdl.output.name
            elif isinstance(ahdl.output, int):
                output_name = ahdl.output
            head = 'assign {} = '.format(output_name)
            terms = [head]
            for i, input in enumerate(ahdl.inputs):
                if i == 0:
                    indent = ''
                else:
                    indent = (len(head) + self.indent) * ' '
                if i < len(ahdl.inputs) - 1:
                    term = indent + '1\'b1 == {}[{}] ? {}:\n'.format(ahdl.selector.sig.name,
                                                                     i,
                                                                     input.name)
                else:
                    if ahdl.defval is None:
                        defval = output_name
                    else:
                        defval = ahdl.defval
                    term = indent + '1\'b1 == {}[{}] ? {}:{};'.format(ahdl.selector.sig.name,
                                                                      i,
                                                                      input.name,
                                                                      defval)
                terms.append(term)
            self.emit(''.join(terms))
        else:
            self.emit('assign {} = {};'.format(ahdl.output.name, ahdl.inputs[0].name))

    def visit_AHDL_DEMUX(self, ahdl):
        if len(ahdl.outputs) > 1:
            if isinstance(ahdl.input, Signal):
                input_name = ahdl.input.name
            elif isinstance(ahdl.input, int):
                input_name = ahdl.input
            for i, output in enumerate(ahdl.outputs):
                if ahdl.defval is None:
                    defval = output.name
                else:
                    defval = ahdl.defval
                self.emit('assign {} = 1\'b1 == {}[{}] ? {}:{};'
                          .format(output.name,
                                  ahdl.selector.sig.name,
                                  i,
                                  input_name,
                                  defval))
        else:
            self.emit('assign {} = {};'.format(ahdl.outputs[0].name, ahdl.input.name))

    def visit_AHDL_TRANSITION(self, ahdl):
        state_var = AHDL_SYMBOL(self.current_state_sig.name)
        state = AHDL_SYMBOL(ahdl.target.name)
        self.visit(AHDL_MOVE(state_var, state))

    def visit_AHDL_TRANSITION_IF(self, ahdl):
        self.visit_AHDL_IF(ahdl)

    def visit_AHDL_PIPELINE_GUARD(self, ahdl):
        self.visit_AHDL_IF(ahdl)
