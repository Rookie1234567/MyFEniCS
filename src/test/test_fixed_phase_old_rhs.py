"""Supplementary zero-carrier RHS regression without another solve/factor."""

import numpy as np
from src.geometry.fixed_phase_plan import fixture_design
from src.solvers.fixed_phase_fem import build_model, physical_rhs
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    build_physical_rhs,
    destroy_same_mesh_physical_action,
)


def test_zero_carrier_rhs_matches_unchanged_ordinary_default():
    model = build_model(fixture_design(), 3, False)
    try:
        new, _ = physical_rhs(model["bundle"])
        old, _ = build_physical_rhs(model["bundle"])
        try:
            relative = float(
                np.linalg.norm(new.array - old.array) / np.linalg.norm(old.array)
            )
            print("zero_carrier_rhs_old_default_relative", relative, flush=True)
            assert relative <= 1e-10
        finally:
            new.destroy()
            old.destroy()
    finally:
        destroy_same_mesh_physical_action(model["bundle"])
