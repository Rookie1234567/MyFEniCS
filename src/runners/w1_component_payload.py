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
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as out:
        json.dump(value, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_arrays(path, arrays):
    import numpy as np

    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as out:
        np.savez(out, **arrays)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
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
    return contract, component


def layout_for(modes, degree):
    import basix
    from src.solvers.directional_boundary import BoundaryLayout, FacetPolynomial
    from benchmarks.run_task40_w1_boundary_probe import (
        _floquet_phases,
        _proportional_axis,
    )

    phases, facts = _floquet_phases(modes)
    x = _proportional_axis([-25.0, -8.5, 0.0, 8.5, 25.0], 272)
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
    selected = {0.0}
    for values in frequencies:
        selected.update([float(values.min()), float(values.max())])
    for index, row in enumerate(modes):
        if [row["side"], row["m"], row["n"], row["polarization"]] == [
            "top",
            -67,
            -34,
            "s",
        ]:
            selected.update(float(a[index]) for a in frequencies)
    checks = []
    for omega in sorted(selected):
        guard(binding)
        a = oracle.unit_interval_moments(omega, 6)
        b, _ = decimal.moments(omega, 6, 80)
        c, _ = decimal.moments(omega, 6, 110, direct_quadrature=True)
        terms = [float(np.max(abs(a - b))), float(np.max(abs(b - c)))]
        checks.append(
            {
                "omega": omega,
                "analytic_Decimal80_absolute": terms[0],
                "Decimal80_Decimal110_Gauss64_absolute": terms[1],
                "pass": max(terms) <= 1e-12,
            }
        )
    return {
        "status": "ORACLE_INTERVAL_PASS"
        if all(r["pass"] for r in checks)
        else "ORACLE_ACCURACY_UNRESOLVED",
        "checks": checks,
        "maximum_half_phase_span": max(abs(a).max() for a in frequencies) / 2,
        "fixed_reference": "qualified Fourier-Legendre plus Decimal80/110 fixed64-point independent crosscheck",
    }


def boundary_worker(root, binding, modes, component, run):
    """Bounded batches of full native columns, no mode-square array."""
    import numpy as np
    from src.solvers.directional_boundary import zvalue

    oracle = oracle_module(root)
    rows, all_pass = [], True
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
        if oracle_gate["status"] != "ORACLE_INTERVAL_PASS":
            return {"status": "ORACLE_ACCURACY_UNRESOLVED", "chunks": rows}
        polynomial = layout.polynomial
        actions = component.probe_actions(layout, modes, q)
        reference_action = {
            name: np.zeros_like(actions[name])
            for name in ("components", "recover", "apply", "adjoint", "modal_rhs")
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
            for start in range(0, len(indices), 64):
                guard(binding)
                subset = indices[start : start + 64]
                candidate, reference = [], []
                for index in subset:
                    k = kvec[index]
                    candidate.append(polynomial.integral_native(side, k, J, origin, q))
                    identity = oracle.facet_identity(polynomial, side, k, J, origin)
                    reference.append(
                        oracle.integrate_receiver_facet(
                            polynomial, side, k, J, origin, expected=identity
                        )
                    )
                arrays = {
                    "candidate": np.array(candidate),
                    "reference": np.array(reference),
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
    oracle_gates = [
        json.loads((producer / f"oracle_p{p}.json").read_text()) for p in (4, 6)
    ]
    all_pass = all(g["status"] == "ORACLE_INTERVAL_PASS" for g in oracle_gates)
    coverage, diagnostics = {4: [], 6: []}, []
    action_states, reference_states, action_metrics, layouts = {}, {}, {}, {}
    for p in (4, 6):
        layouts[p], _ = layout_for(modes, p)
        path = producer / f"actions_p{p}.npz"
        receipt = json.loads((producer / f"actions_p{p}.json").read_text())
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
                )
            }
        reference_states[p] = {
            name: np.zeros_like(action_states[p][name])
            for name in ("components", "recover", "apply", "adjoint", "modal_rhs")
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
                e, t, h = raw["e"][j, :2], raw["traction"][j, :2], float(raw["H"][j])
                ba, bb = a @ -t, b @ -t
                da, db = (a @ e).conj() / h, (b @ e).conj() / h
                metrics = {
                    "integral": component.relative_terms(a, b),
                    "B": component.relative_terms(ba, bb),
                    "D_original_H": component.relative_terms(da, db),
                }
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
    return {
        "status": "P1_Q60_FULL_MODE_PASS" if all_pass else "P1_Q60_FULL_MODE_FAIL",
        "coverage": {str(p): len(v) for p, v in coverage.items()},
        "coverage_complete": complete,
        "actual_action_RHS_adjoint_metrics": action_metrics,
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


def check_local(component, producer, run, binding):
    """Saved full original block equations; no factor or solve in the checker."""
    import numpy as np

    report = json.loads((producer / "component_result.json").read_text())
    guard(binding)
    path = producer / "local_arrays.npz"
    if hashlib.sha256(path.read_bytes()).hexdigest() != report["raw"]["sha256"]:
        raise ValueError("W1_LOCAL_RAW_HASH_CHANGED")
    with np.load(path, allow_pickle=False) as raw:
        a = {k: raw[k] for k in raw.files}
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
    ii, tt = a["interior_positions"], a["trace_positions"]
    V = a["local_native_tensor"]
    xi, xi0, xt = (
        a["recovered_interior"],
        a["known_interior_solution"],
        a["trace_values"],
    )
    fi, ft, bi, bt = a["interior_rhs"], a["trace_rhs"], a["Bi_alpha"], a["Bt_alpha"]
    actual_i, actual_t = (
        V[np.ix_(ii, ii)] @ xi + V[np.ix_(ii, tt)] @ xt + bi,
        V[np.ix_(tt, ii)] @ xi + V[np.ix_(tt, tt)] @ xt + bt,
    )
    alpha, rhs, di, dt = (
        a["mode_alpha"],
        a["port_rhs"],
        a["port_internal_recovered_correction"],
        a["port_trace_action"],
    )
    original = alpha - rhs - di - dt
    reduced = (
        alpha
        + a["port_internal_B_correction"]
        - (rhs + a["port_internal_rhs_correction"])
        - dt
        + a["port_internal_trace_correction"]
    )
    metrics = {
        "interior_original_equation": component.relative_terms(actual_i, fi),
        "trace_original_equation": component.relative_terms(actual_t, ft),
        "full_internal_recovery": component.relative_terms(xi, xi0),
        "port_original_equation": component.relative_terms(alpha - di - dt, rhs),
        "port_reduced_equation": component.relative_terms(
            alpha
            + a["port_internal_B_correction"]
            - dt
            + a["port_internal_trace_correction"],
            rhs + a["port_internal_rhs_correction"],
        ),
    }
    scale = max(
        np.linalg.norm(alpha),
        np.linalg.norm(rhs),
        np.linalg.norm(di),
        np.linalg.norm(dt),
        np.finfo(float).tiny,
    )
    identity = float(np.linalg.norm(original - reduced) / scale)
    passed = (
        all(value["relative"] <= 1e-10 for value in direct_metrics.values())
        and len(alpha) == 32060
        and len(ii) in (108, 450)
        and all(
            v["relative"]
            <= (
                1e-11
                if k in ("interior_original_equation", "full_internal_recovery")
                else 1e-10
            )
            for k, v in metrics.items()
        )
        and identity <= 1e-11
        and report["consumer_quadrature"] == component.consumers(60)
    )
    return {
        "status": "P2_SAVED_LOCAL_PASS" if passed else "P2_SAVED_LOCAL_FAIL",
        "metrics": metrics,
        "independent_native_direct_q60": direct_metrics,
        "port_elimination_identity": identity,
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
    contract, component = source_modules(root, args.frozen_source, binding)
    run = Path(binding["run_path"])
    stage = binding["stage"]
    atomic_json(run / "runtime.json", numeric_runtime())
    guard(binding)
    if stage == "control":
        result = component.control_layout()
        result["p6_native_control"] = component.control_layout(degree=6)
        result["original_inputs"] = contract.validate_originals(binding["spec"])
        result["consumer_quadrature"] = component.consumers(60)
    else:
        contract.require_same_binding(binding, binding["spec"], consumer=stage)
        modes = json.loads(Path(binding["spec"]["manifest_path"]).read_text())["modes"]
        modes, physics = component.physical_modes(modes)
        atomic_json(run / "physics_binding.json", physics)
        if stage == "boundary":
            result = boundary_worker(root, binding, modes, component, run)
        elif stage == "boundary_check":
            result = check_boundary(
                binding,
                modes,
                component,
                Path(binding["spec"]["output_root"]) / "boundary",
                run,
            )
        elif stage.endswith("_check"):
            result = check_local(
                component,
                Path(binding["spec"]["output_root"]) / stage.removesuffix("_check"),
                run,
                binding,
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
    )
    atomic_json(run / "component_result.json", result)
    print(
        json.dumps(
            {k: result[k] for k in ("status", "elapsed_seconds", "receiver_source_sha")}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
