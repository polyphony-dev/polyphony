from .common import Tagged


class Signal(Tagged):
    TAGS = {
        'reg', 'net', 'int', 'condition',
        'input', 'output',
        'extport',
        'statevar',
        'field', 'ctrl', 'memif', 'onehot',
    }

    def __init__(self, name, width, tags):
        if tags is None:
            tags = set()
        super().__init__(tags, Signal.TAGS)
        self.name = name
        self.width = width

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return "Signal(\'{}\', {}, {})".format(self.name, self.width, self.tags)
