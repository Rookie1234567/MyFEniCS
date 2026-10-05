"""Serial W1 receiver payload and saved checker, in an isolated frozen ABI.

Only bootstrap is stdlib. Numerical definitions reside in src/solvers; the
original native module is selected by the hash-bound source snapshot.
"""

import argparse
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def atomic_json(path, value):
    module = load_file(
        "_w1_finite_json", Path(__file__).resolve().parents[2] / "src/io/finite_json.py"
    )
    return module.atomic_json(path, value)


def atomic_arrays(path, arrays, *, compressed=False):
    import numpy as np

    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as out:
        writer = np.savez_compressed if compressed else np.savez
        writer(out, **arrays)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    with np.load(path, allow_pickle=False) as reopened:
        if set(reopened.files) != set(arrays):
            raise ValueError("W1_ATOMIC_ARRAY_REOPEN")
        for name, value in arrays.items():
            if not np.array_equal(reopened[name], value):
                raise ValueError("W1_ATOMIC_ARRAY_REOPEN:" + name)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def file_receipt(path):
    path = Path(path).resolve()
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def checked_receipt(receipt, parent):
    path = Path(receipt["path"])
    if (
        path.is_symlink()
        or not path.resolve().is_relative_to(Path(parent).resolve())
        or file_receipt(path) != {k: receipt[k] for k in ("path", "bytes", "sha256")}
    ):
        raise ValueError("W1_SAVED_RECEIPT_SCOPE_OR_HASH")
    return path


def required_oracle_frequencies(modes, layout):
    from src.solvers.directional_boundary import zvalue
    import numpy as np

    widths = [layout.x[101] - layout.x[100], layout.y[2] - layout.y[1]]
    values = [
        np.array([zvalue(m["k_vector"][axis]).real * widths[axis] for m in modes])
        for axis in (0, 1)
    ]
    selected = {0.0}
    for v in values:
        selected.update(float(value) for value in v)
    return sorted(selected)


def guard(binding):
    import datetime

    left = binding["window"]["deadline_monotonic"] - time.monotonic()
    utc_left = (
        datetime.datetime.fromisoformat(binding["window"]["deadline_utc"])
        - datetime.datetime.now(datetime.timezone.utc)
    ).total_seconds()
    if abs(left - utc_left) > 5:
        raise RuntimeError("TIMEBASE_INCONSISTENCY")
    if min(left, binding["stage_deadline_monotonic"] - time.monotonic()) <= 150:
        raise TimeoutError("W1_SAVE_RESERVE_REACHED")


def numeric_runtime():
    import numpy as np
    import basix
    from mpi4py import MPI
    from petsc4py import PETSc

    if PETSc.ScalarType is not np.complex128 or MPI.COMM_WORLD.size != 1:
        raise ValueError("W1_COMPLEX128_MPI1_REQUIRED")
    if any(
        os.environ.get(k) != "1"
        for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("W1_MATH_THREADS1_REQUIRED")
    if "torch" in sys.modules:
        raise ValueError("W1_FE_MUST_NOT_IMPORT_TORCH")
    return {
        "python": sys.executable,
        "basix": basix.__version__,
        "petsc": PETSc.Sys.getVersion(),
        "scalar": str(np.dtype(PETSc.ScalarType)),
        "int_type": str(np.dtype(PETSc.IntType)),
        "MPI": 1,
        "math_threads": 1,
        "Torch_imported": False,
    }


def source_modules(root, snapshot, binding):
    contract = load_file("_w1_contract", root / "src/io/w1_receiver_contract.py")
    manifest = json.loads(Path(binding["contract_source_manifest_path"]).read_text())
    if (
        manifest["commit"] != contract.MATH_COMMIT
        or contract.digest(binding["contract_source_manifest_path"])
        != binding["source_manifest_sha256"]
    ):
        raise ValueError("W1_FROZEN_SOURCE_IDENTITY")
    for row in manifest["files"]:
        path = snapshot / row["path"]
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != row["bytes"]
            or contract.digest(path) != row["sha256"]
        ):
            raise ValueError("W1_FROZEN_FILE_CHANGED:" + row["path"])
    for name, expected in binding["receiver_files"].items():
        if contract.digest(root / name) != expected:
            raise ValueError("W1_RECEIVER_SOURCE_CHANGED:" + name)
    # No current src package has been imported at this point. Back-end src
    # imports come exclusively from the read-only frozen snapshot.
    sys.path.insert(0, str(snapshot))
    component = load_file(
        "_w1_component", root / "src/solvers/w1_boundary_components.py"
    )
    # Explicitly hash-bound exports-only overlay; immutable snapshot untouched.
    patch = load_file("_w1_export_patch", root / "src/solvers/w1_local_export_patch.py")
    patched_path = Path(binding["run_path"]) / "local_probe_exports.py"
    receipt = patch.materialize_export_module(
        snapshot / "src/solvers/task40_w1_local_probe.py", patched_path
    )
    atomic_json(Path(binding["run_path"]) / "math_export_overlay.json", receipt)
    load_file("src.solvers.task40_w1_local_probe", patched_path)
    return contract, component


def layout_for(modes, degree):
    import basix
    from src.solvers.directional_boundary import BoundaryLayout, FacetPolynomial
    from benchmarks.run_task40_w1_boundary_probe import (
        _floquet_phases,
        _proportional_axis,
    )

    phase_x, phase_y, facts = _floquet_phases(modes)
    phases = (phase_x, phase_y)
    x = _proportional_axis([-25.0, -8.5, 0.0, 8.5, 25.0], 272)
    if len(x) != 273:
        raise ValueError("W1_ORIGINAL_PROPORTIONAL_AXIS")
    y = _proportional_axis([-12.5, -6.25, 0.0, 6.25, 12.5], 4)
    element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        degree,
        basix.LagrangeVariant.legendre,
    )
    polynomial = FacetPolynomial(element)
    return BoundaryLayout(x, y, polynomial, phases), facts


def oracle_module(root):
    # This provider was independently qualified in V23. Its bytes are part
    # of receiver_files; no implementation is copied into the native cache.
    load_file(
        "src.solvers.analytic_face_ports", root / "src/solvers/analytic_face_ports.py"
    )
    return load_file(
        "_w1_interval_oracle", root / "src/solvers/interval_facet_moments.py"
    )


def qualify_oracle(root, modes, layout, oracle, binding):
    import numpy as np

    decimal = load_file(
        "_w1_decimal_oracle", root / "benchmarks/portable_facet_oracle.py"
    )
    from src.solvers.directional_boundary import zvalue

    widths = [layout.x[101] - layout.x[100], layout.y[2] - layout.y[1]]
    frequencies = [
        np.asarray([zvalue(m["k_vector"][axis]).real * widths[axis] for m in modes])
        for axis in (0, 1)
    ]
    selected = required_oracle_frequencies(modes, layout)
    checks = []
    for omega in sorted(selected):
        guard(binding)
        if abs(omega) > 56 or not np.isfinite(omega):
            return {
                "status": "ORACLE_ACCURACY_UNRESOLVED",
                "reason": "original frequency outside previously qualified fixed range",
            }
        a = oracle.unit_interval_moments(omega, 6)
        b, bstrings = decimal.moments(omega, 6, 80)
        c, cstrings = decimal.moments(omega, 6, 110, direct_quadrature=True)
        terms = [float(np.max(abs(a - b))), float(np.max(abs(b - c)))]
        checks.append(
            {
                "omega": omega,
                "analytic_Decimal80_absolute": terms[0],
                "Decimal80_Decimal110_Gauss64_absolute": terms[1],
                "pass": max(terms) <= 1e-12,
                "analytic_values": [[float(v.real), float(v.imag)] for v in a],
                "Decimal80_values": bstrings,
                "Decimal110_Gauss64_values": cstrings,
            }
        )
    return {
        "status": "ORACLE_INTERVAL_PASS"
        if all(r["pass"] for r in checks)
        else "ORACLE_ACCURACY_UNRESOLVED",
        "checks": checks,
        "scope": {
            "maximum_abs_omega": 56,
            "maximum_degree": 6,
            "precision": [80, 110],
            "Gauss_points": 64,
        },
        "maximum_half_phase_span": max(abs(a).max() for a in frequencies) / 2,
        "fixed_reference": "qualified Fourier-Legendre plus Decimal80/110 fixed64-point independent crosscheck",
    }


def boundary_worker(root, binding, modes, component, run):
    """Bounded batches of full native columns, no mode-square array."""
    import numpy as np
    from src.solvers.directional_boundary import zvalue

    oracle = oracle_module(root)
    rows, all_pass, oracle_receipts, incident_receipts = [], True, [], []
    q = binding["contract"]["quadrature_degree"]
    kvec = np.asarray(
        [[zvalue(v) for v in m["k_vector"]] for m in modes], np.complex128
    )
    shift, reverse = component.centered_phase_pair(kvec, [25, 12.5, 0])
    if np.max(abs(shift * reverse - 1)) > 1e-12:
        raise ValueError("W1_CENTERED_LEDGER_PHASE_ROUNDTRIP")
    for degree in (4, 6):
        layout, floquet = layout_for(modes, degree)
        oracle_gate = qualify_oracle(root, modes, layout, oracle, binding)
        atomic_json(run / f"oracle_p{degree}.json", oracle_gate)
        oracle_receipts.append(file_receipt(run / f"oracle_p{degree}.json"))
        if oracle_gate["status"] != "ORACLE_INTERVAL_PASS":
            return {"status": "ORACLE_ACCURACY_UNRESOLVED", "chunks": rows}
        polynomial = layout.polynomial
        actions = component.probe_actions(layout, modes, q)
        reference_action = {
            name: np.zeros_like(actions[name])
            for name in (
                "components",
                "recover",
                "apply",
                "adjoint",
                "modal_rhs",
                "physical_rhs",
            )
        }
        for side in ("top", "bottom"):
            indices = [i for i, row in enumerate(modes) if row["side"] == side]
            folder = run / f"p{degree}_{side}"
            folder.mkdir()
            J = np.diag(
                [layout.x[101] - layout.x[100], layout.y[2] - layout.y[1], 10.0]
            )
            origin = np.array(
                [layout.x[100], layout.y[1], 120.0 if side == "top" else -10.0]
            )
            if side == "top":
                packet = component.incident_boundary_packet(
                    polynomial, side, modes, J, origin, oracle, q
                )
                incident_receipts.append(
                    atomic_arrays(run / f"incident_p{degree}.npz", packet)
                )
            for start in range(0, len(indices), 64):
                guard(binding)
                subset = indices[start : start + 64]
                candidate, reference, absolute = [], [], []
                for index in subset:
                    k = kvec[index]
                    candidate.append(polynomial.integral_native(side, k, J, origin, q))
                    absolute.append(
                        polynomial.integral_native(
                            side, k, J, origin + np.array([25, 12.5, 0]), q
                        )
                    )
                    identity = oracle.facet_identity(polynomial, side, k, J, origin)
                    reference.append(
                        oracle.integrate_receiver_facet(
                            polynomial, side, k, J, origin, expected=identity
                        )
                    )
                arrays = {
                    "candidate": np.array(candidate),
                    "reference": np.array(reference),
                    "absolute_candidate": np.array(absolute),
                    "origins": np.array([origin, origin + np.array([25, 12.5, 0])]),
                    "reference_planes": np.array([130, -10]),
                    "J": J,
                    "alpha": actions["alpha"][subset],
                    "mode_indices": np.array(subset),
                    "k": kvec[subset],
                    "e": np.array(
                        [[zvalue(v) for v in modes[i]["e_vector"]] for i in subset]
                    ),
                    "traction": np.array(
                        [
                            [zvalue(v) for v in modes[i]["traction_vector"]]
                            for i in subset
                        ]
                    ),
                    "H": np.array([modes[i]["projection_denominator"] for i in subset]),
                    "quadrature_degree": np.array(q),
                    "degree": np.array(degree),
                }
                receipt = atomic_arrays(folder / f"{start:05d}.npz", arrays)
                component.reference_actions(
                    layout,
                    modes,
                    arrays["reference"],
                    subset,
                    actions,
                    reference_action,
                )
                for a, b in zip(arrays["candidate"], arrays["reference"], strict=True):
                    all_pass &= component.relative_terms(a, b)["relative"] <= 1e-10
                rows.append(
                    {**receipt, "degree": degree, "side": side, "mode_indices": subset}
                )
                atomic_json(
                    run / "chunk_index.json",
                    {"chunks": rows, "committed_chunks": len(rows)},
                )
        action_receipt = atomic_arrays(
            run / f"actions_p{degree}.npz",
            {
                **actions,
                **{
                    "reference_" + name: value
                    for name, value in reference_action.items()
                },
            },
        )
        atomic_json(run / f"actions_p{degree}.json", action_receipt)
        del layout, polynomial, actions, reference_action
        gc.collect()
    return {
        "status": "BOUNDARY_WORKER_PASS_PENDING_CHECKER"
        if all_pass
        else "Q60_NATIVE_INTEGRAL_FAIL",
        "chunks": rows,
        "oracle_receipts": oracle_receipts,
        "incident_receipts": incident_receipts,
        "consumer_quadrature": component.consumers(q),
        "full_native_columns": True,
        "floquet": floquet,
        "physical_incident_rhs_qualified": False,
        "PDE_solved": False,
    }


def check_boundary(binding, modes, component, producer, run):
    import numpy as np
    from src.solvers.directional_boundary import zvalue

    index = json.loads((producer / "chunk_index.json").read_text())
    equations = load_file(
        "_w1_saved_equations",
        Path(__file__).resolve().parents[2] / "src/solvers/w1_saved_equations.py",
    )
    producer_result = json.loads((producer / "component_result.json").read_text())
    if index["chunks"] != producer_result["chunks"]:
        raise ValueError("W1_SAVED_CHUNK_INDEX_CHANGED")
    raw_receipts = (
        list(producer_result["chunks"])
        + list(producer_result["oracle_receipts"])
        + list(producer_result["incident_receipts"])
    )
    oracle_gates = []
    for receipt in producer_result["oracle_receipts"]:
        checked_receipt(receipt, producer)
        document = json.loads(Path(receipt["path"]).read_text())
        oracle_gates.append(
            equations.oracle_checks(
                document,
                required_oracle_frequencies(
                    modes, layout_for(modes, int(Path(receipt["path"]).stem[-1]))[0]
                ),
            )
        )
    all_pass = (
        all(g["status"] == "ORACLE_INTERVAL_PASS" for g in oracle_gates)
        and len(oracle_gates) == 2
    )
    if not all_pass:
        return {
            "status": "ORACLE_ACCURACY_UNRESOLVED",
            "oracle_numeric_recomputed": oracle_gates,
            "coverage_complete": False,
            "physical_incident_rhs_qualified": False,
            "raw_receipts": raw_receipts,
        }
    oracle = oracle_module(Path(__file__).resolve().parents[2])
    coverage, diagnostics = {4: [], 6: []}, []
    action_states, reference_states, action_metrics, layouts = {}, {}, {}, {}
    for p in (4, 6):
        layouts[p], _ = layout_for(modes, p)
        path = producer / f"actions_p{p}.npz"
        receipt = json.loads((producer / f"actions_p{p}.json").read_text())
        raw_receipts.extend([receipt, file_receipt(producer / f"actions_p{p}.json")])
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt["sha256"]:
            raise ValueError("W1_SAVED_ACTION_HASH_CHANGED")
        with np.load(path, allow_pickle=False) as saved:
            action_states[p] = {
                name: saved[name]
                for name in (
                    "trace",
                    "dual",
                    "alpha",
                    "components",
                    "recover",
                    "apply",
                    "adjoint",
                    "modal_rhs",
                    "physical_alpha",
                    "physical_rhs",
                )
            }
        physical_alpha = component.physical_incidence(modes)[3]
        if not np.array_equal(action_states[p]["physical_alpha"], physical_alpha):
            raise ValueError("W1_ACTION_ACTUAL_PHYSICAL_RHS_IDENTITY")
        reference_states[p] = {
            name: np.zeros_like(action_states[p][name])
            for name in (
                "components",
                "recover",
                "apply",
                "adjoint",
                "modal_rhs",
                "physical_rhs",
            )
        }
    for row in index["chunks"]:
        guard(binding)
        path = Path(row["path"])
        if (
            path.parent.parent != producer
            or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]
        ):
            raise ValueError("W1_SAVED_CHUNK_HASH_OR_PATH")
        with np.load(path, allow_pickle=False) as raw:
            if (
                int(raw["quadrature_degree"]) != 60
                or int(raw["degree"]) != row["degree"]
            ):
                raise ValueError("W1_SAVED_CONSUMER_Q_OR_P")
            if list(raw["mode_indices"]) != row["mode_indices"]:
                raise ValueError("W1_SAVED_KEY_ORDER")
            component.reference_actions(
                layouts[row["degree"]],
                modes,
                raw["reference"],
                row["mode_indices"],
                action_states[row["degree"]],
                reference_states[row["degree"]],
            )
            for j, mode_index in enumerate(row["mode_indices"]):
                m = modes[mode_index]
                if (
                    m["side"] != row["side"]
                    or float(raw["H"][j]) != m["projection_denominator"]
                ):
                    raise ValueError("W1_ORIGINAL_H_OR_SIDE_CHANGED")
                for field, source in (
                    ("k", "k_vector"),
                    ("e", "e_vector"),
                    ("traction", "traction_vector"),
                ):
                    expected = np.array([zvalue(v) for v in m[source]])
                    if not np.array_equal(raw[field][j], expected):
                        raise ValueError("W1_PHYSICAL_MODE_CHANGED")
                a, b = raw["candidate"][j], raw["reference"][j]
                layout = layouts[row["degree"]]
                expected_origin = np.array(
                    [layout.x[100], layout.y[1], 120 if row["side"] == "top" else -10]
                )
                expected_J = np.diag(
                    [layout.x[101] - layout.x[100], layout.y[2] - layout.y[1], 10]
                )
                if not np.array_equal(
                    raw["origins"][0], expected_origin
                ) or not np.array_equal(raw["J"], expected_J):
                    raise ValueError("W1_SAVED_ACTUAL_FACE_GEOMETRY")
                reference_identity = oracle.facet_identity(
                    layout.polynomial,
                    row["side"],
                    raw["k"][j],
                    expected_J,
                    expected_origin,
                )
                rebuilt_reference = oracle.integrate_receiver_facet(
                    layout.polynomial,
                    row["side"],
                    raw["k"][j],
                    expected_J,
                    expected_origin,
                    expected=reference_identity,
                )
                e, t, h = raw["e"][j, :2], raw["traction"][j, :2], float(raw["H"][j])
                ba, bb = a @ -t, b @ -t
                da, db = (a @ e).conj() / h, (b @ e).conj() / h
                metrics = {
                    "integral": component.relative_terms(a, b),
                    "saved_reference_recomputed": component.relative_terms(
                        b, rebuilt_reference
                    ),
                    "B": component.relative_terms(ba, bb),
                    "D_original_H": component.relative_terms(da, db),
                }
                coordinate = equations.coordinate_checks(
                    raw["candidate"][j : j + 1],
                    raw["absolute_candidate"][j : j + 1],
                    raw["k"][j : j + 1],
                    raw["e"][j : j + 1],
                    raw["traction"][j : j + 1],
                    raw["H"][j : j + 1],
                    raw["alpha"][j : j + 1],
                    raw["origins"],
                    raw["reference_planes"],
                )
                metrics.update(
                    {"coordinate_" + name: value for name, value in coordinate.items()}
                )
                # Three fixed nonzero native directions; same complete columns.
                for direction in range(3):
                    v = np.asarray(
                        np.exp((0.19 + 0.07 * direction) * 1j * np.arange(len(ba))),
                        np.complex128,
                    )
                    metrics[f"B_action_{direction}"] = component.relative_terms(
                        ba @ v, bb @ v
                    )
                    metrics[f"D_action_{direction}"] = component.relative_terms(
                        da @ v, db @ v
                    )
                passed = all(value["relative"] <= 1e-10 for value in metrics.values())
                all_pass &= passed
                diagnostics.append(
                    {
                        "degree": row["degree"],
                        "key": [m["side"], m["m"], m["n"], m["polarization"]],
                        "mode_index": mode_index,
                        "metrics": metrics,
                        "pass": passed,
                    }
                )
                coverage[row["degree"]].append(mode_index)
    complete = all(
        sorted(indices) == list(range(32060)) for indices in coverage.values()
    )
    all_pass &= complete
    for p in (4, 6):
        action_metrics[p] = {
            name: component.relative_terms(
                action_states[p][name], reference_states[p][name]
            )
            for name in reference_states[p]
        }
        lhs = np.vdot(action_states[p]["dual"], action_states[p]["apply"])
        rhs = np.vdot(action_states[p]["adjoint"], action_states[p]["trace"])
        action_metrics[p]["real_frozen_action_adjoint"] = component.relative_terms(
            lhs, rhs
        )
        all_pass &= all(
            value["relative"] <= 1e-10 for value in action_metrics[p].values()
        )
    # All denominators and negatives remain in the ignored full record.
    atomic_json(run / "all_mode_denominators.json", diagnostics)
    incident_metrics = []
    for receipt in producer_result["incident_receipts"]:
        checked_receipt(receipt, producer)
        with np.load(receipt["path"], allow_pickle=False) as data:
            kin, kout, e, alpha = component.physical_incidence(modes)
            if (
                not all(
                    np.array_equal(data[name], value)
                    for name, value in (
                        ("k_in", kin),
                        ("k_out", kout),
                        ("e_in", e),
                        ("physical_alpha", alpha),
                    )
                )
                or float(data["reference_plane_nm"]) != 130
                or not np.array_equal(
                    data["origin_absolute"] - data["origin_center"], [25, 12.5, 0]
                )
            ):
                raise ValueError("W1_PHYSICAL_INCIDENT_SAVED_IDENTITY")
            p = int(Path(receipt["path"]).stem[-1])
            layout = layouts[p]
            J = np.diag([layout.x[101] - layout.x[100], layout.y[2] - layout.y[1], 10])
            pos = np.array([layout.x[100], layout.y[1], 120])
            rebuilt = component.incident_boundary_packet(
                layout.polynomial, "top", modes, J, pos, oracle, 60
            )
            if not np.array_equal(data["origin_center"], pos):
                raise ValueError("W1_ACTUAL_INCIDENT_FACE_GEOMETRY")
            metrics = equations.incident_checks(data, rebuilt)
            incident_metrics.append(metrics)
            all_pass &= all(m["relative"] <= 1e-10 for m in metrics.values())
    incident_ok = len(incident_metrics) == 2 and all(
        m["relative"] <= 1e-10 for row in incident_metrics for m in row.values()
    )
    all_pass &= incident_ok
    raw_receipts.append(file_receipt(run / "all_mode_denominators.json"))
    return {
        "status": "P1_Q60_FULL_MODE_PASS" if all_pass else "P1_Q60_FULL_MODE_FAIL",
        "coverage": {str(p): len(v) for p, v in coverage.items()},
        "coverage_complete": complete,
        "physical_incident_rhs_qualified": incident_ok,
        "physical_RHS_scope": "original 1degree/phi0/s incoming natural port load; full grating volume RHS NOT_RUN",
        "physical_incident_metrics": incident_metrics,
        "coordinate_physics_qualified": all(
            v["relative"] <= 1e-10
            for row in diagnostics
            for name, v in row["metrics"].items()
            if name.startswith("coordinate_")
        ),
        "oracle_numeric_recomputed": oracle_gates,
        "raw_receipts": raw_receipts,
        "actual_action_RHS_adjoint_metrics": {
            str(p): metrics for p, metrics in action_metrics.items()
        },
        "failed_mode_count": sum(not r["pass"] for r in diagnostics),
        "maximum_original_relative": max(
            v["relative"] for r in diagnostics for v in r["metrics"].values()
        ),
        "all_mode_denominators_sha256": hashlib.sha256(
            (run / "all_mode_denominators.json").read_bytes()
        ).hexdigest(),
        "consumer_quadrature": component.consumers(60),
        "PDE_solved": False,
    }


def check_local(component, producer, run, binding, modes=None):
    """Saved full original block equations; no factor or solve in the checker."""
    import numpy as np

    report = json.loads((producer / "component_result.json").read_text())
    guard(binding)
    if modes is None:
        raise ValueError("W1_TRUSTED_MODE_IDENTITY_REQUIRED")
    if (
        report["degree"] != int(binding["stage"][1])
        or report["side"] != binding["stage"].split("_")[1]
    ):
        raise ValueError("W1_LOCAL_STAGE_P_SIDE_IDENTITY")
    path = producer / "local_arrays.npz"
    if hashlib.sha256(path.read_bytes()).hexdigest() != report["raw"]["sha256"]:
        raise ValueError("W1_LOCAL_RAW_HASH_CHANGED")
    with np.load(path, allow_pickle=False) as raw:
        a = {k: raw[k] for k in raw.files}
    equations = load_file(
        "_w1_saved_equations",
        Path(__file__).resolve().parents[2] / "src/solvers/w1_saved_equations.py",
    )
    saved = equations.local_equations(a, report, modes)
    witness_index = int(a["witness_mode_index"])
    witness_mode = modes[witness_index]
    from src.solvers.directional_boundary import zvalue

    for field, original in (
        ("witness_mode_k", "k_vector"),
        ("witness_mode_e", "e_vector"),
        ("witness_mode_traction", "traction_vector"),
    ):
        expected = np.array([zvalue(z) for z in witness_mode[original]])
        if len(a[field]) == 2:
            expected = expected[:2]
        if not np.array_equal(a[field], expected):
            raise ValueError("W1_LOCAL_WITNESS_PHYSICAL_IDENTITY")
    if (
        witness_mode["side"] != report["side"]
        or float(a["witness_mode_projection_denominator"])
        != witness_mode["projection_denominator"]
    ):
        raise ValueError("W1_LOCAL_WITNESS_ORIGINAL_H_SIDE")
    from src.solvers.task40_w1_local_probe import _direct_full_basis_integral
    import basix

    p = report["degree"]
    element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        p,
        basix.LagrangeVariant.legendre,
    )
    integral, rule, weights = _direct_full_basis_integral(
        element, report["side"], a["witness_mode_k"], a["local_cell_coordinates"], 60
    )
    if not np.array_equal(
        rule, a["witness_direct_q60_rule_points"]
    ) or not np.array_equal(weights, a["witness_direct_q60_rule_weights"]):
        raise ValueError("W1_SAVED_DIRECT_Q60_RULE_MISMATCH")
    B = np.ascontiguousarray(integral @ -a["witness_mode_traction"])
    D = np.ascontiguousarray(
        (integral @ a["witness_mode_e"]).conj()
        / float(a["witness_mode_projection_denominator"])
    )
    orientation = int(a["local_cell_orientation"][0])
    element.T_apply(B, 1, orientation)
    element.T_apply(D, 1, orientation)
    direct_metrics = {
        "B": component.relative_terms(B, a["witness_candidate_B_native"]),
        "D": component.relative_terms(D, a["witness_candidate_D_native"]),
    }
    pos = np.flatnonzero(a["active_mode_indices"] == witness_index)
    if len(pos) != 1:
        raise ValueError("W1_LOCAL_WITNESS_KEY_COVERAGE")
    full_B, full_D = np.empty_like(B), np.empty_like(D)
    for positions, name in (
        (a["interior_positions"], "saved_Bi"),
        (a["trace_positions"], "saved_Bt"),
    ):
        full_B[positions] = a[name][pos[0]]
    for positions, name in (
        (a["interior_positions"], "saved_Di"),
        (a["trace_positions"], "saved_Dt"),
    ):
        full_D[positions] = a[name][pos[0]]
    direct_metrics.update(
        all_saved_B_columns=component.relative_terms(full_B, B),
        all_saved_D_columns=component.relative_terms(full_D, D),
    )
    passed = (
        all(value["relative"] <= 1e-10 for value in direct_metrics.values())
        and saved["pass"]
        and report["consumer_quadrature"] == component.consumers(60)
    )
    return {
        "status": "P2_SAVED_LOCAL_PASS" if passed else "P2_SAVED_LOCAL_FAIL",
        "metrics": saved["metrics"],
        "metric_limits": saved["limits"],
        "full_mode_count": saved["full_mode_count"],
        "raw_receipts": [report["raw"]],
        "independent_native_direct_q60": direct_metrics,
        "port_elimination_identity": saved["metrics"]["port_elimination_identity"],
        "checker_factor_calls": 0,
        "checker_solve_calls": 0,
        "manufactured_rhs_only": True,
        "full_target_MPC_qualified": False,
        "PDE_solved": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--frozen-source", type=Path, required=True)
    args = parser.parse_args(argv)
    origin = time.monotonic()
    root = Path(__file__).resolve().parents[2]
    binding = json.loads(args.binding.read_text())
    if binding["spec"].get("w1_receiver_schema") == 2:
        driver = load_file("_w28_driver", root / "src/runners/w1_versioned_payload.py")
        return driver.run_payload(
            root, args.frozen_source, binding, sys.modules[__name__]
        )
    if binding["stage"] == "input_recovery":
        contract = load_file("_w1_contract", root / "src/io/w1_receiver_contract.py")
        for name, expected in binding["receiver_files"].items():
            if contract.digest(root / name) != expected:
                raise ValueError("W1_RECOVERY_SOURCE_CHANGED")
        driver = load_file(
            "_w1_input_recovery", root / "src/runners/w1_input_recovery.py"
        )
        run = Path(binding["run_path"])
        guard(binding)
        result = driver.recover(
            args.frozen_source,
            binding,
            atomic_json=atomic_json,
            file_receipt=file_receipt,
        )
        result.update(
            receiver_source_sha=binding["receiver_source_sha"],
            binding_sha256=contract.digest(args.binding),
            elapsed_seconds=time.monotonic() - origin,
        )
        atomic_json(run / "component_result.json", result)
        print(
            json.dumps(
                {k: result[k] for k in ("status", "mode_count", "ordered_key_sha256")}
            )
        )
        return 0
    contract, component = source_modules(root, args.frozen_source, binding)
    run = Path(binding["run_path"])
    stage = binding["stage"]
    atomic_json(run / "runtime.json", numeric_runtime())
    guard(binding)
    if stage == "control":
        result = component.control_layout()
        result["p6_native_control"] = component.control_layout(degree=6)
        arrays = result.pop("arrays")
        arrays.update(
            {"p6_" + k: v for k, v in result["p6_native_control"].pop("arrays").items()}
        )
        result["raw"] = atomic_arrays(run / "control_arrays.npz", arrays)
        result["native_control_complete"] = True
        result["original_inputs"] = contract.validate_originals(binding["spec"])
        result["consumer_quadrature"] = component.consumers(60)
    else:
        contract.require_same_binding(binding, binding["spec"], consumer=stage)
        modes = json.loads(Path(binding["spec"]["manifest_path"]).read_text())["modes"]
        modes, physics = component.physical_modes(modes)
        atomic_json(run / "physics_binding.json", physics)

        def previous(name):
            return Path(
                binding["spec"]
                .get("prerequisite_paths", {})
                .get(name, Path(binding["spec"]["output_root"]) / name)
            )

        if stage == "boundary":
            result = boundary_worker(root, binding, modes, component, run)
        elif stage == "boundary_check":
            result = check_boundary(
                binding,
                modes,
                component,
                previous("boundary"),
                run,
            )
        elif stage.endswith("_check"):
            result = check_local(
                component,
                previous(stage.removesuffix("_check")),
                run,
                binding,
                modes,
            )
        else:
            from src.common.config_3d import SimulationConfig3D

            layout, _ = layout_for(modes, int(stage[1]))
            config = SimulationConfig3D(
                wavelength_nm=0.7,
                eps_r=1 + 0j,
                mu_r=1 + 0j,
                grating_index=0.9998851703688496 + 4.3236152269189515e-6j,
                substrate_index=0.9998851703688496 + 4.3236152269189515e-6j,
            )
            result = component.run_local(binding["spec"], modes, layout, config=config)
            arrays = result.pop("arrays")
            result["raw"] = atomic_arrays(run / "local_arrays.npz", arrays)
            del arrays, layout
            gc.collect()
            result["worker_factor_lifecycle"] = (
                "local factor scoped inside frozen call; released before independent checker process"
            )
            result["status"] = "P2_LOCAL_WORKER_COMPLETED_PENDING_CHECKER"
    result.update(
        elapsed_seconds=time.monotonic() - origin,
        binding_sha256=contract.digest(args.binding),
        receiver_source_sha=binding["receiver_source_sha"],
        math_commit=contract.MATH_COMMIT,
        NN_used=False,
        official_results=False,
        full_target_qualified=False,
        raw_export_overlay=file_receipt(run / "math_export_overlay.json"),
        raw_runtime=file_receipt(run / "runtime.json"),
        raw_abi=file_receipt(run / "abi_receipt.json"),
    )
    if stage != "control":
        result["raw_physics_binding"] = file_receipt(run / "physics_binding.json")
    atomic_json(run / "component_result.json", result)
    print(
        json.dumps(
            {k: result[k] for k in ("status", "elapsed_seconds", "receiver_source_sha")}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
