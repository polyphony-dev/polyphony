from .simpletype import SimpleType
from ...common.env import env


class StrType(SimpleType):
    def __init__(self, explicit):
        super().__init__('str', '__builtin__.str', explicit=explicit)
