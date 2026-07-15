from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.constraints.cross_section_floquet import (
    build_cross_section_floquet_constraints,
    build_distributed_constraint_transform,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)


class Task033CrossSectionExactConstraintTests(unittest.TestCase):
    @staticmethod
    def _spaces(degree: int):
        # The cross-section degree is independent of the legacy 3D Stage-4
        # geometry factory guard, so keep that factory on its p2 baseline.
        cfg = target_stage4_config(degree=2, h_nm=12.5)
        cross_section = build_matching_cross_section(cfg, "air")
        spaces = build_cross_section_spaces(
            cross_section,
            transverse_degree=degree,
            longitudinal_degree=degree,
        )
        return cross_section, spaces

    def test_implementation_has_no_probe_fit_or_global_boundary_map(self):
        source = (
            Path(__file__).parents[1] / "constraints" / "cross_section_floquet.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("allgather(", source)
        self.assertNotIn("pinv(", source)
        self.assertNotIn("lstsq(", source)
        self.assertIn("distributed_match_periodic_records", source)
        self.assertIn("edge_coefficient_transform", source)
        self.assertIn("comm.exscan", source)
        self.assertIn('status = "slave_chain"', source)

    def test_p1_p4_exact_constraints_reproduce_bloch_interpolants(self):
        kx = 0.017
        ky = -0.023
        for degree in range(1, 5):
            with self.subTest(degree=degree):
                cross_section, spaces = self._spaces(degree)
                constraints = build_cross_section_floquet_constraints(
                    cross_section,
                    spaces,
                    kx=kx,
                    ky=ky,
                )
                transform = build_distributed_constraint_transform(spaces, constraints)
                transverse = fem.Function(spaces.transverse)
                longitudinal = fem.Function(spaces.longitudinal)

                def transverse_field(x):
                    phase = np.exp(1j * (kx * x[0] + ky * x[1]))
                    return np.vstack((phase, (0.35 - 0.2j) * phase))

                def longitudinal_field(x):
                    return (0.7 + 0.1j) * np.exp(1j * (kx * x[0] + ky * x[1]))

                transverse.interpolate(transverse_field)
                longitudinal.interpolate(longitudinal_field)
                transverse.x.scatter_forward()
                longitudinal.x.scatter_forward()
                full = fem.Function(spaces.mixed)
                full.x.array[:] = 0.0
                full.x.array[spaces.transverse_to_mixed] = transverse.x.array
                full.x.array[spaces.longitudinal_to_mixed] = longitudinal.x.array
                full.x.scatter_forward()

                index_map = spaces.mixed.dofmap.index_map
                full_local = int(index_map.size_local)
                slave_local = set(int(value) for value in constraints.slave_local)
                free_local = np.asarray(
                    [row for row in range(full_local) if row not in slave_local],
                    dtype=np.int32,
                )
                q = PETSc.Vec().createMPI(
                    (
                        transform.reduced_local_size,
                        transform.reduced_global_size,
                    ),
                    comm=cross_section.mesh.comm,
                )
                reconstructed = transform.matrix.createVecLeft()
                try:
                    q_array = q.getArray()
                    q_array[:] = full.x.array[free_local]
                    q.assemble()
                    transform.matrix.mult(q, reconstructed)
                    difference = (
                        np.asarray(reconstructed.getArray(readonly=True))
                        - full.x.array[:full_local]
                    )
                    local_num = float(np.vdot(difference, difference).real)
                    local_den = float(
                        np.vdot(
                            full.x.array[:full_local], full.x.array[:full_local]
                        ).real
                    )
                    numerator = cross_section.mesh.comm.allreduce(local_num, op=MPI.SUM)
                    denominator = cross_section.mesh.comm.allreduce(
                        local_den, op=MPI.SUM
                    )
                    relative_error = float(
                        np.sqrt(numerator / max(denominator, 1.0e-30))
                    )
                    self.assertLess(relative_error, 5.0e-12)
                    self.assertEqual(constraints.max_probe_residual, 0.0)
                    self.assertEqual(
                        constraints.orientation_schema,
                        "basix_interval_exact_p1_p4",
                    )
                    self.assertFalse(constraints.used_full_boundary_gather)
                    self.assertFalse(constraints.created_dense_boundary_square)
                    self.assertGreater(constraints.transverse_constraint_count, 0)
                    self.assertGreater(constraints.longitudinal_constraint_count, 0)
                    self.assertLess(constraints.max_pair_coordinate_error, 1.0e-12)
                    self.assertEqual(
                        transform.reduced_global_size,
                        transform.full_global_size - transform.global_slave_count,
                    )
                    self.assertIn("MPI exscan", transform.ownership_note)
                finally:
                    reconstructed.destroy()
                    q.destroy()
                    transform.matrix.destroy()

    def test_master_to_slave_chain_fails_closed_without_global_slave_map(self):
        cross_section, spaces = self._spaces(4)
        constraints = build_cross_section_floquet_constraints(
            cross_section,
            spaces,
            kx=0.017,
            ky=-0.023,
        )
        full_global = int(spaces.mixed.dofmap.index_map.size_global)
        local_candidate = int(min(constraints.slave_global, default=full_global))
        global_slave = int(
            cross_section.mesh.comm.allreduce(local_candidate, op=MPI.MIN)
        )
        local_owner = (
            int(cross_section.mesh.comm.rank)
            if global_slave in set(int(value) for value in constraints.slave_global)
            else int(cross_section.mesh.comm.size)
        )
        slave_owner = int(cross_section.mesh.comm.allreduce(local_owner, op=MPI.MIN))
        bad_masters = constraints.master_global.copy()
        bad_owners = constraints.master_owners.copy()
        if len(bad_masters):
            bad_masters[0] = global_slave
            bad_owners[0] = slave_owner
        malformed = replace(
            constraints,
            master_global=bad_masters,
            master_owners=bad_owners,
        )
        with self.assertRaisesRegex(RuntimeError, "slave_chain"):
            build_distributed_constraint_transform(spaces, malformed)


if __name__ == "__main__":
    unittest.main()
