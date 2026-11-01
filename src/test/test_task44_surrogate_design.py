from __future__ import annotations

import json

import tomllib

from scripts.task44_surrogate_design import (
    DESIGN_PATH,
    REPOSITORY_ROOT,
    TEMPLATE_PATH_V2,
    render_candidate_input,
)


def test_candidate_renderer_keeps_v1_default_and_supports_frozen_v2():
    template = (REPOSITORY_ROOT / TEMPLATE_PATH_V2).read_text(encoding="utf-8")
    frozen_v1 = json.loads((REPOSITORY_ROOT / DESIGN_PATH).read_text(encoding="utf-8"))
    samples = {
        sample["sample_id"]: sample
        for sample in frozen_v1["samples"]
        if sample["sample_id"] in {"train_A", "train_C", "train_D"}
    }

    for sample_id in ("train_A", "train_C", "train_D"):
        thicknesses = samples[sample_id]["thicknesses_nm"]
        height = sum(thicknesses)
        v1 = tomllib.loads(
            render_candidate_input(
                template, sample_id, thicknesses, "training"
            ).decode("utf-8")
        )
        v2 = tomllib.loads(
            render_candidate_input(
                template, sample_id, thicknesses, "training", version="v2"
            ).decode("utf-8")
        )

        assert v1["run_id"] == f"task44_{sample_id}_v1"
        assert v1["comparison_group"] == "task44_gp_training_v1"
        assert v2["run_id"] == f"task44_{sample_id}_v2"
        assert v2["comparison_group"] == "task44_gp_training_v2"
        assert v2["geometry"]["grating_layer_thicknesses_nm"] == thicknesses
        assert v2["geometry"]["grating_height_nm"] == height
        assert v2["geometry"]["z_max_nm"] == height + 0.5
        assert v2["discretization"]["nedelec_degree"] == 6
        assert v2["discretization"]["mesh_axis_cell_counts"] == [3, 12, 8]
        assert v2["boundary"]["dtn_order_policy"] == "auto_propagating"
        assert v2["method"]["kind"] == "full3d_direct"
        assert v2["solver"]["direct_solver_profile"] == "mumps_exact"
