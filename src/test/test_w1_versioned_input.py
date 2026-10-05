"""Targeted PURE LOGIC fixtures, not a native FE or 32060-mode certificate.

The transaction fixture replaces only the already checked input identity;
actual writer, seal, reopened supervision and consumer functions execute.
No production constants, old schema limits or numerical thresholds change.
"""

import copy
import datetime
import json
from pathlib import Path

import numpy as np
import pytest

from src.common import w1_mode_validation as modes
from src.io import w1_versioned_input as versioned
from src.io.finite_json import atomic_json
from src.io.w1_evidence import file_receipt, seal_stage
from src.io.w1_receiver_contract import (
    load_w1,
    validate_originals,
    MANIFEST_SHA,
    MANIFEST_BYTES,
)
from src.runners.w1_component_receiver import remaining, compute_stage_deadline
from src.runners.w1_versioned_payload import validate_boundary_summary
from src.solvers.w1_facet_profile import subdivision_count, q60_moments
from src.solvers.w1_saved_boundary import read_npz, terms

ROOT = Path(__file__).resolve().parents[2]


def test_actual_frozen_floquet_return_contract(monkeypatch):
    import ast
    import math
    import sys
    import types
    from src.runners.w1_component_payload import layout_for

    frozen = (
        ROOT
        / "benchmarks/artifacts/task42extra/w1_receiver/source_cccbcbaa3973f16f/benchmarks/run_task40_w1_boundary_probe.py"
    )
    tree = ast.parse(frozen.read_text())
    node = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_floquet_phases"
    )
    scope = dict(
        np=np,
        math=math,
        PERIOD_X_NM=50,
        PERIOD_Y_NM=25,
        zvalue=lambda v: complex(v["real"], v["imag"]),
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(frozen), "exec"), scope)
    probe = types.ModuleType("benchmarks.run_task40_w1_boundary_probe")
    probe._floquet_phases = scope["_floquet_phases"]
    probe._proportional_axis = lambda b, n: np.linspace(b[0], b[-1], n + 1)
    native = types.ModuleType("src.solvers.directional_boundary")
    native.BoundaryLayout = lambda x, y, p, phases: types.SimpleNamespace(phases=phases)
    native.FacetPolynomial = lambda e: e
    # Only Basix/layout construction is stubbed. Actual frozen phase function runs.
    basix = types.SimpleNamespace(
        ElementFamily=types.SimpleNamespace(N1E=1),
        CellType=types.SimpleNamespace(hexahedron=1),
        LagrangeVariant=types.SimpleNamespace(legendre=1),
        create_element=lambda *args: object(),
    )
    monkeypatch.setitem(sys.modules, "basix", basix)
    monkeypatch.setitem(sys.modules, "src.solvers.directional_boundary", native)
    monkeypatch.setitem(sys.modules, "benchmarks.run_task40_w1_boundary_probe", probe)
    _, row = top_mode()
    layout, facts = layout_for([row], 4)
    assert len(layout.phases) == 2
    assert abs(layout.phases[0] - np.exp(1j * row["alpha"]["real"] * 50)) < 1e-14
    assert layout.phases[1] == 1 and "relative_consistency_spread" in facts


def test_unaffected_actual_control_source_reuse():
    from src.runners.w1_component_receiver import RECEIVER_FILES
    from src.runners.w1_versioned_payload import _compatible_prior_control_source

    run = (
        ROOT / "benchmarks/artifacts/task42extra/w1_receiver/v28/control_retry1/control"
    )
    binding = json.loads((run / "binding.json").read_text())
    current = {p: versioned.digest(ROOT / p) for p in RECEIVER_FILES}
    proof = _compatible_prior_control_source(binding, current)
    assert proof["preserved_control_dependencies"] is True
    assert set(proof["boundary_only_changed_files"]) <= {
        "src/runners/w1_component_payload.py",
        "src/runners/w1_versioned_payload.py",
        "src/solvers/w1_saved_boundary.py",
        "src/runners/w1_admission_budget.py",
    }


def test_qualified_oracle_uses_injected_profile_in_frozen_namespace(
    tmp_path, monkeypatch
):
    import sys
    import types
    from src.runners.w1_versioned_payload import qualify_moments
    from src.runners.w1_component_payload import load_file, atomic_arrays
    from src.solvers import w1_facet_profile as injected
    from src.solvers.interval_facet_moments import unit_interval_moments

    # Simulate the frozen namespace: the new profile is not importable through it.
    monkeypatch.setitem(sys.modules, "src.solvers.w1_facet_profile", None)
    native = types.ModuleType("src.solvers.directional_boundary")
    native.zvalue = lambda v: complex(v["real"], v["imag"])
    monkeypatch.setitem(sys.modules, "src.solvers.directional_boundary", native)
    q, w = np.polynomial.legendre.leggauss(31)
    monkeypatch.setitem(
        sys.modules,
        "basix",
        types.SimpleNamespace(
            CellType=types.SimpleNamespace(interval=1),
            make_quadrature=lambda *args: (((q + 1) / 2)[:, None], w / 2),
        ),
    )
    helpers = types.SimpleNamespace(
        file_receipt=file_receipt,
        load_file=load_file,
        atomic_arrays=atomic_arrays,
        atomic_json=atomic_json,
        guard=lambda b: None,
    )
    x = np.zeros(102)
    x[101] = 8.5 / 46
    layout = types.SimpleNamespace(x=x, y=np.array([-12.5, -6.25, 0]))
    _, row = top_mode()
    binding = dict(contract=dict(integration_profile=injected.NATIVE))
    _, _, reference, frequencies = qualify_moments(
        ROOT,
        [row],
        layout,
        types.SimpleNamespace(unit_interval_moments=unit_interval_moments),
        binding,
        tmp_path,
        helpers,
        injected,
    )
    with np.load(tmp_path / "oracle.npz", allow_pickle=False) as raw:
        assert len(frequencies) == 3
        assert np.max(abs(raw["integration_candidate"] - reference)) < 1e-12


def test_control_reuse_protected_function_damage(tmp_path, monkeypatch):
    import hashlib
    import types
    from src.runners import w1_versioned_payload as driver

    path = "src/runners/w1_component_payload.py"
    old = b"def layout_for():\n return 0\ndef control_layout():\n return 1\n"
    new = old.replace(b"return 1", b"return -1")
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_bytes(new)
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    monkeypatch.setattr(
        driver.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout=old)
    )
    binding = dict(
        receiver_source_sha="a" * 40,
        receiver_files={path: hashlib.sha256(old).hexdigest()},
    )
    with pytest.raises(ValueError, match="UNTESTED_DEPENDENCY_CHANGE"):
        driver._compatible_prior_control_source(
            binding, {path: hashlib.sha256(new).hexdigest()}
        )


@pytest.mark.parametrize(
    "schema,cap,allow_read",
    [
        ("task42extra.w1-v28-batch-window.v1", 24, True),
        ("task42extra.w1-receiver-P0RB-window.v27", 12, False),
    ],
)
def test_last_admission_read_is_not_next_admission(tmp_path, schema, cap, allow_read):
    from src.runners.w1_admission_budget import update_budget

    window = tmp_path / "batch_window.json"
    atomic_json(window, dict(schema=schema))
    atomic_json(
        tmp_path / "resource_samples.json",
        dict(events=[dict(kind="admission", elapsed_seconds=1) for _ in range(cap)]),
    )
    if allow_read:
        assert len(update_budget(window)["events"]) == cap
    else:
        with pytest.raises(TimeoutError):
            update_budget(window)
    with pytest.raises(TimeoutError):
        update_budget(window, before_admission=True)
    atomic_json(
        tmp_path / "resource_samples.json",
        dict(
            events=[dict(kind="admission", elapsed_seconds=1) for _ in range(cap + 1)]
        ),
    )
    with pytest.raises(TimeoutError):
        update_budget(window)


def top_mode():
    physical = json.loads(
        (ROOT / "input/task042extra_feinn_5nm/w1_resolved_config_v28.json").read_text()
    )["physical_identity"]
    # Saved physical incident mode values; not produced by the function under test.
    row = dict(
        schema="fullspace-dtn.mode.v1",
        mode_index=0,
        side="top",
        m=0,
        n=0,
        polarization="s",
        alpha={"real": 8.97461192517716, "imag": 0.0},
        gamma={"real": 0.0, "imag": 0.0},
        beta={"real": 0.15665243385951635, "imag": 0.0},
        k_vector=[
            {"real": 8.97461192517716, "imag": 0.0},
            {"real": 0.0, "imag": 0.0},
            {"real": 0.15665243385951635, "imag": 0.0},
        ],
        e_vector=[
            {"real": 0.0, "imag": 0.0},
            {"real": 1.0, "imag": 0.0},
            {"real": 0.0, "imag": 0.0},
        ],
        h_vector=[
            {"real": -0.017452406437281766, "imag": 0.0},
            {"real": 0.0, "imag": 0.0},
            {"real": 0.9998476951563913, "imag": 0.0},
        ],
        refractive_index={"real": 1.0, "imag": 0.0},
        vertical_sign=1,
        electric_tangential_norm_sq=1.0,
        power_per_unit_amplitude=10.907754023301103,
        propagating=True,
        rayleigh_warning=False,
        classification="propagating",
        rayleigh_tolerance=1e-6,
        projection_denominator=1250.0,
        traction_vector=[
            {"real": 0.0, "imag": 0.0},
            {"real": 0.0, "imag": 0.15665243385951635},
            {"real": 0.0, "imag": 0.0},
        ],
    )
    return physical, row


def test_independent_physical_incident_mode():
    physical, row = top_mode()
    checked = modes.check_row(row, physical, 0, ["top", 0, 0, "s"])
    assert max(v["relative"] for v in checked.values()) < 1e-10
    assert modes.decimal_beta_witness(row, physical, 110)["metrics"]["relative"] < 1e-10


@pytest.mark.parametrize(
    "damage",
    ["beta", "e", "H", "traction", "material", "plane", "key", "order", "conjugate"],
)
def test_bad_contents_updated_hash(damage):
    physical, row = top_mode()
    before = modes.canonical_sha(row)
    if damage == "beta":
        row["beta"]["real"] *= -1
    elif damage == "e":
        row["e_vector"][1]["real"] *= -1
    elif damage == "H":
        row["projection_denominator"] *= 2
    elif damage == "traction":
        row["traction_vector"][1]["imag"] *= -1
    elif damage == "material":
        row["refractive_index"]["real"] = 0.8
    elif damage == "plane":
        physical["ports"]["top"]["reference_plane_z_nm"] = 131.0
        row["projection_denominator"] *= 2
    elif damage == "key":
        row["n"] = 1
    elif damage == "order":
        row["mode_index"] = 1
    else:
        row["traction_vector"] = [
            {"real": z["real"], "imag": -z["imag"]} for z in row["traction_vector"]
        ]
    assert modes.canonical_sha(row) != before
    try:
        checked = modes.check_row(row, physical, 0, ["top", 0, 0, "s"])
    except ValueError:
        return
    assert max(v["relative"] for v in checked.values()) > 1e-10


def test_schema2_is_explicit_and_schema1_strict(tmp_path):
    spec = load_w1(ROOT / "input/task042extra_feinn_5nm/v28_manifest_qualify.dat")
    assert spec["w1_receiver_schema"] == 2 and spec["instance_id"] == versioned.INSTANCE
    assert (MANIFEST_SHA, MANIFEST_BYTES) == (
        "52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d",
        36244923,
    )
    legacy = load_w1(ROOT / "input/task042extra_feinn_5nm/v27_rb_control.dat")
    legacy["manifest_path"] = spec["manifest_path"]
    assert validate_originals(legacy)["received"] is False
    text = (ROOT / "input/task042extra_feinn_5nm/v28_manifest_qualify.dat").read_text()
    path = tmp_path / "bad.dat"
    path.write_text(text.replace(versioned.INSTANCE, "UNAUTHORIZED_INSTANCE"))
    with pytest.raises(ValueError, match="FIXED_INSTANCE"):
        load_w1(path)


def transaction_fixture(tmp_path, monkeypatch):
    run = tmp_path / "manifest_qualify"
    run.mkdir()
    spec = dict(
        w1_receiver_schema=2,
        input_origin=versioned.ORIGIN,
        instance_id=versioned.INSTANCE,
        manifest_path=str(tmp_path / "manifest.json"),
        ledger_path=str(tmp_path / "receipt.json"),
        physical_config_path=str(tmp_path / "config.json"),
        math_commit="c354afa449fb80cfb5012e7d2ff66a3e3e64e088",
        quadrature_degree=60,
        integration_profile="q60_native",
        output_root=str(tmp_path),
        input_sha256="",
        coordinate_convention="main_centered_nm",
        ledger_translation_nm=[25.0, 12.5, 0.0],
    )
    dat = tmp_path / "fixture.dat"
    dat.write_text("PURE_LOGIC_TRANSACTION_ONLY")
    spec["input_sha256"] = versioned.digest(dat)
    base = dict(
        status="CANDIDATE_PENDING_SCIENTIFIC_QUALIFICATION",
        received=False,
        candidate_available=True,
        manifest_sha256=versioned.CANDIDATE_SHA,
        instance_id=versioned.INSTANCE,
    )
    monkeypatch.setattr(versioned, "candidate_identity", lambda s: base)
    binding = dict(
        stage="manifest_qualify",
        original_inputs=base,
        contract=spec,
        receiver_files={},
        math_source_sha=spec["math_commit"],
        source_manifest_sha256="a" * 64,
        window_sha256="b" * 64,
        receiver_source_sha="a" * 40,
        spec=dict(path=str(dat)),
    )
    atomic_json(run / "binding.json", binding)
    numeric = dict(
        status="MODE_SCIENCE_PASS",
        mode_count=32060,
        ordered_key_sha256=versioned.KEY_SHA,
        failed_count=0,
        groups={"top/s": 8015, "top/p": 8015, "bottom/s": 8015, "bottom/p": 8015},
        coverage_complete=True,
        maximum_by_field={"synthetic_fixture": dict(relative=0.0)},
    )
    raw = run / "mode_field_metrics.csv"
    raw.write_text("synthetic,no_actual_FE_or_modes\n")
    atomic_json(
        run / "component_result.json",
        dict(
            status="VERSIONED_MODE_INPUT_QUALIFIED",
            mode_validation=numeric,
            binding_sha256=versioned.digest(run / "binding.json"),
            receiver_source_sha="a" * 40,
            raw=file_receipt(raw),
        ),
    )
    atomic_json(
        run / "supervisor_summary.json",
        dict(
            classification="COMPLETED",
            leader_exit_code=0,
            descendants_cleared=True,
            remaining_child_pids=[],
            sampled_process_tree_swap_peak_bytes=0,
        ),
    )
    atomic_json(run / "evidence.json", seal_stage(run))
    atomic_json(
        run / "receiver_result.json",
        dict(
            receiver_classification="COMPLETED",
            receiver_exit_code=0,
            cleared=True,
            worker_started=True,
            evidence_sha256=versioned.digest(run / "evidence.json"),
            binding_sha256=versioned.digest(run / "binding.json"),
            receiver_source_sha="a" * 40,
        ),
    )
    return run, spec


def test_actual_versioned_writer_seal_reopen_consumer(tmp_path, monkeypatch):
    run, spec = transaction_fixture(tmp_path, monkeypatch)
    assert not versioned.validate_inputs(spec)["received"]
    versioned.publish_qualified_inputs(run, spec, atomic_json)
    assert versioned.validate_inputs(spec)["received"]
    ready = json.loads((tmp_path / "inputs_READY.json").read_text())
    assert ready["receipt_sha256"] == versioned.digest(spec["ledger_path"])
    doc = json.loads(Path(spec["ledger_path"]).read_text())
    doc["instance_id"] = "OTHER"
    atomic_json(spec["ledger_path"], doc)
    ready["receipt_sha256"] = versioned.digest(spec["ledger_path"])
    atomic_json(tmp_path / "inputs_READY.json", ready)
    with pytest.raises(ValueError, match="CROSS_INSTANCE"):
        versioned.validate_inputs(spec)


def test_marker_last_failure(tmp_path, monkeypatch):
    run, spec = transaction_fixture(tmp_path, monkeypatch)

    def failed(path, value):
        if Path(path).name == "receipt.json":
            raise OSError("intentional writer failure")
        atomic_json(path, value)

    with pytest.raises(OSError):
        versioned.publish_qualified_inputs(run, spec, failed)
    assert not (tmp_path / "inputs_READY.json").exists()
    assert not versioned.validate_inputs(spec)["received"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("classification", "RSS_HARD_STOP"),
        ("leader_exit_code", 137),
        ("sampled_process_tree_swap_peak_bytes", 1),
        ("descendants_cleared", False),
    ],
)
def test_failed_supervision_updated_receipt_refused(
    tmp_path, monkeypatch, field, value
):
    run, spec = transaction_fixture(tmp_path, monkeypatch)
    summary = json.loads((run / "supervisor_summary.json").read_text())
    summary[field] = value
    atomic_json(run / "supervisor_summary.json", summary)
    # Actual producer seal accepts file identities; scientific consumer must still reject bad supervision.
    atomic_json(run / "evidence.json", seal_stage(run))
    r = json.loads((run / "receiver_result.json").read_text())
    r["evidence_sha256"] = versioned.digest(run / "evidence.json")
    atomic_json(run / "receiver_result.json", r)
    with pytest.raises(ValueError, match="SUPERVISION"):
        versioned.publish_qualified_inputs(run, spec, atomic_json)
    assert not (tmp_path / "inputs_READY.json").exists()


def test_fixed_profile_full_global_coordinates():
    from numpy.polynomial.legendre import leggauss, legvander

    t, w = leggauss(31)
    t = (t + 1) / 2
    w = w / 2
    td, wd = leggauss(64)
    td = (td + 1) / 2
    wd = wd / 2
    for omega in (0.0, -4.3, 54.97787143782138):
        count = subdivision_count(omega)
        candidate = q60_moments(omega, 6, t, w, count)
        reference = (wd * np.exp(1j * omega * td)) @ legvander(2 * td - 1, 6)
        assert np.max(abs(candidate - reference)) < 1e-12
        assert count & (count - 1) == 0 and abs(omega) / count <= 4 * np.pi
    assert subdivision_count(54.97787143782138) == 8
    with pytest.raises(ValueError):
        q60_moments(54.0, 6, t, w, 16)
    with pytest.raises(ValueError):
        subdivision_count(1 + 2j)


def test_saved_numeric_damage_not_status(tmp_path):
    path = tmp_path / "raw.npz"
    np.savez(path, v=np.array([1 + 2j]))
    row = dict(path="raw.npz", bytes=path.stat().st_size, sha256=versioned.digest(path))
    assert np.array_equal(read_npz(tmp_path, row)["v"], [1 + 2j])
    np.savez(path, v=np.array([1 + 3j]))
    row.update(bytes=path.stat().st_size, sha256=versioned.digest(path))
    assert terms(read_npz(tmp_path, row)["v"], np.array([1 + 2j]))["relative"] > 1e-10
    fake = dict(
        status="W1_REPRESENTATIVE_FACETS_FULL_MODE_EMPIRICAL_PASS",
        coverage={"4": 32060, "6": 32060},
        coverage_complete=True,
        failed_metric_count=0,
        physical_incident_rhs_qualified=True,
        coordinate_physics_qualified=True,
        maximum_original_relative=0.0,
        oracle_maximum_absolute=0.0,
        maximum_by_field={"corrupted": dict(relative=1.0)},
    )
    with pytest.raises(ValueError):
        validate_boundary_summary(fake)
    row["path"] = "../raw.npz"
    with pytest.raises(ValueError):
        read_npz(tmp_path, row)


def test_absolute_moment_gate_not_contraction_cancellation():
    value = dict(
        coverage={"4": 32060, "6": 32060},
        coverage_complete=True,
        failed_metric_count=0,
        physical_incident_rhs_qualified=True,
        coordinate_physics_qualified=True,
        maximum_original_relative=0.0,
        oracle_maximum_absolute=0.0,
        one_dimensional_moment_maximum_absolute=0.0,
        one_dimensional_moment_failed_count=0,
        maximum_by_field={"B": dict(relative=0.0)},
    )
    validate_boundary_summary(value)
    value["one_dimensional_moment_maximum_absolute"] = 2e-12
    with pytest.raises(ValueError, match="NUMERIC_GATE"):
        validate_boundary_summary(value)


def test_batch_window_no_reset_and_caps():
    window = json.loads(
        (ROOT / "tmp/task42extra/w1_receiver/v28/batch_window.json").read_text()
    )
    start = window["origin_monotonic"]
    utc = datetime.datetime.fromisoformat(window["T0_utc"])
    assert remaining(window, now=start, utc_now=utc) == 28800
    assert (
        remaining(
            window, now=start + 100, utc_now=utc + datetime.timedelta(seconds=100)
        )
        == 28700
    )
    assert (
        compute_stage_deadline(window, start, 0, "boundary", now=start) == start + 10800
    )
    bad = copy.deepcopy(window)
    bad["budget_seconds"] = 36000
    with pytest.raises(ValueError):
        remaining(bad, now=start, utc_now=utc)


def test_exact_complex_components_and_adjoint():
    rng = np.random.default_rng(4212801)
    B = rng.normal(size=(8, 5)) + 1j * rng.normal(size=(8, 5))
    D = rng.normal(size=(5, 8)) + 1j * rng.normal(size=(5, 8))
    x = rng.normal(size=8) + 1j * rng.normal(size=8)
    y = rng.normal(size=8) + 1j * rng.normal(size=8)
    assert (
        abs(np.vdot(y, B @ (D @ x)) - np.vdot(D.conj().T @ (B.conj().T @ y), x)) < 1e-12
    )
    assert not np.allclose(D, B.conj().T)


def test_native_saved_control_corruption(tmp_path):
    from src.solvers.w1_saved_boundary import validate_native_control_saved

    arrays = {}
    for p, prefix in ((4, ""), (6, "p6_")):
        dim = 3 * p * (p + 1) ** 2
        T = np.eye(dim)
        T[[0, 1]] = T[[1, 0]]
        G = np.zeros((4, 4), complex)
        G[:, 0] = [1, np.exp(0.37j), np.exp(-0.23j), np.exp(0.37j) * np.exp(-0.23j)]
        x = np.array([0.7 + 0.9j, 0, 0, 0])
        dual = np.array([0.1 + 0.3j, -0.8j, 0.9 - 0.2j, -0.4 + 0.7j])
        arrays.update(
            {
                prefix + "orientation": T,
                prefix + "MPC_expansion": G,
                prefix + "MPC_state": x,
                prefix + "MPC_expanded": G @ x,
                prefix + "MPC_expected": G @ x,
                prefix + "MPC_dual": dual,
            }
        )
    path = tmp_path / "control_arrays.npz"
    np.savez(path, **arrays)
    result = dict(
        status="CONTROL_NATIVE_BOUNDARY_PASS_NO_VOLUME_FE",
        native_control_complete=True,
        raw=file_receipt(path),
    )
    atomic_json(tmp_path / "component_result.json", result)
    assert (
        validate_native_control_saved(tmp_path)["6"]["orientation_all_columns"] == 882
    )
    arrays["p6_MPC_expanded"][3] *= -1
    np.savez(path, **arrays)
    result["raw"] = file_receipt(path)
    atomic_json(tmp_path / "component_result.json", result)
    with pytest.raises(ValueError, match="SAVED_NUMERIC"):
        validate_native_control_saved(tmp_path)


@pytest.mark.parametrize(
    "damage",
    [
        "reference_plane",
        "material",
        "time_convention",
        "bridge",
        "rayleigh",
        "false_history",
    ],
)
def test_config_policy_damage(tmp_path, damage):
    spec = load_w1(ROOT / "input/task042extra_feinn_5nm/v28_manifest_qualify.dat")
    original = versioned.candidate_identity(spec)
    assert original["candidate_available"] and original["received"] is False
    config = json.loads(Path(spec["physical_config_path"]).read_text())
    if damage == "reference_plane":
        config["physical_identity"]["ports"]["top"]["reference_plane_z_nm"] = 131.0
    elif damage == "material":
        config["physical_identity"]["materials"]["bottom_external_medium"][
            "refractive_index"
        ][1] *= -1
    elif damage == "time_convention":
        config["time_convention"] = "exp(+i omega t)"
    elif damage == "bridge":
        config["coordinate_bridge_nm"][0] *= -1
    elif damage == "rayleigh":
        config["diffraction_rayleigh_tolerance"] = 1e-3
    else:
        config["schema1_unchanged"] = False
    path = tmp_path / "wrong.json"
    atomic_json(path, config)
    spec["physical_config_path"] = str(path)
    with pytest.raises(ValueError, match="FROZEN_"):
        versioned.candidate_identity(spec)


def test_bundle_pending_rejected_for_main(tmp_path):
    from src.io.w1_boundary_bundle import consume

    package = tmp_path / "package"
    package.mkdir()
    atomic_json(
        package / "package_manifest.json",
        dict(
            schema="w1-relative-boundary-package.v28",
            instance_id=versioned.INSTANCE,
            handoff_status="SEALED_AWAITING_LOCAL_RELOCATED_CONSUMER",
            main_ingestion_occurred=False,
            files={},
        ),
    )
    with pytest.raises(ValueError, match="READY_AFTER_CLEARED"):
        consume(package, tmp_path / "check")
