"""Independent finite V4 decisions from original residual norms and scales."""

import hashlib
import json
import math
from pathlib import Path

INDEX = Path(__file__).resolve().parents[2] / "tmp/task042/v4/stage_index.json"


def rhs_only_packet(path, expected_sha256):
    """Reject hidden teacher/initial-state fields before accessing arrays."""
    import numpy as np

    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("Fresh RHS packet identity changed")
    with np.load(path, allow_pickle=False) as packet:
        if set(packet.files) != {"rhs_fe", "rhs_port"}:
            raise ValueError("Qualification accepts only RHS arrays, never a solution")
        return packet["rhs_fe"], packet["rhs_port"]


def publish(stage, directory, index_file=INDEX):
    """Publish after cleanup using only small JSON; no FE import in launcher."""
    index = json.loads(index_file.read_text()) if index_file.exists() else {}
    if stage in index:
        raise ValueError("V4 stage already published; no numerical retry")
    summary = json.loads((directory / "run_summary.json").read_text())
    if summary["leader_exit_code"] != 0 or not summary["descendants_cleared"]:
        return
    index[stage] = {
        "directory": str(directory),
        "files_sha256": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in (
                "run_manifest.json",
                "run_summary.json",
                "numerical_summary.json",
            )
        },
    }
    temporary = index_file.with_suffix(".pending.json")
    temporary.write_text(json.dumps(index, indent=2, allow_nan=False) + "\n")
    temporary.replace(index_file)


def relative(norm, scale):
    return norm / scale if scale else norm


def strict_from_norms(values):
    keys = ("native", "port", "internal", "native_identity", "Schur_port_identity")
    ratios = {
        key: relative(values[key + "_absolute"], values[key + "_scale"]) for key in keys
    }
    submitted = relative(
        values["submitted_recovery_absolute"], values["submitted_field_norm"]
    )
    recovery = math.hypot(ratios["internal"], submitted)
    return (
        all(
            math.isfinite(value) and value <= 1e-10
            for value in (*ratios.values(), recovery)
        )
        and values["finite"]
        and values["maximum_slave_storage"] == 0.0
    )


def diagnostic_status(rows):
    if len(rows) != 3 or {row["index"] for row in rows} != {0, 10, 11}:
        raise ValueError("Three registered diagnostic RHS required")
    if all(strict_from_norms(row["final_original_norms"]) for row in rows):
        return "STRICT_DIAGNOSTIC_PASS"
    for row in rows:
        values = row["final_original_norms"]
        if (
            not values["finite"]
            or values["maximum_slave_storage"]
            or not all(math.isfinite(value) for value in values.values())
            or not math.isfinite(row["final"]["explicit_Schur_relative_rhs"])
            or any(
                relative(values[key + "_absolute"], values[key + "_scale"]) > 1e-10
                for key in ("native_identity", "Schur_port_identity", "internal")
            )
        ):
            return "COARSE_SPACE_NUMERICAL_BLOCKED"
    for row in rows:
        values = row["final_original_norms"]
        if row["index"] in (0, 11) and (
            relative(values["native_absolute"], values["native_scale"]) > 0.1
            or row["final"]["explicit_Schur_relative_rhs"] > 0.1
        ):
            return "BOUNDED_TWOLEVEL_NEGATIVE"
    return "GLOBAL_SPACE_DIAGNOSTIC_POSITIVE"


def select_route(reports):
    eligible = []
    for route, report in reports.items():
        rows = report.get("rows", [])
        if not rows or diagnostic_status(rows) not in (
            "STRICT_DIAGNOSTIC_PASS",
            "GLOBAL_SPACE_DIAGNOSTIC_POSITIVE",
        ):
            continue
        score = (
            -sum(strict_from_norms(row["final_original_norms"]) for row in rows),
            max(
                relative(
                    row["final_original_norms"]["native_absolute"],
                    row["final_original_norms"]["native_scale"],
                )
                for row in rows
            ),
            max(row["final"]["explicit_Schur_relative_rhs"] for row in rows),
            0 if route == "OLDPOD" else 1,
        )
        eligible.append((score, route))
    return min(eligible)[1] if eligible else None
