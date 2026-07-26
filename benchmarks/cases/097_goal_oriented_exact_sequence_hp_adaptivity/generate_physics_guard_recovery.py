#!/usr/bin/env python3
"""Build the Task035d regional diagnostic and physics-guard plan authority."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

import dolfinx
import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adaptivity.high_order_same_error import (  # noqa: E402
    ProbeSet,
    build_task034_fixed_probe_sets,
    sample_owned_vtu_shards,
)
from src.adaptivity.legacy_seeded_variable_p import (  # noqa: E402
    load_legacy_multigoal_cell_seed,
)
from src.adaptivity.physics_guard_variable_p import (  # noqa: E402
    build_sidewall_z0_guard_plan,
)
from src.adaptivity.variable_p_degree_plan import (  # noqa: E402
    variable_p_cell_degree_plan_payload,
)
from src.common.config_3d import target_stage4_config  # noqa: E402
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d  # noqa: E402


CASE = (
    ROOT
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
)
RECORDS = CASE / "records"
T30_RECORD = RECORDS / "t30_h10_mpi8_controlled_negative_v1.json"
T30_RECORD_SHA256 = (
    "ac0266578fe38dd9934cfcfb840d817f8c4fbc617694a068462f7d505392acc1"
)
LEGACY_SEED = RECORDS / "legacy_multigoal_seed_v1.json"
DIAGNOSTIC = RECORDS / "t30_regional_probe_error_localization_v1.json"
PLAN = RECORDS / "sidewall_z0_guard_h10_cell_degree_plan_v1.json"
SOURCE_PATHS = (
    "src/adaptivity/physics_guard_variable_p.py",
    "src/test/test_195_task035d_physics_guard_selector.py",
    (
        "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
        "generate_physics_guard_recovery.py"
    ),
)
EXPECTED = {
    "counts": {"p4": 72, "p5": 168, "p6": 12},
    "cycle1_counts": {"p4": 0, "p5": 240, "p6": 12},
    "active_fe_dofs": 89_870,
    "active_trace_rows": 36_374,
    "independent_trace_rows": 30_984,
    "solve_rows": 31_064,
    "row_breakdown": {
        "edge": 4_902,
        "face": 31_472,
        "cell_interior": 53_496,
    },
    "plan_content_sha256": (
        "8172bcc9ca2e2fcbc23a8ca15524f80b7658ccf0c19d24da4dcff1ed32fee062"
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _json_safe(dict(payload)),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _resolve(path: str) -> Path:
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else ROOT / candidate
    return candidate.resolve()


def _load_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    if _sha256(path) != expected_sha256:
        raise RuntimeError(f"SHA-256 mismatch: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root is not an object: {path}")
    return payload


def _shard_paths(
    rows: Any,
    *,
    label: str,
) -> tuple[list[Path], list[dict[str, Any]]]:
    if not isinstance(rows, list) or len(rows) != 8:
        raise RuntimeError(f"{label} must contain exactly eight shards")
    paths: list[Path] = []
    authority: list[dict[str, Any]] = []
    for expected_rank, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("rank") != expected_rank:
            raise RuntimeError(f"{label} rank order is invalid")
        path = _resolve(str(row.get("path")))
        expected_sha = str(row.get("sha256"))
        observed_sha = _sha256(path)
        if observed_sha != expected_sha:
            raise RuntimeError(f"{label} rank {expected_rank} SHA mismatch")
        paths.append(path)
        authority.append(
            {
                "rank": expected_rank,
                "path": str(path.relative_to(ROOT)),
                "sha256": observed_sha,
            }
        )
    return paths, authority


def regional_probe_metrics(
    probes: ProbeSet,
    *,
    global_p5: np.ndarray,
    global_p6: np.ndarray,
    candidate: np.ndarray,
) -> dict[str, Any]:
    """Localize a frozen field comparison by existing probe-region labels."""

    values = {
        "global_p5": np.asarray(global_p5, dtype=np.complex128),
        "global_p6": np.asarray(global_p6, dtype=np.complex128),
        "candidate": np.asarray(candidate, dtype=np.complex128),
    }
    expected_shape = (len(probes.points), 3)
    if any(value.shape != expected_shape for value in values.values()):
        raise ValueError("regional field arrays have an unexpected shape")
    labels = np.asarray(probes.region_labels, dtype=object)
    weights = np.asarray(probes.weights, dtype=np.float64)
    if labels.shape != (len(probes.points),) or weights.shape != labels.shape:
        raise ValueError("regional probe labels or weights are inconsistent")

    regions: dict[str, Any] = {}
    for label in sorted(set(probes.region_labels)):
        mask = labels == label
        regional_weights = weights[mask, None]
        reference = values["global_p6"][mask]
        p5_delta = values["global_p5"][mask] - reference
        candidate_delta = values["candidate"][mask] - reference
        reference_energy = float(
            np.sum(regional_weights * np.abs(reference) ** 2)
        )
        if not math.isfinite(reference_energy) or reference_energy <= 0.0:
            raise ValueError(f"region {label} has invalid reference energy")
        p5_relative = math.sqrt(
            float(np.sum(regional_weights * np.abs(p5_delta) ** 2))
            / reference_energy
        )
        candidate_relative = math.sqrt(
            float(np.sum(regional_weights * np.abs(candidate_delta) ** 2))
            / reference_energy
        )
        p5_maximum = float(np.max(np.linalg.norm(p5_delta, axis=1)))
        candidate_maximum = float(
            np.max(np.linalg.norm(candidate_delta, axis=1))
        )
        regions[label] = {
            "probe_count": int(np.count_nonzero(mask)),
            "reference_weighted_energy": reference_energy,
            "global_p5_vs_p6_weighted_relative_l2": p5_relative,
            "t30_vs_p6_weighted_relative_l2": candidate_relative,
            "t30_to_p5_band_relative_l2_ratio": (
                candidate_relative / max(p5_relative, 1.0e-12)
            ),
            "global_p5_vs_p6_max_pointwise_absolute_error": p5_maximum,
            "t30_vs_p6_max_pointwise_absolute_error": candidate_maximum,
            "t30_to_p5_band_maximum_ratio": (
                candidate_maximum / max(p5_maximum, 1.0e-10)
            ),
        }
    return {
        "probe_set": probes.name,
        "probe_sha256": probes.sha256,
        "probe_count": len(probes.points),
        "probe_definition": probes.definition,
        "regions": regions,
    }


def _normalized_channel_failures(t30: Mapping[str, Any]) -> dict[str, Any]:
    channel = t30.get("channel_comparison")
    if not isinstance(channel, dict):
        raise RuntimeError("T30 channel comparison is missing")
    rows = channel.get("channels")
    if not isinstance(rows, list) or len(rows) != 12:
        raise RuntimeError("T30 frozen channel inventory is not 12")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        power_error = float(
            row["candidate_vs_reference_power_absolute_error"]
        )
        power_tolerance = float(row["unchanged_v0_power_tolerance"])
        amplitude_error = float(
            row["candidate_vs_reference_amplitude_absolute_error"]
        )
        amplitude_tolerance = float(
            row["unchanged_v0_complex_amplitude_tolerance"]
        )
        normalized.append(
            {
                "side": row["side"],
                "m": int(row["m"]),
                "n": int(row["n"]),
                "polarization": row["polarization"],
                "power_normalized_error": (
                    power_error / max(power_tolerance, 1.0e-300)
                ),
                "complex_amplitude_normalized_error": (
                    amplitude_error / max(amplitude_tolerance, 1.0e-300)
                ),
                "power_pass": row["power_pass"],
                "complex_amplitude_pass": row[
                    "complex_amplitude_pass"
                ],
            }
        )
    return {
        "channel_count": len(normalized),
        "power_pass_count": sum(row["power_pass"] for row in normalized),
        "complex_amplitude_pass_count": sum(
            row["complex_amplitude_pass"] for row in normalized
        ),
        "minimum_power_normalized_error": min(
            row["power_normalized_error"] for row in normalized
        ),
        "maximum_power_normalized_error": max(
            row["power_normalized_error"] for row in normalized
        ),
        "minimum_complex_amplitude_normalized_error": min(
            row["complex_amplitude_normalized_error"]
            for row in normalized
        ),
        "maximum_complex_amplitude_normalized_error": max(
            row["complex_amplitude_normalized_error"]
            for row in normalized
        ),
        "channels": normalized,
    }


def generate_diagnostic(output: Path = DIAGNOSTIC) -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("regional probe diagnostic is serial-only")
    t30 = _load_json(T30_RECORD, T30_RECORD_SHA256)
    controls = t30.get("control_field_artifacts")
    raw = t30.get("raw_artifacts")
    if not isinstance(controls, dict) or not isinstance(raw, dict):
        raise RuntimeError("T30 field authorities are missing")
    p5_paths, p5_authority = _shard_paths(
        controls.get("global_p5_control"),
        label="global p5",
    )
    p6_paths, p6_authority = _shard_paths(
        controls.get("global_p6_reference"),
        label="global p6",
    )
    t30_paths, t30_authority = _shard_paths(
        raw.get("field_shards"),
        label="T30",
    )

    selections: dict[str, Any] = {}
    sample_authority: dict[str, Any] = {}
    for name, probes in build_task034_fixed_probe_sets().items():
        sampled = {
            "global_p5": sample_owned_vtu_shards(p5_paths, probes),
            "global_p6": sample_owned_vtu_shards(p6_paths, probes),
            "t30": sample_owned_vtu_shards(t30_paths, probes),
        }
        selections[name] = regional_probe_metrics(
            probes,
            global_p5=sampled["global_p5"]["values"],
            global_p6=sampled["global_p6"]["values"],
            candidate=sampled["t30"]["values"],
        )
        sample_authority[name] = {
            label: value["authority"]
            for label, value in sampled.items()
        }
    payload = {
        "schema_version": (
            "task035d.t30-regional-probe-error-localization.v1"
        ),
        "status": "diagnostic_pass_no_accuracy_credit",
        "pass": True,
        "classification": "diagnostic_only",
        "diagnostic_only": True,
        "actual_channel_dwr": False,
        "actual_adjoint_sensitivity": False,
        "formal_accuracy_credit": False,
        "geometry": "Task034 fixed rectangular block grating",
        "source": {
            "commit_sha": _git_head(),
            "t30_compact_record": {
                "path": str(T30_RECORD.relative_to(ROOT)),
                "sha256": T30_RECORD_SHA256,
            },
        },
        "field_shard_authority": {
            "global_p5": p5_authority,
            "global_p6": p6_authority,
            "t30": t30_authority,
        },
        "sample_authority": sample_authority,
        "regional_field_error": selections,
        "channel_failure_width": _normalized_channel_failures(t30),
        "decision_use": {
            "accepted_use": (
                "conservative recovery proposal and p5 guard placement"
            ),
            "forbidden_use": (
                "must not be described as a channel DWR, an adjoint "
                "derivative, or formal accuracy evidence"
            ),
            "candidate": "sidewall_z0_guard_v1",
            "p6_recovery": (
                "lower two grating slabs at z=0..20 nm, protected by p5"
            ),
            "p4_reduction": (
                "only remote outer homogeneous-air strips at z=0..120 nm"
            ),
        },
        "fresh_12_channel_pde_required": True,
        "ordinary_default_changed": False,
    }
    _write(output, payload)
    return payload


def _source_identity() -> dict[str, Any]:
    return {
        "commit_sha": _git_head(),
        "file_sha256": {
            path: _sha256(ROOT / path) for path in SOURCE_PATHS
        },
        "ordinary_default_changed": False,
    }


def _environment() -> dict[str, Any]:
    return {
        "dolfinx_version": str(dolfinx.__version__),
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "mpi_size": int(MPI.COMM_WORLD.size),
    }


def _authority_path(mpi_size: int) -> Path:
    return RECORDS / f"physics_guard_plan_authority_mpi{mpi_size}_v1.json"


def generate_plan_authority() -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    if comm.size not in {1, 2, 8}:
        raise RuntimeError("physics-guard authority requires MPI1/2/8")
    diagnostic = json.loads(DIAGNOSTIC.read_text(encoding="utf-8"))
    diagnostic_sha = _sha256(DIAGNOSTIC)
    if (
        diagnostic.get("schema_version")
        != "task035d.t30-regional-probe-error-localization.v1"
        or diagnostic.get("pass") is not True
        or diagnostic.get("diagnostic_only") is not True
        or diagnostic.get("actual_channel_dwr") is not False
        or diagnostic.get("formal_accuracy_credit") is not False
    ):
        raise RuntimeError("regional diagnostic is not valid input")

    cfg = replace(
        target_stage4_config(degree=6, h_nm=10.0),
        case_name=f"task035d_physics_guard_mpi{comm.size}",
        unique_output=False,
    )
    with tempfile.TemporaryDirectory(
        prefix=f"task035d-physics-guard-mpi{comm.size}-",
        dir="/tmp",
    ) as directory:
        mesh_data = build_airbox_mesh_3d(
            cfg,
            Path(directory) / "mesh",
        )
        proposal = build_sidewall_z0_guard_plan(mesh_data.mesh)
        audit = proposal.audit
        observed = {
            "counts": dict(audit["cell_degree_counts"]),
            "cycle1_counts": dict(audit["cycle1_cell_degree_counts"]),
            "active_fe_dofs": int(
                audit["actual_conforming_active_fe_dofs"]
            ),
            "active_trace_rows": int(
                audit["active_trace_rows_before_periodic_elimination"]
            ),
            "independent_trace_rows": int(
                audit["periodic_independent_trace_rows"]
            ),
            "solve_rows": int(audit["predicted_direct_solve_rows"]),
            "row_breakdown": dict(audit["active_rows_by_dimension"]),
            "plan_content_sha256": str(audit["cycle2_plan_sha256"]),
        }
        if observed != EXPECTED:
            raise RuntimeError(
                f"physics-guard plan differs from frozen expectation: {observed}"
            )
        seed = load_legacy_multigoal_cell_seed(
            mesh_data.mesh,
            LEGACY_SEED,
        )
        p5_or_higher = np.asarray(
            proposal.p5_canonical_cell_ids
            + proposal.p6_canonical_cell_ids,
            dtype=np.int64,
        )
        p6_ids = np.asarray(
            proposal.p6_canonical_cell_ids,
            dtype=np.int64,
        )
        score_context = {
            "legacy_seed_is_diagnostic_only": True,
            "p5_or_higher_legacy_score_mass": float(
                np.sum(seed.score_by_canonical_cell_id[p5_or_higher])
            ),
            "p6_legacy_score_mass": float(
                np.sum(seed.score_by_canonical_cell_id[p6_ids])
            ),
        }
        if comm.size == 1:
            payload = variable_p_cell_degree_plan_payload(
                mesh_data.mesh,
                proposal.cycle2.cell_degree_by_box,
                provenance={
                    "task": "Task035d",
                    "case_id": (
                        "097_goal_oriented_exact_sequence_hp_adaptivity"
                    ),
                    "selector": "sidewall_z0_guard_v1",
                    "regional_diagnostic": {
                        "path": str(DIAGNOSTIC.relative_to(ROOT)),
                        "sha256": diagnostic_sha,
                    },
                    "t30_compact_record_sha256": T30_RECORD_SHA256,
                    "selector_audit": dict(audit),
                    "legacy_score_context": score_context,
                    "formal_accuracy_credit": False,
                    "fresh_12_channel_pde_required": True,
                    "ordinary_default_changed": False,
                },
            )
            _write(PLAN, payload)
        comm.Barrier()
        if not PLAN.exists():
            raise RuntimeError("MPI1 must create the physics-guard plan first")
        plan_payload = json.loads(PLAN.read_text(encoding="utf-8"))
        if (
            plan_payload.get("cell_degree_plan_sha256")
            != EXPECTED["plan_content_sha256"]
        ):
            raise RuntimeError("physics-guard plan file identity differs")

    record = {
        "schema_version": "task035d.physics-guard-plan-authority.v1",
        "status": f"physics_guard_plan_authority_mpi{comm.size}_pass",
        "pass": True,
        "source": _source_identity(),
        "environment": _environment(),
        "geometry": "Task034 fixed rectangular block grating",
        "h_nm": 10.0,
        "degree_container": 6,
        "actual_axis_counts": [6, 3, 14],
        "cell_count": 252,
        "candidate": "sidewall_z0_guard_v1",
        "regional_diagnostic": {
            "path": str(DIAGNOSTIC.relative_to(ROOT)),
            "sha256": diagnostic_sha,
            "diagnostic_only": True,
            "actual_channel_dwr": False,
            "formal_accuracy_credit": False,
        },
        "plan": {
            "path": str(PLAN.relative_to(ROOT)),
            "file_sha256": _sha256(PLAN),
            "cell_degree_plan_sha256": EXPECTED[
                "plan_content_sha256"
            ],
            "cell_degree_counts": EXPECTED["counts"],
            "cycle1_cell_degree_counts": EXPECTED["cycle1_counts"],
            "actual_conforming_active_fe_dofs": EXPECTED[
                "active_fe_dofs"
            ],
            "active_trace_rows_before_periodic_elimination": EXPECTED[
                "active_trace_rows"
            ],
            "periodic_independent_trace_rows": EXPECTED[
                "independent_trace_rows"
            ],
            "predicted_direct_solve_rows": EXPECTED["solve_rows"],
            "active_rows_by_dimension": EXPECTED["row_breakdown"],
            "maximum_adjacent_cell_degree_jump": 1,
            "active_fe_dof_gate_pass": True,
        },
        "heavy_pde_started": False,
        "formal_accuracy_credit": False,
        "fresh_12_channel_pde_required": True,
        "ordinary_default_changed": False,
    }
    if comm.rank == 0:
        _write(_authority_path(comm.size), record)
    comm.Barrier()
    return record


def check() -> None:
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("authority check is serial-only")
    diagnostic = json.loads(DIAGNOSTIC.read_text(encoding="utf-8"))
    if diagnostic.get("pass") is not True:
        raise RuntimeError("regional diagnostic does not pass")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if (
        plan.get("cell_degree_plan_sha256")
        != EXPECTED["plan_content_sha256"]
    ):
        raise RuntimeError("physics-guard plan content differs")
    authorities = [
        json.loads(
            _authority_path(size).read_text(encoding="utf-8")
        )
        for size in (1, 2, 8)
    ]
    identities = [
        {
            "candidate": record.get("candidate"),
            "geometry": record.get("geometry"),
            "plan": record.get("plan"),
            "diagnostic": record.get("regional_diagnostic"),
        }
        for record in authorities
    ]
    if len(
        {
            json.dumps(identity, sort_keys=True)
            for identity in identities
        }
    ) != 1:
        raise RuntimeError("MPI physics-guard authorities disagree")
    for size, record in zip((1, 2, 8), authorities, strict=True):
        if (
            record.get("status")
            != f"physics_guard_plan_authority_mpi{size}_pass"
            or record.get("pass") is not True
            or (record.get("environment") or {}).get("mpi_size") != size
            or record.get("heavy_pde_started") is not False
            or record.get("formal_accuracy_credit") is not False
        ):
            raise RuntimeError(
                f"MPI{size} physics-guard authority is invalid"
            )
    print("Task035d physics-guard plan authorities: PASS")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("diagnostic", "generate", "check"),
        required=True,
    )
    parser.add_argument("--output", type=Path, default=DIAGNOSTIC)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.mode == "diagnostic":
        output = (
            args.output
            if args.output.is_absolute()
            else ROOT / args.output
        )
        generate_diagnostic(output)
    elif args.mode == "generate":
        generate_plan_authority()
    else:
        check()


if __name__ == "__main__":
    main()
