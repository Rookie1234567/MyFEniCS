from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.adaptivity.dtn_goal_adjoint import (
    dtn_power_goal_value,
    replicated_adjoint_partition_content_identity,
    run_target_actual_dtn_adjoint,
    verify_hermitian_discrete_adjoint,
)
from src.common.config_3d import target_stage4_config
from src.common.modes_3d import outgoing_port_modes_3d
from src.solvers.dtn_port_3d import _port_power_metrics


def _idx(values) -> np.ndarray:
    return np.asarray(values, dtype=PETSc.IntType)


class Task035ActualDtnAdjointTests(unittest.TestCase):
    def test_r00_goal_matches_official_zero_order_modal_power(self) -> None:
        config = target_stage4_config(degree=2, h_nm=50.0)
        modes = outgoing_port_modes_3d(config)
        auxiliary = np.asarray(
            [
                complex(0.02 * (index + 1), -0.01 * index)
                for index in range(len(modes))
            ],
            dtype=np.complex128,
        )
        incident = np.zeros(len(modes), dtype=np.complex128)
        metrics = _port_power_metrics(
            config,
            modes,
            auxiliary,
            incident.tolist(),
        )
        functional = dtn_power_goal_value(
            config,
            modes,
            auxiliary,
            incident,
            goal="R00_total",
        )
        self.assertAlmostEqual(functional, metrics["R00_total"])
        self.assertLessEqual(metrics["R00_total"], metrics["R_total"])
        self.assertAlmostEqual(
            metrics["R00_total"],
            metrics["R00_s"] + metrics["R00_p"],
        )

    def test_target_p2_h50_official_r_t_adjoints(self) -> None:
        out_dir = (
            Path(__file__).resolve().parents[2]
            / "benchmarks/artifacts/task035/actual_dtn_adjoint"
            / f"fixture_mpi{MPI.COMM_WORLD.size}"
        )
        result = run_target_actual_dtn_adjoint(out_dir)
        self.assertTrue(result["pass"], result["adjoint"])
        self.assertEqual(
            result["adjoint"]["status"],
            "actual_discrete_dtn_adjoint_pass",
        )
        for goal in ("R00_total", "R_total", "T_total"):
            report = result["adjoint"]["goals"][goal]
            self.assertTrue(report["pass"], report)
            self.assertLess(
                report["official_functional_absolute_closure"], 1.0e-12
            )
            self.assertLess(
                report["adjoint_residual"]["relative_residual"], 1.0e-10
            )
            self.assertLess(
                report["finite_difference_relative_error"], 1.0e-7
            )

    def test_complex_nonhermitian_discrete_adjoint_and_fd(self) -> None:
        comm = MPI.COMM_WORLD
        dense = np.asarray(
            (
                (3.0 + 0.2j, 0.4 - 0.1j, 0.0 + 0.0j),
                (-0.2 + 0.3j, 2.0 - 0.4j, 0.5 + 0.0j),
                (0.0 + 0.1j, -0.3 + 0.2j, 1.7 + 0.1j),
            ),
            dtype=np.complex128,
        )
        matrix = PETSc.Mat().createAIJ(size=(3, 3), comm=comm)
        matrix.setUp()
        row_start, row_end = matrix.getOwnershipRange()
        for row in range(row_start, row_end):
            matrix.setValues(
                _idx([row]),
                _idx(range(3)),
                dense[row].reshape((1, 3)),
            )
        matrix.assemble()

        right_hand_side = PETSc.Vec().createMPI(3, comm=comm)
        b_values = np.asarray(
            (1.0 - 0.1j, -0.2 + 0.4j, 0.3 + 0.2j),
            dtype=np.complex128,
        )
        start, end = right_hand_side.getOwnershipRange()
        if end > start:
            right_hand_side.setValues(
                _idx(range(start, end)),
                b_values[start:end],
            )
        right_hand_side.assemble()

        solver = PETSc.KSP().create(comm)
        solver.setType(PETSc.KSP.Type.PREONLY)
        solver.getPC().setType(PETSc.PC.Type.LU)
        solver.getPC().setFactorSolverType("mumps")
        solver.setOperators(matrix)
        state = right_hand_side.duplicate()
        solver.solve(right_hand_side, state)
        self.assertGreater(solver.getConvergedReason(), 0)

        owner = max(
            rank
            for rank, ownership in enumerate(comm.allgather((start, end)))
            if ownership[0] <= 2 < ownership[1]
        )

        def last_value(vector: PETSc.Vec) -> complex:
            local_start, local_end = vector.getOwnershipRange()
            value = (
                complex(vector.getValues(_idx([2]))[0])
                if local_start <= 2 < local_end
                else 0.0 + 0.0j
            )
            return complex(comm.bcast(value, root=owner))

        incident = 0.17 - 0.08j
        weight = 1.9
        outgoing = last_value(state) - incident
        gradient = state.duplicate()
        gradient.set(PETSc.ScalarType(0.0))
        if start <= 2 < end:
            gradient.setValue(
                2,
                PETSc.ScalarType(2.0 * weight * outgoing),
            )
        gradient.assemble()

        captured_adjoint: dict[str, np.ndarray] = {}

        def capture_adjoint(vector: PETSc.Vec) -> None:
            local_start, local_end = vector.getOwnershipRange()
            packet = (
                int(local_start),
                int(local_end),
                np.asarray(
                    vector.getArray(readonly=True),
                    dtype=np.complex128,
                ).copy(),
            )
            replicated = np.empty(vector.getSize(), dtype=np.complex128)
            for owned_start, owned_end, owned_values in comm.allgather(packet):
                replicated[owned_start:owned_end] = owned_values
            captured_adjoint["values"] = replicated

        report = verify_hermitian_discrete_adjoint(
            matrix,
            right_hand_side,
            state,
            solver,
            gradient,
            lambda candidate: weight
            * abs(last_value(candidate) - incident) ** 2,
            adjoint_observer=capture_adjoint,
        )
        self.assertTrue(report["pass"], report)
        self.assertLess(
            report["adjoint_residual"]["relative_residual"], 1.0e-12
        )
        self.assertLess(report["direct_adjoint_relative_error"], 1.0e-10)
        self.assertLess(report["finite_difference_relative_error"], 1.0e-8)
        self.assertEqual(
            report["complex_adjoint_equation"], "A^H z = g"
        )
        identity = report["adjoint_content_identity"]
        self.assertEqual(identity["mpi_size"], comm.size)
        self.assertEqual(
            identity["communicator_ordered_world_ranks"],
            list(range(comm.size)),
        )
        recomputed = replicated_adjoint_partition_content_identity(
            captured_adjoint["values"],
            identity,
        )
        self.assertEqual(identity, recomputed)
        self.assertEqual(
            report["adjoint_content_sha256"],
            recomputed["global_value_sha256"],
        )
        self.assertEqual(
            report["adjoint_partition_content_sha256"],
            recomputed["global_content_sha256"],
        )
        if comm.size == 2:
            original_split = int(identity["partitions"][0]["ownership_end"])
            alternate_split = 1 if original_split != 1 else 2
            alternate = replicated_adjoint_partition_content_identity(
                captured_adjoint["values"],
                {
                    "partitions": [
                        {
                            "rank": 0,
                            "world_rank": 0,
                            "ownership_start": 0,
                            "ownership_end": alternate_split,
                        },
                        {
                            "rank": 1,
                            "world_rank": 1,
                            "ownership_start": alternate_split,
                            "ownership_end": len(
                                captured_adjoint["values"]
                            ),
                        },
                    ]
                },
            )
            self.assertEqual(
                alternate["global_value_sha256"],
                identity["global_value_sha256"],
            )
            self.assertNotEqual(
                alternate["global_content_sha256"],
                identity["global_content_sha256"],
            )

        gradient.destroy()
        state.destroy()
        solver.destroy()
        right_hand_side.destroy()
        matrix.destroy()


if __name__ == "__main__":
    unittest.main()
