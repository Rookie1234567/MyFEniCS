import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from benchmarks.run_task033_full3d_watchdog import (
    _parse_args,
    _worker,
    _task037_canonical_identity,
    _task037_collect_owned_vector,
)


class _FakeVec:
    def getOwnershipRange(self):
        return (2, 4)

    def getArray(self, readonly=True):
        return np.array([3.0 + 0.0j, 4.0 + 0.0j])

    def getSize(self):
        return 4


class _FakeComm:
    rank = 0

    def gather(self, packet, root=0):
        return [packet, (0, 2, np.array([1.0 + 0.0j, 2.0 + 0.0j]))]


class Task037F0DirectAuthorityTests(unittest.TestCase):
    def test_owned_ranges_and_canonical_identity(self):
        values = _task037_collect_owned_vector(_FakeVec(), _FakeComm())
        np.testing.assert_array_equal(values, np.array([1, 2, 3, 4], dtype="<c16"))
        identity = _task037_canonical_identity("task037.f0.active_trace", values[:2])
        self.assertEqual(identity["namespace"], "task037.f0.active_trace")
        self.assertEqual(identity["shape"], [2])
        self.assertEqual(identity["dtype"], "<c16")
        self.assertEqual(
            identity["sha256"],
            _task037_canonical_identity("task037.f0.active_trace", values[:2])[
                "sha256"
            ],
        )

    def test_observer_flag_requires_task035c_gate(self):
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--degree",
                    "6",
                    "--h-nm",
                    "10",
                    "--task037-f0-vector-observer",
                ]
            )

    def test_f0_observer_forwards_to_solution_slot(self):
        args = SimpleNamespace(
            run_dir=Path("unused"),
            task037_f0_vector_observer=True,
            task037_f1_direct_trace_oracle=None,
            task037_f1_direct_trace_sha256=None,
            task035d_nested_p_dwr_phase=None,
            task035d_selective_face_dwr_phase=None,
        )
        with (
            patch(
                "benchmarks.run_task033_full3d_watchdog._full3d_config",
                return_value=object(),
            ) as config,
            patch(
                "src.solvers.solve_maxwell_3d_stage_4b_block_grating.run_stage4b_block_grating_3d_case"
            ) as solver,
        ):
            self.assertEqual(_worker(args), 0)
        config.assert_called_once_with(args)
        kwargs = solver.call_args.kwargs
        self.assertIsNotNone(kwargs["solution_observer"])
        self.assertIsNone(kwargs["linear_solver_port"])
        self.assertIsNone(kwargs["variable_p_live_observer"])

    def test_f1_direct_trace_oracle_forwards_to_linear_solver_slot(self):
        args = SimpleNamespace(
            run_dir=Path("unused"),
            task037_f0_vector_observer=False,
            task037_f1_direct_trace_oracle=Path("trace.npy"),
            task037_f1_direct_trace_sha256="a" * 64,
            task035d_nested_p_dwr_phase=None,
            task035d_selective_face_dwr_phase=None,
        )
        sentinel = object()
        with (
            patch(
                "benchmarks.run_task033_full3d_watchdog._full3d_config",
                return_value=object(),
            ),
            patch(
                "benchmarks.run_task033_full3d_watchdog._task037_f1_direct_trace_oracle",
                return_value=sentinel,
            ),
            patch(
                "src.solvers.solve_maxwell_3d_stage_4b_block_grating.run_stage4b_block_grating_3d_case"
            ) as solver,
        ):
            self.assertEqual(_worker(args), 0)
        self.assertIs(solver.call_args.kwargs["linear_solver_port"], sentinel)
