"""Independent raw-array coverage/physics consumer, never a FE operator oracle."""

import json
from pathlib import Path

import numpy as np

from benchmarks.check_boundary_witness import metric, read_arrays
from src.solvers.boundary_structure_scope import plan_record, read_stage


def modal_physics(rows, *, area, k0, mu_r):
    """Recompute all modal H and signed reference flux from frozen k/E."""
    from src.solvers.directional_boundary import zvalue

    h_errors, power_errors = [], []
    for row in rows:
        k = np.array([zvalue(v) for v in row["k_vector"]])
        e = np.array([zvalue(v) for v in row["e_vector"]])
        phase2 = abs(np.exp(1j * k[2] * row["reference_plane_nm"])) ** 2
        H = area * (abs(e[0]) ** 2 + abs(e[1]) ** 2) * phase2
        denominator = row["projection_denominator"]
        if not np.isfinite(denominator) or denominator <= 0:
            raise ValueError("nonpositive/nonfinite complete modal H")
        h_errors.append(abs(H - denominator) / denominator)
        h = np.cross(k, e) / (k0 * mu_r)
        flux = 0.5 * (e[0] * h[1].conj() - e[1] * h[0].conj()).real
        flux *= area * phase2 * (1 if row["side"] == "top" else -1)
        power_errors.append(abs(flux - row["power_at_reference_unit_amplitude"]))
    return np.array(h_errors), np.array(power_errors)


def require_action_inventory(data, inputs, n, nm):
    required = {
        f"q{q}_{label}_{kind}"
        for q in (30, 60)
        for label in ("a", "b")
        for kind in ("amplitudes", "forward", "adjoint", "modal", "linear", "zero")
    }
    if set(data) != required | {"H_errors", "unit_power_errors"} or set(inputs) != {
        "x",
        "y",
        "alpha",
    }:
        raise ValueError("complete action/input inventory")
    for name, a in inputs.items():
        if (
            a.shape != ((nm,) if name == "alpha" else (n,))
            or a.dtype != np.complex128
            or not np.isfinite(a).all()
        ):
            raise ValueError("complete action input shape/dtype/finite")
    for name in required:
        a = data[name]
        size = nm if name.endswith("amplitudes") else n
        if a.shape != (size,) or a.dtype != np.complex128 or not np.isfinite(a).all():
            raise ValueError("complete action vector shape/dtype/finite")
    for name in ("H_errors", "unit_power_errors"):
        if data[name].shape != (nm,) or not np.isfinite(data[name]).all():
            raise ValueError("full modal physics inventory")


def final_oracle_links(data, oracle, full_modes, selected_modes, oracle_indices):
    """Link independent saved amplitudes to the final full-inventory output."""
    if len(full_modes) != len({r["mode_index"] for r in full_modes}) or [
        r["mode_index"] for r in full_modes
    ] != list(range(len(full_modes))):
        raise ValueError("ordered full mode identity")
    wanted = [r["mode_index"] for r in selected_modes]
    if oracle_indices != wanted or len(set(wanted)) != len(wanted):
        raise ValueError("oracle selected mode mapping inventory")
    for r in selected_modes:
        i = r["mode_index"]
        if not 0 <= i < len(full_modes) or any(
            r[k] != full_modes[i][k]
            for k in (
                "side",
                "m",
                "n",
                "polarization",
                "reference_plane_nm",
                "projection_denominator",
                "k_vector",
                "e_vector",
                "traction_vector",
            )
        ):
            raise ValueError("oracle/full mode key identity")
    checks = []
    for label in ("a", "b"):
        explicit = oracle[label + "_amplitudes"]
        if explicit.shape != (len(wanted),):
            raise ValueError("oracle amplitude inventory")
        for q in (30, 60):
            actual = data[f"q{q}_{label}_amplitudes"]
            if actual.shape != (len(full_modes),):
                raise ValueError("final full inventory amplitude shape")
            for j, index in enumerate(wanted):
                checks.append(
                    dict(
                        kind="final_full_oracle_amplitude",
                        input=label,
                        q=q,
                        original_index=index,
                        **metric(actual[index : index + 1], explicit[j : j + 1]),
                    )
                )
    return checks


def check_saved():
    b, _bp = read_stage("BRIDGE")
    plan = plan_record()
    ident = json.loads(Path(plan["parent_identity"]["path"]).read_text())
    wp = json.loads(Path(ident["witness_plan"]["path"]).read_text())
    checks = []
    expected = {p["name"]: p for p in wp["patches"]}
    names = [p["description"]["name"] for p in b["patches"]]
    if len(names) != 4 or set(names) != set(expected):
        raise ValueError("complete four class identity")
    for p in b["patches"]:
        if p["description"] != expected[p["description"]["name"]]:
            raise ValueError("literal patch geometry identity")
        native = read_arrays(p["native"])
        new = read_arrays(p["directional"])
        slow = read_arrays(p["independent"])
        for i in range(len(wp["selected_modes"])):
            for kind in ("C", "D"):
                checks.append(
                    dict(
                        patch=p["description"]["name"],
                        index=i,
                        kind="same_q_" + kind,
                        **metric(new[f"{kind}_{i}"], native[f"{kind}_{i}"]),
                    )
                )
                checks.append(
                    dict(
                        patch=p["description"]["name"],
                        index=i,
                        kind="q30_60_" + kind,
                        **metric(new[f"{kind}_{i}"], slow[f"{kind}_{i}"]),
                    )
                )
        if "witness" not in p["component"]:
            raise ValueError("complete patch action inventory")
        data = read_arrays(p["component"]["witness"])
        nm = len(wp["selected_modes"])
        C = np.column_stack([native[f"C_{i}"] for i in range(nm)])
        D = np.row_stack([native[f"D_{i}"] for i in range(nm)])
        H = np.array([r["projection_denominator"] for r in wp["selected_modes"]])
        predictions = {
            "forward": C @ ((D @ data["x"]) / H),
            "adjoint": D.conj().T @ ((C.conj().T @ data["y"]) / H),
            "amplitudes": D @ data["x"] / H,
            "modal": C @ np.ones(nm),
            "linear": (0.37 - 0.91j) * data["forward"],
        }
        for kind, v in predictions.items():
            checks.append(
                dict(patch=p["description"]["name"], kind=kind, **metric(v, data[kind]))
            )
    bridgepass = bool(checks) and all(c["passed"] for c in checks)
    result = {
        "status": "NATIVE_P6_PERIODIC_PATCH_BRIDGE_QUALIFIED"
        if bridgepass
        else "NATIVE_BRIDGE_NOT_QUALIFIED",
        "checks": checks,
        "native_q60": "NOT_RUN_STORAGE_GATE_PRESERVED",
        "target_solve": False,
        "official_RTA": False,
        "MPI_qualification": 1,
        "reference_read": False,
    }
    from src.solvers.boundary_structure_scope import ARTIFACT

    if not (ARTIFACT / "COMPONENT.json").exists():
        result["full_action"] = "NOT_RUN"
        return result
    c, _ = read_stage("COMPONENT")
    if c["status"] != "COMPLETE_BOUNDARY_ACTIONS_FROZEN_PENDING_ORACLE":
        result["full_action"] = "PARTIAL_COST_GATE"
        return result
    n = c["rows"]
    nm = c["mode_count"]
    data = read_arrays(c["outputs"])
    inputs = read_arrays(c["inputs"])
    require_action_inventory(data, inputs, n, nm)
    if (n, nm) != (378432, 32060):
        raise ValueError("full surface/complete mode inventory")
    required = {
        f"q{q}_{label}_{kind}"
        for q in (30, 60)
        for label in ("a", "b")
        for kind in ("amplitudes", "forward", "adjoint", "modal", "linear", "zero")
    }
    if set(data) != required | {"H_errors", "unit_power_errors"}:
        raise ValueError("missing complete action inventory")
    for key, seed in (("x", 423801), ("y", 423803)):
        rng = np.random.default_rng(seed)
        if not np.array_equal(
            inputs[key], rng.normal(size=n) + 1j * rng.normal(size=n)
        ):
            raise ValueError("preregistered mixed boundary seed identity")
    from src.solvers.target_boundary_witness import parent_inventory
    from src.solvers.target_port_preparation import target_config

    _, modes = parent_inventory()
    cfg, _ = target_config()
    h_errors, power_errors = modal_physics(
        modes, area=cfg.period_x * cfg.period_y, k0=cfg.k0, mu_r=cfg.mu_r
    )
    if len(modes) != nm or [r["mode_index"] for r in modes] != list(range(nm)):
        raise ValueError("complete ordered modal physics identity")
    fullchecks = []
    for label, x, y in [
        ("a", inputs["x"], inputs["y"]),
        ("b", inputs["y"], inputs["x"]),
    ]:
        for kind in ("amplitudes", "forward", "adjoint", "modal", "linear", "zero"):
            size = nm if kind == "amplitudes" else n
            for q in (30, 60):
                if data[f"q{q}_{label}_{kind}"].shape != (size,):
                    raise ValueError("full vector shape")
            fullchecks.append(
                dict(
                    kind=kind,
                    input=label,
                    **metric(data[f"q30_{label}_{kind}"], data[f"q60_{label}_{kind}"]),
                )
            )
        for q in (30, 60):
            f = data[f"q{q}_{label}_forward"]
            h = data[f"q{q}_{label}_adjoint"]
            fullchecks.append(
                dict(
                    kind="dual",
                    input=label,
                    q=q,
                    **metric(np.array([np.vdot(y, f)]), np.array([np.vdot(h, x)])),
                )
            )
            fullchecks.append(
                dict(
                    kind="linearity",
                    input=label,
                    q=q,
                    **metric(data[f"q{q}_{label}_linear"], (0.37 - 0.91j) * f),
                )
            )
            fullchecks.append(
                {
                    "kind": "zero",
                    "input": label,
                    "q": q,
                    "passed": not data[f"q{q}_{label}_zero"].any(),
                }
            )
    if not (ARTIFACT / "ORACLE.json").exists():
        result.update(full_action="PARTIAL_MISSING_ORACLE", fullchecks=fullchecks)
        return result
    oracle, _ = read_stage("ORACLE")
    if (
        oracle["modes"] != [r["mode_index"] for r in wp["selected_modes"]]
        or oracle["explicit_face_visits"] != 12 * 2628
    ):
        raise ValueError("fixed complete selected oracle coverage")
    o = read_arrays(oracle["outputs"])
    fullchecks.extend(
        final_oracle_links(data, o, modes, wp["selected_modes"], oracle["modes"])
    )
    for label in ("a", "b"):
        for kind in ("amplitudes", "forward", "adjoint", "modal"):
            fullchecks.append(
                dict(
                    input=label,
                    kind="explicit_" + kind,
                    **metric(o[label + "_" + kind], o["new_" + label + "_" + kind]),
                )
            )
    for label in ("a", "b"):
        a = data[f"q30_{label}_amplitudes"]
        b = data[f"q60_{label}_amplitudes"]
        den = np.maximum(abs(a), abs(b))
        diff = abs(a - b)
        rel = np.divide(diff, den, out=np.zeros_like(diff), where=den != 0)
        fullchecks.append(
            {
                "kind": "all_channel_q30_q60",
                "input": label,
                "passed": bool((rel <= 1e-10).all()),
                "maximum_relative": float(rel.max()),
                "worst_original_index": int(rel.argmax()),
                "numerator": float(diff[rel.argmax()]),
                "denominator": float(den[rel.argmax()]),
            }
        )
    fullpass = (
        bridgepass
        and all(c["passed"] for c in fullchecks)
        and max(data["H_errors"]) <= 1e-10
        and max(data["unit_power_errors"]) <= 1e-10
        and max(h_errors) <= 1e-10
        and max(power_errors) <= 1e-10
    )
    result.update(
        status="TARGET_BOUNDARY_ACTION_QUALIFIED_AT_FROZEN_Q"
        if fullpass
        else "FULL_BOUNDARY_ACTION_NOT_QUALIFIED",
        fullchecks=fullchecks,
        full_action="QUALIFIED" if fullpass else "FAIL",
        q=30,
        modes=nm,
        rows=n,
        H_max_relative=float(max(h_errors)),
        unit_power_max_absolute=float(max(power_errors)),
        H_worst_original_index=int(h_errors.argmax()),
        unit_power_worst_original_index=int(power_errors.argmax()),
        modal_physics_recomputed_from_frozen_inventory=True,
    )
    return result
