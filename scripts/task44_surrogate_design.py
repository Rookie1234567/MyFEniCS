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
DESIGN_SEED = 440731
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
    template: str, sample_id: str, thicknesses_nm: list[float], partition: str
) -> bytes:
    if not re.fullmatch(r"[a-z0-9_]+", sample_id):
        raise ValueError(f"unsafe sample_id: {sample_id}")
    if len(thicknesses_nm) != 6 or not all(np.isfinite(thicknesses_nm)):
        raise ValueError("each candidate requires six finite thicknesses")
    height = float(sum(thicknesses_nm))
    top = height + 0.5
    text = template
    text = _replace_line(text, "run_id", json.dumps(f"task44_{sample_id}_v1"))
    text = _replace_line(
        text, "comparison_group", json.dumps(f"task44_gp_{partition}_v1")
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
    parser.add_argument("--design", type=Path, default=DESIGN_PATH)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--materialize", metavar="SAMPLE_ID")
    args = parser.parse_args()
    design_path = REPOSITORY_ROOT / args.design
    selected_modes = sum((args.freeze, args.verify, args.materialize is not None))
    if selected_modes != 1:
        parser.error("choose exactly one of --freeze, --verify, or --materialize SAMPLE_ID")
    if args.freeze:
        if design_path.exists():
            raise FileExistsError(
                f"frozen design exists; refusing to overwrite {design_path}"
            )
        design = build_design()
        design_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            design, indent=2, sort_keys=True, allow_nan=False
        ) + "\n"
        design_path.write_text(payload, encoding="utf-8")
        print(f"wrote {design_path.relative_to(REPOSITORY_ROOT)}")
    elif args.verify:
        design = json.loads(design_path.read_text(encoding="utf-8"))
        expected = build_design()
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
