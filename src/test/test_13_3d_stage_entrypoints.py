from __future__ import annotations

import unittest
from pathlib import Path

from src import main as main_module
from src.common.config_3d import (
    SI_GRATING_INDEX_EUV_13P5_NM,
    SI_SUBSTRATE_INDEX_EUV_13P5_NM,
    normal_incidence_airbox_config,
)
from src.solvers.solve_maxwell_3d_stage_1_airbox import run_stage1_airbox_3d_case
from src.solvers.solve_maxwell_3d_stage_2a_floquet_airbox import run_stage2a_floquet_airbox_3d_case
from src.solvers.solve_maxwell_3d_stage_2b_pml_airbox import run_stage2b_pml_airbox_3d_case
from src.solvers.solve_maxwell_3d_stage_2c_fresnel_interface import run_stage2c_fresnel_interface_3d_case
from src.solvers.solve_maxwell_3d_stage_4a_flat_layer_sanity import run_stage4a_flat_layer_sanity_3d_case
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import run_stage4b_block_grating_3d_case


class Test3DStageEntrypoints(unittest.TestCase):
    def test_stage_wrappers_reject_wrong_stage_case_before_solving(self):
        out_dir = Path("unused")
        stage1 = normal_incidence_airbox_config(stage_case="stage1_airbox")
        stage2a = normal_incidence_airbox_config(stage_case="floquet_airbox")
        stage2b = normal_incidence_airbox_config(stage_case="pml_airbox")
        stage2c = normal_incidence_airbox_config(stage_case="fresnel_interface")
        stage4a = normal_incidence_airbox_config(stage_case="stage4_flat_layer_sanity")
        stage4b = normal_incidence_airbox_config(stage_case="stage4_block_grating")

        with self.assertRaises(ValueError):
            run_stage1_airbox_3d_case(stage2a, out_dir)
        with self.assertRaises(ValueError):
            run_stage2a_floquet_airbox_3d_case(stage1, out_dir)
        with self.assertRaises(ValueError):
            run_stage2b_pml_airbox_3d_case(stage2c, out_dir)
        with self.assertRaises(ValueError):
            run_stage2c_fresnel_interface_3d_case(stage2b, out_dir)
        with self.assertRaises(ValueError):
            run_stage4a_flat_layer_sanity_3d_case(stage4b, out_dir)
        with self.assertRaises(ValueError):
            run_stage4b_block_grating_3d_case(stage4a, out_dir)

    def test_pycharm_3d_args_use_only_active_dataclass_group(self):
        args = main_module._pycharm_args_3d()
        self.assertIn("--stage-case", args)
        self.assertEqual(args[args.index("--stage-case") + 1], "stage4_block_grating")
        self.assertIn("--period-x", args)
        self.assertIn("--grating-width-x", args)
        self.assertIn("--n-grating", args)
        self.assertEqual(complex(args[args.index("--n-grating") + 1]), SI_GRATING_INDEX_EUV_13P5_NM)
        self.assertIn("--n-substrate", args)
        self.assertEqual(complex(args[args.index("--n-substrate") + 1]), SI_SUBSTRATE_INDEX_EUV_13P5_NM)
        self.assertIn("--substrate-material-label", args)
        self.assertEqual(args[args.index("--substrate-material-label") + 1], "Si / silicon")
        self.assertIn("--grating-material-label", args)
        self.assertEqual(args[args.index("--grating-material-label") + 1], "Si / silicon")
        self.assertIn("--validation-role", args)
        self.assertEqual(args[args.index("--validation-role") + 1], "numerical_sanity_only")
        self.assertNotIn("floquet_airbox", args)


if __name__ == "__main__":
    unittest.main()
