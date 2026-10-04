"""Saved-array independent boundary checker; no FE runtime or solver import."""

import hashlib
import json
from pathlib import Path

import numpy as np

from src.solvers.boundary_witness_scope import ARTIFACT, read_stage


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
        aliases = receipt.get("aliases", {})
        if not set(aliases) <= set(receipt["members"]) or any(
            not isinstance(v, str) or v not in receipt["members"] or v in aliases
            for v in aliases.values()
        ):
            raise ValueError("saved witness alias inventory")
        if set(data.files) != set(receipt["members"]) - set(aliases):
            raise ValueError("saved witness inventory")
        result = {}
        for name, value in receipt["members"].items():
            a = data[aliases.get(name, name)]
            if (
                list(a.shape) != value["shape"]
                or a.dtype.str != value["dtype"]
                or hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
                != value["sha256"]
            ):
                raise ValueError("saved witness member identity")
            result[name] = a
    return result


def require_complete_coverage(plan, result):
    """Validate inventory independently; counts alone cannot prove coverage."""
    expected = {p["name"]: p for p in plan["patches"]}
    found = [p["description"]["name"] for p in result["patches"]]
    if len(found) != len(expected) or set(found) != set(expected):
        raise ValueError("missing/duplicate planned patch identity")
    qset = set(plan["quadrature_degrees"])
    for patch in result["patches"]:
        if patch["description"] != expected[patch["description"]["name"]]:
            raise ValueError("wrong planned patch geometry identity")
        qs = [r["q"] for r in patch["q_records"]]
        if len(qs) != len(qset) or set(qs) != qset:
            raise ValueError("missing/duplicate planned quadrature coverage")
        if "witness" not in patch["component"]:
            raise ValueError("missing planned action witness")


def check_saved():
    if not (ARTIFACT / "PATCH.json").exists():
        return check_partial()
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
    require_complete_coverage(plan, result)
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
            if not {
                "x",
                "y",
                "forward",
                "adjoint",
                "amplitudes",
                "modal",
                "linear",
            } <= set(data):
                raise ValueError("missing complete action inventory")
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
        "component_classification": "TARGET_P6_BOUNDARY_WITNESS_QUALIFIED"
        if same_q and q60 and all(c["passed"] for c in same_q + q60)
        else "TARGET_P6_BOUNDARY_WITNESS_NOT_QUALIFIED",
        "target_solve": False,
        "reference_read": False,
        "new_volume_actions": 0,
        "new_LU": 0,
        "new_QR": 0,
    }


def check_partial():
    result, path = read_stage("CAPACITY")
    identity, _ = read_stage("IDENTITY")
    wp = identity["witness_plan"]
    plan = json.loads(Path(wp["path"]).read_text())
    if (
        hashlib.sha256(Path(wp["path"]).read_bytes()).hexdigest() != wp["sha256"]
        or result["description"] != plan["patches"][0]
    ):
        raise ValueError("fixed partial witness/geometry identity")
    native = {int(q): read_arrays(r) for q, r in result["native_files"].items()}
    manual = {int(q): read_arrays(r) for q, r in result["manual_files"].items()}
    actions = (
        read_arrays(result["component"]["witness"])
        if "witness" in result["component"]
        else None
    )
    rows = plan["selected_modes"]
    nm = len(rows)
    checks = []
    quadrature = []
    physical = []
    if (
        result["native_hex_count"] != len(plan["patches"][0]["cells"])
        or result["selected_mode_count"] != nm
        or nm > 24
    ):
        raise ValueError("partial inventory")

    def z(v):
        return complex(v["real"], v["imag"])

    H = []
    for i, row in enumerate(rows):
        e = np.array([z(v) for v in row["e_vector"]])
        k = np.array([z(v) for v in row["k_vector"]])
        normal = np.array([0, 0, 1 if row["side"] == "top" else -1])
        traction = np.cross(1j * np.cross(k, e), normal)
        for q in (15, 30):
            components = native[q][f"native_components_{i}"]
            for kind, expected in [
                ("C", components @ (-traction[:2])),
                ("D", (components @ e[:2]).conj()),
            ]:
                checks.append(
                    dict(
                        index=i,
                        q=q,
                        kind="native_" + kind,
                        **metric(native[q][f"{kind}_{i}"], expected),
                    )
                )
        for kind in ("C", "D"):
            checks.append(
                dict(
                    index=i,
                    kind="same_q30_" + kind,
                    **metric(manual[30][f"{kind}_{i}"], native[30][f"{kind}_{i}"]),
                )
            )
            quadrature.append(
                dict(
                    index=i,
                    kind="q15_native_vs_q30_native_" + kind,
                    **metric(native[15][f"{kind}_{i}"], native[30][f"{kind}_{i}"]),
                )
            )
            quadrature.append(
                dict(
                    index=i,
                    kind="q30_native_vs_q60_Basix_" + kind,
                    **metric(native[30][f"{kind}_{i}"], manual[60][f"{kind}_{i}"]),
                )
            )
        phase = np.exp(1j * k[2] * row["reference_plane_nm"])
        h = 1250 * float(np.vdot(e[:2], e[:2]).real) * abs(phase) ** 2
        hh = np.cross(k, e) / (2 * np.pi / 0.7)
        power = (
            0.5
            * float(np.cross(e, np.conj(hh))[2].real)
            * abs(phase) ** 2
            * 1250
            * normal[2]
        )
        he = abs(h - row["projection_denominator"]) / row["projection_denominator"]
        pe = abs(power - row["power_at_reference_unit_amplitude"])
        physical.append(
            {
                "index": i,
                "H_relative": he,
                "unit_power_absolute": pe,
                "passed": he <= 1e-10 and pe <= 1e-10,
            }
        )
        H.append(h)
    if actions is not None:
        C = np.column_stack([native[30][f"C_{i}"] for i in range(nm)])
        D = np.row_stack([native[30][f"D_{i}"] for i in range(nm)])
        expected = {
            "forward": C @ ((D @ actions["x"]) / H),
            "adjoint": D.conj().T @ ((C.conj().T @ actions["y"]) / H),
            "amplitudes": D @ actions["x"] / H,
            "modal": C @ np.ones(nm),
            "linear": (0.37 - 0.91j) * actions["forward"],
        }
        checks.extend(
            dict(kind=kind, **metric(actions[kind], value))
            for kind, value in expected.items()
        )
    passed = actions is not None and all(c["passed"] for c in checks + physical)
    return {
        "status": "P6_PARTIAL_SAVED_ARRAYS_VERIFIED"
        if passed
        else "P6_PARTIAL_CHECKER_NUMERICAL_FAILURE",
        "parent": {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        "independent_checks": checks,
        "independent_quadrature_checks": quadrature,
        "independent_H_power": physical,
        "component_passed": passed,
        "q15_vs_q30_pass": all(
            c["passed"] for c in quadrature if c["kind"].startswith("q15")
        ),
        "q30_native_vs_q60_Basix_pass": all(
            c["passed"] for c in quadrature if c["kind"].startswith("q30")
        ),
        "native_q60": "NOT_RUN_STORAGE_GATE",
        "target_witness_qualified": False,
        "target_solve": False,
        "periodic_coverage": "NOT_RUN_STORAGE_GATE",
        "new_volume_actions": 0,
        "new_LU": 0,
        "new_QR": 0,
        "reference_read": False,
    }
