import unittest

import numpy as np

from benchmarks.run_task033_full3d_watchdog import (
    _parse_args,
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
