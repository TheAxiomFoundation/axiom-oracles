"""Read the Axiom oracle bridge's formula strings in Python, for tests.

The bridge (``axiom_oracles/adapters/axiom/tax_projection.py``) writes each
generated rule as a formula string that the Axiom rules engine compiles. The
engine and the pinned RuleSpec checkouts are not available everywhere these
tests run, so this module reads the same strings with the ordinary meaning of
each operator: ``+ - * /``, comparisons, ``and``/``or``/``not``,
``if C: A else: B``, ``min``, ``max``, ``ceil``, and the relation aggregates
``sum_where(relation, value, condition)`` and ``count_where(relation,
condition)`` over the persons a tax unit's relation records name.

It is a reading aid for checking a bridge rule's arithmetic against the
statute, not a model of the engine. It knows only the bridge's own rules, the
projected input records, and values a test passes in for names that imported
RuleSpec modules define. Any other name raises, so a misspelled identifier
fails a test instead of reading as zero. The engine-backed tests, which skip
without the pinned checkouts, remain the evidence for the composed program.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

#: Rates and fractions the imported RuleSpec modules define, from the statute.
STATUTORY_SECA_VALUES = {
    # 26 USC 1401(a): 12.4 percent of self-employment income.
    "self_employment_oasdi_tax_rate": 0.124,
    # 26 USC 1401(b)(1): 2.9 percent of self-employment income.
    "self_employment_hospital_insurance_tax_rate": 0.029,
    # 26 USC 1402(a)(12)(B): "one-half of the sum of the rates imposed by
    # subsections (a) and (b) of section 1401".
    "self_employment_tax_equivalent_deduction_fraction": 0.5,
    # 26 USC 164(f)(1): "one-half of the taxes imposed by section 1401 (other
    # than the taxes imposed by section 1401(b)(2))".
    "self_employment_tax_deduction_fraction": 0.5,
}

_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+(?:\.\d+)?)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op><=|>=|==|!=|[-+*/(),:<>]))"
)
_KEYWORDS = {"if", "else", "and", "or", "not"}
_BOOLEANS = {"True": True, "true": True, "False": False, "false": False}
_COMPARISONS = {"<", ">", "<=", ">=", "==", "!="}


class FormulaError(Exception):
    """A formula the reader cannot read or evaluate."""


def tokenize(text: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    position = 0
    while text[position:].strip():
        match = _TOKEN.match(text, position)
        if match is None:
            raise FormulaError(f"cannot read {text[position:]!r}")
        if match["num"] is not None:
            raw = match["num"]
            tokens.append(("num", float(raw) if "." in raw else int(raw)))
        elif match["name"] is not None:
            tokens.append(("name", match["name"]))
        else:
            tokens.append(("op", match["op"]))
        position = match.end()
    return tokens


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = tokenize(text)
        self.index = 0

    def parse(self):
        node = self._expr()
        if self.index != len(self.tokens):
            raise FormulaError(f"unread tokens in {self.text!r}: {self.tokens[self.index:]}")
        return node

    def _peek(self):
        if self.index < len(self.tokens):
            return self.tokens[self.index]
        return ("end", None)

    def _take(self):
        token = self._peek()
        self.index += 1
        return token

    def _expect(self, kind, value):
        token = self._take()
        if token != (kind, value):
            raise FormulaError(f"expected {value!r} in {self.text!r}, got {token}")

    def _at(self, kind, value) -> bool:
        return self._peek() == (kind, value)

    def _expr(self):
        if self._at("name", "if"):
            self._take()
            condition = self._expr()
            self._expect("op", ":")
            then = self._expr()
            self._expect("name", "else")
            self._expect("op", ":")
            return ("if", condition, then, self._expr())
        return self._or()

    def _or(self):
        node = self._and()
        while self._at("name", "or"):
            self._take()
            node = ("or", node, self._and())
        return node

    def _and(self):
        node = self._not()
        while self._at("name", "and"):
            self._take()
            node = ("and", node, self._not())
        return node

    def _not(self):
        if self._at("name", "not"):
            self._take()
            return ("not", self._not())
        return self._comparison()

    def _comparison(self):
        node = self._additive()
        kind, value = self._peek()
        if kind == "op" and value in _COMPARISONS:
            self._take()
            return ("bin", value, node, self._additive())
        return node

    def _additive(self):
        node = self._term()
        while self._peek() in (("op", "+"), ("op", "-")):
            operator = self._take()[1]
            node = ("bin", operator, node, self._term())
        return node

    def _term(self):
        node = self._unary()
        while self._peek() in (("op", "*"), ("op", "/")):
            operator = self._take()[1]
            node = ("bin", operator, node, self._unary())
        return node

    def _unary(self):
        if self._at("op", "-"):
            self._take()
            return ("neg", self._unary())
        return self._primary()

    def _primary(self):
        kind, value = self._take()
        if kind == "num":
            return ("num", value)
        if (kind, value) == ("op", "("):
            node = self._expr()
            self._expect("op", ")")
            return node
        if kind == "name" and value in _BOOLEANS:
            return ("num", _BOOLEANS[value])
        if kind == "name" and value not in _KEYWORDS:
            if self._at("op", "("):
                self._take()
                arguments = []
                if not self._at("op", ")"):
                    arguments.append(self._expr())
                    while self._at("op", ","):
                        self._take()
                        arguments.append(self._expr())
                self._expect("op", ")")
                return ("call", value, arguments)
            return ("name", value)
        raise FormulaError(f"unexpected {value!r} in {self.text!r}")


def parse(text: str):
    """Parse one formula string into a nested-tuple tree."""
    return _Parser(text).parse()


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return value
    raise FormulaError(f"{value!r} is not a number")


class BridgeReader:
    """Evaluate bridge rules over one projected Case.

    ``rules`` are bridge rule dicts (``US_TAX_ORACLE_PROGRAM_RULES``).
    ``input_records`` and ``relation_records`` are a projected Case's
    ``axiom_input_records`` and ``axiom_relations``. ``values`` pins names the
    imported RuleSpec modules define, or overrides a bridge rule outright.
    """

    def __init__(
        self,
        rules: Iterable[Mapping[str, Any]],
        *,
        input_records: Iterable[Mapping[str, Any]] = (),
        relation_records: Iterable[Mapping[str, Any]] = (),
        values: Mapping[str, Any] | None = None,
    ) -> None:
        self.rules = {rule["name"]: rule for rule in rules}
        self.values = dict(values or {})
        self.inputs: dict[tuple[str, str], Any] = {}
        self.ambiguous: set[tuple[str, str]] = set()
        self.entity_kinds: dict[str, str] = {}
        for record in input_records:
            key = (record["entity_id"], str(record["name"]).rsplit("#input.", 1)[-1])
            if key in self.inputs and self.inputs[key] != record["value"]:
                self.ambiguous.add(key)
            self.inputs.setdefault(key, record["value"])
            self.entity_kinds[record["entity_id"]] = record["entity"]
        self.relations: dict[str, dict[str, list[str]]] = {}
        for record in relation_records:
            name = str(record["name"]).rsplit("#relation.", 1)[-1]
            roles = record["roles"]
            members = self.relations.setdefault(name, {}).setdefault(
                roles["owner_id"], []
            )
            members.append(roles["related_id"])
        self._cache: dict[tuple[str, str], Any] = {}
        self._stack: list[tuple[str, str]] = []

    def value(self, name: str, entity_id: str = "tax_unit") -> Any:
        if name in self.values:
            return self.values[name]
        rule = self.rules.get(name)
        if rule is not None:
            return self._rule_value(rule, entity_id)
        key = (entity_id, name)
        if key in self.ambiguous:
            raise FormulaError(f"input {name!r} of {entity_id!r} has conflicting values")
        if key in self.inputs:
            return self.inputs[key]
        raise FormulaError(
            f"{name!r} is not a bridge rule, a given value, or an input of {entity_id!r}"
        )

    def _rule_value(self, rule: Mapping[str, Any], entity_id: str) -> Any:
        kind = rule.get("kind")
        if kind == "data_relation":
            raise FormulaError(f"{rule['name']!r} is a relation, not a value")
        if kind == "derived":
            expected = rule["entity"]
            actual = self.entity_kinds.get(
                entity_id, "TaxUnit" if entity_id == "tax_unit" else "Person"
            )
            if expected != actual:
                raise FormulaError(
                    f"{rule['name']!r} is a {expected} rule, read from {actual} {entity_id!r}"
                )
        cache_key = (rule["name"], entity_id if kind == "derived" else "")
        if cache_key in self._cache:
            return self._cache[cache_key]
        if cache_key in self._stack:
            raise FormulaError(f"cycle through {rule['name']!r}")
        self._stack.append(cache_key)
        try:
            formula = rule["versions"][-1]["formula"]
            result = self._eval(parse(formula), entity_id)
        finally:
            self._stack.pop()
        self._cache[cache_key] = result
        return result

    def _related(self, relation_node, entity_id: str) -> list[str]:
        if relation_node[0] != "name":
            raise FormulaError(f"relation must be a name, got {relation_node}")
        relation = relation_node[1]
        if relation not in self.relations and relation not in self.rules:
            raise FormulaError(f"unknown relation {relation!r}")
        return self.relations.get(relation, {}).get(entity_id, [])

    def _person_value(self, node, person_id: str) -> Any:
        if node[0] != "name":
            raise FormulaError(f"aggregate operand must be a name, got {node}")
        return self.value(node[1], person_id)

    def _eval(self, node, entity_id: str) -> Any:
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "name":
            return self.value(node[1], entity_id)
        if kind == "neg":
            return -_number(self._eval(node[1], entity_id))
        if kind == "not":
            return not bool(self._eval(node[1], entity_id))
        if kind == "and":
            return bool(self._eval(node[1], entity_id)) and bool(
                self._eval(node[2], entity_id)
            )
        if kind == "or":
            return bool(self._eval(node[1], entity_id)) or bool(
                self._eval(node[2], entity_id)
            )
        if kind == "if":
            branch = node[2] if bool(self._eval(node[1], entity_id)) else node[3]
            return self._eval(branch, entity_id)
        if kind == "bin":
            return self._binary(node[1], node[2], node[3], entity_id)
        if kind == "call":
            return self._call(node[1], node[2], entity_id)
        raise FormulaError(f"unknown node {node}")

    def _binary(self, operator, left_node, right_node, entity_id):
        left = _number(self._eval(left_node, entity_id))
        right = _number(self._eval(right_node, entity_id))
        if operator == "+":
            return left + right
        if operator == "-":
            return left - right
        if operator == "*":
            return left * right
        if operator == "/":
            if right == 0:
                raise FormulaError("division by zero")
            return left / right
        return {
            "<": left < right,
            ">": left > right,
            "<=": left <= right,
            ">=": left >= right,
            "==": left == right,
            "!=": left != right,
        }[operator]

    def _call(self, function, arguments, entity_id):
        if function == "sum_where":
            relation, value, condition = arguments
            return sum(
                _number(self._person_value(value, person))
                for person in self._related(relation, entity_id)
                if bool(self._person_value(condition, person))
            )
        if function == "count_where":
            relation, condition = arguments
            return sum(
                1
                for person in self._related(relation, entity_id)
                if bool(self._person_value(condition, person))
            )
        values = [_number(self._eval(argument, entity_id)) for argument in arguments]
        if function == "max":
            return max(values)
        if function == "min":
            return min(values)
        if function == "ceil":
            [value] = values
            return math.ceil(value)
        raise FormulaError(f"unknown function {function!r}")


def reader_for_case(projected_case, rules, *, values=None) -> BridgeReader:
    """A reader over a Case that ``attach_axiom_tax_inputs_to_case`` projected."""
    return BridgeReader(
        rules,
        input_records=projected_case.metadata["axiom_input_records"],
        relation_records=projected_case.metadata["axiom_relations"],
        values=values,
    )
