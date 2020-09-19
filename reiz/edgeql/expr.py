from __future__ import annotations

from dataclasses import dataclass
from enum import auto

from reiz.db.schema import protected_name
from reiz.edgeql.base import EdgeQLExpression
from reiz.utilities import ReizEnum


@EdgeQLExpression.register
class EdgeQLLogicOperator(ReizEnum):
    IN = auto()
    OR = auto()
    AND = auto()

    def construct(self):
        return self.name


@EdgeQLExpression.register
class EdgeQLComparisonOperator(ReizEnum):
    EQUALS = "="
    CONTAINS = "in"
    NOT_EQUALS = "!="

    def construct(self):
        return self.value


@dataclass(unsafe_hash=True)
class EdgeQLContainer(EdgeQLExpression):

    items: List[EdgeQLObject]

    def construct(self):
        body = ", ".join(construct_seq(self.items))
        return with_parens(body, combo=self.parens)


@dataclass(unsafe_hash=True)
class EdgeQLTuple(EdgeQLContainer):
    PARENS = "()"


@dataclass(unsafe_hash=True)
class EdgeQLArray(EdgeQLContainer):
    PARENS = "[]"


@dataclass(unsafe_hash=True)
class EdgeQLSet(EdgeQLContainer):
    PARENS = "{}"


@dataclass(unsafe_hash=True)
class EdgeQLName(EdgeQLExpression):
    name: str

    def construct(self):
        return self.name


class EdgeQLSpecialName(EdgeQLName):
    def construct(self):
        return self.PREFIX + self.name


@dataclass(unsafe_hash=True)
class EdgeQLVariable(EdgeQLSpecialName):
    PREFIX = "$"


@dataclass(unsafe_hash=True)
class EdgeQLFilterKey(EdgeQLSpecialName):
    PREFIX = "."


@dataclass(unsafe_hash=True)
class EdgeQLCall(EdgeQLExpression):
    func: str
    args: List[EdgeQLObject]

    def construct(self):
        body = ", ".join(construct_seq(self.items))
        return self.func + with_parens(body, combo=self.parens)


@dataclass(unsafe_hash=True)
class EdgeQLCast(EdgeQLExpression):
    type: str
    value: EdgeQLObject

    def construct(self):
        return f"<{protected_name(self.type)}>{construct(self.value)}"
