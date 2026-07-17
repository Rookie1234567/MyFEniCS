from __future__ import annotations

import copy
import unittest

from benchmarks.task033_matched_trace_qualification import (
    aggregate_matched_trace_records,
    matched_trace_shard_gate,
)


def _record(degree: int, mpi_size: int) -> dict:
    source_global = 100 * degree
    trace_global = 20 * degree
    source_parts = [source_global // mpi_size] * mpi_size
    trace_parts = [trace_global // mpi_size] * mpi_size
    source_parts[-1] += source_global - sum(source_parts)
    trace_parts[-1] += trace_global - sum(trace_parts)
    selected = 2 * degree + 4
    record = {
        "schema_version": "task033.phaseB-matched-trace.v1",
        "record_type": "measured_phaseB_matched_trace_component",
        "status": "pending_recomputation",
        "metadata": {
            "mpi_size": mpi_size,
            "source": {
                "commit_sha": "a" * 40,
                "source_clean_verified": True,
                "source_stable_during_run": True,
            },
        },
        "configuration": {"degree": degree},
        "space_identity": {
            "source_3d": {
                "family": "N1curl",
                "degree": degree,
                "global_dofs": source_global,
                "face_trace_dofs_per_cell": 2 * degree * (degree + 1),
            },
            "trace_2d": {
                "family": "N1curl",
                "degree": degree,
                "global_dofs": trace_global,
                "cell_dofs": 2 * degree * (degree + 1),
            },
        },
        "interface_geometry": {
            "matching_xy_axes": True,
            "matching_mesh_sha256": "b" * 64,
            "bottom_top_local_normals_are_opposites": True,
            "local_modal_normals_are_opposites": True,
        },
        "accuracy": {
            "affine_tangential_trace": [
                {
                    "side": side,
                    "relative_trace_coefficient_error": 0.0,
                    "unresolved_points": 0,
                    "global_query_points": 12,
                    "global_source_evaluations": 12,
                    "field_vector_gathered": False,
                    "normal_opposition_error": 0.0,
                }
                for side in ("bottom", "top")
            ]
        },
        "modal_projection": {
            "mode_count": 2,
            "reconstruction_shape": [trace_global, 2],
            "projection_shape": [2, trace_global],
            "trace_mass_nz_used": 8 * trace_global,
            "gram_rank": 2,
            "gram_condition": 3.0,
            "gram_singular_values": [2.0, 1.0],
            "coefficient_relative_error": 0.0,
            "trace_reconstruction_relative_residual": 0.0,
            "right_reconstruction_base_raised_relative_error": 0.0,
            "left_unit_projection_relative_errors": [0.0, 0.0],
            "mode_diagnostics": [
                {
                    "beta_per_nm": [1.0 + 0.1 * index, 0.0],
                    "right_polynomial_relative_residual": 0.0,
                    "left_polynomial_relative_residual": 0.0,
                    "left_unit_projection_relative_error": 0.0,
                }
                for index in range(2)
            ],
            "block_diagnostics": [
                {
                    "indices": [0, 1],
                    "normalization_method": "near_degenerate_block_inverse",
                    "post_normalization_identity_error": 0.0,
                }
            ],
            "full_vector_gathered": False,
            "dense_interface_operator_formed": False,
            "storage": {"dense_NGamma_squared_bytes": 0},
        },
        "quadrature": {
            "policy": "2p_plus_2g_plus_c_plus_2",
            "field_degree": degree,
            "geometry_degree": 1,
            "coefficient_degree": 0,
            "selected_degree": selected,
            "raised_degree": selected + 2,
            "trace_mass_matrix_relative_delta": 0.0,
            "gram_relative_delta": 0.0,
            "coefficient_round_trip_relative_delta": 0.0,
        },
        "mpi": {
            "ownership_by_rank": [
                {
                    "rank": rank,
                    "source_owned_dofs": source_parts[rank],
                    "source_ghost_dofs": 0,
                    "trace_owned_dofs": trace_parts[rank],
                    "trace_ghost_dofs": 0,
                }
                for rank in range(mpi_size)
            ],
            "source_scatter_forward": True,
            "trace_scatter_forward": True,
            "point_ownership_method": (
                "dolfinx.geometry.determine_point_ownership"
            ),
            "tangential_value_bytes_sent": 0,
            "tangential_value_bytes_received": 0,
            "rank_signatures": ["c" * 64] * mpi_size,
        },
        "scalability": {
            "full_3d_field_gathered": False,
            "full_mode_vector_gathered": False,
            "dense_interface_square_formed": False,
        },
    }
    record["status"] = matched_trace_shard_gate(record)["status"]
    return record


class Task033MatchedTraceQualificationTests(unittest.TestCase):
    def test_zero_error_five_shard_matrix_passes(self) -> None:
        records = [
            _record(2, 1),
            _record(3, 1),
            _record(3, 4),
            _record(4, 1),
            _record(4, 4),
        ]
        aggregate = aggregate_matched_trace_records(records)
        self.assertEqual(
            aggregate["status"],
            "phaseB_p3_p4_matched_trace_pass",
        )
        self.assertTrue(aggregate["gates"]["p3_phaseB_matched_trace"])
        self.assertTrue(
            aggregate["gates"]["p4_phaseB_matched_trace_independent"]
        )
        self.assertEqual(
            aggregate["decisions"]["phaseC"],
            "wait_for_independent_review",
        )

    def test_p4_mpi_difference_fails_independently_from_p3(self) -> None:
        records = [
            _record(2, 1),
            _record(3, 1),
            _record(3, 4),
            _record(4, 1),
            _record(4, 4),
        ]
        records[-1]["modal_projection"]["mode_diagnostics"][0][
            "beta_per_nm"
        ] = [3.0, 0.0]
        aggregate = aggregate_matched_trace_records(records)
        self.assertEqual(
            aggregate["status"],
            "phaseB_p3_pass_p4_fail_closed",
        )
        self.assertTrue(aggregate["gates"]["p3_phaseB_matched_trace"])
        self.assertFalse(
            aggregate["gates"]["p4_phaseB_matched_trace_independent"]
        )
        self.assertEqual(
            aggregate["decisions"]["p4"],
            "fail_closed_independently",
        )

    def test_p4_shard_failure_does_not_block_p3(self) -> None:
        records = [
            _record(2, 1),
            _record(3, 1),
            _record(3, 4),
            _record(4, 1),
            _record(4, 4),
        ]
        records[-1]["modal_projection"][
            "coefficient_relative_error"
        ] = 1.0
        records[-1]["status"] = "fail"
        aggregate = aggregate_matched_trace_records(records)
        self.assertEqual(
            aggregate["status"],
            "phaseB_p3_pass_p4_fail_closed",
        )
        self.assertTrue(aggregate["gates"]["p3_phaseB_matched_trace"])
        self.assertFalse(
            aggregate["gates"]["p4_phaseB_matched_trace_independent"]
        )
        self.assertFalse(
            aggregate["gates"]["all_five_expected_shards_present_and_pass"]
        )

    def test_full_gather_claim_is_recomputed_and_rejected(self) -> None:
        record = copy.deepcopy(_record(3, 4))
        record["scalability"]["full_mode_vector_gathered"] = True
        report = matched_trace_shard_gate(record)
        self.assertEqual(report["status"], "fail")
        self.assertIn("no_full_vector_gather", report["failed_checks"])
        self.assertFalse(report["reported_status_matches"])


if __name__ == "__main__":
    unittest.main()
