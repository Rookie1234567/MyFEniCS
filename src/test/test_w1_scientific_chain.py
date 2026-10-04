"""Actual saved checkers/publication/gates on explicit PURE_LOGIC_ONLY fixtures.

Basix and direct face integration are stubbed only in the local algebra
fixture. These tests confer no native/FE/full-mode scientific qualification.
"""

import ast
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from src.io.finite_json import atomic_json
from src.io.w1_evidence import (
    file_receipt,
    scientific_identity,
    seal_stage,
    sha,
    validate_stage,
    validate_A,
)
from src.runners import w1_component_payload as payload
from src.runners import w1_component_receiver as receiver
from src.solvers import w1_boundary_components as component
from src.solvers.w1_local_export_patch import export_source
from src.solvers.w1_saved_equations import (
    coordinate_checks,
    oracle_checks,
    incident_checks,
)

ROOT = Path(__file__).resolve().parents[2]


def zvalue(z):
    return complex(z["real"], z["imag"]) if isinstance(z, dict) else complex(z)


@pytest.fixture
def directional(monkeypatch):
    module = ModuleType("src.solvers.directional_boundary")
    module.zvalue = zvalue
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module


def live_guard(stage="p4_top_check"):
    return {
        "stage": stage,
        "window": {
            "deadline_monotonic": time.monotonic() + 600,
            "deadline_utc": (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=600)
            ).isoformat(),
        },
        "stage_deadline_monotonic": time.monotonic() + 600,
    }


def local_fixture(tmp_path, monkeypatch, degree=4, side="top"):
    rng = np.random.default_rng(4212601)
    dim = 3 * degree * (degree + 1) ** 2
    ni = 108 if degree == 4 else 450
    nt = dim - ni
    ii, tt = np.arange(ni), np.arange(ni, dim)
    modes = [
        {
            "side": s,
            "m": m,
            "n": 0,
            "polarization": p,
            "projection_denominator": 1.0,
            "k_vector": [0.1, 0.2, 0.3],
            "e_vector": [0, 1, 0],
            "traction_vector": [-1, 0, 0],
        }
        for s, m, p in (
            ("top", 0, "s"),
            ("top", 1, "p"),
            ("bottom", 0, "s"),
            ("bottom", 1, "p"),
        )
    ]
    indices = np.array([i for i, m in enumerate(modes) if m["side"] == side])

    def random(shape):
        return 0.003 * (rng.normal(size=shape) + 1j * rng.normal(size=shape))

    diagonal = 2 + np.arange(ni) / ni + 0.4j
    Vit, Vti = random((ni, nt)), random((nt, ni))
    Vtt = np.diag(3 + np.arange(nt) / nt - 0.2j)
    Vii = np.diag(diagonal)
    V = np.block([[Vii, Vit], [Vti, Vtt]])
    Bi, Bt, Di, Dt = [random((2, n)) for n in (ni, nt, ni, nt)]
    alpha = np.exp(0.21j * np.arange(4))
    xi, xt = np.exp(0.07j * np.arange(ni)), (1 + 0.3j) * np.exp(0.11j * np.arange(nt))
    bi, bt = Bi.T @ alpha[indices], Bt.T @ alpha[indices]
    fi, ft = Vii @ xi + Vit @ xt + bi, Vti @ xi + Vtt @ xt + bt
    sB, sf, st, sVit = (
        bi / diagonal,
        fi / diagonal,
        (Vit @ xt) / diagonal,
        Vit / diagonal[:, None],
    )

    def port(v):
        out = np.zeros(4, complex)
        out[indices] = Di @ v
        return out

    dt = np.zeros(4, complex)
    dt[indices] = Dt @ xt
    prhs = alpha - port(xi) - dt
    Schur = Vtt - Vti @ sVit
    bhat, fhat = bt - Vti @ sB, ft - Vti @ sf
    qhat, affine = alpha + port(sB), prhs + port(sf)
    fullB, fullD = np.r_[Bi[0], Bt[0]], np.r_[Di[0], Dt[0]]
    integral = np.column_stack((fullB, fullD.conj()))
    rule, weights = np.array([[0.2, 0.3], [0.7, 0.4]]), np.array([0.5, 0.5])
    probe = ModuleType("src.solvers.task40_w1_local_probe")
    probe._direct_full_basis_integral = lambda *args: (integral, rule, weights)
    fake_basix = ModuleType("basix")
    fake_basix.ElementFamily = SimpleNamespace(N1E=1)
    fake_basix.CellType = SimpleNamespace(hexahedron=1)
    fake_basix.LagrangeVariant = SimpleNamespace(legendre=1)
    fake_basix.create_element = lambda *args: SimpleNamespace(
        T_apply=lambda *args: None
    )
    monkeypatch.setitem(sys.modules, probe.__name__, probe)
    monkeypatch.setitem(sys.modules, "basix", fake_basix)
    arrays = {
        "degree": np.array(degree),
        "side": np.array(side),
        "quadrature_degree": np.array(60),
        "interior_positions": ii,
        "trace_positions": tt,
        "local_native_tensor": V,
        "active_mode_indices": indices,
        "saved_Bi": Bi,
        "saved_Bt": Bt,
        "saved_Di": Di,
        "saved_Dt": Dt,
        "mode_keys": np.array(
            [
                [
                    m["m"],
                    m["n"],
                    0 if m["side"] == "top" else 1,
                    0 if m["polarization"] == "s" else 1,
                ]
                for m in modes
            ]
        ),
        "original_H": np.ones(4),
        "mode_alpha": alpha,
        "trace_values": xt,
        "recovered_interior": xi,
        "known_interior_solution": xi,
        "interior_rhs": fi,
        "trace_rhs": ft,
        "Bi_alpha": bi,
        "Bt_alpha": bt,
        "solve_internal_B": sB,
        "solve_internal_rhs": sf,
        "solve_internal_trace": st,
        "solve_Vit": sVit,
        "reduced_trace_matrix": Schur,
        "reduced_trace_B_alpha": bhat,
        "reduced_trace_rhs": fhat,
        "qhat_alpha": qhat,
        "affine_internal_rhs": affine,
        "port_rhs": prhs,
        "port_internal_B_correction": port(sB),
        "port_internal_rhs_correction": port(sf),
        "port_internal_trace_correction": port(st),
        "port_internal_recovered_correction": port(xi),
        "port_trace_action": dt,
        "port_residual": alpha - prhs - port(xi) - dt,
        "reduced_port_residual": qhat - affine - dt + port(st),
        "original_trace_residual": Vti @ xi + Vtt @ xt + bt - ft,
        "reduced_trace_residual": Schur @ xt + bhat - fhat,
        "witness_mode_index": np.array(indices[0]),
        "witness_mode_k": np.array([0.1, 0.2, 0.3], complex),
        "witness_mode_e": np.array([0, 1], complex),
        "witness_mode_traction": np.array([-1, 0], complex),
        "witness_mode_projection_denominator": np.array(1.0),
        "local_cell_coordinates": np.zeros((8, 3)),
        "local_cell_orientation": np.array([0]),
        "witness_direct_q60_rule_points": rule,
        "witness_direct_q60_rule_weights": weights,
        "witness_candidate_B_native": fullB,
        "witness_candidate_D_native": fullD,
    }
    producer = tmp_path / "producer"
    producer.mkdir()
    report = {
        "degree": degree,
        "side": side,
        "consumer_quadrature": component.consumers(60),
    }

    def save():
        report["raw"] = payload.atomic_arrays(producer / "local_arrays.npz", arrays)
        payload.atomic_json(producer / "component_result.json", report)

    save()
    return arrays, modes, producer, save


def scientific_chain(tmp_path, monkeypatch):
    output = tmp_path / "chain"
    output.mkdir()
    original = {
        "received": True,
        "manifest_sha256": "fixture-only",
        "ledger_sha256": "fixture-only",
    }
    monkeypatch.setattr(receiver, "validate_originals", lambda spec: original)
    window = output / "window.json"
    atomic_json(window, {"fixture": True})
    source = output / "source.json"
    atomic_json(source, {"fixture": True})
    common = {
        "manifest_path": "fixture-manifest",
        "ledger_path": "fixture-ledger",
        "math_commit": receiver.MATH_COMMIT,
        "quadrature_degree": 60,
        "output_root": str(tmp_path),
        "coordinate_convention": "main_centered_nm",
        "ledger_translation_nm": [25.0, 12.5, 0.0],
    }
    spec = {**common, "source_manifest_path": str(source), "window_path": str(window)}
    bindings = {}

    def publish(stage, result, summary=None, source_sha="a" * 40):
        run = output / stage
        run.mkdir(exist_ok=True)
        dat = run / "fixture.dat"
        dat.write_text("fixture-stage=" + stage)
        binding = {
            "stage": stage,
            "receiver_source_sha": source_sha,
            "contract": {**common, "input_sha256": sha(dat)},
            "spec": {"path": str(dat)},
            "original_inputs": original,
            "receiver_files": {
                p: receiver.digest(ROOT / p) for p in receiver.RECEIVER_FILES
            },
            "math_source_sha": receiver.MATH_COMMIT,
            "source_manifest_sha256": sha(source),
            "window_sha256": sha(window),
        }
        atomic_json(run / "binding.json", binding)
        if "raw_receipts" not in result:
            raw = run / "raw.json"
            atomic_json(raw, {"fixture": True})
            result = {**result, "raw_receipts": [file_receipt(raw)]}
        result = {
            **result,
            "binding_sha256": sha(run / "binding.json"),
            "receiver_source_sha": binding["receiver_source_sha"],
        }
        payload.atomic_json(run / "component_result.json", result)
        summary = summary or {
            "classification": "COMPLETED",
            "leader_exit_code": 0,
            "descendants_cleared": True,
            "remaining_child_pids": [],
            "sampled_process_tree_swap_peak_bytes": 0,
        }
        atomic_json(run / "supervisor_summary.json", summary)
        atomic_json(run / "evidence.json", seal_stage(run))
        atomic_json(
            run / "receiver_result.json",
            {
                "receiver_classification": summary["classification"],
                "receiver_exit_code": summary["leader_exit_code"],
                "cleared": summary["descendants_cleared"],
                "worker_started": True,
                "receiver_source_sha": binding["receiver_source_sha"],
                "binding_sha256": sha(run / "binding.json"),
                "evidence_sha256": sha(run / "evidence.json"),
            },
        )
        bindings[stage] = binding
        return run

    publish(
        "control",
        {
            "status": "CONTROL_NATIVE_BOUNDARY_PASS_NO_VOLUME_FE",
            "native_control_complete": True,
        },
    )
    publish("boundary", {"status": "BOUNDARY_WORKER_PASS_PENDING_CHECKER"})
    publish(
        "boundary_check",
        {
            "status": "P1_Q60_FULL_MODE_PASS",
            "coverage_complete": True,
            "physical_incident_rhs_qualified": True,
            "coordinate_physics_qualified": True,
            "coverage": {"4": 32060, "6": 32060},
            "failed_mode_count": 0,
            "maximum_original_relative": 1e-12,
            "actual_action_RHS_adjoint_metrics": {
                "4": {"fixture": {"relative": 1e-12}},
                "6": {"fixture": {"relative": 1e-12}},
            },
            "physical_incident_metrics": [
                {"fixture": {"relative": 1e-12}},
                {"fixture": {"relative": 1e-12}},
            ],
            "oracle_numeric_recomputed": [
                {"checks": 1, "maximum_absolute": 1e-14},
                {"checks": 1, "maximum_absolute": 1e-14},
            ],
        },
    )
    spec["prerequisite_paths"] = {s: str(output / s) for s in bindings}
    return output, spec, bindings, publish


def test_actual_checker_writer_reopen_prerequisite(tmp_path, monkeypatch, directional):
    arrays, modes, producer, _ = local_fixture(tmp_path, monkeypatch)
    result = payload.check_local(component, producer, tmp_path, live_guard(), modes)
    assert result["status"] == "P2_SAVED_LOCAL_PASS"
    output, spec, bindings, publish = scientific_chain(tmp_path, monkeypatch)
    run = publish("p4_top_check", result)
    reopened = validate_stage(
        run,
        identity=scientific_identity(bindings["p4_top_check"]),
        statuses={"P2_SAVED_LOCAL_PASS"},
        expected_stage="p4_top_check",
    )
    assert reopened["metrics"]["qhat_alpha_actual"]["relative"] < 1e-11
    receiver.prerequisite("p4_top", output, spec)
    assert not np.allclose(arrays["solve_internal_rhs"], 0)
    # Unrelated document HEAD can change: exact tested numerical blobs are reused.
    publish(
        "control",
        {
            "status": "CONTROL_NATIVE_BOUNDARY_PASS_NO_VOLUME_FE",
            "native_control_complete": True,
        },
        source_sha="b" * 40,
    )
    receiver.prerequisite("p4_top", output, spec)


@pytest.mark.parametrize(
    "field",
    [
        "qhat_alpha",
        "affine_internal_rhs",
        "reduced_trace_matrix",
        "reduced_trace_rhs",
        "solve_internal_B",
        "trace_rhs",
        "saved_Bi",
        "saved_Dt",
        "port_internal_trace_correction",
    ],
)
def test_updated_hash_broken_consumer_rejected(
    tmp_path, monkeypatch, directional, field
):
    arrays, modes, producer, save = local_fixture(tmp_path, monkeypatch)
    arrays[field].flat[0] += 1e6
    save()  # Actual hash is deliberately updated: the equations still fail.
    result = payload.check_local(component, producer, tmp_path, live_guard(), modes)
    assert result["status"] == "P2_SAVED_LOCAL_FAIL"
    payload.atomic_json(tmp_path / "negative.json", result)
    assert json.loads((tmp_path / "negative.json").read_text())["status"].endswith(
        "FAIL"
    )


@pytest.mark.parametrize(
    "damage", ["partition", "p", "side", "key", "H", "missing-column", "witness", "q"]
)
def test_saved_local_identity_damage(tmp_path, monkeypatch, directional, damage):
    arrays, modes, producer, save = local_fixture(tmp_path, monkeypatch)
    if damage == "partition":
        arrays["interior_positions"][0] = arrays["interior_positions"][1]
    if damage == "p":
        arrays["degree"] = np.array(6)
    if damage == "side":
        arrays["side"] = np.array("bottom")
    if damage == "key":
        arrays["mode_keys"][0, 0] += 1
    if damage == "H":
        arrays["original_H"][0] *= 2
    if damage == "missing-column":
        arrays["saved_Bi"] = arrays["saved_Bi"][:, :-1]
    if damage == "witness":
        arrays["witness_mode_index"] = np.array(2)
    if damage == "q":
        arrays["quadrature_degree"] = np.array(30)
    save()
    with pytest.raises(ValueError, match="W1_"):
        payload.check_local(component, producer, tmp_path, live_guard(), modes)


@pytest.mark.parametrize("stage", ["control", "boundary_check"])
def test_failed_supervision_pass_tag_refused(tmp_path, monkeypatch, stage):
    output, spec, _, publish = scientific_chain(tmp_path, monkeypatch)
    receiver.prerequisite("p6_top", output, spec)
    result = json.loads((output / stage / "component_result.json").read_text())
    publish(
        stage,
        result,
        {
            "classification": "RSS_HARD_STOP",
            "leader_exit_code": 137,
            "descendants_cleared": False,
            "remaining_child_pids": [123],
            "sampled_process_tree_swap_peak_bytes": 0,
        },
    )
    with pytest.raises(ValueError, match="SUPERVISION"):
        receiver.prerequisite("p6_top", output, spec)


@pytest.mark.parametrize(
    "damage", ["source", "window", "original", "dat", "hash", "raw", "missing"]
)
def test_prerequisite_identity_and_reopened_damage(tmp_path, monkeypatch, damage):
    output, spec, _, _ = scientific_chain(tmp_path, monkeypatch)
    p = output / "boundary_check/evidence.json"
    value = json.loads(p.read_text())
    if damage == "source":
        value["scientific_identity"]["receiver_files"]["fake"] = "bad"
    if damage == "window":
        value["scientific_identity"]["window_sha256"] = "bad"
    if damage == "original":
        value["scientific_identity"]["original_inputs"]["manifest_sha256"] = "bad"
    if damage == "hash":
        value["component"]["sha256"] = "bad"
    if damage == "raw":
        Path(value["raw_files"][0]["path"]).write_text("damaged")
    if damage == "dat":
        (output / "boundary_check/fixture.dat").write_text("other-input")
    if damage == "missing":
        p.unlink()
    else:
        atomic_json(p, value)
    # Even if receipt hash is updated, its underlying evidence must qualify.
    if p.exists():
        r = output / "boundary_check/receiver_result.json"
        row = json.loads(r.read_text())
        row["evidence_sha256"] = sha(p)
        atomic_json(r, row)
    with pytest.raises((ValueError, FileNotFoundError)):
        receiver.prerequisite("p6_top", output, spec)


def oracle_fixture():
    return {
        "status": "ORACLE_INTERVAL_PASS",
        "scope": {
            "maximum_abs_omega": 56,
            "maximum_degree": 6,
            "precision": [80, 110],
            "Gauss_points": 64,
        },
        "checks": [
            {
                "omega": 0.0,
                "analytic_values": [[1 / (j + 1), 0.0] for j in range(7)],
                "Decimal80_values": [[str(1 / (j + 1)), "0"] for j in range(7)],
                "Decimal110_Gauss64_values": [
                    [str(1 / (j + 1)), "0"] for j in range(7)
                ],
            }
        ],
    }


def test_oracle_numeric_damage_not_tag(tmp_path, monkeypatch, directional):
    document = oracle_fixture()
    assert oracle_checks(document, [0.0])["status"] == "ORACLE_INTERVAL_PASS"
    document["checks"][0]["analytic_values"][3][0] += 0.1
    assert oracle_checks(document, [0.0])["status"] == "ORACLE_ACCURACY_UNRESOLVED"
    producer = tmp_path / "producer"
    producer.mkdir()
    receipts = []
    for p in (4, 6):
        path = producer / f"oracle_p{p}.json"
        payload.atomic_json(path, document)
        receipts.append(file_receipt(path))
    payload.atomic_json(producer / "chunk_index.json", {"chunks": []})
    payload.atomic_json(
        producer / "component_result.json",
        {"chunks": [], "oracle_receipts": receipts, "incident_receipts": []},
    )
    monkeypatch.setattr(payload, "layout_for", lambda *a: (None, None))
    monkeypatch.setattr(payload, "required_oracle_frequencies", lambda *a: [0.0])
    result = payload.check_boundary(live_guard(), [], component, producer, tmp_path)
    payload.atomic_json(tmp_path / "oracle_result.json", result)
    assert result["status"] == "ORACLE_ACCURACY_UNRESOLVED"
    document["scope"]["maximum_abs_omega"] = 57
    with pytest.raises(ValueError):
        oracle_checks(document, [0.0])


def test_numpy_scalar_writer_and_nonfinite_rollback(tmp_path):
    path = tmp_path / "writer.json"
    payload.atomic_json(
        path,
        {
            "boolean": np.bool_(True),
            "integer": np.int64(7),
            "floating": np.float64(0.125),
        },
    )
    previous = path.read_bytes()
    assert json.loads(previous) == {"boolean": True, "integer": 7, "floating": 0.125}
    for bad in (float("nan"), np.float64("inf"), complex(1, 2), np.ones(2)):
        with pytest.raises((TypeError, ValueError)):
            payload.atomic_json(path, {"bad": bad})
        assert path.read_bytes() == previous


def test_coordinate_sign_origin_and_incident_rhs(directional):
    k0 = 2 * np.pi / 0.7
    angle = np.deg2rad(1)
    kout = np.array([k0 * np.cos(angle), 0, k0 * np.sin(angle)])
    kb = np.array(
        [
            kout[0],
            0,
            -np.sqrt(
                (k0 * (0.9998851703688496 + 4.3236152269189515e-6j)) ** 2 - kout[0] ** 2
            ),
        ]
    )
    e = np.array([0, 1, 0])
    modes = [
        {"side": s, "m": 0, "n": 0, "polarization": "s", "k_vector": k, "e_vector": e}
        for s, k in (("top", kout), ("bottom", kb))
    ]
    # Independent fixture integration of two constant tangential polynomials.
    base = np.array([[1 + 0.3j, 0.5 - 0.2j], [-0.7 + 0.1j, 0.4 + 0.9j]])

    def actual(side, k, J, pos):
        plane = pos.copy()
        plane[2] += J[2, 2] if side == "top" else 0
        return base * np.exp(1j * (k @ plane))

    poly = SimpleNamespace(
        integral_native=lambda side, k, J, pos, q: actual(side, k, J, pos)
    )
    oracle = SimpleNamespace(
        facet_identity=lambda *a: None,
        integrate_receiver_facet=lambda poly, side, k, J, pos, expected: actual(
            side, k, J, pos
        ),
    )
    origin = np.array([-3.0, -4.0, 120.0])
    J = np.diag([0.2, 4.0, 10.0])
    packet = component.incident_boundary_packet(poly, "top", modes, J, origin, oracle)
    metrics = incident_checks(packet, packet)
    assert all(m["relative"] < 1e-10 for m in metrics.values())
    for name in ("rhs_center", "rhs_modal", "background_rhs_center", "rhs_absolute"):
        broken = dict(packet)
        broken[name] = packet[name] * -1
        assert incident_checks(broken, packet)[name]["relative"] > 1
    for name in ("k_in", "reference_plane_nm", "origin_absolute"):
        broken = dict(packet)
        broken[name] = packet[name] + 1
        with pytest.raises(ValueError):
            incident_checks(broken, packet)
    for name in (
        "rhs_center",
        "rhs_absolute",
        "rhs_modal",
        "background_rhs_center",
        "background_rhs_absolute",
    ):
        np.testing.assert_allclose(
            packet[name], packet["rhs_reference"], rtol=1e-11, atol=1e-12
        )
    assert abs(packet["background_interface_curl_jump"]) < 1e-12
    center = actual("top", kout, J, origin)[None, :, :]
    absolute = actual("top", kout, J, origin + np.array([25.0, 12.5, 0]))[None, :, :]
    t = np.cross(1j * np.cross(kout, e), [0, 0, 1])[None, :]
    args = (
        kout[None, :],
        e[None, :],
        t,
        np.array([1250.0]),
        np.array([0.7 + 0.3j]),
        np.vstack((origin, origin + [25, 12.5, 0])),
        [130, -10],
    )
    assert (
        max(v["relative"] for v in coordinate_checks(center, absolute, *args).values())
        < 1e-11
    )
    for bad in (center, center * np.exp(-1j * (kout @ np.array([25, 12.5, 0])))):
        assert (
            max(v["relative"] for v in coordinate_checks(center, bad, *args).values())
            > 1e-4
        )
    wrong = list(args)
    wrong[-1] = [120, -10]
    with pytest.raises(ValueError):
        coordinate_checks(center, absolute, *wrong)
    wrong_modes = [dict(m) for m in modes]
    wrong_modes[0]["k_vector"] = kout.copy()
    wrong_modes[0]["k_vector"][1] = 0.1
    with pytest.raises(ValueError):
        component.physical_incidence(wrong_modes)


def test_export_patch_reuses_original_solves():
    source = subprocess.check_output(
        ["git", "show", receiver.MATH_COMMIT + ":src/solvers/task40_w1_local_probe.py"],
        cwd=ROOT,
        text=True,
    )
    patched = export_source(source)

    def solves(s):
        return sum(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "lu_solve"
            for n in ast.walk(ast.parse(s))
        )

    assert solves(source) == solves(patched)
    assert '"qhat_alpha": qhat_alpha' in patched and '"solve_Vit": solve_Vit' in patched
    with pytest.raises(ValueError, match="BASE_CONTEXT_CHANGED"):
        export_source(
            source.replace("local_integral_calls = 0", "local_integral_calls = 1")
        )


def test_B_window_and_control_budget(tmp_path):
    proof = tmp_path / "A.json"
    atomic_json(proof, {"qualified": True})
    spec = {"window_path": str(tmp_path / "B.json"), "A_qualification_path": str(proof)}
    original = {"received": True, "manifest_sha256": "fixture-only"}
    receiver.prepare_B_window(spec, original, launch_origin=time.monotonic() - 20)
    initial = Path(spec["window_path"]).read_bytes()
    window = json.loads(initial)
    assert 10770 < receiver.remaining(window) < 10790
    receiver.prepare_B_window(spec, original)
    assert Path(spec["window_path"]).read_bytes() == initial
    assert receiver.stage_cap(10000, 7150, "control") == 50
    assert receiver.stage_cap(2000, 0, "boundary") == 200
    with pytest.raises(ValueError, match="CHANGED"):
        receiver.prepare_B_window(spec, {**original, "manifest_sha256": "wrong"})
    atomic_json(proof, {"qualified": "changed"})
    with pytest.raises(ValueError, match="CHANGED"):
        receiver.prepare_B_window(spec, original)


@pytest.mark.parametrize(
    "degree,side", [(4, "top"), (4, "bottom"), (6, "top"), (6, "bottom")]
)
def test_both_orders_and_sides_complete_saved_equations(
    tmp_path, monkeypatch, directional, degree, side
):
    arrays, modes, producer, _ = local_fixture(tmp_path, monkeypatch, degree, side)
    result = payload.check_local(
        component, producer, tmp_path, live_guard(f"p{degree}_{side}_check"), modes
    )
    assert result["status"] == "P2_SAVED_LOCAL_PASS"
    assert result["checker_factor_calls"] == result["checker_solve_calls"] == 0
    assert len(arrays["interior_positions"]) == (108 if degree == 4 else 450)


def test_missing_original_does_not_start_B_clock_or_native(tmp_path, monkeypatch):
    monkeypatch.setattr(receiver.subprocess, "check_output", lambda *a, **kw: b"")
    monkeypatch.setattr(
        receiver,
        "validate_originals",
        lambda spec: {"received": False, "status": "NOT_RUN_INPUT_UNAVAILABLE"},
    )
    spec = {
        "A_qualification_path": str(tmp_path / "not-yet-proof"),
        "window_path": str(tmp_path / "B.json"),
    }
    result = receiver.durable_w1(spec)
    assert result == {
        "scope": "B_NOT_STARTED_INPUT_UNAVAILABLE",
        "socket": None,
        "session": None,
        "output": None,
    }
    assert not Path(spec["window_path"]).exists()


def test_A_qualification_source_junit_and_resource_constraints(tmp_path):
    required = [
        "test_actual_checker_writer_reopen_prerequisite",
        "test_updated_hash_broken_consumer_rejected",
        "test_failed_supervision_pass_tag_refused",
        "test_oracle_numeric_damage_not_tag",
        "test_coordinate_sign_origin_and_incident_rhs",
        "test_numpy_scalar_writer_and_nonfinite_rollback",
        "test_export_patch_reuses_original_solves",
        "test_B_window_and_control_budget",
    ]
    junit = tmp_path / "fixture.xml"
    junit.write_text(
        "<testsuite>"
        + "".join('<testcase name="' + name + '"/>' for name in required)
        + "</testsuite>"
    )
    summary = tmp_path / "summary.json"
    atomic_json(
        summary,
        {
            "classification": "COMPLETED",
            "leader_exit_code": 0,
            "descendants_cleared": True,
            "remaining_child_pids": [],
            "sampled_process_tree_swap_peak_bytes": 0,
            "rss_hard_limit_bytes": 2 * 2**30,
            "sampled_process_tree_rss_peak_bytes": 1000000,
        },
    )
    proof = tmp_path / "proof.json"
    sources = {p: sha(ROOT / p) for p in receiver.RECEIVER_FILES}
    value = {
        "schema": "w1-A-qualification.v1",
        "scope": "PURE_LOGIC_ONLY",
        "receiver_files": sources,
        "supervision": file_receipt(summary),
        "junit": file_receipt(junit),
        "test_source_files": [file_receipt(Path(__file__))],
    }
    atomic_json(proof, value)
    assert validate_A(proof, sources)["scope"] == "PURE_LOGIC_ONLY"
    with pytest.raises(ValueError):
        validate_A(proof, {**sources, "missing-source": "bad"})
    for damage in ("test-hash", "missing-test", "swap", "cap"):
        old_summary = summary.read_bytes()
        old_junit = junit.read_bytes()
        changed = json.loads(json.dumps(value))
        if damage == "test-hash":
            changed["test_source_files"][0]["sha256"] = "bad"
        if damage == "missing-test":
            junit.write_text('<testsuite><testcase name="one"/></testsuite>')
            changed["junit"] = file_receipt(junit)
        if damage in ("swap", "cap"):
            state = json.loads(old_summary)
            state[
                "sampled_process_tree_swap_peak_bytes"
                if damage == "swap"
                else "rss_hard_limit_bytes"
            ] = 1
            atomic_json(summary, state)
            changed["supervision"] = file_receipt(summary)
        atomic_json(proof, changed)
        with pytest.raises(ValueError):
            validate_A(proof, sources)
        summary.write_bytes(old_summary)
        junit.write_bytes(old_junit)


def test_all_new_inputs_use_shared_q_and_explicit_A(monkeypatch):
    from scripts.run_case import main
    from src.io.w1_receiver_contract import load_w1

    files = sorted((ROOT / "input/task042extra_feinn_5nm").glob("v26_w1_*.dat"))
    assert len(files) == 11
    specs = [load_w1(p) for p in files]
    assert len({s["window_path"] for s in specs}) == 1
    assert len({s["input_sha256"] for s in specs}) == 11
    assert all(
        s["quadrature_degree"] == 60 and s["A_qualification_path"] for s in specs
    )
    assert main([str(files[0]), "--validate-only"]) == 0


@pytest.mark.parametrize("damage", ["coverage", "mode-error", "RHS", "oracle"])
def test_numerically_failed_P1_resealed_PASS_is_refused(tmp_path, monkeypatch, damage):
    output, spec, _, publish = scientific_chain(tmp_path, monkeypatch)
    result = json.loads((output / "boundary_check/component_result.json").read_text())
    if damage == "coverage":
        result["coverage"]["6"] -= 1
    if damage == "mode-error":
        result["maximum_original_relative"] = 0.2
    if damage == "RHS":
        result["physical_incident_metrics"][0]["fixture"]["relative"] = 0.1
    if damage == "oracle":
        result["oracle_numeric_recomputed"][0]["maximum_absolute"] = 0.1
    publish("boundary_check", result)
    with pytest.raises(ValueError, match="W1_P1_"):
        receiver.prerequisite("p6_top", output, spec)
