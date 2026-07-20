from __future__ import annotations

import copy
import unittest

from benchmarks.run_task034_adaptive_mechanism import evaluate_mechanism_record


def _record() -> dict:
    environment = {
        "python_executable": "/home/Projects/MyFEniCS/.venv/bin/python",
        "python_version": "3.12.0",
        "mpi_library": "Open MPI",
        "petsc_version": "3.20.0",
        "petsc_scalar_type": "numpy.complex128",
        "petsc_int_type": "numpy.int32",
        "dolfinx_version": "0.8.0",
        "basix_version": "0.8.0",
        "omp_num_threads": "1",
        "openblas_num_threads": "1",
        "mkl_num_threads": "1",
    }
    floquet = {
        "num_constraints": 10,
        "constraint_mode_resolved": "topological_trace_p2",
        "used_full_boundary_gather": False,
        "created_dense_boundary_square": False,
        "max_face_pairing_coordinate_error": 1.0e-13,
        "edge_corner_phase_mismatch": 1.0e-13,
    }
    local = {
        "mesh_cells_xy": [11, 3],
        "global_interface_facet_count": 33,
        "expected_interface_facet_count": 33,
        "floquet": floquet,
    }
    sha = "a" * 40
    plan_hash = "b" * 64
    return {
        "schema_version": "task034.adaptive-mechanism.v1",
        "verified_clean_sha": sha,
        "source_before": {
            "commit_sha": sha,
            "tracked_and_nonignored_untracked_clean": True,
        },
        "source_after": {
            "commit_sha": sha,
            "tracked_and_nonignored_untracked_clean": True,
        },
        "case": {
            "degree": 2,
            "reference_h_nm": 5.0,
            "bottom_interface_nm": 10.0,
            "top_interface_nm": 110.0,
            "profile": "mechanism",
            "polarization_kind": "s",
        },
        "runtime": {"mpi_size": 8, "available_physical_cores": 48},
        "rank_environments": [{"rank": rank, **environment} for rank in range(8)],
        "plan_hashes_all_ranks": [plan_hash] * 8,
        "plan": {
            "plan_hash": plan_hash,
            "material_planes_exact": True,
            "matching_planes_exact": True,
            "quality": {
                "hanging_nodes_present": False,
                "positive_jacobian_proxy": True,
                "axis_width_ratio": 3.0,
            },
            "periodic_pairing": {
                "x_trace_synchronized": True,
                "y_trace_synchronized": True,
                "periodic_mate_refinement_synchronized": True,
            },
            "ordinary_uniform_default_changed": False,
        },
        "local_meshes": {
            "bottom": {**local, "interface_z_nm": 10.0},
            "top": {**local, "interface_z_nm": 110.0},
        },
        "cross_section": {"mesh_cells_xy": [11, 3], "mixed_global_dofs": 20},
        "claims": {"pde_solved": False},
    }


class TestTask034AdaptiveMechanismRecord(unittest.TestCase):
    def test_complete_record_passes_by_recomputation(self) -> None:
        decision = evaluate_mechanism_record(_record())
        self.assertTrue(decision["pass"], decision["failures"])

    def test_claimed_status_cannot_hide_broken_periodic_trace(self) -> None:
        record = copy.deepcopy(_record())
        record["qualification"] = {"pass": True}
        record["plan"]["periodic_pairing"]["x_trace_synchronized"] = False
        decision = evaluate_mechanism_record(record)
        self.assertFalse(decision["pass"])
        self.assertIn("periodic_trace_contract", decision["failures"])

    def test_rank_abi_drift_fails(self) -> None:
        record = copy.deepcopy(_record())
        record["rank_environments"][7]["python_executable"] = "/usr/bin/python3"
        decision = evaluate_mechanism_record(record)
        self.assertFalse(decision["checks"]["rank_environment_identity"])


if __name__ == "__main__":
    unittest.main()
