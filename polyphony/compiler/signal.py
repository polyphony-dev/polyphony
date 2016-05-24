class Signal:
    def __init__(self, name, width, attributes = None):
        self.name = name
        self.width = width
        if isinstance(attributes, list):
            self.attributes = set(attributes)
        elif attributes:
            assert isinstance(attributes, set)
            self.attributes = attributes
        else:
            self.attributes = set()

    def add_attribute(self, attr):
        if isinstance(attr, set):
            self.attributes = self.attributes.union(attr)
        elif isinstance(attr, list):
            self.attributes = self.attributes.union(set(attr))
        else:
            self.attributes.add(attr)

    def is_int(self):
        return 'int' in self.attributes

    def is_condition(self):
        return 'cond' in self.attributes

    def is_field(self):
        return 'field' in self.attributes

    def is_input(self):
        return 'in' in self.attributes

    def is_output(self):
        return 'out' in self.attributes

    def is_wire(self):
        return 'wire' in self.attributes

    def is_reg(self):
        return 'reg' in self.attributes

    def is_ctrl(self):
        return 'ctrl' in self.attributes

    def is_memif(self):
        return 'memif' in self.attributes

    def is_statevar(self):
        return 'statevar' in self.attributes

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name
