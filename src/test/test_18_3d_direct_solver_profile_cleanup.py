import unittest

from mpi4py import MPI

from src.common.config_3d import SimulationConfig3D
from src.solvers.common_3d_solve import _prepare_direct_lu_options_for_comm


class DirectSolverProfileCleanupTests(unittest.TestCase):
    def test_current_public_profiles_are_accepted(self):
        for profile in ("default", "mumps_ooc", "mumps_blr"):
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

    def test_mumps_ooc_extra_options_override_profile_defaults(self):
        cfg = SimulationConfig3D(
            petsc_direct_solver_profile="mumps_ooc",
            petsc_extra_options={"mat_mumps_icntl_14": 200},
        )
        options, _, reason = _prepare_direct_lu_options_for_comm(MPI.COMM_SELF, cfg)
        if reason is not None and "does not report MUMPS" in reason:
            self.skipTest(reason)
        self.assertEqual(options["mat_mumps_icntl_14"], 200)

    def test_mumps_blr_is_an_explicit_direct_factorization_profile(self):
        cfg = SimulationConfig3D(petsc_direct_solver_profile="mumps_blr")
        options, selected, reason = _prepare_direct_lu_options_for_comm(
            MPI.COMM_SELF, cfg
        )
        if reason is not None and "does not report MUMPS" in reason:
            self.skipTest(reason)
        self.assertEqual(selected, "mumps")
        self.assertEqual(options["ksp_type"], "preonly")
        self.assertEqual(options["pc_type"], "lu")
        self.assertEqual(options["mat_mumps_icntl_35"], 1)
        self.assertEqual(options["mat_mumps_cntl_7"], 1.0e-5)


if __name__ == "__main__":
    unittest.main()
