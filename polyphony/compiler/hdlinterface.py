from collections import defaultdict, namedtuple

Port = namedtuple('Port', ('basename', 'width', 'dir'))

'''
module I/O port
  <interface prefix>_<param name>

sub module access port
  <instance name>_<interface prefix>_<param name>
'''

class Interface:
    ANY = -1
    def __init__(self, name, thru, is_public):
        self.name = name
        self.ports = []
        self.thru = thru
        self.is_public = is_public

    def __str__(self):
        ports = '{' + ', '.join(['<{}:{}:{}>'.format(p.basename, p.width, p.dir) for p in self.ports]) + '}'
        return self.name

    def __repr__(self):
        return self.__class__.__name__ + ':' + self.name

    def __lt__(self, other):
        return self.name < other.name

    def _flip_direction(self):
        def flip(d):
            return 'in' if d == 'out' else 'out'
        self.ports = [Port(p.basename, p.width, flip(p.dir)) for p in self.ports]

    def clone(self):
        pass

    def inports(self):
        for p in self.ports:
            if p.dir == 'in':
                yield p

    def outports(self):
        for p in self.ports:
            if p.dir == 'out':
                yield p

    def port_name(self, prefix, port):
        pfx = prefix+'_' if prefix else ''
        if self.name:
            if port.basename:
                return pfx + '{}_{}'.format(self.name, port.basename)
            else:
                return pfx + self.name
        else:
            assert port.basename
            return pfx + port.basename

class FunctionInterface(Interface):
    def __init__(self, name, thru = False, is_method = False):
        super().__init__(name, thru, is_public=True)
        self.is_method = is_method
        self.ports.append(Port('ready',  1, 'in'))
        self.ports.append(Port('accept', 1, 'in'))
        self.ports.append(Port('valid',  1, 'out'))

    def add_data_in(self, din_name, width):
        self.ports.append(Port(din_name, width, 'in'))

    def add_data_out(self, dout_name, width):
        self.ports.append(Port(dout_name, width, 'out'))

    def add_ram_in(self, ramif):
        #TODO
        pass

    def add_ram_out(self, ramif):
        #TODO
        pass

    def clone(self):
        inf = FunctionInterface(self.name, self.thru, self.is_method)
        inf.ports = list(self.ports)
        return inf

class RAMInterface(Interface):
    def __init__(self, name, data_width, addr_width, thru=False, is_public=False):
        super().__init__(name, thru=thru, is_public=is_public)
        self.thru = thru
        self.data_width = data_width
        self.addr_width = addr_width
        self.ports.append(Port('addr', addr_width, 'in'))
        self.ports.append(Port('d',    data_width, 'in'))
        self.ports.append(Port('we',   1,          'in'))
        self.ports.append(Port('q',    data_width, 'out'))
        self.ports.append(Port('len',  addr_width, 'out'))

    def clone(self):
        inf = RAMInterface(self.name, self.data_width, self.addr_width, self.thru, self.is_public)
        inf.ports = list(self.ports)
        return inf

class RAMAccessInterface(RAMInterface):
    def __init__(self, name, data_width, addr_width, flip=False, thru=False):
        super().__init__(name, data_width, addr_width, thru, is_public=True)
        self.ports.append(Port('req', 1, 'in'))
        if flip:
            self._flip_direction()
        
class RegArrayInterface(Interface):
    def __init__(self, name, data_width, length):
        super().__init__('', thru=True, is_public=True)
        self.data_width = data_width
        self.length = length
        for i in range(length):
            pname = '{}{}'.format(name, i)
            self.ports.append(Port(pname, data_width, 'in'))

    def clone(self):
        inf = RegArrayInterface(self.name, self.data_width, self.length)
        inf.ports = list(self.ports)
        return inf

class RegFieldInterface(Interface):
    def __init__(self, field_name, width):
        super().__init__('field_' + field_name, thru=False, is_public=True)
        self.field_name = field_name
        self.width = width
        self.ports.append(Port('in',    width, 'in'))
        self.ports.append(Port('ready',     1, 'in'))
        self.ports.append(Port('',      width, 'out'))
       
class RAMFieldInterface(RAMInterface):
    def __init__(self, field_name, data_width, addr_width, thru=False):
        super().__init__('field_' + field_name, data_width, addr_width, thru=thru, is_public=True)
        self.field_name = field_name
        
class InstanceInterface(Interface):
    def __init__(self, inf, inst_name, scope, is_public):
        super().__init__(inst_name + '_' + inf.name, thru=inf.thru, is_public=is_public)
        self.inf = inf
        self.inst_name = inst_name
        self.scope = scope
        self.ports = list(inf.ports)

    def __str__(self):
        return self.sym.name + '_' + self.inf.name


class Interconnect:
    def __init__(self, name, ins, outs, cs_name=''):
        self.name = name
        self.ins = ins
        self.outs = outs
        self.cs_name = cs_name

    def __str__(self):
        s = self.name+'\n'
        for i in self.ins:
            s += str(i)+'\n'
        for o in self.outs:
            s += str(o)+'\n'
        return s
