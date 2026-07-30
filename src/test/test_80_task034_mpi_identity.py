from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from benchmarks.task034_mpi_identity import build_mpi_identity


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _order(power: float = 0.5) -> dict:
    return {
        "side": "top",
        "m": 0,
        "n": 0,
        "polarization": "s",
        "power_ratio": power,
        "outgoing_amplitude_at_boundary": [0.5, 0.25],
        "beta_per_nm": [0.1, 0.0],
    }


class Task034MPIIdentityTests(unittest.TestCase):
    def _full3d(self, directory: Path, mpi_size: int) -> dict:
        archive = directory / f"field_mpi{mpi_size}.npz"
        np.savez(
            archive,
            E_V_per_m=np.ones((2, 2), dtype=complex),
            H_A_per_m=np.ones((2, 2), dtype=complex),
            E_t_interface_V_per_m=np.ones((2, 2), dtype=complex),
            H_t_interface_A_per_m=np.ones((2, 2), dtype=complex),
        )
        run_dir = directory / f"run_mpi{mpi_size}"
        run_dir.mkdir()
        (run_dir / "orders.json").write_text(
            json.dumps({"orders": [_order()]}), encoding="utf-8"
        )
        return {
            "status": "full3d_reference_pass",
            "degree": 4,
            "h_nm": 5.0,
            "polarization_kind": "s",
            "run_kind": "full-solve",
            "mpi_size": mpi_size,
            "no_swap": True,
            "elapsed_seconds": 2.0,
            "source": {"verified_clean_sha": "a" * 40},
            "qualification": {"pass": True},
            "resource_authority": {"memory_authority_gib": 2.0},
            "raw_evidence": {"run_directory": str(run_dir)},
            "solver_summary": {
                "official_result": True,
                "polarization_kind": "s",
                "num_nedelec_dofs": 10,
                "matrix_stats": {"matrix_rows": 12, "matrix_nnz_used": 30},
                "floquet_num_constraints": 2,
                "floquet_raw_map_nnz": 3,
                "stage4_dtn_num_auxiliary_dofs": 1,
                "mesh_cells_resolved": [1, 1, 1],
                "config": {"degree": 4, "h": 5.0, "polarization_kind": "s"},
                "linear_system_relative_residual": 1.0e-12,
                "R_total": 0.1,
                "T_total": 0.7,
                "A_volume_total": 0.2,
                "dtn_port_orders_json": "orders.json",
                "full3d_reference_archive": str(archive),
                "full3d_reference_archive_sha256": _sha256(archive),
            },
        }

    def _hybrid(self, mpi_size: int) -> dict:
        planes = [
            {
                "z_nm": 30.0,
                "electric": {"relative_l2": 1.0e-6},
                "magnetic": {"relative_l2": 2.0e-6},
            }
        ]
        interface = {
            side: {
                "electric_tangential": {"relative_l2": 1.0e-7},
                "magnetic_tangential": {"relative_l2": 2.0e-7},
            }
            for side in ("bottom", "top")
        }
        return {
            "status": "measured_shard_pass",
            "requested_modes": 160,
            "formal_pass": True,
            "numeric_pass": True,
            "no_swap": True,
            "source": {"verified_clean_sha": "b" * 40},
            "worker_source": {"mpi_size": mpi_size},
            "resource_authority": {"memory_authority_gib": 2.0},
            "measurements": {
                "case": {
                    "degree": 4,
                    "h_nm": 5.0,
                    "polarization_kind": "s",
                    "requested_modes_per_direction": 160,
                    "bottom_interface_nm": 10.0,
                    "top_interface_nm": 110.0,
                },
                "hybrid_system": {
                    "bottom_local_fe_dofs": 10,
                    "top_local_fe_dofs": 10,
                    "bottom_local_mesh_cells": [1, 1, 1],
                    "top_local_mesh_cells": [1, 1, 1],
                },
                "object_payload_ledger": {
                    "interface_active_dofs": {"bottom": 2, "top": 2}
                },
                "solve": {"true_relative_residual": 1.0e-12},
                "validation": {
                    "port_power": {"R_total": 0.1, "T_total": 0.7},
                    "external_diffraction_orders": [_order()],
                },
                "physical_field_reconstruction": {
                    "volume_absorption": {"A_volume_total": 0.2},
                    "selected_plane_full3d_comparison": {"planes": planes},
                    "interface_continuity": interface,
                },
                "gates": {
                    "biorthogonality_identity_error_le_1e-6": True,
                    "right_and_left_qep_residuals_le_1e-8": True,
                },
                "timing_seconds_max_rank": {"total": 2.0},
            },
        }

    def test_full3d_identity_passes_and_fails_closed_on_field_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory_value:
            directory = Path(directory_value)
            records = [self._full3d(directory, size) for size in (1, 8, 16)]
            for index, record in enumerate(records):
                record["raw_global_vector_sha256"] = (
                    f"{index + 1:064x}"
                )
            result = build_mpi_identity(
                records, method="full3d", physical_core_count=48
            )
            self.assertEqual(result["status"], "qualified", result["failures"])
            self.assertFalse(
                result["identity_semantics"][
                    "partition_sensitive_raw_vector_hash_used"
                ]
            )
            archive = Path(records[-1]["solver_summary"]["full3d_reference_archive"])
            np.savez(
                archive,
                E_V_per_m=np.ones((2, 2), dtype=complex) * 2,
                H_A_per_m=np.ones((2, 2), dtype=complex),
                E_t_interface_V_per_m=np.ones((2, 2), dtype=complex),
                H_t_interface_A_per_m=np.ones((2, 2), dtype=complex),
            )
            records[-1]["solver_summary"]["full3d_reference_archive_sha256"] = _sha256(
                archive
            )
            failed = build_mpi_identity(
                records, method="full3d", physical_core_count=48
            )
            self.assertEqual(failed["status"], "not_qualified")

    def test_full3d_identity_accepts_native_beta_order_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory_value:
            directory = Path(directory_value)
            records = [self._full3d(directory, size) for size in (1, 8, 16)]
            for record in records:
                run_dir = Path(record["raw_evidence"]["run_directory"])
                order_path = run_dir / record["solver_summary"][
                    "dtn_port_orders_json"
                ]
                payload = json.loads(order_path.read_text(encoding="utf-8"))
                for order in payload["orders"]:
                    order["beta"] = order.pop("beta_per_nm")
                order_path.write_text(
                    json.dumps(payload), encoding="utf-8"
                )
            result = build_mpi_identity(
                records, method="full3d", physical_core_count=48
            )
            self.assertEqual(result["status"], "qualified", result["failures"])

    def test_hybrid_identity_requires_funnel_and_detects_order_drift(self) -> None:
        records = [self._hybrid(size) for size in (1, 8, 16)]
        funnel = {
            "status": "qualified",
            "qualification": {
                "mode_count_converged": True,
                "selected_mode_count_per_direction": 160,
            },
        }
        result = build_mpi_identity(
            records,
            method="hybrid",
            physical_core_count=48,
            funnel=funnel,
        )
        self.assertEqual(result["status"], "qualified", result["failures"])
        failed_records = copy.deepcopy(records)
        failed_records[-1]["measurements"]["validation"]["external_diffraction_orders"][
            0
        ]["power_ratio"] += 2.0e-8
        failed = build_mpi_identity(
            failed_records,
            method="hybrid",
            physical_core_count=48,
            funnel=funnel,
        )
        self.assertEqual(failed["status"], "not_qualified")

    def test_missing_mpi16_and_oversubscription_fail(self) -> None:
        records = [self._hybrid(size) for size in (1, 8)]
        result = build_mpi_identity(
            records,
            method="hybrid",
            physical_core_count=4,
            funnel={},
        )
        self.assertEqual(result["status"], "not_qualified")
        self.assertFalse(result["checks"]["required_mpi_sizes_present_once"])
        self.assertFalse(result["checks"]["no_oversubscription"])


if __name__ == "__main__":
    unittest.main()
