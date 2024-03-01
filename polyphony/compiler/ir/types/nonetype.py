from dataclasses import dataclass, field
from .simpletype import SimpleType


@dataclass(frozen=True)
class NoneType(SimpleType):
    name: str = field(init=False, default='none')
