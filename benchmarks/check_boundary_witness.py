"""Saved-array independent boundary checker; no FE runtime or solver import."""

import hashlib
import json
from pathlib import Path

import numpy as np

from src.solvers.boundary_witness_scope import read_stage


def metric(a, b):
    numerator = float(np.linalg.norm(a - b))
    denominator = max(float(np.linalg.norm(a)), float(np.linalg.norm(b)))
    return {
        "numerator": numerator,
        "denominator": denominator,
        "relative": numerator / denominator if denominator else None,
        "passed": numerator == 0
        if denominator == 0
        else numerator / denominator <= 1e-10,
    }


def read_arrays(receipt):
    path = Path(receipt["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != receipt["sha256"]:
        raise ValueError("saved witness file hash")
    with np.load(path, allow_pickle=False) as data:
        if set(data.files) != set(receipt["members"]):
            raise ValueError("saved witness inventory")
        result = {}
        for name, value in receipt["members"].items():
            a = data[name]
            if (
                list(a.shape) != value["shape"]
                or a.dtype.str != value["dtype"]
                or hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
                != value["sha256"]
            ):
                raise ValueError("saved witness member identity")
            result[name] = a
    return result


def check_saved():
    result, path = read_stage("PATCH")
    identity, _ = read_stage("IDENTITY")
    checks = []
    counts = 0
    planfile = identity["witness_plan"]
    if (
        hashlib.sha256(Path(planfile["path"]).read_bytes()).hexdigest()
        != planfile["sha256"]
    ):
        raise ValueError("selected inventory")
    plan = json.loads(Path(planfile["path"]).read_text())
    nm = len(plan["selected_modes"])
    if (
        len(result["patches"]) != len(plan["patches"])
        or result["native_hex_count"] > 32
        or nm > 24
    ):
        raise ValueError("complete patch/mode inventory")
    for patch in result["patches"]:
        qdata = {}
        for row in patch["q_records"]:
            data = read_arrays(row["numeric_file"])
            qdata[row["q"]] = data
            if len(row["records"]) != nm or set(data) != {
                f"{kind}_{i}"
                for kind in (
                    "C",
                    "D",
                    "tileC",
                    "tileD",
                    "native_components",
                    "tile_components",
                )
                for i in range(nm)
            }:
                raise ValueError("complete selected native inventory")
            for i in range(nm):
                for a, b in [
                    ("tileC", "C"),
                    ("tileD", "D"),
                    ("tile_components", "native_components"),
                ]:
                    checks.append(
                        dict(
                            patch=patch["description"]["name"],
                            q=row["q"],
                            index=i,
                            kind=a,
                            **metric(data[f"{a}_{i}"], data[f"{b}_{i}"]),
                        )
                    )
                if row["q"] > 15:
                    previous = qdata[15 if row["q"] == 30 else 30]
                    for kind in ("C", "D"):
                        checks.append(
                            dict(
                                patch=patch["description"]["name"],
                                q=row["q"],
                                index=i,
                                kind="previous_q_" + kind,
                                **metric(data[f"{kind}_{i}"], previous[f"{kind}_{i}"]),
                            )
                        )
            counts += len(data)
        component = patch["component"]
        if "witness" in component:
            data = read_arrays(component["witness"])
            native = qdata[30]
            n = nm
            C = np.column_stack([native[f"C_{i}"] for i in range(n)])
            D = np.row_stack([native[f"D_{i}"] for i in range(n)])
            H = np.array([r["projection_denominator"] for r in plan["selected_modes"]])
            predicted = {
                "forward": C @ ((D @ data["x"]) / H),
                "adjoint": D.conj().T @ ((C.conj().T @ data["y"]) / H),
                "amplitudes": D @ data["x"] / H,
                "modal": C @ np.ones(n),
                "linear": (0.37 - 0.91j) * data["forward"],
            }
            for k, a in predicted.items():
                checks.append(
                    dict(
                        patch=patch["description"]["name"], kind=k, **metric(data[k], a)
                    )
                )
            counts += len(data)
    same_q = [c for c in checks if not c["kind"].startswith("previous_q_")]
    q60 = [
        c for c in checks if c.get("q") == 60 and c["kind"].startswith("previous_q_")
    ]
    q30 = [
        c for c in checks if c.get("q") == 30 and c["kind"].startswith("previous_q_")
    ]
    return {
        "status": "BOUNDARY_SAVED_ARRAYS_CHECKED",
        "parent": {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        "independent_checks": checks,
        "same_q_pass": all(c["passed"] for c in same_q),
        "q15_vs_q30_pass": all(c["passed"] for c in q30),
        "q30_vs_q60_pass": all(c["passed"] for c in q60),
        "checked_members": counts,
        "component_classification": result["status"],
        "target_solve": False,
        "reference_read": False,
        "new_volume_actions": 0,
        "new_LU": 0,
        "new_QR": 0,
    }
