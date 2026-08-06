"""Recompute the frozen Task037 M3a 12+12 channel comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTHORITY = (
    ROOT
    / "benchmarks/cases/100_static_condensed_full3d_iterative/records/"
    / "task37_m3a_overlap0125_partition_full_v1.json"
)
DEFAULT_CURRENT = (
    ROOT
    / "benchmarks/artifacts/101_task37_extra_development/"
    / "g0_m3a_mpi1_full_77d39cbe/dtn_port_diffraction_orders_3d.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks/cases/101_task37_extra_development/records/"
    / "g0_m3a_mpi1_full_channels.json"
)
EXPECTED_AUTHORITY_SHA256 = (
    "43c749aa9f25282308c607de73a890acbabaf9af1e5f366a0c9eb5aee10f6019"
)
REFERENCE_ROLE = "direct_authority_embedded_in_historical_m3a_record"
_LABEL_RE = re.compile(r"^(R|T)\((-?\d+),(-?\d+)\)_([^()]+)$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _parse_label(label: Any) -> tuple[str, int, int, str] | None:
    if not isinstance(label, str):
        return None
    match = _LABEL_RE.fullmatch(label)
    if match is None:
        return None
    prefix, m, n, polarization = match.groups()
    side = "top" if prefix == "R" else "bottom"
    return side, int(m), int(n), polarization


def _current_key(row: dict[str, Any]) -> tuple[str, int, int, str] | None:
    side = row.get("side")
    polarization = row.get("polarization")
    m = row.get("m")
    n = row.get("n")
    if (
        not isinstance(side, str)
        or not isinstance(polarization, str)
        or not isinstance(m, int)
        or isinstance(m, bool)
        or not isinstance(n, int)
        or isinstance(n, bool)
    ):
        return None
    return side, m, n, polarization


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def check_channels(
    authority_path: Path = DEFAULT_AUTHORITY,
    current_path: Path = DEFAULT_CURRENT,
) -> dict[str, Any]:
    """Recompute only the twelve frozen channel comparisons."""

    authority_path = Path(authority_path)
    current_path = Path(current_path)
    authority_sha256 = _sha256(authority_path)
    current_sha256 = _sha256(current_path)
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    current = json.loads(current_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    authority_hash_matches = authority_sha256 == EXPECTED_AUTHORITY_SHA256
    if not authority_hash_matches:
        failures.append("frozen_authority_sha256_mismatch")

    frozen = authority.get("channels_12")
    if not isinstance(frozen, list):
        frozen = []
        failures.append("authority_channels_12_missing")

    frozen_rows: list[tuple[dict[str, Any], str, tuple[str, int, int, str]]] = []
    frozen_keys: set[tuple[str, int, int, str]] = set()
    for index, entry in enumerate(frozen):
        if not isinstance(entry, dict):
            failures.append(f"authority_channel_{index}_not_object")
            continue
        label = entry.get("label")
        key = _parse_label(label)
        if key is None:
            failures.append(f"authority_channel_{index}_label_invalid")
            continue
        if key in frozen_keys:
            failures.append(f"authority_channel_{index}_duplicate_label")
        frozen_keys.add(key)
        frozen_rows.append((entry, str(label), key))
        for field in (
            "direct_power",
            "power_tolerance",
            "amplitude_tolerance",
        ):
            if not _finite(entry.get(field)) or float(entry[field]) < 0.0:
                failures.append(f"authority_channel_{index}_{field}_invalid")
        amplitude = entry.get("direct_boundary_amplitude")
        if (
            not isinstance(amplitude, list)
            or len(amplitude) != 2
            or not all(_finite(value) for value in amplitude)
        ):
            failures.append(f"authority_channel_{index}_direct_boundary_amplitude_invalid")

    if len(frozen) != 12:
        failures.append("authority_channel_count_is_not_12")
    if len(frozen_keys) != 12:
        failures.append("authority_channel_labels_are_not_12_unique")

    orders = current.get("orders") if isinstance(current, dict) else None
    if not isinstance(orders, list):
        orders = []
        failures.append("current_orders_missing")
    current_by_key: dict[tuple[str, int, int, str], list[dict[str, Any]]] = {}
    for row in orders:
        if isinstance(row, dict):
            key = _current_key(row)
            if key is not None:
                current_by_key.setdefault(key, []).append(row)

    rows: list[dict[str, Any]] = []
    for entry, label, key in frozen_rows:
        matches = current_by_key.get(key, [])
        row: dict[str, Any] = {
            "label": label,
            "side": key[0],
            "m": key[1],
            "n": key[2],
            "polarization": key[3],
            "match_count": len(matches),
            "reference_role": REFERENCE_ROLE,
            "power_tolerance": entry.get("power_tolerance"),
            "amplitude_tolerance": entry.get("amplitude_tolerance"),
            "power_pass": False,
            "amplitude_pass": False,
        }
        if len(matches) != 1:
            failures.append(f"current_channel_{label}_match_count_{len(matches)}")
            rows.append(row)
            continue

        current_row = matches[0]
        current_power = current_row.get("power_ratio")
        current_amplitude = current_row.get("outgoing_amplitude_at_boundary")
        reference_power = entry.get("direct_power")
        reference_amplitude = entry.get("direct_boundary_amplitude")
        row["current_power_ratio"] = current_power
        row["current_amplitude"] = current_amplitude
        row["reference_power"] = reference_power
        row["reference_amplitude"] = reference_amplitude
        power_valid = _finite(current_power) and _finite(reference_power)
        amplitude_valid = (
            isinstance(current_amplitude, list)
            and len(current_amplitude) == 2
            and all(_finite(value) for value in current_amplitude)
            and isinstance(reference_amplitude, list)
            and len(reference_amplitude) == 2
            and all(_finite(value) for value in reference_amplitude)
        )
        power_diff = (
            abs(float(current_power) - float(reference_power)) if power_valid else None
        )
        amplitude_diff = (
            math.hypot(
                float(current_amplitude[0]) - float(reference_amplitude[0]),
                float(current_amplitude[1]) - float(reference_amplitude[1]),
            )
            if amplitude_valid
            else None
        )
        row["power_abs_diff"] = power_diff
        row["amplitude_abs_diff"] = amplitude_diff
        row["power_pass"] = bool(
            power_diff is not None
            and power_diff <= float(entry["power_tolerance"])
        )
        row["amplitude_pass"] = bool(
            amplitude_diff is not None
            and amplitude_diff <= float(entry["amplitude_tolerance"])
        )
        if not power_valid:
            failures.append(f"current_channel_{label}_power_nonfinite")
        if not amplitude_valid:
            failures.append(f"current_channel_{label}_amplitude_nonfinite")
        rows.append(row)

    power_pass_count = sum(row["power_pass"] for row in rows)
    amplitude_pass_count = sum(row["amplitude_pass"] for row in rows)
    overall_pass = (
        authority_hash_matches
        and len(frozen) == 12
        and len(frozen_keys) == 12
        and len(rows) == 12
        and power_pass_count == 12
        and amplitude_pass_count == 12
        and not failures
    )
    return {
        "record_kind": "task037_extra_g0_posthoc_full_channels",
        "authority_path": _relative_path(authority_path),
        "authority_sha256": authority_sha256,
        "authority_sha256_expected": EXPECTED_AUTHORITY_SHA256,
        "reference_role": REFERENCE_ROLE,
        "current_raw_path": _relative_path(current_path),
        "current_raw_sha256": current_sha256,
        "channels_checked": len(rows),
        "power_pass_count": power_pass_count,
        "amplitude_pass_count": amplitude_pass_count,
        "power_pass_12_of_12": power_pass_count == 12,
        "amplitude_pass_12_of_12": amplitude_pass_count == 12,
        "overall_pass": overall_pass,
        "status": "posthoc_recomputed_12_of_12" if overall_pass else "posthoc_failed",
        "failures": failures,
        "channels": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = check_channels(args.authority, args.current)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "overall_pass": report["overall_pass"]}))
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
