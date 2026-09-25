"""Pure, SHA-bound threshold evidence for the pinned compiled-program IR.

The sparse evaluator at engine d59969b53430ae2fd97eb4349d44ad23ce930d85
(`src/engine.rs`, `src/model.rs`, `src/compile.rs`) uses rust_decimal 1.41:
96-bit coefficients, scale at most 28, and nearest-even arithmetic rounding.
We retain Decimal values, fit each arithmetic result to that representation,
and require an exact differential check of every recorded requested output
before accepting any side classifications. Unsupported semantics fail closed.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from typing import Any

from axiom_oracles.evidence import strict_json_loads

MAX_COEFFICIENT = (1 << 96) - 1
ORDERED_OPS = {"lt", "lte", "gt", "gte"}


class InterpretationError(ValueError):
    """Evidence cannot be interpreted under the supported engine semantics."""


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise InterpretationError("expected numeric scalar")
    return Decimal(value)


def _decimal(value: Decimal, *, rounding: str = ROUND_HALF_EVEN) -> Decimal:
    """Round once to the highest representable rust_decimal scale."""
    if not value.is_finite():
        raise InterpretationError("non-finite decimal")
    with localcontext() as context:
        context.prec = 200
        for scale in range(min(28, max(0, -value.as_tuple().exponent)), -1, -1):
            rounded = value.quantize(Decimal(1).scaleb(-scale), rounding=rounding)
            if abs(rounded.scaleb(scale)) <= MAX_COEFFICIENT:
                return rounded
    raise InterpretationError("decimal overflow")


def _literal(value: dict, *, round_input: bool = False) -> Decimal | int | bool:
    kind, raw = value["kind"], value["value"]
    if kind == "bool" and isinstance(raw, bool):
        return raw
    if kind == "integer" and type(raw) is int and -(1 << 63) <= raw < (1 << 63):
        return raw
    if kind == "decimal" and (isinstance(raw, str) or type(raw) is int):
        raw = str(raw)
        if not re.fullmatch(r"[+-]?(?:[0-9][0-9_]*(?:\.[0-9_]*)?|\.[0-9][0-9_]*)", raw):
            raise InterpretationError("unsupported decimal string syntax")
        parsed = Decimal(raw)
        if parsed.is_finite() and (round_input or _decimal(parsed) == parsed):
            # rust_decimal 1.41.0 src/str.rs::maybe_round rounds discarded
            # midpoint digits away from zero; arithmetic uses nearest-even.
            return _decimal(
                parsed, rounding=ROUND_HALF_UP if round_input else ROUND_HALF_EVEN
            )
    raise InterpretationError(f"unsupported or invalid scalar {kind!r}")


def _text(value: Decimal | int | None) -> str | None:
    if value is None:
        return None
    value = _number(value)
    if not value:
        return "0"
    return (
        format(value, "f").rstrip("0").rstrip(".")
        if "." in format(value, "f")
        else str(value)
    )


def _nearest(observations: list[tuple[Decimal, Decimal]], *, below: bool) -> str | None:
    candidates = [
        (left, right)
        for left, right in observations
        if (left < right if below else left > right)
    ]
    if not candidates:
        return None
    with localcontext() as context:
        context.prec = 200
        nearest = min(
            candidates, key=lambda pair: (abs(pair[0] - pair[1]), pair[0], pair[1])
        )
    return _text(nearest[0])


def _children(expr: dict) -> list[tuple[str, dict]]:
    kind = expr.get("kind")
    if kind in {"literal", "input", "derived"}:
        return []
    if kind == "parameter_lookup":
        return [("index", expr["index"])]
    if kind in {"add", "min", "max", "and", "or"}:
        return [(f"items/{i}", item) for i, item in enumerate(expr["items"])]
    if kind in {"sub", "mul", "div", "comparison"}:
        if kind == "comparison" and expr.get("op") not in ORDERED_OPS | {"eq", "ne"}:
            raise InterpretationError(f"unknown comparison {expr.get('op')!r}")
        return [("left", expr["left"]), ("right", expr["right"])]
    if kind == "floor":
        return [("value", expr["value"])]
    if kind == "not":
        return [("item", expr["item"])]
    if kind == "if":
        return [(key, expr[key]) for key in ("condition", "then_expr", "else_expr")]
    raise InterpretationError(f"unknown node kind {kind!r}")


class Interpreter:
    """One compiled artifact; requests retain entity and interval boundaries."""

    def __init__(self, artifact: dict):
        if artifact.get("artifact_format_version") != 1:
            raise InterpretationError("unsupported compiled artifact format")
        self.artifact = artifact
        self.derived = {row["name"]: row for row in artifact["program"]["derived"]}
        self.parameters = {
            row["name"]: row for row in artifact["program"]["parameters"]
        }
        self.roots = {
            row.get("id") or row["name"]: row["name"] for row in self.derived.values()
        }
        self.aliases = {}
        for row in artifact["metadata"]["input_catalog"]:
            for name in row["request_names"]:
                if name in self.aliases and self.aliases[name] != row["slot"]:
                    raise InterpretationError(f"ambiguous input name {name}")
                self.aliases[name] = row["slot"]
        if len(self.derived) != len(artifact["program"]["derived"]):
            raise InterpretationError("duplicate derived names")
        self.period: dict = {}
        self.entity_id = ""
        self.inputs: dict = {}
        self.cache: dict = {}
        self.active: set = set()
        self.live: dict = {}

    def prepare(self, request: dict, query: dict) -> None:
        self.period = query["period"]
        for key in ("start", "end"):
            date.fromisoformat(self.period[key])
        self.entity_id = query["entity_id"]
        self.inputs = defaultdict(list)
        for record in request["dataset"]["inputs"]:
            for key in ("start", "end"):
                date.fromisoformat(record["interval"][key])
            name = record["name"]
            if name not in self.aliases:
                raise InterpretationError(f"unknown request input name {name!r}")
            self.inputs[(self.aliases[name], record["entity_id"])].append(record)
        for rows in self.inputs.values():
            rows.sort(key=lambda row: row["interval"]["start"], reverse=True)
        self.cache, self.live, self.active = {}, {}, set()

    def formula(self, name: str) -> tuple[dict, str]:
        row = self.derived[name]
        if row.get("rounding"):
            raise InterpretationError(f"unsupported output rounding on {name}")
        versions = row.get("versions", [])
        if versions:
            applicable = [
                (i, v)
                for i, v in enumerate(versions)
                if v["effective_from"] <= self.period["start"]
            ]
            if not applicable:
                raise InterpretationError(f"no derived formula version for {name}")
            i, selected = max(applicable, key=lambda item: item[1]["effective_from"])
            return selected["expr"], f"/versions/{i}/expr"
        return row["expr"], "/expr"

    def parameter(self, name: str, index: int) -> Decimal | int | bool:
        versions = [
            v
            for v in self.parameters[name]["versions"]
            if v["effective_from"] <= self.period["start"]
        ]
        if not versions:
            raise InterpretationError(f"no parameter version for {name}")
        selected = max(versions, key=lambda v: v["effective_from"])
        if str(index) not in selected["values"]:
            raise InterpretationError(f"no parameter value {name}[{index}]")
        return _literal(selected["values"][str(index)])

    def evaluate(self, root: str) -> Decimal | int | bool:
        name = self.roots.get(root, root)
        if name not in self.derived:
            raise InterpretationError(f"unknown derived root {root}")
        if name in self.cache:
            return self.cache[name]
        if name in self.active:
            raise InterpretationError(f"derived cycle at {name}")
        self.active.add(name)
        expr, path = self.formula(name)
        value = self.eval_expr(expr, name, path)
        self.active.remove(name)
        self.cache[name] = value
        return value

    def eval_expr(self, expr: dict, derived: str, path: str) -> Decimal | int | bool:
        _children(expr)  # Unknown kinds fail before evaluation.
        kind = expr["kind"]

        def child(key: str):
            return self.eval_expr(expr[key], derived, f"{path}/{key}")

        def items():
            for i, item in enumerate(expr["items"]):
                yield self.eval_expr(item, derived, f"{path}/items/{i}")

        with localcontext() as context:
            context.prec = 200
            if kind == "literal":
                value = _literal(expr["value"])
            elif kind == "input":
                matches = [
                    r
                    for r in self.inputs.get((expr["name"], self.entity_id), [])
                    if r["interval"]["start"] <= self.period["start"]
                    and r["interval"]["end"] >= self.period["end"]
                ]
                if not matches:
                    raise InterpretationError(f"missing input {expr['name']}")
                value = _literal(matches[0]["value"], round_input=True)
            elif kind == "derived":
                value = self.evaluate(expr["name"])
            elif kind == "parameter_lookup":
                index = _number(child("index"))
                if index != index.to_integral_value() or not -(1 << 63) <= index < (
                    1 << 63
                ):
                    raise InterpretationError("parameter index must be an integer")
                value = self.parameter(expr["parameter"], int(index))
            elif kind == "add":
                value = Decimal(0)
                for item in items():
                    value = _decimal(value + _number(item))
            elif kind in {"sub", "mul", "div"}:
                if kind == "div":
                    right, left = _number(child("right")), _number(child("left"))
                    if not right:
                        raise InterpretationError("division by zero")
                    value = _decimal(left / right)
                else:
                    left, right = _number(child("left")), _number(child("right"))
                    value = _decimal(left - right if kind == "sub" else left * right)
            elif kind in {"min", "max"}:
                operands = [_number(item) for item in items()]
                if not operands:
                    raise InterpretationError(f"{kind} requires operands")
                value = (min if kind == "min" else max)(operands)
            elif kind == "floor":
                value = _number(child("value")).to_integral_value(rounding=ROUND_FLOOR)
            elif kind == "if":
                condition = child("condition")
                if type(condition) is not bool:
                    raise InterpretationError("if requires a judgment")
                value = child("then_expr" if condition else "else_expr")
            elif kind in {"and", "or"}:
                value = kind == "and"
                for item in items():
                    if type(item) is not bool:
                        raise InterpretationError(f"{kind} requires judgments")
                    value = item
                    if (kind == "and" and not item) or (kind == "or" and item):
                        break
            elif kind == "not":
                item = child("item")
                if type(item) is not bool:
                    raise InterpretationError("not requires a judgment")
                value = not item
            else:  # comparison
                left, right, op = child("left"), child("right"), expr["op"]
                if isinstance(left, bool) or isinstance(right, bool):
                    if (
                        type(left) is not bool
                        or type(right) is not bool
                        or op not in {"eq", "ne"}
                    ):
                        raise InterpretationError(
                            "boolean comparisons only support == and !="
                        )
                else:
                    left, right = _number(left), _number(right)
                value = {
                    "lt": lambda: left < right,
                    "lte": lambda: left <= right,
                    "gt": lambda: left > right,
                    "gte": lambda: left >= right,
                    "eq": lambda: left == right,
                    "ne": lambda: left != right,
                }[op]()
        self.live[(derived, path)] = value
        return value

    def dependencies(
        self, expr: dict, active: tuple = ()
    ) -> tuple[set[str], dict[str, dict]]:
        _children(expr)
        kind = expr["kind"]
        if kind == "literal":
            _literal(expr["value"])
        if kind == "input":
            return {expr["name"]}, {}
        if kind == "derived":
            name = expr["name"]
            if name in active:
                raise InterpretationError(f"derived cycle at {name}")
            return self.dependencies(self.formula(name)[0], (*active, name))
        inputs: set[str] = set()
        parameters: dict[str, dict] = {}
        for _, child in _children(expr):
            child_inputs, child_parameters = self.dependencies(child, active)
            inputs |= child_inputs
            parameters.update(child_parameters)
        if kind == "parameter_lookup":
            if expr["index"]["kind"] != "literal":
                raise InterpretationError("dynamic parameter indices are unsupported")
            index = _number(_literal(expr["index"]["value"]))
            if index != index.to_integral_value():
                raise InterpretationError("parameter index must be an integer")
            ref = {
                "parameter": expr["parameter"],
                "index": int(index),
                "value": _text(self.parameter(expr["parameter"], int(index))),
            }
            parameters[json.dumps(ref, sort_keys=True)] = ref
        return inputs, parameters

    def input_terms(self, expr: dict) -> dict[str, Decimal]:
        """Retain dependencies conservatively except identical expressions.

        Algebraic cancellation of ``x + p - x`` is unsound here: rounding to
        the engine's finite coefficient can make that difference depend on x.
        Expand derived references, but preserve every arithmetic operation.
        """
        if not self.dependencies(expr)[0]:
            return {}

        def expand(value):
            if isinstance(value, dict):
                if value.get("kind") == "derived":
                    return expand(self.formula(value["name"])[0])
                return {key: expand(item) for key, item in value.items()}
            if isinstance(value, list):
                return [expand(item) for item in value]
            return value

        return {json.dumps(expand(expr), sort_keys=True): Decimal(1)}

    def sites(self, roots: list[str]) -> list[dict]:
        result: list[dict] = []
        visited = set()

        def visit_derived(root):
            name = self.roots.get(root, root)
            if name in visited:
                return
            visited.add(name)
            expr, path = self.formula(name)
            walk(expr, name, path)

        def walk(expr, name, path):
            children = _children(expr)
            self.dependencies(expr)  # Validate even branches never selected.
            if expr["kind"] == "derived":
                visit_derived(expr["name"])
            pairs = []
            if expr["kind"] in {"min", "max"}:
                pairs = list(itertools.combinations(children, 2))
            elif expr["kind"] == "comparison" and expr["op"] in ORDERED_OPS:
                pairs = [(children[0], children[1])]
            for (left_path, left), (right_path, right) in pairs:
                li, lp = self.dependencies(left)
                ri, rp = self.dependencies(right)
                if not (lp or rp) or self.input_terms(left) == self.input_terms(right):
                    continue
                # Orient the input-bearing side first when the other is constant.
                if ri and not li:
                    left_path, right_path = right_path, left_path
                    left, right = right, left
                refs = sorted(
                    {**lp, **rp}.values(),
                    key=lambda ref: (ref["parameter"], ref["index"], ref["value"]),
                )
                derived_id = self.derived[name].get("id") or name
                ident = f"{derived_id}{path}:{left_path}~{right_path}:" + ";".join(
                    f"{r['parameter']}[{r['index']}]={r['value']}" for r in refs
                )
                result.append(
                    {
                        "id": ident,
                        "derived": derived_id,
                        "path": path,
                        "kind": expr["kind"],
                        "parameters": refs,
                        "_key": (name, path),
                        "_left": (name, f"{path}/{left_path}"),
                        "_right": (name, f"{path}/{right_path}"),
                    }
                )
            for suffix, child in children:
                walk(child, name, f"{path}/{suffix}")

        for root in roots:
            visit_derived(root)
        return result


def compute_threshold_straddle(
    compiled_program: bytes,
    traces: dict,
    *,
    view: str | None = None,
    roots: list[str] | None = None,
) -> dict:
    """Interpret bound requests, reconcile outputs, and count live site sides."""
    sha = hashlib.sha256(compiled_program).hexdigest()
    block = {
        "mode": "computed",
        "compiled_program_sha256": sha,
        "self_check": {
            "evaluations": 0,
            "outputs_checked": 0,
            "outputs_matched": 0,
            "complete": False,
            "failures": [],
        },
        "sites": [],
        "unstraddled": [],
        "complete": False,
        "defects": [],
    }
    check = block["self_check"]
    trace_binding = traces.get("compiled_program") if isinstance(traces, dict) else None
    if (
        not isinstance(trace_binding, dict)
        or trace_binding.get("artifact_sha256") != sha
    ):
        block["defects"].append(
            "compiled program SHA256 disagrees with evaluation traces"
        )
        return block
    try:
        interpreter = Interpreter(strict_json_loads(compiled_program.decode()))
        evaluations = [
            e for e in traces["evaluations"] if view is None or e["view"] == view
        ]
        certified_roots = (
            roots
            if roots is not None
            else sorted({r for e in evaluations for r in e["requested_output_roots"]})
        )
        block["requested_output_roots"] = certified_roots
        if not evaluations or not certified_roots:
            raise InterpretationError("no evaluations or requested roots")
        observed_roots = {r for e in evaluations for r in e["requested_output_roots"]}
        if (
            len(set(certified_roots)) != len(certified_roots)
            or set(certified_roots) != observed_roots
        ):
            raise InterpretationError(
                "certified roots disagree with observed requested roots"
            )
        collected: dict[str, dict] = {}
        site_cache: dict[str, list[dict]] = {}
        for evaluation in evaluations:
            check["evaluations"] += 1
            try:
                queries = evaluation["request"]["queries"]
                if len(queries) != 1:
                    raise InterpretationError(
                        "normalized traces require exactly one query"
                    )
                query = queries[0]
                if sorted(query["outputs"]) != sorted(
                    evaluation["requested_output_roots"]
                ):
                    raise InterpretationError("trace roots disagree with query outputs")
                response = evaluation["response"]
                if set(response["outputs"]) != set(query["outputs"]):
                    raise InterpretationError(
                        "recorded outputs disagree with query outputs"
                    )
                if (
                    response.get("entity_id") != query["entity_id"]
                    or response.get("period") != query["period"]
                ):
                    raise InterpretationError(
                        "recorded entity or period disagrees with query"
                    )
                interpreter.prepare(evaluation["request"], query)
                period_key = query["period"]["start"]
                if period_key not in site_cache:
                    site_cache[period_key] = interpreter.sites(certified_roots)
                candidates = site_cache[period_key]
                for site in candidates:
                    collected.setdefault(site["id"], {**site, "_observations": []})
                for root in query["outputs"]:
                    check["outputs_checked"] += 1
                    actual = interpreter.evaluate(root)
                    recorded = evaluation["response"]["outputs"][root]
                    expected = (
                        recorded["outcome"] == "holds"
                        if recorded["kind"] == "judgment"
                        else _literal(recorded["value"])
                    )
                    if recorded["kind"] == "judgment" and recorded["outcome"] not in {
                        "holds",
                        "not_holds",
                    }:
                        raise InterpretationError("unsupported judgment outcome")
                    if (
                        isinstance(actual, bool) != isinstance(expected, bool)
                        or actual != expected
                    ):
                        raise InterpretationError(
                            f"interpreter mismatch for {root}: {actual!s} != {expected!s}"
                        )
                    check["outputs_matched"] += 1
                for site in candidates:
                    if site["_key"] in interpreter.live:
                        left = _number(interpreter.live[site["_left"]])
                        right = _number(interpreter.live[site["_right"]])
                        collected[site["id"]]["_observations"].append((left, right))
            except (
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
                ArithmeticError,
            ) as error:
                check["failures"].append(
                    {
                        "evaluation_id": evaluation.get("evaluation_id"),
                        "reason": str(error),
                    }
                )
        for site in sorted(collected.values(), key=lambda site: site["id"]):
            observations = site["_observations"]
            below = [left for left, right in observations if left < right]
            at = [left for left, right in observations if left == right]
            above = [left for left, right in observations if left > right]
            row = {k: v for k, v in site.items() if not k.startswith("_")}
            row.update(
                below=len(below),
                at=len(at),
                above=len(above),
                live_observations=len(observations),
                straddled=bool(below and above),
                nearest_below=_nearest(observations, below=True),
                nearest_above=_nearest(observations, below=False),
                min_observed=_text(min(left for left, _ in observations))
                if observations
                else None,
                max_observed=_text(max(left for left, _ in observations))
                if observations
                else None,
                threshold=_text(observations[0][1])
                if observations and len({r for _, r in observations}) == 1
                else None,
            )
            if len(row["parameters"]) == 1:
                row.update(row["parameters"][0])
            block["sites"].append(row)
        block["unstraddled"] = [row for row in block["sites"] if not row["straddled"]]
        check["complete"] = (
            not check["failures"]
            and check["outputs_checked"] == check["outputs_matched"]
            and check["outputs_checked"] > 0
        )
        block["complete"] = check["complete"] and not block["unstraddled"]
    except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError) as error:
        block["defects"].append(str(error))
    return block


def parameter_only_straddle(
    module_bytes: bytes, *, roots: list[str], module_id: str
) -> dict:
    """Prove zero sites in source bytes whose signature the caller validated."""
    import yaml

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node):
        pairs = loader.construct_pairs(node, deep=True)
        result = {}
        for key, value in pairs:
            if key in result:
                raise InterpretationError(f"duplicate YAML key {key!r}")
            result[key] = value
        return result

    UniqueLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping
    )
    try:
        document = yaml.load(module_bytes, Loader=UniqueLoader)
        if not roots or len(set(roots)) != len(roots):
            raise InterpretationError("parameter root set is empty or duplicated")
        rules = document["rules"]
        if not isinstance(rules, list):
            raise InterpretationError("module rules are not a list")
        by_name = {}
        for rule in rules:
            name = rule.get("name") or rule.get("id")
            if name in by_name:
                raise InterpretationError("duplicate parameter rule")
            by_name[name] = rule
        for root in roots:
            if not root.startswith(module_id + "#"):
                raise InterpretationError(f"root is outside signed module: {root}")
            name = root[len(module_id) + 1 :]
            rule = by_name.get(name)
            if not rule or rule.get("kind") != "parameter":
                raise InterpretationError(f"root is not a parameter rule: {root}")
            versions = rule.get("versions")
            if not isinstance(versions, list) or not versions:
                raise InterpretationError(f"parameter has no literal versions: {root}")
            for version in versions:
                formula = version.get("formula")
                if isinstance(formula, bool) or not isinstance(
                    formula, (int, float, str)
                ):
                    raise InterpretationError(
                        f"parameter formula is not a numeric literal: {root}"
                    )
                if (
                    not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", str(formula))
                    or not Decimal(str(formula)).is_finite()
                ):
                    raise InterpretationError(
                        f"parameter formula is not a numeric literal: {root}"
                    )
        return {
            "mode": "computed",
            "basis": "signed-parameter-only-roots",
            "module_sha256": hashlib.sha256(module_bytes).hexdigest(),
            "requested_output_roots": roots,
            "sites": [],
            "unstraddled": [],
            "complete": True,
        }
    except (ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError) as error:
        return {"mode": "unavailable", "reason": str(error), "complete": False}
