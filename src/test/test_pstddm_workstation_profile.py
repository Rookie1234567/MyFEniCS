"""No-FE fixtures for the opt-in native-Linux PSTDDM workstation profile."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.pstddm_partition_pilot import supervise
from benchmarks.pstddm_partition_pilot.workstation_review import review_saved_n2_pair
from scipy import sparse
from src.runners.pstddm_workstation_case import (
    _sha256,
    _source_sha,
    run_workstation_case,
    validate_supervisor_handoff,
    validate_workstation_cgroup,
)
from src.solvers.pstddm_material import derive_si_optical_identity
from src.solvers.pstddm_model import make_cfg, workstation_spec_from_material_identity


ROOT = Path(__file__).resolve().parents[2]


class WorkstationProfileFixtures(unittest.TestCase):
    def test_p6_retry_cache_requires_same_math_runtime_and_product_hash(self):
        import json
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); donor=root/'p6_h10_direct_13p5'; output=root/'p6_h10_direct_13p5_retry1'
            donor.mkdir(); output.mkdir()
            input_path=root/'old.dat'
            input_path.write_text('case_id="p6_h10_direct_13p5"\nh_nm=10.0\n')
            runtime={key: {} for key in ('activation_and_abi_dependencies','PETSc_scalar_type',
                     'PETSc_integer_type','PETSc_version','MPI_library','modules','python_executable')}
            runtime_path=donor/'runtime_receipt.json';runtime_path.write_text(json.dumps(runtime))
            source={'src/solvers/volume.py':'frozen'}
            identity=dict(input_path=str(input_path),input_sha256=_sha256(input_path),source_sha='old',
                          source_hashes=source,runtime_receipt_sha256=_sha256(runtime_path))
            (donor/'supervisor_identity.json').write_text(json.dumps(identity))
            cache=donor/'cache/fenics/kernel.so';cache.parent.mkdir(parents=True);cache.write_bytes(b'qualified')
            inventory={'cache/fenics/kernel.so':dict(bytes=cache.stat().st_size,sha256=_sha256(cache))}
            (donor/'artifact_hashes.json').write_text(json.dumps(inventory))
            document=dict(case_id=output.name,h_nm=10.0)
            result=supervise._seed_p6_retry_jit_cache(output,document,runtime,source,0)
            self.assertEqual(result['files'],1)
            self.assertEqual((output/'cache/fenics/kernel.so').read_bytes(),cache.read_bytes())
            with self.assertRaisesRegex(RuntimeError,'mathematical'):
                supervise._seed_p6_retry_jit_cache(output,{**document,'h_nm':7.5},runtime,source,0)
            with self.assertRaisesRegex(RuntimeError,'dependency'):
                supervise._seed_p6_retry_jit_cache(output,document,runtime,{'src/solvers/volume.py':'changed'},0)
            cache.write_bytes(b'corrupted')
            with self.assertRaisesRegex(RuntimeError,'identity'):
                supervise._seed_p6_retry_jit_cache(output,document,runtime,source,0)

    def test_p6_budget_is_explicit_and_historical_profile_stays_unchanged(self):
        self.assertEqual(supervise._workstation_limits(
            'workstation', 'pstddm_stationary_workstation_pilot'),
            (8_000_000_000, 1800, 'budget_ledger.json'))
        self.assertEqual(supervise._workstation_limits(
            'workstation-p6', 'pstddm_p6_convergence_workstation'),
            (64 << 30, 7200, 'budget_ledger_p6.json'))
        with self.assertRaisesRegex(ValueError, 'profile/model'):
            supervise._workstation_limits('workstation-p6', 'pstddm_stationary_workstation_pilot')
        facts = dict(memory_current_bytes=60 << 30, memory_max_bytes=64 << 30,
                     swap_current_bytes=0, swap_max_bytes=0)
        validate_workstation_cgroup('/p6', facts, '/abi', tree_limit_bytes=64 << 30)
        with self.assertRaisesRegex(ValueError, 'memory.max'):
            validate_workstation_cgroup('/p6', facts, '/abi')
        with self.assertRaises(MemoryError):
            validate_workstation_cgroup('/p6', facts, '/abi',
                                        tree_limit_bytes=64 << 30, future_bytes=4 << 30)
        with self.assertRaisesRegex(ValueError, 'swap'):
            validate_workstation_cgroup('/p6', {**facts, 'swap_current_bytes':1},
                                        '/abi', tree_limit_bytes=64 << 30)
        with self.assertRaisesRegex(MemoryError, 'ancestor'):
            validate_workstation_cgroup('/p6', {**facts, 'ancestors':[
                dict(path='/parent', memory_max_bytes=100 << 30, memory_current_bytes=99 << 30)]},
                '/abi', tree_limit_bytes=64 << 30, future_bytes=1 << 30)

    def test_13p5_direct_dat_dry_run_is_a_no_fe_preflight(self):
        result = run_workstation_case(
            ROOT / "input/pstddm_workstation_pilot/13p5_direct.dat", dry_run=True,
        )

        self.assertEqual(result["status"], "VALID_CONFIGURATION_NOT_RUN")
        preflight = result["preflight"]["model_preflight"]
        self.assertEqual(preflight["axis_cell_counts"], [4, 4, 16])
        self.assertEqual(preflight["cells"], 256)
        self.assertEqual(preflight["independent_fe_rows"], 6272)
        self.assertEqual(preflight["mode_count"], 612)
        self.assertEqual((preflight["selected_m_max"], preflight["selected_n_max"]), (4, 8))
        self.assertEqual(preflight["mode_window_policy"], "all_propagating_plus_rectangular_one_order_padding")

    def test_stationary_dtn_is_global_and_legacy_pml_remains_available(self):
        legacy_pml = make_cfg("pml", degree=2)
        self.assertTrue(legacy_pml.use_pml)

        material = derive_si_optical_identity(13.5)
        model = workstation_spec_from_material_identity(material)
        stationary_dtn = make_cfg("dtn", degree=2, model_spec=model)
        self.assertFalse(stationary_dtn.use_pml)
        self.assertEqual(stationary_dtn.mesh_axis_cell_counts_requested, (4, 4, 16))
        with self.assertRaisesRegex(ValueError, "local to PSTDDM"):
            make_cfg("pml", degree=2, model_spec=model)

    def test_case_cgroup_must_be_distinct_capped_and_swap_free(self):
        facts = {
            "memory_current_bytes": 1_000_000_000,
            "memory_max_bytes": 8_000_000_000,
            "swap_current_bytes": 0,
            "swap_max_bytes": 0,
        }
        validate_workstation_cgroup(
            "/system.slice/pstddm-case.scope", facts,
            "/system.slice/pstddm-abi-receipt-20261114.service",
        )
        with self.assertRaisesRegex(ValueError, "separate"):
            validate_workstation_cgroup(
                "/system.slice/pstddm-abi-receipt-20261114.service", facts,
                "/system.slice/pstddm-abi-receipt-20261114.service",
            )
        wrong_cap = {**facts, "memory_max_bytes": 7_000_000_000}
        with self.assertRaisesRegex(ValueError, "memory.max"):
            validate_workstation_cgroup(
                "/system.slice/pstddm-case.scope", wrong_cap,
                "/system.slice/pstddm-abi-receipt-20261114.service",
            )

    def test_supervisor_handoff_accepts_only_its_precreated_empty_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            scope = Path(temporary).resolve()
            input_dir = scope / "input"
            runs = scope / "runs"
            input_dir.mkdir()
            runs.mkdir()
            case_path = input_dir / "13p5_direct.dat"
            case_path.write_text("fixture input\n", encoding="utf-8")
            case_id = "13p5_direct"
            output = runs / case_id
            input_sha = _sha256(case_path)
            parent_pid = os.getpid()
            runtime = {"runtime_profile": "native_linux", "fixture": True}
            identity = {
                "case_id": case_id,
                "supervisor_pid": parent_pid,
                "source_sha": _source_sha(),
                "input_path": str(case_path),
                "input_sha256": input_sha,
                "scope_root": str(scope),
                "runs_root": str(runs),
            }
            supervise._workstation_prepare_case_output(output, runtime, identity)

            with patch.dict(os.environ, {"PSTDDM_WORKSTATION_SUPERVISOR_PID": str(parent_pid)}):
                accepted = validate_supervisor_handoff(
                    case_path, case_id, input_sha, scope, output, parent_pid=parent_pid,
                )
                self.assertEqual(accepted["case_id"], case_id)
                (output / "A.npz").write_bytes(b"science output")
                with self.assertRaisesRegex(RuntimeError, "unexpected artifacts"):
                    validate_supervisor_handoff(
                        case_path, case_id, input_sha, scope, output, parent_pid=parent_pid,
                    )

    def test_n2_local_review_missing_matrices_is_explicitly_not_recomputable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = sparse.eye(2, format="csr", dtype=complex)
            result = review_saved_n2_pair(
                root / "pair0_map.npz", root / "pair0_L.npz", original,
                in_process_relative=4.2e-15,
            )
        self.assertEqual(result["status"], "NOT_RECOMPUTABLE_MISSING_SAVED_LOCAL_MATRICES")
        self.assertEqual(result["missing_files"], ["pair0_map.npz", "pair0_L.npz"])
        self.assertEqual(result["in_process_n2_operator_relative"], 4.2e-15)
        self.assertIsNone(result["independent_operator_relative"])

    def test_n2_local_review_recomputes_complete_saved_matrices(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pair_map = sparse.eye(2, format="csr", dtype=complex)
            local = sparse.diags([2.0, 3.0], format="csr", dtype=complex)
            original = pair_map.T @ local @ pair_map
            sparse.save_npz(root / "pair0_map.npz", pair_map)
            sparse.save_npz(root / "pair0_L.npz", local)
            result = review_saved_n2_pair(
                root / "pair0_map.npz", root / "pair0_L.npz", original,
                in_process_relative=0.0,
            )
        self.assertEqual(result["status"], "INDEPENDENT_N2_LOCAL_MATRIX_RECOMPUTATION_PASS")
        self.assertEqual(result["missing_files"], [])
        self.assertEqual(result["independent_operator_relative"], 0.0)

    def test_n2_local_review_fails_for_complete_but_mismatched_matrices(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pair_map = sparse.eye(2, format="csr", dtype=complex)
            local = sparse.diags([2.0, 3.0], format="csr", dtype=complex)
            original = sparse.diags([2.0, 4.0], format="csr", dtype=complex)
            sparse.save_npz(root / "pair0_map.npz", pair_map)
            sparse.save_npz(root / "pair0_L.npz", local)
            with self.assertRaisesRegex(AssertionError, "operator mismatch"):
                review_saved_n2_pair(
                    root / "pair0_map.npz", root / "pair0_L.npz", original,
                    in_process_relative=0.0,
                )


if __name__ == "__main__":
    unittest.main()
