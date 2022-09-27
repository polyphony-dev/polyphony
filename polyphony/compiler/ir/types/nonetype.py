from .simpletype import SimpleType
from ...common.env import env


class NoneType(SimpleType):
    def __init__(self, explicit):
        super().__init__('none', env.scopes['__builtin__.none'], explicit=explicit)
