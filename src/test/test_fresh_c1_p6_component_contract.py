"""Pure supervision/storage/error-policy tests; no FE or numerical imports.

Staged only.  These tests do not qualify the p6 component algorithm or live PDE.
"""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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


def test_frozen_w0_raw_member_cap_is_8_gib_and_cannot_be_raised():
    callback = lambda *_: None
    assert COMPONENT.W0_ARCHIVE_PAYLOAD_LIMIT_BYTES == 8 * 1024**3
    COMPONENT.require_callbacks(callback, callback, callback, 8 * 1024**3)
    with pytest.raises(ValueError, match="frozen W0 8 GiB"):
        COMPONENT.require_callbacks(callback, callback, callback, 8 * 1024**3 + 1)


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


def test_worker_and_runner_do_not_route_through_y_orbit_solver_or_probe():
    runner = Path(__file__).parents[2] / "benchmarks" / "run_fresh_c1_p6_component.py"
    for source in (SOURCE, runner):
        text = source.read_text()
        tree = ast.parse(text)
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any("y_orbit" in (node.module or "") for node in imports)
        assert not any("y_orbit" in alias.name for node in ast.walk(tree)
                       if isinstance(node, ast.Import) for alias in node.names)
    run = next(node for node in ast.parse(runner.read_text()).body
               if isinstance(node, ast.FunctionDef) and node.name == "run")
    calls = [(node.lineno, node.func.id) for node in ast.walk(run)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id in {"qualify_live_identity", "run_fresh_p6_component",
                                  "require_live_carrier_unchanged"}]
    by_name = {name: line for line, name in calls}
    assert by_name["qualify_live_identity"] < by_name["run_fresh_p6_component"]
    assert by_name["run_fresh_p6_component"] < by_name["require_live_carrier_unchanged"]
    profile_binding = next(node for node in ast.walk(run) if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Subscript)
                                   and isinstance(target.value, ast.Name)
                                   and target.value.id == "bundle"
                                   and isinstance(target.slice, ast.Constant)
                                   and target.slice.value == "runtime_profile"
                                   for target in node.targets))
    assert isinstance(profile_binding.value, ast.Subscript)
    assert isinstance(profile_binding.value.value, ast.Name)
    assert profile_binding.value.value.id == "abi_identity"
    assert profile_binding.lineno < by_name["qualify_live_identity"]


def test_literal532_profile_identity_accepts_only_exact_profile_scoped_hashes():
    from benchmarks.run_fresh_c1_p6_component import require_fresh_c1_mode_identity
    from src.solvers.fresh_c1_manifest_identity import (
        LOCAL_WSL2_LITERAL532_MANIFEST_SHA256,
        LOCAL_WSL2_PROFILE,
        NATIVE_LITERAL532_MANIFEST_SHA256,
        NATIVE_LINUX_PROFILE,
    )

    require_fresh_c1_mode_identity(532, NATIVE_LITERAL532_MANIFEST_SHA256, NATIVE_LINUX_PROFILE)
    require_fresh_c1_mode_identity(532, LOCAL_WSL2_LITERAL532_MANIFEST_SHA256, LOCAL_WSL2_PROFILE)
    with pytest.raises(ValueError, match="identity mismatch"):
        require_fresh_c1_mode_identity(532, LOCAL_WSL2_LITERAL532_MANIFEST_SHA256, NATIVE_LINUX_PROFILE)
    with pytest.raises(ValueError, match="identity mismatch"):
        require_fresh_c1_mode_identity(532, NATIVE_LITERAL532_MANIFEST_SHA256, LOCAL_WSL2_PROFILE)
    with pytest.raises(ValueError, match="exactly 532"):
        require_fresh_c1_mode_identity(531, LOCAL_WSL2_LITERAL532_MANIFEST_SHA256, LOCAL_WSL2_PROFILE)
    with pytest.raises(ValueError, match="qualified Task40 runtime profile"):
        require_fresh_c1_mode_identity(532, LOCAL_WSL2_LITERAL532_MANIFEST_SHA256, "unqualified")

    # Synthetic digests outside the two-entry allowlist fail closed. These are
    # digest negatives, not regenerated row-level mutation fixtures.
    for changed_manifest in ("material", "phase_or_vector", "row_order", "missing_field"):
        changed_sha = hashlib.sha256(
            f"{LOCAL_WSL2_LITERAL532_MANIFEST_SHA256}:{changed_manifest}".encode("ascii")
        ).hexdigest()
        with pytest.raises(ValueError, match="identity mismatch"):
            require_fresh_c1_mode_identity(532, changed_sha, LOCAL_WSL2_PROFILE)


def test_profile_specific_degree_metadata_preserves_native_shape():
    from src.solvers.dtn_boundary_plane_qualification import fresh_c1_degree_profile
    from src.solvers.fresh_c1_manifest_identity import (
        LOCAL_WSL2_LITERAL532_MANIFEST_SHA256,
        LOCAL_WSL2_PROFILE,
        NATIVE_LITERAL532_MANIFEST_SHA256,
        NATIVE_LINUX_PROFILE,
    )

    native = fresh_c1_degree_profile(6, NATIVE_LINUX_PROFILE)
    local = fresh_c1_degree_profile(6, LOCAL_WSL2_PROFILE)
    assert native["physical_generator_manifest_sha256"] == NATIVE_LITERAL532_MANIFEST_SHA256
    assert "runtime_profile" not in native
    assert local["physical_generator_manifest_sha256"] == LOCAL_WSL2_LITERAL532_MANIFEST_SHA256
    assert local["runtime_profile"] == LOCAL_WSL2_PROFILE


@pytest.mark.parametrize(
    "runtime_profile,carrier_matches,rebuilt_matches,expected",
    [
        ("native_linux", True, True, "reached"),
        ("local_wsl2_authorized", True, True, "reached"),
        ("local_wsl2_authorized", False, True, "carrier_rejected"),
        ("local_wsl2_authorized", True, False, "inventory_rejected"),
    ],
)
def test_qualify_live_identity_uses_nested_profile_and_rejects_wrong_hashes(
    monkeypatch, tmp_path, runtime_profile, carrier_matches, rebuilt_matches, expected
):
    from types import SimpleNamespace
    from src.solvers import fullspace_dtn_action
    from src.solvers import fresh_c1_live_contract as live_contract
    from src.solvers.dtn_boundary_plane_qualification import fresh_c1_degree_profile
    from src.solvers.fresh_c1_manifest_identity import (
        NATIVE_LINUX_PROFILE, literal532_manifest_sha256,
    )

    class ReachedBeforeOracle(Exception):
        pass

    manifest_sha = literal532_manifest_sha256(runtime_profile)
    wrong_sha = literal532_manifest_sha256(NATIVE_LINUX_PROFILE)
    modes = tuple(SimpleNamespace(side="top", m=index - 266, n=0, polarization="s")
                  for index in range(532))
    ordered_keys = tuple((index, mode.side, mode.m, mode.n, mode.polarization)
                         for index, mode in enumerate(modes))
    carrier = object()
    identity = {"physical_generator_manifest_sha256": manifest_sha if carrier_matches else wrong_sha,
                "mode_count": 532, "ordered_mode_keys": ordered_keys}
    outer_profile = {
        "degree": 6,
        "fresh_fixture_c1": True,
        "fresh_c1_profile": fresh_c1_degree_profile(6, runtime_profile),
    }
    monkeypatch.setattr(live_contract, "carrier_numeric_identity", lambda actual: identity)
    monkeypatch.setattr(live_contract, "validate_fresh_c1_bundle_profile",
                        lambda bundle: outer_profile)
    rebuilt_sha = manifest_sha if rebuilt_matches else wrong_sha
    monkeypatch.setattr(fullspace_dtn_action, "build_dynamic_mode_inventory",
                        lambda cfg: (modes, (), rebuilt_sha))

    def checkpoint(stage, facts):
        if stage == "same_live_component_before_qualification":
            raise ReachedBeforeOracle

    bundle = {"dtn_action": SimpleNamespace(carrier=carrier),
              "runtime_profile": runtime_profile,
              "dtn_phase_gauge": live_contract.BOUNDARY_PLANE,
              "cfg": object()}
    call = lambda: live_contract.qualify_live_identity(
        bundle, record_path=tmp_path / "receipt.json",
        allocation_gate=lambda *args: None, checkpoint=checkpoint)
    if expected == "reached":
        with pytest.raises(ReachedBeforeOracle):
            call()
    elif expected == "carrier_rejected":
        with pytest.raises(ValueError, match="same-live qualification accepts only"):
            call()
    else:
        with pytest.raises(ValueError, match="independently regenerated ordered literal532"):
            call()


@pytest.mark.parametrize(
    "runtime_profile,wrong_expected",
    [("native_linux", False), ("local_wsl2_authorized", False),
     ("local_wsl2_authorized", True)],
)
def test_boundary_oracle_uses_nested_profile_before_numerical_work(
    monkeypatch, tmp_path, runtime_profile, wrong_expected
):
    from types import SimpleNamespace
    from src.solvers import dtn_boundary_plane_qualification as qualification
    from src.solvers.dtn_boundary_plane_qualification import fresh_c1_degree_profile
    from src.solvers.fresh_c1_manifest_identity import literal532_manifest_sha256
    from src.solvers.dtn_boundary_phase_gauge import BOUNDARY_PLANE

    class ReachedAfterProfileComparison(Exception):
        pass

    class Config:
        @property
        def stage4_dtn_order_policy(self):
            raise ReachedAfterProfileComparison

    manifest_sha = literal532_manifest_sha256(runtime_profile)
    modes = tuple(SimpleNamespace(side="top", m=index - 266, n=0, polarization="s")
                  for index in range(532))
    ordered_keys = tuple((index, mode.side, mode.m, mode.n, mode.polarization)
                         for index, mode in enumerate(modes))
    entries = tuple(SimpleNamespace(mode_key=key, coupling_rows=(1,), projection_rows=(1,))
                    for key in ordered_keys)
    carrier = SimpleNamespace(
        entries=entries, physical_generator_manifest_sha256=manifest_sha,
        mode_manifest_sha256="assembly-modes", assembly_context_sha256="assembly-context",
        assembly_context={}, construction_numeric_inventory={},
    )
    identity = {"physical_generator_manifest_sha256": manifest_sha,
                "carrier_numeric_sha256": "carrier", "mode_count": 532,
                "ordered_mode_keys": ordered_keys}
    outer_profile = {
        "degree": 6,
        "fresh_fixture_c1": True,
        "fresh_c1_profile": fresh_c1_degree_profile(6, runtime_profile),
    }
    monkeypatch.setattr(qualification, "carrier_numeric_identity", lambda actual: identity)
    monkeypatch.setattr(qualification, "validate_fresh_c1_bundle_profile",
                        lambda bundle: outer_profile)
    bundle = {"dtn_action": SimpleNamespace(carrier=carrier), "degree": 6,
              "cfg": Config(), "setup": object(), "dtn_phase_gauge": BOUNDARY_PLANE,
              "modes": modes, "mode_sha256": manifest_sha}
    expected_sha = "wrong-full-manifest" if wrong_expected else manifest_sha
    record_path = tmp_path / f"{runtime_profile}-{wrong_expected}.json"
    call = lambda: qualification.qualify_fresh_c1_p6_boundary_plane_bundle(
        bundle, record_path=record_path,
        expected_physical_manifest=expected_sha, expected_ordered_keys=ordered_keys)
    if wrong_expected:
        with pytest.raises(ValueError, match="differs from the qualified runtime profile"):
            call()
    else:
        with pytest.raises(ReachedAfterProfileComparison):
            call()
    failed_packet = json.loads(record_path.with_name("failed_live_component.json").read_text())
    if runtime_profile == "local_wsl2_authorized":
        assert failed_packet["runtime_profile"] == runtime_profile
    else:
        assert "runtime_profile" not in failed_packet




def _same_live_profile_report(tmp_path, runtime_profile, *, mismatch=None):
    from benchmarks import check_fresh_c1_p6_component as checker
    from src.solvers.fresh_c1_manifest_identity import literal532_manifest_sha256

    expected = literal532_manifest_sha256(runtime_profile)
    wrong = literal532_manifest_sha256(
        "native_linux" if runtime_profile == "local_wsl2_authorized" else "local_wsl2_authorized")
    physical = wrong if mismatch == "receipt" else expected
    keys = [[index, "top", 0, 0, "s"] for index in range(532)]
    identity = {"physical_generator_manifest_sha256": expected,
                "carrier_numeric_sha256": "carrier-sha", "assembly_context_sha256": "context-sha",
                "assembly_mode_manifest_sha256": "assembly-sha", "ordered_mode_keys": keys}
    receipt = {"schema": "task40extra.same-live-boundary-component.v1",
        "status": "PASS_COMPONENT_ONLY", "full_case_pass": True,
        "PDE_solved": False, "official_results": False, "fresh_fixture_c1": True,
        "degree": 6, "mode_count": 532,
        "physical_generator_manifest_sha256": physical,
        "completed_gates": list(checker.LIVE_COMPONENT_GATES),
        "identity": identity,
        "per_mode": [{"index": index, "key": key} for index, key in enumerate(keys)],
        "output_component_gates": [{"gate": index} for index in range(5)],
        "qualification_source_sha256": "a" * 64}
    receipt_path = tmp_path / f"{runtime_profile}-{mismatch}.json"
    receipt_raw = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    receipt_path.write_bytes(receipt_raw)
    contract_physical = wrong if mismatch == "contract" else expected
    contract = {"physical_generator_manifest_sha256": contract_physical,
        "carrier_numeric_sha256": "carrier-sha", "assembly_context_sha256": "context-sha",
        "assembly_mode_manifest_sha256": "assembly-sha", "ordered_mode_keys": keys}
    before_physical = wrong if mismatch == "before" else expected
    after_physical = wrong if mismatch == "after" else expected
    return {"same_live_qualification": {"schema": receipt["schema"],
            "status": "PASS_COMPONENT_ONLY", "receipt_path": str(receipt_path),
            "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
            "shared_discrete_contract": contract, "live_contract_source_sha256": "b" * 64},
        "carrier_before": {"carrier_numeric_sha256": "carrier-sha",
                           "physical_generator_manifest_sha256": before_physical},
        "carrier_after": {"carrier_numeric_sha256": "carrier-sha",
                          "physical_generator_manifest_sha256": after_physical},
        "source_identity": {"files": {
            "src/solvers/dtn_boundary_plane_qualification.py": "a" * 64,
            "src/solvers/fresh_c1_live_contract.py": "b" * 64}}}


@pytest.mark.parametrize("runtime_profile", ["native_linux", "local_wsl2_authorized"])
def test_checker_same_live_identity_accepts_each_exact_profile(monkeypatch, tmp_path, runtime_profile):
    from benchmarks import check_fresh_c1_p6_component as checker
    from src.solvers import fresh_c1_live_contract

    forwarded = {}
    monkeypatch.setattr(fresh_c1_live_contract, "validate_live_receipt",
                        lambda receipt, **kwargs: forwarded.update(kwargs))
    result = checker._validate_same_live_binding(
        _same_live_profile_report(tmp_path, runtime_profile), runtime_profile=runtime_profile)
    assert result["mode_count"] == 532
    assert forwarded["runtime_profile"] == runtime_profile


@pytest.mark.parametrize("identity_field", ["receipt", "contract", "before", "after"])
def test_checker_same_live_identity_rejects_cross_profile_hash_at_every_binding(
    monkeypatch, tmp_path, identity_field
):
    from benchmarks import check_fresh_c1_p6_component as checker
    from src.solvers import fresh_c1_live_contract

    monkeypatch.setattr(fresh_c1_live_contract, "validate_live_receipt",
                        lambda *_args, **_kwargs: pytest.fail("invalid identity reached receipt validation"))
    report = _same_live_profile_report(
        tmp_path, "local_wsl2_authorized", mismatch=identity_field)
    with pytest.raises(ValueError, match="does not bind|outside the fresh p6 scope"):
        checker._validate_same_live_binding(report, runtime_profile="local_wsl2_authorized")


def test_checker_rejects_unknown_and_cross_profile_carrier_hashes_before_array_reads():
    from benchmarks import check_fresh_c1_p6_component as checker

    with pytest.raises(ValueError, match="qualified Task40 runtime profile"):
        checker._profile_manifest_identity("unqualified_profile")
    report = {"carrier_sources": {"ports": [None] * 532,
        "physical_generator_manifest_sha256": "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"}}
    with pytest.raises(ValueError, match="complete current physical532 carrier source"):
        checker._carrier(None, report, {}, (), lambda *_args: None, None,
                         runtime_profile="local_wsl2_authorized")


@pytest.mark.parametrize("runtime_profile", ["native_linux", "local_wsl2_authorized"])
def test_runner_checker_cli_forwards_the_qualified_receipt_profile(monkeypatch, tmp_path, runtime_profile):
    from benchmarks import check_fresh_c1_p6_component as checker
    from benchmarks import run_fresh_c1_p6_component as runner

    (tmp_path / "worker_report.json").write_text(json.dumps({"schema": "worker-fixture"}))
    monkeypatch.setattr(runner, "_qualified_runtime",
        lambda _receipt: (None, None, {"runtime_profile": runtime_profile}))
    noop = lambda *_args, **_kwargs: None
    monkeypatch.setattr(runner, "_native_callbacks",
        lambda *_args, **_kwargs: (noop, None, noop, noop))
    received = {}
    def fake_check(report, _load_array, **kwargs):
        received.update(kwargs)
        assert report["schema"] == "worker-fixture"
        return {"independent_component_pass": True}
    monkeypatch.setattr(checker, "check_component", fake_check)

    assert runner._checker_cli(tmp_path, tmp_path / "abi_receipt.json") == 0
    assert received["runtime_profile"] == runtime_profile
    assert json.loads((tmp_path / "checker_report.json").read_text())["independent_component_pass"] is True



def test_pyvista_postprocessing_import_is_deferred_to_plot_callsite():
    source = Path(__file__).parents[1] / "solvers" / "solve_vector_maxwell.py"
    tree = ast.parse(source.read_text())
    top_imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]
    assert not any(node.module and node.module.endswith("postprocessing.postprocess")
                   for node in top_imports)
    run_case = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "run_case")
    imports = [node for node in ast.walk(run_case) if isinstance(node, ast.ImportFrom)
               and node.module and node.module.endswith("postprocessing.postprocess")]
    assert len(imports) == 1
    imported = {alias.name for alias in imports[0].names}
    assert "save_fields_and_plots" in imported
    call = next(node for node in ast.walk(run_case) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == "save_fields_and_plots")
    assert imports[0].lineno < call.lineno


def test_budget_manifest_is_a_finite_complete_member_bound():
    runner = Path(__file__).parents[2] / "benchmarks" / "run_fresh_c1_p6_component.py"
    spec = importlib.util.spec_from_file_location("fresh_p6_runner_contract", runner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    budget = module.frozen_budget_identity()
    assert budget["frozen_raw_member_payload_limit_bytes"] == 8 * 1024**3
    assert budget["derived_worst_case_member_upper_bytes"] == 6_900_030_936
    assert budget["remaining_limit_margin_bytes"] == 1_689_903_656
    sources = module.source_identity()
    assert "benchmarks/fresh_c1_p6_w0_dependencies.json" in sources["files"]
    assert "src/solvers/fresh_c1_manifest_identity.py" in sources["files"]
    dependencies = json.loads((Path(__file__).parents[2]
                               / "benchmarks" / "fresh_c1_p6_w0_dependencies.json").read_text())
    assert "src/solvers/fresh_c1_manifest_identity.py" in dependencies["source_sha_manifest_binds"]
    checker_path = Path(__file__).parents[2] / "benchmarks" / "check_fresh_c1_p6_component.py"
    checker_tree = ast.parse(checker_path.read_text())
    checker_source_files = next(ast.literal_eval(node.value) for node in checker_tree.body
                                if isinstance(node, ast.Assign) and any(
                                    isinstance(target, ast.Name) and target.id == "W0_SOURCE_FILES"
                                    for target in node.targets))
    assert set(sources["files"]) == set(checker_source_files)
    assert set(sources["files"]) == set(dependencies["source_sha_manifest_binds"])
    assert sources["source_status"] == "NEW_UNQUALIFIED"


def test_external_guard_stop_preserves_first_cause_and_rejects_empty_reason():
    from benchmarks.subreaper_watchdog import _external_guard_stop_reason

    assert _external_guard_stop_reason(
        "GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED",
        {"stop": True, "reason": "EXTERNAL_RESOURCE_CONTROLLED_STOP"},
    ) == "GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED"
    assert _external_guard_stop_reason(None, {"stop": True, "reason": None}) == "MONITORING_FAILED"


def test_component_same_live_wrapper_rejects_metadata_only_receipt():
    from src.solvers.fresh_c1_live_contract import validate_live_receipt
    import pytest

    identity = {"physical_generator_manifest_sha256": "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951",
                "assembly_mode_manifest_sha256": "m", "assembly_context_sha256": "c",
                "carrier_numeric_sha256": "d", "mode_count": 532,
                "ordered_mode_keys": tuple((i, "top", 0, 0, "s") for i in range(532))}
    with pytest.raises(ValueError, match="complete same-live"):
        validate_live_receipt({"schema": "task40extra.same-live-boundary-component.v1",
                               "status": "PASS_METADATA_ONLY", "full_case_pass": True},
                              identity=identity)


def test_literal532_mode_identity_normalizes_tuple_and_rejects_missing_duplicate_or_reordered_keys():
    from src.solvers.fresh_c1_live_contract import (
        _json_plain, _validate_ordered_mode_identity,
    )

    tuple_keys = tuple((i, "top", 0, 0, "s") for i in range(532))
    tuple_identity = _json_plain({"ordered_mode_keys": tuple_keys})
    list_identity = _json_plain({"ordered_mode_keys": [list(key) for key in tuple_keys]})
    assert tuple_identity == list_identity
    modes = [{"index": i, "key": list(key)} for i, key in enumerate(tuple_keys)]
    assert _validate_ordered_mode_identity(tuple_identity, modes) == list_identity["ordered_mode_keys"]

    missing = {"ordered_mode_keys": tuple_identity["ordered_mode_keys"][:-1]}
    with pytest.raises(ValueError, match="incomplete or repeated"):
        _validate_ordered_mode_identity(missing, modes)

    duplicated_keys = list(tuple_identity["ordered_mode_keys"])
    duplicated_keys[1] = duplicated_keys[0]
    with pytest.raises(ValueError, match="incomplete or repeated"):
        _validate_ordered_mode_identity({"ordered_mode_keys": duplicated_keys}, modes)

    reordered_keys = list(tuple_identity["ordered_mode_keys"])
    reordered_keys[0], reordered_keys[1] = reordered_keys[1], reordered_keys[0]
    with pytest.raises(ValueError, match="key order changed"):
        _validate_ordered_mode_identity({"ordered_mode_keys": reordered_keys}, modes)


def test_dense_and_compact_original_H_keep_the_same_action_without_dense_Hhat():
    import numpy as np
    from src.solvers.original_port_blocks import DiagonalOriginalPortBlock
    from src.solvers.retained_port_block_layout import (
        build_cached_port_representation, port_block_representation_identity,
    )

    keys = ((0, "top", 0, 0, "s"), (1, "bottom", 0, 0, "p"), (2, "top", 1, 0, "s"))
    original = DiagonalOriginalPortBlock(np.asarray([2+1j, 3-.5j, 4+0.25j]), keys)
    ports0 = np.asarray([0, 2], dtype=np.int32); ports0.flags.writeable = False
    di0 = np.asarray([[.5+.2j, -.1j], [0.3, .7-.2j]], dtype=np.complex128); di0.flags.writeable = False
    xib0 = np.asarray([[.2+.1j, .5], [-.3j, .25+.4j]], dtype=np.complex128); xib0.flags.writeable = False
    hlocal0 = np.zeros((2, 2), dtype=np.complex128); hlocal0.flags.writeable = False
    ports1 = np.asarray([], dtype=np.int32); ports1.flags.writeable = False
    di1 = np.empty((0, 1), dtype=np.complex128); di1.flags.writeable = False
    xib1 = np.empty((1, 0), dtype=np.complex128); xib1.flags.writeable = False
    cells = (SimpleNamespace(ports=ports0, Di=di0, XiB=xib0, Hlocal=hlocal0),
             SimpleNamespace(ports=ports1, Di=di1, XiB=xib1, Hlocal=None))
    dense_hhat = np.diag(original.diagonal).copy()
    dense_hhat[np.ix_(ports0, ports0)] += di0 @ xib0
    _same_original, compact_hhat = build_cached_port_representation(original, cells)
    identity = port_block_representation_identity(original, compact_hhat)
    rhs = np.asarray([[1+2j, .5-1j], [2-.25j, -3j], [.2+.7j, 4+.5j]])
    np.testing.assert_allclose(compact_hhat.apply(rhs), dense_hhat @ rhs, rtol=1e-14, atol=1e-14)
    np.testing.assert_allclose(original.solve(rhs), rhs / original.diagonal[:, None], rtol=0, atol=0)
    assert identity["all_cell_count"] == 2 and identity["correction_count"] == 1
    assert compact_hhat.audit["new_square_Hhat_arrays"] == 0
    assert compact_hhat.original_h is original


def test_compact_original_H_stops_on_nonzero_Hlocal_instead_of_dropping_it():
    import numpy as np
    from src.solvers.original_port_blocks import DiagonalOriginalPortBlock
    from src.solvers.retained_port_block_layout import build_cached_port_representation

    original = DiagonalOriginalPortBlock(np.asarray([1+0j]), ((0, "top", 0, 0, "s"),))
    ports = np.asarray([0], dtype=np.int32); ports.flags.writeable = False
    di = np.asarray([[1+0j]], dtype=np.complex128); di.flags.writeable = False
    xib = np.asarray([[1+0j]], dtype=np.complex128); xib.flags.writeable = False
    hlocal = np.asarray([[1e-6+0j]], dtype=np.complex128); hlocal.flags.writeable = False
    cell = SimpleNamespace(ports=ports, Di=di, XiB=xib, Hlocal=hlocal)
    with pytest.raises(NotImplementedError, match="nonzero Hlocal"):
        build_cached_port_representation(original, (cell,))
