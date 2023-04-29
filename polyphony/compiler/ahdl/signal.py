from ..common.common import Tagged


class Signal(Tagged):
    TAGS = {
        'reserved',
        'reg', 'net', 'int', 'condition',
        'regarray', 'netarray', 'rom',
        'input', 'output', 'parameter', 'constant',
        'extport',
        'field', 'ctrl', 'onehot',
        'single_port', 'pipelined',
        'initializable',
        'induction',
        'pipeline_ctrl',
        'rewritable',
        'interface', 'submodule',
    }

    def __init__(self, hdlscope, name, width, tags, sym=None):
        super().__init__(tags)
        self.hdlscope = hdlscope
        self.name = name
        self.width = width  # width:int | (width:int, array_length:int)
        self.sym = sym
        self.init_value = 0

    def __str__(self):
        return '{}<{}>'.format(self.name, self.width)

    def __eq__(self, other):
        return self.name == other.name

    def __lt__(self, other):
        return self.name < other.name

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return "Signal(\'{}\', {}, {})".format(self.name, self.width, self.tags)

    def prefix(self):
        return self.name[:-len(self.sym.hdl_name())]
