from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence


CHECKER_SCHEMA = "task035e.reference-leak-check.v1"
CHECKER_ARTIFACT_SCHEMA = "task035e.reference-leak-check-artifact.v1"
BLIND_INPUT_MANIFEST_SCHEMA = "task035e.blind-input-manifest.v1"
FORMAL_BLIND_ENTRYPOINTS = (
    "benchmarks/task035e_campaign_bootstrap.py",
    "benchmarks/task035e_initial_space.py",
    "benchmarks/task035e_trial_metadata.py",
    "benchmarks/task035e_transition_producer.py",
    "benchmarks/task035e_candidate_output.py",
    "benchmarks/task035e_live_shadow_bridge.py",
    "benchmarks/task035e_cellwise_authority.py",
    "benchmarks/task035e_goal_marking.py",
    "benchmarks/task035e_shadow_bundle.py",
    "benchmarks/task035e_blind_bindings.py",
    "benchmarks/task035e_internal_gate_authority.py",
    "benchmarks/task035e_blind_campaign.py",
    "benchmarks/task035e_campaign_stages.py",
    "benchmarks/task035e_campaign_handlers.py",
    "benchmarks/task035e_p7_saturation_bridge.py",
    "benchmarks/task035e_blind_cycle.py",
)

EXIT_PASS = 0
EXIT_CONFIGURATION_ERROR = 2
EXIT_STATIC_LEAK = 4
EXIT_MANIFEST_LEAK_OR_SCHEMA_ERROR = 8
EXIT_DYNAMIC_ACCESS = 16

_HEX_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_HEX_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_OPAQUE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_FORBIDDEN_IMPORT_RE = re.compile(
    r"(?:^|\.)(?:reference_certifier|hidden_auditor)(?:\.|$)",
    re.IGNORECASE,
)
_FORBIDDEN_SYMBOL_RE = re.compile(
    r"(?:"
    r"reference[_-]?certifier"
    r"|hidden[_-]?auditor"
    r"|(?:hidden|sealed|golden)[_-]?reference"
    r"|reference[_-]?(?:authority|loader|package|path|record|solution|"
    r"observable|error)"
    r"|reference[_-]?(?:hash|sha)(?:$|[_-])"
    r"|reference[_-]?(?:value|label)$"
    r"|(?:load|read|open|get)[_-]?(?:hidden|sealed|reference)[_-]?"
    r"(?:authority|package|record|solution|value)?"
    r"|(?:known|golden)[_-]?(?:grid|solution|answer|reference)"
    r"|authority[_-]?loader"
    r")",
    re.IGNORECASE,
)
_FORBIDDEN_PATH_LITERAL_RE = re.compile(
    r"(?:^|[/\\])(?:"
    r"hidden(?:[_-]?reference)?"
    r"|sealed[_-]?reference"
    r"|golden(?:[_-]?(?:reference|data))?"
    r"|reference[_-]?(?:authority|package|data|records?)"
    r")(?:[/\\]|$)",
    re.IGNORECASE,
)
_PLAIN_REFERENCE_PATH_SEGMENT_RE = re.compile(
    r"(?:^|[/\\])reference[/\\]",
    re.IGNORECASE,
)
_KNOWN_REFERENCE_GRID_RE = re.compile(
    r"\bp6(?:[/_.-]|_h|h)+(?:h)?(?:10|7(?:[._-]|p)?5|5)\b",
    re.IGNORECASE,
)
_ALLOWED_ROOT_FIELDS = frozenset({"schema", "trial", "cycle"})
_ALLOWED_TRIAL_FIELDS = frozenset(
    {
        "trial_id",
        "algorithm_id",
        "source_sha",
        "initial_path_id",
        "maximum_cycles",
    }
)
_ALLOWED_CYCLE_FIELDS = frozenset(
    {
        "cycle_index",
        "state",
        "mesh_forest_sha256",
        "degree_map_sha256",
        "solution_snapshot_sha256",
        "goal_inventory_sha256",
        "full_residual_sha256",
        "adjoint_bundle_sha256",
        "p_shadow_bundle_sha256",
        "h_shadow_bundle_sha256",
        "resource_inventory_sha256",
    }
)
_ALLOWED_CYCLE_STATES = frozenset(
    {
        "initialized",
        "solve",
        "estimate",
        "mark",
        "verify",
        "freeze_ready",
        "frozen",
    }
)
_AUDIT_MARKER = "__TASK035E_AUDIT_RESULT__"


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _safe_relative(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return f"external/{_fingerprint(str(path.resolve()))[:16]}.py"
    if (
        _FORBIDDEN_IMPORT_RE.search(relative)
        or _FORBIDDEN_SYMBOL_RE.search(relative)
        or _FORBIDDEN_PATH_LITERAL_RE.search(relative)
    ):
        return f"redacted/{_fingerprint(relative)[:16]}.py"
    return relative


def _finding(
    *,
    rule_id: str,
    path: Path,
    source_root: Path,
    line: int,
    column: int,
    protected_value: str,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "source": _safe_relative(path, source_root),
        "line": int(line),
        "column": int(column),
        "protected_fingerprint": _fingerprint(protected_value),
    }


def _module_name(path: Path, source_root: Path) -> str:
    relative = path.resolve().relative_to(source_root.resolve())
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_local_module(module: str, source_root: Path) -> Path | None:
    if not module or not all(part.isidentifier() for part in module.split(".")):
        return None
    stem = source_root.joinpath(*module.split("."))
    module_file = stem.with_suffix(".py")
    package_file = stem / "__init__.py"
    source_root_resolved = source_root.resolve()
    for candidate in (module_file, package_file):
        try:
            resolved = candidate.resolve()
            resolved.relative_to(source_root_resolved)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _absolute_from_import(
    *,
    current_module: str,
    current_is_package: bool,
    imported_module: str | None,
    level: int,
) -> str:
    if level == 0:
        return imported_module or ""
    package_parts = current_module.split(".")
    if not current_is_package:
        package_parts = package_parts[:-1]
    ascend = max(0, level - 1)
    if ascend > len(package_parts):
        return ""
    if ascend:
        package_parts = package_parts[:-ascend]
    if imported_module:
        package_parts.extend(imported_module.split("."))
    return ".".join(package_parts)


def _identifier_values(tree: ast.AST) -> list[tuple[str, int, int]]:
    values: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            values.append((node.id, node.lineno, node.col_offset))
        elif isinstance(node, ast.Attribute):
            values.append((node.attr, node.lineno, node.col_offset))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            values.append((node.name, node.lineno, node.col_offset))
        elif isinstance(node, ast.arg):
            values.append((node.arg, node.lineno, node.col_offset))
        elif isinstance(node, ast.keyword) and node.arg is not None:
            values.append((node.arg, node.lineno, node.col_offset))
        elif isinstance(node, ast.alias):
            values.append(
                (
                    node.asname or node.name,
                    getattr(node, "lineno", 0),
                    getattr(node, "col_offset", 0),
                )
            )
    return values


def _literal_rule(value: str) -> str | None:
    if _FORBIDDEN_IMPORT_RE.search(value):
        return "S004"
    if _FORBIDDEN_SYMBOL_RE.search(value):
        return "S005"
    if (
        _FORBIDDEN_PATH_LITERAL_RE.search(value)
        or _PLAIN_REFERENCE_PATH_SEGMENT_RE.search(value)
    ):
        return "S006"
    if _KNOWN_REFERENCE_GRID_RE.search(value):
        return "S007"
    return None


def _assignment_names(node: ast.AST) -> tuple[str, ...]:
    targets: list[ast.AST] = []
    if isinstance(node, ast.Assign):
        targets.extend(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets.append(node.target)
    names = []
    for target in targets:
        for child in ast.walk(target):
            if isinstance(child, ast.Name):
                names.append(child.id.lower())
    return tuple(names)


def _direct_body_raises(statements: Sequence[ast.stmt]) -> bool:
    return bool(statements) and isinstance(statements[0], ast.Raise)


def _is_docstring_literal(
    node: ast.Constant,
    *,
    parents: Mapping[ast.AST, ast.AST],
) -> bool:
    expression = parents.get(node)
    owner = parents.get(expression) if expression is not None else None
    return (
        isinstance(expression, ast.Expr)
        and isinstance(owner, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and bool(owner.body)
        and owner.body[0] is expression
    )


def _dict_key_is_explicit_false(
    node: ast.Constant,
    *,
    parents: Mapping[ast.AST, ast.AST],
) -> bool:
    parent = parents.get(node)
    if not isinstance(parent, ast.Dict):
        return False
    for key, value in zip(parent.keys, parent.values, strict=True):
        if key is node:
            return isinstance(value, ast.Constant) and value.value is False
    return False


def _key_access_call_or_subscript(
    node: ast.Constant,
    *,
    parents: Mapping[ast.AST, ast.AST],
) -> ast.AST | None:
    parent = parents.get(node)
    if (
        isinstance(parent, ast.Call)
        and isinstance(parent.func, ast.Attribute)
        and parent.func.attr == "get"
        and node in parent.args
    ):
        return parent
    if isinstance(parent, ast.Subscript) and parent.slice is node:
        return parent
    return None


def _compare_requires_false(
    comparison: ast.Compare,
    access: ast.AST,
) -> bool:
    if (
        comparison.left is not access
        or len(comparison.ops) != 1
        or len(comparison.comparators) != 1
    ):
        return False
    false_value = comparison.comparators[0]
    if not isinstance(false_value, ast.Constant) or false_value.value is not False:
        return False
    return isinstance(comparison.ops[0], (ast.Is, ast.IsNot))


def _comparison_rejects_non_false(
    comparison: ast.Compare,
    *,
    parents: Mapping[ast.AST, ast.AST],
) -> bool:
    if not isinstance(comparison.ops[0], ast.IsNot):
        return False
    current: ast.AST = comparison
    for _depth in range(8):
        parent = parents.get(current)
        if isinstance(parent, ast.BoolOp) and isinstance(parent.op, ast.Or):
            current = parent
            continue
        if isinstance(parent, ast.If):
            return _direct_body_raises(parent.body)
        break
    return False


def _comparison_is_checked_by_all_guard(
    comparison: ast.Compare,
    *,
    parents: Mapping[ast.AST, ast.AST],
) -> bool:
    if not isinstance(comparison.ops[0], ast.Is):
        return False
    current: ast.AST = comparison
    assignment: ast.Assign | ast.AnnAssign | None = None
    for _depth in range(8):
        parent = parents.get(current)
        if isinstance(parent, (ast.Tuple, ast.List, ast.Set)):
            current = parent
            continue
        if isinstance(parent, (ast.Assign, ast.AnnAssign)):
            assignment = parent
        break
    if assignment is None:
        return False
    names = _assignment_names(assignment)
    if len(names) != 1:
        return False
    binding = names[0]
    owner = parents.get(assignment)
    if owner is None:
        return False
    statement_lists = [
        value
        for _field, value in ast.iter_fields(owner)
        if isinstance(value, list) and assignment in value
    ]
    if len(statement_lists) != 1:
        return False
    statements = statement_lists[0]
    assignment_index = statements.index(assignment)
    for candidate in statements[assignment_index + 1 :]:
        if isinstance(candidate, (ast.Assign, ast.AnnAssign)):
            if binding in _assignment_names(candidate):
                return False
        if not isinstance(candidate, ast.If) or not _direct_body_raises(
            candidate.body
        ):
            continue
        test = candidate.test
        if not (
            isinstance(test, ast.UnaryOp)
            and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Call)
            and isinstance(test.operand.func, ast.Name)
            and test.operand.func.id == "all"
            and len(test.operand.args) == 1
            and isinstance(test.operand.args[0], ast.Name)
            and test.operand.args[0].id.lower() == binding
        ):
            continue
        return True
    return False


def _is_false_enforcement_literal(
    node: ast.Constant,
    *,
    parents: Mapping[ast.AST, ast.AST],
) -> bool:
    access = _key_access_call_or_subscript(node, parents=parents)
    if access is None:
        return False
    comparison = parents.get(access)
    if not isinstance(comparison, ast.Compare) or not _compare_requires_false(
        comparison,
        access,
    ):
        return False
    return _comparison_rejects_non_false(
        comparison,
        parents=parents,
    ) or _comparison_is_checked_by_all_guard(
        comparison,
        parents=parents,
    )


def _is_forbidden_presence_guard_literal(
    node: ast.Constant,
    *,
    parents: Mapping[ast.AST, ast.AST],
) -> bool:
    access = _key_access_call_or_subscript(node, parents=parents)
    comparison = parents.get(access) if access is not None else None
    if (
        access is None
        or not isinstance(comparison, ast.Compare)
        or comparison.left is not access
        or len(comparison.ops) != 1
        or not isinstance(comparison.ops[0], ast.IsNot)
        or len(comparison.comparators) != 1
        or not isinstance(comparison.comparators[0], ast.Constant)
        or comparison.comparators[0].value is not None
    ):
        return False
    current: ast.AST = comparison
    while (
        isinstance(parents.get(current), ast.BoolOp)
        and isinstance(parents[current].op, ast.Or)
    ):
        current = parents[current]
    owner = parents.get(current)
    return isinstance(owner, ast.If) and _direct_body_raises(owner.body)


def _is_membership_denial_guard_literal(
    node: ast.Constant,
    *,
    parents: Mapping[ast.AST, ast.AST],
) -> bool:
    current: ast.AST = node
    comparison: ast.Compare | None = None
    for _depth in range(6):
        parent = parents.get(current)
        if isinstance(parent, (ast.Set, ast.Tuple, ast.List)):
            current = parent
            continue
        if isinstance(parent, ast.Compare):
            comparison = parent
        break
    if (
        comparison is None
        or len(comparison.ops) != 1
        or not isinstance(comparison.ops[0], (ast.In, ast.NotIn))
    ):
        return False
    branch: ast.AST = comparison
    while (
        isinstance(parents.get(branch), ast.BoolOp)
        and isinstance(parents[branch].op, ast.Or)
    ):
        branch = parents[branch]
    owner = parents.get(branch)
    if not isinstance(owner, ast.If):
        return False
    if _direct_body_raises(owner.body):
        return True
    for statement in owner.body:
        if (
            isinstance(statement, ast.If)
            and isinstance(statement.test, ast.Compare)
            and len(statement.test.ops) == 1
            and isinstance(statement.test.ops[0], ast.IsNot)
            and len(statement.test.comparators) == 1
            and isinstance(statement.test.comparators[0], ast.Constant)
            and statement.test.comparators[0].value is False
            and _direct_body_raises(statement.body)
        ):
            return True
    return False


def _module_proves_denial_key(
    tree: ast.AST,
    value: str,
    *,
    parents: Mapping[ast.AST, ast.AST],
    excluded: ast.Constant,
) -> bool:
    for candidate in ast.walk(tree):
        if (
            candidate is excluded
            or not isinstance(candidate, ast.Constant)
            or candidate.value != value
        ):
            continue
        if (
            _dict_key_is_explicit_false(candidate, parents=parents)
            or _is_false_enforcement_literal(candidate, parents=parents)
            or _is_forbidden_presence_guard_literal(
                candidate,
                parents=parents,
            )
            or _is_membership_denial_guard_literal(candidate, parents=parents)
        ):
            return True
    return False


def _is_schema_denial_field_literal(
    node: ast.Constant,
    *,
    tree: ast.AST,
    parents: Mapping[ast.AST, ast.AST],
) -> bool:
    current: ast.AST = node
    assignment: ast.AST | None = None
    for _depth in range(5):
        parent = parents.get(current)
        if isinstance(parent, (ast.Set, ast.Tuple, ast.List)):
            current = parent
            continue
        if (
            isinstance(parent, ast.Call)
            and isinstance(parent.func, ast.Name)
            and parent.func.id == "frozenset"
            and current in parent.args
        ):
            current = parent
            continue
        if isinstance(parent, (ast.Assign, ast.AnnAssign)):
            assignment = parent
        break
    if assignment is None:
        return False
    names = _assignment_names(assignment)
    if not names or not all(
        name.endswith(("_keys", "_fields")) for name in names
    ):
        return False
    return _module_proves_denial_key(
        tree,
        str(node.value),
        parents=parents,
        excluded=node,
    )


def _is_explicit_denial_guard_literal(
    node: ast.Constant,
    *,
    tree: ast.AST,
    parents: Mapping[ast.AST, ast.AST],
) -> bool:
    """Allow protected words only when the AST proves a local reject guard."""

    if (
        _is_docstring_literal(node, parents=parents)
        or _dict_key_is_explicit_false(node, parents=parents)
        or _is_false_enforcement_literal(node, parents=parents)
        or _is_forbidden_presence_guard_literal(node, parents=parents)
        or _is_membership_denial_guard_literal(node, parents=parents)
        or _is_schema_denial_field_literal(
            node,
            tree=tree,
            parents=parents,
        )
    ):
        return True

    current: ast.AST = node
    for _depth in range(6):
        parent = parents.get(current)
        if parent is None:
            break
        names = _assignment_names(parent)
        if any(
            "forbidden" in name or "blocked_layer" in name
            for name in names
        ):
            return True
        current = parent

    return False


def _dynamic_import_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name) and node.func.id == "__import__":
        return "__import__"
    if isinstance(node.func, ast.Attribute) and node.func.attr in {
        "import_module",
        "run_module",
    }:
        return node.func.attr
    return None


def scan_blind_controller(
    controller_package: Path,
    *,
    source_root: Path | None = None,
    source_entrypoints: Sequence[Path] = (),
    protected_fingerprints: Sequence[str] = (),
    maximum_files: int = 4096,
) -> dict[str, Any]:
    package = controller_package.resolve()
    root = (source_root or package.parent).resolve()
    if not package.is_dir():
        raise ValueError("controller package is not a directory")
    try:
        package.relative_to(root)
    except ValueError as error:
        raise ValueError("controller package is outside source root") from error
    protected = frozenset(str(item).lower() for item in protected_fingerprints)
    if any(not _HEX_SHA256_RE.fullmatch(item) for item in protected):
        raise ValueError("protected fingerprints must be lowercase SHA-256 values")

    controller_sources = sorted(path.resolve() for path in package.rglob("*.py"))
    if not controller_sources:
        raise ValueError("controller package contains no Python sources")
    entrypoints: list[Path] = []
    for raw_entrypoint in source_entrypoints:
        entrypoint = Path(raw_entrypoint).resolve()
        try:
            entrypoint.relative_to(root)
        except ValueError as error:
            raise ValueError("source entrypoint is outside source root") from error
        if not entrypoint.is_file() or entrypoint.suffix != ".py":
            raise ValueError("source entrypoint is not a Python source file")
        entrypoints.append(entrypoint)
    if len(set(entrypoints)) != len(entrypoints):
        raise ValueError("source entrypoints must be unique")
    initial = sorted(set(controller_sources) | set(entrypoints))
    pending = list(initial)
    queued = set(initial)
    scanned: set[Path] = set()
    findings: list[dict[str, Any]] = []
    import_edges = 0

    while pending:
        path = pending.pop(0)
        if path in scanned:
            continue
        if len(scanned) >= maximum_files:
            raise ValueError("transitive scan exceeded maximum_files")
        scanned.add(path)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=path.name)
        except (OSError, UnicodeError, SyntaxError) as error:
            findings.append(
                _finding(
                    rule_id="S000",
                    path=path,
                    source_root=root,
                    line=getattr(error, "lineno", 0) or 0,
                    column=getattr(error, "offset", 0) or 0,
                    protected_value=type(error).__name__,
                )
            )
            continue
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }

        current_module = _module_name(path, root)
        current_is_package = path.name == "__init__.py"
        for node in ast.walk(tree):
            import_targets: list[str] = []
            if isinstance(node, ast.Import):
                import_targets.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = _absolute_from_import(
                    current_module=current_module,
                    current_is_package=current_is_package,
                    imported_module=node.module,
                    level=node.level,
                )
                if base:
                    import_targets.append(base)
                    import_targets.extend(
                        f"{base}.{alias.name}"
                        for alias in node.names
                        if alias.name != "*"
                    )
            else:
                continue
            for target in import_targets:
                import_edges += 1
                if _FORBIDDEN_IMPORT_RE.search(target):
                    findings.append(
                        _finding(
                            rule_id="S001",
                            path=path,
                            source_root=root,
                            line=node.lineno,
                            column=node.col_offset,
                            protected_value=target,
                        )
                    )
                    continue
                resolved = _resolve_local_module(target, root)
                if resolved is not None and resolved not in queued:
                    queued.add(resolved)
                    pending.append(resolved)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            dynamic_name = _dynamic_import_name(node)
            if dynamic_name is not None:
                findings.append(
                    _finding(
                        rule_id="S009",
                        path=path,
                        source_root=root,
                        line=node.lineno,
                        column=node.col_offset,
                        protected_value=dynamic_name,
                    )
                )

        for identifier, line, column in _identifier_values(tree):
            if _FORBIDDEN_SYMBOL_RE.search(identifier):
                findings.append(
                    _finding(
                        rule_id="S002",
                        path=path,
                        source_root=root,
                        line=line,
                        column=column,
                        protected_value=identifier,
                    )
                )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            rule_id = _literal_rule(value)
            if (
                rule_id is not None
                and _is_explicit_denial_guard_literal(
                    node,
                    tree=tree,
                    parents=parents,
                )
            ):
                rule_id = None
            if rule_id is None and _fingerprint(value) in protected:
                rule_id = "S008"
            if rule_id is not None:
                findings.append(
                    _finding(
                        rule_id=rule_id,
                        path=path,
                        source_root=root,
                        line=node.lineno,
                        column=node.col_offset,
                        protected_value=value,
                    )
                )

    unique = {
        (
            item["rule_id"],
            item["source"],
            item["line"],
            item["column"],
            item["protected_fingerprint"],
        ): item
        for item in findings
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: (
            item["source"],
            item["line"],
            item["column"],
            item["rule_id"],
        ),
    )
    return {
        "pass": not ordered,
        "scanned_file_count": len(scanned),
        "controller_file_count": len(controller_sources),
        "source_entrypoint_file_count": len(entrypoints),
        "source_entrypoints": [
            {
                "source": _safe_relative(path, root),
                "file_sha256": _file_sha256(path),
            }
            for path in entrypoints
        ],
        "transitive_file_count": len(scanned - set(initial)),
        "import_edge_count": import_edges,
        "findings": ordered,
    }


def _manifest_issue(
    *,
    rule_id: str,
    location: str,
    protected_value: str | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "rule_id": rule_id,
        "location": location,
    }
    if protected_value is not None:
        issue["protected_fingerprint"] = _fingerprint(protected_value)
    return issue


def _check_exact_fields(
    value: Any,
    *,
    allowed: frozenset[str],
    location: str,
    issues: list[dict[str, Any]],
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        issues.append(_manifest_issue(rule_id="M001", location=location))
        return None
    keys = set(value)
    for key in sorted(keys - allowed):
        issues.append(
            _manifest_issue(
                rule_id="M002",
                location=location,
                protected_value=str(key),
            )
        )
    for key in sorted(allowed - keys):
        issues.append(
            _manifest_issue(
                rule_id="M003",
                location=f"{location}.{key}",
            )
        )
    return value


def _check_identifier(
    value: Any,
    *,
    location: str,
    issues: list[dict[str, Any]],
) -> None:
    if not isinstance(value, str) or _OPAQUE_ID_RE.fullmatch(value) is None:
        issues.append(_manifest_issue(rule_id="M004", location=location))


def _check_sha(
    value: Any,
    *,
    location: str,
    sha256_only: bool,
    nullable: bool,
    issues: list[dict[str, Any]],
) -> None:
    if value is None and nullable:
        return
    pattern = _HEX_SHA256_RE if sha256_only else _HEX_SHA_RE
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        issues.append(_manifest_issue(rule_id="M005", location=location))


def _scan_manifest_protected_values(
    value: Any,
    *,
    location: str,
    protected_fingerprints: frozenset[str],
    issues: list[dict[str, Any]],
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if (
                _FORBIDDEN_SYMBOL_RE.search(key_text)
                or _FORBIDDEN_IMPORT_RE.search(key_text)
                or _fingerprint(key_text) in protected_fingerprints
            ):
                issues.append(
                    _manifest_issue(
                        rule_id="M010",
                        location=location,
                        protected_value=key_text,
                    )
                )
            _scan_manifest_protected_values(
                child,
                location=f"{location}.<field>",
                protected_fingerprints=protected_fingerprints,
                issues=issues,
            )
    elif isinstance(value, list):
        for child in value:
            _scan_manifest_protected_values(
                child,
                location=f"{location}[]",
                protected_fingerprints=protected_fingerprints,
                issues=issues,
            )
    elif isinstance(value, str):
        if (
            _literal_rule(value) is not None
            or _fingerprint(value) in protected_fingerprints
        ):
            issues.append(
                _manifest_issue(
                    rule_id="M011",
                    location=location,
                    protected_value=value,
                )
            )


def validate_blind_input_manifest(
    payload: Any,
    *,
    protected_fingerprints: Sequence[str] = (),
) -> dict[str, Any]:
    protected = frozenset(str(item).lower() for item in protected_fingerprints)
    if any(not _HEX_SHA256_RE.fullmatch(item) for item in protected):
        raise ValueError("protected fingerprints must be lowercase SHA-256 values")
    issues: list[dict[str, Any]] = []
    root = _check_exact_fields(
        payload,
        allowed=_ALLOWED_ROOT_FIELDS,
        location="$",
        issues=issues,
    )
    if root is not None:
        if root.get("schema") != BLIND_INPUT_MANIFEST_SCHEMA:
            issues.append(_manifest_issue(rule_id="M006", location="$.schema"))

        trial = _check_exact_fields(
            root.get("trial"),
            allowed=_ALLOWED_TRIAL_FIELDS,
            location="$.trial",
            issues=issues,
        )
        if trial is not None:
            _check_identifier(
                trial.get("trial_id"),
                location="$.trial.trial_id",
                issues=issues,
            )
            _check_identifier(
                trial.get("algorithm_id"),
                location="$.trial.algorithm_id",
                issues=issues,
            )
            _check_sha(
                trial.get("source_sha"),
                location="$.trial.source_sha",
                sha256_only=False,
                nullable=False,
                issues=issues,
            )
            _check_identifier(
                trial.get("initial_path_id"),
                location="$.trial.initial_path_id",
                issues=issues,
            )
            maximum_cycles = trial.get("maximum_cycles")
            if (
                type(maximum_cycles) is not int
                or maximum_cycles < 1
                or maximum_cycles > 6
            ):
                issues.append(
                    _manifest_issue(
                        rule_id="M007",
                        location="$.trial.maximum_cycles",
                    )
                )

        cycle = _check_exact_fields(
            root.get("cycle"),
            allowed=_ALLOWED_CYCLE_FIELDS,
            location="$.cycle",
            issues=issues,
        )
        if cycle is not None:
            cycle_index = cycle.get("cycle_index")
            maximum_cycles = (
                trial.get("maximum_cycles")
                if trial is not None
                else None
            )
            if (
                type(cycle_index) is not int
                or cycle_index < 0
                or cycle_index > 5
                or (
                    type(maximum_cycles) is int
                    and cycle_index >= maximum_cycles
                )
            ):
                issues.append(
                    _manifest_issue(
                        rule_id="M008",
                        location="$.cycle.cycle_index",
                    )
                )
            if cycle.get("state") not in _ALLOWED_CYCLE_STATES:
                issues.append(
                    _manifest_issue(
                        rule_id="M009",
                        location="$.cycle.state",
                    )
                )
            for field in sorted(_ALLOWED_CYCLE_FIELDS - {"cycle_index", "state"}):
                _check_sha(
                    cycle.get(field),
                    location=f"$.cycle.{field}",
                    sha256_only=True,
                    nullable=field
                    in {
                        "p_shadow_bundle_sha256",
                        "h_shadow_bundle_sha256",
                    },
                    issues=issues,
                )

    _scan_manifest_protected_values(
        payload,
        location="$",
        protected_fingerprints=protected,
        issues=issues,
    )
    unique = {
        (
            item["rule_id"],
            item["location"],
            item.get("protected_fingerprint"),
        ): item
        for item in issues
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: (
            item["location"],
            item["rule_id"],
            item.get("protected_fingerprint", ""),
        ),
    )
    return {
        "pass": not ordered,
        "schema": BLIND_INPUT_MANIFEST_SCHEMA,
        "additional_properties": False,
        "issues": ordered,
    }


_AUDIT_BOOTSTRAP = r"""
import base64
import hashlib
import json
import os
import runpy
import sys

MARKER = "__TASK035E_AUDIT_RESULT__"
payload = json.loads(base64.urlsafe_b64decode(sys.argv[1]).decode("utf-8"))
entrypoint = os.path.realpath(payload["entrypoint"])
protected = tuple(os.path.realpath(path) for path in payload["protected_paths"])
entry_argv = list(payload["argv"])
violations = []

class ProtectedAccess(RuntimeError):
    pass

def fingerprint(value):
    return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()

def contained(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except (OSError, ValueError):
        return False

def audit_hook(event, args):
    if event in {
        "subprocess.Popen",
        "os.system",
        "os.posix_spawn",
        "os.posix_spawnp",
        "os.exec",
    }:
        violations.append(
            {
                "rule_id": "D002",
                "protected_fingerprint": fingerprint(event),
            }
        )
        raise ProtectedAccess("unmonitored child process denied")
    if event != "open" or not args:
        return
    candidate = args[0]
    if isinstance(candidate, int):
        return
    try:
        resolved = os.path.realpath(os.fsdecode(candidate))
    except (OSError, TypeError, ValueError):
        return
    for root in protected:
        if contained(resolved, root):
            violations.append(
                {
                    "rule_id": "D001",
                    "protected_fingerprint": fingerprint(resolved),
                }
            )
            raise ProtectedAccess("protected access denied")

sys.addaudithook(audit_hook)
execution_error = None
sys.argv = [entrypoint, *entry_argv]
sys.path.insert(0, os.getcwd())
try:
    runpy.run_path(entrypoint, run_name="__main__")
except SystemExit as error:
    if error.code not in (None, 0):
        execution_error = "SystemExit"
except ProtectedAccess:
    pass
except BaseException as error:
    execution_error = type(error).__name__

result = {
    "pass": not violations and execution_error is None,
    "violations": violations,
    "execution_error_type": execution_error,
}
print(MARKER + json.dumps(result, sort_keys=True, separators=(",", ":")))
"""


def run_audit_canary(
    entrypoint: Path,
    *,
    protected_paths: Sequence[Path],
    argv: Sequence[str] = (),
    cwd: Path | None = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    entry = entrypoint.resolve()
    if not entry.is_file():
        raise ValueError("audit entrypoint is not a file")
    if not protected_paths:
        raise ValueError("dynamic audit requires at least one protected path")
    protected = [Path(path).resolve() for path in protected_paths]
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    payload = {
        "entrypoint": str(entry),
        "protected_paths": [str(path) for path in protected],
        "argv": [str(item) for item in argv],
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _AUDIT_BOOTSTRAP, encoded],
            cwd=str((cwd or entry.parent).resolve()),
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
            env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
        )
    except subprocess.TimeoutExpired:
        return {
            "pass": False,
            "status": "audit_timeout",
            "violations": [],
            "protected_root_fingerprints": [
                _fingerprint(str(path)) for path in protected
            ],
        }

    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    parsed: Mapping[str, Any] | None = None
    for line in reversed(stdout.splitlines()):
        if not line.startswith(_AUDIT_MARKER):
            continue
        try:
            candidate = json.loads(line[len(_AUDIT_MARKER) :])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, Mapping):
            parsed = candidate
            break
    if parsed is None:
        return {
            "pass": False,
            "status": "audit_protocol_error",
            "return_code": completed.returncode,
            "stdout_sha256": _fingerprint(stdout),
            "stderr_sha256": _fingerprint(stderr),
            "stdout_bytes": len(completed.stdout),
            "stderr_bytes": len(completed.stderr),
            "violations": [],
            "protected_root_fingerprints": [
                _fingerprint(str(path)) for path in protected
            ],
        }

    violations = []
    raw_violations = parsed.get("violations")
    if isinstance(raw_violations, list):
        for item in raw_violations:
            if not isinstance(item, Mapping):
                continue
            fingerprint = item.get("protected_fingerprint")
            if isinstance(fingerprint, str) and _HEX_SHA256_RE.fullmatch(fingerprint):
                violations.append(
                    {
                        "rule_id": (
                            item.get("rule_id")
                            if item.get("rule_id") in {"D001", "D002"}
                            else "D000"
                        ),
                        "protected_fingerprint": fingerprint,
                    }
                )
    execution_error_type = parsed.get("execution_error_type")
    execution_error_type = (
        execution_error_type if isinstance(execution_error_type, str) else None
    )
    passed = (
        completed.returncode == 0
        and not violations
        and execution_error_type is None
        and parsed.get("pass") is True
    )
    return {
        "pass": passed,
        "status": (
            "audit_pass"
            if passed
            else (
                "protected_access_detected"
                if violations
                else "controller_execution_error"
            )
        ),
        "return_code": completed.returncode,
        "violations": violations,
        "execution_error_type": execution_error_type,
        "stdout_sha256": _fingerprint(stdout),
        "stderr_sha256": _fingerprint(stderr),
        "stdout_bytes": len(completed.stdout),
        "stderr_bytes": len(completed.stderr),
        "protected_root_fingerprints": [
            _fingerprint(str(path)) for path in protected
        ],
    }


def build_reference_leak_report(
    *,
    controller_package: Path,
    manifest: Any,
    source_root: Path | None = None,
    source_entrypoints: Sequence[Path] = (),
    protected_fingerprints: Sequence[str] = (),
    audit_entrypoint: Path | None = None,
    audit_protected_paths: Sequence[Path] = (),
    audit_argv: Sequence[str] = (),
    audit_cwd: Path | None = None,
) -> dict[str, Any]:
    static_report = scan_blind_controller(
        controller_package,
        source_root=source_root,
        source_entrypoints=source_entrypoints,
        protected_fingerprints=protected_fingerprints,
    )
    manifest_report = validate_blind_input_manifest(
        manifest,
        protected_fingerprints=protected_fingerprints,
    )
    dynamic_report: dict[str, Any]
    if audit_entrypoint is None:
        if audit_protected_paths:
            raise ValueError("protected paths require an audit entrypoint")
        dynamic_report = {
            "pass": False,
            "status": "formal_dynamic_audit_required",
            "violations": [],
        }
    else:
        entry = audit_entrypoint.resolve()
        allowed_dynamic_entries = {
            Path(path).resolve() for path in source_entrypoints
        }
        try:
            entry.relative_to(controller_package.resolve())
            inside_controller = True
        except ValueError:
            inside_controller = False
        if not inside_controller and entry not in allowed_dynamic_entries:
            raise ValueError(
                "formal audit entrypoint must be in the controller package "
                "or the explicit source-entry contract"
            )
        if not audit_protected_paths:
            raise ValueError(
                "formal dynamic audit requires at least one protected path"
            )
        dynamic_report = run_audit_canary(
            entry,
            protected_paths=audit_protected_paths,
            argv=audit_argv,
            cwd=audit_cwd,
        )

    exit_code = EXIT_PASS
    if not static_report["pass"]:
        exit_code |= EXIT_STATIC_LEAK
    if not manifest_report["pass"]:
        exit_code |= EXIT_MANIFEST_LEAK_OR_SCHEMA_ERROR
    if not dynamic_report["pass"]:
        exit_code |= EXIT_DYNAMIC_ACCESS
    return {
        "schema": CHECKER_SCHEMA,
        "schema_version": CHECKER_SCHEMA,
        "manifest_sha256": _json_sha256(manifest),
        "source_sha": (
            manifest.get("trial", {}).get("source_sha")
            if isinstance(manifest, Mapping)
            and isinstance(manifest.get("trial"), Mapping)
            else None
        ),
        "pass": exit_code == EXIT_PASS,
        "status": (
            "reference_isolation_pass"
            if exit_code == EXIT_PASS
            else "reference_isolation_fail_closed"
        ),
        "exit_code": exit_code,
        "exit_code_bits": {
            "static_leak": bool(exit_code & EXIT_STATIC_LEAK),
            "manifest_leak_or_schema_error": bool(
                exit_code & EXIT_MANIFEST_LEAK_OR_SCHEMA_ERROR
            ),
            "dynamic_access": bool(exit_code & EXIT_DYNAMIC_ACCESS),
        },
        "checks": {
            "static": static_report,
            "manifest": manifest_report,
            "dynamic": dynamic_report,
        },
    }


def build_reference_leak_report_artifact(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Wrap one independently computed report in a closed self-hashed artifact."""

    required = {
        "schema",
        "schema_version",
        "manifest_sha256",
        "source_sha",
        "pass",
        "status",
        "exit_code",
        "checks",
    }
    if not required <= set(report):
        raise ValueError("reference-leak report is incomplete")
    if (
        report["schema"] != CHECKER_SCHEMA
        or report["schema_version"] != CHECKER_SCHEMA
    ):
        raise ValueError("reference-leak report schema differs")
    payload = dict(report)
    return {
        "schema_version": CHECKER_ARTIFACT_SCHEMA,
        "producer": {
            "source": "benchmarks/task035e_reference_leak_checker.py",
            "file_sha256": _file_sha256(Path(__file__).resolve()),
        },
        "sha256": _json_sha256(payload),
        "payload": payload,
    }


def write_reference_leak_report_artifact(
    path: Path,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Write one mode-0600 report artifact without replacing prior evidence."""

    destination = path.resolve()
    artifact = build_reference_leak_report_artifact(report)
    encoded = (
        json.dumps(
            artifact,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {
        "path": str(destination),
        "file_sha256": _file_sha256(destination),
        "payload_sha256": str(artifact["sha256"]),
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = _JsonArgumentParser(
        description="Fail-closed Task035e blind-controller reference-leak checker."
    )
    parser.add_argument("--controller-package", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--source-entry", type=Path, action="append", default=[])
    parser.add_argument("--formal-task035e-entrypoints", action="store_true")
    parser.add_argument("--protected-fingerprint", action="append", default=[])
    parser.add_argument("--audit-entry", type=Path)
    parser.add_argument("--protected-path", type=Path, action="append", default=[])
    parser.add_argument("--audit-arg", action="append", default=[])
    parser.add_argument("--audit-cwd", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _configuration_error_report(error: BaseException) -> dict[str, Any]:
    return {
        "schema": CHECKER_SCHEMA,
        "pass": False,
        "status": "configuration_error",
        "exit_code": EXIT_CONFIGURATION_ERROR,
        "error_type": type(error).__name__,
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        source_entrypoints = tuple(args.source_entry)
        if args.formal_task035e_entrypoints:
            if args.source_root is None:
                raise ValueError(
                    "--formal-task035e-entrypoints requires --source-root"
                )
            if source_entrypoints:
                raise ValueError(
                    "formal entrypoints cannot be mixed with --source-entry"
                )
            source_entrypoints = tuple(
                args.source_root / relative
                for relative in FORMAL_BLIND_ENTRYPOINTS
            )
        if not source_entrypoints:
            raise ValueError(
                "formal checker CLI requires explicit source entrypoints"
            )
        manifest_text = args.manifest.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        report = build_reference_leak_report(
            controller_package=args.controller_package,
            manifest=manifest,
            source_root=args.source_root,
            source_entrypoints=source_entrypoints,
            protected_fingerprints=args.protected_fingerprint,
            audit_entrypoint=args.audit_entry,
            audit_protected_paths=args.protected_path,
            audit_argv=args.audit_arg,
            audit_cwd=args.audit_cwd,
        )
        return_code = int(report["exit_code"])
        if args.output is not None:
            write_reference_leak_report_artifact(args.output, report)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        report = _configuration_error_report(error)
        return_code = EXIT_CONFIGURATION_ERROR
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BLIND_INPUT_MANIFEST_SCHEMA",
    "CHECKER_SCHEMA",
    "EXIT_CONFIGURATION_ERROR",
    "EXIT_DYNAMIC_ACCESS",
    "EXIT_MANIFEST_LEAK_OR_SCHEMA_ERROR",
    "EXIT_PASS",
    "EXIT_STATIC_LEAK",
    "build_reference_leak_report",
    "main",
    "run_audit_canary",
    "scan_blind_controller",
    "validate_blind_input_manifest",
]
