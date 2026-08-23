"""Thin Task040 Level-A runner over the reviewed PETSc transmission carrier."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.run_task037b_hybrid_iterative import collective_heap_cleanup
from benchmarks.task039_v3_7_orchestration import (
    _load_v5_blr_reference_spool_remapped,
    _load_v5_fixed_budget_spool_shards,
    _v9_frozen_holdout_identity,
)
from benchmarks.task039_v3_side_oracle import _build_research_explicit_side_components
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.runners.task039_hybrid_iterative import make_task039_hybrid_iterative_profile
from src.solvers.hybrid_local_dtn_action import assemble_hybrid_local_dtn_action_system
from src.solvers.hybrid_layer_block import (
    run_v1_1_right_preconditioned_fgmres_batch,
)
from src.solvers.hybrid_side_impedance import (
    TASK040_LEVEL_A_SOURCE_LABELS,
    assemble_reduced_artificial_interface_tangential_mass,
    audit_artificial_z_interface_support,
    audit_petsc_level_a_one_apply,
    build_level_a_cell_recovery_group_rows,
    build_level_a_oracle,
)


TASK040_LEVEL_A_METHOD = "task040_level_a_bare_f_transmission"
TASK040_LEVEL_A_SCHEMA = "task040.level_a.bare_f_transmission.v1"
TASK040_LEVEL_A_PROFILE_ID = "task040.level_a.h4.bottom.v1"
TASK040_LEVEL_A_HARD_STOP_BYTES = 45 * 2**30
TASK040_LEVEL_A_TIMEOUT_SECONDS = 21600
TASK040_LEVEL_A_MPI_SIZE = 8
TASK040_LEVEL_A_THREADS = 1
TASK040_LEVEL_A_SEQUENCE = (0, 1, 2, 2, 1, 0)
TASK040_LEVEL_A_BETA_AUTHORITY = (
    "src.solvers.dtn_port_3d::_zero_order_local_robin_forms"
)
TASK040_V1_1_SCALAR_KRYLOV_FLAG = "--v1-1-scalar-krylov"
TASK040_V1_1_METHOD = "task040_v1_1_scalar_krylov"
TASK040_V1_1_SCHEMA = "task040.v1_1.scalar_krylov.v1"
TASK040_V1_1_PROFILE_ID = "task040.v1_1.h4.bottom.scalar_krylov.v1"

__all__ = (
    "TASK040_LEVEL_A_METHOD",
    "TASK040_LEVEL_A_SCHEMA",
    "TASK040_LEVEL_A_PROFILE_ID",
    "TASK040_LEVEL_A_HARD_STOP_BYTES",
    "TASK040_LEVEL_A_SEQUENCE",
    "TASK040_V1_1_SCALAR_KRYLOV_FLAG",
    "TASK040_V1_1_METHOD",
    "TASK040_V1_1_SCHEMA",
    "TASK040_V1_1_PROFILE_ID",
    "build_task040_level_a_plan",
    "level_a_bottom_beta",
    "run_task040_level_a",
)


def level_a_bottom_beta(cfg: Any) -> complex:
    """Use the frozen bottom Robin beta authority, with no parameter scan."""

    return complex(cfg.k0) * complex(cfg.substrate_index)


def build_task040_level_a_plan(
    *,
    input_path: str | Path,
    exact_spool_root: str | Path,
    run_directory: str | Path,
    source_sha: str,
    scalar_krylov: bool = False,
) -> dict[str, Any]:
    """Build a dry-run contract without creating a result directory."""

    source_sha = str(source_sha)
    if len(source_sha) != 40 or any(
        character not in "0123456789abcdef" for character in source_sha
    ):
        raise ValueError("Task040 source_sha must be a 40-character lowercase hex SHA")
    run_directory = Path(run_directory).resolve()
    if run_directory.exists():
        raise ValueError(f"Task040 run directory already exists: {run_directory}")
    plan = {
        "schema": TASK040_LEVEL_A_SCHEMA,
        "method": TASK040_LEVEL_A_METHOD,
        "profile": TASK040_LEVEL_A_PROFILE_ID,
        "source_sha": source_sha,
        "input": str(Path(input_path).resolve()),
        "exact_spool_root": str(Path(exact_spool_root).resolve()),
        "run_directory": str(run_directory),
        "mpi_size": TASK040_LEVEL_A_MPI_SIZE,
        "threads": TASK040_LEVEL_A_THREADS,
        "timeout_seconds": TASK040_LEVEL_A_TIMEOUT_SECONDS,
        "absolute_terminate_memory_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
        "swap_limit_bytes": 0,
        "oracle_only": True,
        "scalable_candidate": False,
        "forbidden": [
            "global_direct_factor",
            "qep",
            "outer_ksp",
            "recovery",
            "top",
            "full_hybrid",
            "response_packet",
        ],
    }
    if scalar_krylov:
        plan.update(
            {
                "schema": TASK040_V1_1_SCHEMA,
                "method": TASK040_V1_1_METHOD,
                "profile": TASK040_V1_1_PROFILE_ID,
                "scalar_krylov": True,
                "research_only": True,
            }
        )
    return plan


def _worker_current_resource(comm: MPI.Intracomm) -> dict[str, Any]:
    authority = resource_authority_sample(os.getpid(), include_smaps=False)
    process_tree = authority["process_tree"]
    job_cgroup = authority["job_cgroup"]
    has_cgroup = bool(job_cgroup["dedicated_job_cgroup"])
    local_cgroup_memory = int(job_cgroup["memory_current_bytes"] or 0)
    local_cgroup_swap = int(job_cgroup["swap_current_bytes"] or 0)
    process_rss_sum = int(comm.allreduce(int(process_tree["rss_bytes"]), op=MPI.SUM))
    process_swap_sum = int(comm.allreduce(int(process_tree["swap_bytes"]), op=MPI.SUM))
    has_cgroup_any = bool(comm.allreduce(has_cgroup, op=MPI.LOR))
    cgroup_memory_max = int(comm.allreduce(local_cgroup_memory, op=MPI.MAX))
    cgroup_swap_max = int(comm.allreduce(local_cgroup_swap, op=MPI.MAX))
    rss_bytes = max(process_rss_sum, cgroup_memory_max if has_cgroup_any else 0)
    swap_bytes = max(process_swap_sum, cgroup_swap_max if has_cgroup_any else 0)
    readable = bool(
        process_tree["all_status_readable"]
        and (
            not has_cgroup
            or (
                job_cgroup["memory_current_bytes"] is not None
                and job_cgroup["swap_current_bytes"] is not None
            )
        )
    )
    readable = bool(comm.allreduce(readable, op=MPI.LAND))
    return {
        "rss_bytes": rss_bytes,
        "swap_bytes": swap_bytes,
        "process_tree_rss_sum_bytes": process_rss_sum,
        "process_tree_swap_sum_bytes": process_swap_sum,
        "dedicated_cgroup_memory_current_max_bytes": (
            cgroup_memory_max if has_cgroup_any else None
        ),
        "dedicated_cgroup_swap_current_max_bytes": (
            cgroup_swap_max if has_cgroup_any else None
        ),
        "authority_semantics": (
            "max(sum(all-rank process-tree RSS), max(dedicated cgroup memory.current)); "
            "swap uses the same sum/max rule"
        ),
        "all_status_readable": readable,
        "source": "worker_process_tree_and_dedicated_cgroup",
        "pass": bool(
            readable and rss_bytes < TASK040_LEVEL_A_HARD_STOP_BYTES and swap_bytes == 0
        ),
    }


def _emit(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    stage: str,
    **detail: Any,
) -> None:
    if callback is not None:
        callback(stage, detail)


def _file_marker_callback(
    stages_path: str | Path | None,
    markers_path: str | Path | None,
    *,
    enabled: bool,
) -> Callable[[str, Mapping[str, Any]], None] | None:
    if not enabled or stages_path is None or markers_path is None:
        return None
    stages_path = Path(stages_path)
    markers_path = Path(markers_path)
    stages_path.parent.mkdir(parents=True, exist_ok=True)
    markers_path.parent.mkdir(parents=True, exist_ok=True)

    def record(stage: str, detail: Mapping[str, Any]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        status = "running" if stage.endswith("_begin") else "complete"
        stage_record = {
            "timestamp_utc": timestamp,
            "stage": stage,
            "status": status,
            **dict(detail),
        }
        marker_record = {
            "timestamp_utc": timestamp,
            "stage": stage,
            "detail": dict(detail),
        }
        with stages_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(stage_record, sort_keys=True) + "\n")
        with markers_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(marker_record, sort_keys=True) + "\n")

    return record


def _destroy_explicit_components(components: Any) -> bool:
    destroyed = True
    for name in ("H", "D", "C", "F"):
        matrix = getattr(components, name, None)
        if matrix is not None:
            matrix.destroy()
            setattr(components, name, None)
        destroyed = destroyed and getattr(components, name, None) is None
    return bool(destroyed)


def run_task040_level_a(
    cfg: Any,
    profile: Any,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    exact_spool_root: str | Path,
    source_sha: str,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    side_system_builder: Callable[..., Any] | None = None,
    scalar_krylov: bool = False,
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the six-source Level-A audit; all numerical work stays in src."""

    system = None
    components = None
    action = None
    owner = None
    source_vectors: dict[str, PETSc.Vec] = {}
    supports: list[dict[str, Any]] = []
    masses: list[Any] = []
    result: dict[str, Any] | None = None
    cleanup: dict[str, Any] = {}
    _emit(marker_callback, "construction_begin", method=TASK040_LEVEL_A_METHOD)
    try:
        if side_system_builder is None:
            system = assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=profile.bottom_interface_nm,
                top_interface_z_nm=profile.top_interface_nm,
                comm=comm,
                log=None,
            )
        else:
            system = side_system_builder(
                side="bottom", cfg=cfg, profile=profile, comm=comm
            )
        system_inventory = dict(system.inventory)
        system_inventory_ok = (
            system_inventory.get("direct_factor_count") == 0
            and system_inventory.get("global_A_materialized") is False
        )
        if not bool(comm.allreduce(system_inventory_ok, op=MPI.LAND)):
            raise RuntimeError(
                "Task040 system inventory is not factor-free/action-only: "
                f"{system_inventory!r}"
            )
        _emit(
            marker_callback,
            "system_ready",
            matrix_free=bool(system_inventory.get("matrix_free")),
            direct_factor_count=system_inventory.get("direct_factor_count"),
            global_A_materialized=system_inventory.get("global_A_materialized"),
        )
        components = _build_research_explicit_side_components(system)
        bare_f = components.F
        z_values = system.local_mesh.z_values
        interface_z = (float(z_values[2]), float(z_values[4]))
        for index, interface in enumerate(interface_z):
            _emit(marker_callback, "interface_mass_begin", interface=index, z=interface)
            support = audit_artificial_z_interface_support(
                system.V,
                system.static_condensation.condensed,
                interface,
            )
            supports.append(support)
            masses.append(
                assemble_reduced_artificial_interface_tangential_mass(
                    system.V,
                    system.static_condensation.condensed,
                    support,
                    bare_operator=bare_f,
                )
            )
            _emit(
                marker_callback,
                "interface_mass_ready",
                interface=index,
                support=masses[-1].audit,
            )

        group_rows, group_audit = build_level_a_cell_recovery_group_rows(
            system, bare_f, supports
        )
        beta = level_a_bottom_beta(cfg)
        _emit(
            marker_callback,
            "projection_begin",
            beta=[beta.real, beta.imag],
            q=[(-1j * beta).real, (-1j * beta).imag],
        )
        action, owner, oracle_diagnostics = build_level_a_oracle(
            bare_f=bare_f,
            group_rows=group_rows,
            interface_masses=masses,
            beta=beta,
            group_audit=group_audit,
        )
        _emit(
            marker_callback,
            "projection_ready",
            group_audit=group_audit,
            restriction_prolongation_error=oracle_diagnostics[
                "restriction_prolongation_error"
            ],
        )

        packet_identity, manifest_sha, catalog = _v9_frozen_holdout_identity(
            exact_spool_root, comm
        )
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=packet_identity,
            manifest_sha256=manifest_sha,
        )
        for label in TASK040_LEVEL_A_SOURCE_LABELS:
            template = bare_f.createVecLeft()
            try:
                source_vectors[label] = _load_v5_blr_reference_spool_remapped(
                    spool[label]["rhs"], template
                )
            finally:
                template.destroy()
        _emit(
            marker_callback,
            "source_ready",
            labels=list(TASK040_LEVEL_A_SOURCE_LABELS),
            source_identity={
                label: spool[label]["rhs"]["probe_metadata"]
                for label in TASK040_LEVEL_A_SOURCE_LABELS
            },
            rhs_vectors_loaded=len(TASK040_LEVEL_A_SOURCE_LABELS),
            exact_outputs_used=False,
            exact_output_vectors_loaded=0,
            exact_output_metadata_hash_validation_only=True,
        )
        required_factor_counts = {
            "cross_section_factor_count_ready": 3,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        }
        if any(
            oracle_diagnostics.get(key) != value
            for key, value in required_factor_counts.items()
        ):
            raise RuntimeError(
                "Task040 factor inventory failed: "
                f"{required_factor_counts!r} vs {oracle_diagnostics!r}"
            )
        factor_inventory = {
            "observed": True,
            **required_factor_counts,
            "factor_count_ready": oracle_diagnostics[
                "cross_section_factor_count_ready"
            ],
            "system_direct_factor_count_observed": system_inventory[
                "direct_factor_count"
            ],
            "system_global_A_materialized_observed": system_inventory[
                "global_A_materialized"
            ],
            "oracle_only": True,
            "scalable_candidate": False,
        }
        action_result = audit_petsc_level_a_one_apply(
            action,
            bare_f,
            source_vectors,
            factor_inventory,
            collect_scalar_contractions=scalar_krylov,
        )
        scalar_screen = None
        if scalar_krylov:
            scalar_labels = tuple(TASK040_LEVEL_A_SOURCE_LABELS[1:])
            scalar_screen = run_v1_1_right_preconditioned_fgmres_batch(
                bare_f,
                {label: source_vectors[label] for label in scalar_labels},
                action,
                labels=scalar_labels,
                resource_callback=resource_callback,
                checkpoint_callback=lambda row: _emit(
                    marker_callback, "v1_1_fgmres_checkpoint", **dict(row)
                ),
            )
            _emit(
                marker_callback,
                "v1_1_scalar_screen_complete",
                conditional_32_authorized=scalar_screen["conditional_32_authorized"],
                ksp_setup_count=scalar_screen["ksp_setup_count"],
                ksp_destroy_count=scalar_screen["ksp_destroy_count"],
                right_pc_apply_count=scalar_screen["right_pc_apply_count"],
            )
        _emit(
            marker_callback,
            "level_a_audit_complete",
            source_rho={
                report["label"]: report["true_residual_relative"]
                for report in action_result["reports"]
            },
            worst_mandatory_rho=action_result["gate"]["worst_mandatory_rho"],
            preferred_rho_pass=action_result["gate"]["preferred_rho_pass"],
            gate_pass=action_result["gate"]["pass"],
            factor_inventory=factor_inventory,
        )
        result = {
            "schema": TASK040_V1_1_SCHEMA if scalar_krylov else TASK040_LEVEL_A_SCHEMA,
            "method": TASK040_V1_1_METHOD if scalar_krylov else TASK040_LEVEL_A_METHOD,
            "profile": TASK040_V1_1_PROFILE_ID
            if scalar_krylov
            else TASK040_LEVEL_A_PROFILE_ID,
            "source_sha": str(source_sha),
            "beta": {
                "formula": "cfg.k0 * complex(cfg.substrate_index)",
                "value": [beta.real, beta.imag],
                "q": [(-1j * beta).real, (-1j * beta).imag],
                "authority": TASK040_LEVEL_A_BETA_AUTHORITY,
            },
            "sequence": list(TASK040_LEVEL_A_SEQUENCE),
            "input_identity": catalog,
            "packet_identity": packet_identity,
            "spool_manifest_sha256": manifest_sha,
            "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS),
            "exact_output_vectors_loaded": 0,
            "exact_output_metadata_hash_validation_only": True,
            "interface_masses": [mass.audit for mass in masses],
            "oracle": oracle_diagnostics,
            "factor_inventory": factor_inventory,
            "action": action_result,
            "source_loading": {
                "labels": list(TASK040_LEVEL_A_SOURCE_LABELS),
                "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS),
                "exact_output_vectors_loaded": 0,
                "exact_output_metadata_hash_validation_only": True,
            },
            "pde_solve": "not_run",
            "top": "not_run",
            "scalable_candidate": False,
        }
        if scalar_krylov:
            result["scalar_krylov"] = True
            result["scalar_screen"] = scalar_screen
    finally:
        for vector in source_vectors.values():
            vector.destroy()
        if owner is not None:
            ready_owner = owner.diagnostics
            owner.destroy()
            cleanup["factor_owner"] = {
                "ready": ready_owner,
                "after": owner.diagnostics,
            }
        elif action is not None:
            action.destroy()
        for mass in masses:
            mass.destroy()
        if components is not None:
            cleanup["components_destroyed"] = _destroy_explicit_components(components)
        if system is not None:
            system.destroy()
        cleanup["collective_heap"] = collective_heap_cleanup(comm)
        _emit(marker_callback, "cleanup", **cleanup)
        if result is not None:
            result["cleanup"] = cleanup
    if result is None:
        raise RuntimeError("Task040 Level-A did not produce a result")
    return result


def _load_cfg(input_path: str | Path) -> tuple[Any, Any]:
    spec = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(spec.as_jsonable())
    profile = make_task039_hybrid_iterative_profile(480, 8, mesh_target_nm=4.0)
    return cfg, profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--input", required=True)
    parser.add_argument("--exact-spool-root", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(TASK040_V1_1_SCALAR_KRYLOV_FLAG, action="store_true")
    parser.add_argument("--memory-stages")
    parser.add_argument("--memory-markers")
    args = parser.parse_args(argv)
    plan = build_task040_level_a_plan(
        input_path=args.input,
        exact_spool_root=args.exact_spool_root,
        run_directory=args.run_directory,
        source_sha=args.source_sha,
        scalar_krylov=args.v1_1_scalar_krylov,
    )
    if args.dry_run:
        if MPI.COMM_WORLD.rank == 0:
            print(json.dumps(plan, sort_keys=True))
        return 0
    cfg, profile = _load_cfg(args.input)
    marker_callback = _file_marker_callback(
        args.memory_stages,
        args.memory_markers,
        enabled=MPI.COMM_WORLD.rank == 0,
    )
    result = run_task040_level_a(
        cfg,
        profile,
        exact_spool_root=args.exact_spool_root,
        source_sha=args.source_sha,
        marker_callback=marker_callback,
        scalar_krylov=args.v1_1_scalar_krylov,
        resource_callback=(
            lambda: (
                _worker_current_resource(MPI.COMM_WORLD)
                if args.v1_1_scalar_krylov
                else None
            )
        ),
    )
    if MPI.COMM_WORLD.rank == 0:
        run_directory = Path(args.run_directory)
        run_directory.mkdir(parents=True, exist_ok=True)
        summary_path = run_directory / "run_summary.json"
        if summary_path.exists():
            raise FileExistsError(f"Task040 run summary already exists: {summary_path}")
        summary_path.write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
