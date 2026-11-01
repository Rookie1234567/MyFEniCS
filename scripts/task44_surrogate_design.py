"""Freeze and materialize the initial Task44 six-parameter sample design."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import tomllib

from src.io.input_validation import load_and_resolve
from src.io.run_specification import thaw
from src.studies.task44_surrogate import (
    OUTPUT_NAMES,
    initial_geometry_partitions,
    validate_disjoint_geometry_groups,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = Path("docs/task44_sixlayer_surrogate_0p7nm/sample_design_v1.json")
TEMPLATE_PATH = Path("input/task44_sample_a_condensed_direct_v1.dat")
DESIGN_PATH_V2 = Path("docs/task44_sixlayer_surrogate_0p7nm/sample_design_v2.json")
TEMPLATE_PATH_V2 = Path("input/task44_accuracy_propagation_y2_v1.dat")
DESIGN_SEED = 440731
ANCHOR_B_V2_RUN = Path(
    "results/task44_sixlayer_0p7nm/"
    "task44_accuracy_propagation_y2_20261031__full3d_direct__mpi1__Mna/"
    "20261031T091904.310578Z"
)
ANCHOR_NAMES = ("A", "B", "C", "D")
ANCHOR_RUNS = {
    "A": {
        "input": Path("input/task44_sample_a_condensed_direct_v1.dat"),
        "run": Path(
            "results/task44_sixlayer_0p7nm/sample_A_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T055027.974554Z"
        ),
    },
    "B": {
        "input": Path("input/task44_sample_b_condensed_direct_v1.dat"),
        "run": Path(
            "results/task44_sixlayer_0p7nm/sample_B_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T063009.557323Z"
        ),
    },
    "C": {
        "input": Path("input/task44_sample_c_condensed_direct_v1.dat"),
        "run": Path(
            "results/task44_sixlayer_0p7nm/sample_C_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T070135.788196Z"
        ),
    },
    "D": {
        "input": Path("input/task44_sample_d_condensed_direct_v1.dat"),
        "run": Path(
            "results/task44_sixlayer_0p7nm/sample_D_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T073200.895421Z"
        ),
    },
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return _sha256(payload)


def _replace_line(text: str, key: str, value: str) -> str:
    updated, count = re.subn(
        rf"(?m)^{re.escape(key)}\s*=.*$",
        f"{key} = {value}",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"input template must contain exactly one `{key}` assignment")
    return updated


def render_candidate_input(
    template: str,
    sample_id: str,
    thicknesses_nm: list[float],
    partition: str,
    *,
    version: str = "v1",
) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_]+", sample_id):
        raise ValueError(f"unsafe sample_id: {sample_id}")
    if not re.fullmatch(r"v[0-9]+", version):
        raise ValueError(f"unsafe design version: {version}")
    if len(thicknesses_nm) != 6 or not all(np.isfinite(thicknesses_nm)):
        raise ValueError("each candidate requires six finite thicknesses")
    height = float(sum(thicknesses_nm))
    top = height + 0.5
    text = template
    text = _replace_line(text, "run_id", json.dumps(f"task44_{sample_id}_{version}"))
    text = _replace_line(
        text, "comparison_group", json.dumps(f"task44_gp_{partition}_{version}")
    )
    text = _replace_line(text, "z_max_nm", repr(top))
    text = _replace_line(text, "air_height_nm", repr(top))
    text = _replace_line(text, "grating_height_nm", repr(height))
    text = _replace_line(
        text, "grating_layer_thicknesses_nm", repr(thicknesses_nm)
    )
    parsed = tomllib.loads(text)
    geometry = parsed["geometry"]
    if not np.allclose(geometry["grating_layer_thicknesses_nm"], thicknesses_nm):
        raise ValueError("rendered input changed the thickness vector")
    if not np.isclose(geometry["grating_height_nm"], height):
        raise ValueError("rendered input changed the total column height")
    if not np.isclose(geometry["z_max_nm"], height + 0.5):
        raise ValueError("rendered input changed the top air gap")
    return text.encode("utf-8")


def _physics_definition(config: dict[str, Any]) -> dict[str, Any]:
    geometry = config["geometry"]
    return {
        "model_id": config["model_id"],
        "geometry": {
            "geometry_kind": geometry["geometry_kind"],
            "period_x_nm": geometry["period_x_nm"],
            "period_y_nm": geometry["period_y_nm"],
            "z_min_nm": geometry["z_min_nm"],
            "interface_z_nm": geometry["interface_z_nm"],
            "substrate_thickness_nm": geometry["substrate_thickness_nm"],
            "grating_width_x_nm": geometry["grating_width_x_nm"],
            "grating_width_y_nm": geometry["grating_width_y_nm"],
            "dynamic_air_gap_nm": 0.5,
        },
        "materials": config["materials"],
        "incidence": config["incidence"],
        "boundary": config["boundary"],
        "frozen_thickness_bounds_nm": {"lower": 0.5, "upper": 1.0},
    }


def _geometry_sha256(thicknesses_nm: list[float]) -> str:
    return _canonical_sha256([float(value).hex() for value in thicknesses_nm])


def _resolved_identity(input_path: Path) -> tuple[str, str]:
    specification = load_and_resolve(input_path)
    discrete_definition = {
        "discretization": thaw(specification.discretization),
        "boundary": thaw(specification.boundary),
        "method": thaw(specification.method),
        "solver": thaw(specification.solver),
    }
    return (
        specification.physical_model_sha256,
        _canonical_sha256(discrete_definition),
    )


def _resolved_identity_for_bytes(payload: bytes, sample_id: str) -> tuple[str, str]:
    with tempfile.NamedTemporaryFile(
        prefix=f"task44-{sample_id}-", suffix=".dat", dir="/tmp", delete=False
    ) as handle:
        handle.write(payload)
        staged_path = Path(handle.name)
    try:
        return _resolved_identity(staged_path)
    finally:
        staged_path.unlink(missing_ok=True)


def build_design(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    template_bytes = (root / TEMPLATE_PATH).read_bytes()
    template_text = template_bytes.decode("utf-8")
    template_config = tomllib.loads(template_text)
    physics_hash = _canonical_sha256(_physics_definition(template_config))
    _, discretization_hash = _resolved_identity(root / TEMPLATE_PATH)
    groups = initial_geometry_partitions(seed=DESIGN_SEED)
    validate_disjoint_geometry_groups(groups)

    samples: list[dict[str, Any]] = []
    for anchor, paths in ANCHOR_RUNS.items():
        input_path = root / paths["input"]
        run_path = root / paths["run"]
        manifest = json.loads((run_path / "run_manifest.json").read_text())
        result_path = run_path / "numerical_output/run_summary.json"
        result = json.loads(result_path.read_text())
        source_bytes = input_path.read_bytes()
        expected_input_hash = _sha256(source_bytes)
        if manifest["input_sha256"] != expected_input_hash:
            raise ValueError(f"{anchor} input hash differs from its run manifest")
        physical_hash, resolved_discretization_hash = _resolved_identity(input_path)
        if physical_hash != manifest["physical_model_sha256"]:
            raise ValueError(f"{anchor} resolved physical hash differs from run manifest")
        if resolved_discretization_hash != discretization_hash:
            raise ValueError(f"{anchor} resolved discrete signature is inconsistent")
        labels = {name: float(result[name]) for name in OUTPUT_NAMES}
        thicknesses = [float(value) for value in tomllib.loads(
            source_bytes.decode("utf-8")
        )["geometry"]["grating_layer_thicknesses_nm"]]
        samples.append(
            {
                "sample_id": f"train_{anchor}",
                "partition": "training",
                "thicknesses_nm": thicknesses,
                "geometry_sha256": _geometry_sha256(thicknesses),
                "input_path": str(paths["input"]),
                "input_sha256": expected_input_hash,
                "physics_definition_sha256": physics_hash,
                "physical_model_sha256": physical_hash,
                "discretization_sha256": resolved_discretization_hash,
                "source_sha": manifest["source_sha"],
                "result_path": str(
                    paths["run"] / "numerical_output/run_summary.json"
                ),
                "result_sha256": _sha256(result_path.read_bytes()),
                "status": "measured_candidate_pending_accuracy_gate",
                "gp_eligible": False,
                "labels": labels,
            }
        )

    template_hash = _sha256(template_bytes)
    planned_index = 5
    for sample_id_prefix, partition, geometries in (
        ("train", "training", groups["training"][4:]),
        ("development", "development", groups["development"]),
        ("blind", "blind_test", groups["blind_test"]),
    ):
        for index, row in enumerate(geometries, start=1):
            if partition == "training":
                sample_id = f"train_{planned_index:03d}"
                planned_index += 1
            else:
                sample_id = f"{sample_id_prefix}_{index:03d}"
            thicknesses = [float(value) for value in row]
            input_rel = Path("input/task44_surrogate_design_v1") / f"{sample_id}.dat"
            rendered = render_candidate_input(
                template_text, sample_id, thicknesses, partition
            )
            physical_hash, resolved_discretization_hash = _resolved_identity_for_bytes(
                rendered, sample_id
            )
            if resolved_discretization_hash != discretization_hash:
                raise ValueError("candidate resolved discrete signature changed")
            samples.append(
                {
                    "sample_id": sample_id,
                    "partition": partition,
                    "thicknesses_nm": thicknesses,
                    "geometry_sha256": _geometry_sha256(thicknesses),
                    "input_path": input_rel.as_posix(),
                    "input_sha256": _sha256(rendered),
                    "template_path": TEMPLATE_PATH.as_posix(),
                    "template_sha256": template_hash,
                    "physics_definition_sha256": physics_hash,
                    "physical_model_sha256": physical_hash,
                    "discretization_sha256": resolved_discretization_hash,
                    "source_sha": None,
                    "result_path": None,
                    "result_sha256": None,
                    "status": "planned_not_run",
                    "gp_eligible": False,
                }
            )

    if len({sample["sample_id"] for sample in samples}) != 40:
        raise ValueError("the frozen design must contain 40 unique sample IDs")
    serialized_groups = {
        name: [
            sample["thicknesses_nm"]
            for sample in samples
            if sample["partition"] == name
        ]
        for name in ("training", "development", "blind_test")
    }
    validate_disjoint_geometry_groups(serialized_groups)
    return {
        "schema": "task44.surrogate_sample_design.v1",
        "design_id": "task44_gp_20261031_seed440731_v1",
        "frozen_at_utc": "2026-10-31",
        "random_seed": DESIGN_SEED,
        "sampler": "independent six-dimensional stratified Latin hypercube per partition",
        "rng": "NumPy PCG64; partition seeds = base seed + 1/2/3",
        "parameter_names": [f"t{index}_nm" for index in range(1, 7)],
        "parameter_bounds_nm": [[0.5, 1.0]] * 6,
        "output_names": list(OUTPUT_NAMES),
        "partition_sizes": {name: len(rows) for name, rows in serialized_groups.items()},
        "blind_test_labels_read": False,
        "blind_test_policy": "do not attach labels or inspect results before model and selection policy freeze",
        "physics_definition_sha256": physics_hash,
        "discretization_sha256": discretization_hash,
        "template_path": TEMPLATE_PATH.as_posix(),
        "template_sha256": template_hash,
        "samples": samples,
    }



def build_design_v2(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Build the unchanged 440731 geometry partition for the qualified y12 model."""
    template_bytes = (root / TEMPLATE_PATH_V2).read_bytes()
    template_text = template_bytes.decode("utf-8")
    template_config = tomllib.loads(template_text)
    physics_hash = _canonical_sha256(_physics_definition(template_config))
    _, discretization_hash = _resolved_identity(root / TEMPLATE_PATH_V2)
    groups = initial_geometry_partitions(seed=DESIGN_SEED)
    validate_disjoint_geometry_groups(groups)

    previous_design_bytes = (root / DESIGN_PATH).read_bytes()
    previous_design = json.loads(previous_design_bytes)
    previous_samples = {
        sample["sample_id"]: sample
        for sample in previous_design["samples"]
    }
    if (
        previous_design.get("schema") != "task44.surrogate_sample_design.v1"
        or previous_design.get("design_id") != "task44_gp_20261031_seed440731_v1"
        or len(previous_samples) != 40
    ):
        raise ValueError("the frozen v1 design identity or sample count changed")

    anchor_input = root / TEMPLATE_PATH_V2
    anchor_run = root / ANCHOR_B_V2_RUN
    anchor_manifest = json.loads((anchor_run / "run_manifest.json").read_text())
    anchor_result_path = anchor_run / "numerical_output/run_summary.json"
    anchor_result_bytes = anchor_result_path.read_bytes()
    anchor_result = json.loads(anchor_result_bytes)
    anchor_input_bytes = anchor_input.read_bytes()
    anchor_thicknesses = [
        float(value)
        for value in tomllib.loads(anchor_input_bytes.decode("utf-8"))["geometry"][
            "grating_layer_thicknesses_nm"
        ]
    ]
    original_input_bytes = (anchor_run / "input_original.dat").read_bytes()
    anchor_input_hash = _sha256(anchor_input_bytes)
    if (
        original_input_bytes != anchor_input_bytes
        or anchor_manifest["input_sha256"] != anchor_input_hash
        or (anchor_run / "input_sha256.txt").read_text().strip() != anchor_input_hash
    ):
        raise ValueError("B y12 original input bytes differ from the frozen input")
    if (
        (anchor_run / "source_sha.txt").read_text().strip()
        != anchor_manifest["source_sha"]
    ):
        raise ValueError("B y12 source SHA file differs from its run manifest")
    if (
        (anchor_run / "physical_model_sha256.txt").read_text().strip()
        != anchor_manifest["physical_model_sha256"]
    ):
        raise ValueError("B y12 physical-model SHA file differs from its run manifest")
    original_resolved_path = anchor_run / "resolved_config.json"
    original_resolved_bytes = original_resolved_path.read_bytes()
    original_resolved_hash = _sha256(original_resolved_bytes)
    if original_resolved_hash != anchor_manifest["resolved_config_sha256"]:
        raise ValueError("B y12 resolved-config file differs from its run manifest")
    anchor_specification = load_and_resolve(anchor_input)
    current_resolved_config = anchor_specification.as_jsonable()
    current_physical_hash = anchor_specification.physical_model_sha256
    _, anchor_discretization_hash = _resolved_identity(anchor_input)
    if anchor_discretization_hash != discretization_hash:
        raise ValueError("B y12 discrete signature differs from the v2 template")
    expected_current_resolved = json.loads(original_resolved_bytes)
    expected_current_resolved["boundary"]["dtn_phase_gauge"] = "global_z"
    expected_current_resolved["provenance"]["physical_model_sha256"] = (
        current_physical_hash
    )
    if current_resolved_config != expected_current_resolved:
        raise ValueError(
            "B y12 resolved fields differ beyond global_z and its derived hash"
        )
    resolved_config_differences = [
        {
            "path": "boundary.dtn_phase_gauge",
            "original": "<missing>",
            "current": "global_z",
        },
        {
            "path": "provenance.physical_model_sha256",
            "original": anchor_manifest["physical_model_sha256"],
            "current": current_physical_hash,
        },
    ]
    rendered_b = render_candidate_input(
        template_text,
        "train_B",
        [
            float(value)
            for value in tomllib.loads(anchor_input_bytes.decode("utf-8"))["geometry"][
                "grating_layer_thicknesses_nm"
            ]
        ],
        "training",
        version="v2",
    )
    rendered_b_physics_hash, rendered_b_discretization_hash = (
        _resolved_identity_for_bytes(rendered_b, "train_B")
    )
    if (
        rendered_b_physics_hash != current_physical_hash
        or rendered_b_discretization_hash != anchor_discretization_hash
    ):
        raise ValueError("rendered v2 B does not match the current resolved anchor")

    runtime_config = anchor_result.get("config", {})
    runtime_layer_thicknesses = [
        float(layer["thickness_nm"])
        for layer in runtime_config.get("grating_layers", [])
    ]
    runtime_layer_names = [
        layer["name"] for layer in runtime_config.get("grating_layers", [])
    ]
    runtime_config_receipt = {
        "nedelec_degree": runtime_config.get("nedelec_degree"),
        "mesh_axis_cell_counts": runtime_config.get("mesh_axis_cell_counts"),
        "assembly_backend": runtime_config.get("stage4_full3d_assembly_backend"),
        "direct_solver_profile": runtime_config.get("petsc_direct_solver_profile"),
        "layer_names": runtime_layer_names,
        "layer_thicknesses_nm": runtime_layer_thicknesses,
        "dtn_phase_gauge": anchor_result.get("dtn_phase_gauge"),
        "propagating_dtn_modes": anchor_result.get("dtn_port_propagating_mode_count"),
        "top_dtn_modes": anchor_result.get("dtn_port_top_mode_count"),
        "bottom_dtn_modes": anchor_result.get("dtn_port_bottom_mode_count"),
    }
    expected_runtime_config = {
        "nedelec_degree": template_config["discretization"]["nedelec_degree"],
        "mesh_axis_cell_counts": template_config["discretization"][
            "mesh_axis_cell_counts"
        ],
        "assembly_backend": template_config["discretization"]["assembly_backend"],
        "direct_solver_profile": template_config["solver"]["direct_solver_profile"],
        "layer_names": template_config["materials"]["grating_layer_names"],
        "layer_thicknesses_nm": anchor_thicknesses,
        "dtn_phase_gauge": "global_z",
        "propagating_dtn_modes": 160,
        "top_dtn_modes": 80,
        "bottom_dtn_modes": 80,
    }
    if runtime_config_receipt != expected_runtime_config:
        raise ValueError("B y12 run-summary configuration differs from the v2 model")
    identity_bridge = {
        "original_source_sha": anchor_manifest["source_sha"],
        "original_input_sha256": anchor_input_hash,
        "original_physical_model_sha256": anchor_manifest["physical_model_sha256"],
        "original_resolved_config_sha256": original_resolved_hash,
        "original_result_sha256": _sha256(anchor_result_bytes),
        "current_resolved_physical_model_sha256": current_physical_hash,
        "current_discretization_sha256": anchor_discretization_hash,
        "current_resolved_config_sha256": _canonical_sha256(current_resolved_config),
        "resolved_config_field_differences": resolved_config_differences,
        "run_config_compatibility": runtime_config_receipt,
    }
    if _geometry_sha256(anchor_thicknesses) != _geometry_sha256(
        [float(value) for value in groups["training"][1]]
    ):
        raise ValueError("B y12 anchor is not the frozen train_B geometry")
    if not (
        anchor_result.get("official_result") is True
        and anchor_result.get("stage4_true_residual_gate_pass") is True
        and anchor_result.get("stage4_energy_closure_gate_pass") is True
        and anchor_result.get("dtn_phase_gauge") == "global_z"
        and anchor_result.get("dtn_port_mode_count") == 160
        and anchor_result.get("dtn_port_top_mode_count") == 80
        and anchor_result.get("dtn_port_bottom_mode_count") == 80
    ):
        raise ValueError("B y12 anchor did not pass the frozen numerical gates")
    labels = {name: float(anchor_result[name]) for name in OUTPUT_NAMES}
    if not all(np.isfinite(value) and 0.0 <= value <= 1.0 for value in labels.values()):
        raise ValueError("B y12 anchor has nonphysical surrogate outputs")
    if labels["R_total"] + labels["T_total"] > 1.0 + 1.0e-5:
        raise ValueError("B y12 anchor violates total power closure")
    if labels["R00_total"] > labels["R_total"] + 1.0e-8:
        raise ValueError("B y12 zero-order reflection exceeds total reflection")
    try:
        anchor_residual = float(anchor_result["linear_system_relative_residual"])
        anchor_absorption = float(anchor_result["A_volume_total"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "B y12 anchor is missing its residual or volume absorption"
        ) from error
    if not np.all(np.isfinite([anchor_residual, anchor_absorption])):
        raise ValueError("B y12 anchor residual or volume absorption is nonfinite")
    if anchor_residual > 1.0e-6:
        raise ValueError("B y12 linear-system relative residual exceeds 1e-6")
    anchor_energy_closure = (
        labels["R_total"] + labels["T_total"] + anchor_absorption - 1.0
    )
    if not np.isfinite(anchor_energy_closure) or abs(anchor_energy_closure) > 1.0e-5:
        raise ValueError("B y12 recomputed energy closure exceeds 1e-5")
    anchor_quality_receipt = {
        "official_result": True,
        "stage4_true_residual_gate_pass": True,
        "stage4_energy_closure_gate_pass": True,
        "linear_system_relative_residual": anchor_residual,
        "linear_system_relative_residual_limit": 1.0e-6,
        "A_volume_total": anchor_absorption,
        "recomputed_energy_closure": anchor_energy_closure,
        "recomputed_energy_closure_limit": 1.0e-5,
    }

    template_hash = _sha256(template_bytes)
    samples: list[dict[str, Any]] = []
    partitions = (
        ("training", groups["training"]),
        ("development", groups["development"]),
        ("blind_test", groups["blind_test"]),
    )
    for partition, geometries in partitions:
        for index, row in enumerate(geometries):
            thicknesses = [float(value) for value in row]
            if partition == "training" and index < len(ANCHOR_NAMES):
                sample_id = f"train_{ANCHOR_NAMES[index]}"
            elif partition == "training":
                sample_id = f"train_{index + 1:03d}"
            elif partition == "development":
                sample_id = f"development_{index + 1:03d}"
            else:
                sample_id = f"blind_{index + 1:03d}"
            geometry_hash = _geometry_sha256(thicknesses)
            if sample_id == "train_B":
                samples.append(
                    {
                        "sample_id": sample_id,
                        "partition": partition,
                        "thicknesses_nm": thicknesses,
                        "geometry_sha256": geometry_hash,
                        "input_path": TEMPLATE_PATH_V2.as_posix(),
                        "input_sha256": anchor_input_hash,
                        "physics_definition_sha256": physics_hash,
                        "physical_model_sha256": anchor_manifest[
                            "physical_model_sha256"
                        ],
                        "resolved_config_sha256": original_resolved_hash,
                        "current_resolved_physical_model_sha256": current_physical_hash,
                        "identity_bridge": identity_bridge,
                        "discretization_sha256": anchor_discretization_hash,
                        "source_sha": anchor_manifest["source_sha"],
                        "result_path": (
                            ANCHOR_B_V2_RUN / "numerical_output/run_summary.json"
                        ).as_posix(),
                        "result_sha256": _sha256(anchor_result_bytes),
                        "status": "measured_accuracy_qualified_anchor",
                        "gp_eligible": True,
                        "quality_receipt": anchor_quality_receipt,
                        "labels": labels,
                    }
                )
                continue

            input_path = Path("input/task44_surrogate_design_v2") / f"{sample_id}.dat"
            rendered = render_candidate_input(
                template_text,
                sample_id,
                thicknesses,
                partition,
                version="v2",
            )
            physical_hash, candidate_discretization_hash = (
                _resolved_identity_for_bytes(rendered, sample_id)
            )
            if candidate_discretization_hash != discretization_hash:
                raise ValueError(f"{sample_id} changed the frozen discrete signature")
            samples.append(
                {
                    "sample_id": sample_id,
                    "partition": partition,
                    "thicknesses_nm": thicknesses,
                    "geometry_sha256": geometry_hash,
                    "input_path": input_path.as_posix(),
                    "input_sha256": _sha256(rendered),
                    "template_path": TEMPLATE_PATH_V2.as_posix(),
                    "template_sha256": template_hash,
                    "physics_definition_sha256": physics_hash,
                    "physical_model_sha256": physical_hash,
                    "discretization_sha256": candidate_discretization_hash,
                    "source_sha": None,
                    "result_path": None,
                    "result_sha256": None,
                    "status": "planned_not_run",
                    "gp_eligible": False,
                }
            )

    if len(samples) != 40 or len({sample["sample_id"] for sample in samples}) != 40:
        raise ValueError("the frozen v2 design must contain 40 unique sample IDs")
    if set(previous_samples) != {sample["sample_id"] for sample in samples}:
        raise ValueError("the v2 sample IDs differ from the frozen v1 design")
    for sample in samples:
        old_sample = previous_samples[sample["sample_id"]]
        old_hex = [float(value).hex() for value in old_sample["thicknesses_nm"]]
        new_hex = [float(value).hex() for value in sample["thicknesses_nm"]]
        if (
            old_sample["partition"] != sample["partition"]
            or old_hex != new_hex
            or old_sample["geometry_sha256"] != sample["geometry_sha256"]
        ):
            raise ValueError(
                f"{sample['sample_id']} changed its frozen v1 partition or geometry"
            )
    serialized_groups = {
        name: [
            sample["thicknesses_nm"]
            for sample in samples
            if sample["partition"] == name
        ]
        for name in ("training", "development", "blind_test")
    }
    validate_disjoint_geometry_groups(serialized_groups)
    return {
        "schema": "task44.surrogate_sample_design.v2",
        "design_version": "v2",
        "design_id": "task44_gp_20261101_seed440731_p6_y12_air0p5_v2",
        "frozen_at_utc": "2026-11-01",
        "previous_design_id": "task44_gp_20261031_seed440731_v1",
        "previous_design_sha256": _sha256(previous_design_bytes),
        "random_seed": DESIGN_SEED,
        "sampler": "independent six-dimensional stratified Latin hypercube per partition",
        "rng": "NumPy PCG64; partition seeds = base seed + 1/2/3",
        "parameter_names": [f"t{index}_nm" for index in range(1, 7)],
        "parameter_bounds_nm": [[0.5, 1.0]] * 6,
        "output_names": list(OUTPUT_NAMES),
        "partition_sizes": {name: len(rows) for name, rows in serialized_groups.items()},
        "blind_test_labels_read": False,
        "blind_test_policy": "do not attach labels or inspect results before model and selection policy freeze",
        "physics_definition_sha256": physics_hash,
        "discretization_sha256": discretization_hash,
        "template_path": TEMPLATE_PATH_V2.as_posix(),
        "template_sha256": template_hash,
        "frozen_numerical_model": {
            "finite_element_degree": template_config["discretization"][
                "nedelec_degree"
            ],
            "mesh_axis_cell_counts": template_config["discretization"][
                "mesh_axis_cell_counts"
            ],
            "top_air_gap_nm": 0.5,
            "dtn_phase_gauge": "global_z",
            "propagating_dtn_modes": 160,
            "top_dtn_modes": 80,
            "bottom_dtn_modes": 80,
            "assembly_backend": template_config["discretization"]["assembly_backend"],
            "method": template_config["method"]["kind"],
            "direct_solver_profile": template_config["solver"]["direct_solver_profile"],
            "mpi_size": 1,
            "thread_limit": 1,
        },
        "sample_reuse": {
            "sample_id": "train_B",
            "source_sha": anchor_manifest["source_sha"],
            "input_sha256": anchor_input_hash,
            "physical_model_sha256": anchor_manifest["physical_model_sha256"],
            "resolved_config_sha256": original_resolved_hash,
            "current_resolved_physical_model_sha256": current_physical_hash,
            "current_discretization_sha256": anchor_discretization_hash,
            "result_sha256": _sha256(anchor_result_bytes),
            "identity_bridge": identity_bridge,
            "result_path": (
                ANCHOR_B_V2_RUN / "numerical_output/run_summary.json"
            ).as_posix(),
            "quality_receipt": anchor_quality_receipt,
        },
        "samples": samples,
    }

def materialize_sample(design: dict[str, Any], sample_id: str, root: Path) -> Path:
    sample = next(
        (item for item in design["samples"] if item["sample_id"] == sample_id), None
    )
    if sample is None:
        raise ValueError(f"unknown sample_id: {sample_id}")
    if sample["partition"] == "training" and sample["status"].startswith("measured"):
        raise ValueError("measured A-D inputs already exist and cannot be regenerated")
    template_path = root / sample["template_path"]
    template_bytes = template_path.read_bytes()
    if _sha256(template_bytes) != sample["template_sha256"]:
        raise ValueError("frozen input template hash changed")
    rendered = render_candidate_input(
        template_bytes.decode("utf-8"),
        sample["sample_id"],
        sample["thicknesses_nm"],
        sample["partition"],
        version=design.get("design_version", "v1"),
    )
    if _sha256(rendered) != sample["input_sha256"]:
        raise ValueError("regenerated input does not match frozen input hash")
    path = root / sample["input_path"]
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rendered)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=("v1", "v2"), default="v1")
    parser.add_argument("--design", type=Path)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--materialize", metavar="SAMPLE_ID")
    args = parser.parse_args()
    default_design_path = DESIGN_PATH if args.version == "v1" else DESIGN_PATH_V2
    design_path = REPOSITORY_ROOT / (args.design or default_design_path)
    build = build_design if args.version == "v1" else build_design_v2
    selected_modes = sum((args.freeze, args.verify, args.materialize is not None))
    if selected_modes != 1:
        parser.error("choose exactly one of --freeze, --verify, or --materialize SAMPLE_ID")
    if args.freeze:
        if design_path.exists():
            raise FileExistsError(
                f"frozen design exists; refusing to overwrite {design_path}"
            )
        design = build()
        design_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            design, indent=2, sort_keys=True, allow_nan=False
        ) + "\n"
        design_path.write_text(payload, encoding="utf-8")
        print(f"wrote {design_path.relative_to(REPOSITORY_ROOT)}")
    elif args.verify:
        design = json.loads(design_path.read_text(encoding="utf-8"))
        expected = build()
        if design != expected:
            raise ValueError("frozen sample design differs from its deterministic rebuild")
        print(
            f"verified {design_path.relative_to(REPOSITORY_ROOT)} "
            f"({len(design['samples'])} samples)"
        )
    else:
        design = json.loads(design_path.read_text(encoding="utf-8"))
        print(
            materialize_sample(design, args.materialize, REPOSITORY_ROOT).relative_to(
                REPOSITORY_ROOT
            )
        )


if __name__ == "__main__":
    main()
