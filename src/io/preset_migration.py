"""Single source of truth for the T7 ordinary-preset dat migration."""

from __future__ import annotations

from types import MappingProxyType


MIGRATED_PRESET_DATS = MappingProxyType(
    {
        "2d_tm_pml_floquet_smoke": "input/smoke/2d_tm_pml_floquet_smoke.dat",
        "2d_tm_dtn_auxiliary_smoke": "input/smoke/2d_tm_dtn_auxiliary_smoke.dat",
        "2d_tm_dtn_explicit_smoke": "input/smoke/2d_tm_dtn_explicit_smoke.dat",
        "2d_te_port_smoke": "input/smoke/2d_te_port_smoke.dat",
        "2d_complex_absorption": "input/smoke/2d_complex_absorption.dat",
        "2d_euv_grating_direct": "input/examples/2d_euv_grating_direct.dat",
        "3d_stage1_airbox_smoke": "input/smoke/3d_stage1_airbox_smoke.dat",
        "3d_stage2a_floquet_smoke": "input/smoke/3d_stage2a_floquet_smoke.dat",
        "3d_stage2b_pml_smoke": "input/smoke/3d_stage2b_pml_smoke.dat",
        "3d_stage2c_fresnel_smoke": "input/smoke/3d_stage2c_fresnel_smoke.dat",
        "3d_stage4a_flat_layer_direct": "input/smoke/3d_stage4a_flat_layer_direct.dat",
    }
)

MIGRATED_PRESET_NAMES = tuple(MIGRATED_PRESET_DATS)


__all__ = ["MIGRATED_PRESET_DATS", "MIGRATED_PRESET_NAMES"]
