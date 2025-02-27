from dataclasses import dataclass, field
from .simpletype import SimpleType


@dataclass(frozen=True)
class StrType(SimpleType):
    name: str = field(init=False, default='str')
