"""Independent raw-array coverage/physics consumer, never a FE operator oracle."""

import json
from pathlib import Path

import numpy as np

from benchmarks.check_boundary_witness import metric, read_arrays
from src.solvers.boundary_structure_scope import plan_record, read_stage


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
        f = data[f"q30_{label}_forward"]
        h = data[f"q30_{label}_adjoint"]
        fullchecks.append(
            dict(
                kind="dual",
                input=label,
                **metric(np.array([np.vdot(y, f)]), np.array([np.vdot(h, x)])),
            )
        )
        fullchecks.append(
            dict(
                kind="linearity",
                input=label,
                **metric(data[f"q30_{label}_linear"], (0.37 - 0.91j) * f),
            )
        )
        fullchecks.append(
            {
                "kind": "zero",
                "input": label,
                "passed": not data[f"q30_{label}_zero"].any(),
            }
        )
    if not (ARTIFACT / "ORACLE.json").exists():
        result.update(full_action="PARTIAL_MISSING_ORACLE", fullchecks=fullchecks)
        return result
    oracle, _ = read_stage("ORACLE")
    o = read_arrays(oracle["outputs"])
    for label in ("a", "b"):
        for kind in ("amplitudes", "forward", "adjoint", "modal"):
            fullchecks.append(
                dict(
                    input=label,
                    kind="explicit_" + kind,
                    **metric(o[label + "_" + kind], o["new_" + label + "_" + kind]),
                )
            )
    fullpass = (
        bridgepass
        and all(c["passed"] for c in fullchecks)
        and max(data["H_errors"]) <= 1e-10
        and max(data["unit_power_errors"]) <= 1e-10
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
        H_max_relative=float(max(data["H_errors"])),
        unit_power_max_absolute=float(max(data["unit_power_errors"])),
    )
    return result
