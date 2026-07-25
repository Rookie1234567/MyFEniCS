from __future__ import annotations

import gc
import inspect
import os
from pathlib import Path
import unittest
import weakref

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.run_task034_wsl_qualification import _dolfinx_mpc_abi_probe
from benchmarks.task033_qep_qualification import resource_authority_gate
from benchmarks.task034_numerical_blob_checker import build_record
from benchmarks.task034_wsl_resources import (
    effective_memory_limit,
    resource_authority_sample,
)
from src.common.distributed_matrix_diagnostics import (
    distributed_active_column_count,
)
from src.constraints.high_order_floquet_trace import (
    FloquetTopologyCache,
    FloquetTopologyKey,
    FloquetTraceTopology,
)

ROOT = Path(__file__).resolve().parents[2]


class _Owner:
    pass


class Task034HardeningTests(unittest.TestCase):
    def _topology(self, token: str = "task034") -> FloquetTraceTopology:
        return FloquetTraceTopology(
            key=FloquetTopologyKey(
                mesh_token=token, element_family="N1curl", degree=3
            ),
            blocks=(),
            topology_build_seconds=0.0,
            bytes_sent=0,
            bytes_received=0,
        )

    def test_cache_weak_owners_release_and_prevent_stale_hit(self) -> None:
        cache = FloquetTopologyCache(max_entries=2)
        topology = self._topology()
        mesh = _Owner()
        space = _Owner()
        mesh_ref = weakref.ref(mesh)
        space_ref = weakref.ref(space)
        cache.put(topology, mesh=mesh, space=space)
        self.assertIs(cache.get(topology.key, mesh=mesh, space=space), topology)
        del mesh, space
        gc.collect()
        self.assertIsNone(mesh_ref())
        self.assertIsNone(space_ref())
        self.assertIsNone(
            cache.get(topology.key, mesh=_Owner(), space=_Owner())
        )
        self.assertEqual(len(cache), 0)

    def test_cache_clear_is_explicit_and_idempotent(self) -> None:
        cache = FloquetTopologyCache(max_entries=2)
        cache.put(self._topology())
        self.assertEqual(len(cache), 1)
        cache.clear()
        cache.clear()
        self.assertEqual(len(cache), 0)

    def test_active_column_count_uses_owner_routed_marker(self) -> None:
        matrix = PETSc.Mat().createAIJ([4, 8], nnz=3, comm=PETSc.COMM_WORLD)
        try:
            first, last = matrix.getOwnershipRange()
            for row in range(first, last):
                columns = [0, 2] if row % 2 == 0 else [2, 5]
                matrix.setValues(row, columns, np.ones(len(columns)))
            matrix.assemblyBegin()
            matrix.assemblyEnd()
            result = distributed_active_column_count(matrix)
            self.assertEqual(result.global_count, 3)
            self.assertFalse(result.python_object_allgather_used)
            self.assertIn("owner routing", result.communication)
            self.assertIn("local_active_columns", result.memory_complexity)
        finally:
            matrix.destroy()

    def test_active_column_count_ignores_explicit_zero_entries(self) -> None:
        matrix = PETSc.Mat().createAIJ([2, 8], nnz=3, comm=PETSc.COMM_WORLD)
        try:
            first, last = matrix.getOwnershipRange()
            for row in range(first, last):
                matrix.setValues(row, [0, 2, 5], [1.0, 1.0, 0.0])
            matrix.assemblyBegin()
            matrix.assemblyEnd()
            result = distributed_active_column_count(matrix)
            self.assertEqual(result.global_count, 2)
        finally:
            matrix.destroy()

    def test_million_column_sparse_diagnostic_memory_is_owned(self) -> None:
        columns = 1_000_000
        matrix = PETSc.Mat().createAIJ([2, columns], nnz=2, comm=PETSc.COMM_WORLD)
        try:
            first, last = matrix.getOwnershipRange()
            for row in range(first, last):
                matrix.setValues(row, [1, columns - 1], [1.0, 1.0])
            matrix.assemblyBegin()
            matrix.assemblyEnd()
            result = distributed_active_column_count(matrix)
            self.assertEqual(result.global_count, 2)
            self.assertLessEqual(
                result.marker_owned_entries,
                (columns + MPI.COMM_WORLD.size - 1) // MPI.COMM_WORLD.size,
            )
            self.assertLessEqual(result.local_unique_candidates, 2)
        finally:
            matrix.destroy()

    def test_active_column_implementation_has_no_object_allgather(self) -> None:
        source = inspect.getsource(distributed_active_column_count)
        self.assertNotIn("allgather", source)
        self.assertIn("setValues", source)
        self.assertIn("allreduce", source)

    def test_wsl_authority_separates_job_swap_from_global_diagnostic(self) -> None:
        sample = resource_authority_sample(os.getpid())
        self.assertIn(os.getpid(), sample["process_tree"]["pids"])
        self.assertEqual(
            sample["memory_authority_semantics"],
            "max(process-tree RSS, dedicated job cgroup memory.current when present)",
        )
        self.assertFalse(sample["mumps_ooc_is_swap"])
        self.assertFalse(sample["windows_pagefile_is_linux_swap"])
        self.assertIn("pswpin_pages", sample["wsl_vm_global_swap_diagnostic"])

    def test_nonzero_wsl_global_pswp_is_diagnostic_without_job_cgroup(self) -> None:
        gate = resource_authority_gate({
            "simultaneous_live_worker_rss_sum_bytes": 1024,
            "container_cgroup_current_bytes": None,
            "memory_authority_bytes": 1024,
            "container_memory_limit_bytes": 4096,
            "host_available_memory_bytes": 8192,
            "container_swap_current_bytes": 0,
            "pswpin_delta_pages": 11,
            "pswpout_delta_pages": 7,
            "job_cgroup_dedicated": False,
            "wsl_global_pswp_formal": False,
        })
        self.assertTrue(gate["pass"], gate["failures"])
        self.assertTrue(gate["checks"]["pswpin_delta_zero"])
        self.assertTrue(gate["checks"]["pswpout_delta_zero"])

    def test_dolfinx_mpc_probe_requires_project_complex_abi(self) -> None:
        probe = _dolfinx_mpc_abi_probe()
        self.assertTrue(probe["pass"], probe)
        self.assertTrue(probe["checks"]["dolfinx_complex_loaded"])
        self.assertTrue(probe["checks"]["petsc_complex_loaded"])
        self.assertTrue(probe["checks"]["no_dolfinx_real_loaded"])
        self.assertTrue(probe["checks"]["no_petsc_real_loaded"])

    def test_effective_memory_limit_formula_and_thresholds(self) -> None:
        record = effective_memory_limit()
        self.assertIsNotNone(record["effective_limit_bytes"])
        self.assertLess(record["warning_bytes"], record["termination_bytes"])
        self.assertEqual(
            record["termination_bytes"],
            int(0.95 * record["effective_limit_bytes"]),
        )

    def test_formal_runners_do_not_hide_untracked_paths(self) -> None:
        offenders = []
        for path in (ROOT / "benchmarks").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "--untracked-files=no" in text or "--untracked-files=normal" in text:
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_numerical_blob_checker_classifies_every_required_path(self) -> None:
        record = build_record()
        self.assertTrue(record["formal_pass"], record["failures"])
        self.assertEqual(
            record["corresponding_pde_rerun_required_paths"],
            [
                "src/common/config_3d.py",
                "src/geometry/mesh_builder_3d.py",
                "src/constraints/floquet_3d.py",
                "src/constraints/high_order_floquet_trace.py",
                "src/modes/mode_classification.py",
                "src/coupling/hybrid_internal_modes.py",
                "src/solvers/common_3d_case_flow.py",
                "src/solvers/dtn_port_3d.py",
                "src/solvers/hcurl_cell_static_condensation.py",
                "src/solvers/hybrid_local_dtn.py",
                "src/solvers/hybrid_fem_modal_schur_direct.py",
                "src/solvers/hcurl_multilevel.py",
            ],
        )
        self.assertTrue(all(row["pass"] for row in record["rows"]))

    def test_tracked_activation_is_wsl_complex_and_thread_bounded(self) -> None:
        text = (ROOT / "scripts/activate_myfenics_wsl.sh").read_text()
        self.assertIn("microsoft", text)
        self.assertIn("x86_64-linux-gnu-complex", text)
        self.assertIn("libdolfinx_mpc.so", text)
        self.assertIn("LD_LIBRARY_PATH", text)
        self.assertIn("OMP_NUM_THREADS=1", text)
        self.assertNotIn("/mnt/c", text.lower())


if __name__ == "__main__":
    unittest.main()
