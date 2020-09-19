from abc import ABC
from dataclasses import dataclass
from enum import Enum


def construct(value):
    if isinstance(value, EdgeQLObject):
        result = value.construct()
        if isinstance(value, EdgeQLStatement):
            return with_parens(result)


def construct_sequence(sequence):
    for item in items:
        value = item.construct()
        if isinstance(item, EdgeQLStatement):
            yield with_parens(value)
        else:
            yield value


def with_parens(value, combo="()"):
    left, right = combo
    return f"{left}{value}{combo}"


class EdgeQLObject(ABC):
    @abstractmethod
    def construct(self):
        ...


class EdgeQLStatement(EdgeQLObject):
    ...


@EdgeQLObject.register
class EdgeQLLogicOperator(Enum):
    IN = auto()
    OR = auto()
    AND = auto()

    def construct(self):
        return self.name


@EdgeQLObject.register
class EdgeQLComparisonOperator(Enum):
    EQUALS = "="
    CONTAINS = "in"

    def construct(self):
        return self.value


@dataclass
class EdgeQLContainer(EdgeQLObject):

    items: List[EdgeQLObject]

    def construct(self):
        body = ", ".join(construct_seq(self.items))
        return with_parens(body, combo=self.parens)


@dataclass
class EdgeQLTuple(EdgeQLContainer):
    PARENS = "()"


@dataclass
class EdgeQLArray(EdgeQLContainer):
    PARENS = "[]"


@dataclass
class EdgeQLSet(EdgeQLContainer):
    PARENS = "{}"


@dataclass
class EdgeQLName(EdgeQLObject):
    name: str

    def construct(self):
        return self.name


class EdgeQLSpecialName(EdgeQLName):
    def construct(self):
        return self.PREFIX + self.name


@dataclass
class EdgeQLVariable(EdgeQLSpecialName):
    PREFIX = "$"


@dataclass
class EdgeQLFilterKey(EdgeQLSpecialName):
    PREFIX = "."
