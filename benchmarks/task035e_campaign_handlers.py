#!/usr/bin/env python3
"""Repository-owned formal stage handlers for the Task035e campaign.

The crash-resumable campaign core deliberately knows nothing about numerical
producers.  This module is the closed adapter that connects every campaign
stage to the existing Task035e producer APIs and to the sole qualified heavy
entrypoint, :mod:`benchmarks.run_task033_full3d_watchdog`.

No handler invokes a shell.  Every generated artifact lives below the current
immutable attempt directory.  A missing producer field or an unsupported
evidence transition is published as a machine-readable controlled-negative
blocker; it is never replaced by a placeholder ``completed`` receipt.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence

from benchmarks.task035e_blind_campaign import (
    AttemptHandle,
    BlindCampaignError,
    BlindCampaignIdentity,
    BlindPathIdentity,
    CampaignEvidenceError,
    CommandExecutionReceipt,
    PreparedStage,
    StageArtifactBinding,
    StageExecutionContext,
    StageResult,
    WatchdogLaunchSpec,
    build_watchdog_argv,
    initialize_campaign,
    run_campaign,
)
from benchmarks.task035e_campaign_stages import (
    ContractStagePreparer,
    FormalStageHandler,
    campaign_final_stage_handlers,
)


ROOT = Path(__file__).resolve().parents[1]
HANDLER_SCHEMA = "task035e.repository-formal-campaign-handlers.v1"
TARGET_CATALOG_SCHEMA = "task035e.shadow-discovery-target-catalog.v2"
LEGAL_SKIP_SCHEMA = "task035e.formal-stage-legal-skip.v1"
BLOCKER_SCHEMA = "task035e.formal-stage-blocker.v1"
TRANSITION_MODE_SCHEMA = "task035e.cross-cycle-transition-mode.v1"
SELECTION_SCHEMA = "task035e.cycle-action-selection.v1"
FREEZE_INTENT_SCHEMA = "task035e.cycle-freeze-intent.v1"
FORMAL_MPI_SIZE = 8
FINAL_PROBE_CYCLE = 5

_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_PROTECTED_PARTS = frozenset(
    {
        "reference_" + "certifier",
        "hidden_" + "auditor",
        "sealed_" + "reference",
        "golden_" + "reference",
    }
)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_file(
    path: Path,
    *,
    label: str,
    expected_sha256: str | None = None,
) -> Path:
    raw = Path(path).expanduser()
    if raw.is_symlink():
        raise CampaignEvidenceError(f"{label} must not be a symlink")
    resolved = raw.resolve()
    if {part.lower() for part in resolved.parts}.intersection(
        _PROTECTED_PARTS
    ):
        raise CampaignEvidenceError(f"{label} crosses a protected layer")
    try:
        metadata = resolved.stat()
    except OSError as exc:
        raise CampaignEvidenceError(f"{label} is absent") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise CampaignEvidenceError(
            f"{label} must be a mode-0600 regular file"
        )
    observed = _file_sha256(resolved)
    if expected_sha256 is not None and observed != expected_sha256:
        raise CampaignEvidenceError(f"{label} SHA-256 differs")
    return resolved


def _strict_json(
    binding: StageArtifactBinding,
    *,
    label: str,
) -> Mapping[str, Any]:
    path = _safe_file(
        binding.path,
        label=label,
        expected_sha256=binding.sha256,
    )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignEvidenceError(f"{label} is not strict JSON") from exc
    if not isinstance(value, Mapping):
        raise CampaignEvidenceError(f"{label} must be one JSON object")
    return value


def _artifact(
    role: str,
    path: Path,
) -> StageArtifactBinding:
    return StageArtifactBinding.from_file(role, path)


def _command_hashes(
    receipts: Sequence[CommandExecutionReceipt],
) -> tuple[str, ...]:
    return tuple(receipt.receipt_file_sha256 for receipt in receipts)


def _completed(
    context: StageExecutionContext,
    *,
    classification: str,
    paths: Mapping[str, Path],
    receipts: Sequence[CommandExecutionReceipt] = (),
    next_plan_sha256: str | None = None,
    lane_decision: str = "continue",
    freeze_requested: bool = False,
    p6_saturation: str = "not_applicable",
    h_level3_saturation: str = "not_applicable",
) -> StageResult:
    return StageResult(
        status="completed",
        classification=classification,
        input_plan_sha256=context.input_plan_sha256,
        artifacts=tuple(
            _artifact(role, paths[role]) for role in sorted(paths)
        ),
        command_receipt_file_sha256s=_command_hashes(receipts),
        next_plan_sha256=next_plan_sha256,
        lane_decision=lane_decision,
        freeze_requested=freeze_requested,
        p6_saturation=p6_saturation,
        h_level3_saturation=h_level3_saturation,
    )


def _blocker_result(
    context: StageExecutionContext,
    attempt: AttemptHandle,
    *,
    code: str,
    message: str,
    inputs: Mapping[str, Any] | None = None,
    receipts: Sequence[CommandExecutionReceipt] = (),
) -> StageResult:
    unsigned: dict[str, Any] = {
        "schema_version": BLOCKER_SCHEMA,
        "status": "controlled_negative",
        "pass": False,
        "stage_id": context.stage.stage_id,
        "stage_name": context.stage.stage_name,
        "path_id": context.stage.path_id,
        "cycle_index": context.stage.cycle_index,
        "source_sha": context.source_sha,
        "input_plan_sha256": context.input_plan_sha256,
        "code": str(code),
        "message": str(message),
        "inputs": {} if inputs is None else dict(inputs),
        "accuracy_credit": False,
        "ordinary_default_changed": False,
    }
    payload = {**unsigned, "blocker_sha256": _json_sha256(unsigned)}
    path = attempt.write_artifact("stage-blocker.json", payload)
    return StageResult(
        status="controlled_negative",
        classification="formal_stage_blocker",
        input_plan_sha256=context.input_plan_sha256,
        artifacts=(_artifact("stage_blocker", path),),
        command_receipt_file_sha256s=_command_hashes(receipts),
        lane_decision="controlled_negative",
    )


def _blocker_prepared(
    context: StageExecutionContext,
    *,
    code: str,
    message: str,
    inputs: Mapping[str, Any] | None = None,
) -> PreparedStage:
    def execute(
        attempt: AttemptHandle,
        receipts: tuple[CommandExecutionReceipt, ...],
    ) -> StageResult:
        return _blocker_result(
            context,
            attempt,
            code=code,
            message=message,
            inputs=inputs,
            receipts=receipts,
        )

    return PreparedStage(execute=execute)


def _skip_payload(
    context: StageExecutionContext,
    *,
    lane: str,
    reason: str,
    role: str,
) -> Mapping[str, Any]:
    unsigned = {
        "schema_version": LEGAL_SKIP_SCHEMA,
        "status": "legal_no_target_skip",
        "pass": True,
        "stage_id": context.stage.stage_id,
        "path_id": context.stage.path_id,
        "cycle_index": context.stage.cycle_index,
        "lane": lane,
        "reason": reason,
        "artifact_role": role,
        "source_sha": context.source_sha,
        "input_plan_sha256": context.input_plan_sha256,
        "pde_executed": False,
        "accuracy_credit": False,
        "ordinary_default_changed": False,
    }
    return {**unsigned, "skip_sha256": _json_sha256(unsigned)}


def _write_skips(
    context: StageExecutionContext,
    attempt: AttemptHandle,
    *,
    lane: str,
    reason: str,
    roles: Sequence[str],
) -> dict[str, Path]:
    return {
        role: attempt.write_artifact(
            f"{role}.json",
            _skip_payload(
                context,
                lane=lane,
                reason=reason,
                role=role,
            ),
        )
        for role in roles
    }


def _is_skip(binding: StageArtifactBinding) -> bool:
    value = _strict_json(binding, label=f"{binding.role} artifact")
    return (
        value.get("schema_version") == LEGAL_SKIP_SCHEMA
        and value.get("status") == "legal_no_target_skip"
        and value.get("pass") is True
    )


def _copy_private(
    attempt: AttemptHandle,
    *,
    name: str,
    binding: StageArtifactBinding,
) -> Path:
    source = _safe_file(
        binding.path,
        label=binding.role,
        expected_sha256=binding.sha256,
    )
    return attempt.write_artifact(name, source.read_bytes())


@dataclass(frozen=True, slots=True)
class FormalCampaignSettings:
    """Fixed runtime locations and narrow final-probe policy."""

    python_executable: Path
    artifact_root: Path
    tensor_cache_directory: Path
    timeout_seconds: float = 43200.0

    def __post_init__(self) -> None:
        python = Path(self.python_executable).expanduser()
        if not python.is_absolute():
            raise BlindCampaignError("python_executable must be absolute")
        rendered_python = python.as_posix()
        if rendered_python == "/mnt" or rendered_python.startswith("/mnt/"):
            raise BlindCampaignError(
                "python_executable must use the Linux filesystem"
            )
        if not python.is_file():
            raise BlindCampaignError("python_executable is missing")
        # Preserve the qualified venv entrypoint.  Path.resolve() would follow
        # its intentional symlink to /usr/bin/python and silently drop the
        # repository activation/ABI identity.
        object.__setattr__(
            self,
            "python_executable",
            Path(os.path.abspath(str(python))),
        )
        for name in ("artifact_root", "tensor_cache_directory"):
            path = Path(getattr(self, name)).expanduser()
            if not path.is_absolute():
                raise BlindCampaignError(f"{name} must be absolute")
            rendered = path.as_posix()
            if rendered == "/mnt" or rendered.startswith("/mnt/"):
                raise BlindCampaignError(f"{name} must use the Linux filesystem")
            object.__setattr__(self, name, path.resolve())
        if (
            not math.isfinite(float(self.timeout_seconds))
            or float(self.timeout_seconds) <= 0.0
        ):
            raise BlindCampaignError("timeout_seconds must be positive")


def _watchdog_spec(
    settings: FormalCampaignSettings,
    context: StageExecutionContext,
    attempt: AttemptHandle,
    *,
    output_role: str,
    plan: StageArtifactBinding,
    record_name: str,
    run_name: str,
    snapshot: StageArtifactBinding | None = None,
    transition: StageArtifactBinding | None = None,
    internal_probe_kind: str | None = None,
    mpi_size: int = FORMAL_MPI_SIZE,
    probe_dtn_max_m: int | None = None,
    probe_dtn_max_n: int | None = None,
    probe_surface_quadrature_degree: int | None = None,
) -> tuple[str, ...]:
    return build_watchdog_argv(
        WatchdogLaunchSpec(
            python_executable=settings.python_executable,
            source_sha=context.source_sha,
            path_id=context.stage.path_id,
            nominal_h_nm=context.nominal_h_nm,
            trial_id=context.trial_id,
            cycle_index=context.stage.cycle_index,
            output_role=output_role,
            plan_path=plan.path,
            plan_sha256=plan.sha256,
            artifact_root=settings.artifact_root,
            tensor_cache_directory=settings.tensor_cache_directory,
            run_dir=attempt.attempt_dir / run_name,
            record_path=attempt.attempt_dir / record_name,
            mpi_size=mpi_size,
            current_snapshot_path=(
                None if snapshot is None else snapshot.path
            ),
            current_snapshot_sha256=(
                None if snapshot is None else snapshot.sha256
            ),
            transition_action_path=(
                None if transition is None else transition.path
            ),
            transition_action_sha256=(
                None if transition is None else transition.sha256
            ),
            internal_probe_kind=internal_probe_kind,
            probe_dtn_max_m=probe_dtn_max_m,
            probe_dtn_max_n=probe_dtn_max_n,
            probe_surface_quadrature_degree=(
                probe_surface_quadrature_degree
            ),
            final_internal_gate=internal_probe_kind is not None,
            timeout_seconds=settings.timeout_seconds,
        )
    )


def _record_binding(
    receipt: CommandExecutionReceipt,
    *,
    role: str,
) -> StageArtifactBinding:
    if receipt.watchdog_record_path is None:
        raise CampaignEvidenceError("command has no watchdog record")
    return _artifact(role, receipt.watchdog_record_path)


def _controlled_resource_stop(
    context: StageExecutionContext,
    attempt: AttemptHandle,
    *,
    receipt: CommandExecutionReceipt,
    plan: StageArtifactBinding,
    output_role: str,
) -> StageResult | None:
    """Turn only a fully bound 11 GiB watchdog stop into lane evidence."""

    if receipt.exit_code == 0:
        return None
    record = _record_binding(receipt, role="controlled_resource_watchdog")
    if (
        receipt.exit_code != 2
        or receipt.watchdog_record_sha256 != record.sha256
    ):
        raise CampaignEvidenceError(
            "nonzero watchdog is not a hash-bound controlled resource stop"
        )
    payload = _strict_json(record, label="controlled-resource watchdog")
    source = payload.get("source")
    source = source if isinstance(source, Mapping) else {}
    launch = payload.get("task035e_blind_candidate_launch_gate")
    launch = launch if isinstance(launch, Mapping) else {}
    launch_plan = launch.get("plan")
    launch_plan = (
        launch_plan if isinstance(launch_plan, Mapping) else {}
    )
    live = launch.get("live_resource_gate")
    live = live if isinstance(live, Mapping) else {}
    policy = payload.get("resource_policy")
    policy = policy if isinstance(policy, Mapping) else {}
    authority = payload.get("resource_authority")
    authority = authority if isinstance(authority, Mapping) else {}
    memory_gib = authority.get("combined_memory_swap_authority_gib")
    checks = (
        payload.get("status") == "controlled_resource_stop",
        payload.get("controlled_resource_stop") is True,
        payload.get("terminated_for_memory") is True,
        payload.get("terminated_for_timeout") is False,
        payload.get("terminated_for_authority_unreadable") is False,
        payload.get("controlled_resource_stop_reason")
        == "effective_job_cap_reached",
        payload.get("no_swap") is True,
        payload.get("task035e_blind_candidate") is None,
        source.get("commit_sha") == context.source_sha,
        source.get("head_after_sha") == context.source_sha,
        source.get("stable_and_clean_after") is True,
        source.get("tracked_source_dirty") is False,
        launch.get("selected") is True,
        launch_plan.get("pass") is True,
        launch_plan.get("observed_file_sha256") == plan.sha256,
        live.get("controlled_resource_stop") is True,
        live.get("zero_swap_every_sample") is True,
        live.get("effective_job_cap_respected") is False,
        live.get("stop_reason") == "effective_job_cap_reached",
        policy.get("termination_gib") == 11.0,
        isinstance(memory_gib, (int, float)),
        (
            isinstance(memory_gib, (int, float))
            and float(memory_gib) >= 11.0
        ),
    )
    if not all(checks):
        raise CampaignEvidenceError(
            "nonzero watchdog failed the controlled-resource-stop contract"
        )
    return _blocker_result(
        context,
        attempt,
        code=f"{output_role}_controlled_resource_stop",
        message=(
            f"{output_role} reached the formal 11 GiB cap before a "
            "qualified field was available"
        ),
        inputs={
            "watchdog_record_sha256": record.sha256,
            "output_role": output_role,
            "plan_file_sha256": plan.sha256,
            "combined_memory_swap_authority_gib": float(memory_gib),
            "no_swap": True,
            "stop_reason": "effective_job_cap_reached",
            "accuracy_credit": False,
        },
        receipts=(receipt,),
    )


def _candidate_and_live_paths(
    record: StageArtifactBinding,
    *,
    output_role: str,
) -> tuple[Any, Path]:
    from benchmarks.task035e_candidate_output import (
        CandidateWatchdogInput,
        adapt_candidate_output,
    )

    adapted = adapt_candidate_output(
        CandidateWatchdogInput(record.path, record.sha256),
        output_role=output_role,
    )
    run_dir = record.path.parent / (
        "run-current"
        if output_role == "current"
        else f"run-{output_role}"
    )
    # The watchdog record itself is authoritative about its run directory.
    raw = _strict_json(record, label=f"{output_role} watchdog record")
    evidence = raw.get("raw_evidence")
    if isinstance(evidence, Mapping):
        raw_run = evidence.get("run_directory")
        if isinstance(raw_run, str) and raw_run:
            candidate = Path(raw_run)
            run_dir = (
                candidate
                if candidate.is_absolute()
                else ROOT / candidate
            ).resolve()
    live = (
        run_dir / "task035e_current_snapshot" / "manifest.json"
        if output_role == "current"
        else run_dir
        / f"task035e_{output_role.replace('-', '_')}_evaluation.json"
    )
    return adapted, live


def _validate_candidate_context(
    adapted: Any,
    *,
    context: StageExecutionContext,
    plan: StageArtifactBinding,
    output_role: str,
) -> None:
    expected_role = {
        "current": "blind_current_solve",
        "p-shadow": "blind_p_shadow_solve",
        "h-shadow": "blind_h_shadow_solve",
    }[output_role]
    if (
        adapted.source_sha != context.source_sha
        or adapted.trial_id != context.trial_id
        or adapted.cycle_index != context.stage.cycle_index
        or adapted.output_role != expected_role
        or adapted.plan_file_sha256 != plan.sha256
    ):
        raise CampaignEvidenceError(
            f"{output_role} candidate identity differs from its stage context"
        )


class RepositoryFormalStageHandlers:
    """Build the complete repository-owned formal handler inventory."""

    def __init__(self, settings: FormalCampaignSettings) -> None:
        self.settings = settings

    def mapping(self) -> Mapping[str, FormalStageHandler]:
        handlers: dict[str, FormalStageHandler] = {
            "initial_plan": self.initial_plan,
            "current_solve": self.current_solve,
            "shadow_target_discovery": self.shadow_target_discovery,
            "p_shadow_discovery": self.p_shadow_discovery,
            "h_shadow_discovery": self.h_shadow_discovery,
            "cellwise_partition": self.cellwise_partition,
            "goal_marking": self.goal_marking,
            "p_selected_shadow_verification": (
                self.p_selected_shadow_verification
            ),
            "h_selected_shadow_verification": (
                self.h_selected_shadow_verification
            ),
            "shadow_bundle": self.shadow_bundle,
            "internal_gate_deferred_or_final": (
                self.internal_gate_deferred_or_final
            ),
            "isolation_audit": self.isolation_audit,
            "cycle_binding": self.cycle_binding,
            "cycle_advance": self.cycle_advance,
            "transition_or_pkeep": self.transition_or_pkeep,
        }
        handlers.update(campaign_final_stage_handlers())
        return handlers

    def preparer(self) -> ContractStagePreparer:
        return ContractStagePreparer(self.mapping())

    def initial_plan(
        self,
        context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        def execute(
            attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if receipts:
                raise CampaignEvidenceError(
                    "initial metadata stage must be light"
                )
            from benchmarks.task035e_trial_metadata import (
                write_trial_metadata,
            )

            output = attempt.attempt_dir / "trial-metadata.json"
            written = write_trial_metadata(
                output,
                initial_plan_path=context.artifact("current_plan").path,
                initial_space_authority_path=context.artifact(
                    "initial_space_authority"
                ).path,
                qualified_solver_config_path=context.artifact(
                    "qualified_solver_config"
                ).path,
            )
            if (
                written.source_sha != context.source_sha
                or written.trial_id != context.trial_id
            ):
                raise CampaignEvidenceError(
                    "trial metadata identity differs from campaign context"
                )
            return _completed(
                context,
                classification="trial_metadata_qualified",
                paths={"trial_metadata": output},
            )

        return PreparedStage(execute=execute)


    def current_solve(
        self,
        context: StageExecutionContext,
        attempt: AttemptHandle,
    ) -> PreparedStage:
        cycle = context.stage.cycle_index
        plan = context.artifact("current_plan")
        snapshot = (
            None
            if cycle == 0
            else context.artifact("current_snapshot")
        )
        transition = (
            None
            if cycle == 0
            else context.artifact("next_transition_action")
        )
        argv = _watchdog_spec(
            self.settings,
            context,
            attempt,
            output_role="current",
            plan=plan,
            record_name="current-watchdog.json",
            run_name="run-current",
            snapshot=snapshot,
            transition=transition,
        )

        def execute(
            checked_attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if len(receipts) != 1:
                raise CampaignEvidenceError(
                    "current solve requires one watchdog receipt"
                )
            stopped = _controlled_resource_stop(
                context,
                checked_attempt,
                receipt=receipts[0],
                plan=plan,
                output_role="current",
            )
            if stopped is not None:
                return stopped
            from benchmarks.task035e_candidate_output import (
                write_candidate_output,
            )

            record = _record_binding(
                receipts[0],
                role="current_watchdog_record",
            )
            adapted, snapshot_path = _candidate_and_live_paths(
                record,
                output_role="current",
            )
            _validate_candidate_context(
                adapted,
                context=context,
                plan=plan,
                output_role="current",
            )
            output = checked_attempt.attempt_dir / "current-candidate.json"
            write_candidate_output(output, adapted)
            snapshot_path = _safe_file(
                snapshot_path,
                label="current live snapshot",
            )
            return _completed(
                context,
                classification="current_candidate_solve_pass",
                paths={
                    "current_watchdog_record": record.path,
                    "current_candidate_output": output,
                    "current_snapshot": snapshot_path,
                },
                receipts=receipts,
            )

        return PreparedStage(
            execute=execute,
            argv=argv,
            allow_controlled_resource_stop=True,
        )

    def shadow_target_discovery(
        self,
        context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        def execute(
            attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if receipts:
                raise CampaignEvidenceError(
                    "target discovery must not execute a PDE"
                )
            from src.adaptivity.task035e_hp_transition import (
                canonical_hp_cell_target_id,
                close_p_up_degree_jump_targets,
            )
            from src.adaptivity.task035e_local_shadows import (
                build_local_shadow_catalog,
            )
            from src.adaptivity.task035e_plan_transition import (
                rebuild_hp_transition_state_from_solver_plan,
            )
            from src.common.config_3d import target_stage4_config
            from benchmarks.task035e_transition_producer import (
                write_transition_bundle,
            )

            plan_binding = context.artifact("current_plan")
            plan = _strict_json(plan_binding, label="current solver plan")
            state = rebuild_hp_transition_state_from_solver_plan(
                target_stage4_config(
                    degree=6,
                    h_nm=context.nominal_h_nm,
                ),
                current_plan=plan,
                comm_size=FORMAL_MPI_SIZE,
            )
            if (
                state.source_sha != context.source_sha
                or state.cycle_index != context.stage.cycle_index
            ):
                raise CampaignEvidenceError(
                    "replayed target catalog identity differs"
                )
            ids = {
                "p": tuple(
                    canonical_hp_cell_target_id(key)
                    for key in sorted(
                        key
                        for key, degree in state.cell_degree_by_key.items()
                        if int(degree) < 6
                    )
                ),
                "h": tuple(
                    canonical_hp_cell_target_id(key)
                    for key in sorted(
                        cell.key
                        for cell in state.forest.leaves
                        if int(cell.key.level) < 2
                    )
                ),
            }
            paths: dict[str, Path] = {}
            for lane, kind in (("p", "p-up"), ("h", "h-refine")):
                targets_role = f"{lane}_discovery_targets"
                action_role = f"{lane}_discovery_transition_action"
                plan_role = f"{lane}_discovery_plan"
                if not ids[lane]:
                    paths.update(
                        _write_skips(
                            context,
                            attempt,
                            lane=lane,
                            reason=(
                                "all_cells_are_p6"
                                if lane == "p"
                                else "all_leaves_at_maximum_level"
                            ),
                            roles=(
                                targets_role,
                                action_role,
                                plan_role,
                            ),
                        )
                    )
                    continue
                catalog = build_local_shadow_catalog(
                    ids[lane],
                    lane=lane,
                    path_id=context.stage.path_id,
                    cycle_index=int(context.stage.cycle_index),
                )
                selected_set = set(catalog.selected_target_ids)
                window_ids = tuple(
                    target_id
                    for target_id in ids[lane]
                    if target_id in selected_set
                )
                selection_audit: dict[str, Any] = {
                    "window": dict(catalog.audit),
                }
                if lane == "p":
                    key_by_id = {
                        canonical_hp_cell_target_id(key): key
                        for key in state.cell_degree_by_key
                    }
                    closed_keys, closure_audit = (
                        close_p_up_degree_jump_targets(
                            state,
                            tuple(key_by_id[value] for value in window_ids),
                        )
                    )
                    selected_ids = tuple(
                        canonical_hp_cell_target_id(key)
                        for key in closed_keys
                    )
                    selection_audit["p_degree_jump_closure"] = dict(
                        closure_audit
                    )
                else:
                    selected_ids = window_ids
                action_path = attempt.attempt_dir / f"{lane}-discovery-action.json"
                next_plan_path = (
                    attempt.attempt_dir / f"{lane}-discovery-plan.json"
                )
                transition_receipt = write_transition_bundle(
                    current_plan_path=plan_binding.path,
                    current_plan_file_sha256=plan_binding.sha256,
                    source_sha=context.source_sha,
                    action_kind=kind,
                    canonical_target_ids=selected_ids,
                    action_path=action_path,
                    next_plan_path=next_plan_path,
                )
                unsigned = {
                    "schema_version": TARGET_CATALOG_SCHEMA,
                    "status": "resource_bounded_reference_blind_catalog",
                    "pass": True,
                    "lane": lane,
                    "action_kind": kind,
                    "source_sha": context.source_sha,
                    "path_id": context.stage.path_id,
                    "cycle_index": context.stage.cycle_index,
                    "current_plan_file_sha256": plan_binding.sha256,
                    "current_state_sha256": state.state_sha256,
                    "eligible_target_count": len(ids[lane]),
                    "window_selected_target_count": len(window_ids),
                    "selected_target_count": len(selected_ids),
                    "canonical_target_ids": list(selected_ids),
                    "selection_audit": selection_audit,
                    "discovery_action_file_sha256": (
                        transition_receipt.action_file_sha256
                    ),
                    "discovery_plan_file_sha256": (
                        transition_receipt.plan_file_sha256
                    ),
                    "selection_inputs": (
                        "closed current-plan degree/level bounds plus "
                        "fixed source-independent rotating window"
                    ),
                    "solved_field_inputs_consumed": False,
                    "ordinary_default_changed": False,
                }
                target_path = attempt.write_artifact(
                    f"{lane}-discovery-targets.json",
                    {**unsigned, "catalog_sha256": _json_sha256(unsigned)},
                )
                paths.update(
                    {
                        targets_role: target_path,
                        action_role: action_path,
                        plan_role: next_plan_path,
                    }
                )
            return _completed(
                context,
                classification="complete_shadow_target_catalog",
                paths=paths,
            )

        return PreparedStage(execute=execute)

    def _discovery_shadow(
        self,
        context: StageExecutionContext,
        attempt: AttemptHandle,
        *,
        lane: str,
    ) -> PreparedStage:
        prefix = f"{lane}_shadow"
        targets = context.artifact(f"{lane}_discovery_targets")
        output_roles = (
            f"{prefix}_watchdog_record",
            f"{prefix}_candidate_output",
            f"{lane}_live_dwr_evidence",
        )
        if _is_skip(targets):
            def execute_skip(
                checked_attempt: AttemptHandle,
                receipts: tuple[CommandExecutionReceipt, ...],
            ) -> StageResult:
                if receipts:
                    raise CampaignEvidenceError(
                        "no-target discovery executed a watchdog"
                    )
                paths = _write_skips(
                    context,
                    checked_attempt,
                    lane=lane,
                    reason=(
                        "all_cells_are_p6"
                        if lane == "p"
                        else "all_leaves_at_maximum_level"
                    ),
                    roles=output_roles,
                )
                return _completed(
                    context,
                    classification="legal_no_target_skip",
                    paths=paths,
                )

            return PreparedStage(execute=execute_skip)

        action = context.artifact(
            f"{lane}_discovery_transition_action"
        )
        plan = context.artifact(f"{lane}_discovery_plan")
        output_role = f"{lane}-shadow"
        argv = _watchdog_spec(
            self.settings,
            context,
            attempt,
            output_role=output_role,
            plan=plan,
            record_name=f"{lane}-shadow-watchdog.json",
            run_name=f"run-{output_role}",
            snapshot=context.artifact("current_snapshot"),
            transition=action,
        )

        def execute(
            checked_attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if len(receipts) != 1:
                raise CampaignEvidenceError(
                    "discovery shadow requires one watchdog receipt"
                )
            stopped = _controlled_resource_stop(
                context,
                checked_attempt,
                receipt=receipts[0],
                plan=plan,
                output_role=output_role,
            )
            if stopped is not None:
                return stopped
            from benchmarks.task035e_candidate_output import (
                write_candidate_output,
            )
            from benchmarks.task035e_live_shadow_bridge import (
                BoundJSONInput,
                build_live_shadow_bridge,
                write_live_shadow_bridge,
            )

            record = _record_binding(
                receipts[0],
                role=f"{prefix}_watchdog_record",
            )
            adapted, live_path = _candidate_and_live_paths(
                record,
                output_role=output_role,
            )
            _validate_candidate_context(
                adapted,
                context=context,
                plan=plan,
                output_role=output_role,
            )
            output = (
                checked_attempt.attempt_dir
                / f"{lane}-shadow-candidate.json"
            )
            write_candidate_output(output, adapted)
            live_path = _safe_file(
                live_path,
                label=f"{lane}-shadow live DWR evidence",
            )
            current = context.artifact("current_watchdog_record")
            built = build_live_shadow_bridge(
                current_record=BoundJSONInput(
                    current.path,
                    current.sha256,
                ),
                shadow_record=BoundJSONInput(record.path, record.sha256),
                transition_action=BoundJSONInput(
                    action.path,
                    action.sha256,
                ),
                live_shadow_evidence=BoundJSONInput(
                    live_path,
                    _file_sha256(live_path),
                ),
            )
            bridge = (
                checked_attempt.attempt_dir
                / f"{lane}-live-dwr-bridge.json"
            )
            bridge_receipt = write_live_shadow_bridge(bridge, built)
            if not bridge_receipt.passed:
                return _blocker_result(
                    context,
                    checked_attempt,
                    code=f"{lane}_shadow_effectivity_failed",
                    message=bridge_receipt.classification,
                    inputs={
                        "shadow_record_sha256": record.sha256,
                        "live_bridge_sha256": (
                            bridge_receipt.file_sha256
                        ),
                    },
                    receipts=receipts,
                )
            return _completed(
                context,
                classification=f"{lane}_discovery_shadow_pass",
                paths={
                    f"{prefix}_watchdog_record": record.path,
                    f"{prefix}_candidate_output": output,
                    f"{lane}_live_dwr_evidence": bridge,
                },
                receipts=receipts,
            )

        return PreparedStage(
            execute=execute,
            argv=argv,
            allow_controlled_resource_stop=True,
        )

    def p_shadow_discovery(
        self,
        context: StageExecutionContext,
        attempt: AttemptHandle,
    ) -> PreparedStage:
        return self._discovery_shadow(context, attempt, lane="p")

    def h_shadow_discovery(
        self,
        context: StageExecutionContext,
        attempt: AttemptHandle,
    ) -> PreparedStage:
        return self._discovery_shadow(context, attempt, lane="h")

    def cellwise_partition(
        self,
        context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        def execute(
            attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if receipts:
                raise CampaignEvidenceError(
                    "cellwise partition stage must be light"
                )
            from benchmarks.task035e_cellwise_authority import (
                build_cellwise_authority,
                write_cellwise_authority,
            )

            current_record = context.artifact("current_watchdog_record")
            current_output = context.artifact("current_candidate_output")
            paths: dict[str, Path] = {}
            for lane, kind in (("p", "p-up"), ("h", "h-refine")):
                output_role = f"{lane}_cellwise_authority"
                live = context.artifact(f"{lane}_live_dwr_evidence")
                if _is_skip(live):
                    paths.update(
                        _write_skips(
                            context,
                            attempt,
                            lane=lane,
                            reason=(
                                "all_cells_are_p6"
                                if lane == "p"
                                else "all_leaves_at_maximum_level"
                            ),
                            roles=(output_role,),
                        )
                    )
                    continue
                shadow_record = context.artifact(
                    f"{lane}_shadow_watchdog_record"
                )
                shadow_output = context.artifact(
                    f"{lane}_shadow_candidate_output"
                )
                payload = build_cellwise_authority(
                    current_record_path=current_record.path,
                    current_record_file_sha256=current_record.sha256,
                    shadow_record_path=shadow_record.path,
                    shadow_record_file_sha256=shadow_record.sha256,
                    current_output_path=current_output.path,
                    current_output_file_sha256=current_output.sha256,
                    shadow_output_path=shadow_output.path,
                    shadow_output_file_sha256=shadow_output.sha256,
                    live_shadow_evidence_path=live.path,
                    live_shadow_evidence_file_sha256=live.sha256,
                    source_sha=context.source_sha,
                    action_kind=kind,
                )
                output = (
                    attempt.attempt_dir
                    / f"{lane}-cellwise-authority.json"
                )
                written = write_cellwise_authority(output, payload)
                if payload.get("pass") is not True:
                    return _blocker_result(
                        context,
                        attempt,
                        code=f"{lane}_cellwise_authority_failed",
                        message=written.classification,
                        inputs={
                            "authority_file_sha256": (
                                written.file_sha256
                            )
                        },
                    )
                paths[output_role] = output
            return _completed(
                context,
                classification="cellwise_shadow_partition_pass",
                paths=paths,
            )

        return PreparedStage(execute=execute)

    def goal_marking(
        self,
        context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        def execute(
            attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if receipts:
                raise CampaignEvidenceError(
                    "goal marking stage must be light"
                )
            from benchmarks.task035e_blind_bindings import (
                write_verification_prediction,
            )
            from benchmarks.task035e_goal_marking import (
                produce_goal_marking,
            )
            from benchmarks.task035e_transition_producer import (
                write_transition_bundle,
            )

            current_plan = context.artifact("current_plan")
            paths: dict[str, Path] = {}
            for lane, kind in (("p", "p-up"), ("h", "h-refine")):
                roles = {
                    "marking": f"{lane}_goal_marking",
                    "action": f"{lane}_selected_transition_action",
                    "plan": f"{lane}_selected_plan",
                    "prediction": f"{lane}_verification_prediction",
                }
                authority = context.artifact(
                    f"{lane}_cellwise_authority"
                )
                if _is_skip(authority):
                    paths.update(
                        _write_skips(
                            context,
                            attempt,
                            lane=lane,
                            reason=(
                                "all_cells_are_p6"
                                if lane == "p"
                                else "all_leaves_at_maximum_level"
                            ),
                            roles=tuple(roles.values()),
                        )
                    )
                    continue
                marking_path = (
                    attempt.attempt_dir / f"{lane}-goal-marking.json"
                )
                marking = produce_goal_marking(
                    current_plan_path=current_plan.path,
                    current_plan_file_sha256=current_plan.sha256,
                    dwr_authority_path=authority.path,
                    dwr_authority_file_sha256=authority.sha256,
                    source_sha=context.source_sha,
                    action_kind=kind,
                    output_path=marking_path,
                )
                if not marking.canonical_target_ids:
                    return _blocker_result(
                        context,
                        attempt,
                        code=f"{lane}_goal_marking_no_verification_target",
                        message=(
                            "goal marking produced neither a production "
                            "candidate nor a deterministic verification-only "
                            "fallback"
                        ),
                        inputs={
                            "marking_status": marking.status,
                            "marking_classification": (
                                marking.classification
                            ),
                            "marking_file_sha256": marking.file_sha256,
                        },
                    )
                action_path = (
                    attempt.attempt_dir
                    / f"{lane}-selected-transition-action.json"
                )
                selected_plan_path = (
                    attempt.attempt_dir / f"{lane}-selected-plan.json"
                )
                write_transition_bundle(
                    current_plan_path=current_plan.path,
                    current_plan_file_sha256=current_plan.sha256,
                    source_sha=context.source_sha,
                    action_kind=kind,
                    canonical_target_ids=marking.canonical_target_ids,
                    action_path=action_path,
                    next_plan_path=selected_plan_path,
                )
                prediction_path = (
                    attempt.attempt_dir
                    / f"{lane}-verification-prediction.json"
                )
                write_verification_prediction(
                    prediction_path,
                    goal_marking_path=marking_path,
                    transition_action_path=action_path,
                )
                paths.update(
                    {
                        roles["marking"]: marking_path,
                        roles["action"]: action_path,
                        roles["plan"]: selected_plan_path,
                        roles["prediction"]: prediction_path,
                    }
                )
            return _completed(
                context,
                classification="goal_marking_and_verification_plan_pass",
                paths=paths,
            )

        return PreparedStage(execute=execute)

    def _selected_shadow_verification(
        self,
        context: StageExecutionContext,
        attempt: AttemptHandle,
        *,
        lane: str,
    ) -> PreparedStage:
        action = context.artifact(f"{lane}_selected_transition_action")
        output_roles = (
            f"{lane}_selected_shadow_watchdog_record",
            f"{lane}_selected_shadow_candidate_output",
            f"{lane}_selected_live_dwr_evidence",
        )
        if _is_skip(action):
            def execute_skip(
                checked_attempt: AttemptHandle,
                receipts: tuple[CommandExecutionReceipt, ...],
            ) -> StageResult:
                if receipts:
                    raise CampaignEvidenceError(
                        "no-action verification executed a watchdog"
                    )
                return _completed(
                    context,
                    classification="legal_no_selected_action_skip",
                    paths=_write_skips(
                        context,
                        checked_attempt,
                        lane=lane,
                        reason=(
                            "all_cells_are_p6"
                            if lane == "p"
                            else "all_leaves_at_maximum_level"
                        ),
                        roles=output_roles,
                    ),
                )

            return PreparedStage(execute=execute_skip)

        plan = context.artifact(f"{lane}_selected_plan")
        output_role = f"{lane}-shadow"
        argv = _watchdog_spec(
            self.settings,
            context,
            attempt,
            output_role=output_role,
            plan=plan,
            record_name=f"{lane}-selected-watchdog.json",
            run_name=f"run-{output_role}",
            snapshot=context.artifact("current_snapshot"),
            transition=action,
        )

        def execute(
            checked_attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if len(receipts) != 1:
                raise CampaignEvidenceError(
                    "selected verification requires one watchdog receipt"
                )
            stopped = _controlled_resource_stop(
                context,
                checked_attempt,
                receipt=receipts[0],
                plan=plan,
                output_role=f"{output_role}-selected",
            )
            if stopped is not None:
                return stopped
            from benchmarks.task035e_candidate_output import (
                write_candidate_output,
            )
            from benchmarks.task035e_live_shadow_bridge import (
                BoundJSONInput,
                build_live_shadow_bridge,
                write_live_shadow_bridge,
            )

            record = _record_binding(
                receipts[0],
                role=f"{lane}_selected_shadow_watchdog_record",
            )
            adapted, live_path = _candidate_and_live_paths(
                record,
                output_role=output_role,
            )
            _validate_candidate_context(
                adapted,
                context=context,
                plan=plan,
                output_role=output_role,
            )
            output = (
                checked_attempt.attempt_dir
                / f"{lane}-selected-candidate.json"
            )
            write_candidate_output(output, adapted)
            live_path = _safe_file(
                live_path,
                label=f"{lane} selected live DWR evidence",
            )
            current = context.artifact("current_watchdog_record")
            built = build_live_shadow_bridge(
                current_record=BoundJSONInput(
                    current.path,
                    current.sha256,
                ),
                shadow_record=BoundJSONInput(record.path, record.sha256),
                transition_action=BoundJSONInput(
                    action.path,
                    action.sha256,
                ),
                live_shadow_evidence=BoundJSONInput(
                    live_path,
                    _file_sha256(live_path),
                ),
            )
            bridge = (
                checked_attempt.attempt_dir
                / f"{lane}-selected-live-dwr-bridge.json"
            )
            bridge_receipt = write_live_shadow_bridge(bridge, built)
            if not bridge_receipt.passed:
                return _blocker_result(
                    context,
                    checked_attempt,
                    code=f"{lane}_selected_effectivity_failed",
                    message=bridge_receipt.classification,
                    inputs={
                        "shadow_record_sha256": record.sha256,
                        "live_bridge_sha256": (
                            bridge_receipt.file_sha256
                        ),
                    },
                    receipts=receipts,
                )
            return _completed(
                context,
                classification=f"{lane}_selected_verification_pass",
                paths={
                    f"{lane}_selected_shadow_watchdog_record": (
                        record.path
                    ),
                    f"{lane}_selected_shadow_candidate_output": output,
                    f"{lane}_selected_live_dwr_evidence": bridge,
                },
                receipts=receipts,
            )

        return PreparedStage(
            execute=execute,
            argv=argv,
            allow_controlled_resource_stop=True,
        )

    def p_selected_shadow_verification(
        self,
        context: StageExecutionContext,
        attempt: AttemptHandle,
    ) -> PreparedStage:
        return self._selected_shadow_verification(
            context,
            attempt,
            lane="p",
        )

    def h_selected_shadow_verification(
        self,
        context: StageExecutionContext,
        attempt: AttemptHandle,
    ) -> PreparedStage:
        return self._selected_shadow_verification(
            context,
            attempt,
            lane="h",
        )

    def shadow_bundle(
        self,
        context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        def execute(
            attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if receipts:
                raise CampaignEvidenceError(
                    "shadow bundle stage must be light"
                )
            from benchmarks.task035e_blind_bindings import (
                ShadowEndpointInput,
                write_shadow_request,
            )
            from benchmarks.task035e_shadow_bundle import (
                BoundJSONInput,
                build_shadow_bundle,
                write_shadow_bundle,
            )

            endpoints: dict[str, tuple[ShadowEndpointInput, ...]] = {}
            for lane in ("p", "h"):
                action = context.artifact(
                    f"{lane}_selected_transition_action"
                )
                if _is_skip(action):
                    endpoints[lane] = ()
                    continue
                endpoints[lane] = (
                    ShadowEndpointInput(
                        transition_action_path=action.path,
                        goal_marking_path=context.artifact(
                            f"{lane}_goal_marking"
                        ).path,
                        verification_prediction_path=context.artifact(
                            f"{lane}_verification_prediction"
                        ).path,
                        shadow_record_path=context.artifact(
                            f"{lane}_selected_shadow_watchdog_record"
                        ).path,
                        dwr_evidence_path=context.artifact(
                            f"{lane}_selected_live_dwr_evidence"
                        ).path,
                    ),
                )
            request_path = (
                attempt.attempt_dir / "selected-shadow-request.json"
            )
            request = write_shadow_request(
                request_path,
                current_record_path=context.artifact(
                    "current_watchdog_record"
                ).path,
                p_actions=endpoints["p"],
                h_actions=endpoints["h"],
            )
            built = build_shadow_bundle(
                BoundJSONInput(request.path, request.file_sha256)
            )
            bundle_path = (
                attempt.attempt_dir / "selected-shadow-bundle.json"
            )
            write_shadow_bundle(bundle_path, built)
            return _completed(
                context,
                classification="actual_selected_shadow_bundle_pass",
                paths={
                    "shadow_request": request_path,
                    "shadow_bundle": bundle_path,
                },
            )

        return PreparedStage(execute=execute)

    @staticmethod
    def _probe_limits(
        current_record: StageArtifactBinding,
    ) -> tuple[int, int, int]:
        record = _strict_json(
            current_record,
            label="current watchdog record",
        )
        raw = record.get("raw_evidence")
        summary = record.get("solver_summary")
        if not isinstance(raw, Mapping) or not isinstance(summary, Mapping):
            raise CampaignEvidenceError(
                "current watchdog lacks probe baseline evidence"
            )
        dtn_path_raw = raw.get("dtn_orders")
        if not isinstance(dtn_path_raw, str) or not dtn_path_raw:
            raise CampaignEvidenceError(
                "current watchdog lacks DtN order artifact"
            )
        dtn_path = Path(dtn_path_raw)
        dtn_path = (
            dtn_path if dtn_path.is_absolute() else ROOT / dtn_path
        ).resolve()
        dtn_path = _safe_file(dtn_path, label="baseline DtN orders")
        try:
            dtn = json.loads(dtn_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CampaignEvidenceError(
                "baseline DtN orders are unreadable"
            ) from exc
        rows = dtn.get("orders") if isinstance(dtn, Mapping) else None
        if not isinstance(rows, list) or not rows:
            raise CampaignEvidenceError(
                "baseline DtN order inventory is empty"
            )
        max_m = max(abs(int(row["m"])) for row in rows) + 1
        max_n = max(abs(int(row["n"])) for row in rows) + 1
        baseline_q = summary.get("stage4_dtn_surface_quadrature_degree")
        if type(baseline_q) is not int or baseline_q < 1:
            raise CampaignEvidenceError(
                "baseline surface quadrature degree is absent"
            )
        return max_m, max_n, int(baseline_q) + 2

    def internal_gate_deferred_or_final(
        self,
        context: StageExecutionContext,
        attempt: AttemptHandle,
    ) -> PreparedStage:
        current_record = context.artifact("current_watchdog_record")
        current_output = context.artifact("current_candidate_output")
        current_plan = context.artifact("current_plan")
        current_snapshot = context.artifact("current_snapshot")
        if context.stage.cycle_index < FINAL_PROBE_CYCLE:
            def execute_deferred(
                checked_attempt: AttemptHandle,
                receipts: tuple[CommandExecutionReceipt, ...],
            ) -> StageResult:
                if receipts:
                    raise CampaignEvidenceError(
                        "deferred internal Gate executed a probe"
                    )
                from benchmarks.task035e_internal_gate_authority import (
                    BoundJSONInput,
                    write_deferred_internal_gate_authority,
                )

                output = (
                    checked_attempt.attempt_dir
                    / "deferred-internal-gate.json"
                )
                write_deferred_internal_gate_authority(
                    output,
                    candidate_record=BoundJSONInput(
                        current_record.path,
                        current_record.sha256,
                    ),
                    candidate_output=BoundJSONInput(
                        current_output.path,
                        current_output.sha256,
                    ),
                    current_plan=BoundJSONInput(
                        current_plan.path,
                        current_plan.sha256,
                    ),
                    current_snapshot=BoundJSONInput(
                        current_snapshot.path,
                        current_snapshot.sha256,
                    ),
                )
                return _completed(
                    context,
                    classification="internal_gate_deferred",
                    paths={"internal_gate_authority": output},
                )

            return PreparedStage(execute=execute_deferred)

        dtn_m, dtn_n, post_q = self._probe_limits(current_record)
        probe_specs = (
            ("algebraic", FORMAL_MPI_SIZE, None, None, None),
            ("dtn", FORMAL_MPI_SIZE, dtn_m, dtn_n, None),
            ("postprocess", FORMAL_MPI_SIZE, None, None, post_q),
            ("serial_mpi1", 1, None, None, None),
        )
        argvs = tuple(
            _watchdog_spec(
                self.settings,
                context,
                attempt,
                output_role="current",
                plan=current_plan,
                record_name=f"{kind}-probe-watchdog.json",
                run_name=f"run-probe-{kind}",
                snapshot=current_snapshot,
                internal_probe_kind=kind,
                mpi_size=mpi_size,
                probe_dtn_max_m=max_m,
                probe_dtn_max_n=max_n,
                probe_surface_quadrature_degree=quadrature,
            )
            for kind, mpi_size, max_m, max_n, quadrature in probe_specs
        )

        def execute_final(
            checked_attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if len(receipts) != 4:
                raise CampaignEvidenceError(
                    "final internal Gate requires four probe receipts"
                )
            from benchmarks.task035e_internal_gate_authority import (
                BoundJSONInput,
                write_internal_gate_authority,
            )

            records = tuple(
                _record_binding(receipt, role=f"probe_{index}")
                for index, receipt in enumerate(receipts)
            )
            output = (
                checked_attempt.attempt_dir / "final-internal-gate.json"
            )
            written = write_internal_gate_authority(
                output,
                candidate_record=BoundJSONInput(
                    current_record.path,
                    current_record.sha256,
                ),
                candidate_output=BoundJSONInput(
                    current_output.path,
                    current_output.sha256,
                ),
                current_plan=BoundJSONInput(
                    current_plan.path,
                    current_plan.sha256,
                ),
                current_snapshot=BoundJSONInput(
                    current_snapshot.path,
                    current_snapshot.sha256,
                ),
                algebraic_probe_record=BoundJSONInput(
                    records[0].path,
                    records[0].sha256,
                ),
                dtn_probe_record=BoundJSONInput(
                    records[1].path,
                    records[1].sha256,
                ),
                postprocess_probe_record=BoundJSONInput(
                    records[2].path,
                    records[2].sha256,
                ),
                serial_mpi1_record=BoundJSONInput(
                    records[3].path,
                    records[3].sha256,
                ),
            )
            if not written.serial_mpi_identity_pass:
                return _blocker_result(
                    context,
                    checked_attempt,
                    code="final_internal_gate_failed",
                    message=written.classification,
                    inputs={
                        "internal_gate_file_sha256": written.file_sha256
                    },
                    receipts=receipts,
                )
            return _completed(
                context,
                classification="final_internal_gate_qualified",
                paths={"internal_gate_authority": output},
                receipts=receipts,
            )

        return PreparedStage(execute=execute_final, argvs=argvs)

    def isolation_audit(
        self,
        context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        def execute(
            attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if receipts:
                raise CampaignEvidenceError(
                    "isolation audit must not execute a PDE"
                )
            from benchmarks.task035e_blind_bindings import (
                write_blind_input_manifest,
            )

            manifest_path = (
                attempt.attempt_dir / "blind-input-manifest.json"
            )
            write_blind_input_manifest(
                manifest_path,
                trial_metadata_path=context.artifact(
                    "trial_metadata"
                ).path,
                current_record_path=context.artifact(
                    "current_watchdog_record"
                ).path,
                candidate_output_path=context.artifact(
                    "current_candidate_output"
                ).path,
                current_snapshot_path=context.artifact(
                    "current_snapshot"
                ).path,
                shadow_bundle_path=context.artifact(
                    "shadow_bundle"
                ).path,
            )
            protected_canary = attempt.attempt_dir / "protected-canary"
            protected_canary.mkdir(mode=0o700)
            checker_path = (
                ROOT
                / "benchmarks"
                / ("task035e_" + "reference_leak_checker.py")
            )
            report_path = attempt.attempt_dir / "isolation-report.json"
            completed = subprocess.run(
                (
                    str(self.settings.python_executable),
                    str(checker_path),
                    "--controller-package",
                    str(
                        ROOT
                        / "src"
                        / "adaptivity"
                        / "blind_controller"
                    ),
                    "--manifest",
                    str(manifest_path),
                    "--source-root",
                    str(ROOT),
                    "--formal-task035e-entrypoints",
                    "--audit-entry",
                    str(Path(__file__).resolve()),
                    "--protected-path",
                    str(protected_canary),
                    "--audit-arg=--help",
                    "--audit-cwd",
                    str(ROOT),
                    "--output",
                    str(report_path),
                ),
                cwd=ROOT,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=min(self.settings.timeout_seconds, 300.0),
            )
            stdout_path = attempt.write_artifact(
                "isolation-checker.stdout",
                completed.stdout,
            )
            stderr_path = attempt.write_artifact(
                "isolation-checker.stderr",
                completed.stderr,
            )
            report_outer: Mapping[str, Any] = {}
            report: Mapping[str, Any] = {}
            if report_path.is_file():
                parsed = json.loads(report_path.read_text(encoding="utf-8"))
                if isinstance(parsed, Mapping):
                    report_outer = parsed
                payload = report_outer.get("payload")
                if isinstance(payload, Mapping):
                    report = payload
            if completed.returncode != 0 or report.get("pass") is not True:
                return _blocker_result(
                    context,
                    attempt,
                    code="reference_isolation_failed",
                    message=str(report.get("status")),
                    inputs={
                        "manifest_file_sha256": _file_sha256(
                            manifest_path
                        ),
                        "report_file_sha256": (
                            _file_sha256(report_path)
                            if report_path.is_file()
                            else None
                        ),
                        "checker_return_code": completed.returncode,
                        "report_exit_code": report.get("exit_code"),
                        "stdout_sha256": _file_sha256(stdout_path),
                        "stderr_sha256": _file_sha256(stderr_path),
                    },
                )
            return _completed(
                context,
                classification="reference_isolation_pass",
                paths={
                    "blind_input_manifest": manifest_path,
                    "isolation_report": report_path,
                },
            )

        return PreparedStage(execute=execute)

    def cycle_binding(
        self,
        context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        def execute(
            attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if receipts:
                raise CampaignEvidenceError(
                    "cycle binding must not execute a PDE"
                )
            from benchmarks.task035e_blind_bindings import (
                VerificationPredictionInput,
                write_cycle_binding,
            )

            cycle = context.stage.cycle_index
            prior_state = None
            verification_inputs: tuple[VerificationPredictionInput, ...] = ()
            repeat_action = None
            if cycle > 0:
                prior_state = context.artifact("trial_state").path
                mode_binding = context.artifact(
                    "previous_transition_mode"
                )
                mode = _strict_json(
                    mode_binding,
                    label="previous transition mode",
                )
                if (
                    mode.get("schema_version") != TRANSITION_MODE_SCHEMA
                    or mode.get("source_sha") != context.source_sha
                    or mode.get("to_cycle_index") != cycle
                ):
                    raise CampaignEvidenceError(
                        "previous transition mode identity differs"
                    )
                transition = context.artifact("next_transition_action")
                if mode.get("mode") == "selected_action":
                    marking = context.artifact(
                        "previous_selected_goal_marking"
                    )
                    prediction = context.artifact(
                        "previous_selected_verification_prediction"
                    )
                    if _is_skip(marking) or _is_skip(prediction):
                        raise CampaignEvidenceError(
                            "selected transition lost its prior marking"
                        )
                    verification_inputs = (
                        VerificationPredictionInput(
                            transition_action_path=transition.path,
                            goal_marking_path=marking.path,
                            prediction_path=prediction.path,
                        ),
                    )
                elif mode.get("mode") == "pkeep":
                    repeat_action = transition.path
                else:
                    raise CampaignEvidenceError(
                        "previous transition mode is invalid"
                    )
            output = attempt.attempt_dir / "cycle-binding.json"
            write_cycle_binding(
                output,
                trial_metadata_path=context.artifact(
                    "trial_metadata"
                ).path,
                current_record_path=context.artifact(
                    "current_watchdog_record"
                ).path,
                candidate_output_path=context.artifact(
                    "current_candidate_output"
                ).path,
                current_snapshot_path=context.artifact(
                    "current_snapshot"
                ).path,
                shadow_bundle_path=context.artifact("shadow_bundle").path,
                internal_gates_path=context.artifact(
                    "internal_gate_authority"
                ).path,
                isolation_report_path=context.artifact(
                    "isolation_report"
                ).path,
                prior_trial_state_path=prior_state,
                verification_inputs=verification_inputs,
                stability_repeat_action_path=repeat_action,
            )
            return _completed(
                context,
                classification="cycle_binding_pass",
                paths={"cycle_binding": output},
            )

        return PreparedStage(execute=execute)

    def cycle_advance(
        self,
        context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        def execute(
            attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if receipts:
                raise CampaignEvidenceError(
                    "cycle advance must not execute a PDE"
                )
            from benchmarks.task035e_blind_cycle import (
                load_trial_state,
                run_blind_cycle,
            )

            evidence = attempt.attempt_dir / "cycle-evidence.json"
            state_path = attempt.attempt_dir / "trial-state.json"
            prior = (
                None
                if context.stage.cycle_index == 0
                else context.artifact("trial_state")
            )
            written = run_blind_cycle(
                candidate_output_path=context.artifact(
                    "current_candidate_output"
                ).path,
                candidate_output_sha256=context.artifact(
                    "current_candidate_output"
                ).sha256,
                shadow_bundle_path=context.artifact(
                    "shadow_bundle"
                ).path,
                shadow_bundle_sha256=context.artifact(
                    "shadow_bundle"
                ).sha256,
                cycle_binding_path=context.artifact(
                    "cycle_binding"
                ).path,
                cycle_binding_sha256=context.artifact(
                    "cycle_binding"
                ).sha256,
                reference_isolation_report_path=context.artifact(
                    "isolation_report"
                ).path,
                reference_isolation_report_sha256=context.artifact(
                    "isolation_report"
                ).sha256,
                evidence_output_path=evidence,
                trial_state_output_path=state_path,
                prior_trial_state_path=(
                    None if prior is None else prior.path
                ),
                prior_trial_state_sha256=(
                    None if prior is None else prior.sha256
                ),
            )
            if written.controlled_negative:
                return _blocker_result(
                    context,
                    attempt,
                    code="blind_cycle_controlled_negative",
                    message=written.status,
                    inputs={
                        "cycle_evidence_file_sha256": (
                            written.evidence_file_sha256
                        ),
                        "trial_state_file_sha256": (
                            written.trial_state_file_sha256
                        ),
                    },
                )
            trial = load_trial_state(
                state_path,
                written.trial_state_file_sha256,
            )
            if not trial.results:
                raise CampaignEvidenceError(
                    "advanced trial state has no result"
                )
            result = trial.results[-1]
            selected = tuple(result.selected_action_ids)
            if len(selected) > 1:
                return _blocker_result(
                    context,
                    attempt,
                    code="combined_action_not_wired",
                    message=(
                        "repository campaign currently accepts the controller "
                        "single-lane policy only"
                    ),
                    inputs={"selected_action_ids": list(selected)},
                )
            selection_unsigned = {
                "schema_version": SELECTION_SCHEMA,
                "status": (
                    "selected_action"
                    if selected
                    else "no_production_action"
                ),
                "source_sha": context.source_sha,
                "path_id": context.stage.path_id,
                "cycle_index": context.stage.cycle_index,
                "selected_action_ids": list(selected),
                "controller_certificate_sha256": (
                    result.internal_certificate_sha256
                ),
                "freeze_ready": result.freeze_ready,
                "ordinary_default_changed": False,
            }
            selection = attempt.write_artifact(
                "selected-action-or-pkeep.json",
                {
                    **selection_unsigned,
                    "selection_sha256": _json_sha256(selection_unsigned),
                },
            )
            freeze_unsigned = {
                "schema_version": FREEZE_INTENT_SCHEMA,
                "status": (
                    "freeze_requested"
                    if result.freeze_ready
                    else "continue"
                ),
                "source_sha": context.source_sha,
                "path_id": context.stage.path_id,
                "cycle_index": context.stage.cycle_index,
                "freeze_requested": result.freeze_ready,
                "p6_saturation_status": result.p6_saturation.status,
                "p6_saturation_freeze_passed": (
                    result.p6_saturation.freeze_passed
                ),
                "h_level3_saturation_status": (
                    result.h_level3_saturation.status
                ),
                "h_level3_saturation_freeze_passed": (
                    result.h_level3_saturation.freeze_passed
                ),
                "controller_certificate_sha256": (
                    result.internal_certificate_sha256
                ),
                "ordinary_default_changed": False,
            }
            freeze = attempt.write_artifact(
                "freeze-intent.json",
                {
                    **freeze_unsigned,
                    "freeze_intent_sha256": _json_sha256(
                        freeze_unsigned
                    ),
                },
            )
            return _completed(
                context,
                classification="blind_cycle_decision",
                paths={
                    "cycle_evidence": evidence,
                    "trial_state": state_path,
                    "selected_action_binding_or_pkeep": selection,
                    "freeze_intent": freeze,
                },
                lane_decision=(
                    "freeze_ready" if result.freeze_ready else "continue"
                ),
                freeze_requested=result.freeze_ready,
                p6_saturation=(
                    "verified"
                    if result.p6_saturation.freeze_passed
                    else "unknown"
                ),
                h_level3_saturation=(
                    "verified"
                    if result.h_level3_saturation.freeze_passed
                    else "unknown"
                ),
            )

        return PreparedStage(execute=execute)

    @staticmethod
    def _transition_action_identity(
        binding: StageArtifactBinding,
    ) -> Mapping[str, Any]:
        value = _strict_json(binding, label=binding.role)
        if set(value) == {"schema_version", "sha256", "payload"}:
            value = value.get("payload")
        if not isinstance(value, Mapping):
            raise CampaignEvidenceError(
                "transition action payload is absent"
            )
        kind = value.get("kind")
        targets = value.get("canonical_target_ids")
        if (
            kind not in {"p-up", "p-down", "p-keep", "h-refine"}
            or not isinstance(targets, list)
            or any(not isinstance(item, str) for item in targets)
        ):
            raise CampaignEvidenceError(
                "transition action identity is incomplete"
            )
        return value

    def transition_or_pkeep(
        self,
        context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        def execute(
            attempt: AttemptHandle,
            receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            if receipts:
                raise CampaignEvidenceError(
                    "transition stage must not execute a PDE"
                )
            from benchmarks.task035e_transition_producer import (
                write_transition_bundle,
            )

            selection_binding = context.artifact(
                "selected_action_binding_or_pkeep"
            )
            selection = _strict_json(
                selection_binding,
                label="cycle action selection",
            )
            selected = selection.get("selected_action_ids")
            if (
                selection.get("schema_version") != SELECTION_SCHEMA
                or not isinstance(selected, list)
                or len(selected) > 1
            ):
                raise CampaignEvidenceError(
                    "cycle action selection schema differs"
                )
            current_plan = context.artifact("current_plan")
            lane: str | None = None
            source_action: StageArtifactBinding | None = None
            source_marking: StageArtifactBinding | None = None
            source_prediction: StageArtifactBinding | None = None
            if selected:
                selected_id = str(selected[0])
                for candidate_lane in ("p", "h"):
                    candidate = context.artifact(
                        f"{candidate_lane}_selected_transition_action"
                    )
                    if _is_skip(candidate):
                        continue
                    identity = self._transition_action_identity(candidate)
                    if str(identity.get("action_id")) == selected_id:
                        lane = candidate_lane
                        source_action = candidate
                        source_marking = context.artifact(
                            f"{candidate_lane}_goal_marking"
                        )
                        source_prediction = context.artifact(
                            f"{candidate_lane}_verification_prediction"
                        )
                        break
                if source_action is None:
                    return _blocker_result(
                        context,
                        attempt,
                        code="selected_action_artifact_missing",
                        message=(
                            "controller-selected action is absent from the "
                            "verified p/h shadow inventory"
                        ),
                        inputs={"selected_action_id": selected_id},
                    )
                action_identity = self._transition_action_identity(
                    source_action
                )
                mode = "selected_action"
                action_kind = str(action_identity["kind"])
                targets = tuple(
                    str(value)
                    for value in action_identity[
                        "canonical_target_ids"
                    ]
                )
            else:
                selected_id = None
                mode = "pkeep"
                action_kind = "p-keep"
                targets = ()
            action_path = (
                attempt.attempt_dir / "next-transition-action.json"
            )
            plan_path = attempt.attempt_dir / "next-current-plan.json"
            written = write_transition_bundle(
                current_plan_path=current_plan.path,
                current_plan_file_sha256=current_plan.sha256,
                source_sha=context.source_sha,
                action_kind=action_kind,
                canonical_target_ids=targets,
                action_path=action_path,
                next_plan_path=plan_path,
            )
            if mode == "selected_action":
                assert source_marking is not None
                assert source_prediction is not None
                prior_marking = _copy_private(
                    attempt,
                    name="previous-selected-goal-marking.json",
                    binding=source_marking,
                )
                prior_prediction = _copy_private(
                    attempt,
                    name="previous-selected-verification-prediction.json",
                    binding=source_prediction,
                )
            else:
                skipped = _write_skips(
                    context,
                    attempt,
                    lane="none",
                    reason="pkeep_has_no_selected_shadow_marking",
                    roles=(
                        "previous_selected_goal_marking",
                        "previous_selected_verification_prediction",
                    ),
                )
                prior_marking = skipped[
                    "previous_selected_goal_marking"
                ]
                prior_prediction = skipped[
                    "previous_selected_verification_prediction"
                ]
            mode_unsigned = {
                "schema_version": TRANSITION_MODE_SCHEMA,
                "status": "transition_published",
                "mode": mode,
                "source_sha": context.source_sha,
                "path_id": context.stage.path_id,
                "from_cycle_index": context.stage.cycle_index,
                "to_cycle_index": context.stage.cycle_index + 1,
                "selected_lane": lane,
                "selected_action_id": selected_id,
                "action_kind": action_kind,
                "canonical_target_ids": list(targets),
                "action_file_sha256": written.action_file_sha256,
                "next_plan_file_sha256": written.plan_file_sha256,
                "ordinary_default_changed": False,
            }
            mode_path = attempt.write_artifact(
                "previous-transition-mode.json",
                {
                    **mode_unsigned,
                    "transition_mode_sha256": _json_sha256(mode_unsigned),
                },
            )
            return _completed(
                context,
                classification=(
                    "selected_transition_published"
                    if mode == "selected_action"
                    else "pkeep_transition_published"
                ),
                paths={
                    "next_transition_action": action_path,
                    "current_plan": plan_path,
                    "previous_transition_mode": mode_path,
                    "previous_selected_goal_marking": prior_marking,
                    "previous_selected_verification_prediction": (
                        prior_prediction
                    ),
                },
                next_plan_sha256=written.plan_file_sha256,
            )

        return PreparedStage(execute=execute)


def live_clean_source_sha() -> str:
    """Return the current clean Git HEAD or fail before campaign execution."""

    head = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        cwd=ROOT,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout
    if _SOURCE_SHA_RE.fullmatch(head) is None or status:
        raise BlindCampaignError(
            "formal campaign requires one clean lowercase full Git HEAD"
        )
    return head


def live_qualified_abi_sha256() -> str:
    """Hash the validated live Linux complex128/int32 ABI preflight."""

    from benchmarks import task035e_trial_metadata as metadata

    preflight = metadata._validated_abi_preflight(  # noqa: SLF001
        metadata._qualified_abi_preflight()  # noqa: SLF001
    )
    return _json_sha256(preflight)


def repository_formal_stage_handlers(
    settings: FormalCampaignSettings,
) -> Mapping[str, FormalStageHandler]:
    """Public factory used by the formal CLI and component tests."""

    return RepositoryFormalStageHandlers(settings).mapping()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--abi-sha256", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument(
        "--tensor-cache-directory",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--python-executable",
        type=Path,
        default=Path(sys.executable),
    )
    parser.add_argument("--timeout-seconds", type=float, default=43200.0)
    parser.add_argument("--maximum-new-stages", type=int)
    for lane in ("a", "b"):
        parser.add_argument(f"--path-{lane}-plan", type=Path, required=True)
        parser.add_argument(f"--path-{lane}-plan-sha256", required=True)
        parser.add_argument(
            f"--path-{lane}-initial-space-authority",
            type=Path,
            required=True,
        )
        parser.add_argument(
            f"--path-{lane}-initial-space-authority-sha256",
            required=True,
        )
        parser.add_argument(
            f"--path-{lane}-qualified-solver-config",
            type=Path,
            required=True,
        )
        parser.add_argument(
            f"--path-{lane}-qualified-solver-config-sha256",
            required=True,
        )
        parser.add_argument(
            f"--path-{lane}-trial-id",
            default=f"task035e-blind-path-{lane}",
        )
    return parser


def _path_identity(
    args: argparse.Namespace,
    *,
    lane: str,
) -> BlindPathIdentity:
    lower = lane.lower()
    return BlindPathIdentity(
        path_id=lane,
        trial_id=str(getattr(args, f"path_{lower}_trial_id")),
        nominal_h_nm=20.0 if lane == "A" else 15.0,
        initial_plan_path=getattr(args, f"path_{lower}_plan"),
        initial_plan_sha256=getattr(
            args,
            f"path_{lower}_plan_sha256",
        ),
        initial_space_authority_path=getattr(
            args,
            f"path_{lower}_initial_space_authority",
        ),
        initial_space_authority_sha256=getattr(
            args,
            f"path_{lower}_initial_space_authority_sha256",
        ),
        qualified_solver_config_path=getattr(
            args,
            f"path_{lower}_qualified_solver_config",
        ),
        qualified_solver_config_sha256=getattr(
            args,
            f"path_{lower}_qualified_solver_config_sha256",
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run or resume the formal campaign without caller-supplied handlers."""

    args = _parser().parse_args(argv)
    try:
        source = live_clean_source_sha()
        abi = live_qualified_abi_sha256()
        if source != args.source_sha:
            raise BlindCampaignError(
                "supplied source SHA differs from live clean HEAD"
            )
        if abi != args.abi_sha256:
            raise BlindCampaignError(
                "supplied ABI SHA-256 differs from live qualified ABI"
            )
        identity = BlindCampaignIdentity(
            source_sha=source,
            abi_sha256=abi,
            paths=(
                _path_identity(args, lane="A"),
                _path_identity(args, lane="B"),
            ),
        )
        settings = FormalCampaignSettings(
            python_executable=args.python_executable,
            artifact_root=args.artifact_root,
            tensor_cache_directory=args.tensor_cache_directory,
            timeout_seconds=args.timeout_seconds,
        )
        root = initialize_campaign(args.campaign_root, identity)
        report = run_campaign(
            root,
            identity,
            prepare_stage=RepositoryFormalStageHandlers(
                settings
            ).preparer(),
            source_sha_provider=live_clean_source_sha,
            abi_sha256_provider=live_qualified_abi_sha256,
            maximum_new_stages=args.maximum_new_stages,
        )
    except (
        BlindCampaignError,
        FileExistsError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {
                    "schema_version": HANDLER_SCHEMA,
                    "status": "failed",
                    "error": str(exc),
                    "ordinary_default_changed": False,
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("status") in {"completed", "partial"} else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BLOCKER_SCHEMA",
    "FormalCampaignSettings",
    "HANDLER_SCHEMA",
    "LEGAL_SKIP_SCHEMA",
    "RepositoryFormalStageHandlers",
    "TARGET_CATALOG_SCHEMA",
    "live_clean_source_sha",
    "live_qualified_abi_sha256",
    "main",
    "repository_formal_stage_handlers",
]
