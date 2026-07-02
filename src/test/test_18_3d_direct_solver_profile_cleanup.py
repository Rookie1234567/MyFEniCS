import unittest

from src.common.config_3d import SimulationConfig3D


class DirectSolverProfileCleanupTests(unittest.TestCase):
    def test_current_public_profiles_are_accepted(self):
        for profile in ("default", "mumps_ooc"):
            cfg = SimulationConfig3D(petsc_direct_solver_profile=profile)
            self.assertEqual(cfg.petsc_direct_solver_profile_requested, profile)

    def test_removed_diagnostic_profiles_are_rejected(self):
        removed_profiles = (
            "mumps",
            "mumps_ooc_seq_analysis",
            "mumps_ooc_parallel_analysis",
            "mumps_ooc_requested_legacy",
            "mkl_pardiso",
            "superlu_dist",
            "strumpack",
        )
        for profile in removed_profiles:
            cfg = SimulationConfig3D(petsc_direct_solver_profile=profile)
            with self.subTest(profile=profile):
                with self.assertRaises(ValueError):
                    _ = cfg.petsc_direct_solver_profile_requested


if __name__ == "__main__":
    unittest.main()
