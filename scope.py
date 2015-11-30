from collections import defaultdict, namedtuple
from env import env
from symbol import Symbol
from logging import getLogger
logger = getLogger(__name__)

FunctionParam = namedtuple('FunctionParam', ('sym', 'copy', 'defval'))

class Scope:
    @classmethod
    def create(cls, parent, name = None, attributes = []):
        if name is None:
            name = "unnamed_scope" + str(len(env.scopes))
        s = Scope(parent, name, attributes)
        assert s.name not in env.scopes
        env.append_scope(s)
        return s

    def __init__(self, parent, name, attributes):
        self.name = name
        self.orig_name = name
        self.parent = parent
        if parent:
            self.name = parent.name + "." + name
            parent.append_child(self)

        self.funcnames = []
        self.attributes = attributes
        self.symbols = {}
        self.params = []
        self.return_type = None
        self.blocks = []
        self.blk_grp_stack = []
        self.children = []
        self.usedef = None
        self.loop_nest_tree = None
        self.loop_infos = {}
        self.calls = defaultdict(set)
        self.blk_grp_instances = []
        self.meminfos = {}
        self.stgs = []
        self.mem_links = defaultdict(dict)

    def __str__(self):
        s = '\n================================\n'
        attributes = ", ".join([att for att in self.attributes])
        if self.parent:
            s += "Scope: {}, parent={} ({})\n".format(self.orig_name, self.parent.name, attributes)
        else:
            s += "Scope: {} ({})\n".format(self.orig_name, attributes)

        s += ", ".join([str(sym) for sym in self.symbols])
        s += "\n"
        s += '================================\n'
        s += 'Parameters\n'
        for p, copy, val in self.params:
            s += '{} = {}\n'.format(p, val)
        s += "\n"
        s += '================================\n'
        for blk in self.blocks:
            s += str(blk)

        s += '================================\n'
        s += 'Block Group\n'
        for bl in self.blk_grp_instances:
            s += str(bl)+'\n'

        s += '================================\n'
        s += 'MemoryInfo\n'
        for meminfo in self.meminfos.values():
            s += str(meminfo)+'\n'
        s += '================================\n'    
        return s

    def add_funcname(self, name):
        self.funcnames.append(name)

    def is_funcname(self, name):
        return name in self.funcnames

    def find_scope_having_funcname(self, name):
        if name in self.funcnames:
            return self
        elif self.parent:
            return self.parent.find_scope_having_funcname(name)
        else:
            return None

    def find_func_scope(self, func_name):
        if self.orig_name == func_name:
            return self
        for child in self.children:
            if child.orig_name == func_name:
                return child
        if self.parent:
            return self.parent.find_func_scope(func_name)
        else:
            return None

    def add_sym(self, name):
        if name in self.symbols:
            raise RuntimeError("symbol '{}' is already registered ".format(name))
        sym = Symbol.new(name, self)
        self.symbols[name] = sym
        return sym

    def find_sym(self, name):
        if name in self.symbols:
            return self.symbols[name]
        elif self.parent:
            found = self.parent.find_sym(name)
            #if found:
            #    raise RuntimeError("'{}' is in the outer scope. Polyphony supports local name scope only.".format(name))
            return found
        return None

    def has_sym(self, name):
        return name in self.symbols

    def gen_sym(self, name):
        sym = self.find_sym(name)
        if not sym:
            sym = self.add_sym(name)
        return sym

    def inherit_sym(self, orig_sym, new_name):
        new_sym = orig_sym.scope.gen_sym(new_name)
        new_sym.typ = orig_sym.typ
        new_sym.ancestor = orig_sym
        return new_sym

    def qualified_name(self):
        n = ""
        if self.parent is not None:
            n = self.parent.qualified_name() + "_"
        n += self.name
        return n

    def remove_block(self, blk):
        self.blocks.remove(blk)
        blk.group.remove(blk)
        if not blk.group.blocks:
            self.blk_grp_instances.remove(blk.group)

    def append_block(self, blk):
        blk.set_scope(self)
        self.blocks.append(blk)
        self.blk_grp_stack[-1].append(blk)

    def append_child(self, child_scope):
        self.children.append(child_scope)

    def add_param(self, sym, copy, defval):
        self.params.append(FunctionParam(sym, copy, defval))

    def has_param(self, sym):
        name = sym.name.split('#')[0]
        for p, _, _ in self.params:
            if p.name == name:
                return True
        return False

    def append_call(self, func_sym, inst_name):
        self.calls[func_sym].add(inst_name)

    def dfgs(self, bottom_up=False):
        infos = sorted(self.loop_infos.values(), key=lambda l:l.name, reverse=bottom_up)
        return [info.dfg for info in infos]

    def begin_block_group(self, tag):
        grp = self._create_block_group(tag)
        #if self.blk_grp_stack:
        #    grp.parent = self.blk_grp_stack[-1]
        self.blk_grp_stack.append(grp)

    def end_block_group(self):
        self.blk_grp_stack.pop()

    def _create_block_group(self, tag):
        name = 'grp_' + tag + str(len(self.blk_grp_instances))
        bl = BlockGroup(name)
        self.blk_grp_instances.append(bl)
        return bl

    def create_loop_info(self, head):
        name = 'L' + str(len(self.loop_infos))
        li = LoopBlockInfo(head, name)
        self.loop_infos[head] = li
        return li

    def find_loop_head(self, block):
        for head, bodies in self.loop_infos.items():
            if head is block:
                return head
            for b in bodies:
                if block is b:
                    return head
        return None

    def is_testbench(self):
        return 'testbench' in self.attributes

    def is_main(self):
        return 'top' in self.attributes

    def find_stg(self, name):
        assert self.stgs
        for stg in self.stgs:
            if stg.name == name:
                return stg
        return None

    def get_main_stg(self):
        assert self.stgs
        for stg in self.stgs:
            if stg.is_main():
                return stg
        return None

    def add_mem_link(self, mem, callee_func, callee_inst, param_info):
        callee_scope_name = self.name + '_' + callee_func
        self.mem_links[mem][callee_inst] = (callee_scope_name, callee_inst, param_info)

    def append_loop_counter(self, loop):
        self.loop_counter.append(loop)


class BlockGroup:
    def __init__(self, name):
        self.name = name
        self.blocks = []
        self.parent = None

    def __str__(self):
        if self.parent:
            return '{} ({}) parent:{}'.format(self.name, ', '.join([blk.name for blk in self.blocks]), self.parent.name)
        else:
            return '{} ({})'.format(self.name, ', '.join([blk.name for blk in self.blocks]))
    def append(self, blk):
        self.blocks.append(blk)
        blk.group = self

    def remove(self, blk):
        self.blocks.remove(blk)

class LoopBlockInfo:
    def __init__(self, head, name):
        self.head = head
        self.bodies = set()
        self.breaks = []
        self.returns = []
        self.exit = None
        self.name = name
        self.defs = None
        self.uses = None

    def append_break(self, brk):
        self.breaks.append(brk)

    def append_return(self, blk):
        self.returns.append(blk)

    def append_bodies(self, bodies):
        assert isinstance(bodies, set)
        self.bodies = self.bodies.union(bodies)

MemLink = namedtuple('MemLink', ('inst_name', 'meminfo'))

class MemInfo:
    ''' the infomation that this scope accessing '''
    def __init__(self, sym, length):
        self.sym = sym
        self.length = length
        self.width = 32 # TODO
        self.initstm = None
        self.rom = False
        self.shared = False
        self.ref_index = -1
        self.accessed_index = set()
        self.links = defaultdict(set)
        self.src_mem = None

    def __str__(self):
        return '{}[{}]:rom={}:shared={}:ref={}:initstm={}'.format(self.sym, self.length, self.rom, self.shared, self.ref_index, self.initstm)

    def __repr__(self):
        return self.__str__()

    def set_src(self, meminfo):
        assert self.src_mem is None or self.src_mem is meminfo
        self.src_mem = meminfo
        self._set_length(meminfo.length)

    def _set_length(self, len):
        '''Set a memory length recursively'''
        assert self.length == -1 or self.length == len
        self.length = len
        for links in self.links.values():
            for inst, linked_meminfo in links:
                linked_meminfo._set_length(len)
