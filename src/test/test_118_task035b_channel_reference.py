"""Tests for the Task035b significant-channel reference v1."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pytest

from benchmarks.task035b_significant_channel_reference import main
from src.adaptivity.significant_channel_reference import (
    AMPLITUDE_TOLERANCE_FLOOR,
    EXPECTED_SIGNIFICANT_CHANNELS,
    GEOMETRY,
    MANIFEST_SCHEMA_VERSION,
    POWER_TOLERANCE_FLOOR,
    SIGNIFICANT_POWER_FLOOR,
    build_significant_channel_reference,
    unwrap_phase_near_center,
)


_ROLES = {
    "p4_h10": "trend_only",
    "p4_h7p5": "numerical_band",
    "p4_h5": "numerical_band",
    "p5_h10": "unchanged_v0_gate",
    "p6_h10": "reference_center",
    "p5_h15": "underresolved_diagnostic",
    "p6_h15": "underresolved_diagnostic",
    "fixed_p5trace_p6interior_h15": (
        "underresolved_trace_diagnostic"
    ),
}
_SAMPLE_OFFSETS = {
    "p4_h10": -8.0e-4,
    "p4_h7p5": -4.0e-4,
    "p4_h5": -2.0e-4,
    "p5_h10": -1.0e-4,
    "p6_h10": 0.0,
    "p5_h15": 0.1,
    "p6_h15": 0.2,
    "fixed_p5trace_p6interior_h15": 0.3,
}
_COMSOL_ROWS = [
    {
        "table_heading": "## 直接法：四阶拉格朗日单元",
        "source_model": "3D_benchmark_direct_5to2p4.mph",
        "element": "六面体",
        "h_nm": 2.0,
        "solution": "sol47",
        "dofs": 4818792,
        "R00": 0.000752895,
        "R_total": 0.000762014,
        "T_total": 0.602707488,
    },
    {
        "table_heading": "## 直接法：四阶拉格朗日单元",
        "source_model": "3D_benchmark_direct_5to2p4.mph",
        "element": "四面体",
        "h_nm": 3.0,
        "solution": "sol42",
        "dofs": 4323924,
        "R00": 0.000752897,
        "R_total": 0.000762016,
        "T_total": 0.602707468,
    },
    {
        "table_heading": "## 直接法：四阶拉格朗日单元",
        "source_model": "3D_benchmark_direct_5to2p4.mph",
        "element": "四面体",
        "h_nm": 2.5,
        "solution": "sol43",
        "dofs": 7490900,
        "R00": 0.000752891,
        "R_total": 0.000762010,
        "T_total": 0.602707520,
    },
    {
        "table_heading": "## 直接法：六阶拉格朗日单元",
        "source_model": "3D_benchmark_direct_p6.mph",
        "element": "六面体",
        "h_nm": 7.5,
        "solution": "sol44",
        "dofs": 488150,
        "R00": 0.000752896,
        "R_total": 0.000762015,
        "T_total": 0.602707484,
    },
    {
        "table_heading": "## 直接法：六阶拉格朗日单元",
        "source_model": "3D_benchmark_direct_p6.mph",
        "element": "四面体",
        "h_nm": 7.0,
        "solution": "sol50",
        "dofs": 950924,
        "R00": 0.000752895,
        "R_total": 0.000762014,
        "T_total": 0.602707512,
    },
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_comsol_fixture(root: Path) -> dict[str, Any]:
    path = root / "docs" / "COMSOL_direct_solver_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# fixture",
        "",
        "模型版本：COMSOL 6.4.0.293。",
        "",
        "- 直接法均为 **MUMPS 直接求解器**。",
        "",
    ]
    for heading, source in (
        (
            "## 直接法：四阶拉格朗日单元",
            "3D_benchmark_direct_5to2p4.mph",
        ),
        (
            "## 直接法：六阶拉格朗日单元",
            "3D_benchmark_direct_p6.mph",
        ),
    ):
        lines.extend(
            [
                heading,
                "",
                f"来源：`{source}`。",
                "",
                "| 单元 | 尺寸 (nm) | 保存解 | DOFs | R(0,0) | R | T |",
                "|---|---:|---|---:|---:|---:|---:|",
            ]
        )
        for row in _COMSOL_ROWS:
            if row["table_heading"] != heading:
                continue
            lines.append(
                "| {element} | {h_nm} | `{solution}` | {dofs:,} | "
                "{R00:.9f} | {R_total:.9f} | {T_total:.9f} |".format(
                    **row
                )
            )
        lines.append("")
    lines.extend(
        [
            "## 收敛结论",
            "",
            "R(0,0)=0.000752895、R=0.000762014、T=0.6027075。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "authority_document_path": str(path.relative_to(root)),
        "authority_document_sha256": _sha256(path),
        "software_identity": "COMSOL 6.4.0.293",
        "solver_scope": "MUMPS direct solver tables only",
        "center_derivation": (
            "componentwise median of five selected p4/p6 direct-solver "
            "hexa/tetra convergence-anchor rows, rounded to the precision "
            "reported in the document conclusion"
        ),
        "center_precision_decimal_places": {
            "R00": 9,
            "R_total": 9,
            "T_total": 7,
        },
        "reported_convergence_center": {
            "R00": 0.000752895,
            "R_total": 0.000762014,
            "T_total": 0.6027075,
        },
        "selected_table_rows": deepcopy(_COMSOL_ROWS),
        "excluded_from_channel_band": True,
        "excluded_from_12_channel_gate": True,
        "complex_channel_amplitudes_available": False,
        "changes_unchanged_v0_acceptance_gate": False,
    }


def _all_keys() -> list[tuple[str, int, int, str]]:
    keys = list(EXPECTED_SIGNIFICANT_CHANNELS)
    for side in ("bottom", "top"):
        for order_m in range(-17, 17):
            keys.append((side, order_m, 1, "p"))
    assert len(keys) == 80
    assert len(set(keys)) == 80
    return keys


def _order(
    key: tuple[str, int, int, str],
    *,
    offset: float,
) -> dict[str, Any]:
    side, order_m, order_n, polarization = key
    significant = key in EXPECTED_SIGNIFICANT_CHANNELS
    amplitude = (
        [0.1 + offset + order_m * 1.0e-4, 0.02 + 0.5 * offset]
        if significant
        else [1.0e-14, -2.0e-14]
    )
    return {
        "side": side,
        "direction": "outgoing_down" if side == "bottom" else "outgoing_up",
        "medium": "substrate" if side == "bottom" else "air",
        "m": order_m,
        "n": order_n,
        "order_m": order_m,
        "order_n": order_n,
        "polarization": polarization,
        "alpha": [0.01 * order_m, 0.0],
        "gamma": [0.01 * order_n, 0.0],
        "beta": [0.2, 0.0],
        "kz": [0.2, 0.0],
        "vertical_sign": -1 if side == "bottom" else 1,
        "propagating": True,
        "power_carrying": True,
        "rayleigh_warning": False,
        "refractive_index": [1.0, 0.0],
        "boundary_phase": [1.0, 0.0],
        "outgoing_amplitude_at_boundary": amplitude,
        "power_ratio": (
            0.01 + offset + (order_m + 7) * 1.0e-5
            if significant
            else 1.0e-16
        ),
    }


def _write_fixture(
    root: Path,
    *,
    raw_mutator: Any = None,
) -> dict[str, Any]:
    samples = []
    for sample_id, role in _ROLES.items():
        run_directory = Path("artifacts") / sample_id
        raw_relative = "dtn_port_diffraction_orders_3d.json"
        raw_path = root / run_directory / raw_relative
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        orders = [
            _order(key, offset=_SAMPLE_OFFSETS[sample_id])
            for key in _all_keys()
        ]
        if raw_mutator is not None:
            raw_mutator(sample_id, orders)
        raw_path.write_text(
            json.dumps({"orders": orders}),
            encoding="utf-8",
        )

        source_sha = (sample_id.encode().hex() + "0" * 40)[:40]
        record = {
            "status": "fixture_pass",
            "qualification": {"pass": True},
            "source": {
                "commit_sha": source_sha,
                "stable_and_clean_after": True,
            },
            "raw_evidence": {"run_directory": str(run_directory)},
            "identity": {
                "geometry": GEOMETRY,
                "sample_id": sample_id,
            },
        }
        record_path = root / "records" / f"{sample_id}.json"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record), encoding="utf-8")
        samples.append(
            {
                "sample_id": sample_id,
                "role": role,
                "degree": (
                    "p5_trace_p6_interior"
                    if sample_id.startswith("fixed_")
                    else int(sample_id[1])
                ),
                "h_nm": 7.5 if "h7p5" in sample_id else (
                    5.0 if sample_id.endswith("_h5") else (
                        15.0 if "h15" in sample_id else 10.0
                    )
                ),
                "record_path": str(record_path.relative_to(root)),
                "record_sha256": _sha256(record_path),
                "source_sha": source_sha,
                "identity_class": "fixture_identity",
                "record_expectations": {
                    "status": "fixture_pass",
                    "qualification.pass": True,
                    "source.commit_sha": source_sha,
                    "source.stable_and_clean_after": True,
                    "identity.geometry": GEOMETRY,
                    "identity.sample_id": sample_id,
                },
                "raw_relative_to_run_directory": raw_relative,
                "raw_sha256": _sha256(raw_path),
                "raw_order_count": len(orders),
            }
        )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "geometry": GEOMETRY,
        "significant_power_floor": SIGNIFICANT_POWER_FLOOR,
        "power_tolerance_floor": POWER_TOLERANCE_FLOOR,
        "amplitude_tolerance_floor": AMPLITUDE_TOLERANCE_FLOOR,
        "expected_significant_channels": [
            {
                "side": side,
                "m": order_m,
                "n": order_n,
                "polarization": polarization,
            }
            for side, order_m, order_n, polarization
            in EXPECTED_SIGNIFICANT_CHANNELS
        ],
        "samples": samples,
        "cross_code_scalar_context": _write_comsol_fixture(root),
        "excluded_negative_evidence": [],
    }


def _sample(
    manifest: dict[str, Any],
    sample_id: str,
) -> dict[str, Any]:
    return next(
        sample
        for sample in manifest["samples"]
        if sample["sample_id"] == sample_id
    )


def _refresh_raw_sha(
    root: Path,
    manifest: dict[str, Any],
    sample_id: str,
) -> Path:
    sample = _sample(manifest, sample_id)
    record = json.loads(
        (root / sample["record_path"]).read_text(encoding="utf-8")
    )
    path = (
        root
        / record["raw_evidence"]["run_directory"]
        / sample["raw_relative_to_run_directory"]
    )
    sample["raw_sha256"] = _sha256(path)
    return path


def test_reference_freezes_exactly_12_channels_and_cli_outputs(
    tmp_path: Path,
) -> None:
    manifest = _write_fixture(tmp_path)
    record = build_significant_channel_reference(tmp_path, manifest)
    assert record["pass"] is True
    assert record["significant_channel_selection"]["channel_count"] == 12
    assert [
        (
            item["channel"]["side"],
            item["channel"]["m"],
            item["channel"]["n"],
            item["channel"]["polarization"],
        )
        for item in record["channels"]
    ] == list(EXPECTED_SIGNIFICANT_CHANNELS)
    assert all(
        item["unchanged_v0_acceptance_gate"][
            "unchanged_v0_formula_verified"
        ]
        for item in record["channels"]
    )
    assert record["reference_convergence_summary"][
        "all_12_channels_converged"
    ]
    assert not record["reference_convergence_summary"][
        "nonconverged_channels"
    ]
    cross_code = record["cross_code_scalar_context"]
    assert cross_code["convergence_center"] == {
        "R00": 0.000752895,
        "R_total": 0.000762014,
        "T_total": 0.6027075,
    }
    assert cross_code["excluded_from_channel_band"] is True
    assert cross_code["excluded_from_12_channel_gate"] is True
    assert cross_code["complex_channel_amplitudes"]["available"] is False
    assert cross_code["changes_unchanged_v0_acceptance_gate"] is False

    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "reference.json"
    markdown_path = tmp_path / "reference.md"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert (
        main(
            [
                "--repo-root",
                str(tmp_path),
                "--authority-manifest",
                str(manifest_path),
                "--output",
                str(output_path),
                "--markdown-output",
                str(markdown_path),
            ]
        )
        == 0
    )
    assert json.loads(output_path.read_text())["schema_version"].endswith(
        ".v1"
    )
    markdown = markdown_path.read_text()
    assert "| T(-7,0)_s |" in markdown
    assert "## COMSOL cross-code scalar context" in markdown
    assert "| excluded_from_channel_band | `true` |" in markdown
    assert "## FEniCS authority identity" in markdown


def test_phase_unwrap_uses_branch_nearest_p6_h10_center() -> None:
    center = math.radians(179.0)
    wrapped = math.radians(-179.0)
    unwrapped = unwrap_phase_near_center(wrapped, center)
    assert math.isclose(
        unwrapped,
        math.radians(181.0),
        rel_tol=0.0,
        abs_tol=1.0e-14,
    )


def test_diagnostic_values_cannot_expand_band_or_v0_gate(
    tmp_path: Path,
) -> None:
    manifest = _write_fixture(tmp_path)
    baseline = build_significant_channel_reference(tmp_path, manifest)

    for sample_id in (
        "p5_h15",
        "p6_h15",
        "fixed_p5trace_p6interior_h15",
    ):
        sample = _sample(manifest, sample_id)
        record = json.loads(
            (tmp_path / sample["record_path"]).read_text(encoding="utf-8")
        )
        raw_path = (
            tmp_path
            / record["raw_evidence"]["run_directory"]
            / sample["raw_relative_to_run_directory"]
        )
        raw = json.loads(raw_path.read_text())
        for order in raw["orders"]:
            if (
                order["side"],
                order["m"],
                order["n"],
                order["polarization"],
            ) in EXPECTED_SIGNIFICANT_CHANNELS:
                order["power_ratio"] = 1.0e6
                order["outgoing_amplitude_at_boundary"] = [1.0e6, -1.0e6]
        raw_path.write_text(json.dumps(raw), encoding="utf-8")
        _refresh_raw_sha(tmp_path, manifest, sample_id)

    changed = build_significant_channel_reference(tmp_path, manifest)
    for before, after in zip(
        baseline["channels"],
        changed["channels"],
        strict=True,
    ):
        assert (
            before["numerical_convergence_band"]
            == after["numerical_convergence_band"]
        )
        assert (
            before["unchanged_v0_acceptance_gate"]
            == after["unchanged_v0_acceptance_gate"]
        )
        assert after["underresolved_diagnostics_not_in_bands"]


def test_nonconverged_channel_fails_top_level_reference(
    tmp_path: Path,
) -> None:
    manifest = _write_fixture(tmp_path)
    raw_path = _refresh_raw_sha(tmp_path, manifest, "p4_h5")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    first_significant = next(
        order
        for order in raw["orders"]
        if (
            order["side"],
            order["m"],
            order["n"],
            order["polarization"],
        )
        in EXPECTED_SIGNIFICANT_CHANNELS
    )
    first_significant["power_ratio"] = 0.5
    first_significant["outgoing_amplitude_at_boundary"] = [0.5, -0.5]
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    _refresh_raw_sha(tmp_path, manifest, "p4_h5")

    record = build_significant_channel_reference(tmp_path, manifest)

    assert record["mechanical_validation_pass"] is True
    assert record["pass"] is False
    assert record["status"] == (
        "significant_channel_reference_v1_not_converged"
    )
    assert record["reference_convergence_summary"][
        "all_12_channels_converged"
    ] is False
    assert record["reference_convergence_summary"][
        "nonconverged_channels"
    ]


def test_missing_and_duplicate_channels_fail_closed(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"

    def remove_channel(sample_id: str, orders: list[dict[str, Any]]) -> None:
        if sample_id == "p4_h5":
            orders.pop(0)

    missing = _write_fixture(missing_root, raw_mutator=remove_channel)
    with pytest.raises(ValueError, match="missing T\\(-7,0\\)_s"):
        build_significant_channel_reference(missing_root, missing)

    duplicate_root = tmp_path / "duplicate"

    def duplicate_channel(
        sample_id: str,
        orders: list[dict[str, Any]],
    ) -> None:
        if sample_id == "p5_h10":
            orders[-1] = deepcopy(orders[0])

    duplicate = _write_fixture(
        duplicate_root,
        raw_mutator=duplicate_channel,
    )
    with pytest.raises(ValueError, match="duplicate channel"):
        build_significant_channel_reference(duplicate_root, duplicate)


def test_channel_and_record_identity_fail_closed(tmp_path: Path) -> None:
    channel_root = tmp_path / "channel"

    def corrupt_channel_identity(
        sample_id: str,
        orders: list[dict[str, Any]],
    ) -> None:
        if sample_id == "p4_h7p5":
            orders[0]["alpha"] = [123.0, 0.0]

    channel_manifest = _write_fixture(
        channel_root,
        raw_mutator=corrupt_channel_identity,
    )
    with pytest.raises(ValueError, match="analytic identity differs"):
        build_significant_channel_reference(
            channel_root,
            channel_manifest,
        )

    record_root = tmp_path / "record"
    record_manifest = _write_fixture(record_root)
    sample = _sample(record_manifest, "p6_h10")
    sample["source_sha"] = "f" * 40
    with pytest.raises(ValueError, match="source SHA identity mismatch"):
        build_significant_channel_reference(record_root, record_manifest)


def test_comsol_scalar_table_identity_fails_closed(tmp_path: Path) -> None:
    manifest = _write_fixture(tmp_path)
    context = manifest["cross_code_scalar_context"]
    path = tmp_path / context["authority_document_path"]
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("0.000752895 | 0.000762014", "0.000752999 | 0.000762014"),
        encoding="utf-8",
    )
    context["authority_document_sha256"] = _sha256(path)
    with pytest.raises(ValueError, match="COMSOL row mismatch"):
        build_significant_channel_reference(tmp_path, manifest)

    manifest = _write_fixture(tmp_path / "scope")
    manifest["cross_code_scalar_context"][
        "complex_channel_amplitudes_available"
    ] = True
    with pytest.raises(
        ValueError,
        match="complex_channel_amplitudes_available",
    ):
        build_significant_channel_reference(tmp_path / "scope", manifest)
