"""Thin Task040 Level-A runner over the reviewed PETSc transmission carrier."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from dolfinx import fem

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.run_task037b_hybrid_iterative import collective_heap_cleanup
from benchmarks.task039_v3_7_orchestration import (
    _load_v5_blr_reference_spool_remapped,
    _load_v5_fixed_budget_spool_shards,
    _v9_frozen_holdout_identity,
)
from benchmarks.task039_v4_selected_mode_packet import (
    stream_task039_v4_selected_mode_columns,
)
from benchmarks.task039_v3_side_oracle import _build_research_explicit_side_components
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.common.modes_3d import outgoing_port_modes_3d
from src.coupling.hybrid_internal_modes import (
    _ReusableInterfaceLifter,
    _trace_from_streamed_local_values,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.hybrid_interface_basis import (
    build_artificial_gamma_column,
    build_group_basis_columns,
    build_lower_fourier_trace_columns,
    build_mass_dual_from_active_vec,
    canonical_external_mode_metadata_sha256,
    collect_streamed_trace_basis,
)
from src.solvers.hybrid_interface_packet import (
    PacketGroup,
    finalize_manifest,
    load_packet_shard,
    redistribute_packet_group_rows,
    write_group_shard,
)
from src.solvers.hybrid_interface_packet_dolfinx import (
    CanonicalOwnerLocalBasis,
    build_dolfinx_plane_gamma_layout,
    build_gamma_canonical_layout,
    audit_owner_local_basis_round_trip,
    canonicalize_owner_local_basis_in_place,
    reconstruct_owner_local_basis,
)
from src.solvers.hybrid_interface_schur import (
    build_petsc_interface_schur_oracle,
    build_distributed_petrov_action,
)
from src.solvers.hybrid_interface_run_b import (
    build_v1_3_projected_transmission,
    build_v2_packet_projected_transmission,
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
TASK040_V1_2_INTERFACE_SCHUR_FLAG = "--v1-2-interface-schur"
TASK040_V1_2_METHOD = "task040_v1_2_interface_schur"
TASK040_V1_2_SCHEMA = "task040.v1_2.interface_schur.v1"
TASK040_V1_2_PROFILE_ID = "task040.v1_2.h4.run_b.v1"
TASK040_V1_2_PROBE_MANIFEST = (
    "benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/"
    "task040_v1_2_probe_manifest_v1.json"
)
TASK040_V1_2_PROBE_MANIFEST_SHA256 = (
    "7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad"
)
TASK040_V1_2_INPUT_SHA256 = (
    "4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811"
)
TASK040_V1_2_PHYSICAL_MODEL_SHA256 = (
    "8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c"
)
TASK040_V1_2_SELECTED_MANIFEST_SHA256 = (
    "2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067"
)
TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256 = (
    "a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384"
)
TASK040_V1_2_LOWER_RESOLVED_MODE_METADATA_SHA256 = (
    "dde523dc62c73f7bd50953958fde42d42d0cfd5756c16329b16915e13c4742da"
)
TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG = "--v2-interface-packet-producer"
TASK040_V2_INTERFACE_PACKET_METHOD = "task040_v2_interface_packet_producer"
TASK040_V2_INTERFACE_PACKET_SCHEMA = "task040.v2.interface_packet_producer.v1"
TASK040_V2_INTERFACE_PACKET_PROFILE_ID = "task040.v2.a1.interface_packet_producer.v1"
TASK040_V2_INTERFACE_PACKET_PREFERRED_BYTES = 45 * 2**30
TASK040_V2_INTERFACE_PACKET_HARD_STOP_BYTES = 55 * 2**30
TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG = "--v2-interface-packet-consumer"
TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD = "task040_v2_interface_packet_consumer"
TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA = "task040.v2.interface_packet_consumer.v1"
TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID = (
    "task040.v2.b2.interface_packet_consumer.v1"
)
TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256 = (
    "19de50f3cdb32766bf6f13fc55c9ac498b21a9a00ddc261768d7d55b7c9da8b0"
)

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
    "TASK040_V1_2_INTERFACE_SCHUR_FLAG",
    "TASK040_V1_2_METHOD",
    "TASK040_V1_2_SCHEMA",
    "TASK040_V1_2_PROFILE_ID",
    "TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG",
    "TASK040_V2_INTERFACE_PACKET_METHOD",
    "TASK040_V2_INTERFACE_PACKET_SCHEMA",
    "TASK040_V2_INTERFACE_PACKET_PROFILE_ID",
    "TASK040_V2_INTERFACE_PACKET_PREFERRED_BYTES",
    "TASK040_V2_INTERFACE_PACKET_HARD_STOP_BYTES",
    "TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG",
    "TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD",
    "TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA",
    "TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID",
    "TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256",
    "TASK040_V1_2_PROBE_MANIFEST",
    "TASK040_V1_2_PROBE_MANIFEST_SHA256",
    "TASK040_V1_2_INPUT_SHA256",
    "TASK040_V1_2_PHYSICAL_MODEL_SHA256",
    "TASK040_V1_2_SELECTED_MANIFEST_SHA256",
    "TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256",
    "TASK040_V1_2_LOWER_RESOLVED_MODE_METADATA_SHA256",
    "build_task040_level_a_plan",
    "level_a_bottom_beta",
    "run_task040_level_a",
)


def level_a_bottom_beta(cfg: Any) -> complex:
    """Use the frozen bottom Robin beta authority, with no parameter scan."""

    return complex(cfg.k0) * complex(cfg.substrate_index)


def _v1_2_identity_pass(
    *,
    identity_observed: Mapping[str, Any],
    frozen_identity: Mapping[str, Any],
    manifest: Mapping[str, Any],
    exact_identities: Mapping[str, Any],
) -> bool:
    """Check the frozen Run-B identity before constructing V1-3 factors."""

    return bool(
        identity_observed["input_sha256"] == frozen_identity["input_sha256"]
        and identity_observed["physical_model_sha256"]
        == frozen_identity["physical_model_sha256"]
        and identity_observed["selected_identity_physical_sha256"]
        == frozen_identity["physical_model_sha256"]
        and identity_observed["selected_manifest_sha256"]
        == frozen_identity["selected_manifest_sha256"]
        and identity_observed["selected_identity_sha256"]
        == frozen_identity["selected_identity_sha256"]
        and identity_observed["selected_selection_sha256"]
        == frozen_identity["selected_selection_sha256"]
        and identity_observed["resolved_config_sha256"]
        == frozen_identity["exact_spool_resolved_config_sha256"]
        and identity_observed["spool_catalog_sha256"]
        == TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256
        and identity_observed["upper_mode_key_sha256"]
        == manifest["upper_selected_packet_basis"]["positive_mode_keys_sha256"]
        and identity_observed["upper_beta_sha256"]
        == manifest["upper_selected_packet_basis"]["positive_beta_sha256"]
        and identity_observed["lower_mode_key_sha256"]
        == manifest["lower_fourier_floquet_basis"]["canonical_key_list_sha256"]
        and identity_observed["lower_resolved_mode_metadata_sha256"]
        == TASK040_V1_2_LOWER_RESOLVED_MODE_METADATA_SHA256
        and identity_observed["lower_resolved_mode_metadata_sha256"]
        != identity_observed["lower_legacy_beta_metadata_sha256"]
        and identity_observed["exact_output_identity_sha256"] == exact_identities
    )


def build_task040_level_a_plan(
    *,
    input_path: str | Path,
    exact_spool_root: str | Path,
    run_directory: str | Path,
    source_sha: str,
    scalar_krylov: bool = False,
    interface_schur: bool = False,
    packet_producer: bool = False,
    packet_consumer: bool = False,
    interface_packet_root: str | Path | None = None,
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
    if (
        sum(
            bool(value)
            for value in (
                scalar_krylov,
                interface_schur,
                packet_producer,
                packet_consumer,
            )
        )
        > 1
    ):
        raise ValueError("Task040 research routes are mutually exclusive")
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
    if interface_schur:
        plan.update(
            {
                "schema": TASK040_V1_2_SCHEMA,
                "method": TASK040_V1_2_METHOD,
                "profile": TASK040_V1_2_PROFILE_ID,
                "interface_schur": True,
                "research_only": True,
                "probe_manifest": TASK040_V1_2_PROBE_MANIFEST,
                "probe_manifest_sha256": TASK040_V1_2_PROBE_MANIFEST_SHA256,
                "expected_input_sha256": TASK040_V1_2_INPUT_SHA256,
                "expected_physical_model_sha256": (TASK040_V1_2_PHYSICAL_MODEL_SHA256),
                "expected_selected_manifest_sha256": (
                    TASK040_V1_2_SELECTED_MANIFEST_SHA256
                ),
                "expected_exact_spool_catalog_sha256": (
                    TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256
                ),
                # Keep these frozen aliases for the established dry-run
                # contract; runtime observations are recorded separately.
                "selected_manifest_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
                "exact_spool_catalog_sha256": (TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256),
                "v1_3_conditional": True,
            }
        )
    if packet_producer:
        plan.update(
            {
                "schema": TASK040_V2_INTERFACE_PACKET_SCHEMA,
                "method": TASK040_V2_INTERFACE_PACKET_METHOD,
                "profile": TASK040_V2_INTERFACE_PACKET_PROFILE_ID,
                "packet_producer": True,
                "research_only": True,
                "pde_solve": "not_run",
                "qep_calls": 0,
                "v1_3_conditional": False,
                "absolute_terminate_memory_bytes": (
                    TASK040_V2_INTERFACE_PACKET_HARD_STOP_BYTES
                ),
                "preferred_memory_bytes": TASK040_V2_INTERFACE_PACKET_PREFERRED_BYTES,
                "packet_root": str(run_directory / "interface_packet"),
                "forbidden": [
                    "v1_3_projected_transmission",
                    "fgmres",
                    "qep",
                    "pde_solve",
                    "global_direct_factor",
                    "full_side_factor",
                ],
                "packet_complete_required": True,
            }
        )
    if packet_consumer:
        if interface_packet_root is None:
            raise ValueError("V2 packet consumer requires interface_packet_root")
        plan.update(
            {
                "schema": TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA,
                "method": TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD,
                "profile": TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID,
                "packet_consumer": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "pde_solve": "not_run",
                "qep_calls": 0,
                "absolute_terminate_memory_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "interface_packet_root": str(Path(interface_packet_root).resolve()),
                "packet_manifest_sha256": TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
                "forbidden": [
                    "qep",
                    "exact_interface_oracle",
                    "outer_ksp",
                    "recovery",
                    "top",
                    "full_hybrid",
                    "response_packet",
                    "exact_output_vector_load",
                    "global_direct_factor",
                    "full_side_factor",
                    "pde_solve",
                ],
                "packet_complete_required": True,
            }
        )
    return plan


def _worker_current_resource(
    comm: MPI.Intracomm,
    hard_limit_bytes: int = TASK040_LEVEL_A_HARD_STOP_BYTES,
) -> dict[str, Any]:
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
            readable and rss_bytes < int(hard_limit_bytes) and swap_bytes == 0
        ),
        "hard_limit_bytes": int(hard_limit_bytes),
    }


def _emit(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    stage: str,
    **detail: Any,
) -> None:
    if callback is not None:
        callback(stage, detail)


def _v2_collective_stage_error(
    comm: MPI.Intracomm,
    stage: str,
    local_error: str | None,
) -> None:
    """Propagate one V2 packet-stage error before another collective."""

    errors = comm.allgather(local_error)
    first = next(
        ((rank, error) for rank, error in enumerate(errors) if error is not None),
        None,
    )
    if first is not None:
        rank, error = first
        raise ValueError(
            f"V2 packet stage {stage} failed on first failing rank {rank}: {error}"
        )


def _v2_group_marker(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    stage: str,
    *,
    group: int,
    layout: Any,
    span_size: int | None,
    comm: MPI.Intracomm,
    started: float | None = None,
    **detail: Any,
) -> None:
    """Emit one V2 group marker with a cross-rank maximum elapsed time."""

    marker_detail = {
        "group": int(group),
        "local_rows": int(layout.audit["local_row_count"]),
        "local_blocks": int(len(layout.blocks)),
        "span_size": None if span_size is None else int(span_size),
    }
    if started is not None:
        marker_detail["cross_rank_max_elapsed_seconds"] = float(
            comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
        )
    _emit(callback, stage, **marker_detail, **detail)


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


def _v1_2_complex(value: Any) -> complex:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    return complex(value)


def _v1_2_mode_key(mode: Any) -> dict[str, Any]:
    return {
        "m": int(mode.m),
        "n": int(mode.n),
        "polarization": str(mode.polarization),
        "side": str(mode.side),
    }


def _v1_2_load_manifest() -> tuple[Path, dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    path = root / TASK040_V1_2_PROBE_MANIFEST
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != TASK040_V1_2_PROBE_MANIFEST_SHA256:
        raise ValueError("Task040 V1-2 probe manifest hash mismatch")
    return path, json.loads(payload)


def _v1_2_lower_mode_count(resolved_modes: Mapping[str, Any]) -> int:
    """Read the resolved inventory's per-side bottom mode count."""

    return int(resolved_modes["counts"]["per_side"]["bottom"])


def _v1_2_validate_spool_identity(
    *, selected_manifest_sha256: str, catalog: Mapping[str, Any]
) -> str:
    """Validate selected-spool manifest and catalog identities separately."""

    if selected_manifest_sha256 != TASK040_V1_2_SELECTED_MANIFEST_SHA256:
        raise ValueError("V1-2 selected spool manifest is not frozen")
    catalog_sha256 = str(catalog["catalog_sha256"])
    if catalog_sha256 != TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256:
        raise ValueError("V1-2 exact spool catalog is not frozen")
    return catalog_sha256


def _v1_2_local_interface_rows(
    condensed: Any,
    support: Mapping[str, Any],
    gamma_rows_local: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    constraints = condensed.trace_constraints
    owned_original = {int(value) for value in constraints.owned_active_original_dofs}
    original_to_active = {
        int(key): int(value) for key, value in constraints.original_to_active.items()
    }
    by_active: dict[int, int] = {}
    for original in support["raw_support"]:
        original = int(original)
        if original in owned_original:
            if original not in original_to_active:
                raise ValueError("V1-2 artificial support lacks active identity")
            active = original_to_active[original]
            if active in by_active:
                raise ValueError("V1-2 local support has duplicate active rows")
            by_active[active] = original
    gamma = np.asarray(gamma_rows_local, dtype=PETSc.IntType)
    if set(by_active) != {int(value) for value in gamma}:
        raise ValueError("V1-2 local raw/active support does not match Gamma rows")
    plane_original = np.asarray(
        [by_active[int(value)] for value in gamma], dtype=PETSc.IntType
    )
    return plane_original, gamma.copy()


def _v1_2_build_lower_basis(
    *,
    cfg: Any,
    system: Any,
    spaces: Any,
    condensed: Any,
    support: Mapping[str, Any],
    gamma_rows_local: np.ndarray,
    interface_z: float,
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    modes = [mode for mode in outgoing_port_modes_3d(cfg) if mode.side == "bottom"]
    expected_keys = tuple(authority["keys"])
    expected_metadata = tuple(authority["modes"])
    if len(modes) != int(authority["count"]):
        raise ValueError("V1-2 lower mode count differs from resolved authority")
    mode_by_token = {
        json.dumps(_v1_2_mode_key(mode), sort_keys=True, separators=(",", ":")): mode
        for mode in modes
    }
    if len(mode_by_token) != len(modes):
        raise ValueError("V1-2 lower mode keys are duplicated")
    plane_original, gamma = _v1_2_local_interface_rows(
        condensed, support, gamma_rows_local
    )
    lifter = _ReusableInterfaceLifter(
        system,
        target_space=system.V,
        interface_z_nm=interface_z,
        plane_cell_side="lower",
    )
    xy = np.asarray(spaces.transverse.mesh.geometry.x, dtype=np.float64)[:, :2]

    def trace_to_gamma(_values: np.ndarray, info: Mapping[str, Any]) -> np.ndarray:
        token = json.dumps(
            {
                "m": int(info["m"]),
                "n": int(info["n"]),
                "polarization": str(info["polarization"]),
                "side": str(info["side"]),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        mode = mode_by_token.get(token)
        if mode is None:
            raise ValueError("V1-2 lower Fourier mode is absent from authority")
        trace = fem.Function(spaces.transverse)
        e_vector = np.asarray(mode.e_vector[:2], dtype=np.complex128)
        alpha = complex(mode.alpha)
        transverse_beta = complex(mode.k_vector[2])

        def values(points: np.ndarray) -> np.ndarray:
            phase = np.exp(
                1j
                * (
                    alpha * points[0]
                    + complex(mode.gamma) * points[1]
                    + transverse_beta * interface_z
                )
            )
            return np.vstack((phase * e_vector[0], phase * e_vector[1]))

        try:
            trace.interpolate(values)
            trace.x.scatter_forward()
            return build_artificial_gamma_column(
                trace,
                system=system,
                condensed=condensed,
                interface_z_nm=interface_z,
                plane_cell_side="lower",
                plane_original_dofs=plane_original,
                gamma_rows_local=gamma,
                lifter=lifter,
            )
        finally:
            del trace

    result = build_lower_fourier_trace_columns(
        modes,
        xy,
        interface_z,
        expected_count=int(authority["count"]),
        expected_keys=expected_keys,
        expected_key_sha256=str(authority["canonical_key_list_sha256"]),
        expected_metadata=expected_metadata,
        expected_metadata_sha256=canonical_external_mode_metadata_sha256(
            expected_metadata
        ),
        frozen_manifest_beta_metadata_sha256=str(authority["beta_metadata_sha256"]),
        trace_to_gamma=trace_to_gamma,
    )
    result["left"] = np.asarray(result["values"], dtype=np.complex128).copy()
    result["resolved_mode_metadata_sha256"] = canonical_external_mode_metadata_sha256(
        expected_metadata
    )
    result["legacy_manifest_beta_metadata_sha256"] = str(
        authority["beta_metadata_sha256"]
    )
    return result


def _v1_2_build_upper_basis(
    *,
    system: Any,
    spaces: Any,
    condensed: Any,
    support: Mapping[str, Any],
    gamma_rows_local: np.ndarray,
    interface_z: float,
    selected_manifest: Path,
    selected_identity: Mapping[str, Any],
    selected_payload: Mapping[str, Any],
    expected_mode_key_sha256: str,
    expected_beta_sha256: str,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    selection = selected_payload["selection"]["positive"]
    expected_keys = tuple(selection["mode_keys"])
    expected_betas = tuple(_v1_2_complex(value) for value in selection["beta"])
    plane_original, gamma = _v1_2_local_interface_rows(
        condensed, support, gamma_rows_local
    )
    lifter = _ReusableInterfaceLifter(
        system,
        target_space=system.V,
        interface_z_nm=interface_z,
        plane_cell_side="upper",
    )

    def trace_from_values(
        values: np.ndarray, info: Mapping[str, Any], role: str
    ) -> np.ndarray:
        trace = _trace_from_streamed_local_values(
            values,
            spaces,
            info["ownership_range"],
            name=f"task040_v1_2_upper_{role}",
        )
        try:
            return build_artificial_gamma_column(
                trace,
                system=system,
                condensed=condensed,
                interface_z_nm=interface_z,
                plane_cell_side="upper",
                plane_original_dofs=plane_original,
                gamma_rows_local=gamma,
                lifter=lifter,
            )
        finally:
            del trace

    def stream(callback: Callable[..., None]) -> Mapping[str, Any]:
        return stream_task039_v4_selected_mode_columns(
            selected_manifest,
            identity=selected_identity,
            expected_manifest_sha256=TASK040_V1_2_SELECTED_MANIFEST_SHA256,
            branch="positive",
            indices=tuple(range(int(selected_payload["mode_count"]))),
            callback=callback,
            comm=comm,
        )

    result = collect_streamed_trace_basis(
        stream,
        indices=tuple(range(int(selected_payload["mode_count"]))),
        trace_from_values=trace_from_values,
        expected_mode_keys=expected_keys,
        expected_mode_key_sha256=str(expected_mode_key_sha256),
        expected_betas=expected_betas,
        expected_selected_packet_beta_sha256=str(expected_beta_sha256),
    )
    return result


def _v1_2_scalar_gamma_apply(
    *,
    condensed: Any,
    group: int,
    gamma_rows: np.ndarray,
    masses: Sequence[Any],
    beta: complex,
) -> Callable[[PETSc.Vec, PETSc.Vec], None]:
    mass_indices = (0,) if int(group) == 0 else (1,) if int(group) == 2 else (0, 1)
    q = -1j * complex(beta)

    def apply(source: PETSc.Vec, target: PETSc.Vec) -> None:
        active = condensed.create_active_vector()
        image = active.duplicate()
        try:
            first, last = map(int, active.getOwnershipRange())
            rows = np.asarray(gamma_rows, dtype=np.int64)
            if len(rows) and (int(rows.min()) < first or int(rows.max()) >= last):
                raise ValueError("V1-2 Gamma rows do not match active ownership")
            active.set(0.0)
            if len(rows):
                active.array[rows - first] = source.array
            active.assemble()
            target.set(0.0)
            for index in mass_indices:
                image.set(0.0)
                masses[index].matrix.mult(active, image)
                if len(rows):
                    target.array[:] += q * image.array[rows - first]
            target.assemble()
        finally:
            image.destroy()
            active.destroy()

    return apply


def _v1_2_restrict_exact_probes(
    *,
    spool: Mapping[str, Any],
    labels: Sequence[str],
    expected_identities: Mapping[str, str],
    template_matrix: PETSc.Mat,
    lower_rows: np.ndarray,
    upper_rows: np.ndarray,
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, str]]:
    result: dict[str, dict[str, np.ndarray]] = {}
    observed_output_ids: dict[str, str] = {}
    for label in labels:
        shards = spool[label]["exact_output"]["shards"]
        observed_identities = []
        for shard in shards:
            identity = shard.get("source_identity", {}).get("vector_identity", {})
            observed = identity.get("global_sha256")
            if not isinstance(observed, str):
                raise ValueError(
                    f"V1-2 exact-output vector identity is missing for {label}"
                )
            observed_identities.append(observed)
        if (
            not observed_identities
            or len(set(observed_identities)) != 1
            or observed_identities[0] != expected_identities[label]
        ):
            raise ValueError(
                f"V1-2 exact-output identity mismatch across ranks for {label}"
            )
        observed_output_ids[label] = observed_identities[0]
        template = template_matrix.createVecLeft()
        vector = None
        try:
            vector = _load_v5_blr_reference_spool_remapped(
                spool[label]["exact_output"], template
            )
            first, last = map(int, vector.getOwnershipRange())
            for rows in (lower_rows, upper_rows):
                if len(rows) and (int(rows.min()) < first or int(rows.max()) >= last):
                    raise ValueError("V1-2 exact-output rows are not locally owned")
            result[label] = {
                "lower": np.asarray(
                    vector.array[lower_rows - first], dtype=np.complex128
                ).copy(),
                "upper": np.asarray(
                    vector.array[upper_rows - first], dtype=np.complex128
                ).copy(),
            }
        finally:
            template.destroy()
            if vector is not None:
                vector.destroy()
    return result, observed_output_ids


def _v1_2_group_probe_values(
    group_rows: np.ndarray,
    lower_rows: np.ndarray,
    lower_values: np.ndarray,
    upper_rows: np.ndarray,
    upper_values: np.ndarray,
) -> np.ndarray:
    lower_map = {int(row): value for row, value in zip(lower_rows, lower_values)}
    upper_map = {int(row): value for row, value in zip(upper_rows, upper_values)}
    values = np.empty(len(group_rows), dtype=np.complex128)
    for index, row in enumerate(group_rows):
        if int(row) in lower_map:
            values[index] = lower_map[int(row)]
        elif int(row) in upper_map:
            values[index] = upper_map[int(row)]
        else:
            raise ValueError("V1-2 group Gamma row is not in either interface")
    return values


def _v1_2_relative_error(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.duplicate()
    try:
        left.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), right)
        return float(difference.norm()) / max(float(right.norm()), 1.0e-30)
    finally:
        difference.destroy()


def _v1_2_probe_actions(
    *,
    labels: Sequence[str],
    traces: Mapping[str, Mapping[str, np.ndarray]],
    oracle: Any,
    petrov_actions: Sequence[Any],
    scalar_apply: Sequence[Callable[[PETSc.Vec, PETSc.Vec], None]],
    gamma_rows: Sequence[np.ndarray],
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for label in labels:
        for group in range(3):
            source = oracle.create_group_gamma_vector(group)
            scalar_target = source.duplicate()
            exact_target = source.duplicate()
            projected_target = source.duplicate()
            try:
                values = _v1_2_group_probe_values(
                    gamma_rows[group],
                    gamma_rows[0],
                    traces[label]["lower"],
                    gamma_rows[2],
                    traces[label]["upper"],
                )
                source.array[:] = values
                source.assemble()
                scalar_apply[group](source, scalar_target)
                oracle.apply_directed_neighbor(group, source, exact_target)
                petrov_actions[group].apply(source, projected_target)
                reports.append(
                    {
                        "label": label,
                        "kind": "physical",
                        "group": group,
                        "scalar_exact_relative": _v1_2_relative_error(
                            scalar_target, exact_target
                        ),
                        "projected_exact_relative": _v1_2_relative_error(
                            projected_target, exact_target
                        ),
                        "scalar_norm": float(scalar_target.norm()),
                        "exact_norm": float(exact_target.norm()),
                        "projected_norm": float(projected_target.norm()),
                        "contractions": _v1_2_vec_contractions(
                            source, scalar_target, exact_target, projected_target
                        ),
                    }
                )
            finally:
                projected_target.destroy()
                exact_target.destroy()
                scalar_target.destroy()
                source.destroy()
    return reports


def _v1_2_complex_pairs(values: np.ndarray) -> list[list[float]]:
    return [
        [float(complex(value).real), float(complex(value).imag)]
        for value in np.asarray(values, dtype=np.complex128).reshape(-1)
    ]


def _v1_2_scalar_pair(value: Any) -> list[float]:
    value = complex(value)
    return [float(value.real), float(value.imag)]


def _v1_2_matrix_pairs(value: np.ndarray) -> list[list[list[float]]]:
    matrix = np.asarray(value, dtype=np.complex128)
    if matrix.ndim != 2:
        raise ValueError("V1-2 contraction must be a matrix")
    return [[_v1_2_scalar_pair(item) for item in row] for row in matrix]


def _v1_2_json_finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(np.asarray(value, dtype=np.float64)).all())
    except (TypeError, ValueError):
        return False


def _v1_2_vec_contractions(
    source: PETSc.Vec,
    scalar: PETSc.Vec,
    exact: PETSc.Vec,
    projected: PETSc.Vec,
) -> dict[str, list[float]]:
    """Record only distributed Vec dot products, never FE-sized values."""

    return {
        "source_h_source": _v1_2_scalar_pair(source.dot(source)),
        "scalar_h_scalar": _v1_2_scalar_pair(scalar.dot(scalar)),
        "exact_h_exact": _v1_2_scalar_pair(exact.dot(exact)),
        "projected_h_projected": _v1_2_scalar_pair(projected.dot(projected)),
        "scalar_h_exact": _v1_2_scalar_pair(scalar.dot(exact)),
        "projected_h_exact": _v1_2_scalar_pair(projected.dot(exact)),
    }


def _v1_2_probe_coefficients(seed: int, count: int) -> np.ndarray:
    if int(count) <= 0:
        raise ValueError("V1-2 probe basis must be non-empty")
    indices = np.arange(int(count), dtype=np.int64)
    phase = ((int(seed) + 1) * (indices + 1)) % 104729
    return np.exp(2j * np.pi * phase / 104729.0).astype(np.complex128)


def _v1_2_seed_interface_active_row(
    seed: int, interface_rows_global: Sequence[int]
) -> int:
    rows = tuple(int(row) for row in interface_rows_global)
    if not rows:
        raise ValueError("V1-2 interface seed has no Gamma rows")
    return rows[int(seed) % len(rows)]


def _v1_2_global_interface_row_identity(
    oracle: Any, comm: MPI.Intracomm
) -> dict[str, dict[str, Any]]:
    identity: dict[str, dict[str, Any]] = {}
    for interface, group in (("lower", 0), ("upper", 2)):
        local_rows = oracle.group_gamma_rows_local(group)
        global_rows = tuple(
            int(row) for part in comm.allgather(local_rows.tolist()) for row in part
        )
        array = np.asarray(global_rows, dtype=np.int64)
        identity[interface] = {
            "global_rows": list(global_rows),
            "size": int(array.size),
            "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
        }
    return identity


def _v1_2_interface_probes(
    *,
    manifest: Mapping[str, Any],
    oracle: Any,
    petrov_actions: Sequence[Any],
    scalar_apply: Sequence[Callable[[PETSc.Vec, PETSc.Vec], None]],
    z_group: Sequence[np.ndarray],
    comm: MPI.Intracomm,
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    seed_groups = manifest["fixed_probe_seeds"]
    for interface, (group, seed_key) in enumerate(((0, "lower"), (2, "upper"))):
        basis = np.asarray(z_group[group], dtype=np.complex128)
        for probe_kind, seeds in (
            ("modal_combination", seed_groups["modal_combinations"][seed_key]),
            ("complement", seed_groups["complements"][seed_key]),
        ):
            for seed in seeds:
                source_values = np.zeros(basis.shape[0], dtype=np.complex128)
                if probe_kind == "modal_combination":
                    source_values[:] = basis @ _v1_2_probe_coefficients(
                        int(seed), basis.shape[1]
                    )
                else:
                    first, last = petrov_actions[group].ownership_range
                    packed_row = int(seed) % int(petrov_actions[group].global_rows)
                    if first <= packed_row < last:
                        source_values[packed_row - first] = 1.0
                source = petrov_actions[group].synthesize_owner_rows(source_values)
                scalar_target = source.duplicate()
                exact_target = source.duplicate()
                projected_target = source.duplicate()
                try:
                    y_before = petrov_actions[group].project_owner_rows(source)
                    if probe_kind == "complement":
                        factors = petrov_actions[group].projected_woodbury_factors()
                        local_coefficients = np.asarray(
                            factors["V"].conj().T
                            @ np.asarray(source.array, dtype=np.complex128),
                            dtype=np.complex128,
                        )
                        coefficients = np.empty_like(local_coefficients)
                        comm.Allreduce(local_coefficients, coefficients, op=MPI.SUM)
                        projected_values = source_values - basis @ coefficients
                        source.destroy()
                        source = petrov_actions[group].synthesize_owner_rows(
                            projected_values
                        )
                        norm = float(source.norm())
                        if norm <= 1.0e-30:
                            raise ValueError("V1-2 complement projection is zero")
                        source.scale(PETSc.ScalarType(1.0 / norm))
                        y_after = petrov_actions[group].project_owner_rows(source)
                    else:
                        y_after = y_before
                    scalar_apply[group](source, scalar_target)
                    oracle.apply_directed_neighbor(group, source, exact_target)
                    petrov_actions[group].apply(source, projected_target)
                    reports.append(
                        {
                            "interface": interface,
                            "group": group,
                            "kind": probe_kind,
                            "label": f"{seed_key}_{probe_kind}_{int(seed)}",
                            "seed": int(seed),
                            "scalar_exact_relative": _v1_2_relative_error(
                                scalar_target, exact_target
                            ),
                            "projected_exact_relative": _v1_2_relative_error(
                                projected_target, exact_target
                            ),
                            "YH_before_projection": _v1_2_complex_pairs(y_before),
                            "YH_after_projection": _v1_2_complex_pairs(y_after),
                            "complement_orthogonality_relative": (
                                float(np.linalg.norm(y_after))
                                / max(float(np.linalg.norm(y_before)), 1.0e-30)
                                if probe_kind == "complement"
                                else None
                            ),
                            "contractions": _v1_2_vec_contractions(
                                source,
                                scalar_target,
                                exact_target,
                                projected_target,
                            ),
                            "finite": bool(
                                np.isfinite(source.array).all()
                                and np.isfinite(scalar_target.array).all()
                                and np.isfinite(exact_target.array).all()
                                and np.isfinite(projected_target.array).all()
                            ),
                        }
                    )
                finally:
                    projected_target.destroy()
                    exact_target.destroy()
                    scalar_target.destroy()
                    source.destroy()
    return reports


def _v1_2_middle_cross_interface_samples(
    *,
    manifest: Mapping[str, Any],
    oracle: Any,
    petrov_actions: Sequence[Any],
    z_group: Sequence[np.ndarray],
    comm: MPI.Intracomm,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Sample the retained middle Schur, separately from the neighbor map."""

    seed_groups = manifest["fixed_probe_seeds"]
    group = 1
    basis = np.asarray(z_group[group], dtype=np.complex128)
    lower_count = int(np.asarray(z_group[0]).shape[1])
    middle_rows = oracle.group_gamma_rows_local(group)
    lower_rows = set(map(int, oracle.group_gamma_rows_local(0)))
    upper_rows = set(map(int, oracle.group_gamma_rows_local(2)))
    interface_identity = _v1_2_global_interface_row_identity(oracle, comm)
    interface_rows_global = {
        interface: tuple(identity["global_rows"])
        for interface, identity in interface_identity.items()
    }
    reports: list[dict[str, Any]] = []
    for interface, column_slice, seed_key in (
        ("lower", slice(0, lower_count), "lower"),
        ("upper", slice(lower_count, None), "upper"),
    ):
        interface_basis = basis[:, column_slice]
        for probe_kind, seeds in (
            ("modal_combination", seed_groups["modal_combinations"][seed_key]),
            ("complement", seed_groups["complements"][seed_key]),
        ):
            for seed in seeds:
                source_values = np.zeros(basis.shape[0], dtype=np.complex128)
                if probe_kind == "modal_combination":
                    source_values[:] = interface_basis @ _v1_2_probe_coefficients(
                        int(seed), interface_basis.shape[1]
                    )
                else:
                    active_row = _v1_2_seed_interface_active_row(
                        int(seed), interface_rows_global[seed_key]
                    )
                    local_matches = np.asarray(
                        [int(row) == active_row for row in middle_rows],
                        dtype=np.int32,
                    )
                    if int(comm.allreduce(int(local_matches.sum()), op=MPI.SUM)) != 1:
                        raise ValueError(
                            "V1-2 middle complement seed has no unique owner"
                        )
                    source_values[local_matches.astype(bool)] = 1.0
                    factors = petrov_actions[group].projected_woodbury_factors()
                    local_coefficients = np.asarray(
                        factors["V"].conj().T
                        @ np.asarray(source_values, dtype=np.complex128),
                        dtype=np.complex128,
                    )
                    coefficients = np.empty_like(local_coefficients)
                    comm.Allreduce(local_coefficients, coefficients, op=MPI.SUM)
                    source_values = source_values - basis @ coefficients
                source = petrov_actions[group].synthesize_owner_rows(source_values)
                target = oracle.create_group_gamma_vector(group)
                try:
                    if probe_kind == "complement":
                        norm = float(source.norm())
                        if norm <= 1.0e-30:
                            raise ValueError("V1-2 middle complement is zero")
                        source.scale(PETSc.ScalarType(1.0 / norm))
                    oracle.apply_group(group, source, target)
                    source_h_source = _v1_2_scalar_pair(source.dot(source))
                    target_values = np.asarray(target.array, dtype=np.complex128)
                    if interface == "lower":
                        same_mask = np.asarray(
                            [int(row) in lower_rows for row in middle_rows],
                            dtype=bool,
                        )
                        cross_mask = np.asarray(
                            [int(row) in upper_rows for row in middle_rows],
                            dtype=bool,
                        )
                    else:
                        same_mask = np.asarray(
                            [int(row) in upper_rows for row in middle_rows],
                            dtype=bool,
                        )
                        cross_mask = np.asarray(
                            [int(row) in lower_rows for row in middle_rows],
                            dtype=bool,
                        )
                    if np.any(same_mask & cross_mask):
                        raise ValueError("middle Gamma interface masks overlap")
                    if not np.all(same_mask | cross_mask):
                        raise ValueError(
                            "middle Gamma row is not in either interface support"
                        )
                    same_local = float(
                        np.real(
                            np.vdot(target_values[same_mask], target_values[same_mask])
                        )
                    )
                    cross_local = float(
                        np.real(
                            np.vdot(
                                target_values[cross_mask],
                                target_values[cross_mask],
                            )
                        )
                    )
                    same_squared = float(comm.allreduce(same_local, op=MPI.SUM))
                    cross_squared = float(comm.allreduce(cross_local, op=MPI.SUM))
                    total_squared = same_squared + cross_squared
                    same_interface_norm = math.sqrt(max(same_squared, 0.0))
                    cross_interface_norm = math.sqrt(max(cross_squared, 0.0))
                    total_norm = math.sqrt(max(total_squared, 0.0))
                    middle_h_middle = _v1_2_scalar_pair(target.dot(target))
                    source_h_middle = _v1_2_scalar_pair(source.dot(target))
                    identity = interface_identity[seed_key]
                    seed_identity = {}
                    if probe_kind == "complement":
                        interface_row_index = int(seed) % int(identity["size"])
                        seed_identity = {
                            "selected_active_row": int(
                                identity["global_rows"][interface_row_index]
                            ),
                            "interface_row_index": interface_row_index,
                            "interface_size": int(identity["size"]),
                            "interface_rows_global_order_sha256": identity["sha256"],
                        }
                    reports.append(
                        {
                            "label": f"middle_{seed_key}_{probe_kind}_{int(seed)}",
                            "interface": interface,
                            "group": group,
                            "source_group": group,
                            "kind": probe_kind,
                            "seed": int(seed),
                            "response": "middle_group1_schur",
                            "direction": "apply_group",
                            **seed_identity,
                            "contractions": {
                                "source_h_source": source_h_source,
                                "middle_h_middle": middle_h_middle,
                                "source_h_middle": source_h_middle,
                            },
                            "source_norm": float(source.norm()),
                            "middle_norm": total_norm,
                            "same_interface_norm": same_interface_norm,
                            "cross_interface_norm": cross_interface_norm,
                            "total_norm": total_norm,
                            "partition_disjoint": True,
                            "partition_complete": True,
                            "cross_to_total": (
                                cross_interface_norm / total_norm
                                if total_norm > 0.0
                                else 0.0
                            ),
                            "finite": bool(
                                np.isfinite(source.array).all()
                                and np.isfinite(target.array).all()
                            ),
                        }
                    )
                finally:
                    target.destroy()
                    source.destroy()
    return reports, interface_identity


def _v2_build_packet_layouts(
    *,
    system: Any,
    condensed: Any,
    supports: Sequence[Mapping[str, Any]],
    gamma_rows: Sequence[np.ndarray],
    lower_z: float,
    upper_z: float,
    comm: MPI.Intracomm,
) -> tuple[Any, Any, Any]:
    """Build the three owner-local canonical packet layouts."""

    lower_original, _ = _v1_2_local_interface_rows(
        condensed, supports[0], gamma_rows[0]
    )
    upper_original, _ = _v1_2_local_interface_rows(
        condensed, supports[1], gamma_rows[2]
    )
    lower_layout = build_dolfinx_plane_gamma_layout(
        function_space=system.V,
        condensed=condensed,
        floquet_data=getattr(system, "floquet_data", None),
        interface_z_nm=lower_z,
        plane_cell_side="lower",
        plane_original_dofs=lower_original,
        gamma_rows_local=gamma_rows[0],
        plane_identity={"route": "v2_interface_packet", "group": "group0"},
    )
    upper_layout = build_dolfinx_plane_gamma_layout(
        function_space=system.V,
        condensed=condensed,
        floquet_data=getattr(system, "floquet_data", None),
        interface_z_nm=upper_z,
        plane_cell_side="upper",
        plane_original_dofs=upper_original,
        gamma_rows_local=gamma_rows[2],
        plane_identity={"route": "v2_interface_packet", "group": "group2"},
    )
    middle_blocks = tuple(
        placement.block
        for layout in (lower_layout, upper_layout)
        for placement in layout.blocks
    )
    middle_layout = build_gamma_canonical_layout(
        middle_blocks,
        gamma_rows[1],
        plane_identity={
            "route": "v2_interface_packet",
            "group": "group1",
            "planes": ["lower", "upper"],
            "interface_z_nm": [lower_z, upper_z],
            "phase_convention": "stored_raw=phase*E*canonical",
        },
        comm=comm,
    )
    return lower_layout, middle_layout, upper_layout


def _v2_prepare_packet_shards(
    *,
    packet_root: str | Path,
    petrov_actions: Sequence[Any],
    packet_layouts: Sequence[Any],
    petrov_diagnostics: Sequence[Mapping[str, Any]],
    identity_observed: Mapping[str, Any],
    z_shapes: Sequence[Sequence[int]],
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    selected_manifest_sha256: str,
    spool_catalog_sha256: str,
    probe_manifest_sha256: str,
    lower_metadata: Mapping[str, Any],
    upper_metadata: Mapping[str, Any],
    physical_probe_reports: Sequence[Mapping[str, Any]],
    interface_probe_reports: Sequence[Mapping[str, Any]],
    middle_cross_interface_reports: Sequence[Mapping[str, Any]],
    middle_cross_interface_identity: Mapping[str, Any],
    middle_group_schur: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Detach one Petrov action at a time and write its owner-local shard."""

    descriptors: list[dict[str, Any]] = []
    small_matrices: dict[str, np.ndarray] = {}
    lower_span, middle_span, upper_span = (
        int(z_shapes[group][1]) for group in range(3)
    )
    if middle_span != lower_span + upper_span:
        raise ValueError("projected middle Schur spans do not form lower plus upper")
    middle_projected = np.asarray(middle_group_schur["projected"], dtype=np.complex128)
    if (
        middle_projected.shape != (middle_span, middle_span)
        or not np.isfinite(middle_projected).all()
    ):
        raise ValueError(
            "projected middle group Schur has the wrong shape or finite values"
        )
    lower_error: float | None = None
    upper_error: float | None = None
    for group, action in enumerate(petrov_actions):
        ownership_range = tuple(int(value) for value in action.ownership_range)
        factors = action.detach_projected_woodbury_factors()
        values_u = factors["U"]
        values_v = factors["V"]
        canonical = canonicalize_owner_local_basis_in_place(
            packet_layouts[group], values_u, values_v
        )
        descriptors.append(
            write_group_shard(
                packet_root,
                PacketGroup(f"group{group}", canonical.keys, canonical.U, canonical.V),
                comm=comm,
                ownership_range=ownership_range,
            )
        )
        if comm.rank == 0:
            small_matrices.update(
                {
                    f"gram_group{group}": np.asarray(factors["G"]),
                    f"projected_scalar_group{group}": np.asarray(
                        factors["projected_scalar"]
                    ),
                    f"projected_exact_group{group}": np.asarray(
                        factors["projected_exact"]
                    ),
                }
            )
        if group == 0:
            reference = middle_projected[:lower_span, :lower_span]
            lower_error = float(
                np.linalg.norm(factors["projected_exact"] - reference)
                / max(np.linalg.norm(reference), np.finfo(float).tiny)
            )
        elif group == 2:
            reference = middle_projected[lower_span:middle_span, lower_span:middle_span]
            upper_error = float(
                np.linalg.norm(factors["projected_exact"] - reference)
                / max(np.linalg.norm(reference), np.finfo(float).tiny)
            )
        if group == 2 and (
            lower_error is None
            or upper_error is None
            or lower_error > 1.0e-12
            or upper_error > 1.0e-12
        ):
            raise ValueError(
                "projected middle Schur diagonal blocks do not match group exact"
            )
        del canonical, values_u, values_v, factors
    middle_metadata = {
        key: value for key, value in middle_group_schur.items() if key != "projected"
    }
    middle_metadata.update(
        {
            "schema": "task040.v3.middle_group_schur_projection.v1",
            "storage": "packet_small_matrices",
            "matrix_name": "projected_middle_group_schur",
            "lower_identity_relative_error": lower_error,
            "upper_identity_relative_error": upper_error,
            "cross_blocks": {
                "LU_frobenius_norm": float(
                    np.linalg.norm(
                        middle_projected[:lower_span, lower_span:middle_span], ord="fro"
                    )
                ),
                "UL_frobenius_norm": float(
                    np.linalg.norm(
                        middle_projected[lower_span:middle_span, :lower_span], ord="fro"
                    )
                ),
                "LU_relative_frobenius_norm": float(
                    np.linalg.norm(
                        middle_projected[:lower_span, lower_span:middle_span], ord="fro"
                    )
                    / max(
                        np.linalg.norm(middle_projected, ord="fro"),
                        np.finfo(float).tiny,
                    )
                ),
                "UL_relative_frobenius_norm": float(
                    np.linalg.norm(
                        middle_projected[lower_span:middle_span, :lower_span], ord="fro"
                    )
                    / max(
                        np.linalg.norm(middle_projected, ord="fro"),
                        np.finfo(float).tiny,
                    )
                ),
            },
            "joint_exact_definition": (
                "projected_middle_group_schur + projected_exact_group1"
            ),
        }
    )
    if comm.rank == 0:
        small_matrices["projected_middle_group_schur"] = middle_projected
    return {
        "descriptors": descriptors,
        "small_matrices": small_matrices if comm.rank == 0 else None,
        "provenance": {
            "schema": "task040.v2.interface_packet_producer.v1",
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "selected_manifest_sha256": str(selected_manifest_sha256),
            "exact_spool_catalog_sha256": str(spool_catalog_sha256),
            "probe_manifest_sha256": str(probe_manifest_sha256),
            "qep_calls": 0,
            "pde_solve": "not_run",
            "v1_3_built": False,
        },
        "diagnostics": {
            "group_order": ["group0", "group1", "group2"],
            "groups": [
                {
                    "group": group,
                    "span_size": int(z_shapes[group][1]),
                    "gamma_layout": {
                        **dict(packet_layouts[group].audit),
                        **(
                            {
                                "global_size": int(
                                    middle_cross_interface_identity[interface]["size"]
                                ),
                                "gamma_rows_global_order_sha256": (
                                    middle_cross_interface_identity[interface]["sha256"]
                                ),
                            }
                            if (
                                interface := (
                                    "lower"
                                    if group == 0
                                    else "upper"
                                    if group == 2
                                    else None
                                )
                            )
                            is not None
                            else {}
                        ),
                    },
                    "petrov": dict(petrov_diagnostics[group]),
                }
                for group in range(3)
            ],
            "identity_observed": dict(identity_observed),
            "probe_manifest_sha256": identity_observed["probe_manifest_sha256"],
            "input_sha256": identity_observed["input_sha256"],
            "physical_model_sha256": identity_observed["physical_model_sha256"],
            "selected_manifest_sha256": identity_observed["selected_manifest_sha256"],
            "lower": {
                "mode_count": int(lower_metadata["mode_count"]),
                "mode_key_sha256": lower_metadata["mode_key_sha256"],
                "legacy_beta_metadata_sha256": lower_metadata[
                    "legacy_manifest_beta_metadata_sha256"
                ],
                "resolved_mode_metadata_sha256": lower_metadata[
                    "resolved_mode_metadata_sha256"
                ],
            },
            "upper": {
                "mode_count": int(len(upper_metadata["mode_keys"])),
                "mode_key_sha256": upper_metadata["mode_key_sha256"],
                "beta_sha256": upper_metadata["selected_packet_beta_sha256"],
                "branch_authority": upper_metadata["branch_authority"],
                "qep_calls": int(upper_metadata["qep_calls"]),
            },
            "exact_output_identity_sha256": dict(
                identity_observed["exact_output_identity_sha256"]
            ),
            "incoming_neighbor_map": {
                "map": "block_diagonal_neighbor_transmission",
                "response": "apply_directed_neighbor",
                "probe_count": len(interface_probe_reports),
            },
            "probes": list(physical_probe_reports) + list(interface_probe_reports),
            "lower_resolved_mode_metadata_sha256": lower_metadata[
                "resolved_mode_metadata_sha256"
            ],
            "upper_mode_key_sha256": upper_metadata["mode_key_sha256"],
            "upper_beta_sha256": upper_metadata["selected_packet_beta_sha256"],
            "basis_global_replicated": False,
            "fe_numeric_allgather": False,
            "physical_probe_reports": list(physical_probe_reports),
            "interface_probe_reports": list(interface_probe_reports),
            "middle_cross_interface_sampled_response": list(
                middle_cross_interface_reports
            ),
            "middle_cross_interface_identity": dict(middle_cross_interface_identity),
            "projected_matrix_names": {
                f"group{group}": {
                    "gram": f"gram_group{group}",
                    "scalar": f"projected_scalar_group{group}",
                    "exact": f"projected_exact_group{group}",
                }
                for group in range(3)
            },
            "additional_projected_matrices": {
                "projected_middle_group_schur": middle_metadata,
            },
            "factor_inventory": {
                "ready": 3,
                "after": 0,
                "simultaneous_max": 3,
                "full_side": 0,
                "global_direct": 0,
                "nested_ksp": 0,
            },
        },
        "expected_group_counts": {
            f"group{group}": int(packet_layouts[group].audit["global_row_count"])
            for group in range(3)
        },
    }


def _v2_finalize_packet(
    *,
    packet_root: str | Path,
    pending: Mapping[str, Any],
    exact_ready: Mapping[str, Any],
    exact_after: Mapping[str, Any],
    v1_2_gate: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    packet_diagnostics = {
        **dict(pending["diagnostics"]),
        **dict(diagnostics),
        "v1_2_gate": dict(v1_2_gate),
        "factor_lifecycle": {
            "exact_oracle_ready": dict(exact_ready),
            "exact_oracle_after_cleanup": dict(exact_after),
            "factor_count_ready": int(exact_ready["factor_count_ready"]),
            "factor_count_after_cleanup": int(
                exact_after["factor_count_after_cleanup"]
            ),
            "simultaneous_factor_count_max": int(exact_ready["factor_count_ready"]),
        },
        "packet_complete": True,
    }
    return finalize_manifest(
        packet_root,
        list(pending["descriptors"]),
        provenance=dict(pending["provenance"]),
        group_names=("group0", "group1", "group2"),
        expected_group_counts=dict(pending["expected_group_counts"]),
        small_matrices=pending["small_matrices"],
        diagnostics=packet_diagnostics,
        comm=comm,
    )


def _run_v1_2_interface_schur(
    *,
    cfg: Any,
    system: Any,
    bare_f: PETSc.Mat,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    group_rows: Sequence[np.ndarray],
    group_audit: dict[str, Any],
    supports: Sequence[Mapping[str, Any]],
    masses: Sequence[Any],
    exact_spool_root: str | Path,
    beta: complex,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
    resource_callback: Callable[[], Mapping[str, Any]] | None,
    producer_mode: bool = False,
    packet_root: str | Path | None = None,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    manifest_path, manifest = _v1_2_load_manifest()
    identity = manifest["identity"]
    selected_manifest = (
        Path(__file__).resolve().parents[1] / identity["selected_manifest"]
    )
    selected_manifest_sha256 = hashlib.sha256(
        selected_manifest.read_bytes()
    ).hexdigest()
    selected_payload = json.loads(selected_manifest.read_text(encoding="utf-8"))
    selected_identity_path = selected_manifest.with_name("identity.json")
    selected_identity = json.loads(selected_identity_path.read_text(encoding="utf-8"))
    if selected_payload.get("identity_sha256") != identity["selected_identity_sha256"]:
        raise ValueError("V1-2 selected identity SHA differs from frozen manifest")
    if (
        selected_payload.get("selection_sha256")
        != identity["selected_selection_sha256"]
    ):
        raise ValueError("V1-2 selected selection SHA differs from frozen manifest")
    resolved_path = Path(exact_spool_root).resolve().parent / "resolved_config.json"
    resolved = json.loads(resolved_path.read_text(encoding="utf-8"))
    resolved_modes = resolved["derived"]["external_mode_inventory"]
    lower_authority = {
        **resolved_modes,
        "keys": tuple(
            key for key in resolved_modes["keys"] if str(key["side"]) == "bottom"
        ),
        "modes": tuple(
            mode for mode in resolved_modes["modes"] if str(mode["side"]) == "bottom"
        ),
        "count": _v1_2_lower_mode_count(resolved_modes),
        "canonical_key_list_sha256": manifest["lower_fourier_floquet_basis"][
            "canonical_key_list_sha256"
        ],
        "beta_metadata_sha256": manifest["lower_fourier_floquet_basis"][
            "beta_metadata_sha256"
        ],
    }
    if _v1_2_build_hash := manifest["identity"]["exact_spool_resolved_config_sha256"]:
        if hashlib.sha256(resolved_path.read_bytes()).hexdigest() != _v1_2_build_hash:
            raise ValueError("V1-2 resolved lower-mode authority hash mismatch")
    cross_section = build_matching_cross_section(system.cfg, "stage4_xy", comm=comm)
    spaces = build_cross_section_spaces(
        cross_section, transverse_degree=int(system.cfg.nedelec_degree)
    )
    condensed = system.static_condensation.condensed
    oracle = None
    petrov_actions: list[Any] = []
    projected_action = None
    projected_owner = None
    owner_transferred = False
    exact_after: dict[str, Any] | None = None
    packet_layouts: tuple[Any, Any, Any] | None = None
    packet_pending: dict[str, Any] | None = None
    packet_manifest: dict[str, Any] | None = None
    middle_group_schur: dict[str, Any] | None = None
    middle_group_schur_metadata: dict[str, Any] | None = None
    source_vectors: dict[str, PETSc.Vec] = {}
    try:
        oracle = build_petsc_interface_schur_oracle(bare_f, group_rows, supports)
        gamma_rows = tuple(oracle.group_gamma_rows_local(group) for group in range(3))
        lower = _v1_2_build_lower_basis(
            cfg=cfg,
            system=system,
            spaces=spaces,
            condensed=condensed,
            support=supports[0],
            gamma_rows_local=gamma_rows[0],
            interface_z=float(manifest["interfaces"]["lower"]["z"]),
            authority=lower_authority,
        )
        upper = _v1_2_build_upper_basis(
            system=system,
            spaces=spaces,
            condensed=condensed,
            support=supports[1],
            gamma_rows_local=gamma_rows[2],
            interface_z=float(manifest["interfaces"]["upper"]["z"]),
            selected_manifest=selected_manifest,
            selected_identity=selected_identity,
            selected_payload=selected_payload,
            expected_mode_key_sha256=manifest["upper_selected_packet_basis"][
                "positive_mode_keys_sha256"
            ],
            expected_beta_sha256=manifest["upper_selected_packet_basis"][
                "positive_beta_sha256"
            ],
            comm=comm,
        )
        lower_y_audit: dict[str, Any] = {}
        upper_y_audit: dict[str, Any] = {}
        lower_y = build_mass_dual_from_active_vec(
            masses[0], condensed, gamma_rows[0], lower["left"], lower_y_audit
        )
        upper_y = build_mass_dual_from_active_vec(
            masses[1], condensed, gamma_rows[2], upper["left"], upper_y_audit
        )
        z_group = tuple(
            build_group_basis_columns(
                group,
                gamma_rows[group],
                gamma_rows[0],
                lower["values"],
                gamma_rows[2],
                upper["right"],
            )
            for group in range(3)
        )
        y_group = tuple(
            build_group_basis_columns(
                group,
                gamma_rows[group],
                gamma_rows[0],
                lower_y,
                gamma_rows[2],
                upper_y,
            )
            for group in range(3)
        )
        scalar_apply = tuple(
            _v1_2_scalar_gamma_apply(
                condensed=condensed,
                group=group,
                gamma_rows=gamma_rows[group],
                masses=masses,
                beta=beta,
            )
            for group in range(3)
        )
        for group in range(3):
            layout = oracle.create_group_gamma_vector(group)
            try:
                petrov_actions.append(
                    build_distributed_petrov_action(
                        layout,
                        scalar_apply[group],
                        lambda source, target, group=group: (
                            oracle.apply_directed_neighbor(group, source, target)
                        ),
                        z_group[group],
                        y_group[group],
                        local_row_ids=gamma_rows[group],
                    )
                )
            finally:
                layout.destroy()
        spool_identity, spool_manifest_sha, catalog = _v9_frozen_holdout_identity(
            exact_spool_root, comm
        )
        spool_catalog_sha256 = _v1_2_validate_spool_identity(
            selected_manifest_sha256=spool_manifest_sha, catalog=catalog
        )
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=spool_identity,
            manifest_sha256=spool_manifest_sha,
        )
        labels = tuple(manifest["physical_probes"]["labels"])
        exact_identities = manifest["physical_probes"]["exact_output_identity_sha256"]
        traces, observed_exact_ids = _v1_2_restrict_exact_probes(
            spool=spool,
            labels=labels,
            expected_identities=exact_identities,
            template_matrix=bare_f,
            lower_rows=gamma_rows[0],
            upper_rows=gamma_rows[2],
        )
        probe_reports = _v1_2_probe_actions(
            labels=labels,
            traces=traces,
            oracle=oracle,
            petrov_actions=petrov_actions,
            scalar_apply=scalar_apply,
            gamma_rows=gamma_rows,
        )
        interface_probe_reports = _v1_2_interface_probes(
            manifest=manifest,
            oracle=oracle,
            petrov_actions=petrov_actions,
            scalar_apply=scalar_apply,
            z_group=z_group,
            comm=comm,
        )
        (
            middle_cross_interface_reports,
            middle_cross_interface_identity,
        ) = _v1_2_middle_cross_interface_samples(
            manifest=manifest,
            oracle=oracle,
            petrov_actions=petrov_actions,
            z_group=z_group,
            comm=comm,
        )
        if producer_mode:
            middle_group_schur = petrov_actions[1].project_additional_action(
                lambda source, target: oracle.apply_group(1, source, target),
                name="projected_middle_group_schur",
                semantic="Y1^H [oracle.apply_group(1)] Z1",
            )
        exact_ready = oracle.diagnostics
        petrov_diagnostics = [action.diagnostics for action in petrov_actions]
        petrov_contractions = None
        if not producer_mode:
            petrov_contractions = [
                {
                    name: _v1_2_matrix_pairs(value)
                    for name, value in action.projected_contractions.items()
                    if name in {"gram", "scalar", "exact"}
                }
                for action in petrov_actions
            ]
        if producer_mode:
            if packet_root is None:
                raise ValueError("V2 producer requires a worker packet root")
            packet_layouts = _v2_build_packet_layouts(
                system=system,
                condensed=condensed,
                supports=supports,
                gamma_rows=gamma_rows,
                lower_z=float(manifest["interfaces"]["lower"]["z"]),
                upper_z=float(manifest["interfaces"]["upper"]["z"]),
                comm=comm,
            )
        if producer_mode:
            assert packet_layouts is not None
            group_layouts = [dict(layout.audit) for layout in packet_layouts]
        else:
            group_layouts = [
                {
                    **oracle.group_gamma_layout(group),
                    "basis_global_replicated": False,
                    "fe_numeric_allgather": False,
                }
                for group in range(3)
            ]
        identity_observed = {
            "probe_manifest_sha256": hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest(),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "selected_manifest_sha256": selected_manifest_sha256,
            "selected_identity_sha256": selected_payload.get("identity_sha256"),
            "selected_selection_sha256": selected_payload.get("selection_sha256"),
            "selected_identity_physical_sha256": selected_identity.get(
                "physical_sha256"
            ),
            "resolved_config_sha256": hashlib.sha256(
                resolved_path.read_bytes()
            ).hexdigest(),
            "spool_catalog_sha256": spool_catalog_sha256,
            "exact_output_identity_sha256": dict(observed_exact_ids),
            "upper_mode_key_sha256": upper["mode_key_sha256"],
            "upper_beta_sha256": upper["selected_packet_beta_sha256"],
            "lower_mode_key_sha256": lower["mode_key_sha256"],
            "lower_resolved_mode_metadata_sha256": lower[
                "resolved_mode_metadata_sha256"
            ],
            "lower_legacy_beta_metadata_sha256": lower[
                "legacy_manifest_beta_metadata_sha256"
            ],
        }
        identity_pass = _v1_2_identity_pass(
            identity_observed=identity_observed,
            frozen_identity=identity,
            manifest=manifest,
            exact_identities=exact_identities,
        )
        resource_observed = (
            dict(resource_callback()) if resource_callback is not None else None
        )
        resource_pass = bool(
            resource_observed is not None
            and resource_observed.get("all_status_readable") is True
            and int(resource_observed.get("rss_bytes", -1))
            < (
                TASK040_V2_INTERFACE_PACKET_HARD_STOP_BYTES
                if producer_mode
                else TASK040_LEVEL_A_HARD_STOP_BYTES
            )
            and int(resource_observed.get("swap_bytes", -1)) == 0
        )
        preferred_resource_pass = bool(
            resource_observed is not None
            and resource_observed.get("all_status_readable") is True
            and int(resource_observed.get("rss_bytes", -1))
            <= TASK040_V2_INTERFACE_PACKET_PREFERRED_BYTES
            and int(resource_observed.get("swap_bytes", -1)) == 0
        )
        condition_pass = all(
            np.isfinite(float(petrov_diagnostics[group]["gram"]["condition"]))
            and float(petrov_diagnostics[group]["gram"]["condition"]) <= 1.0e12
            for group in range(3)
        )
        v1_2_gate = {
            "identity_pass": identity_pass,
            "projection_pass": all(
                all(np.isfinite(values).all() for values in matrix)
                for matrix in (lower["values"], upper["right"], upper["left"])
            ),
            "finite_pass": all(
                np.isfinite(report["projected_exact_relative"])
                and all(
                    _v1_2_json_finite(value)
                    for value in report["contractions"].values()
                )
                for report in probe_reports
            )
            and all(report["finite"] for report in interface_probe_reports)
            and all(report["finite"] for report in middle_cross_interface_reports),
            "gram_pass": all(
                petrov_diagnostics[group]["gram"]["rank"]
                == petrov_diagnostics[group]["small_replicated_shapes"]["gram"][0]
                for group in range(3)
            ),
            "complement_pass": all(
                report["kind"] != "complement"
                or report["complement_orthogonality_relative"] <= 1.0e-8
                for report in interface_probe_reports
            ),
            "factor_pass": exact_ready.get("factor_count_ready") == 3,
            "lifecycle_pass": False,
            "resource_pass": resource_pass,
            "middle_cross_interface_pass": bool(
                len(middle_cross_interface_reports) == 8
                and all(
                    report["finite"]
                    and report["source_norm"] > 0.0
                    and report["middle_norm"] > 0.0
                    for report in middle_cross_interface_reports
                )
            ),
        }
        if producer_mode:
            v1_2_gate["condition_pass"] = condition_pass
            v1_2_gate["preferred_resource_pass"] = preferred_resource_pass
            z_shapes = tuple(
                tuple(int(value) for value in matrix.shape) for matrix in z_group
            )
            y_shapes = tuple(
                tuple(int(value) for value in matrix.shape) for matrix in y_group
            )
            for key in ("values", "left"):
                lower.pop(key, None)
            for key in ("right", "left"):
                upper.pop(key, None)
            del spool, traces, scalar_apply, z_group, y_group, lower_y, upper_y
            if not all(
                bool(value)
                for name, value in v1_2_gate.items()
                if name
                not in {"factor_pass", "lifecycle_pass", "preferred_resource_pass"}
            ):
                raise RuntimeError(
                    "V2 producer stopped before packet export: V1-2 probe Gate failed"
                )
            assert packet_layouts is not None
            packet_pending = _v2_prepare_packet_shards(
                packet_root=packet_root,
                petrov_actions=petrov_actions,
                packet_layouts=packet_layouts,
                petrov_diagnostics=petrov_diagnostics,
                identity_observed=identity_observed,
                z_shapes=z_shapes,
                source_sha=source_sha,
                input_sha256=input_sha256,
                physical_model_sha256=physical_model_sha256,
                selected_manifest_sha256=selected_manifest_sha256,
                spool_catalog_sha256=spool_catalog_sha256,
                probe_manifest_sha256=identity_observed["probe_manifest_sha256"],
                lower_metadata=lower,
                upper_metadata=upper,
                physical_probe_reports=probe_reports,
                interface_probe_reports=interface_probe_reports,
                middle_cross_interface_reports=middle_cross_interface_reports,
                middle_cross_interface_identity=middle_cross_interface_identity,
                middle_group_schur=middle_group_schur,
                comm=comm,
            )
            middle_group_schur_metadata = dict(
                packet_pending["diagnostics"]["additional_projected_matrices"][
                    "projected_middle_group_schur"
                ]
            )
            packet_layouts = None
            middle_group_schur = None
        _emit(
            marker_callback,
            "v1_2_exact_oracle_ready",
            factor_count_ready=exact_ready["factor_count_ready"],
            group_count=3,
            lower_mode_count=int(lower["mode_count"]),
            upper_mode_count=int(selected_payload["mode_count"]),
        )
        oracle.destroy()
        exact_after = oracle.diagnostics
        oracle = None
        v1_2_gate["factor_pass"] = bool(
            exact_ready.get("factor_count_ready") == 3
            and exact_after.get("factor_count_after_cleanup") == 0
            and exact_after.get("destroyed") is True
        )
        v1_2_gate["lifecycle_pass"] = bool(
            exact_ready.get("factor_count_ready") == 3
            and exact_after.get("factor_count_after_cleanup") == 0
        )
        v1_2_gate["pass"] = all(
            bool(value)
            for name, value in v1_2_gate.items()
            if name != "preferred_resource_pass"
        )
        _emit(
            marker_callback,
            "v1_2_exact_oracle_released",
            factor_count_after_cleanup=exact_after["factor_count_after_cleanup"],
        )
        if producer_mode:
            if not v1_2_gate["pass"]:
                raise RuntimeError(
                    "V2 producer exact factor lifecycle did not close 3->0"
                )
            assert packet_pending is not None
            packet_manifest = _v2_finalize_packet(
                packet_root=packet_root,
                pending=packet_pending,
                exact_ready=exact_ready,
                exact_after=exact_after,
                v1_2_gate=v1_2_gate,
                diagnostics={
                    "identity_observed": identity_observed,
                    "middle_cross_interface_sampled_response": (
                        middle_cross_interface_reports
                    ),
                    "middle_cross_interface_identity": middle_cross_interface_identity,
                },
                comm=comm,
            )
            projected_diagnostics = {"v1_3_not_run": "producer_route_disables_v1_3"}
        elif v1_2_gate["pass"]:
            projected_action, projected_owner, projected_diagnostics = (
                build_v1_3_projected_transmission(
                    bare_f=bare_f,
                    group_rows=list(group_rows),
                    interface_masses=list(masses),
                    beta=beta,
                    group_audit=group_audit,
                    petrov_actions=petrov_actions,
                )
            )
            _emit(
                marker_callback,
                "v1_3_projected_ready",
                **dict(projected_diagnostics),
            )
        else:
            projected_diagnostics = {"v1_3_not_run": "v1_2_gate_failed"}
        projected_ready = (
            projected_owner.diagnostics if projected_owner is not None else None
        )
        projected_audit = None
        projected_screen = None
        projected_inventory = None
        if projected_action is not None and projected_owner is not None:
            for label in TASK040_LEVEL_A_SOURCE_LABELS:
                template = bare_f.createVecLeft()
                try:
                    source_vectors[label] = _load_v5_blr_reference_spool_remapped(
                        spool[label]["rhs"], template
                    )
                finally:
                    template.destroy()
            projected_inventory = {
                "observed": True,
                "factor_count_ready": int(projected_ready["factor_count_ready"]),
                "cross_section_factor_count_ready": int(
                    projected_ready["factor_count_ready"]
                ),
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "oracle_only": True,
                "scalable_candidate": False,
            }
            if projected_inventory["factor_count_ready"] != 3:
                raise RuntimeError("V1-3 scalar factor inventory is not exactly three")
            projected_audit = audit_petsc_level_a_one_apply(
                projected_action,
                bare_f,
                source_vectors,
                projected_inventory,
                collect_scalar_contractions=True,
            )
            projected_screen = run_v1_1_right_preconditioned_fgmres_batch(
                bare_f,
                {
                    label: source_vectors[label]
                    for label in TASK040_LEVEL_A_SOURCE_LABELS[1:]
                },
                projected_action,
                labels=TASK040_LEVEL_A_SOURCE_LABELS[1:],
                resource_callback=resource_callback,
                stop_on_frozen_gate=True,
                checkpoint_callback=lambda row: _emit(
                    marker_callback, "v1_3_fgmres_checkpoint", **dict(row)
                ),
            )
            for vector in source_vectors.values():
                vector.destroy()
            source_vectors.clear()
        for action in petrov_actions:
            action.destroy()
        petrov_actions.clear()
        route_result = {
            "result": {
                "schema": (
                    TASK040_V2_INTERFACE_PACKET_SCHEMA
                    if producer_mode
                    else TASK040_V1_2_SCHEMA
                ),
                "method": (
                    TASK040_V2_INTERFACE_PACKET_METHOD
                    if producer_mode
                    else TASK040_V1_2_METHOD
                ),
                "profile": (
                    TASK040_V2_INTERFACE_PACKET_PROFILE_ID
                    if producer_mode
                    else TASK040_V1_2_PROFILE_ID
                ),
                "source_sha": str(source_sha),
                "input_sha256": str(input_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "selected_manifest_sha256": selected_manifest_sha256,
                "exact_spool_catalog_sha256": spool_catalog_sha256,
                "sequence": list(TASK040_LEVEL_A_SEQUENCE),
                "beta": {
                    "formula": "cfg.k0 * complex(cfg.substrate_index)",
                    "value": [float(beta.real), float(beta.imag)],
                    "q": [float((-1j * beta).real), float((-1j * beta).imag)],
                    "authority": TASK040_LEVEL_A_BETA_AUTHORITY,
                },
                "interface_schur_raw": {
                    "basis_global_replicated": False,
                    "fe_numeric_allgather": False,
                    "probe_manifest_sha256": identity_observed["probe_manifest_sha256"],
                    "lower": {
                        "mode_count": int(lower["mode_count"]),
                        "mode_key_sha256": lower["mode_key_sha256"],
                        "legacy_beta_metadata_sha256": lower[
                            "legacy_manifest_beta_metadata_sha256"
                        ],
                        "resolved_mode_metadata_sha256": lower[
                            "resolved_mode_metadata_sha256"
                        ],
                    },
                    "upper": {
                        "mode_count": int(upper["mode_keys"].__len__()),
                        "mode_key_sha256": upper["mode_key_sha256"],
                        "beta_sha256": upper["selected_packet_beta_sha256"],
                        "branch_authority": upper["branch_authority"],
                        "qep_calls": upper["qep_calls"],
                    },
                    "exact_output_identity_sha256": dict(observed_exact_ids),
                    "exact_output_metadata_hash_validation": True,
                    "spool_catalog_sha256": spool_catalog_sha256,
                    "spool_catalog": catalog,
                    "groups": [
                        {
                            "group": group,
                            "span_size": int(
                                z_shapes[group][1]
                                if producer_mode
                                else z_group[group].shape[1]
                            ),
                            "gamma_layout": group_layouts[group],
                            "z_shape_local": list(
                                z_shapes[group]
                                if producer_mode
                                else z_group[group].shape
                            ),
                            "y_shape_local": list(
                                y_shapes[group]
                                if producer_mode
                                else y_group[group].shape
                            ),
                            "petrov": petrov_diagnostics[group],
                            "projected_contractions": (
                                petrov_contractions[group]
                                if petrov_contractions is not None
                                else {
                                    "storage": "packet_small_matrices",
                                    "gram": f"gram_group{group}",
                                    "scalar": f"projected_scalar_group{group}",
                                    "exact": f"projected_exact_group{group}",
                                }
                            ),
                        }
                        for group in range(3)
                    ],
                    "physical_probes": probe_reports,
                    "incoming_neighbor_map": {
                        "map": "block_diagonal_neighbor_transmission",
                        "response": "apply_directed_neighbor",
                        "probe_count": len(interface_probe_reports),
                    },
                    "interface_probes": interface_probe_reports,
                    "middle_cross_interface_sampled_response": (
                        middle_cross_interface_reports
                    ),
                    "middle_cross_interface_identity": (
                        middle_cross_interface_identity
                    ),
                    "probes": probe_reports + interface_probe_reports,
                    "exact_oracle": exact_ready,
                    "exact_oracle_after_cleanup": exact_after,
                    "factor_inventory": {
                        "ready": exact_ready.get("factor_count_ready"),
                        "after": exact_after.get("factor_count_after_cleanup"),
                        "simultaneous_max": exact_ready.get("factor_count_ready"),
                        "full_side": exact_ready.get("full_side_exact_factor_count", 0),
                        "global_direct": exact_ready.get(
                            "global_direct_factor_count", 0
                        ),
                        "nested_ksp": exact_ready.get("nested_ksp_count", 0),
                    },
                    "lifecycle": {
                        "exact_factor_count_ready": exact_ready.get(
                            "factor_count_ready"
                        ),
                        "exact_factor_count_after_cleanup": exact_after.get(
                            "factor_count_after_cleanup"
                        ),
                        "simultaneous_factor_count_max": exact_ready.get(
                            "factor_count_ready"
                        ),
                    },
                    "v1_2_gate": v1_2_gate,
                    "identity_observed": identity_observed,
                    "resource_observed": resource_observed,
                    "v1_3_conditional": projected_diagnostics,
                    "v1_3_factor_inventory": projected_inventory
                    if projected_action is not None
                    else None,
                    "v1_3_one_apply": projected_audit,
                    "v1_3_screen": projected_screen,
                },
                "source_loading": {
                    "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS)
                    if projected_action is not None
                    else 0,
                    "exact_output_vectors_loaded": len(labels),
                    "exact_output_metadata_hash_validation_only": False,
                },
                "pde_solve": "not_run",
                "top": "not_run",
                "scalable_candidate": False,
            },
            "action": projected_action,
            "owner": projected_owner,
        }
        if producer_mode:
            route_result["result"]["interface_schur_raw"].update(
                {
                    "packet": packet_manifest,
                    "producer_route": True,
                    "additional_projected_matrices": {
                        "projected_middle_group_schur": middle_group_schur_metadata,
                    },
                }
            )
        owner_transferred = True
        return route_result
    finally:
        for vector in source_vectors.values():
            vector.destroy()
        for action in reversed(petrov_actions):
            action.destroy()
        if not owner_transferred:
            if projected_owner is not None:
                projected_owner.destroy()
                projected_owner = None
                projected_action = None
            elif projected_action is not None:
                projected_action.destroy()
                projected_action = None
        if oracle is not None:
            oracle.destroy()
        del spaces, cross_section


def _v2_packet_provenance(
    manifest: Mapping[str, Any],
    *,
    input_sha256: str,
    physical_model_sha256: str,
) -> dict[str, Any]:
    """Validate the producer identity without constructing its FEM objects."""

    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("V2 packet manifest has no producer provenance")
    expected = {
        "schema": TASK040_V2_INTERFACE_PACKET_SCHEMA,
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "selected_manifest_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
        "exact_spool_catalog_sha256": TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
        "probe_manifest_sha256": TASK040_V1_2_PROBE_MANIFEST_SHA256,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "v1_3_built": False,
    }
    if any(provenance.get(key) != value for key, value in expected.items()):
        raise ValueError("V2 packet producer provenance is not frozen")
    producer_source = provenance.get("source_sha")
    if (
        not isinstance(producer_source, str)
        or len(producer_source) != 40
        or any(character not in "0123456789abcdef" for character in producer_source)
    ):
        raise ValueError("V2 packet producer source SHA is invalid")
    return dict(provenance)


def _v2_packet_gamma_rows(
    supports: Sequence[Mapping[str, Any]],
    group_rows: Sequence[np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Select packet Gamma rows from the current owner-local group order."""

    lower = {int(row) for row in supports[0]["active_support"]}
    upper = {int(row) for row in supports[1]["active_support"]}
    if lower.intersection(upper):
        raise ValueError("V2 packet lower/upper Gamma supports overlap")
    expected = (lower, lower | upper, upper)
    result: list[np.ndarray] = []
    for group, rows in enumerate(group_rows):
        ordered = np.asarray(
            [int(row) for row in rows if int(row) in expected[group]],
            dtype=PETSc.IntType,
        )
        result.append(ordered)
    return result[0], result[1], result[2]


def _run_v2_packet_consumer(
    *,
    system: Any,
    bare_f: PETSc.Mat,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    group_rows: Sequence[np.ndarray],
    group_audit: Mapping[str, Any],
    supports: Sequence[Mapping[str, Any]],
    masses: Sequence[Any],
    exact_spool_root: str | Path,
    beta: complex,
    packet_root: str | Path,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
    resource_callback: Callable[[], Mapping[str, Any]] | None,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Hydrate one reviewed packet into the existing Level-A projected sweep."""

    packet_layouts: tuple[Any, Any, Any] | None = None
    gamma_factors: list[dict[str, np.ndarray]] = []
    source_vectors: dict[str, PETSc.Vec] = {}
    action: Any | None = None
    owner: Any | None = None
    owner_transferred = False
    remap_reports: list[dict[str, Any]] = []
    manifest: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    packet_manifest_sha256: str | None = None
    try:
        z_values = system.local_mesh.z_values
        packet_gamma_rows = _v2_packet_gamma_rows(supports, group_rows)
        packet_layouts = _v2_build_packet_layouts(
            system=system,
            condensed=system.static_condensation.condensed,
            supports=supports,
            gamma_rows=packet_gamma_rows,
            lower_z=float(z_values[2]),
            upper_z=float(z_values[4]),
            comm=comm,
        )
        manifest_group_diagnostics = None
        for group in range(3):
            name = f"group{group}"
            layout = packet_layouts[group]
            load_started = time.perf_counter()
            _v2_group_marker(
                marker_callback,
                "packet_group_load_begin",
                group=group,
                layout=layout,
                span_size=None,
                comm=comm,
            )
            loaded = load_packet_shard(
                packet_root,
                groups=(name,),
                expected_manifest_sha256=(TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256),
                comm=comm,
            )
            packet_group: PacketGroup | None = None
            group_descriptor: Mapping[str, Any] | None = None
            group_diagnostic: Mapping[str, Any] | None = None
            expected_count = -1
            span_size: int | None = None
            local_error: str | None = None
            try:
                if manifest is None:
                    manifest = loaded["manifest"]
                    packet_manifest_sha256 = str(loaded["manifest_sha256"])
                    provenance = _v2_packet_provenance(
                        manifest,
                        input_sha256=input_sha256,
                        physical_model_sha256=physical_model_sha256,
                    )
                    diagnostics_groups = manifest.get("diagnostics", {}).get("groups")
                    if (
                        not isinstance(diagnostics_groups, list)
                        or len(diagnostics_groups) != 3
                    ):
                        raise ValueError(
                            "V2 packet diagnostics have no three group records"
                        )
                    manifest_group_diagnostics = tuple(diagnostics_groups)
                packet_group = loaded["groups"].get(name)
                if packet_group is None:
                    raise ValueError(f"V2 packet did not load {name}")
                group_descriptor = manifest["groups"].get(name)
                group_diagnostic = manifest_group_diagnostics[group]
                expected_count = int(group_descriptor["global_count"])
                if int(layout.audit["global_row_count"]) != expected_count:
                    raise ValueError(
                        f"V2 packet {name} Gamma count differs from current layout"
                    )
                span_size = int(packet_group.U.shape[1])
                if int(group_diagnostic.get("span_size", span_size)) != span_size:
                    raise ValueError(
                        f"V2 packet {name} span size differs from manifest"
                    )
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
            _v2_collective_stage_error(comm, "packet_group_descriptor", local_error)
            assert packet_group is not None
            assert group_descriptor is not None
            assert group_diagnostic is not None
            assert span_size is not None
            _v2_group_marker(
                marker_callback,
                "packet_group_load_ready",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                started=load_started,
                global_row_count=expected_count,
            )

            redistribution_started = time.perf_counter()
            _v2_group_marker(
                marker_callback,
                "packet_group_owner_redistribute_begin",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                source_local_rows=int(packet_group.U.shape[0]),
                target_local_rows=len(layout.canonical_keys),
            )
            try:
                redistributed_group, redistribution_audit = (
                    redistribute_packet_group_rows(
                        packet_group,
                        layout.canonical_keys,
                        comm=comm,
                    )
                )
            except Exception as exc:
                raise RuntimeError(
                    f"V2 packet stage packet_group_owner_redistribute failed: {exc}"
                ) from exc
            redistribution_marker = dict(redistribution_audit)
            redistribution_marker.pop("span_size", None)
            _v2_group_marker(
                marker_callback,
                "packet_group_owner_redistribute_ready",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                started=redistribution_started,
                **redistribution_marker,
            )
            del packet_group, loaded

            reconstruct_started = time.perf_counter()
            _v2_group_marker(
                marker_callback,
                "packet_group_reconstruct_begin",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
            )
            canonical_basis: CanonicalOwnerLocalBasis | None = None
            raw_basis: Any | None = None
            local_error = None
            try:
                canonical_basis = CanonicalOwnerLocalBasis(
                    tuple(redistributed_group.keys),
                    redistributed_group.U,
                    redistributed_group.V,
                )
                raw_basis = reconstruct_owner_local_basis(
                    layout,
                    canonical_basis.keys,
                    canonical_basis.U,
                    canonical_basis.V,
                )
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
            _v2_collective_stage_error(comm, "packet_group_reconstruct", local_error)
            assert canonical_basis is not None
            assert raw_basis is not None
            _v2_group_marker(
                marker_callback,
                "packet_group_reconstruct_ready",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                started=reconstruct_started,
            )

            audit_started = time.perf_counter()
            _v2_group_marker(
                marker_callback,
                "packet_group_roundtrip_audit_begin",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
            )
            audit: dict[str, Any] | None = None
            local_error = None
            try:
                audit = audit_owner_local_basis_round_trip(
                    layout,
                    raw_basis.U,
                    raw_basis.V,
                    canonical_basis,
                )
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
            _v2_collective_stage_error(
                comm, "packet_group_roundtrip_audit", local_error
            )
            assert audit is not None
            global_error = float(
                comm.allreduce(float(audit["max_relative_error"]), op=MPI.MAX)
            )
            _v2_group_marker(
                marker_callback,
                "packet_group_roundtrip_audit_ready",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                started=audit_started,
                collective_max_relative_error=global_error,
            )
            local_error = None
            if not bool(audit["pass"]) or global_error > 1.0e-12:
                local_error = (
                    f"{name} canonical remap exceeds tolerance ({global_error:.17g})"
                )
            _v2_collective_stage_error(
                comm, "packet_group_collective_remap", local_error
            )
            remap_reports.append(
                {
                    "group": group,
                    "global_row_count": expected_count,
                    "span_size": span_size,
                    "local_row_count": int(layout.audit["local_row_count"]),
                    "local": audit,
                    "owner_redistribution": redistribution_audit,
                    "collective_max_relative_error": global_error,
                    "pass": bool(audit["pass"] and global_error <= 1.0e-12),
                }
            )
            gamma_factors.append({"U": raw_basis.U, "V": raw_basis.V})
            _v2_group_marker(
                marker_callback,
                "packet_group_collective_remap_ready",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                collective_max_relative_error=global_error,
            )
            del raw_basis, canonical_basis, redistributed_group

        if manifest is None or provenance is None:
            raise RuntimeError("V2 packet did not provide a manifest")
        if (
            manifest.get("basis_global_replicated") is not False
            or manifest.get("fe_numeric_allgather") is not False
        ):
            raise ValueError("V2 packet numeric replication flags are invalid")
        if packet_manifest_sha256 is None:
            raise RuntimeError("V2 packet manifest SHA was not observed")
        packet_layouts = None
        _emit(marker_callback, "projected_setup_begin", group_count=3)
        action, owner, projected_diagnostics = build_v2_packet_projected_transmission(
            bare_f=bare_f,
            group_rows=list(group_rows),
            interface_masses=list(masses),
            beta=beta,
            group_audit=dict(group_audit),
            gamma_rows=list(packet_gamma_rows),
            gamma_factors=gamma_factors,
        )
        projected_required = {
            "projected_factor_count_ready": 3,
            "exact_interface_oracle_factor_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "oracle_only": True,
            "scalable_candidate": False,
            "fe_numeric_allgather": False,
        }
        if any(
            projected_diagnostics.get(key) != value
            for key, value in projected_required.items()
        ):
            raise RuntimeError("V2 consumer projected diagnostics failed")
        _emit(
            marker_callback,
            "projected_setup_ready",
            factor_count_ready=projected_diagnostics["projected_factor_count_ready"],
        )
        gamma_factors.clear()
        ready_owner = dict(owner.diagnostics)
        factor_inventory = {
            "observed": True,
            "factor_count_ready": int(ready_owner.get("factor_count_ready", -1)),
            "cross_section_factor_count_ready": int(
                ready_owner.get("factor_count_ready", -1)
            ),
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "exact_interface_oracle_factor_count": 0,
            "oracle_only": True,
            "scalable_candidate": False,
        }
        if factor_inventory["factor_count_ready"] != 3:
            raise RuntimeError("V2 consumer projected factor inventory is not three")

        packet_identity, selected_manifest_sha, catalog = _v9_frozen_holdout_identity(
            exact_spool_root, comm
        )
        catalog_sha = _v1_2_validate_spool_identity(
            selected_manifest_sha256=selected_manifest_sha,
            catalog=catalog,
        )
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=packet_identity,
            manifest_sha256=selected_manifest_sha,
        )
        for label in TASK040_LEVEL_A_SOURCE_LABELS:
            template = bare_f.createVecLeft()
            try:
                source_vectors[label] = _load_v5_blr_reference_spool_remapped(
                    spool[label]["rhs"], template
                )
            finally:
                template.destroy()
        del spool
        _emit(
            marker_callback,
            "source_ready",
            labels=list(TASK040_LEVEL_A_SOURCE_LABELS),
            rhs_vectors_loaded=len(TASK040_LEVEL_A_SOURCE_LABELS),
            exact_output_vectors_loaded=0,
            exact_output_metadata_hash_validation_only=True,
        )
        one_apply = audit_petsc_level_a_one_apply(
            action,
            bare_f,
            source_vectors,
            factor_inventory,
            collect_scalar_contractions=True,
        )
        one_apply_gate = one_apply["gate"]
        implementation_subset_pass = all(
            (
                one_apply_gate.get("finite_pass") is True,
                one_apply_gate.get("zero_map_pass") is True,
                one_apply_gate.get("action_identity_pass") is True,
                one_apply_gate.get("repeat_pass") is True,
                one_apply_gate.get("linearity_pass") is True,
                one_apply_gate.get("factor_inventory_pass") is True,
            )
        )
        if not implementation_subset_pass:
            raise RuntimeError(
                "V2 consumer one-apply implementation subset failed: "
                f"{one_apply_gate!r}"
            )
        one_apply_gate["v2_implementation_subset_pass"] = True
        scalar_labels = tuple(TASK040_LEVEL_A_SOURCE_LABELS[1:])
        screen = run_v1_1_right_preconditioned_fgmres_batch(
            bare_f,
            {label: source_vectors[label] for label in scalar_labels},
            action,
            labels=scalar_labels,
            resource_callback=resource_callback,
            stop_on_frozen_gate=True,
            checkpoint_callback=lambda row: _emit(
                marker_callback, "v2_consumer_fgmres_checkpoint", **dict(row)
            ),
        )
        first_preferred_checkpoint = None
        phase = screen["phase1"]
        for checkpoint in ("4", "8", "16"):
            values = [
                phase[label]["checkpoints"]
                .get(checkpoint, {})
                .get("true_residual_relative")
                for label in scalar_labels
            ]
            if (
                values
                and all(
                    isinstance(value, (int, float))
                    and np.isfinite(float(value))
                    and float(value) <= 1.0e-2
                    for value in values
                )
                and all(float(value) <= 1.0e-3 for value in values[:3])
            ):
                first_preferred_checkpoint = int(checkpoint)
                break
        if first_preferred_checkpoint is None and screen["phase2"]:
            values = [
                screen["phase2"][label]["checkpoints"]
                .get("32", {})
                .get("true_residual_relative")
                for label in scalar_labels
            ]
            if (
                values
                and all(
                    isinstance(value, (int, float))
                    and np.isfinite(float(value))
                    and float(value) <= 1.0e-2
                    for value in values
                )
                and all(float(value) <= 1.0e-3 for value in values[:3])
            ):
                first_preferred_checkpoint = 32
        _emit(
            marker_callback,
            "level_a_audit_complete",
            first_preferred_checkpoint=first_preferred_checkpoint,
            factor_count_ready=factor_inventory["factor_count_ready"],
        )
        result = {
            "schema": TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA,
            "method": TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD,
            "profile": TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID,
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "selected_manifest_sha256": selected_manifest_sha,
            "exact_spool_catalog_sha256": catalog_sha,
            "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS),
            "packet_manifest_sha256": packet_manifest_sha256,
            "packet_producer_source_sha": provenance["source_sha"],
            "pde_solve": "not_run",
            "qep_calls": 0,
            "exact_output_vectors_loaded": 0,
            "interface_packet_raw": {
                "packet_consumer": True,
                "producer_source_sha": provenance["source_sha"],
                "packet_manifest_sha256": packet_manifest_sha256,
                "packet_provenance": provenance,
                "basis_global_replicated": False,
                "fe_numeric_allgather": False,
                "groups": remap_reports,
                "remap_pass": all(item["pass"] for item in remap_reports),
                "factor_inventory": factor_inventory,
                "one_apply": one_apply,
                "fgmres_screen": screen,
                "first_preferred_checkpoint": first_preferred_checkpoint,
                "lifecycle": {
                    "factor_count_ready": 3,
                    "exact_interface_oracle_factor_count": 0,
                    "simultaneous_factor_count_max": 3,
                },
                "source_loading": {
                    "labels": list(TASK040_LEVEL_A_SOURCE_LABELS),
                    "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS),
                    "exact_output_vectors_loaded": 0,
                    "exact_output_metadata_hash_validation_only": True,
                },
                "forbidden_routes": [
                    "exact_interface_oracle",
                    "qep",
                    "pde_solve",
                    "outer_ksp",
                    "recovery",
                    "top",
                    "full_hybrid",
                    "response_packet",
                    "exact_output_vector_load",
                    "global_direct_factor",
                    "full_side_factor",
                ],
                "projected_diagnostics": dict(projected_diagnostics),
            },
        }
        owner_transferred = True
        return {"action": action, "owner": owner, "result": result}
    finally:
        for vector in source_vectors.values():
            vector.destroy()
        if not owner_transferred:
            if owner is not None:
                owner.destroy()
            elif action is not None:
                action.destroy()
        packet_layouts = None
        gamma_factors.clear()


def run_task040_level_a(
    cfg: Any,
    profile: Any,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    exact_spool_root: str | Path,
    source_sha: str,
    input_sha256: str | None = None,
    physical_model_sha256: str | None = None,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    side_system_builder: Callable[..., Any] | None = None,
    scalar_krylov: bool = False,
    interface_schur: bool = False,
    packet_producer: bool = False,
    packet_consumer: bool = False,
    packet_root: str | Path | None = None,
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the six-source Level-A audit; all numerical work stays in src."""

    if (
        sum(
            bool(value)
            for value in (
                scalar_krylov,
                interface_schur,
                packet_producer,
                packet_consumer,
            )
        )
        > 1
    ):
        raise ValueError("Task040 research routes are mutually exclusive")
    if interface_schur or packet_producer or packet_consumer:
        if packet_consumer and packet_root is None:
            raise ValueError("V2 packet consumer requires packet_root")
        for name, value in (
            ("input_sha256", input_sha256),
            ("physical_model_sha256", physical_model_sha256),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"Task040 V1-2 requires a real 64-character {name}")
    system = None
    components = None
    action = None
    owner = None
    source_vectors: dict[str, PETSc.Vec] = {}
    supports: list[dict[str, Any]] = []
    masses: list[Any] = []
    result: dict[str, Any] | None = None
    cleanup: dict[str, Any] = {}
    _emit(
        marker_callback,
        "construction_begin",
        method=(
            TASK040_V2_INTERFACE_PACKET_METHOD
            if packet_producer
            else TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD
            if packet_consumer
            else TASK040_V1_2_METHOD
            if interface_schur
            else TASK040_LEVEL_A_METHOD
        ),
    )
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
        if packet_consumer:
            route = _run_v2_packet_consumer(
                system=system,
                bare_f=bare_f,
                source_sha=source_sha,
                input_sha256=str(input_sha256),
                physical_model_sha256=str(physical_model_sha256),
                group_rows=group_rows,
                group_audit=group_audit,
                supports=supports,
                masses=masses,
                exact_spool_root=exact_spool_root,
                beta=beta,
                packet_root=packet_root,
                marker_callback=marker_callback,
                resource_callback=resource_callback,
                comm=comm,
            )
            action = route["action"]
            owner = route["owner"]
            result = route["result"]
            return result
        if interface_schur or packet_producer:
            route = _run_v1_2_interface_schur(
                cfg=cfg,
                system=system,
                bare_f=bare_f,
                source_sha=source_sha,
                input_sha256=str(input_sha256),
                physical_model_sha256=str(physical_model_sha256),
                group_rows=group_rows,
                group_audit=group_audit,
                supports=supports,
                masses=masses,
                exact_spool_root=exact_spool_root,
                beta=beta,
                marker_callback=marker_callback,
                resource_callback=resource_callback,
                producer_mode=packet_producer,
                packet_root=packet_root,
                comm=comm,
            )
            action = route["action"]
            owner = route["owner"]
            result = route["result"]
            return result
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
            owner = None
            action = None
        elif action is not None:
            action.destroy()
            action = None
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
            if interface_schur or packet_producer or packet_consumer:
                raw = result.get(
                    "interface_schur_raw"
                    if not packet_consumer
                    else "interface_packet_raw"
                )
                if isinstance(raw, dict):
                    lifecycle = raw.setdefault("lifecycle", {})
                    lifecycle["worker_cleanup"] = cleanup
                    factor_owner = cleanup.get("factor_owner")
                    after_owner = (
                        factor_owner.get("after", {})
                        if isinstance(factor_owner, dict)
                        else {}
                    )
                    lifecycle["action_destroyed"] = action is None
                    lifecycle["factor_destroyed"] = bool(
                        not factor_owner or after_owner.get("destroyed") is True
                    )
                    if packet_consumer:
                        lifecycle["factor_count_after_cleanup"] = after_owner.get(
                            "factor_count_after_cleanup"
                        )
                        lifecycle["projected_inverse_count_after_cleanup"] = (
                            after_owner.get("auxiliary_owner_count")
                        )
    if result is None:
        raise RuntimeError("Task040 Level-A did not produce a result")
    return result


def _load_cfg(input_path: str | Path) -> tuple[Any, Any, str, str]:
    spec = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(spec.as_jsonable())
    profile = make_task039_hybrid_iterative_profile(480, 8, mesh_target_nm=4.0)
    return cfg, profile, spec.input_sha256, spec.physical_model_sha256


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--input", required=True)
    parser.add_argument("--exact-spool-root", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(TASK040_V1_1_SCALAR_KRYLOV_FLAG, action="store_true")
    parser.add_argument(TASK040_V1_2_INTERFACE_SCHUR_FLAG, action="store_true")
    parser.add_argument(TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG, action="store_true")
    parser.add_argument(TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG, action="store_true")
    parser.add_argument("--interface-packet-root")
    parser.add_argument("--memory-stages")
    parser.add_argument("--memory-markers")
    args = parser.parse_args(argv)
    plan = build_task040_level_a_plan(
        input_path=args.input,
        exact_spool_root=args.exact_spool_root,
        run_directory=args.run_directory,
        source_sha=args.source_sha,
        scalar_krylov=args.v1_1_scalar_krylov,
        interface_schur=args.v1_2_interface_schur,
        packet_producer=args.v2_interface_packet_producer,
        packet_consumer=args.v2_interface_packet_consumer,
        interface_packet_root=args.interface_packet_root,
    )
    if args.dry_run:
        if MPI.COMM_WORLD.rank == 0:
            print(json.dumps(plan, sort_keys=True))
        return 0
    cfg, profile, input_sha256, physical_model_sha256 = _load_cfg(args.input)
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
        input_sha256=input_sha256,
        physical_model_sha256=physical_model_sha256,
        marker_callback=marker_callback,
        scalar_krylov=args.v1_1_scalar_krylov,
        interface_schur=args.v1_2_interface_schur,
        packet_producer=args.v2_interface_packet_producer,
        packet_consumer=args.v2_interface_packet_consumer,
        resource_callback=(
            lambda: (
                _worker_current_resource(
                    MPI.COMM_WORLD,
                    hard_limit_bytes=(
                        TASK040_V2_INTERFACE_PACKET_HARD_STOP_BYTES
                        if args.v2_interface_packet_producer
                        else TASK040_LEVEL_A_HARD_STOP_BYTES
                    ),
                )
                if (
                    args.v1_1_scalar_krylov
                    or args.v1_2_interface_schur
                    or args.v2_interface_packet_producer
                    or args.v2_interface_packet_consumer
                )
                else None
            )
        ),
        packet_root=(
            Path(args.run_directory) / "interface_packet"
            if args.v2_interface_packet_producer
            else args.interface_packet_root
            if args.v2_interface_packet_consumer
            else None
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
