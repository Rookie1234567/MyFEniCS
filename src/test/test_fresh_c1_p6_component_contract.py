"""Pure supervision/storage/error-policy tests; no FE or numerical imports.

Staged only.  These tests do not qualify the p6 component algorithm or live PDE.
"""

import ast
import importlib.util
import json
from pathlib import Path

import pytest


SOURCE = Path(__file__).parents[1] / "solvers" / "fresh_c1_p6_component.py"
SPEC = importlib.util.spec_from_file_location("fresh_p6_contract_only", SOURCE)
COMPONENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPONENT)


def test_callbacks_rejected_before_execution():
    calls = []

    def callback(*args):
        calls.append(args)

    for position in range(3):
        callbacks = [callback] * 3
        callbacks[position] = None
        with pytest.raises(TypeError, match="must be callable"):
            COMPONENT.require_callbacks(*callbacks, 10000)
    assert calls == []
    COMPONENT.require_callbacks(callback, callback, callback, 10000)
    assert calls == []


@pytest.mark.parametrize("budget", [0, -1, True, 1.0, None])
def test_archive_budget_is_explicit_positive_integer(budget):
    callback = lambda *_: None
    with pytest.raises(ValueError, match="positive integer"):
        COMPONENT.require_callbacks(callback, callback, callback, budget)


def test_snapshot_admission_preserves_complete_member_or_stops():
    header = COMPONENT.NPY_HEADER_BYTES_UPPER
    accepted = COMPONENT.admit_snapshot_bytes(1000, 12446784, 1000 + 12446784 + header)
    assert accepted == 1000 + 12446784 + header
    with pytest.raises(COMPONENT.SnapshotBudgetExceeded, match="exceeds admitted archive limit"):
        COMPONENT.admit_snapshot_bytes(1000, 12446784, accepted - 1)
    # No clipping, compression assumption, or partial-member result exists.
    assert COMPONENT.admit_snapshot_bytes(accepted, 0, accepted + header) == accepted + header


@pytest.mark.parametrize("sizes", [(-1, 0, 100), (0, -1, 100), (False, 0, 100), (0, 1.0, 100)])
def test_snapshot_admission_rejects_invalid_size_metadata(sizes):
    with pytest.raises(ValueError, match="nonnegative integers"):
        COMPONENT.admit_snapshot_bytes(*sizes)


def test_zero_operation_scale_requires_exact_zero_error():
    zero = COMPONENT.metric_record(0, 0, 1e-12)
    assert zero["passed"] and zero["relative"] == 0
    for error in (1e-300, 1e-15, 1e-12, 1.0):
        result = COMPONENT.metric_record(error, 0, 1e-12)
        assert result["finite"] and not result["passed"]
        assert result["relative"] is None
        assert result["zero_scale_rule"] == "error_must_be_exactly_zero"


def test_positive_scale_uses_relative_gate_without_absolute_relaxation():
    assert COMPONENT.metric_record(5e-24, 1e-12, 1e-11)["passed"]
    assert not COMPONENT.metric_record(1e-15, 1e-12, 1e-11)["passed"]
    assert not COMPONENT.metric_record(1e-12, 1e-6, 1e-11, absolute_limit=1.0)["passed"]


def test_nonzero_components_cannot_pass_if_zero_scale_norm_underflows():
    # The real component check discovers a nonzero entry before computing the
    # norm.  Feed its exact witness through the pure diagnostic policy.
    result = COMPONENT.metric_record(0, 0, 1e-12, nonzero_error_at_zero_scale=True)
    assert result["finite"] and not result["passed"]
    assert result["nonzero_error_at_zero_scale"]
    assert result["error_norm_underflow_at_zero_scale"]
    json.dumps(result, allow_nan=False)
    tree = ast.parse(SOURCE.read_text())
    metric = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_metric")
    witness = next(node for node in metric.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "nonzero_at_zero_scale"
                           for target in node.targets))
    assert any(isinstance(node, ast.Compare) and any(isinstance(op, ast.NotEq) for op in node.ops)
               for node in ast.walk(witness))


@pytest.mark.parametrize("error,scale", [(float("nan"), 1), (float("inf"), 1), (1, float("inf")),
                                        (-1, 1), (1, -1)])
def test_nonfinite_or_invalid_metrics_fail_with_json_safe_diagnostics(error, scale):
    result = COMPONENT.metric_record(error, scale, 1e-11)
    assert not result["finite"] and not result["passed"]
    assert result["relative"] is None
    json.dumps(result, allow_nan=False)


def test_original_geometry_helper_receives_same_mandatory_tolerance_as_builder():
    """Catch the real inherited helper's mandatory keyword-only argument."""
    tree = ast.parse(SOURCE.read_text())
    calls = {node.func.id: node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id in {"_canonical_axis_aligned_coordinates",
                                  "build_unconstrained_assembly_time_condensation"}}
    exporter = {item.arg: item.value for item in calls["_canonical_axis_aligned_coordinates"].keywords}
    builder = {item.arg: item.value for item in calls["build_unconstrained_assembly_time_condensation"].keywords}
    assert ast.dump(exporter["tolerance"]) == ast.dump(builder["geometry_tolerance"])
    assert isinstance(exporter["tolerance"], ast.Name)
    assert exporter["tolerance"].id == "GEOMETRY_TOLERANCE"
    assert COMPONENT.GEOMETRY_TOLERANCE == 1e-11


def test_pre_elimination_authority_is_checkpointed_before_any_export_and_in_failure():
    tree = ast.parse(SOURCE.read_text())
    runner = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "run_fresh_p6_component")
    checkpoint = next(node for node in ast.walk(runner)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                      and node.func.id == "checkpoint" and node.args
                      and isinstance(node.args[0], ast.Constant)
                      and node.args[0].value == "pre_elimination_tensor_identities")
    exported = next(node for node in ast.walk(runner)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_export_original_tensors")
    first_snapshot = next(node for node in ast.walk(runner)
                          if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                          and node.func.id == "_save_native_maps")
    assert checkpoint.lineno < first_snapshot.lineno < exported.lineno
    failure = next(node for node in ast.walk(runner)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id == "checkpoint" and node.args
                   and isinstance(node.args[0], ast.Constant)
                   and node.args[0].value == "component_control_failure")
    fields = {key.value: value for key, value in zip(failure.args[1].keys, failure.args[1].values)}
    assert ast.dump(fields["pre_elimination_tensor_identities"]) == ast.dump(
        ast.Name(id="pre_elimination_tensor_identities", ctx=ast.Load()))


def test_native_integrity_and_CSR_equivalence_are_separate_at_existing_limit():
    tree = ast.parse(SOURCE.read_text())
    exporter = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "_export_original_tensors")
    source = ast.get_source_segment(SOURCE.read_text(), exporter)
    assert 'actual_hashes["oriented_sha256"] != identity["oriented_sha256"]' in source
    assert '_sha(reconstructed' not in source
    assert '"native_Basix_row_transpose_row_v2"' in source
    assert '"pre_elimination_tensor_identities": _jsonable(identities)' in source
    comparisons = [node for node in ast.walk(exporter) if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name) and node.func.id == "_compare"]
    assert len(comparisons) == 1
    assert isinstance(comparisons[0].args[-1], ast.Name)
    assert comparisons[0].args[-1].id == "ALGEBRA_LIMIT"
    assert COMPONENT.ALGEBRA_LIMIT == 1e-12
