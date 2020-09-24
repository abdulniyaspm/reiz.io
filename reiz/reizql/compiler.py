import functools
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

from reiz.db.schema import protected_name
from reiz.edgeql import *
from reiz.reizql.nodes import (
    ReizQLConstant,
    ReizQLList,
    ReizQLLogicalOperation,
    ReizQLLogicOperator,
    ReizQLMatch,
    ReizQLMatchEnum,
    ReizQLSet,
)

__DEFAULT_FOR_TARGET = "__KEY"


@dataclass(unsafe_hash=True)
class SelectState:
    name: str
    pointer: Optional[str] = None
    assignments: Dict[str, EdgeQLObject] = field(default_factory=dict)


@functools.singledispatch
def compile_edgeql(obj, state):
    raise ReizQLSyntaxError(f"Unexpected query object: {obj!r}")


@compile_edgeql.register(ReizQLMatch)
def convert_match(node, state=None):
    query = None
    state = SelectState(node.name, None)
    for key, value in node.filters.items():
        state.pointer = protected_name(key, prefix=False)
        conversion = compile_edgeql(value, state)
        if not isinstance(conversion, EdgeQLFilterType):
            conversion = EdgeQLFilter(
                EdgeQLFilterKey(state.pointer), conversion
            )

        if query is None:
            query = conversion
        else:
            query = EdgeQLFilterChain(query, conversion)

    params = {"filters": query}
    if state.assignments:
        params["with_block"] = EdgeQLWithBlock(state.assignments)
    return EdgeQLSelect(state.name, **params)


@compile_edgeql.register(ReizQLMatchEnum)
def convert_match_enum(node, state):
    return EdgeQLCast(protected_name(node.base, prefix=True), repr(node.name))


@compile_edgeql.register(ReizQLLogicalOperation)
def convert_logical_operation(node, state):
    left = compile_edgeql(node.left, state)
    right = compile_edgeql(node.right, state)

    if not isinstance(left, EdgeQLFilterChain):
        left = EdgeQLFilter(EdgeQLFilterKey(state.pointer), left)
    if not isinstance(right, EdgeQLFilterChain):
        right = EdgeQLFilter(EdgeQLFilterKey(state.pointer), right)
    return EdgeQLFilterChain(left, right, compile_edgeql(node.operator, state))


@compile_edgeql.register(ReizQLLogicOperator)
def convert_logical_operator(node, state):
    if node is ReizQLLogicOperator.OR:
        return EdgeQLLogicOperator.OR


@compile_edgeql.register(ReizQLSet)
def convert_set(node, state):
    return EdgeQLSet([compile_edgeql(item, state) for item in node.items])


def generate_typechecked_query(filters, base):
    base_query = None
    for query, operator in unpack_filters(filters):
        assert isinstance(query.key, EdgeQLFilterKey)
        key = EdgeQLAttribute(base, query.key.name)

        current_query = None
        if isinstance(query.value, EdgeQLPreparedQuery):
            current_query = replace(query, key=key)
        elif isinstance(query.value, EdgeQLSelect):
            model = protected_name(query.value.name, prefix=True)
            verifier = EdgeQLVerify(key, EdgeQLVerifyOperator.IS, model)
            current_query = generate_typechecked_query(
                query.value.filters, verifier
            )
        else:
            raise ReizQLSyntaxError("Unsupported syntax")

        base_query = merge_filters(base_query, current_query, operator)

    return base_query


@compile_edgeql.register(ReizQLList)
def convert_list(node, state):
    quantity_verifier = EdgeQLFilter(
        EdgeQLCall("count", [EdgeQLFilterKey(state.pointer)]), len(node.items)
    )
    if len(node.items) == 0:
        return quantity_verifier

    key_types = []
    assignments = {}
    select_filters = None
    for index, item in enumerate(node.items):
        assert isinstance(item, ReizQLMatch)
        key_types.append(item.name)
        selection = EdgeQLSelect(
            EdgeQLFilterKey(state.pointer),
            ordered=EdgeQLProperty("index"),
            offset=index,
            limit=1,
        )
        filters = convert_match(item).filters

        if filters is None:
            continue

        assignments[f"__item_{index}"] = EdgeQLVerify(
            selection,
            EdgeQLVerifyOperator.IS,
            protected_name(item.name, prefix=True),
        )
        select_filters = merge_filters(
            select_filters,
            generate_typechecked_query(filters, f"__item_{index}"),
        )

    for ql_type in set(key_types):
        state.assignments[ql_type] = EdgeQLSelect(
            EdgeQLPreparedQuery("schema::ObjectType"),
            filters=make_filter(
                name=repr(protected_name(ql_type, prefix=True))
            ),
        )

    # array_agg((FOR KEY in {(SELECT .keys ORDER BY @index)} UNION KEY.__type__.id)) = [Constant.id, Call.id]
    iterator = EdgeQLSet(
        [
            EdgeQLSelect(
                EdgeQLFilterKey(state.pointer),
                ordered=EdgeQLProperty("index"),
            )
        ]
    )

    list_type_checker = EdgeQLCall(
        "array_agg",
        [
            EdgeQLFor(
                target=__DEFAULT_FOR_TARGET,
                iterator=iterator,
                generator=EdgeQLAttribute(
                    EdgeQLAttribute(
                        __DEFAULT_FOR_TARGET,
                        "__type__",
                    ),
                    "id",
                ),
            )
        ],
    )

    type_verifier = EdgeQLFilter(
        list_type_checker,
        EdgeQLArray(
            [EdgeQLAttribute(key_type, "id") for key_type in key_types]
        ),
    )

    object_verifier = EdgeQLFilterChain(quantity_verifier, type_verifier)
    if select_filters:
        value_verifier = EdgeQLSelect(
            select_filters,
            with_block=EdgeQLWithBlock(assignments),
        )
        object_verifier = EdgeQLFilterChain(
            object_verifier,
            value_verifier,
        )
    return object_verifier


@compile_edgeql.register(ReizQLConstant)
def convert_atomic(node, state):
    return EdgeQLPreparedQuery(str(node.value))
