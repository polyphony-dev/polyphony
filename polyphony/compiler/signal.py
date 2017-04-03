from .common import Tagged


class Signal(Tagged):
    TAGS = {
        'reg', 'net', 'int', 'condition',
        'regarray', 'netarray',
        'input', 'output',
        'extport',
        'valid_protocol', 'ready_valid_protocol',
        'statevar',
        'field', 'ctrl', 'memif', 'onehot',
        'single_port', 'seq_port', 'fifo_port',
        'initializable',
    }

    def __init__(self, name, width, tags):
        super().__init__(tags)
        self.name = name
        self.width = width
        self.init_value = 0

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return "Signal(\'{}\', {}, {})".format(self.name, self.width, self.tags)
