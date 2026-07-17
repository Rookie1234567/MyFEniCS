"""Fail-closed qualification for Task033 Phase-B matched-trace records."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
from typing import Any


FULL_SHA = re.compile(r"[0-9a-f]{40}")
TRACE_ERROR_MAX = 1.0e-10
COEFFICIENT_ERROR_MAX = 1.0e-9
LEFT_PROJECTION_ERROR_MAX = 1.0e-9
RIGHT_RESIDUAL_MAX = 1.0e-10
LEFT_RESIDUAL_MAX = 1.0e-8
BIORTHOGONALITY_MAX = 1.0e-6
GRAM_CONDITION_MAX = 1.0e12
RAISED_QUADRATURE_DELTA_MAX = 2.0e-12
MPI_BETA_RELATIVE_DELTA_MAX = 1.0e-8
MPI_INVARIANT_RELATIVE_DELTA_MAX = 1.0e-7
EXPECTED_SHARDS = ((2, 1), (3, 1), (3, 4), (4, 1), (4, 4))


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return value
    return ()


def _relative_delta(first: float, second: float) -> float:
    return float(abs(first - second) / max(abs(first), abs(second), 1.0e-30))


def _finite_le(value: object, limit: float) -> bool:
    parsed = _finite(value)
    return parsed is not None and parsed <= limit


def _complex(value: object) -> complex | None:
    items = _sequence(value)
    if len(items) != 2:
        return None
    real = _finite(items[0])
    imaginary = _finite(items[1])
    if real is None or imaginary is None:
        return None
    return complex(real, imaginary)


def _all_finite_le(values: object, limit: float) -> bool:
    parsed = [_finite(value) for value in _sequence(values)]
    return bool(parsed) and all(
        value is not None and value <= limit for value in parsed
    )


def _owned_sum(
    ownership: Sequence[Any],
    field: str,
) -> int | None:
    values = []
    for item in ownership:
        if not isinstance(item, Mapping):
            return None
        value = item.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return None
        values.append(value)
    return sum(values)


def _record_identity(record: Mapping[str, Any]) -> tuple[int, int] | None:
    configuration = _mapping(record.get("configuration"))
    degree = configuration.get("degree")
    mpi_size = _mapping(record.get("metadata")).get("mpi_size")
    if (
        isinstance(degree, int)
        and not isinstance(degree, bool)
        and isinstance(mpi_size, int)
        and not isinstance(mpi_size, bool)
    ):
        return int(degree), int(mpi_size)
    return None


def matched_trace_shard_gate(record: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute every positive gate used by one Phase-B shard."""

    identity = _record_identity(record)
    degree, mpi_size = identity if identity is not None else (-1, -1)
    metadata = _mapping(record.get("metadata"))
    source = _mapping(metadata.get("source"))
    spaces = _mapping(record.get("space_identity"))
    source_space = _mapping(spaces.get("source_3d"))
    trace_space = _mapping(spaces.get("trace_2d"))
    geometry = _mapping(record.get("interface_geometry"))
    accuracy = _mapping(record.get("accuracy"))
    interfaces = _sequence(accuracy.get("affine_tangential_trace"))
    projection = _mapping(record.get("modal_projection"))
    quadrature = _mapping(record.get("quadrature"))
    mpi = _mapping(record.get("mpi"))
    scalability = _mapping(record.get("scalability"))
    mode_diagnostics = _sequence(projection.get("mode_diagnostics"))
    block_diagnostics = _sequence(projection.get("block_diagnostics"))

    interface_accuracy = (
        len(interfaces) == 2
        and {item.get("side") for item in interfaces if isinstance(item, Mapping)}
        == {"bottom", "top"}
        and all(
            isinstance(item, Mapping)
            and _finite_le(
                item.get("relative_trace_coefficient_error"),
                TRACE_ERROR_MAX,
            )
            and item.get("unresolved_points") == 0
            and item.get("global_query_points")
            == item.get("global_source_evaluations")
            and item.get("field_vector_gathered") is False
            and _finite_le(item.get("normal_opposition_error"), 1.0e-14)
            for item in interfaces
        )
    )
    projection_accuracy = (
        _finite_le(
            projection.get("coefficient_relative_error"),
            COEFFICIENT_ERROR_MAX,
        )
        and _finite_le(
            projection.get("trace_reconstruction_relative_residual"),
            COEFFICIENT_ERROR_MAX,
        )
        and _finite_le(
            projection.get("right_reconstruction_base_raised_relative_error"),
            RAISED_QUADRATURE_DELTA_MAX,
        )
        and _finite_le(projection.get("gram_condition"), GRAM_CONDITION_MAX)
        and projection.get("gram_rank") == projection.get("mode_count")
        and _all_finite_le(
            projection.get("left_unit_projection_relative_errors"),
            LEFT_PROJECTION_ERROR_MAX,
        )
    )
    modes_ok = (
        len(mode_diagnostics) == projection.get("mode_count")
        and len(mode_diagnostics) > 0
        and all(
            isinstance(item, Mapping)
            and _complex(item.get("beta_per_nm")) is not None
            and _finite_le(
                item.get("right_polynomial_relative_residual"),
                RIGHT_RESIDUAL_MAX,
            )
            and _finite_le(
                item.get("left_polynomial_relative_residual"),
                LEFT_RESIDUAL_MAX,
            )
            and _finite_le(
                item.get("left_unit_projection_relative_error"),
                LEFT_PROJECTION_ERROR_MAX,
            )
            for item in mode_diagnostics
        )
    )
    blocks_ok = bool(block_diagnostics) and all(
        isinstance(item, Mapping)
        and bool(_sequence(item.get("indices")))
        and item.get("normalization_method")
        in {"diagonal_qprime", "near_degenerate_block_inverse"}
        and _finite_le(
            item.get("post_normalization_identity_error"),
            BIORTHOGONALITY_MAX,
        )
        for item in block_diagnostics
    )

    selected_expected = 2 * degree + 4
    quadrature_ok = (
        quadrature.get("policy") == "2p_plus_2g_plus_c_plus_2"
        and quadrature.get("field_degree") == degree
        and quadrature.get("geometry_degree") == 1
        and quadrature.get("coefficient_degree") == 0
        and quadrature.get("selected_degree") == selected_expected
        and quadrature.get("raised_degree") == selected_expected + 2
        and _finite_le(
            quadrature.get("trace_mass_matrix_relative_delta"),
            RAISED_QUADRATURE_DELTA_MAX,
        )
        and _finite_le(
            quadrature.get("gram_relative_delta"),
            RAISED_QUADRATURE_DELTA_MAX,
        )
        and _finite_le(
            quadrature.get("coefficient_round_trip_relative_delta"),
            COEFFICIENT_ERROR_MAX,
        )
    )

    ownership = _sequence(mpi.get("ownership_by_rank"))
    source_global = source_space.get("global_dofs")
    trace_global = trace_space.get("global_dofs")
    ownership_ok = (
        len(ownership) == mpi_size
        and all(isinstance(item, Mapping) for item in ownership)
        and _owned_sum(ownership, "source_owned_dofs")
        == source_global
        and _owned_sum(ownership, "trace_owned_dofs")
        == trace_global
        and mpi.get("source_scatter_forward") is True
        and mpi.get("trace_scatter_forward") is True
        and mpi.get("point_ownership_method")
        == "dolfinx.geometry.determine_point_ownership"
        and mpi.get("tangential_value_bytes_sent")
        == mpi.get("tangential_value_bytes_received")
        and isinstance(mpi.get("tangential_value_bytes_sent"), int)
        and mpi.get("tangential_value_bytes_sent") >= 0
    )
    rank_signatures = _sequence(mpi.get("rank_signatures"))
    rank_agreement = (
        len(rank_signatures) == mpi_size
        and len(set(rank_signatures)) == 1
    )

    checks = {
        "record_identity": (
            record.get("schema_version") == "task033.phaseB-matched-trace.v1"
            and record.get("record_type")
            == "measured_phaseB_matched_trace_component"
            and identity in EXPECTED_SHARDS
        ),
        "source_identity": (
            isinstance(source.get("commit_sha"), str)
            and FULL_SHA.fullmatch(source["commit_sha"].lower()) is not None
            and source.get("source_clean_verified") is True
            and source.get("source_stable_during_run") is True
        ),
        "space_identity": (
            source_space.get("family") == "N1curl"
            and trace_space.get("family") == "N1curl"
            and source_space.get("degree") == degree
            and trace_space.get("degree") == degree
            and source_space.get("face_trace_dofs_per_cell")
            == trace_space.get("cell_dofs")
            and isinstance(source_global, int)
            and source_global > 0
            and isinstance(trace_global, int)
            and trace_global > 0
        ),
        "matching_geometry_and_orientation": (
            geometry.get("matching_xy_axes") is True
            and isinstance(geometry.get("matching_mesh_sha256"), str)
            and len(geometry["matching_mesh_sha256"]) == 64
            and geometry.get("bottom_top_local_normals_are_opposites") is True
            and geometry.get("local_modal_normals_are_opposites") is True
        ),
        "affine_3d_to_2d_trace": interface_accuracy,
        "right_reconstruction_and_left_petrov_projection": projection_accuracy,
        "per_mode_diagnostics": modes_ok,
        "per_block_diagnostics": blocks_ok,
        "degree_aware_raised_quadrature": quadrature_ok,
        "mpi_ownership_and_ghost_handling": ownership_ok,
        "rank_local_results_agree": rank_agreement,
        "no_full_vector_gather": (
            scalability.get("full_3d_field_gathered") is False
            and scalability.get("full_mode_vector_gathered") is False
            and projection.get("full_vector_gathered") is False
        ),
        "no_dense_interface_square": (
            scalability.get("dense_interface_square_formed") is False
            and projection.get("dense_interface_operator_formed") is False
            and _mapping(projection.get("storage")).get(
                "dense_NGamma_squared_bytes"
            )
            == 0
        ),
    }
    recomputed_status = "pass" if all(checks.values()) else "fail"
    return {
        "identity": {"degree": degree, "mpi_size": mpi_size},
        "status": recomputed_status,
        "reported_status_matches": record.get("status") == recomputed_status,
        "checks": checks,
        "failed_checks": [
            name for name, passed in checks.items() if not passed
        ],
    }


def _beta_assignment_delta(
    first: Sequence[Any], second: Sequence[Any]
) -> tuple[float, list[int]] | None:
    first_values = [
        _complex(_mapping(item).get("beta_per_nm")) for item in first
    ]
    second_values = [
        _complex(_mapping(item).get("beta_per_nm")) for item in second
    ]
    if (
        not first_values
        or len(first_values) != len(second_values)
        or any(value is None for value in (*first_values, *second_values))
    ):
        return None
    parsed_first = [complex(value) for value in first_values if value is not None]
    parsed_second = [complex(value) for value in second_values if value is not None]
    best: tuple[float, list[int]] | None = None
    for permutation in itertools.permutations(range(len(parsed_second))):
        delta = max(
            abs(parsed_first[index] - parsed_second[permutation[index]])
            / max(
                abs(parsed_first[index]),
                abs(parsed_second[permutation[index]]),
                1.0e-30,
            )
            for index in range(len(parsed_first))
        )
        candidate = (float(delta), list(permutation))
        if best is None or candidate[0] < best[0]:
            best = candidate
    return best


def _mpi_pair_diagnostic(
    mpi1: Mapping[str, Any], mpi4: Mapping[str, Any]
) -> dict[str, Any]:
    geometry1 = _mapping(mpi1.get("interface_geometry"))
    geometry4 = _mapping(mpi4.get("interface_geometry"))
    spaces1 = _mapping(mpi1.get("space_identity"))
    spaces4 = _mapping(mpi4.get("space_identity"))
    projection1 = _mapping(mpi1.get("modal_projection"))
    projection4 = _mapping(mpi4.get("modal_projection"))
    quadrature1 = _mapping(mpi1.get("quadrature"))
    quadrature4 = _mapping(mpi4.get("quadrature"))
    beta = _beta_assignment_delta(
        _sequence(projection1.get("mode_diagnostics")),
        _sequence(projection4.get("mode_diagnostics")),
    )
    condition1 = _finite(projection1.get("gram_condition"))
    condition4 = _finite(projection4.get("gram_condition"))
    singular1 = [
        _finite(value) for value in _sequence(projection1.get("gram_singular_values"))
    ]
    singular4 = [
        _finite(value) for value in _sequence(projection4.get("gram_singular_values"))
    ]
    singular_delta = (
        max(
            _relative_delta(float(first), float(second))
            for first, second in zip(singular1, singular4)
            if first is not None and second is not None
        )
        if singular1
        and len(singular1) == len(singular4)
        and all(value is not None for value in (*singular1, *singular4))
        else math.inf
    )
    block1 = [
        (
            len(_sequence(_mapping(item).get("indices"))),
            _mapping(item).get("normalization_method"),
        )
        for item in _sequence(projection1.get("block_diagnostics"))
    ]
    block4 = [
        (
            len(_sequence(_mapping(item).get("indices"))),
            _mapping(item).get("normalization_method"),
        )
        for item in _sequence(projection4.get("block_diagnostics"))
    ]
    checks = {
        "matching_mesh_hash_exact": (
            geometry1.get("matching_mesh_sha256")
            == geometry4.get("matching_mesh_sha256")
        ),
        "space_global_dofs_exact": (
            _mapping(spaces1.get("source_3d")).get("global_dofs")
            == _mapping(spaces4.get("source_3d")).get("global_dofs")
            and _mapping(spaces1.get("trace_2d")).get("global_dofs")
            == _mapping(spaces4.get("trace_2d")).get("global_dofs")
        ),
        "projection_shapes_and_nnz_exact": all(
            projection1.get(name) == projection4.get(name)
            for name in (
                "mode_count",
                "reconstruction_shape",
                "projection_shape",
                "trace_mass_nz_used",
            )
        ),
        "quadrature_identity_exact": all(
            quadrature1.get(name) == quadrature4.get(name)
            for name in ("selected_degree", "raised_degree")
        ),
        "per_mode_beta_assignment": (
            beta is not None and beta[0] <= MPI_BETA_RELATIVE_DELTA_MAX
        ),
        "per_block_structure": sorted(block1) == sorted(block4),
        "gram_condition_invariant": (
            condition1 is not None
            and condition4 is not None
            and _relative_delta(condition1, condition4)
            <= MPI_INVARIANT_RELATIVE_DELTA_MAX
        ),
        "gram_singular_values_invariant": (
            singular_delta <= MPI_INVARIANT_RELATIVE_DELTA_MAX
        ),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "beta_assignment": (
            None
            if beta is None
            else {
                "maximum_relative_delta": beta[0],
                "mpi4_indices_for_mpi1_modes": beta[1],
            }
        ),
        "gram_condition_relative_delta": (
            None
            if condition1 is None or condition4 is None
            else _relative_delta(condition1, condition4)
        ),
        "gram_singular_values_max_relative_delta": (
            None if not math.isfinite(singular_delta) else singular_delta
        ),
        "scope_note": (
            "MPI identity is recomputed from mesh/space/algebra invariants, "
            "per-mode beta assignment, and per-block structure. No full "
            "eigenvector gather or cross-MPI full-vector dot is performed."
        ),
    }


def aggregate_matched_trace_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the independent lightweight Phase-B aggregate."""

    indexed: dict[tuple[int, int], Mapping[str, Any]] = {}
    duplicate_identities: list[list[int]] = []
    for record in records:
        identity = _record_identity(record)
        if identity is None:
            continue
        if identity in indexed:
            duplicate_identities.append(list(identity))
        indexed[identity] = record

    shard_reports = {
        f"p{degree}_mpi{mpi_size}": matched_trace_shard_gate(record)
        for (degree, mpi_size), record in sorted(indexed.items())
    }
    expected_present = set(indexed) == set(EXPECTED_SHARDS)
    all_shards_recomputed_pass = (
        expected_present
        and not duplicate_identities
        and all(
            report["status"] == "pass"
            and report["reported_status_matches"] is True
            for report in shard_reports.values()
        )
    )
    p3_required_shards_recomputed_pass = (
        expected_present
        and not duplicate_identities
        and all(
            shard_reports.get(f"p{degree}_mpi{mpi_size}", {}).get("status")
            == "pass"
            and shard_reports.get(
                f"p{degree}_mpi{mpi_size}", {}
            ).get("reported_status_matches")
            is True
            for degree, mpi_size in ((2, 1), (3, 1), (3, 4))
        )
    )
    source_shas = {
        _mapping(_mapping(record.get("metadata")).get("source")).get(
            "commit_sha"
        )
        for record in indexed.values()
    }
    stable_source = (
        len(source_shas) == 1
        and None not in source_shas
        and all(
            _mapping(_mapping(record.get("metadata")).get("source")).get(
                "source_clean_verified"
            )
            is True
            for record in indexed.values()
        )
    )
    mpi_diagnostics = {}
    for degree in (3, 4):
        if (degree, 1) in indexed and (degree, 4) in indexed:
            mpi_diagnostics[f"p{degree}"] = _mpi_pair_diagnostic(
                indexed[(degree, 1)], indexed[(degree, 4)]
            )
    p2_pass = shard_reports.get("p2_mpi1", {}).get("status") == "pass"
    p3_pass = all(
        shard_reports.get(f"p3_mpi{mpi_size}", {}).get("status") == "pass"
        for mpi_size in (1, 4)
    )
    p4_pass = all(
        shard_reports.get(f"p4_mpi{mpi_size}", {}).get("status") == "pass"
        for mpi_size in (1, 4)
    )
    p3_mpi_pass = mpi_diagnostics.get("p3", {}).get("status") == "pass"
    p4_mpi_pass = mpi_diagnostics.get("p4", {}).get("status") == "pass"
    p3_no_gather = all(
        report.get("checks", {}).get("no_full_vector_gather") is True
        for name, report in shard_reports.items()
        if name in {"p2_mpi1", "p3_mpi1", "p3_mpi4"}
    )
    p3_no_dense = all(
        report.get("checks", {}).get("no_dense_interface_square") is True
        for name, report in shard_reports.items()
        if name in {"p2_mpi1", "p3_mpi1", "p3_mpi4"}
    )
    p3_raised_stable = all(
        report.get("checks", {}).get("degree_aware_raised_quadrature") is True
        for name, report in shard_reports.items()
        if name in {"p2_mpi1", "p3_mpi1", "p3_mpi4"}
    )
    p4_no_gather = all(
        shard_reports.get(name, {})
        .get("checks", {})
        .get("no_full_vector_gather")
        is True
        for name in ("p4_mpi1", "p4_mpi4")
    )
    p4_no_dense = all(
        shard_reports.get(name, {})
        .get("checks", {})
        .get("no_dense_interface_square")
        is True
        for name in ("p4_mpi1", "p4_mpi4")
    )
    p4_raised_stable = all(
        shard_reports.get(name, {})
        .get("checks", {})
        .get("degree_aware_raised_quadrature")
        is True
        for name in ("p4_mpi1", "p4_mpi4")
    )
    p3_phase_b_pass = bool(
        p3_required_shards_recomputed_pass
        and stable_source
        and p2_pass
        and p3_pass
        and p3_mpi_pass
        and p3_raised_stable
        and p3_no_gather
        and p3_no_dense
    )
    p4_independent_pass = bool(
        stable_source
        and p4_pass
        and p4_mpi_pass
        and p4_raised_stable
        and p4_no_gather
        and p4_no_dense
    )
    status = (
        "phaseB_p3_p4_matched_trace_pass"
        if p3_phase_b_pass and p4_independent_pass
        else (
            "phaseB_p3_pass_p4_fail_closed"
            if p3_phase_b_pass
            else "phaseB_matched_trace_not_qualified"
        )
    )
    payload = {
        "schema_version": "task033.phaseB-matched-trace-aggregate.v1",
        "record_type": "independent_lightweight_phaseB_aggregate",
        "status": status,
        "source_commit_sha": next(iter(source_shas), None),
        "expected_shards": [
            {"degree": degree, "mpi_size": mpi_size}
            for degree, mpi_size in EXPECTED_SHARDS
        ],
        "shard_reports": shard_reports,
        "mpi_identity_diagnostics": mpi_diagnostics,
        "gates": {
            "all_five_expected_shards_present_and_pass": (
                all_shards_recomputed_pass
            ),
            "p2_p3_required_shards_present_and_pass": (
                p3_required_shards_recomputed_pass
            ),
            "single_clean_stable_source": stable_source,
            "p2_mpi1_regression_anchor": p2_pass,
            "p3_mpi1_mpi4_components": p3_pass,
            "p4_mpi1_mpi4_components": p4_pass,
            "p3_mpi1_mpi4_identity": p3_mpi_pass,
            "p4_mpi1_mpi4_identity": p4_mpi_pass,
            "p2_p3_raised_quadrature_stable": p3_raised_stable,
            "p4_raised_quadrature_stable": p4_raised_stable,
            "p2_p3_no_full_vector_gather": p3_no_gather,
            "p4_no_full_vector_gather": p4_no_gather,
            "p2_p3_no_dense_interface_square": p3_no_dense,
            "p4_no_dense_interface_square": p4_no_dense,
            "p3_phaseB_matched_trace": p3_phase_b_pass,
            "p4_phaseB_matched_trace_independent": p4_independent_pass,
        },
        "decisions": {
            "p3": "pass" if p3_phase_b_pass else "fail_closed",
            "p4": "pass" if p4_independent_pass else "fail_closed_independently",
            "phaseC": "wait_for_independent_review",
            "target_full3d_or_hybrid_run_started": False,
            "case090_rerun": False,
        },
        "scope_qualifications": [
            "This aggregate qualifies only the small matching-interface component.",
            "It does not qualify a target-grating full3D or Hybrid solve.",
            "MPI comparison uses compact scalar/block invariants and no full-vector gather.",
            "Phase C remains blocked until this aggregate receives independent review.",
        ],
        "duplicate_identities": duplicate_identities,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    digest_payload = dict(payload)
    digest_payload.pop("generated_at_utc")
    payload["evidence_sha256"] = hashlib.sha256(
        json.dumps(
            digest_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate the five Task033 Phase-B matched-trace shards."
    )
    parser.add_argument("--p2-mpi1", type=Path, required=True)
    parser.add_argument("--p3-mpi1", type=Path, required=True)
    parser.add_argument("--p3-mpi4", type=Path, required=True)
    parser.add_argument("--p4-mpi1", type=Path, required=True)
    parser.add_argument("--p4-mpi4", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    paths = (
        args.p2_mpi1,
        args.p3_mpi1,
        args.p3_mpi4,
        args.p4_mpi1,
        args.p4_mpi4,
    )
    records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    aggregate = aggregate_matched_trace_records(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(aggregate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"status": aggregate["status"], "gates": aggregate["gates"]},
            indent=2,
        )
    )
    if aggregate["gates"]["p3_phaseB_matched_trace"] is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
