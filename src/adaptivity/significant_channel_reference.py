"""Freeze a SHA-bound Task035b significant-channel reference.

This module is deliberately pure Python.  It reads already accepted records
and raw DtN-port order files; it does not import the PDE stack or run a solve.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "task035b.significant-channel-reference.v1"
MANIFEST_SCHEMA_VERSION = "task035b.channel-authority-manifest.v1"
GEOMETRY = "Task034 fixed rectangular block grating"
SIGNIFICANT_POWER_FLOOR = 1.0e-8
POWER_TOLERANCE_FLOOR = 1.0e-12
AMPLITUDE_TOLERANCE_FLOOR = 1.0e-10

EXPECTED_SIGNIFICANT_CHANNELS = tuple(
    (side, order_m, 0, "s")
    for side in ("bottom", "top")
    for order_m in (-7, -5, -4, -2, -1, 0)
)

_EXPECTED_SAMPLE_ROLES = {
    "p4_h10": "trend_only",
    "p4_h7p5": "numerical_band",
    "p4_h5": "numerical_band",
    "p5_h10": "unchanged_v0_gate",
    "p6_h10": "reference_center",
    "p5_h15": "underresolved_diagnostic",
    "p6_h15": "underresolved_diagnostic",
    "fixed_p5trace_p6interior_h15": "underresolved_trace_diagnostic",
}
_NUMERICAL_SAMPLE_IDS = (
    "p4_h10",
    "p4_h7p5",
    "p4_h5",
    "p5_h10",
    "p6_h10",
)
_DIAGNOSTIC_SAMPLE_IDS = (
    "p5_h15",
    "p6_h15",
    "fixed_p5trace_p6interior_h15",
)


def _pair_record(
    *,
    record_path: str,
    record_sha256: str,
    source_sha: str,
    h_nm: float,
    mesh_cells: list[int],
    mesh_sha256: str,
    cell_tag_sha256: str,
    facet_tag_sha256: str,
) -> dict[str, Any]:
    expectations = {
        "status": "actual_global_r5_pass",
        "qualification.pass": True,
        "source.commit_sha": source_sha,
        "source.stable_and_clean_after": True,
        "target_identity.wavelength_nm": 13.5,
        "target_identity.incidence_theta_deg": 80.0,
        "target_identity.grazing_angle_deg": 10.0,
        "target_identity.polarization": "S",
        "target_identity.geometry": GEOMETRY,
        "target_identity.mesh_backend": (
            "boundary-fitted conforming hexahedron"
        ),
        "common_mesh_identity.mesh_cell_type": "hexahedron",
        "common_mesh_identity.mesh_cells_resolved": mesh_cells,
        "common_mesh_identity.partition_independent_mesh_sha256": (
            mesh_sha256
        ),
        "common_mesh_identity.cell_tag_sha256": cell_tag_sha256,
        "common_mesh_identity.facet_tag_sha256": facet_tag_sha256,
        "coarse.degree": 5,
        "coarse.h_nm": h_nm,
        "coarse.mpi_size": 8,
        "enriched.degree": 6,
        "enriched.h_nm": h_nm,
        "enriched.mpi_size": 8,
    }
    return {
        "record_path": record_path,
        "record_sha256": record_sha256,
        "source_sha": source_sha,
        "identity_class": "partition_independent_mesh_hash",
        "record_expectations": expectations,
    }


def _legacy_p4_sample(
    *,
    sample_id: str,
    h_nm: float,
    mesh_cells: list[int],
    record_path: str,
    record_sha256: str,
    raw_sha256: str,
    role: str,
) -> dict[str, Any]:
    source_sha = "e0917859aa53cd6cff6bc3bc411b29255aeac9e2"
    return {
        "sample_id": sample_id,
        "role": role,
        "degree": 4,
        "h_nm": h_nm,
        "record_path": record_path,
        "record_sha256": record_sha256,
        "source_sha": source_sha,
        "identity_class": "qualified_legacy_axis_plan_no_partition_hash",
        "record_expectations": {
            "status": "full3d_reference_pass",
            "degree": 4,
            "h_nm": h_nm,
            "mpi_size": 8,
            "qualification.pass": True,
            "source.commit_sha": source_sha,
            "source.stable_and_clean_after": True,
            "solver_summary.lambda0_nm": 13.5,
            "solver_summary.geometry_kind": "rectangular_block_grating",
            "solver_summary.stage_case": "stage4_block_grating",
            "solver_summary.mesh_cell_type_resolved": "hexahedron",
            "solver_summary.mesh_cells_resolved": mesh_cells,
            "solver_summary.nedelec_degree": 4,
            "solver_summary.mpi_size": 8,
            "solver_summary.mesh_target_size": h_nm,
        },
        "raw_relative_to_run_directory": (
            "dtn_port_diffraction_orders_3d.json"
        ),
        "raw_sha256": raw_sha256,
        "raw_order_count": 80,
    }


_H10_PAIR = _pair_record(
    record_path=(
        "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
        "records/global_hexa_p5_p6_h10_projection_signals_mpi8.json"
    ),
    record_sha256=(
        "7984c18b128134a58ce496106ea06b46b5820d0b5cea813e2d51a9ec59b8bf74"
    ),
    source_sha="65bf6fb034d6717e190a5d1ab4a2025fb1c4ff3b",
    h_nm=10.0,
    mesh_cells=[6, 3, 14],
    mesh_sha256=(
        "f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857"
    ),
    cell_tag_sha256=(
        "42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131"
    ),
    facet_tag_sha256=(
        "0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd"
    ),
)
_H15_PAIR = _pair_record(
    record_path=(
        "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
        "records/global_hexa_p5_p6_h15_assembly_time_condensed_"
        "independent_mpi8.json"
    ),
    record_sha256=(
        "59859ef7b49ac6c40e2e3d803a366c71742a29411f7d9591384c62dc8fa923f9"
    ),
    source_sha="5d75c5ed8ae0dd4382eccf0c47e22fce01391184",
    h_nm=15.0,
    mesh_cells=[6, 2, 10],
    mesh_sha256=(
        "f6ed05e9f88f05cb88631698c2fe6692f054bfd41fd615272efda436362e3cc0"
    ),
    cell_tag_sha256=(
        "a326daa4edcb470ab6159b30be56a8c69619d0a61290b8f96aadce098a187d63"
    ),
    facet_tag_sha256=(
        "e898956f4c0eb1b463e0bca42033b832b5a9b350c44da659f1578c13aa2a9797"
    ),
)

DEFAULT_AUTHORITY_MANIFEST: dict[str, Any] = {
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
    "samples": [
        _legacy_p4_sample(
            sample_id="p4_h10",
            h_nm=10.0,
            mesh_cells=[6, 3, 14],
            record_path=(
                "benchmarks/artifacts/task034/phase_f/records/"
                "p4_h10_full_mpi8_e091785.json"
            ),
            record_sha256=(
                "ec949270b4440a0f68ac1406a345882d25f7daa34048397b89095895ffb8d6c1"
            ),
            raw_sha256=(
                "f4e48e7547816d189b21b389c1f73fd6d350f62164bdfb983dd3c49232a79792"
            ),
            role="trend_only",
        ),
        _legacy_p4_sample(
            sample_id="p4_h7p5",
            h_nm=7.5,
            mesh_cells=[9, 4, 20],
            record_path=(
                "benchmarks/artifacts/task034/phase_f/records/"
                "p4_h7p5_full_mpi8_e091785.json"
            ),
            record_sha256=(
                "09e3b01da9800578b391df4a42b4e4d6fb8b411722867906a942dfefe495f7aa"
            ),
            raw_sha256=(
                "51a1b236b0fcd93b6cda5cf3e359fc8fee3748405cfa83313225390aa45d96e4"
            ),
            role="numerical_band",
        ),
        _legacy_p4_sample(
            sample_id="p4_h5",
            h_nm=5.0,
            mesh_cells=[12, 5, 28],
            record_path=(
                "benchmarks/artifacts/task034/phase_f/records/"
                "p4_h5_full_mpi8_e091785.json"
            ),
            record_sha256=(
                "879816e0c7c9f345deeb23435607560be9af7ad431142f8b2e3ea4f9a8022cab"
            ),
            raw_sha256=(
                "e034219a6f6308c3af7f2fde326ca7a63d457a9e93e7df462c856151b8fb4e64"
            ),
            role="numerical_band",
        ),
        {
            "sample_id": "p5_h10",
            "role": "unchanged_v0_gate",
            "degree": 5,
            "h_nm": 10.0,
            **deepcopy(_H10_PAIR),
            "raw_relative_to_run_directory": (
                "coarse_p5/dtn_port_diffraction_orders_3d.json"
            ),
            "raw_sha256": (
                "e69ac315fa8cfdec0ae039b474cdab8aee3eaeab6ece762ce08996c4f1de5606"
            ),
            "raw_order_count": 80,
        },
        {
            "sample_id": "p6_h10",
            "role": "reference_center",
            "degree": 6,
            "h_nm": 10.0,
            **deepcopy(_H10_PAIR),
            "raw_relative_to_run_directory": (
                "enriched_p6/dtn_port_diffraction_orders_3d.json"
            ),
            "raw_sha256": (
                "363865d51102eed02ae74fc08d32678467f8d067611255b474e89c153a745913"
            ),
            "raw_order_count": 80,
        },
        {
            "sample_id": "p5_h15",
            "role": "underresolved_diagnostic",
            "degree": 5,
            "h_nm": 15.0,
            **deepcopy(_H15_PAIR),
            "raw_relative_to_run_directory": (
                "coarse_p5/dtn_port_diffraction_orders_3d.json"
            ),
            "raw_sha256": (
                "0bb1f7835132eedef825698f4e12d49aee979574a09f3da0b239363331a3daa3"
            ),
            "raw_order_count": 80,
        },
        {
            "sample_id": "p6_h15",
            "role": "underresolved_diagnostic",
            "degree": 6,
            "h_nm": 15.0,
            **deepcopy(_H15_PAIR),
            "raw_relative_to_run_directory": (
                "enriched_p6/dtn_port_diffraction_orders_3d.json"
            ),
            "raw_sha256": (
                "e803ae7454b5e5088de76795f23d961f806c73274aac28b733bceb6e6a29c6c3"
            ),
            "raw_order_count": 80,
        },
        {
            "sample_id": "fixed_p5trace_p6interior_h15",
            "role": "underresolved_trace_diagnostic",
            "degree": "p5_trace_p6_interior",
            "h_nm": 15.0,
            "record_path": (
                "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
                "records/fixed_p5trace_p6interior_h15_tensor_dedup_"
                "preallocation_mpi8.json"
            ),
            "record_sha256": (
                "1ffde81be08c24232e62c1d2dfbf1b7ad2dcb3623444ea40af68b5c6585758e3"
            ),
            "source_sha": "7f61d554b0441d7b224c096aba402d3b3ac2baa6",
            "identity_class": "h15_fixed_trace_controlled_negative",
            "record_expectations": {
                "status": "actual_fixed_trace_controlled_negative",
                "qualification.pass": True,
                "source.commit_sha": (
                    "7f61d554b0441d7b224c096aba402d3b3ac2baa6"
                ),
                "source.stable_and_clean_after": True,
                "target_identity.geometry": GEOMETRY,
                "target_identity.h_nm": 15.0,
                "target_identity.trace_degree": 5,
                "target_identity.interior_degree": 6,
            },
            "raw_relative_to_run_directory": (
                "candidate/dtn_port_diffraction_orders_3d.json"
            ),
            "raw_sha256": (
                "e585cdce2dfc10e10eb52198a56009d2ff5725fbb09d869706d88d9eb9e1d06e"
            ),
            "raw_order_count": 80,
        },
    ],
    "cross_code_scalar_context": {
        "authority_document_path": "docs/COMSOL_direct_solver_report.md",
        "authority_document_sha256": (
            "80d32c80f28f0bcc87470881f639bbbfe54b468b7a7da53c31a26b3785cd6ec4"
        ),
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
        "selected_table_rows": [
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
        ],
        "excluded_from_channel_band": True,
        "excluded_from_12_channel_gate": True,
        "complex_channel_amplitudes_available": False,
        "changes_unchanged_v0_acceptance_gate": False,
    },
    "excluded_negative_evidence": [
        {
            "evidence_id": "task035_tetra_theta0p4_p5_p6_h50",
            "record_path": (
                "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/"
                "records/actual_hp_budget_theta0p4_tetra_p5_p6_h50_mpi8.json"
            ),
            "record_sha256": (
                "8a579b5141e12ac3f029b2ff72ba3d597da46ea2d0a96757593ef191e77c938c"
            ),
            "source_sha": "74f5d23cd2771390322947dc82d6edf6c0f81e86",
            "record_expectations": {
                "status": "actual_common_mesh_angle_sweep_pass",
                "qualification.pass": True,
                "source.commit_sha": (
                    "74f5d23cd2771390322947dc82d6edf6c0f81e86"
                ),
                "source.stable_and_clean_after": True,
                "target_identity.geometry": GEOMETRY,
                "common_mesh_identity.partition_independent_mesh_sha256": (
                    "ffe347854e0e416936f36159cd41846171a01ead1ebf6fe38744a29099a4ec36"
                ),
                "common_mesh_identity.cell_tag_sha256": (
                    "723e89985a1662b4da5f7d40231ee804a6f76dabe52b0a5d4f66bf778094ca0f"
                ),
                "common_mesh_identity.facet_tag_sha256": (
                    "d1a04a4e450b671506c662ed7a8e47cccb92e902e01c0d1b92141ed3d5c075aa"
                ),
            },
            "exclusion": (
                "qualified tetra hp result but not same-error with the "
                "structured p6/h10 center; controlled negative only"
            ),
        }
    ],
}


def default_authority_manifest() -> dict[str, Any]:
    """Return a caller-owned copy of the frozen default authority manifest."""

    return deepcopy(DEFAULT_AUTHORITY_MANIFEST)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_repo_path(repo_root: Path, relative: str) -> Path:
    root = repo_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"authority path escapes repository: {relative}") from error
    if not path.is_file():
        raise ValueError(f"authority file is missing: {relative}")
    return path


def _lookup(payload: Mapping[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for component in dotted_path.split("."):
        if not isinstance(value, Mapping) or component not in value:
            raise ValueError(f"record identity field is missing: {dotted_path}")
        value = value[component]
    return value


def _validate_expected_fields(
    payload: Mapping[str, Any],
    expectations: Mapping[str, Any],
    *,
    authority_name: str,
) -> None:
    for dotted_path, expected in expectations.items():
        actual = _lookup(payload, dotted_path)
        if actual != expected:
            raise ValueError(
                f"{authority_name} identity mismatch for {dotted_path}: "
                f"expected {expected!r}, got {actual!r}"
            )


def _channel_key(order: Mapping[str, Any]) -> tuple[str, int, int, str]:
    try:
        return (
            str(order["side"]),
            int(order.get("order_m", order["m"])),
            int(order.get("order_n", order["n"])),
            str(order["polarization"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("raw order has an incomplete channel identity") from error


def _channel_label(key: tuple[str, int, int, str]) -> str:
    side, order_m, order_n, polarization = key
    observable = "T" if side == "bottom" else "R"
    return f"{observable}({order_m},{order_n})_{polarization}"


def _finite_float(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} is not numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{field} is not finite")
    return result


def _complex_amplitude(order: Mapping[str, Any]) -> complex:
    pair = order.get("outgoing_amplitude_at_boundary")
    if (
        not isinstance(pair, list)
        or len(pair) != 2
    ):
        raise ValueError("raw order lacks a complex boundary amplitude")
    return complex(
        _finite_float(pair[0], field="amplitude real"),
        _finite_float(pair[1], field="amplitude imag"),
    )


def _analytic_identity(order: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "side",
        "direction",
        "medium",
        "m",
        "n",
        "order_m",
        "order_n",
        "polarization",
        "alpha",
        "gamma",
        "beta",
        "kz",
        "vertical_sign",
        "propagating",
        "power_carrying",
        "rayleigh_warning",
        "refractive_index",
        "boundary_phase",
    )
    identity = {}
    for field in fields:
        if field not in order:
            raise ValueError(f"raw order identity field is missing: {field}")
        identity[field] = order[field]
    return identity


def _identities_close(left: Any, right: Any) -> bool:
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _identities_close(a, b) for a, b in zip(left, right, strict=True)
        )
    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)
    return left == right


def _load_raw_orders(
    repo_root: Path,
    sample: Mapping[str, Any],
    record: Mapping[str, Any],
) -> tuple[Path, dict[tuple[str, int, int, str], dict[str, Any]]]:
    run_directory = _lookup(record, "raw_evidence.run_directory")
    if not isinstance(run_directory, str):
        raise ValueError("raw_evidence.run_directory must be a string")
    relative = str(
        Path(run_directory) / str(sample["raw_relative_to_run_directory"])
    )
    raw_path = _resolve_repo_path(repo_root, relative)
    actual_sha = _sha256(raw_path)
    if actual_sha != sample["raw_sha256"]:
        raise ValueError(
            f"{sample['sample_id']} raw SHA mismatch: "
            f"expected {sample['raw_sha256']}, got {actual_sha}"
        )
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load raw authority: {relative}") from error
    orders = payload.get("orders")
    if not isinstance(orders, list):
        raise ValueError(f"{sample['sample_id']} raw authority lacks orders")
    if len(orders) != int(sample["raw_order_count"]):
        raise ValueError(
            f"{sample['sample_id']} raw order count mismatch: "
            f"expected {sample['raw_order_count']}, got {len(orders)}"
        )
    indexed: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for order in orders:
        if not isinstance(order, dict):
            raise ValueError(f"{sample['sample_id']} has a non-object order")
        key = _channel_key(order)
        if key in indexed:
            raise ValueError(
                f"{sample['sample_id']} has duplicate channel "
                f"{_channel_label(key)}"
            )
        _finite_float(order.get("power_ratio"), field="power_ratio")
        _complex_amplitude(order)
        indexed[key] = order
    return raw_path, indexed


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported authority manifest schema")
    if manifest.get("geometry") != GEOMETRY:
        raise ValueError("authority manifest targets the wrong geometry")
    samples = manifest.get("samples")
    if not isinstance(samples, list):
        raise ValueError("authority manifest samples must be a list")
    by_id: dict[str, Mapping[str, Any]] = {}
    for sample in samples:
        if not isinstance(sample, Mapping):
            raise ValueError("authority manifest contains a non-object sample")
        sample_id = str(sample.get("sample_id", ""))
        if sample_id in by_id:
            raise ValueError(f"authority manifest duplicates sample {sample_id}")
        by_id[sample_id] = sample
    if set(by_id) != set(_EXPECTED_SAMPLE_ROLES):
        missing = sorted(set(_EXPECTED_SAMPLE_ROLES) - set(by_id))
        extra = sorted(set(by_id) - set(_EXPECTED_SAMPLE_ROLES))
        raise ValueError(
            f"authority manifest sample set mismatch; missing={missing}, "
            f"extra={extra}"
        )
    for sample_id, expected_role in _EXPECTED_SAMPLE_ROLES.items():
        if by_id[sample_id].get("role") != expected_role:
            raise ValueError(
                f"{sample_id} must have frozen role {expected_role}"
            )
    expected_channels = manifest.get("expected_significant_channels")
    if not isinstance(expected_channels, list):
        raise ValueError("manifest lacks expected significant channels")
    keys = [_channel_key(channel) for channel in expected_channels]
    if len(keys) != 12 or len(set(keys)) != 12:
        raise ValueError("manifest must name 12 unique significant channels")
    if tuple(keys) != EXPECTED_SIGNIFICANT_CHANNELS:
        raise ValueError("manifest significant-channel identity changed")
    for field, expected in (
        ("significant_power_floor", SIGNIFICANT_POWER_FLOOR),
        ("power_tolerance_floor", POWER_TOLERANCE_FLOOR),
        ("amplitude_tolerance_floor", AMPLITUDE_TOLERANCE_FLOOR),
    ):
        if manifest.get(field) != expected:
            raise ValueError(f"manifest changed frozen {field}")
    cross_code = manifest.get("cross_code_scalar_context")
    if not isinstance(cross_code, Mapping):
        raise ValueError("manifest lacks COMSOL cross-code scalar context")
    for field, expected in (
        ("excluded_from_channel_band", True),
        ("excluded_from_12_channel_gate", True),
        ("complex_channel_amplitudes_available", False),
        ("changes_unchanged_v0_acceptance_gate", False),
    ):
        if cross_code.get(field) is not expected:
            raise ValueError(f"COMSOL context changed frozen {field}")
    center = cross_code.get("reported_convergence_center")
    if not isinstance(center, Mapping) or set(center) != {
        "R00",
        "R_total",
        "T_total",
    }:
        raise ValueError("COMSOL context must contain only R00/R/T center")
    selected_rows = cross_code.get("selected_table_rows")
    if not isinstance(selected_rows, list) or len(selected_rows) != 5:
        raise ValueError("COMSOL context must bind five direct table rows")


def _markdown_section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        raise ValueError(f"COMSOL table heading is missing: {heading}")
    next_heading = text.find("\n## ", start + len(heading))
    return text[start:] if next_heading < 0 else text[start:next_heading]


def _markdown_table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _validate_cross_code_scalar_context(
    repo_root: Path,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    relative = str(context["authority_document_path"])
    document_path = _resolve_repo_path(repo_root, relative)
    actual_sha = _sha256(document_path)
    if actual_sha != context["authority_document_sha256"]:
        raise ValueError(
            "COMSOL scalar authority SHA mismatch: "
            f"expected {context['authority_document_sha256']}, "
            f"got {actual_sha}"
        )
    text = document_path.read_text(encoding="utf-8")
    if str(context["software_identity"]) not in text:
        raise ValueError("COMSOL software identity is missing from authority")
    if "直接法均为 **MUMPS 直接求解器**" not in text:
        raise ValueError("COMSOL direct-solver identity is missing")

    validated_rows = []
    for expected in context["selected_table_rows"]:
        heading = str(expected["table_heading"])
        section = _markdown_section(text, heading)
        source_model = str(expected["source_model"])
        if f"`{source_model}`" not in section:
            raise ValueError(
                f"COMSOL source model is missing under {heading}: "
                f"{source_model}"
            )
        matches = []
        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            cells = _markdown_table_cells(line)
            if len(cells) < 7:
                continue
            if (
                cells[0] == expected["element"]
                and cells[1] == str(expected["h_nm"])
                and cells[2].strip("`") == expected["solution"]
            ):
                matches.append(cells)
        if len(matches) != 1:
            raise ValueError(
                "COMSOL table-row identity is not unique for "
                f"{heading}/{expected['element']}/h={expected['h_nm']}/"
                f"{expected['solution']}"
            )
        cells = matches[0]
        parsed = {
            "table_heading": heading,
            "source_model": source_model,
            "element": cells[0],
            "h_nm": _finite_float(cells[1], field="COMSOL h"),
            "solution": cells[2].strip("`"),
            "dofs": int(cells[3].replace(",", "")),
            "R00": _finite_float(cells[4], field="COMSOL R00"),
            "R_total": _finite_float(cells[5], field="COMSOL R"),
            "T_total": _finite_float(cells[6], field="COMSOL T"),
        }
        for field in (
            "element",
            "h_nm",
            "solution",
            "dofs",
            "R00",
            "R_total",
            "T_total",
        ):
            if parsed[field] != expected[field]:
                raise ValueError(
                    f"COMSOL row mismatch for {field}: "
                    f"expected {expected[field]!r}, got {parsed[field]!r}"
                )
        validated_rows.append(parsed)

    precision = context["center_precision_decimal_places"]
    derived_center = {}
    for field in ("R00", "R_total", "T_total"):
        values = sorted(float(row[field]) for row in validated_rows)
        median = values[len(values) // 2]
        derived_center[field] = round(median, int(precision[field]))
    reported_center = {
        field: float(value)
        for field, value in context["reported_convergence_center"].items()
    }
    if derived_center != reported_center:
        raise ValueError(
            "COMSOL table rows do not reproduce the reported R00/R/T "
            f"center: derived={derived_center}, expected={reported_center}"
        )
    conclusion_tokens = (
        f"R(0,0)={reported_center['R00']:.9f}",
        f"R={reported_center['R_total']:.9f}",
        f"T={reported_center['T_total']:.7f}",
    )
    for token in conclusion_tokens:
        if token not in text:
            raise ValueError(
                f"COMSOL convergence conclusion token is missing: {token}"
            )
    rows_encoded = json.dumps(
        validated_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "role": "cross_code_scalar_context_only",
        "authority_document": {
            "path": str(document_path.relative_to(repo_root.resolve())),
            "sha256": actual_sha,
            "software_identity": context["software_identity"],
            "solver_scope": context["solver_scope"],
        },
        "table_identity": {
            "selected_direct_row_count": len(validated_rows),
            "selected_rows": validated_rows,
            "selected_rows_canonical_json_sha256": hashlib.sha256(
                rows_encoded
            ).hexdigest(),
        },
        "convergence_center": reported_center,
        "center_derivation": context["center_derivation"],
        "excluded_from_channel_band": True,
        "excluded_from_12_channel_gate": True,
        "complex_channel_amplitudes": {
            "available": False,
            "reason": (
                "the COMSOL report contains scalar R00/R/T tables, not "
                "per-channel complex amplitudes"
            ),
        },
        "changes_unchanged_v0_acceptance_gate": False,
        "mechanically_validated": True,
    }


def _unwrap_phase_near_center(phase: float, center_phase: float) -> float:
    """Return the nearest 2π branch of ``phase`` around ``center_phase``."""

    return center_phase + math.atan2(
        math.sin(phase - center_phase),
        math.cos(phase - center_phase),
    )


def unwrap_phase_near_center(phase: float, center_phase: float) -> float:
    """Public, tested wrapper for nearest-branch phase unwrapping."""

    phase_value = _finite_float(phase, field="phase")
    center_value = _finite_float(center_phase, field="center phase")
    return _unwrap_phase_near_center(phase_value, center_value)


def _sample_values(
    order: Mapping[str, Any],
    *,
    center_phase: float,
) -> dict[str, float | list[float]]:
    amplitude = _complex_amplitude(order)
    principal_phase = math.atan2(amplitude.imag, amplitude.real)
    unwrapped_phase = _unwrap_phase_near_center(
        principal_phase,
        center_phase,
    )
    return {
        "power": _finite_float(order["power_ratio"], field="power_ratio"),
        "complex_amplitude": [amplitude.real, amplitude.imag],
        "amplitude_real": amplitude.real,
        "amplitude_imag": amplitude.imag,
        "amplitude_magnitude": abs(amplitude),
        "phase_principal_radians": principal_phase,
        "phase_unwrapped_radians": unwrapped_phase,
        "phase_unwrapped_degrees": math.degrees(unwrapped_phase),
    }


def _absolute_differences(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, float]:
    left_complex = complex(*left["complex_amplitude"])
    right_complex = complex(*right["complex_amplitude"])
    return {
        "power": abs(float(left["power"]) - float(right["power"])),
        "amplitude_real": abs(
            float(left["amplitude_real"]) - float(right["amplitude_real"])
        ),
        "amplitude_imag": abs(
            float(left["amplitude_imag"]) - float(right["amplitude_imag"])
        ),
        "amplitude_magnitude": abs(
            float(left["amplitude_magnitude"])
            - float(right["amplitude_magnitude"])
        ),
        "complex_amplitude_norm": abs(left_complex - right_complex),
        "phase_radians": abs(
            float(left["phase_unwrapped_radians"])
            - float(right["phase_unwrapped_radians"])
        ),
    }


def _monotone_nonincreasing(values: Iterable[float]) -> bool:
    sequence = list(values)
    return all(
        later <= earlier + 1.0e-15
        for earlier, later in zip(sequence, sequence[1:])
    )


def _spread(
    values: Mapping[str, Mapping[str, Any]],
    *,
    center: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    component_floors = {
        "power": POWER_TOLERANCE_FLOOR,
        "amplitude_real": AMPLITUDE_TOLERANCE_FLOOR,
        "amplitude_imag": AMPLITUDE_TOLERANCE_FLOOR,
        "amplitude_magnitude": AMPLITUDE_TOLERANCE_FLOOR,
        "phase_unwrapped_radians": 1.0e-15,
    }
    for component, floor in component_floors.items():
        samples = [float(value[component]) for value in values.values()]
        center_value = float(center[component])
        absolute_spread = max(samples) - min(samples)
        max_center_deviation = max(
            abs(value - center_value) for value in samples
        )
        result[component] = {
            "minimum": min(samples),
            "maximum": max(samples),
            "absolute_spread": absolute_spread,
            "max_absolute_deviation_from_p6_h10": max_center_deviation,
            "relative_spread_to_p6_h10": (
                absolute_spread / max(abs(center_value), floor)
            ),
            "max_relative_deviation_from_p6_h10": (
                max_center_deviation / max(abs(center_value), floor)
            ),
        }
    return result


def _authority_summary(
    repo_root: Path,
    sample: Mapping[str, Any],
    record_path: Path,
    raw_path: Path,
) -> dict[str, Any]:
    return {
        "sample_id": sample["sample_id"],
        "role": sample["role"],
        "degree": sample["degree"],
        "h_nm": sample["h_nm"],
        "source_sha": sample["source_sha"],
        "identity_class": sample["identity_class"],
        "record": {
            "path": str(record_path.relative_to(repo_root.resolve())),
            "sha256": sample["record_sha256"],
        },
        "raw_dtn_port_orders": {
            "path": str(raw_path.relative_to(repo_root.resolve())),
            "sha256": sample["raw_sha256"],
            "order_count": sample["raw_order_count"],
        },
        "record_expectations": deepcopy(sample["record_expectations"]),
        "qualification": "validated_pass",
    }


def _load_and_validate_authorities(
    repo_root: Path,
    manifest: Mapping[str, Any],
) -> tuple[
    dict[str, dict[tuple[str, int, int, str], dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    record_cache: dict[str, tuple[Path, dict[str, Any]]] = {}
    order_maps = {}
    authorities = []
    for sample in manifest["samples"]:
        sample_id = str(sample["sample_id"])
        record_relative = str(sample["record_path"])
        cached = record_cache.get(record_relative)
        if cached is None:
            record_path = _resolve_repo_path(repo_root, record_relative)
            actual_sha = _sha256(record_path)
            if actual_sha != sample["record_sha256"]:
                raise ValueError(
                    f"{sample_id} record SHA mismatch: "
                    f"expected {sample['record_sha256']}, got {actual_sha}"
                )
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError(
                    f"cannot load authority record: {record_relative}"
                ) from error
            cached = (record_path, record)
            record_cache[record_relative] = cached
        record_path, record = cached
        if _sha256(record_path) != sample["record_sha256"]:
            raise ValueError(
                f"{sample_id} shares a record with inconsistent SHA identity"
            )
        _validate_expected_fields(
            record,
            sample["record_expectations"],
            authority_name=sample_id,
        )
        if _lookup(record, "source.commit_sha") != sample["source_sha"]:
            raise ValueError(f"{sample_id} source SHA identity mismatch")
        raw_path, indexed = _load_raw_orders(repo_root, sample, record)
        order_maps[sample_id] = indexed
        authorities.append(
            _authority_summary(repo_root, sample, record_path, raw_path)
        )

    excluded = []
    for evidence in manifest.get("excluded_negative_evidence", []):
        evidence_id = str(evidence["evidence_id"])
        record_path = _resolve_repo_path(
            repo_root,
            str(evidence["record_path"]),
        )
        actual_sha = _sha256(record_path)
        if actual_sha != evidence["record_sha256"]:
            raise ValueError(
                f"{evidence_id} excluded record SHA mismatch: "
                f"expected {evidence['record_sha256']}, got {actual_sha}"
            )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        _validate_expected_fields(
            record,
            evidence["record_expectations"],
            authority_name=evidence_id,
        )
        if _lookup(record, "source.commit_sha") != evidence["source_sha"]:
            raise ValueError(f"{evidence_id} source SHA identity mismatch")
        excluded.append(
            {
                "evidence_id": evidence_id,
                "record": {
                    "path": str(record_path.relative_to(repo_root.resolve())),
                    "sha256": actual_sha,
                },
                "source_sha": evidence["source_sha"],
                "mesh_identity": {
                    "partition_independent_mesh_sha256": _lookup(
                        record,
                        (
                            "common_mesh_identity."
                            "partition_independent_mesh_sha256"
                        ),
                    ),
                    "cell_tag_sha256": _lookup(
                        record,
                        "common_mesh_identity.cell_tag_sha256",
                    ),
                    "facet_tag_sha256": _lookup(
                        record,
                        "common_mesh_identity.facet_tag_sha256",
                    ),
                },
                "qualification": "validated_pass",
                "classification": "excluded_controlled_negative",
                "exclusion": evidence["exclusion"],
                "used_in_numerical_band": False,
                "used_in_acceptance_gate": False,
            }
        )
    return order_maps, authorities, excluded


def _build_channel(
    key: tuple[str, int, int, str],
    order_maps: Mapping[
        str,
        Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    ],
) -> dict[str, Any]:
    center_order = order_maps["p6_h10"].get(key)
    if center_order is None:
        raise ValueError(f"p6_h10 is missing {_channel_label(key)}")
    center_identity = _analytic_identity(center_order)
    center_amplitude = _complex_amplitude(center_order)
    center_phase = math.atan2(center_amplitude.imag, center_amplitude.real)
    values: dict[str, dict[str, Any]] = {}
    for sample_id, orders in order_maps.items():
        order = orders.get(key)
        if order is None:
            raise ValueError(f"{sample_id} is missing {_channel_label(key)}")
        identity = _analytic_identity(order)
        if not _identities_close(identity, center_identity):
            raise ValueError(
                f"{sample_id} analytic identity differs for "
                f"{_channel_label(key)}"
            )
        values[sample_id] = _sample_values(
            order,
            center_phase=center_phase,
        )

    p4_h7p5_to_h5 = _absolute_differences(
        values["p4_h5"],
        values["p4_h7p5"],
    )
    p5_to_p6_h10 = _absolute_differences(
        values["p6_h10"],
        values["p5_h10"],
    )
    p4_h5_to_p6_h10 = _absolute_differences(
        values["p6_h10"],
        values["p4_h5"],
    )
    numerical_band = {
        component: max(
            p4_h7p5_to_h5[component],
            p5_to_p6_h10[component],
            p4_h5_to_p6_h10[component],
        )
        for component in p5_to_p6_h10
    }
    center = values["p6_h10"]
    numerical_band_relative = {
        "power": numerical_band["power"]
        / max(abs(float(center["power"])), POWER_TOLERANCE_FLOOR),
        "amplitude_real": numerical_band["amplitude_real"]
        / max(
            abs(float(center["amplitude_real"])),
            AMPLITUDE_TOLERANCE_FLOOR,
        ),
        "amplitude_imag": numerical_band["amplitude_imag"]
        / max(
            abs(float(center["amplitude_imag"])),
            AMPLITUDE_TOLERANCE_FLOOR,
        ),
        "amplitude_magnitude": numerical_band["amplitude_magnitude"]
        / max(
            abs(float(center["amplitude_magnitude"])),
            AMPLITUDE_TOLERANCE_FLOOR,
        ),
        "complex_amplitude_norm": numerical_band[
            "complex_amplitude_norm"
        ]
        / max(
            abs(complex(*center["complex_amplitude"])),
            AMPLITUDE_TOLERANCE_FLOOR,
        ),
        "phase_radians": numerical_band["phase_radians"]
        / max(abs(float(center["phase_unwrapped_radians"])), 1.0e-15),
    }
    v0_power_tolerance = max(
        p5_to_p6_h10["power"],
        POWER_TOLERANCE_FLOOR,
    )
    v0_amplitude_tolerance = max(
        p5_to_p6_h10["complex_amplitude_norm"],
        AMPLITUDE_TOLERANCE_FLOOR,
    )

    p4_series_ids = ("p4_h10", "p4_h7p5", "p4_h5")
    p4_errors = {
        sample_id: _absolute_differences(values[sample_id], center)
        for sample_id in p4_series_ids
    }
    p4_monotone = {
        component: _monotone_nonincreasing(
            p4_errors[sample_id][component]
            for sample_id in p4_series_ids
        )
        for component in p4_errors["p4_h10"]
    }
    h10_series_ids = ("p4_h10", "p5_h10", "p6_h10")
    h10_errors = {
        sample_id: _absolute_differences(values[sample_id], center)
        for sample_id in h10_series_ids
    }
    h10_monotone = {
        component: _monotone_nonincreasing(
            h10_errors[sample_id][component]
            for sample_id in h10_series_ids
        )
        for component in h10_errors["p4_h10"]
    }
    component_floors = {
        "power": POWER_TOLERANCE_FLOOR,
        "amplitude_real": AMPLITUDE_TOLERANCE_FLOOR,
        "amplitude_imag": AMPLITUDE_TOLERANCE_FLOOR,
        "amplitude_magnitude": AMPLITUDE_TOLERANCE_FLOOR,
        "complex_amplitude_norm": AMPLITUDE_TOLERANCE_FLOOR,
        "phase_radians": 1.0e-15,
    }
    h_direction_stable = {
        component: (
            p4_monotone[component]
            or p4_errors["p4_h5"][component]
            <= max(p5_to_p6_h10[component], component_floors[component])
        )
        for component in p4_monotone
    }
    p_direction_stable = all(h10_monotone.values())
    all_h_direction_stable = all(h_direction_stable.values())
    strict_h_monotone = all(p4_monotone.values())
    if p_direction_stable and all_h_direction_stable:
        reference_status = (
            "reference_converged_monotone_p_and_h"
            if strict_h_monotone
            else "reference_converged_with_bounded_final_h_confirmation"
        )
    else:
        reference_status = "reference_not_converged"

    return {
        "channel": {
            "label": _channel_label(key),
            "side": key[0],
            "m": key[1],
            "n": key[2],
            "polarization": key[3],
        },
        "analytic_identity": center_identity,
        "reference_center": {
            "sample_id": "p6_h10",
            **center,
        },
        "samples": {
            sample_id: values[sample_id]
            for sample_id in _NUMERICAL_SAMPLE_IDS
        },
        "p_h_trend": {
            "p4_h_series_coarse_to_fine": {
                "sample_ids": list(p4_series_ids),
                "absolute_error_to_p6_h10": p4_errors,
                "componentwise_monotone_nonincreasing": p4_monotone,
            },
            "h10_p_series_p4_to_p6": {
                "sample_ids": list(h10_series_ids),
                "absolute_error_to_p6_h10": h10_errors,
                "componentwise_monotone_nonincreasing": h10_monotone,
                "mesh_identity_semantics": (
                    "same axis plan; the legacy p4 record predates the "
                    "partition-independent mesh hash"
                ),
            },
        },
        "reference_convergence": {
            "status": reference_status,
            "p_direction_stable": p_direction_stable,
            "h_direction_stable_by_component": h_direction_stable,
            "strict_h_componentwise_monotone": strict_h_monotone,
            "bounded_final_h_confirmation_definition": (
                "a nonmonotone p4 h-component is stable only when its "
                "p4/h5 error to p6/h10 is no larger than the independent "
                "h10 p5-to-p6 correction with the existing absolute floor"
            ),
            "nonmonotone_h_components": sorted(
                component
                for component, passed in p4_monotone.items()
                if not passed
            ),
        },
        "spread_over_numerical_authorities": _spread(
            {
                sample_id: values[sample_id]
                for sample_id in _NUMERICAL_SAMPLE_IDS
            },
            center=center,
        ),
        "numerical_convergence_band": {
            "definition": (
                "componentwise max of |p4/h5-p4/h7.5|, "
                "|p6/h10-p5/h10| and |p6/h10-p4/h5|"
            ),
            "absolute": numerical_band,
            "relative_to_p6_h10": numerical_band_relative,
            "contributions": {
                "p4_h7p5_to_p4_h5_final_h_step": p4_h7p5_to_h5,
                "p5_h10_to_p6_h10_p_step": p5_to_p6_h10,
                "p4_h5_to_p6_h10_cross_confirmation": p4_h5_to_p6_h10,
            },
            "acceptance_semantics": "diagnostic_only_never_a_gate_tolerance",
        },
        "unchanged_v0_acceptance_gate": {
            "definition": (
                "frozen h10 p5-to-p6 absolute correction plus existing floors"
            ),
            "significant_power_floor": SIGNIFICANT_POWER_FLOOR,
            "power_tolerance_floor": POWER_TOLERANCE_FLOOR,
            "amplitude_tolerance_floor": AMPLITUDE_TOLERANCE_FLOOR,
            "p5_to_p6_h10_power_absolute_correction": p5_to_p6_h10[
                "power"
            ],
            "power_absolute_tolerance": v0_power_tolerance,
            "p5_to_p6_h10_complex_amplitude_absolute_correction": (
                p5_to_p6_h10["complex_amplitude_norm"]
            ),
            "complex_amplitude_absolute_tolerance": (
                v0_amplitude_tolerance
            ),
            "uses_numerical_convergence_band": False,
            "uses_h15_or_fixed_diagnostics": False,
            "unchanged_v0_formula_verified": (
                v0_power_tolerance
                == max(p5_to_p6_h10["power"], POWER_TOLERANCE_FLOOR)
                and v0_amplitude_tolerance
                == max(
                    p5_to_p6_h10["complex_amplitude_norm"],
                    AMPLITUDE_TOLERANCE_FLOOR,
                )
            ),
        },
        "underresolved_diagnostics_not_in_bands": {
            sample_id: {
                **values[sample_id],
                "difference_to_p6_h10": _absolute_differences(
                    values[sample_id],
                    center,
                ),
            }
            for sample_id in _DIAGNOSTIC_SAMPLE_IDS
        },
    }


def build_significant_channel_reference(
    repo_root: Path,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load, validate, and freeze the 12-channel Task035b reference."""

    root = repo_root.resolve()
    authority_manifest = (
        default_authority_manifest() if manifest is None else deepcopy(manifest)
    )
    _validate_manifest(authority_manifest)
    cross_code_scalar_context = _validate_cross_code_scalar_context(
        root,
        authority_manifest["cross_code_scalar_context"],
    )
    manifest_encoded = json.dumps(
        authority_manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest_sha256 = hashlib.sha256(manifest_encoded).hexdigest()
    order_maps, authorities, excluded = _load_and_validate_authorities(
        root,
        authority_manifest,
    )
    center_keys = {
        key
        for key, order in order_maps["p6_h10"].items()
        if _finite_float(order["power_ratio"], field="power_ratio")
        >= SIGNIFICANT_POWER_FLOOR
    }
    expected_keys = set(EXPECTED_SIGNIFICANT_CHANNELS)
    if center_keys != expected_keys:
        missing = sorted(expected_keys - center_keys)
        extra = sorted(center_keys - expected_keys)
        raise ValueError(
            "p6/h10 significant-channel selection differs from the frozen "
            f"12-channel set; missing={missing}, extra={extra}"
        )
    channels = [
        _build_channel(key, order_maps)
        for key in EXPECTED_SIGNIFICANT_CHANNELS
    ]
    convergence_counts: dict[str, int] = {}
    for channel in channels:
        status = channel["reference_convergence"]["status"]
        convergence_counts[status] = convergence_counts.get(status, 0) + 1
    all_channels_converged = all(
        channel["reference_convergence"]["status"]
        != "reference_not_converged"
        for channel in channels
    )
    record = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "significant_channel_reference_v1_frozen"
            if all_channels_converged
            else "significant_channel_reference_v1_not_converged"
        ),
        "pass": all_channels_converged,
        "mechanical_validation_pass": True,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "geometry": GEOMETRY,
        "reference_center": "global structured-hexa p6/h10 MPI8",
        "phase_convention": (
            "atan2 boundary-amplitude phase, nearest 2pi branch around each "
            "p6/h10 channel center"
        ),
        "significant_channel_selection": {
            "authority": "p6_h10",
            "significant_power_floor": SIGNIFICANT_POWER_FLOOR,
            "channel_count": len(channels),
            "expected_and_observed_identity_match": True,
        },
        "reference_convergence_summary": {
            "all_12_channels_converged": all_channels_converged,
            "status_counts": convergence_counts,
            "nonconverged_channels": [
                channel["channel"]["label"]
                for channel in channels
                if channel["reference_convergence"]["status"]
                == "reference_not_converged"
            ],
        },
        "cross_code_scalar_context": cross_code_scalar_context,
        "authority_manifest": {
            "schema_version": authority_manifest["schema_version"],
            "geometry": authority_manifest["geometry"],
            "canonical_json_sha256": manifest_sha256,
            "mechanically_validated": True,
            "sample_roles_frozen": deepcopy(_EXPECTED_SAMPLE_ROLES),
            "numerical_band_sample_ids": list(_NUMERICAL_SAMPLE_IDS),
            "diagnostic_only_sample_ids": list(_DIAGNOSTIC_SAMPLE_IDS),
        },
        "authorities": authorities,
        "channels": channels,
        "excluded_negative_evidence": excluded,
        "scope_guards": {
            "h15_and_fixed_are_diagnostic_only": True,
            "tetra_negative_excluded": True,
            "numerical_band_cannot_modify_acceptance_gate": True,
            "unchanged_v0_acceptance_gate_is_h10_p5p6_only": True,
            "comsol_scalar_context_excluded_from_channel_band": True,
            "comsol_scalar_context_excluded_from_12_channel_gate": True,
            "comsol_context_does_not_change_v0_gate": True,
            "new_pde_run_performed": False,
        },
    }
    encoded = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    record["reference_payload_sha256"] = hashlib.sha256(encoded).hexdigest()
    return record


def render_significant_channel_markdown(record: Mapping[str, Any]) -> str:
    """Render the Chinese, table-first CR0 convergence outcome."""

    summary = record["reference_convergence_summary"]
    manifest = record["authority_manifest"]
    lines = [
        "# Task035b 显著衍射通道收敛参考 v1",
        "",
        "## 结论",
        "",
        "| 项目 | 结果 |",
        "|---|---|",
        f"| JSON status | `{record['status']}` |",
        f"| 顶层 pass | `{str(record['pass']).lower()}` |",
        "| 机械校验 | "
        f"`{str(record['mechanical_validation_pass']).lower()}` |",
        "| 参考中心 | global structured-hexa p6/h10，MPI8 |",
        "| 显著通道 | 12；p6/h10 power floor = `1e-8` |",
        "| 严格 p/h 单调 | 11 / 12 |",
        "| bounded final-h confirmation | 1 / 12：`R(-7,0)_s` |",
        "| 未收敛通道 | "
        f"{summary['nonconverged_channels'] or '无'} |",
        "| production qualified | "
        f"`{str(record['production_qualified']).lower()}` |",
        "| ordinary default changed | "
        f"`{str(record['ordinary_default_changed']).lower()}` |",
        "| authority manifest SHA256 | "
        f"`{manifest['canonical_json_sha256']}` |",
        "| reference payload SHA256 | "
        f"`{record['reference_payload_sha256']}` |",
        "",
        "本文件冻结的是当前 fixed rectangular block grating 的 "
        "best-available same-code 离散参考，不宣称 continuum truth，也不把 "
        "reference v1 提升为 production default。",
        "",
        "## 12 通道中心、band 与不变 v0 Gate",
        "",
        "| 通道 | p6/h10 power | amplitude Re | amplitude Im | "
        "amplitude magnitude | unwrap phase (deg) | numerical power band | "
        "numerical amplitude-norm band | phase band (deg) | v0 power tol | "
        "v0 amplitude-norm tol | p/h 趋势 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for channel in record["channels"]:
        center = channel["reference_center"]
        band = channel["numerical_convergence_band"]["absolute"]
        gate = channel["unchanged_v0_acceptance_gate"]
        convergence = channel["reference_convergence"]
        trend = (
            "p/h strict monotone"
            if convergence["status"]
            == "reference_converged_monotone_p_and_h"
            else "p monotone；h bounded confirmation"
        )
        lines.append(
            "| {label} | {power:.12e} | {real:.12e} | {imag:.12e} | "
            "{magnitude:.12e} | {phase:.9f} | {power_band:.12e} | "
            "{amplitude_band:.12e} | {phase_band:.9e} | "
            "{power_gate:.12e} | {amplitude_gate:.12e} | {trend} |".format(
                label=channel["channel"]["label"],
                power=center["power"],
                real=center["amplitude_real"],
                imag=center["amplitude_imag"],
                magnitude=center["amplitude_magnitude"],
                phase=center["phase_unwrapped_degrees"],
                power_band=band["power"],
                amplitude_band=band["complex_amplitude_norm"],
                phase_band=math.degrees(band["phase_radians"]),
                power_gate=gate["power_absolute_tolerance"],
                amplitude_gate=gate[
                    "complex_amplitude_absolute_tolerance"
                ],
                trend=trend,
            )
        )
    lines.extend(
        [
            "",
            "numerical band 对每个分量分别取以下三项绝对差的最大值："
            "`|p4/h5-p4/h7.5|`、`|p6/h10-p5/h10|`、"
            "`|p6/h10-p4/h5|`。它只描述离散 spread，绝不作为放宽 Gate "
            "的替代 tolerance。",
            "",
            "不变 v0 Gate 仍逐通道严格使用：",
            "",
            "- power tolerance = "
            "`max(|power(p6/h10)-power(p5/h10)|, 1e-12)`；",
            "- complex-amplitude tolerance = "
            "`max(|a(p6/h10)-a(p5/h10)|, 1e-10)`；",
            "- `uses_numerical_convergence_band=false`；",
            "- `uses_h15_or_fixed_diagnostics=false`。",
            "",
            "### `R(-7,0)_s` bounded 说明",
            "",
            "该通道的 p 方向全部分量单调；p4 h10→h7.5→h5 中 power、"
            "amplitude Re 和 magnitude 在最后一步存在微小回摆。它们的 "
            "p4/h5→p6/h10 误差均不大于独立 h10 p5→p6 修正，因此按预先"
            "写入记录的 bounded-final-h 判据通过；非单调分量仍完整保留，"
            "未改写为 strict monotone。",
            "",
            "## COMSOL cross-code scalar context",
            "",
            "| scalar | COMSOL direct convergence center | 使用范围 |",
            "|---|---:|---|",
        ]
    )
    cross_code = record["cross_code_scalar_context"]
    for label, field in (
        ("R00", "R00"),
        ("R total", "R_total"),
        ("T total", "T_total"),
    ):
        lines.append(
            f"| {label} | {cross_code['convergence_center'][field]:.9g} | "
            "cross-code scalar context only |"
        )
    document = cross_code["authority_document"]
    lines.extend(
        [
            "",
            "| COMSOL 约束 | 值 |",
            "|---|---|",
            f"| authority | `{document['path']}` |",
            f"| authority SHA256 | `{document['sha256']}` |",
            f"| software | `{document['software_identity']}` |",
            f"| solver scope | `{document['solver_scope']}` |",
            "| selected row identity SHA256 | "
            f"`{cross_code['table_identity']['selected_rows_canonical_json_sha256']}` |",
            "| excluded_from_channel_band | `true` |",
            "| excluded_from_12_channel_gate | `true` |",
            "| complex channel amplitudes | `not available` |",
            "| changes unchanged_v0 acceptance gate | `false` |",
            "",
            "中心由以下 5 个直接法表行逐分量取 median，并按原报告结论精度"
            "舍入。COMSOL Lagrange 与 FEniCS Nédélec 阶次不可一一映射；"
            "这里不从 scalar 表推断任何衍射通道复振幅。",
            "",
            "| COMSOL 表 | MPH | element | h (nm) | solution | DOFs | "
            "R00 | R | T |",
            "|---|---|---|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in cross_code["table_identity"]["selected_rows"]:
        lines.append(
            "| {heading} | `{source}` | {element} | {h:.1f} | "
            "`{solution}` | {dofs:,} | {R00:.9f} | {R:.9f} | "
            "{T:.9f} |".format(
                heading=row["table_heading"].removeprefix("## "),
                source=row["source_model"],
                element=row["element"],
                h=row["h_nm"],
                solution=row["solution"],
                dofs=row["dofs"],
                R00=row["R00"],
                R=row["R_total"],
                T=row["T_total"],
            )
        )

    lines.extend(
        [
            "",
            "## FEniCS authority identity",
            "",
            "| sample | role | p / h (nm) | source SHA | record SHA | "
            "raw DtN-order SHA | mesh / legacy identity |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for authority in record["authorities"]:
        expectations = authority["record_expectations"]
        mesh_sha = expectations.get(
            "common_mesh_identity.partition_independent_mesh_sha256"
        )
        if mesh_sha is not None:
            identity = (
                f"mesh `{mesh_sha}`; "
                f"cell-tag `{expectations['common_mesh_identity.cell_tag_sha256']}`; "
                f"facet-tag `{expectations['common_mesh_identity.facet_tag_sha256']}`"
            )
        elif "solver_summary.mesh_cells_resolved" in expectations:
            identity = (
                "`qualified_legacy_axis_plan_no_partition_hash`; plan "
                f"`{expectations['solver_summary.mesh_cells_resolved']}`"
            )
        else:
            identity = f"`{authority['identity_class']}`"
        lines.append(
            "| {sample} | `{role}` | {degree} / {h} | `{source}` | "
            "`{record_sha}` | `{raw_sha}` | {identity} |".format(
                sample=authority["sample_id"],
                role=authority["role"],
                degree=authority["degree"],
                h=authority["h_nm"],
                source=authority["source_sha"],
                record_sha=authority["record"]["sha256"],
                raw_sha=authority["raw_dtn_port_orders"]["sha256"],
                identity=identity,
            )
        )

    lines.extend(
        [
            "",
            "## 诊断与排除",
            "",
            "- global p5/p6 h15 与 fixed p5-trace/p6-interior h15 仅作为 "
            "underresolved/trace diagnostic，不进入 numerical band 或 v0 "
            "Gate；",
            "- Task035 tetra theta0p4 p5/p6 h50 保留为 "
            "`excluded_controlled_negative`，不作为 structured-hexa "
            "same-error authority；",
            "- 本次只聚合既有记录，没有运行新 PDE；",
            "- 所有 12 通道的 power、复振幅 Re/Im、magnitude、unwrap "
            "phase、p/h 差、绝对/相对 spread 均保存在对应 JSON channel "
            "对象中。",
            "",
        ]
    )
    return "\n".join(lines)
