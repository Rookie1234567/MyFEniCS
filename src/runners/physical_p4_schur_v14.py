"""Task39extra V14 workers for the fresh p4 full/direct Schur comparison.

Q1 and Q2 are deliberately separate worker stages.  Each worker builds the
same p6/p4 mesh, mode inventory and three hash-bound p4 right-hand sides, then
exits after its own factors have been destroyed.  Q3 is a diagnostic interface
candidate stage; Q4--Q6 remain explicit not-run stages until later gates
authorize them.
"""

from __future__ import annotations

from contextlib import contextmanager
import gc
import hashlib
import json
import os
from pathlib import Path
import signal
import time
from typing import Any, Mapping

import numpy as np

from src.io.physical_intermediate_profile import SCHUR_PROFILE, profile_facts


_Q1_Q2_RHS = (
    {
        "stem": "A2R160_BAL_H_p4_01",
        "input_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/A2R160_BAL_H_p4_01_input.json",
        "input_sha256": "630d72b522ea2fe87d124833c031206708bbde1be1aca12e9bdf113af6c1c6a1",
        "input_npz_sha256": "a630483a3fb3b6dac145809545ac3768b8ff22dd15aad8f7e6f2fff43068b268",
        "g_sha256": "f768ff33bdd7d87844126da745897462793ac8d7f10d63eca0b7e5df65624c35",
        "reference_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/A2R160_BAL_H_p4_01_residual_0.json",
        "reference_json_sha256": "100adfa1791943951d356ee3741f42ae8700df584491c9432bed5c5ba4c54b75",
        "reference_npz_sha256": "2eef8af221f793df08eb95ed475f409d8b84e4c3defe5a96fa7a01473441bd0f",
        "logical_rhs": 1,
    },
    {
        "stem": "A2R160_BAL_H_p4_02",
        "input_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/A2R160_BAL_H_p4_02_input.json",
        "input_sha256": "bd67fd98422179f6a66d0cbbb7a958e738b0acdad8905e11e0182f9496d85826",
        "input_npz_sha256": "ac3d29e8dc50f1c8ff46e7e11546b6b66702270e8183026ce0393674327c5bd9",
        "g_sha256": "9f80339733111712644f976d6ed7728d4a8ea0a0c9ddc2f70079ebf2fbd12fb8",
        "reference_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/A2R160_BAL_H_p4_02_residual_0.json",
        "reference_json_sha256": "e07c05442ffc9a0544ce50c8c054439d48770b773e6b95f4311feafb05a06c20",
        "reference_npz_sha256": "5a166d02c8c62dff444e339539525521a30dbdaa8023838fa5edf94f29a939f3",
        "logical_rhs": 2,
    },
    {
        "stem": "LIGHT448_BAL_H_p4_09",
        "input_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/LIGHT448_BAL_H_p4_09_input.json",
        "input_sha256": "e3a919807e5d80f20e7e96b58626ea6e392a32e5b5280e0a175452b133cb2e76",
        "input_npz_sha256": "212700de37917f3f706395e08d8c645333fcfbebad236d649f14bcf415144728",
        "g_sha256": "dc121f45e8ffe2105a61b9cfc0783b600d1b6c155223dd49029a7017be27e24e",
        "reference_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/LIGHT448_BAL_H_p4_09_residual_0.json",
        "reference_json_sha256": "3fa6f5c510db29d38276ee9aa299b527bb083be9335e66528c12d727c7acef24",
        "reference_npz_sha256": "3b28af8443fd61df198a86ad4f4adc8228bb7caaa29ba23a17f7d9af639cc3fa",
        "logical_rhs": 9,
    },
)


class V14ResourceStop(RuntimeError):
    """The worker-side stage inventory gate requested a controlled stop."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    from .physical_diagnosis_worker import _sha256_file as chunked_sha256_file

    return chunked_sha256_file(path)


def _jsonable(value: Any) -> Any:
    """Keep JSON evidence compact while retaining array identity hashes."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        return {
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "sha256": _sha256_bytes(array.tobytes()),
        }
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("ab") as stream:
        stream.write(
            (
                json.dumps(
                    _jsonable(value),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        )
        stream.flush()
        os.fsync(stream.fileno())


def _save_packet(
    directory: Path,
    name: str,
    facts: Mapping[str, Any],
    *,
    runtime: _V14Runtime | None = None,
) -> dict[str, Any]:
    """Reuse the audited packet writer for immediate vector evidence."""

    from .physical_diagnosis_worker import save_packet

    directory.mkdir(parents=True, exist_ok=True)
    workspace_label = f"packet_{name}"
    if runtime is not None:
        runtime.reserve_workspace(workspace_label, 17 << 20)
    try:
        save_packet(directory, name, dict(facts))
    finally:
        if runtime is not None:
            runtime.release_workspace(workspace_label)
    packet_path = directory / f"{name}.json"
    return json.loads(packet_path.read_text(encoding="utf-8"))


def _repo_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / "src").is_dir() and (candidate / "input").is_dir():
            return candidate
    raise RuntimeError("V14 worker cannot locate the repository root")


def _load_rhs_and_reference(root: Path, storage_rows: int) -> list[dict[str, Any]]:
    """Load the three reviewed packets through the audited calibration loader.

    ``load_recursive_calibration`` binds ``g``, ``y``, ``A4y`` and the frozen
    native p4 constraint map together.  The current worker still rebuilds its
    mesh and operators, then checks those identities before any factor is
    built; the old packet is never used as a solver setup shortcut.
    """

    from .physical_recursive_controls import load_recursive_calibration

    inventory_path = root / "benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json"
    loaded = load_recursive_calibration(inventory_path)
    wanted = {item["stem"]: item for item in _Q1_Q2_RHS}
    selected = {
        item["identity"]["stem"]: item
        for item in loaded
        if item["identity"].get("stem") in wanted
    }
    if tuple(selected) != tuple(item["stem"] for item in _Q1_Q2_RHS):
        raise ValueError("V14 calibration loader did not return the reviewed RHS order")
    result = []
    for item in _Q1_Q2_RHS:
        loaded_item = selected[item["stem"]]
        identity = loaded_item["identity"]
        input_json = root / item["input_json"]
        input_npz = input_json.with_suffix(".npz")
        reference_json = root / item["reference_json"]
        reference_metadata = json.loads(reference_json.read_text(encoding="utf-8"))
        reference_npz = root / reference_metadata["arrays"]["path"]
        if identity.get("input_sha256") != item["input_sha256"]:
            raise ValueError(f"{item['stem']} calibration identity changed")
        for path, expected, label in (
            (input_json, item["input_sha256"], "input metadata"),
            (input_npz, item["input_npz_sha256"], "input array"),
            (reference_json, item["reference_json_sha256"], "reference metadata"),
            (reference_npz, item["reference_npz_sha256"], "reference array"),
        ):
            if _sha256_file(path) != expected:
                raise ValueError(f"{item['stem']} {label} hash changed")
        rhs = np.ascontiguousarray(loaded_item["rhs"], dtype=np.complex128).copy()
        reference = np.ascontiguousarray(
            loaded_item["reference_y"], dtype=np.complex128
        ).copy()
        reference_A4y = np.ascontiguousarray(
            loaded_item["reference_A4y"], dtype=np.complex128
        ).copy()
        if rhs.shape != (storage_rows,) or reference.shape != (storage_rows,):
            raise ValueError(f"{item['stem']} p4 storage vector shape changed")
        if reference_A4y.shape != (storage_rows,):
            raise ValueError(f"{item['stem']} saved A4y shape changed")
        if _sha256_bytes(rhs.tobytes()) != item["g_sha256"]:
            raise ValueError(f"{item['stem']} RHS content hash changed")
        result.append(
            {
                "stem": item["stem"],
                "logical_rhs": int(item["logical_rhs"]),
                "rhs": rhs,
                "reference_solution": reference,
                "reference_A4y": reference_A4y,
                "reference_identity": loaded_item.get("reference_identity"),
                "reference_map": loaded_item["reference_map"],
                "calibration_identity": identity,
                "input_json": str(input_json),
                "input_npz": str(input_npz),
                "input_sha256": item["input_sha256"],
                "input_npz_sha256": item["input_npz_sha256"],
                "g_sha256": item["g_sha256"],
                "reference_json": str(reference_json),
                "reference_json_sha256": item["reference_json_sha256"],
                "reference_npz": str(reference_npz),
                "reference_npz_sha256": item["reference_npz_sha256"],
                "reference_true_residual": reference_metadata.get("final_true_residual"),
            }
        )
    # Make the fact that only the three reviewed entries remain explicit.
    for item in loaded:
        if item["identity"].get("stem") not in wanted:
            del item["rhs"]
            if item.get("reference_y") is not None:
                del item["reference_y"]
            if item.get("reference_A4y") is not None:
                del item["reference_A4y"]
    return result


class _V14Runtime:
    """Worker ledger with separate resident-RSS and live-inventory gates."""

    SHARED_WORKFLOW_SECONDS = 43_200.0

    def __init__(
        self,
        directory: Path,
        stage: str,
        contract: Mapping[str, Any],
        *,
        root: Path,
        source_sha: str,
    ) -> None:
        self.directory = directory
        self.stage = stage
        self.contract = contract
        self.root = root
        self.source_sha = source_sha
        self.events_path = directory / "v14_events.jsonl"
        self.resources_path = directory / "v14_worker_resources.jsonl"
        self.inventory_path = directory / "v14_inventory.json"
        self.phase_path = Path(
            os.environ.get("PHYSICAL_WATCHDOG_PHASE_PATH", directory / "workflow_phase.json")
        )
        self.parent_pid = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "-1"))
        self.parent_cap = int(
            os.environ.get(
                "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES",
                contract["resources"]["tree_cap_bytes"],
            )
        )
        self.inventory_cap = contract["resources"]["inventory_memory_cap_bytes_by_stage"].get(stage)
        self.workspace_cap = int(
            contract["resources"]["shared_temp_workspace_cap_bytes"]
        )
        self.stop_requested = False
        self.pc_soft_stop_requested = False
        self._pc_clock = None
        self._outer_solve_active = False
        self._phase_record = None
        self._phase = "preflight"
        self.inventory_entries: dict[str, dict[str, Any]] = {}
        self.inventory_used_bytes = 0
        self.inventory_peak_bytes = 0
        self.workspace_entries: dict[str, int] = {}
        self.workspace_live_bytes = 0
        self.workspace_peak_bytes = 0
        parent_ledger = os.environ.get("PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH")
        if parent_ledger is None:
            raise RuntimeError(
                "V14 worker requires the parent-owned shared workflow ledger"
            )
        self._ledger_path = Path(parent_ledger)
        self._stage_attempt_index = int(
            os.environ.get("PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX", "-1")
        )
        if self._stage_attempt_index < 0:
            raise RuntimeError("V14 parent ledger attempt index is missing")
        shared_ledger = json.loads(self._ledger_path.read_text(encoding="utf-8"))
        if shared_ledger.get("batch_identity") != "review_v14":
            raise RuntimeError("V14 parent ledger batch identity changed")
        attempts = list(
            shared_ledger.get("stages", {}).get(self.stage, {}).get("attempts", [])
        )
        if not 0 <= self._stage_attempt_index < len(attempts):
            raise RuntimeError("V14 parent ledger attempt is missing")
        attempt = attempts[self._stage_attempt_index]
        if attempt.get("source_sha") != self.source_sha:
            raise RuntimeError("V14 parent ledger source SHA differs from worker")
        if attempt.get("status") not in {"RESERVED", "RUNNING"}:
            raise RuntimeError("V14 parent ledger attempt is not live")
        workflow_clock_start = attempt.get("workflow_clock_start")
        reserved_seconds = attempt.get("reserved_seconds")
        workflow_clock_source = "parent_attempt.workflow_clock_start"
        if not isinstance(workflow_clock_start, Mapping):
            # Older unit-test fixtures predate the parent clock fields.  Keep
            # those non-Q3 runtime tests focused on their clock semantics, but
            # never allow the production Q3 stage to run without the parent
            # attempt's immutable start sample.
            if self.stage == "Q3_INTERFACE_CONTROL":
                raise RuntimeError("V14 parent workflow clock start is missing")
            from .workflow_timebase import clock_sample

            workflow_clock_start = clock_sample()
            workflow_clock_source = (
                "worker_start_fallback_for_non_q3_legacy_fixture"
            )
        if (
            not isinstance(reserved_seconds, (int, float))
            or not np.isfinite(float(reserved_seconds))
            or float(reserved_seconds) <= 0.0
        ):
            if self.stage == "Q3_INTERFACE_CONTROL":
                raise RuntimeError("V14 parent workflow reservation is invalid")
            reserved_seconds = (
                contract["resources"].get("stage_budgets", {})
                .get(self.stage, {})
                .get("workflow_seconds", self.SHARED_WORKFLOW_SECONDS)
            )
            workflow_clock_source = (
                "worker_start_fallback_for_non_q3_legacy_fixture"
            )
        self.workflow_clock_start = dict(workflow_clock_start)
        self.workflow_reserved_seconds = float(reserved_seconds)
        self.workflow_clock_source = workflow_clock_source
        self.phase_path.parent.mkdir(parents=True, exist_ok=True)
        self.set_phase(self._phase)
        self._persist_inventory()

    def _persist_inventory(self) -> None:
        component_totals: dict[str, int] = {}
        for entry in self.inventory_entries.values():
            for key, value in entry["components"].items():
                component_totals[key] = component_totals.get(key, 0) + int(value)
            component_totals["workspace_bytes"] = component_totals.get(
                "workspace_bytes", 0
            ) + int(entry.get("workspace_bytes", 0))
        _write_json(
            self.inventory_path,
            {
                "schema": "task039extra.v14.inventory-ledger.v1",
                "stage": self.stage,
                "source_sha": self.source_sha,
                "inventory_cap_bytes": self.inventory_cap,
                "inventory_used_bytes": self.inventory_used_bytes,
                "inventory_peak_bytes": self.inventory_peak_bytes,
                "workspace_cap_bytes": self.workspace_cap,
                "workspace_live_bytes": self.workspace_live_bytes,
                "workspace_peak_bytes": self.workspace_peak_bytes,
                "component_totals": component_totals,
                "entries": self.inventory_entries,
            },
        )

    def workflow_clock_interval(self) -> dict[str, Any]:
        """Return elapsed time from the parent attempt's immutable clock start."""

        from .workflow_timebase import CONSERVATIVE_REALTIME, checked_interval, clock_sample

        return checked_interval(
            self.workflow_clock_start,
            clock_sample(),
            policy=CONSERVATIVE_REALTIME,
        )

    def _inventory_size(self, components: Mapping[str, int]) -> int:
        values = {str(key): int(value) for key, value in components.items()}
        if any(value < 0 for value in values.values()):
            raise ValueError("V14 inventory components cannot be negative")
        return int(sum(values.values()))

    def reserve_inventory(
        self,
        label: str,
        components: Mapping[str, int],
        *,
        workspace_bytes: int = 0,
        check_rss: bool = True,
    ) -> dict[str, Any]:
        key = str(label)
        if workspace_bytes:
            raise ValueError("reserve workspace separately with reserve_workspace")
        if key in self.inventory_entries:
            raise RuntimeError(f"V14 inventory label is already live: {key}")
        normalized = {str(name): int(value) for name, value in components.items()}
        amount = self._inventory_size(normalized)
        if check_rss:
            self.check_projected(key, amount)
        self.check_inventory_projected(key, amount)
        projected = self.inventory_used_bytes + amount
        if self.inventory_cap is not None and projected > int(self.inventory_cap):
            raise V14ResourceStop(
                f"V14 live inventory exceeds stage cap: {key} {projected}>{self.inventory_cap}"
            )
        entry = {
            "components": normalized,
            "bytes": amount,
            "reserved_timestamp_ns": time.time_ns(),
        }
        self.inventory_entries[key] = entry
        self.inventory_used_bytes = projected
        self.inventory_peak_bytes = max(self.inventory_peak_bytes, projected)
        self._persist_inventory()
        self.marker(
            "v14_inventory_reserved",
            {"label": key, "entry": entry, "used_bytes": projected},
        )
        return entry

    def check_inventory_projected(self, label: str, amount: int) -> dict[str, Any]:
        projected = self.inventory_used_bytes + int(amount)
        facts = {
            "label": str(label),
            "current_inventory_bytes": self.inventory_used_bytes,
            "projected_inventory_bytes": projected,
            "inventory_cap_bytes": self.inventory_cap,
            "gate": "independent_live_inventory_cap",
        }
        self.marker("v14_projected_inventory_gate", facts)
        if self.inventory_cap is not None and projected > int(self.inventory_cap):
            raise V14ResourceStop(f"V14 projected live inventory exceeds cap: {facts}")
        return facts

    def replace_inventory(self, label: str, components: Mapping[str, int]) -> None:
        key = str(label)
        old = self.inventory_entries.get(key)
        if old is None:
            raise RuntimeError(f"V14 inventory label is not live: {key}")
        normalized = {str(name): int(value) for name, value in components.items()}
        amount = self._inventory_size(normalized)
        projected = self.inventory_used_bytes - int(old["bytes"]) + amount
        if self.inventory_cap is not None and projected > int(self.inventory_cap):
            raise V14ResourceStop(
                f"V14 replaced inventory exceeds stage cap: {key} {projected}>{self.inventory_cap}"
            )
        self.inventory_entries[key] = {
            "components": normalized,
            "bytes": amount,
            "replaced_timestamp_ns": time.time_ns(),
            "reserved_upper_bound_bytes": int(old["bytes"]),
        }
        self.inventory_used_bytes = projected
        self.inventory_peak_bytes = max(self.inventory_peak_bytes, projected)
        self._persist_inventory()
        self.marker(
            "v14_inventory_replaced",
            {"label": key, "old_bytes": old["bytes"], "new_bytes": amount},
        )

    def reserve_workspace(self, label: str, workspace_bytes: int) -> None:
        key = str(label)
        amount = int(workspace_bytes)
        if amount < 0:
            raise ValueError("V14 workspace allocation cannot be negative")
        if key in self.workspace_entries:
            raise RuntimeError(f"V14 workspace label is already live: {key}")
        self.check_workspace_projected(key, amount)
        self.check_projected(key, 0, workspace_bytes=amount)
        projected = self.workspace_live_bytes + amount
        if projected > self.workspace_cap:
            raise V14ResourceStop(
                f"V14 shared temporary workspace exceeds cap: {key} {projected}>{self.workspace_cap}"
            )
        self.workspace_entries[key] = amount
        self.workspace_live_bytes = projected
        self.workspace_peak_bytes = max(self.workspace_peak_bytes, projected)
        self._persist_inventory()
        self.marker(
            "v14_workspace_reserved",
            {"label": key, "bytes": amount, "live_bytes": projected},
        )

    def check_workspace_projected(self, label: str, workspace_bytes: int) -> dict[str, Any]:
        amount = int(workspace_bytes)
        if amount < 0:
            raise ValueError("V14 workspace allocation cannot be negative")
        projected = self.workspace_live_bytes + amount
        facts = {
            "label": str(label),
            "current_workspace_bytes": self.workspace_live_bytes,
            "projected_workspace_bytes": projected,
            "workspace_cap_bytes": self.workspace_cap,
            "gate": "independent_shared_temporary_workspace_cap",
        }
        self.marker("v14_projected_workspace_gate", facts)
        if projected > self.workspace_cap:
            raise V14ResourceStop(f"V14 projected workspace exceeds cap: {facts}")
        return facts

    def release_workspace(self, label: str) -> None:
        key = str(label)
        amount = self.workspace_entries.pop(key, None)
        if amount is None:
            return
        self.workspace_live_bytes -= amount
        if self.workspace_live_bytes < 0:
            raise RuntimeError("V14 workspace ledger became negative")
        self._persist_inventory()
        self.marker(
            "v14_workspace_released",
            {"label": key, "bytes": amount, "live_bytes": self.workspace_live_bytes},
        )

    def release_inventory(self, label: str) -> None:
        key = str(label)
        entry = self.inventory_entries.pop(key, None)
        if entry is None:
            return
        self.inventory_used_bytes -= int(entry["bytes"])
        if self.inventory_used_bytes < 0:
            raise RuntimeError("V14 inventory ledger became negative")
        self._persist_inventory()
        self.marker(
            "v14_inventory_released",
            {"label": key, "bytes": entry["bytes"], "used_bytes": self.inventory_used_bytes},
        )

    def check_projected(
        self,
        label: str,
        allocation_bytes: int,
        *,
        workspace_bytes: int = 0,
    ) -> dict[str, Any]:
        resource = self.sample(f"{label}_projected")
        allocation = int(allocation_bytes)
        workspace = int(workspace_bytes)
        if allocation < 0 or workspace < 0:
            raise ValueError("V14 projected allocation cannot be negative")
        workspace_live = int(self.workspace_live_bytes)
        untouched_workspace = max(
            0, self.workspace_cap - workspace_live - workspace
        )
        # The current RSS sample already contains any workspace that has
        # materialized.  The still-unmaterialized part of the single shared
        # workspace pool is carried as a conservative future-copy reserve;
        # the new workspace request and that remainder together never exceed
        # the same 1 GiB pool.
        projected_rss = (
            int(resource["rss_bytes"])
            + allocation
            + workspace
            + untouched_workspace
        )
        facts = {
            "label": str(label),
            "allocation_bytes": allocation,
            "workspace_bytes": workspace,
            "workspace_live_bytes": workspace_live,
            "workspace_untouched_reserve_bytes": untouched_workspace,
            "workspace_pool_cap_bytes": self.workspace_cap,
            "rss_bytes": int(resource["rss_bytes"]),
            "projected_rss_bytes": projected_rss,
            "launch_cap_bytes": int(resource["launch_cap_bytes"]),
            "gate": (
                "rss_includes_live_workspace_plus_new_workspace_plus_"
                "untouched_shared_workspace_reserve"
            ),
            "survival_assumption": (
                "all currently reserved workspace is resident in sampled RSS; "
                "the unmaterialized remainder may appear with the next allocation"
            ),
        }
        self.marker("v14_projected_allocation_gate", facts)
        if projected_rss >= int(resource["launch_cap_bytes"]):
            raise V14ResourceStop(f"V14 projected resident allocation exceeds cap: {facts}")
        return facts

    def set_phase(self, phase: str) -> None:
        if self._outer_solve_active and phase != "solve":
            self._phase_record["solve_subphase"] = str(phase)
            _write_json(self.phase_path, self._phase_record)
            return
        if self._phase_record is not None and phase == self._phase:
            return
        self._phase = str(phase)
        from .workflow_timebase import clock_sample

        clock = clock_sample() if os.environ.get("PHYSICAL_TIMEBASE_GUARD") == "1" else None
        value = {
            "schema": "task039extra.v14.workflow-phase.v1",
            "phase": self._phase,
            "stage": self.stage,
            "phase_started_monotonic": time.monotonic(),
            "phase_started_clock": clock,
            "clock_error": None,
            "active_pc": None,
        }
        self._phase_record = value
        _write_json(self.phase_path, value)

    def begin_outer_solve(self) -> None:
        """Anchor the single KSP run, including all in-solve checkpoints."""

        if self._outer_solve_active or self._pc_clock is not None:
            raise RuntimeError("cannot restart an active V14 outer solve")
        # Earlier setup/backsolve probes may also have used the solve phase.
        # Only this explicit transition establishes the one outer KSP start.
        self._phase_record = None
        self.set_phase("solve")
        self._outer_solve_active = True

    def finish_outer_solve(self) -> None:
        if not self._outer_solve_active or self._pc_clock is not None:
            raise RuntimeError("V14 outer solve must finish between whole PC actions")
        self._outer_solve_active = False

    def begin_pc(self, sequence: int) -> None:
        """Arm the parent deadline for one whole BAL_H action."""

        from .workflow_timebase import ClockBudget, CONSERVATIVE_REALTIME, clock_sample

        if self._pc_clock is not None:
            raise RuntimeError("a whole V14 PC action is already active")
        self.set_phase("solve")
        start = clock_sample()
        self._pc_clock = ClockBudget(start, policy=CONSERVATIVE_REALTIME)
        self._phase_record["active_pc"] = {
            "sequence": int(sequence), "started_clock": start,
        }
        self._phase_record["solve_subphase"] = "pc"
        _write_json(self.phase_path, self._phase_record)

    def finish_pc(self, *, completed: bool = True) -> dict[str, Any]:
        """Disarm after return and request soft stop only for a complete PC."""

        from .workflow_timebase import clock_sample

        if self._pc_clock is None:
            raise RuntimeError("no whole V14 PC action is active")
        interval = self._pc_clock.update(clock_sample())
        facts = {
            **self._phase_record["active_pc"],
            "completed": bool(completed),
            "clock_interval": interval,
            "soft_limit_seconds": self.contract["resources"]["pc_soft_seconds"],
            "hard_limit_seconds": self.contract["resources"]["pc_hard_seconds"],
        }
        self._phase_record["active_pc"] = None
        self._phase_record["solve_subphase"] = "between_pc"
        self._pc_clock = None
        _write_json(self.phase_path, self._phase_record)
        if completed and interval["budget_seconds"] >= facts["soft_limit_seconds"]:
            self.pc_soft_stop_requested = True
        facts["soft_stop_requested"] = self.pc_soft_stop_requested
        facts["hard_limit_exceeded"] = (
            interval["budget_seconds"] >= facts["hard_limit_seconds"]
        )
        self.marker("v14_whole_pc_returned", facts)
        if completed and facts["hard_limit_exceeded"]:
            raise V14ResourceStop(f"PC_TIME_CONTROLLED_STOP: {facts}")
        return facts

    def marker(self, name: str, facts: Mapping[str, Any] | None = None) -> None:
        if self._pc_clock is None and name.endswith("started"):
            if "numeric" in name or "symbolic" in name or "factor" in name:
                self.set_phase("factor")
            elif "solve" in name:
                self.set_phase("solve")
            elif "assembly" in name or "compile" in name:
                self.set_phase("assembly")
        _append_jsonl(
            self.events_path,
            {
                "event": name,
                "stage": self.stage,
                "timestamp_ns": time.time_ns(),
                "facts": {} if facts is None else facts,
            },
        )

    def sample(self, label: str | None = None) -> dict[str, Any]:
        if self.stop_requested:
            raise V14ResourceStop("parent requested a V14 worker stop")
        if self._pc_clock is not None:
            from .workflow_timebase import clock_sample

            self._pc_clock.update(clock_sample())
        if self.parent_pid <= 0 or self.parent_pid == os.getpid() or not Path(
            f"/proc/{self.parent_pid}"
        ).is_dir():
            raise RuntimeError("V14 worker requires the dedicated parent watchdog")
        from benchmarks.subreaper_watchdog import memory_envelope
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot

        value = process_tree_snapshot(self.parent_pid, self._phase, None)
        envelope = memory_envelope()
        dynamic_cap = (
            int(value["rss_bytes"])
            + int(envelope["effective_available_bytes"])
            - int(envelope["reserve_bytes"])
        )
        cap = min(self.parent_cap, dynamic_cap)
        value.update(
            {
                "label": label,
                "memory_envelope": envelope,
                "launch_cap_bytes": cap,
                "parent_tree_cap_bytes": self.parent_cap,
                "inventory_memory_cap_bytes": self.inventory_cap,
                "inventory_used_bytes": self.inventory_used_bytes,
                "inventory_peak_bytes": self.inventory_peak_bytes,
                "workspace_live_bytes": self.workspace_live_bytes,
                "workspace_peak_bytes": self.workspace_peak_bytes,
                "cap_policy": "min(parent_tree_cap,current_tree_rss+available-reserve)",
                "inventory_policy": "independent_live_matrix_factor_coupling_workspace_sum",
            }
        )
        _append_jsonl(self.resources_path, value)
        if (
            not value["all_status_readable"]
            or int(value["swap_bytes"]) != 0
            or int(envelope["effective_available_bytes"]) < int(envelope["reserve_bytes"])
            or int(value["rss_bytes"]) >= cap
            or (
                self.inventory_cap is not None
                and self.inventory_used_bytes > int(self.inventory_cap)
            )
            or self.workspace_live_bytes > self.workspace_cap
        ):
            raise V14ResourceStop(f"V14 {self.stage} resource gate failed: {value}")
        return value

def _abi_facts() -> dict[str, Any]:
    from .fine_reference_preflight import qualified_abi

    return qualified_abi()


def _v14_known_preallocation_gate(
    runtime: _V14Runtime,
    stage: str,
    *,
    include_common: bool = True,
    include_matrices: bool = True,
) -> None:
    """Gate known allocations at the point where their live peers exist.

    The common-cache estimate is checked before constructing the common core.
    The Q1/Q2 sparse-object estimate is checked later, after the common core
    and reviewed RHS packets are live and immediately before volume creation.
    Thus the second check uses the sampled RSS containing the actual common
    objects rather than an empty-process estimate.
    """

    p6_storage_rows = 173802
    p4_storage_rows = 53084
    p4_volume_nnz = 24730144
    p4_augmented_rows = 53164
    p4_augmented_nnz = 24730144
    port_count = 80
    index_bytes = 4
    scalar_bytes = 16

    # This is an auditable count-based estimate for retained common payloads:
    # four volume component actions, two metric actions, two known 6-to-4
    # transfer plan/cache families, and the two 80-port carriers.  The
    # allowance terms are derived conservative estimates from the review
    # inventory assumptions; they are not mathematical strict upper bounds.
    component_vectors = 4 * (p6_storage_rows + p4_storage_rows) * scalar_bytes * 8
    component_indices = 4 * (p6_storage_rows + p4_storage_rows) * index_bytes * 8
    metric_vectors = 2 * p6_storage_rows * scalar_bytes * 8
    transfer_and_owner_plan = 256 * 1024**2
    carrier_and_mode_metadata = 64 * 1024**2 + port_count * scalar_bytes * 8
    common_upper = (
        component_vectors
        + component_indices
        + metric_vectors
        + transfer_and_owner_plan
        + carrier_and_mode_metadata
    )
    common_facts = {
        "stage": stage,
        "allocation_bytes": int(common_upper),
        "estimate_classification": "derived_conservative_estimate",
        "strict_upper_bound": False,
        "formula": {
            "component_vectors": "4*(N6_storage+N4_storage)*16*8",
            "component_indices": "4*(N6_storage+N4_storage)*4*8",
            "metric_vectors": "2*N6_storage*16*8",
            "transfer_and_owner_plan": (
                "implementation-derived 256MiB estimate from current owner-routing "
                "arrays and plan storage; not separately calibrated"
            ),
            "carrier_and_mode_metadata": (
                "implementation-derived 64MiB estimate for current carrier/mode "
                "metadata plus 80*16*8; not separately calibrated"
            ),
        },
        "assumptions": [
            "common component arrays and index maps remain resident through Q1/Q2",
            "the 256MiB and 64MiB terms cover implementation-dependent metadata",
            "these implementation estimates are conservative but not strict allocation proofs",
        ],
        "counts": {
            "p6_storage_rows": p6_storage_rows,
            "p4_storage_rows": p4_storage_rows,
            "port_count": port_count,
        },
        "gate": "known_common_payload_before_build",
    }
    if include_common:
        runtime.check_projected("common_setup_preallocation", common_upper)
        runtime.marker("v14_common_preallocation_gate", common_facts)

    if not include_matrices:
        return

    volume_payload = (p4_storage_rows + 1) * index_bytes + p4_volume_nnz * (
        index_bytes + scalar_bytes
    )
    augmented_payload = (p4_augmented_rows + 1) * index_bytes + p4_augmented_nnz * (
        index_bytes + scalar_bytes
    )
    if stage == "Q1_FULL_DIRECT":
        pair_upper = volume_payload + augmented_payload + 128 * 1024**2
        runtime.check_projected(
            "q1_original_volume_and_augmented_preallocation", pair_upper
        )
        runtime.marker(
            "q1_original_sparse_preallocation_gate",
            {
                "volume_rows": p4_storage_rows,
                "volume_nnz_upper": p4_volume_nnz,
                "volume_payload_bytes": volume_payload,
                "augmented_rows": p4_augmented_rows,
                "augmented_nnz_upper": p4_augmented_nnz,
                "augmented_payload_bytes": augmented_payload,
                "temporary_workspace_upper_bytes": 128 * 1024**2,
                "simultaneous_upper_bytes": pair_upper,
                "estimate_classification": "derived_conservative_estimate",
                "strict_upper_bound": False,
                "allowance_basis": (
                    "implementation-derived 128MiB temporary assembly estimate from "
                    "sparse-construction and packet-copy assumptions; not separately calibrated"
                ),
                "gate": "volume_and_augmented_sparse_objects_live_together",
            },
        )
    elif stage == "Q2_SCHUR_DIRECT":
        runtime.check_projected(
            "q2_full_and_active_volume_preallocation",
            volume_payload * 2 + 64 * 1024**2,
        )
        runtime.marker(
            "q2_volume_preallocation_gate",
            {
                "full_volume_payload_upper_bytes": volume_payload,
                "active_volume_payload_upper_bytes": volume_payload,
                "temporary_workspace_upper_bytes": 64 * 1024**2,
                "simultaneous_upper_bytes": volume_payload * 2 + 64 * 1024**2,
                "estimate_classification": "derived_conservative_estimate",
                "strict_upper_bound": False,
                "allowance_basis": (
                    "implementation-derived 64MiB temporary submatrix estimate from "
                    "active-volume construction assumptions; not separately calibrated"
                ),
                "gate": "full_and_active_sparse_objects_overlap_during_submatrix",
            },
        )
    elif stage == "Q3_INTERFACE_CONTROL":
        runtime.check_projected(
            "q3_full_and_active_volume_preallocation",
            volume_payload * 2 + 128 * 1024**2,
        )
        runtime.marker(
            "q3_volume_preallocation_gate",
            {
                "full_storage_payload_upper_bytes": volume_payload,
                "active_payload_upper_bytes": volume_payload,
                "temporary_workspace_upper_bytes": 128 * 1024**2,
                "simultaneous_upper_bytes": volume_payload * 2 + 128 * 1024**2,
                "estimate_classification": "derived_conservative_estimate",
                "strict_upper_bound": False,
                "allowance_basis": (
                    "implementation-derived active-volume and Schur construction "
                    "allowance; not a measured sparse payload"
                ),
                "gate": "q3_full_and_active_sparse_objects_before_matrix_free_release",
            },
        )
    elif stage == "Q0_CORE":
        volume_upper = volume_payload + 64 * 1024**2
        runtime.check_projected("q0_p4_volume_preallocation", volume_upper)
        runtime.marker(
            "q0_volume_preallocation_gate",
            {
                "volume_rows": p4_storage_rows,
                "volume_nnz_upper": p4_volume_nnz,
                "volume_payload_upper_bytes": volume_payload,
                "temporary_workspace_upper_bytes": 64 * 1024**2,
                "simultaneous_upper_bytes": volume_upper,
                "estimate_classification": "derived_conservative_estimate",
                "strict_upper_bound": False,
                "allowance_basis": (
                    "implementation-derived 64MiB temporary volume-assembly estimate; "
                    "not separately calibrated"
                ),
                "gate": "single_p4_volume_before_q0_partition_and_core",
            },
        )


def _build_common(runtime: _V14Runtime, cfg: Any) -> dict[str, Any]:
    from mpi4py import MPI
    from src.solvers.fullspace_physical_intermediate_runtime import (
        fine_volume_quadrature_metadata,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg import (
        build_same_mesh_hcurl_transfer,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
        build_same_mesh_hcurl_owner_transfer,
    )
    from src.solvers.physical_error_metric import LosslessFEMetric

    runtime.set_phase("setup")
    runtime.marker("v14_common_setup_started", {"levels": [6, 4]})
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_WORLD, (6, 4), include_positive_coefficients=True
    )
    runtime.sample("same_mesh_levels")
    quadrature, integral_records = fine_volume_quadrature_metadata(levels, cfg)
    runtime.marker(
        "v14_fine_quadrature_complete",
        {"quadrature": quadrature, "integrals": integral_records},
    )
    fine = build_same_mesh_physical_action(
        levels, cfg, 6, volume_quadrature_metadata=quadrature
    )
    runtime.sample("fine_physical_action")
    mode_inventory = (fine["modes"], fine["mode_rows"], fine["mode_sha256"])
    p4 = build_same_mesh_physical_action(
        levels,
        cfg,
        4,
        mode_inventory=mode_inventory,
        volume_quadrature_metadata=quadrature,
    )
    runtime.sample("p4_physical_action")
    local_transfer = build_same_mesh_hcurl_transfer(6, 4)
    transfer = build_same_mesh_hcurl_owner_transfer(
        levels["spaces"][6],
        levels["floquets"][6],
        levels["spaces"][4],
        levels["floquets"][4],
        local_transfer=local_transfer,
    )
    runtime.marker("v14_p64_transfer_complete", dict(transfer=transfer.audit))
    metric = LosslessFEMetric(
        levels,
        6,
        cfg.k0,
        quadrature,
        build_cell_basis=False,
    )
    runtime.marker("v14_degree6_metric_complete", dict(metric=metric.audit))
    warm_p4 = _new_storage_vector(levels["spaces"][4])
    warm_p6 = None
    try:
        warm_p4.set(0)
        warm_p6 = transfer.apply_primal(warm_p4)
        metric.mass(np.zeros(metric.mass.indices.size, dtype=np.complex128))
        metric.curl(np.zeros(metric.curl.indices.size, dtype=np.complex128))
    finally:
        if warm_p6 is not None:
            warm_p6.destroy()
        warm_p4.destroy()
    runtime.sample("v14_common_evaluation_warmup")

    def required_int(mapping: Mapping[str, Any], key: str, label: str) -> int:
        value = mapping.get(key)
        if type(value) is not int or value < 0:
            raise RuntimeError(f"{label} is missing a non-negative integer {key}")
        return int(value)

    def audited_numeric_components(owner: Any, prefix: str) -> dict[str, int]:
        audit = getattr(owner, "audit", None)
        if not isinstance(audit, Mapping):
            raise RuntimeError(f"{prefix} has no retained numeric payload audit")
        components = audit.get("retained_numeric_payload_components")
        if not isinstance(components, Mapping):
            raise RuntimeError(f"{prefix} retained numeric payload components are missing")
        # The retained component names are the auditable keys; keep them
        # individually visible in the inventory rather than replacing them
        # with a default total.
        return {
            f"{prefix}_{str(key)}": required_int(components, str(key), prefix)
            for key in components
        }

    def add_component_audit(
        target: dict[str, int], owner: Any, prefix: str
    ) -> None:
        target.update(audited_numeric_components(owner, prefix))

    metric_vector_bytes = sum(
        int(getattr(action.source, "array", np.empty(0)).nbytes)
        + int(getattr(action.target, "array", np.empty(0)).nbytes)
        for action in (metric.mass, metric.curl)
    )
    transfer_audit = dict(transfer.audit)
    routing_costs = dict(getattr(transfer, "routing_costs", {}))
    transfer_audit["routing_costs"] = routing_costs
    common_inventory: dict[str, int] = {
        "p64_local_cache_bytes": required_int(
            transfer_audit, "local_cache_array_bytes", "P64 transfer audit"
        ),
        "p64_owner_plan_bytes": required_int(
            routing_costs, "plan_bytes", "P64 transfer routing audit"
        ),
        "p64_work_vector_bytes": int(
            16
            * (
                int(transfer_audit.get("fine_local_owned_rows", 0))
                + int(transfer_audit.get("coarse_local_owned_rows", 0))
            )
        ),
        "degree6_metric_vector_bytes": metric_vector_bytes,
    }
    for degree, bundle in ((6, fine), (4, p4)):
        volume_action = bundle["volume_action"]
        component_actions = getattr(volume_action, "component_actions", None)
        if not isinstance(component_actions, Mapping):
            raise RuntimeError(f"p{degree} volume action component audit is missing")
        for component_name, action in component_actions.items():
            add_component_audit(
                common_inventory,
                action,
                f"p{degree}_volume_{component_name}",
            )
        dtn_audit = bundle["dtn_action"].audit
        for key in (
            "retained_numeric_bytes_local",
            "retained_identity_bytes",
            "bounded_work_bytes_local",
            "recovery_output_bytes",
        ):
            common_inventory[f"p{degree}_dtn_{key}"] = required_int(
                dtn_audit, key, f"p{degree} DtN audit"
            )
    for component_name, action in metric.actions.items():
        add_component_audit(
            common_inventory,
            action,
            f"degree6_metric_{component_name}",
        )
    # This registration records objects that are already live.  The preceding
    # samples are the RSS gate for their construction; inventory registration
    # must not count the same allocation a second time as a projected RSS.
    runtime.reserve_inventory(
        "common_fixed_caches", common_inventory, check_rss=False
    )
    runtime.marker(
        "v14_common_setup_complete",
        {
            "levels": sorted(int(value) for value in levels["spaces"]),
            "mode_count": len(fine["modes"]),
            "mode_sha256": fine["mode_sha256"],
            "quadrature": quadrature,
            "transfer": transfer_audit,
            "metric": metric.audit,
            "common_inventory": common_inventory,
        },
    )
    return {
        "levels": levels,
        "fine": fine,
        "p4": p4,
        "cfg": cfg,
        "quadrature": quadrature,
        "integral_records": integral_records,
        "transfer": transfer,
        "local_transfer": local_transfer,
        "metric": metric,
        "common_inventory_label": "common_fixed_caches",
    }


def _destroy_common(common: dict[str, Any], runtime: _V14Runtime | None = None) -> None:
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    metric = common.pop("metric", None)
    if metric is not None:
        metric.destroy()
    transfer = common.pop("transfer", None)
    if transfer is not None:
        transfer.destroy()
    local_transfer = common.pop("local_transfer", None)
    # ``SameMeshHcurlTransfer`` is an immutable NumPy map without a destroy
    # method; the owner wrapper has already dropped its reference to it.
    del local_transfer
    for name in ("p4", "fine"):
        bundle = common.pop(name, None)
        if bundle is not None:
            destroy_same_mesh_physical_action(bundle)
    common.pop("levels", None)
    if runtime is not None:
        runtime.release_inventory(common.pop("common_inventory_label", "common_fixed_caches"))
    gc.collect()


def _release_reviewed_rhs(rhs_records: list[dict[str, Any]] | None) -> None:
    """Drop large reviewed RHS/reference arrays before the common cleanup RSS sample."""

    if rhs_records is None:
        return
    for record in rhs_records:
        for key in ("rhs", "reference_solution", "reference_A4y", "reference_map"):
            record.pop(key, None)
    rhs_records.clear()
    gc.collect()


def _prepare_reviewed_rhs(
    runtime: _V14Runtime,
    common: Mapping[str, Any],
    resolved_payload: Mapping[str, Any],
    root: Path,
    storage_rows: int,
) -> list[dict[str, Any]]:
    """Bind the frozen packets to the freshly rebuilt p4 map and physics."""

    from src.solvers.condensed_fine_reference import native_map_arrays

    runtime.marker("v14_reviewed_rhs_loading_started", {})
    records = _load_rhs_and_reference(root, storage_rows)
    current_map = native_map_arrays(
        common["levels"]["spaces"][4], common["levels"]["floquets"][4]
    )
    current_map6 = native_map_arrays(
        common["levels"]["spaces"][6], common["levels"]["floquets"][6]
    )
    identity_records = []
    for item in records:
        reference_map = item["reference_map"]
        missing = sorted(set(current_map) - set(reference_map))
        if missing or any(
            key not in reference_map or not np.array_equal(current_map[key], reference_map[key])
            for key in current_map
        ):
            raise ValueError(f"{item['stem']} fresh p4 native constraint map differs")
        reference_identity = item.get("reference_identity") or {}
        expected_mode = reference_identity.get("mode_sha256")
        expected_physical = reference_identity.get("original_physical_sha256")
        actual_mode = str(common["p4"]["mode_sha256"])
        actual_physical = resolved_payload["provenance"]["physical_model_sha256"]
        if expected_mode is not None and actual_mode != expected_mode:
            raise ValueError(f"{item['stem']} fresh mode identity differs")
        if expected_physical is not None and actual_physical != expected_physical:
            raise ValueError(f"{item['stem']} fresh physical identity differs")
        source = _storage_rhs(common["levels"]["spaces"][4], item["reference_solution"])
        native = source.duplicate()
        try:
            common["p4"]["physical_action"].apply(source, native)
            difference = np.asarray(native.array - item["reference_A4y"], dtype=np.complex128)
            scale = max(float(np.linalg.norm(item["reference_A4y"])), np.finfo(float).tiny)
            a4_relative = float(np.linalg.norm(difference)) / scale
        finally:
            native.destroy()
            source.destroy()
        if a4_relative > 1.0e-10:
            raise ValueError(f"{item['stem']} saved A4y differs from fresh p4 physics")
        identity_records.append(
            {
                "stem": item["stem"],
                "logical_rhs": item["logical_rhs"],
                "calibration_identity": item["calibration_identity"],
                "reference_identity": reference_identity,
                "fresh_physical_model_sha256": actual_physical,
                "fresh_mode_sha256": actual_mode,
                "fresh_p4_map": {
                    key: _jsonable(value) for key, value in current_map.items()
                },
                "fresh_p6_map": {
                    key: _jsonable(value) for key, value in current_map6.items()
                },
                "fresh_A4y_relative_to_saved": a4_relative,
            }
        )
    _save_packet(
        runtime.directory,
        "reviewed_rhs_identity",
        {
            "schema": "task039extra.v14.reviewed-rhs-identity.v1",
            "source_sha": runtime.source_sha,
            "rhs_count": len(records),
            "ordered_stems": [item["stem"] for item in records],
            "records": identity_records,
        },
        runtime=runtime,
    )
    runtime.marker(
        "v14_reviewed_rhs_loading_complete",
        {
            "count": len(records),
            "ordered_stems": [item["stem"] for item in records],
            "mode_sha256": common["p4"]["mode_sha256"],
        },
    )
    return records


def _assemble_volume(
    runtime: _V14Runtime,
    common: Mapping[str, Any],
    *,
    inventory_label: str | None = None,
) -> Any:
    import dolfinx_mpc
    from src.solvers.fullspace_v17_p3_oracle import compile_physical_diagnostic_volume

    setup = common["levels"]
    cfg = common["cfg"]
    degree = 4
    runtime.set_phase("assembly")
    runtime.marker("v14_p4_volume_compile_started", {})
    compiled = compile_physical_diagnostic_volume(
        setup, cfg, degree, volume_quadrature_metadata=common["quadrature"]
    )
    floquet = setup["floquets"][degree]
    volume = dolfinx_mpc.cpp.mpc.create_matrix(
        compiled._cpp_object, floquet.mpc._cpp_object, floquet.mpc._cpp_object
    )
    try:
        runtime.sample("p4_volume_pattern")
        dolfinx_mpc.assemble_matrix(compiled, floquet.mpc, bcs=[], A=volume)
        volume.assemble()
        volume_info = volume.getInfo()
        runtime.marker(
            "v14_p4_volume_complete",
            {"size": list(volume.getSize()), "matrix_info": volume_info},
        )
        runtime.sample("p4_volume_complete")
        if inventory_label is not None:
            runtime.check_inventory_projected(
                inventory_label,
                _sparse_payload_bytes(volume_info, int(volume.getSize()[0])),
            )
            runtime.reserve_inventory(
                inventory_label,
                {
                    "matrix_payload_bytes": _sparse_payload_bytes(
                        volume_info, int(volume.getSize()[0])
                    )
                },
                check_rss=False,
            )
        return volume
    except BaseException:
        volume.destroy()
        raise
    finally:
        del compiled


def _new_storage_vector(space: Any) -> Any:
    from dolfinx.la.petsc import create_vector

    return create_vector([(space.dofmap.index_map, space.dofmap.index_map_bs)])


def _sparse_payload_bytes(matrix_info: Mapping[str, Any], rows: int) -> int:
    from petsc4py import PETSc

    nnz = int(matrix_info.get("nz_allocated", 0))
    return (int(rows) + 1) * np.dtype(PETSc.IntType).itemsize + nnz * (
        np.dtype(PETSc.IntType).itemsize + np.dtype(PETSc.ScalarType).itemsize
    )


def _mumps_memory_observation(facts: Mapping[str, Any]) -> dict[str, Any]:
    raw = facts.get("numeric_raw")
    if not isinstance(raw, Mapping) or not isinstance(raw.get("infog"), Mapping):
        raise RuntimeError("V11 numeric factor did not return MUMPS INFOG")
    infog = raw["infog"]
    values: dict[str, int] = {}
    for key in ("19", "22"):
        value = infog.get(key)
        if type(value) is not int or value < 0:
            raise RuntimeError(f"V11 numeric MUMPS INFOG({key}) is unavailable")
        values[key] = int(value)
    return {
        "unit": "decimal_MB",
        "unit_bytes": 1_000_000,
        "infog19_allocated_mb": values["19"],
        "infog22_used_mb": values["22"],
        "infog19_allocated_bytes_upper": (values["19"] + 1) * 1_000_000,
        "infog22_used_bytes_upper": (values["22"] + 1) * 1_000_000,
        "raw_infog19_and_22": {"19": values["19"], "22": values["22"]},
        "allocation_is_not_inferred_from_icntl23": True,
    }


def _factor_inventory_components(facts: Mapping[str, Any]) -> dict[str, int]:
    rows = int(facts["rows"])
    matrix_info = facts.get("matrix_info_after_factor") or facts["matrix_info_before_factor"]
    request_bytes = int(
        facts["memory_request"]["requested_memory_limit_mb"]
    ) * 1_000_000
    if "numeric_raw" in facts:
        factor_bytes = int(
            _mumps_memory_observation(facts)["infog19_allocated_bytes_upper"]
        )
        factor_key = "factor_infog19_allocated_bytes_upper"
    else:
        factor_bytes = request_bytes
        factor_key = "factor_memory_package_requested_bytes"
    components = {
        "matrix_payload_bytes": _sparse_payload_bytes(matrix_info, rows),
        factor_key: factor_bytes,
    }
    for key, value in dict(facts.get("inventory_components", {})).items():
        components[str(key)] = components.get(str(key), 0) + int(value)
    return components


def _factor_gates(
    runtime: _V14Runtime,
    *,
    local_limit: bool = False,
    matrix_already_reserved: bool = False,
):
    local_cap = int(
        runtime.contract["resources"]["local_factor_matrix_and_allocated_cap_bytes"]
    )
    interface_cap = int(
        runtime.contract["resources"]["interface_matrix_factor_solve_cap_bytes"]
    )

    def before(facts: Mapping[str, Any]) -> None:
        label = str(facts.get("label", ""))
        components = _factor_inventory_components(facts)
        facts["factor_inventory_components"] = dict(components)
        if matrix_already_reserved:
            components["matrix_payload_bytes"] = 0
        matrix_bytes = int(components["matrix_payload_bytes"])
        request_bytes = int(
            components.get(
                "factor_memory_package_requested_bytes",
                components.get("factor_infog19_allocated_bytes_upper", 0),
            )
        )
        if local_limit and label.startswith("internal_") and matrix_bytes + request_bytes > local_cap:
            raise V14ResourceStop(
                "local internal factor matrix+requested allocation exceeds 512MiB"
            )
        if label.startswith("coarse_E") and matrix_bytes + request_bytes > interface_cap:
            raise V14ResourceStop(
                "coarse E matrix+factor+solve allocation exceeds 64MiB"
            )
        runtime.check_inventory_projected(label, sum(components.values()))
        runtime.marker("v14_factor_pre_numeric_gate", dict(facts))
        # The matrix is already resident at this point; only the new factor
        # package and its temporary solve workspace are projected against RSS.
        runtime.check_projected(label, request_bytes)

    def after(facts: Mapping[str, Any]) -> None:
        facts["mumps_memory_observation"] = _mumps_memory_observation(facts)
        complete_components = _factor_inventory_components(facts)
        facts["factor_inventory_components"] = dict(complete_components)
        components = dict(complete_components)
        if matrix_already_reserved:
            components["matrix_payload_bytes"] = 0
        allocated_bytes = int(
            components.get("factor_infog19_allocated_bytes_upper", 0)
        )
        matrix_bytes = int(components.get("matrix_payload_bytes", 0))
        if (
            local_limit
            and str(facts.get("label", "")).startswith("internal_")
            and matrix_bytes + allocated_bytes > local_cap
        ):
            raise V14ResourceStop(
                "local internal factor matrix+INFOG(19) allocation exceeds 512MiB"
            )
        runtime.sample(f"{facts.get('label')}_post_numeric")
        runtime.reserve_inventory(
            str(facts.get("label")),
            components,
            check_rss=False,
        )
        runtime.marker("v14_factor_post_numeric_gate", dict(facts))

    return before, after


def _matrix_residual(matrix: Any, rhs: Any, solution: Any) -> float:
    applied = _matrix_residual_vector(matrix, rhs, solution)
    try:
        denominator = max(float(rhs.norm()), np.finfo(float).tiny)
        value = float(applied.norm()) / denominator
        if not np.isfinite(value):
            raise FloatingPointError("nonfinite explicit matrix residual")
        return value
    finally:
        applied.destroy()


def _matrix_residual_vector(matrix: Any, rhs: Any, solution: Any) -> Any:
    applied = matrix.createVecLeft()
    try:
        matrix.mult(solution, applied)
        applied.axpy(-1.0, rhs)
        return applied
    except BaseException:
        applied.destroy()
        raise


def _physical_residual(action: Any, rhs: Any, solution: Any) -> float:
    applied = solution.duplicate()
    try:
        action.apply(solution, applied)
        applied.axpy(-1.0, rhs)
        denominator = max(float(rhs.norm()), np.finfo(float).tiny)
        value = float(applied.norm()) / denominator
        if not np.isfinite(value):
            raise FloatingPointError("nonfinite native physical residual")
        return value
    finally:
        applied.destroy()


def _physical_residual_decomposition(
    action: Any,
    rhs: Any,
    solution: Any,
    partition: Any,
) -> dict[str, Any]:
    """Evaluate one native A4 residual and split it into I/Gamma pieces."""

    applied = solution.duplicate()
    try:
        action.apply(solution, applied)
        residual = np.asarray(
            rhs.array - applied.array,
            dtype=np.complex128,
        )
        denominator = max(
            float(np.linalg.norm(rhs.array)),
            np.finfo(float).tiny,
        )
        active = residual[partition.active_full_indices]
        interface = active[partition.gamma_active_indices]
        internal_parts = [active[block] for block in partition.internal_blocks_active]
        internal = (
            np.concatenate(internal_parts)
            if internal_parts
            else np.empty(0, dtype=np.complex128)
        )
        total_norm = float(np.linalg.norm(residual))
        internal_norm = float(np.linalg.norm(internal))
        interface_norm = float(np.linalg.norm(interface))
        partition_norm = float(np.hypot(internal_norm, interface_norm))
        return {
            "total_absolute_norm": total_norm,
            "total_relative": total_norm / denominator,
            "internal_absolute_norm": internal_norm,
            "internal_relative": internal_norm / denominator,
            "interface_absolute_norm": interface_norm,
            "interface_relative": interface_norm / denominator,
            "partition_absolute_norm": partition_norm,
            "partition_relative": partition_norm / denominator,
            "partition_residual_pythagorean_relative": abs(
                partition_norm - float(np.linalg.norm(active))
            )
            / max(float(np.linalg.norm(active)), np.finfo(float).tiny),
            "normalization": "full_storage_rhs_norm",
            "native_action_count": 1,
            "finite": bool(
                np.isfinite(total_norm)
                and np.isfinite(internal_norm)
                and np.isfinite(interface_norm)
            ),
        }
    finally:
        applied.destroy()


def _field_metrics(
    runtime: _V14Runtime,
    common: Mapping[str, Any],
    solution_arrays: list[np.ndarray],
    references: list[np.ndarray],
) -> list[dict[str, Any]]:
    from src.solvers.physical_error_diagnostics import metric_square

    runtime.set_phase("evaluation")
    runtime.marker("v14_field_metrics_started", {})
    metric = common["metric"]
    transfer = common["transfer"]
    indices = metric.mass.indices
    result = []
    for solution, reference in zip(solution_arrays, references, strict=True):
        solution_p4 = _storage_rhs(common["levels"]["spaces"][4], solution)
        reference_p4 = _storage_rhs(common["levels"]["spaces"][4], reference)
        solution_p6 = reference_p6 = None
        try:
            solution_p6 = transfer.apply_primal(solution_p4)
            reference_p6 = transfer.apply_primal(reference_p4)
            fine_solution = np.asarray(solution_p6.array[indices], dtype=np.complex128)
            fine_reference = np.asarray(reference_p6.array[indices], dtype=np.complex128)
            delta = fine_solution - fine_reference
            fields = {}
            for name, action in (("L2", metric.mass), ("scaled_curl", metric.curl)):
                error_norm = float(np.sqrt(metric_square(action, delta)))
                reference_norm = float(np.sqrt(metric_square(action, fine_reference)))
                fields[name] = {
                    "absolute_error_norm": error_norm,
                    "reference_norm": reference_norm,
                    "relative": error_norm
                    / max(reference_norm, np.finfo(float).tiny),
                }
            result.append(
                {
                    "field_l2_relative": fields["L2"]["relative"],
                    "scaled_curl_relative": fields["scaled_curl"]["relative"],
                    "fields": fields,
                    "evaluation_space": "P64_primal_to_degree6_independent",
                    "metric_degree": 6,
                    "metric_cell_basis_built": False,
                }
            )
        finally:
            if solution_p6 is not None:
                solution_p6.destroy()
            if reference_p6 is not None:
                reference_p6.destroy()
            solution_p4.destroy()
            reference_p4.destroy()
    runtime.marker(
        "v14_field_metrics_complete",
        {"count": len(result), "metric": metric.audit},
    )
    runtime.sample("field_metrics_complete")
    return result


def _augmented_residual_arrays(
    volume_action: Any,
    physical_action: Any,
    carrier: Any,
    rhs: Any,
    solution: Any,
    port_solution: np.ndarray,
) -> tuple[dict[str, float], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    native = volume_action.apply(solution)
    native_volume_top = np.asarray(native.array - rhs.array, dtype=np.complex128).copy()
    physical = solution.duplicate()
    try:
        physical_action.apply(solution, physical)
        native_A4_top = np.asarray(
            physical.array - rhs.array, dtype=np.complex128
        ).copy()
    finally:
        physical.destroy()
    augmented_top = native_volume_top.copy()
    for index, entry in enumerate(carrier.entries):
        if len(entry.coupling_rows):
            augmented_top[entry.coupling_rows] += (
                entry.coupling_values * port_solution[index]
            )
    port = np.asarray(
        [
            -np.dot(entry.projection_values, solution.array[entry.projection_rows])
            + entry.normalization_h * port_solution[index]
            for index, entry in enumerate(carrier.entries)
        ],
        dtype=np.complex128,
    )
    denominator = max(float(np.linalg.norm(rhs.array)), np.finfo(float).tiny)
    native_volume_relative = float(np.linalg.norm(native_volume_top)) / denominator
    native_A4_relative = float(np.linalg.norm(native_A4_top)) / denominator
    augmented_top_relative = float(np.linalg.norm(augmented_top)) / denominator
    port_relative = float(np.linalg.norm(port)) / denominator
    total_relative = float(
        np.sqrt(np.vdot(augmented_top, augmented_top).real + np.vdot(port, port).real)
    ) / denominator
    facts = {
        "native_A4_relative": native_A4_relative,
        "native_volume_top_relative": native_volume_relative,
        "augmented_top_relative": augmented_top_relative,
        "port_relative": port_relative,
        "augmented_total_relative": total_relative,
        "native_A4_norm": float(np.linalg.norm(native_A4_top)),
        "native_volume_top_norm": float(np.linalg.norm(native_volume_top)),
        "augmented_top_norm": float(np.linalg.norm(augmented_top)),
        "port_residual_norm": float(np.linalg.norm(port)),
    }
    return facts, native_A4_top, native_volume_top, augmented_top, port


def _core_action_checks(
    runtime: _V14Runtime,
    core: Any,
    common: Mapping[str, Any],
    storage_template: Any,
) -> dict[str, Any]:
    """Qualify block actions, local backsolves, adjoints and recovery identity."""

    runtime.set_phase("action_checks")
    gamma = core.V_GG.createVecRight()
    gamma_y = gamma.duplicate()
    gamma_mf = gamma.duplicate()
    gamma_explicit = gamma.duplicate()
    gamma_adjoint = gamma.duplicate()
    gamma_adj_explicit = gamma.duplicate()
    interface = core.interface_matrix.createVecRight()
    interface_mf = interface.duplicate()
    interface_explicit = interface.duplicate()
    zero_storage = storage_template.duplicate()
    try:
        gamma.array[:] = np.arange(gamma.getLocalSize(), dtype=np.float64) + 1j * 0.25
        gamma.array[:] /= max(float(gamma.norm()), 1.0)
        gamma_y.array[:] = 1.0 + 1j * np.arange(gamma_y.getLocalSize(), dtype=np.float64)
        gamma_y.array[:] /= max(float(gamma_y.norm()), 1.0)
        core.S_V.mult(gamma, gamma_explicit)
        core.apply_volume_schur(gamma, gamma_mf)
        core.S_V.multHermitian(gamma, gamma_adj_explicit)
        core.apply_volume_schur_adjoint(gamma, gamma_adjoint)
        interface.array[:] = np.arange(interface.getLocalSize(), dtype=np.float64) + 1j * 0.5
        interface.array[:] /= max(float(interface.norm()), 1.0)
        core.interface_matrix.mult(interface, interface_explicit)
        core.apply_interface_matrix_free(interface, interface_mf)

        zero_storage.set(0)
        recovered = core.recover(zero_storage, gamma)
        native_output = recovered.duplicate()
        volume_gamma = gamma.duplicate()
        schur_gamma = gamma.duplicate()
        physical = physical_adjoint = schur_y = adjoint_y = None
        try:
            common["p4"]["physical_action"].apply(recovered, native_output)
            native_gamma = native_output.array[core.partition.gamma_full_indices]
            physical = core.apply_physical_schur(gamma)
            physical_difference = np.linalg.norm(native_gamma - physical.array) / max(
                float(physical.norm()), np.finfo(float).tiny
            )
            physical_adjoint = core.apply_physical_schur_adjoint(gamma)
            expected_adjoint = gamma_adj_explicit.duplicate()
            try:
                expected_adjoint.array[:] = gamma_adj_explicit.array
                for entry in core.port_data:
                    value = np.dot(
                        np.conj(entry["b_values"]), gamma.array[entry["b_gamma"]]
                    ) / np.conj(entry["normalization_h"])
                    expected_adjoint.array[entry["d_gamma"]] += (
                        np.conj(entry["d_values"]) * value
                    )
                physical_adjoint_difference = np.linalg.norm(
                    physical_adjoint.array - expected_adjoint.array
                ) / max(float(expected_adjoint.norm()), np.finfo(float).tiny)
            finally:
                expected_adjoint.destroy()

            # ``g-A4F`` is checked in its internal and Gamma components using
            # the native volume blocks; the carrier contribution is qualified
            # separately by the physical Schur comparison above.
            core.V_GG.mult(gamma, volume_gamma)
            local_backsolve = []
            active_recovered = recovered.array[core.partition.active_full_indices]
            for item in core.internal:
                x_i = np.asarray(active_recovered[item.indices], dtype=np.complex128)
                rhs_i = np.zeros(item.indices.size, dtype=np.complex128)
                if item.gcols.size:
                    rhs_i -= item.A_i_g @ gamma.array[item.gcols]
                x_vec = item.matrix.createVecRight()
                residual_vec = item.matrix.createVecLeft()
                try:
                    x_vec.array[:] = x_i
                    item.matrix.mult(x_vec, residual_vec)
                    residual_vec.array[:] -= rhs_i
                    operation_scale = max(
                        float(np.linalg.norm(rhs_i)),
                        float(np.linalg.norm(residual_vec.array + rhs_i)),
                        np.finfo(float).tiny,
                    )
                    local_backsolve.append(
                        float(residual_vec.norm()) / operation_scale
                    )
                finally:
                    x_vec.destroy()
                    residual_vec.destroy()
                if item.grows.size:
                    volume_gamma.array[item.grows] += item.A_gi @ x_i
            core.S_V.mult(gamma, schur_gamma)
            gamma_decomposition = np.asarray(
                volume_gamma.array - schur_gamma.array, dtype=np.complex128
            )
            decomposition_scale = max(
                float(volume_gamma.norm()),
                float(schur_gamma.norm()),
                float(gamma.norm()),
                np.finfo(float).tiny,
            )
            gamma_decomposition_relative = (
                float(np.linalg.norm(gamma_decomposition)) / decomposition_scale
            )

            schur_y = core.apply_physical_schur(gamma_y)
            adjoint_y = core.apply_physical_schur_adjoint(gamma_y)
            lhs = complex(physical.dot(gamma_y))
            rhs_inner = complex(gamma.dot(adjoint_y))
            inner_scale = max(
                abs(lhs),
                abs(rhs_inner),
                float(physical.norm()) * float(gamma_y.norm()),
                np.finfo(float).tiny,
            )
            adjoint_inner_relative = abs(lhs - rhs_inner) / inner_scale
        finally:
            for value in (native_output, volume_gamma, schur_gamma):
                value.destroy()
            for value in (physical, physical_adjoint, schur_y, adjoint_y):
                if value is not None:
                    value.destroy()
            recovered.destroy()
        facts = {
            "volume_explicit_vs_matrix_free": _vec_relative(gamma_explicit, gamma_mf),
            "volume_adjoint_explicit_vs_matrix_free": _vec_relative(
                gamma_adj_explicit, gamma_adjoint
            ),
            "interface_explicit_vs_matrix_free": _vec_relative(
                interface_explicit, interface_mf
            ),
            "physical_schur_vs_native_carrier": float(physical_difference),
            "physical_schur_adjoint_formula": float(physical_adjoint_difference),
            "local_backsolve_original_matrix_max_relative": max(local_backsolve, default=0.0),
            "g_minus_A4F_internal_relative": max(local_backsolve, default=0.0),
            "g_minus_A4F_gamma_relative": gamma_decomposition_relative,
            "g_minus_A4F_operation_scale": decomposition_scale,
            "physical_schur_complex_inner_product_relative": float(adjoint_inner_relative),
            "factor_solve_counts_after_action_checks": _factor_solve_counts(core),
        }
        limits = {
            "action_bridge": 1.0e-10,
            "physical_schur": 1.0e-10,
            "local_backsolve": 1.0e-10,
            "adjoint_inner_product": 1.0e-10,
            "recovery_decomposition": 1.0e-10,
        }
        facts["limits"] = limits
        facts["passed"] = bool(
            facts["volume_explicit_vs_matrix_free"] <= limits["action_bridge"]
            and facts["volume_adjoint_explicit_vs_matrix_free"] <= limits["action_bridge"]
            and facts["interface_explicit_vs_matrix_free"] <= limits["action_bridge"]
            and facts["physical_schur_vs_native_carrier"] <= limits["physical_schur"]
            and facts["physical_schur_adjoint_formula"] <= limits["physical_schur"]
            and facts["local_backsolve_original_matrix_max_relative"] <= limits["local_backsolve"]
            and facts["g_minus_A4F_gamma_relative"] <= limits["recovery_decomposition"]
            and facts["physical_schur_complex_inner_product_relative"] <= limits["adjoint_inner_product"]
        )
        runtime.marker("v14_action_checks_complete", facts)
        runtime.sample("q2_action_checks_complete")
        return facts
    finally:
        for value in (
            gamma,
            gamma_y,
            gamma_mf,
            gamma_explicit,
            gamma_adjoint,
            gamma_adj_explicit,
            interface,
            interface_mf,
            interface_explicit,
            zero_storage,
        ):
            value.destroy()


def _vec_relative(left: Any, right: Any) -> float:
    difference = left.copy()
    try:
        difference.axpy(-1.0, right)
        return float(difference.norm()) / max(float(right.norm()), np.finfo(float).tiny)
    finally:
        difference.destroy()


def _factor_solve_counts(core: Any) -> dict[str, Any]:
    return {
        "internal": [int(getattr(item.factor, "solve_calls", 0)) for item in core.internal],
        "interface": None
        if core.interface_factor is None
        else int(getattr(core.interface_factor, "solve_calls", 0)),
        "internal_total": int(
            sum(int(getattr(item.factor, "solve_calls", 0)) for item in core.internal)
        ),
    }


def _q1_residual_arrays(
    common: Mapping[str, Any],
    reviewed: Mapping[str, Any],
    solution: Any,
    storage_rows: int,
) -> tuple[dict[str, float], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    storage = _storage_rhs(
        common["levels"]["spaces"][4], solution.array[:storage_rows]
    )
    rhs = _storage_rhs(common["levels"]["spaces"][4], reviewed["rhs"])
    try:
        return _augmented_residual_arrays(
            common["p4"]["volume_action"],
            common["p4"]["physical_action"],
            common["p4"]["dtn_action"].carrier,
            rhs,
            storage,
            np.asarray(solution.array[storage_rows:], dtype=np.complex128),
        )
    finally:
        storage.destroy()
        rhs.destroy()


def _q1_full_direct(
    runtime: _V14Runtime,
    common: dict[str, Any],
    rhs_records: list[dict[str, Any]],
) -> dict[str, Any]:
    from src.solvers.fullspace_p4_reference import build_reference_matrix
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
    from src.solvers.physical_interface_schur import _prepare_factor

    storage_rows = int(common["p4"]["dtn_action"].carrier.global_rows)
    if storage_rows != 53084:
        raise ValueError(f"V14 p4 carrier storage rows changed: {storage_rows}")
    workspace_label = "q1_augmentation_workspace"
    matrix = None
    factor = None
    factor_facts = None
    solutions: list[np.ndarray] = []
    solve_records: list[dict[str, Any]] = []

    def allocation_callback(facts: Mapping[str, Any]) -> None:
        volume_bytes = _sparse_payload_bytes(
            {"nz_allocated": facts["volume_nnz"]}, int(facts["volume_rows"])
        )
        augmented_bytes = int(facts["matrix_payload_bytes"])
        workspace = min(
            int(runtime.workspace_cap),
            16 * (int(facts["volume_rows"]) + int(facts["port_rows"])) * 16,
        )
        runtime.check_inventory_projected(
            "q1_augmented_matrix", volume_bytes + augmented_bytes
        )
        runtime.check_projected(
            "q1_augmented_matrix", augmented_bytes, workspace_bytes=workspace
        )
        runtime.reserve_workspace(workspace_label, workspace)

    runtime.set_phase("assembly")
    matrix, matrix_facts = build_reference_matrix(
        common["levels"],
        common["cfg"],
        common["p4"],
        common["quadrature"],
        marker=runtime.marker,
        sample=lambda: runtime.sample("q1_assembly"),
        degree=4,
        allocation_callback=allocation_callback,
    )
    runtime.release_workspace(workspace_label)
    before, after = _factor_gates(runtime)
    try:
        runtime.set_phase("factor")
        factor, factor_facts = _prepare_factor(
            matrix,
            _MumpsFactor,
            label="q1_full_global",
            resource_sample=lambda: runtime.sample("q1_factor"),
            marker=runtime.marker,
            pre_numeric_gate=before,
            post_numeric_gate=after,
        )
        for reviewed in rhs_records:
            runtime.set_phase("solve")
            runtime.marker("q1_rhs_solve_started", {"stem": reviewed["stem"]})
            started = time.perf_counter()
            rhs = matrix.createVecRight()
            rhs.set(0)
            rhs.array[:storage_rows] = reviewed["rhs"]
            solution = matrix.createVecRight()
            residual_vector = None
            try:
                solve_before = int(getattr(factor, "solve_calls", 0))
                factor.solve_repeated(rhs, solution)
                refinements = []
                for refinement_index in range(3):
                    if residual_vector is not None:
                        residual_vector.destroy()
                    residual_vector = _matrix_residual_vector(matrix, rhs, solution)
                    facts, native_A4, native_volume, augmented_top, port = _q1_residual_arrays(
                        common, reviewed, solution, storage_rows
                    )
                    if facts["native_A4_relative"] <= 1.0e-10:
                        break
                    if refinement_index == 2:
                        break
                    refine_started = time.perf_counter()
                    count_before = int(getattr(factor, "solve_calls", 0))
                    correction = matrix.createVecRight()
                    try:
                        factor.solve_repeated(residual_vector, correction)
                        solution.axpy(-1.0, correction)
                    finally:
                        correction.destroy()
                    refinements.append(
                        {
                            "index": refinement_index + 1,
                            "elapsed_seconds": time.perf_counter() - refine_started,
                            "factor_solve_calls_before": count_before,
                            "factor_solve_calls_after": int(getattr(factor, "solve_calls", 0)),
                            "trigger": "native_augmented_residual_above_1e-10",
                        }
                    )
                if residual_vector is None:
                    residual_vector = _matrix_residual_vector(matrix, rhs, solution)
                facts, native_A4, native_volume, augmented_top, port = _q1_residual_arrays(
                    common, reviewed, solution, storage_rows
                )
                solution_array = np.asarray(solution.array[:storage_rows]).copy()
                solutions.append(solution_array)
                solve_after = int(getattr(factor, "solve_calls", 0))
                solve_record = {
                    "stem": reviewed["stem"],
                    "elapsed_seconds": time.perf_counter() - started,
                    "matrix_relative_residual": float(residual_vector.norm())
                    / max(float(rhs.norm()), np.finfo(float).tiny),
                    "augmented_residual": facts,
                    "native_A4_relative_residual": facts["native_A4_relative"],
                    "native_volume_top_relative_residual": facts["native_volume_top_relative"],
                    "augmented_top_relative_residual": facts["augmented_top_relative"],
                    "augmented_total_relative_residual": facts["augmented_total_relative"],
                    "factor_solve_calls_before": solve_before,
                    "factor_solve_calls_after": solve_after,
                    "factor_solve_call_delta": solve_after - solve_before,
                    "refinements": refinements,
                    "solution_sha256": _sha256_bytes(
                        np.ascontiguousarray(solution_array).tobytes()
                    ),
                }
                packet = _save_packet(
                    runtime.directory / "q1_rhs_packets",
                    reviewed["stem"],
                    {
                        "schema": "task039extra.v14.q1-rhs-packet.v1",
                        "identity": {
                            key: value
                            for key, value in reviewed.items()
                            if key
                            not in {
                                "rhs",
                                "reference_solution",
                                "reference_A4y",
                                "reference_map",
                            }
                        },
                        "solve": solve_record,
                        "x_augmented": np.asarray(solution.array).copy(),
                        "x_storage": solution_array,
                        "matrix_residual": np.asarray(residual_vector.array).copy(),
                        "native_A4_residual": native_A4,
                        "native_volume_top_residual": native_volume,
                        "augmented_top_residual": augmented_top,
                        "port_residual": port,
                    },
                    runtime=runtime,
                )
                solve_record["packet"] = packet
                solve_records.append(solve_record)
            except BaseException as exc:
                _save_packet(
                    runtime.directory / "q1_rhs_packets",
                    reviewed["stem"] + "_failure",
                    {
                        "schema": "task039extra.v14.q1-rhs-failure-packet.v1",
                        "identity": {
                            key: value
                            for key, value in reviewed.items()
                            if key
                            not in {
                                "rhs",
                                "reference_solution",
                                "reference_A4y",
                                "reference_map",
                            }
                        },
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                        "factor_solve_calls": int(getattr(factor, "solve_calls", 0)),
                    },
                    runtime=runtime,
                )
                raise
            finally:
                if residual_vector is not None:
                    residual_vector.destroy()
                rhs.destroy()
                solution.destroy()
            runtime.sample(f"q1_rhs_{reviewed['stem']}_complete")
        field = _field_metrics(
            runtime,
            common,
            solutions,
            [item["reference_solution"] for item in rhs_records],
        )
        for solve, field_record, reviewed in zip(
            solve_records, field, rhs_records, strict=True
        ):
            solve["field_metrics"] = field_record
            solve["reference_true_residual"] = reviewed["reference_true_residual"]
        max_matrix = max(item["matrix_relative_residual"] for item in solve_records)
        max_native_A4 = max(item["native_A4_relative_residual"] for item in solve_records)
        max_augmented = max(
            item["augmented_total_relative_residual"] for item in solve_records
        )
        max_field = max(
            max(
                item["field_metrics"]["field_l2_relative"],
                item["field_metrics"]["scaled_curl_relative"],
            )
            for item in solve_records
        )
        # Review V14's numerical admission line is the original native A4
        # residual.  The assembled-matrix and augmented-vector residuals are
        # retained as diagnostics for investigating construction errors, but
        # they are not promoted to a second independent precision gate.
        exact_pass = max_native_A4 <= 1.0e-10
        field_pass = max_field <= 1.0e-8
        record = {
            "schema": "task039extra.v14.q1-full-direct.v2",
            "status": "Q1_FULL_DIRECT_PASS"
            if exact_pass and field_pass
            else "EXACT_CONTROL_UNQUALIFIED",
            "official_result": bool(exact_pass and field_pass),
            "rhs": [
                {
                    key: value
                    for key, value in item.items()
                    if key
                    not in {
                        "rhs",
                        "reference_solution",
                        "reference_A4y",
                        "reference_map",
                    }
                }
                for item in rhs_records
            ],
            "matrix": {**matrix_facts, "matrix_info": matrix.getInfo()},
            "factor": factor_facts,
            "solve_records": solve_records,
            "gates": {
                "native_A4_relative_residual": 1.0e-10,
                "field_l2_and_scaled_curl": 1.0e-8,
                "admission_basis": "original_A4_and_P64_field_metrics",
                "max_matrix_relative_residual": max_matrix,
                "max_native_A4_relative_residual": max_native_A4,
                "max_augmented_total_relative_residual": max_augmented,
                "matrix_and_augmented_residuals_are_diagnostics_only": True,
                "max_field_l2_or_scaled_curl": max_field,
            },
            "lifecycle": {
                "factor_count": 1,
                "factor_solve_count": int(getattr(factor, "solve_calls", 0)),
                "sequential_rhs": True,
                "factor_live_through_all_rhs_and_metrics": True,
            },
        }
        runtime.marker("q1_full_direct_complete", record)
        return record
    finally:
        runtime.release_workspace(workspace_label)
        if factor is not None:
            factor.destroy()
            runtime.release_inventory("q1_full_global")
        if matrix is not None:
            matrix.destroy()


def _storage_rhs(space: Any, values: np.ndarray) -> Any:
    result = _new_storage_vector(space)
    result.array[:] = values
    return result


def _save_atomic_npz(path: Path, arrays: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        np.savez(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _save_petsc_binary(path: Path, matrix: Any) -> None:
    from petsc4py import PETSc

    temporary = path.with_name(path.name + ".tmp")
    viewer = PETSc.Viewer().createBinary(
        str(temporary), "w", comm=matrix.getComm()
    )
    try:
        matrix.view(viewer)
        viewer.flush()
    finally:
        viewer.destroy()
    os.replace(temporary, path)


def _q2_state_artifact(
    runtime: _V14Runtime,
    root: Path,
    relative_path: str,
    writer: Any,
    *,
    workspace_bytes: int = 17 << 20,
) -> dict[str, Any]:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    label = f"q2_state_{path.name}"
    runtime.reserve_workspace(label, int(workspace_bytes))
    try:
        writer(path)
        # The hash is part of the same bounded save operation: the existing
        # chunked helper uses a 1 MiB streaming read buffer.
        descriptor = {
            "path": str(path),
            "relative_path": str(path.relative_to(root)),
            "bytes": int(path.stat().st_size),
            "sha256": _sha256_file(path),
        }
    finally:
        runtime.release_workspace(label)
    return descriptor


def _factor_count_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    internal = [
        int(right) - int(left)
        for left, right in zip(before["internal"], after["internal"], strict=True)
    ]
    interface = None
    if before.get("interface") is not None and after.get("interface") is not None:
        interface = int(after["interface"]) - int(before["interface"])
    return {
        "internal": internal,
        "interface": interface,
        "internal_total": int(sum(internal)),
    }


def _q2_interface_residual(
    core: Any,
    rhs: Any,
    interface_solution: np.ndarray,
) -> dict[str, Any]:
    started = time.perf_counter()
    reduced, port_rhs = core.reduce(rhs)
    interface_rhs = np.concatenate((reduced, port_rhs))
    interface_vector = core.interface_matrix.createVecRight()
    interface_applied = core.interface_matrix.createVecLeft()
    try:
        interface_vector.array[:] = interface_solution
        core.interface_matrix.mult(interface_vector, interface_applied)
        residual = np.asarray(
            interface_applied.array - interface_rhs, dtype=np.complex128
        ).copy()
    finally:
        interface_vector.destroy()
        interface_applied.destroy()
    original_rhs_norm = max(float(rhs.norm()), np.finfo(float).tiny)
    reduced_rhs_norm = max(float(np.linalg.norm(interface_rhs)), np.finfo(float).tiny)
    residual_norm = float(np.linalg.norm(residual))
    return {
        "reduced_rhs": np.asarray(reduced).copy(),
        "port_rhs": np.asarray(port_rhs).copy(),
        "interface_rhs": interface_rhs,
        "interface_residual": residual,
        # The first value is the only interface residual reported on the
        # original-RHS scale.  The reduced-RHS normalization is useful for
        # conditioning/debugging but is explicitly diagnostic rather than an
        # additional Review V14 admission gate.
        "original_rhs_norm": original_rhs_norm,
        "reduced_rhs_norm": reduced_rhs_norm,
        "interface_residual_norm": residual_norm,
        "interface_relative_residual": residual_norm / original_rhs_norm,
        "interface_relative_residual_original_rhs": residual_norm / original_rhs_norm,
        "interface_reduced_rhs_relative_residual": residual_norm / reduced_rhs_norm,
        "interface_residual_normalization": "original_storage_rhs_norm",
        "interface_reduced_rhs_normalization": "reduced_rhs_norm_diagnostic_only",
        "elapsed_seconds": time.perf_counter() - started,
    }


def _q2_residual_arrays(
    common: Mapping[str, Any],
    reviewed: Mapping[str, Any],
    solution: Any,
    interface_solution: np.ndarray,
    gamma_rows: int,
) -> tuple[dict[str, float], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    interface_solution = np.asarray(interface_solution, dtype=np.complex128)
    port_count = len(common["p4"]["dtn_action"].carrier.entries)
    if interface_solution.size != int(gamma_rows) + port_count:
        raise ValueError("Q2 interface solution has an unexpected Gamma/port layout")
    rhs = _storage_rhs(common["levels"]["spaces"][4], reviewed["rhs"])
    try:
        return _augmented_residual_arrays(
            common["p4"]["volume_action"],
            common["p4"]["physical_action"],
            common["p4"]["dtn_action"].carrier,
            rhs,
            solution,
            interface_solution[int(gamma_rows) :],
        )
    finally:
        rhs.destroy()


def _q2_reusable_state(runtime: _V14Runtime, core: Any) -> dict[str, Any]:
    """Persist the Q2 core incrementally without a global in-memory copy."""

    state_root = runtime.directory / "q2_reusable_state"
    state_root.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []

    def add(path: Path, kind: str, **facts: Any) -> None:
        artifacts.append({"kind": kind, **facts, "artifact": _jsonable(path)})

    runtime.marker("q2_reusable_state_save_started", {})
    partition_arrays: dict[str, Any] = {
        "active_full_indices": core.partition.active_full_indices,
        "slave_full_indices": core.partition.slave_full_indices,
        "gamma_full_indices": core.partition.gamma_full_indices,
        "gamma_active_indices": core.partition.gamma_active_indices,
        "port_support_full_indices": core.partition.port_support_full_indices,
    }
    for index, block in enumerate(core.partition.internal_blocks_full):
        partition_arrays[f"internal_block_{index}_full"] = block
        partition_arrays[f"internal_block_{index}_active"] = (
            core.partition.internal_blocks_active[index]
        )
    partition_path = _q2_state_artifact(
        runtime,
        runtime.directory,
        "q2_reusable_state/partition.npz",
        lambda path, arrays=partition_arrays: _save_atomic_npz(path, arrays),
    )
    add(Path(partition_path["path"]), "partition_arrays", descriptor=partition_path)
    del partition_arrays

    for name, matrix in (("S_V", core.S_V), ("V_GG", core.V_GG)):
        descriptor = _q2_state_artifact(
            runtime,
            runtime.directory,
            f"q2_reusable_state/{name}.petscbin",
            lambda path, matrix=matrix: _save_petsc_binary(path, matrix),
        )
        add(
            Path(descriptor["path"]),
            "petsc_matrix",
            name=name,
            shape=[int(value) for value in matrix.getSize()],
            matrix_info=matrix.getInfo(),
            descriptor=descriptor,
        )

    port_arrays: dict[str, Any] = {}
    for index, entry in enumerate(core.port_data):
        for key in ("b_gamma", "b_values", "b_full", "d_gamma", "d_values", "d_full"):
            port_arrays[f"port_{index:03d}_{key}"] = entry[key]
        port_arrays[f"port_{index:03d}_normalization_h"] = np.asarray(
            [entry["normalization_h"]], dtype=np.complex128
        )
    port_descriptor = _q2_state_artifact(
        runtime,
        runtime.directory,
        "q2_reusable_state/port_data.npz",
        lambda path, arrays=port_arrays: _save_atomic_npz(path, arrays),
    )
    add(
        Path(port_descriptor["path"]),
        "port_arrays",
        port_count=len(core.port_data),
        descriptor=port_descriptor,
    )
    del port_arrays

    internal_descriptors = []
    factor_records = list(core.factor_facts.get("internal", []))
    for index, item in enumerate(core.internal):
        coupling_arrays = {
            "indices": item.indices,
            "grows": item.grows,
            "gcols": item.gcols,
            "A_gi": item.A_gi,
            "A_i_g": item.A_i_g,
        }
        coupling_descriptor = _q2_state_artifact(
            runtime,
            runtime.directory,
            f"q2_reusable_state/internal_{index:02d}_coupling.npz",
            lambda path, arrays=coupling_arrays: _save_atomic_npz(path, arrays),
        )
        del coupling_arrays
        matrix_descriptor = _q2_state_artifact(
            runtime,
            runtime.directory,
            f"q2_reusable_state/internal_{index:02d}.petscbin",
            lambda path, matrix=item.matrix: _save_petsc_binary(path, matrix),
        )
        factor_record = factor_records[index] if index < len(factor_records) else {}
        metadata = {
            "schema": "task039extra.v14.q2-internal-state.v1",
            "block_index": int(item.block_index),
            "rows": int(item.indices.size),
            "grows": int(item.grows.size),
            "gcols": int(item.gcols.size),
            "factor_solve_calls_at_build": int(item.solve_calls_at_build),
            "factor": factor_record,
            "coupling": coupling_descriptor,
            "matrix": matrix_descriptor,
        }
        metadata_descriptor = _q2_state_artifact(
            runtime,
            runtime.directory,
            f"q2_reusable_state/internal_{index:02d}.json",
            lambda path, metadata=metadata: _write_json(path, metadata),
            workspace_bytes=1 << 20,
        )
        internal_descriptors.append(metadata_descriptor)
        add(
            Path(metadata_descriptor["path"]),
            "internal_block_metadata",
            block_index=index,
            descriptor=metadata_descriptor,
        )

    state = {
        "schema": "task039extra.v14.q2-reusable-core-state.v2",
        "source_sha": runtime.source_sha,
        "partition": core.partition.audit(),
        "internal_block_count": len(core.internal),
        "artifacts": artifacts,
        "internal_metadata": internal_descriptors,
        "omitted": [
            "interface_matrix",
            "global_interface_factor",
            "numeric_interface_solution",
        ],
        "factor_facts_summary": {
            "S_V": core.factor_facts.get("S_V"),
            "interface": {
                "rows": core.factor_facts.get("interface", {}).get("rows"),
                "matrix_info": core.factor_facts.get("interface", {}).get(
                    "matrix_info"
                ),
                "not_saved": True,
            },
        },
    }
    index_path = state_root / "index.json"
    runtime.reserve_workspace("q2_state_index", 1 << 20)
    try:
        _write_json(index_path, state)
        index_sha = _sha256_file(index_path)
    finally:
        runtime.release_workspace("q2_state_index")
    state["index"] = {
        "path": str(index_path),
        "relative_path": str(index_path.relative_to(runtime.directory)),
        "bytes": int(index_path.stat().st_size),
        "sha256": index_sha,
    }
    runtime.marker("q2_reusable_state_save_complete", state["index"])
    return state


def _q2_reference_elimination_checks(
    runtime: _V14Runtime,
    core: Any,
    common: Mapping[str, Any],
    rhs_records: list[dict[str, Any]],
    storage_template: Any,
) -> dict[str, Any]:
    """Check the existing ``g, y, A4y`` packets against the fresh Schur core."""

    gamma_full = core.partition.gamma_full_indices
    gamma_active = core.partition.gamma_active_indices
    records: list[dict[str, Any]] = []
    for reviewed in rhs_records:
        started = time.perf_counter()
        rhs = storage_template.copy()
        rhs.array[:] = reviewed["rhs"]
        reference_y = np.asarray(reviewed["reference_solution"], dtype=np.complex128)
        reference_A4y = np.asarray(reviewed["reference_A4y"], dtype=np.complex128)
        try:
            rhs_norm = float(np.linalg.norm(reviewed["rhs"]))
            counts_before = _factor_solve_counts(core)
            elimination_started = time.perf_counter()
            f_gamma, _port_rhs = core.reduce(rhs)
            elimination_seconds = time.perf_counter() - elimination_started
            elimination_after = _factor_solve_counts(core)

            y_gamma = core.V_GG.createVecRight()
            volume_schur_y = core.S_V.createVecLeft()
            try:
                y_gamma.array[:] = reference_y[gamma_full]
                core.S_V.mult(y_gamma, volume_schur_y)
                physical_schur_array = np.asarray(
                    volume_schur_y.array, dtype=np.complex128
                ).copy()
                for entry in core.port_data:
                    h = entry["normalization_h"]
                    if h == 0:
                        raise ZeroDivisionError("reference port normalization H is zero")
                    alpha = np.dot(
                        entry["d_values"], reference_y[entry["d_full"]]
                    ) / h
                    physical_schur_array[entry["b_gamma"]] += (
                        entry["b_values"] * alpha
                    )
                expected_gamma = np.asarray(
                    f_gamma - physical_schur_array, dtype=np.complex128
                ).copy()
            finally:
                volume_schur_y.destroy()
                y_gamma.destroy()

            active_rhs = np.asarray(
                reviewed["rhs"][core.partition.active_full_indices],
                dtype=np.complex128,
            )
            active_reference = np.asarray(
                reference_y[core.partition.active_full_indices],
                dtype=np.complex128,
            )
            local_records: list[dict[str, Any]] = []
            recovery_started = time.perf_counter()
            recovered_result, recovery_facts = core.recover(
                rhs,
                np.asarray(reference_y[gamma_full], dtype=np.complex128),
                return_facts=True,
            )
            recovery_seconds = time.perf_counter() - recovery_started
            counts_after = _factor_solve_counts(core)
            try:
                recovered_active = np.asarray(
                    recovered_result.array[core.partition.active_full_indices],
                    dtype=np.complex128,
                ).copy()
                for item in core.internal:
                    local_rhs = active_rhs[item.indices].copy()
                    if item.gcols.size:
                        local_rhs -= item.A_i_g @ recovered_active[
                            gamma_active[item.gcols]
                        ]
                    recovered_local = recovered_active[item.indices]
                    local_residual = item.matrix.createVecLeft()
                    local_vector = item.matrix.createVecRight()
                    try:
                        local_vector.array[:] = recovered_local
                        item.matrix.mult(local_vector, local_residual)
                        local_residual.array[:] -= local_rhs
                        local_scale = max(
                            float(np.linalg.norm(local_rhs)),
                            float(np.linalg.norm(local_residual.array + local_rhs)),
                            np.finfo(float).tiny,
                        )
                        local_records.append(
                            {
                                "block_index": int(item.block_index),
                                "rows": int(item.indices.size),
                                "relative_residual": float(local_residual.norm())
                                / local_scale,
                                "reference_difference_relative": float(
                                    np.linalg.norm(
                                        recovered_local - active_reference[item.indices]
                                    )
                                )
                                / max(
                                    float(np.linalg.norm(active_reference[item.indices])),
                                    np.finfo(float).tiny,
                                ),
                            }
                        )
                    finally:
                        local_vector.destroy()
                        local_residual.destroy()
            finally:
                recovered_result.destroy()

            g_minus_A4y = np.asarray(
                reviewed["rhs"] - reference_A4y, dtype=np.complex128
            ).copy()
            expected_identity = np.zeros(storage_template.getLocalSize(), dtype=np.complex128)
            expected_identity[gamma_full] = expected_gamma
            identity_difference = g_minus_A4y - expected_identity
            internal_identity = g_minus_A4y[core.partition.internal_blocks_full[0]]
            for block in core.partition.internal_blocks_full[1:]:
                internal_identity = np.concatenate(
                    (internal_identity, g_minus_A4y[block])
                )
            max_local_residual = max(
                (item["relative_residual"] for item in local_records),
                default=0.0,
            )
            max_reference_difference = max(
                (item["reference_difference_relative"] for item in local_records),
                default=0.0,
            )
            identity_relative = float(np.linalg.norm(identity_difference)) / max(
                rhs_norm, np.finfo(float).tiny
            )
            internal_zero_relative = float(np.linalg.norm(internal_identity)) / max(
                rhs_norm, np.finfo(float).tiny
            )
            gamma_identity_relative = float(
                np.linalg.norm(g_minus_A4y[gamma_full] - expected_gamma)
            ) / max(rhs_norm, np.finfo(float).tiny)
            counts_after = _factor_solve_counts(core)
            facts = {
                "stem": reviewed["stem"],
                "logical_rhs": reviewed["logical_rhs"],
                "rhs_sha256": reviewed["g_sha256"],
                "reference_solution_sha256": _sha256_bytes(reference_y.tobytes()),
                "reference_A4y_sha256": _sha256_bytes(reference_A4y.tobytes()),
                "rhs_norm": rhs_norm,
                "elimination_seconds": elimination_seconds,
                "recovery_seconds": recovery_seconds,
                "factor_solve_counts_before": counts_before,
                "factor_solve_counts_after_elimination": elimination_after,
                "factor_solve_counts_after_recovery": counts_after,
                "factor_solve_call_delta_elimination": _factor_count_delta(
                    counts_before, elimination_after
                ),
                "factor_solve_call_delta_recovery": _factor_count_delta(
                    elimination_after, counts_after
                ),
                "recovery_facts": recovery_facts,
                "internal_block_count": len(core.internal),
                "internal_recovery_records": local_records,
                "internal_zero_relative": internal_zero_relative,
                "gamma_identity_relative": gamma_identity_relative,
                "full_identity_relative": identity_relative,
                "max_local_recovery_residual": max_local_residual,
                "max_reference_internal_difference": max_reference_difference,
                "elapsed_seconds": time.perf_counter() - started,
                "limits": {
                    "internal_zero_relative": 1.0e-10,
                    "gamma_identity_relative": 1.0e-10,
                    "full_identity_relative": 1.0e-10,
                    "local_recovery_residual": 1.0e-10,
                },
            }
            facts["passed"] = bool(
                facts["internal_zero_relative"] <= facts["limits"]["internal_zero_relative"]
                and facts["gamma_identity_relative"]
                <= facts["limits"]["gamma_identity_relative"]
                and facts["full_identity_relative"]
                <= facts["limits"]["full_identity_relative"]
                and facts["max_local_recovery_residual"]
                <= facts["limits"]["local_recovery_residual"]
                and facts["factor_solve_call_delta_elimination"]["internal_total"]
                == len(core.internal)
                and facts["factor_solve_call_delta_recovery"]["internal_total"]
                == len(core.internal)
            )
            _save_packet(
                runtime.directory / "q2_reference_elimination",
                reviewed["stem"],
                {
                    "schema": "task039extra.v14.q2-reference-elimination-packet.v1",
                    "facts": facts,
                    "g_minus_A4y": g_minus_A4y,
                    "expected_identity": expected_identity,
                    "identity_difference": identity_difference,
                    "reference_y": reference_y,
                    "reference_A4y": reference_A4y,
                    "recovered_active": recovered_active,
                },
                runtime=runtime,
            )
            records.append(facts)
            if not facts["passed"]:
                raise RuntimeError(
                    f"V14 reviewed reference elimination identity failed: {facts}"
                )
        finally:
            rhs.destroy()
    return {
        "schema": "task039extra.v14.q2-reference-elimination.v1",
        "records": records,
        "rhs_count": len(records),
        "passed": len(records) == len(rhs_records) and all(
            record["passed"] for record in records
        ),
    }


def _q2_schur_direct(
    runtime: _V14Runtime,
    common: dict[str, Any],
    rhs_records: list[dict[str, Any]],
) -> dict[str, Any]:
    from src.solvers.physical_interface_schur import (
        _submatrix,
        build_interface_partition,
        build_physical_interface_schur,
        factorize_interface_schur,
    )

    storage_rows = int(common["p4"]["dtn_action"].carrier.global_rows)
    if storage_rows != 53084:
        raise ValueError(f"V14 p4 carrier storage rows changed: {storage_rows}")
    full_volume = None
    active_volume = None
    storage_template = None
    core = None
    last_rhs = None
    last_gamma = None
    reserved_labels: set[str] = set()
    reserved_workspaces: set[str] = set()
    volume_facts: dict[str, Any] = {}
    state = None
    try:
        carrier = common["p4"]["dtn_action"].carrier
        runtime.set_phase("assembly")
        full_volume = _assemble_volume(
            runtime, common, inventory_label="q2_full_volume"
        )
        partition, port_data = build_interface_partition(
            common["levels"]["spaces"][4],
            common["levels"]["floquets"][4],
            carrier,
            volume=full_volume,
        )
        runtime.marker("q2_partition_complete", partition.audit())
        full_info = full_volume.getInfo()
        full_rows = int(full_volume.getSize()[0])
        full_payload = _sparse_payload_bytes(full_info, full_rows)
        active_upper_label = "q2_active_volume"
        runtime.check_projected(active_upper_label, full_payload)
        runtime.reserve_inventory(
            active_upper_label,
            {"matrix_payload_upper_bytes": full_payload},
            check_rss=False,
        )
        reserved_labels.add(active_upper_label)
        storage_template = full_volume.createVecRight()
        active_volume = _submatrix(full_volume, partition.active_full_indices)
        active_info = active_volume.getInfo()
        active_rows = int(active_volume.getSize()[0])
        active_payload = _sparse_payload_bytes(active_info, active_rows)
        runtime.replace_inventory(
            active_upper_label,
            {"matrix_payload_bytes": active_payload},
        )
        full_volume.destroy()
        full_volume = None
        runtime.release_inventory("q2_full_volume")
        volume_facts = {
            "full_storage_rows": full_rows,
            "full_matrix_info": full_info,
            "full_matrix_payload_bytes": full_payload,
            "active_rows": active_rows,
            "active_matrix_info": active_info,
            "active_matrix_payload_bytes": active_payload,
        }

        def allocation_gate(label: str, facts: Mapping[str, Any]) -> None:
            if label == "V_GG":
                inventory_label = "q2_V_GG"
                allocation = int(facts["matrix_payload_bytes"])
                runtime.check_projected(inventory_label, allocation)
                runtime.reserve_inventory(
                    inventory_label,
                    {"matrix_payload_upper_bytes": allocation},
                    check_rss=False,
                )
                reserved_labels.add(inventory_label)
                return
            if label.startswith("internal_coupling_"):
                block = int(facts["block_index"])
                coupling = int(facts["coupling_bytes"])
                index_bytes = int(facts["index_bytes"])
                workspace = int(facts["workspace_bytes"])
                runtime.check_inventory_projected(
                    f"internal_{block}", coupling + index_bytes + workspace
                )
                runtime.check_projected(
                    f"internal_coupling_{block}",
                    coupling + index_bytes,
                    workspace_bytes=workspace,
                )
                return
            if label in {"S_V", "interface_matrix"}:
                inventory_label = (
                    "q2_S_V" if label == "S_V" else "q2_interface_matrix"
                )
                workspace_label = (
                    "q2_S_V_assembly_workspace"
                    if label == "S_V"
                    else "q2_interface_assembly_workspace"
                )
                allocation = int(facts["matrix_payload_bytes"])
                workspace = int(facts.get("workspace_bytes", 0))
                runtime.check_projected(
                    inventory_label, allocation, workspace_bytes=workspace
                )
                runtime.reserve_inventory(
                    inventory_label,
                    {"matrix_payload_upper_bytes": allocation},
                    check_rss=False,
                )
                reserved_labels.add(inventory_label)
                if workspace:
                    runtime.reserve_workspace(workspace_label, workspace)
                    reserved_workspaces.add(workspace_label)
                return
            raise ValueError(f"unexpected V14 Schur allocation gate: {label}")

        before, after = _factor_gates(runtime, local_limit=True)
        core = build_physical_interface_schur(
            active_volume,
            partition,
            carrier,
            port_data=port_data,
            resource_sample=lambda: runtime.sample("q2_internal_factor"),
            marker=runtime.marker,
            pre_numeric_gate=before,
            post_numeric_gate=after,
            allocation_gate=allocation_gate,
            owns_volume=True,
        )
        active_volume = None
        for workspace_label in tuple(reserved_workspaces):
            runtime.release_workspace(workspace_label)
            reserved_workspaces.remove(workspace_label)
        runtime.replace_inventory(
            "q2_V_GG",
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    core.V_GG.getInfo(), int(core.V_GG.getSize()[0])
                )
            },
        )
        runtime.replace_inventory(
            "q2_S_V",
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    core.S_V.getInfo(), int(core.S_V.getSize()[0])
                )
            },
        )
        runtime.replace_inventory(
            "q2_interface_matrix",
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    core.interface_matrix.getInfo(),
                    int(core.interface_matrix.getSize()[0]),
                )
            },
        )
        runtime.marker(
            "q2_local_core_complete",
            {
                "internal_factor_count": len(core.internal),
                "factor_inventory": core.factor_facts,
                "volume": volume_facts,
            },
        )

        # This is deliberately before action checks and before the global
        # interface factor.  The reusable state contains only the matrices
        # and local couplings needed by the conditional later route; the
        # global augmented matrix is rebuilt, not copied into this archive.
        state = _q2_reusable_state(runtime, core)
        action_checks = _core_action_checks(runtime, core, common, storage_template)
        if not action_checks["passed"]:
            raise RuntimeError(
                f"V14 explicit/matrix-free action gate failed: {action_checks}"
            )
        reference_elimination = _q2_reference_elimination_checks(
            runtime,
            core,
            common,
            rhs_records,
            storage_template,
        )
        if not reference_elimination["passed"]:
            raise RuntimeError(
                "V14 reviewed reference elimination identity did not pass"
            )
        _save_packet(
            runtime.directory,
            "q2_pre_global_factor",
            {
                "schema": "task039extra.v14.q2-pre-global-factor.v1",
                "source_sha": runtime.source_sha,
                "partition": partition.audit(),
                "reusable_state_index": state["index"],
                "action_checks": action_checks,
                "reference_elimination": reference_elimination,
                "factor_solve_counts": _factor_solve_counts(core),
                "global_interface_factor_built": False,
            },
            runtime=runtime,
        )
        runtime.sample("q2_pre_global_factor_checkpoint")

        global_before, global_after = _factor_gates(
            runtime, local_limit=False, matrix_already_reserved=True
        )
        interface_facts = factorize_interface_schur(
            core,
            resource_sample=lambda: runtime.sample("q2_interface_factor"),
            marker=runtime.marker,
            pre_numeric_gate=global_before,
            post_numeric_gate=global_after,
        )
        runtime.marker(
            "q2_global_interface_factor_complete",
            {
                "interface_factor": interface_facts,
                "factor_solve_counts": _factor_solve_counts(core),
            },
        )

        solution_arrays: list[np.ndarray] = []
        solve_records: list[dict[str, Any]] = []
        for reviewed in rhs_records:
            runtime.set_phase("solve")
            runtime.marker("q2_rhs_solve_started", {"stem": reviewed["stem"]})
            started = time.perf_counter()
            rhs = storage_template.copy()
            rhs.array[:] = reviewed["rhs"]
            solution = None
            try:
                counts_before = _factor_solve_counts(core)
                solution, core_facts = core.solve(rhs, return_facts=True)
                interface_solution = np.asarray(
                    core_facts.pop("interface_solution"), dtype=np.complex128
                ).copy()
                counts_after_core = _factor_solve_counts(core)
                residual_facts, native_A4, native_volume, augmented_top, port = (
                    _q2_residual_arrays(
                        common,
                        reviewed,
                        solution,
                        interface_solution,
                        partition.gamma_rows,
                    )
                )
                refinements: list[dict[str, Any]] = []
                for refinement_index in range(2):
                    if residual_facts["native_A4_relative"] <= 1.0e-10:
                        break
                    refine_started = time.perf_counter()
                    refine_before = _factor_solve_counts(core)
                    correction_rhs = rhs.copy()
                    correction = None
                    try:
                        correction_rhs.array[:] = augmented_top
                        reduced, correction_port = core.reduce(
                            correction_rhs, port_rhs=port
                        )
                        delta_interface = core._interface_solve(
                            np.concatenate((reduced, correction_port))
                        )
                        correction = core.recover(
                            correction_rhs,
                            delta_interface[: partition.gamma_rows],
                        )
                        solution.axpy(-1.0, correction)
                        interface_solution -= delta_interface
                    finally:
                        if correction is not None:
                            correction.destroy()
                        correction_rhs.destroy()
                    refine_after = _factor_solve_counts(core)
                    (
                        residual_facts,
                        native_A4,
                        native_volume,
                        augmented_top,
                        port,
                    ) = _q2_residual_arrays(
                        common,
                        reviewed,
                        solution,
                        interface_solution,
                        partition.gamma_rows,
                    )
                    refinements.append(
                        {
                            "index": refinement_index + 1,
                            "elapsed_seconds": time.perf_counter() - refine_started,
                            "trigger": "native_A4_residual_above_1e-10",
                            "factor_solve_counts_before": refine_before,
                            "factor_solve_counts_after": refine_after,
                            "factor_solve_call_delta": _factor_count_delta(
                                refine_before, refine_after
                            ),
                        }
                    )
                interface_evidence = _q2_interface_residual(
                    core, rhs, interface_solution
                )
                counts_after_evidence = _factor_solve_counts(core)
                solution_array = np.asarray(solution.array).copy()
                solution_arrays.append(solution_array)
                solve_record = {
                    "stem": reviewed["stem"],
                    "logical_rhs": reviewed["logical_rhs"],
                    "elapsed_seconds": time.perf_counter() - started,
                    "core_facts": core_facts,
                    "augmented_residual": residual_facts,
                    "native_A4_relative_residual": residual_facts[
                        "native_A4_relative"
                    ],
                    "native_volume_top_relative_residual": residual_facts[
                        "native_volume_top_relative"
                    ],
                    "augmented_top_relative_residual": residual_facts[
                        "augmented_top_relative"
                    ],
                    "augmented_total_relative_residual": residual_facts[
                        "augmented_total_relative"
                    ],
                    "interface_relative_residual": interface_evidence[
                        "interface_relative_residual"
                    ],
                    "interface_reduced_rhs_relative_residual": interface_evidence[
                        "interface_reduced_rhs_relative_residual"
                    ],
                    "interface_residual_norm": float(
                        np.linalg.norm(interface_evidence["interface_residual"])
                    ),
                    "factor_solve_counts_before": counts_before,
                    "factor_solve_counts_after_core_solve": counts_after_core,
                    "factor_solve_counts_after_rhs_evidence": counts_after_evidence,
                    "factor_solve_call_delta_core_solve": _factor_count_delta(
                        counts_before, counts_after_core
                    ),
                    "factor_solve_call_delta_rhs_evidence": _factor_count_delta(
                        counts_before, counts_after_evidence
                    ),
                    "refinements": refinements,
                    "solution_sha256": _sha256_bytes(solution_array.tobytes()),
                    "reference_true_residual": reviewed["reference_true_residual"],
                }
                packet = _save_packet(
                    runtime.directory / "q2_rhs_packets",
                    reviewed["stem"],
                    {
                        "schema": "task039extra.v14.q2-rhs-packet.v2",
                        "identity": {
                            key: value
                            for key, value in reviewed.items()
                            if key
                            not in {
                                "rhs",
                                "reference_solution",
                                "reference_A4y",
                                "reference_map",
                            }
                        },
                        "solve": solve_record,
                        "x_storage": solution_array,
                        "interface_solution": interface_solution,
                        "native_A4_residual": native_A4,
                        "native_volume_top_residual": native_volume,
                        "augmented_top_residual": augmented_top,
                        "port_residual": port,
                        "interface_rhs": interface_evidence["interface_rhs"],
                        "interface_residual": interface_evidence[
                            "interface_residual"
                        ],
                    },
                    runtime=runtime,
                )
                solve_record["packet"] = packet
                solve_records.append(solve_record)
                if last_rhs is not None:
                    last_rhs.destroy()
                last_rhs = rhs.copy()
                last_gamma = interface_solution[: partition.gamma_rows].copy()
            except BaseException as exc:
                _save_packet(
                    runtime.directory / "q2_rhs_packets",
                    reviewed["stem"] + "_failure",
                    {
                        "schema": "task039extra.v14.q2-rhs-failure-packet.v1",
                        "identity": {
                            key: value
                            for key, value in reviewed.items()
                            if key
                            not in {
                                "rhs",
                                "reference_solution",
                                "reference_A4y",
                                "reference_map",
                            }
                        },
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                        "factor_solve_counts": _factor_solve_counts(core),
                    },
                    runtime=runtime,
                )
                raise
            finally:
                if solution is not None:
                    solution.destroy()
                rhs.destroy()
            runtime.sample(f"q2_rhs_{reviewed['stem']}_complete")

        field = _field_metrics(
            runtime,
            common,
            solution_arrays,
            [record["reference_solution"] for record in rhs_records],
        )
        for solve, field_record in zip(solve_records, field, strict=True):
            solve["field_metrics"] = field_record
        max_native_A4 = max(
            item["native_A4_relative_residual"] for item in solve_records
        )
        max_augmented = max(
            item["augmented_total_relative_residual"] for item in solve_records
        )
        max_interface = max(
            item["interface_relative_residual"] for item in solve_records
        )
        max_field = max(
            max(
                item["field_metrics"]["field_l2_relative"],
                item["field_metrics"]["scaled_curl_relative"],
            )
            for item in solve_records
        )
        if last_rhs is None or last_gamma is None:
            raise RuntimeError("Q2 did not retain a final RHS/recovery state")
        pre_release_solution = solution_arrays[-1].copy()
        core.release_explicit_schur()
        runtime.release_inventory("interface")
        runtime.release_inventory("q2_interface_matrix")
        runtime.release_inventory("q2_S_V")
        runtime.release_inventory("q2_active_volume")
        released = core.recover(last_rhs, last_gamma)
        try:
            release_relative = float(
                np.linalg.norm(released.array - pre_release_solution)
            ) / max(float(np.linalg.norm(pre_release_solution)), np.finfo(float).tiny)
        finally:
            released.destroy()
        # As in Q1, the original native A4 residual is the numerical
        # admission line.  Augmented and interface residuals remain recorded
        # for construction/error diagnosis; the reduced-RHS-normalized
        # interface number cannot replace the original A4 criterion.
        residual_pass = max_native_A4 <= 1.0e-10
        field_pass = max_field <= 1.0e-8
        record = {
            "schema": "task039extra.v14.q2-schur-direct.v2",
            "status": "Q2_SCHUR_DIRECT_PASS"
            if residual_pass and field_pass and release_relative <= 1.0e-10
            else "EXACT_CONTROL_UNQUALIFIED",
            "official_result": bool(
                residual_pass and field_pass and release_relative <= 1.0e-10
            ),
            "rhs": [
                {
                    key: value
                    for key, value in item.items()
                    if key
                    not in {"rhs", "reference_solution", "reference_A4y", "reference_map"}
                }
                for item in rhs_records
            ],
            "partition": partition.audit(),
            "volume": volume_facts,
            "factor_inventory": core.factor_facts,
            "global_interface_factor": interface_facts,
            "reusable_state": state,
            "action_checks": action_checks,
            "solve_records": solve_records,
            "gates": {
                "native_A4_relative_residual": 1.0e-10,
                "field_l2_and_scaled_curl": 1.0e-8,
                "admission_basis": "original_A4_and_P64_field_metrics",
                "post_release_recovery": 1.0e-10,
                "max_native_A4_relative_residual": max_native_A4,
                "max_augmented_total_relative_residual": max_augmented,
                "max_interface_relative_residual": max_interface,
                "max_interface_reduced_rhs_relative_residual": max(
                    item["interface_reduced_rhs_relative_residual"]
                    for item in solve_records
                ),
                "augmented_and_interface_residuals_are_diagnostics_only": True,
                "max_field_l2_or_scaled_curl": max_field,
                "post_release_recovery_relative": release_relative,
            },
            "lifecycle": {
                "internal_factor_count": len(core.internal),
                "global_interface_factor_count": 1,
                "factor_live_through_all_rhs_and_metrics": True,
                "explicit_schur_released_before_final_recovery_check": True,
                "local_factors_retained_for_recovery": True,
                "factor_solve_counts_after_all_rhs": _factor_solve_counts(core),
                "inventory_peak_bytes": runtime.inventory_peak_bytes,
                "workspace_peak_bytes": runtime.workspace_peak_bytes,
            },
        }
        runtime.marker("q2_schur_direct_complete", record)
        return record
    finally:
        for workspace_label in tuple(reserved_workspaces):
            runtime.release_workspace(workspace_label)
        if last_rhs is not None:
            last_rhs.destroy()
        if core is not None:
            core.destroy()
        elif active_volume is not None:
            active_volume.destroy()
        if full_volume is not None:
            full_volume.destroy()
            runtime.release_inventory("q2_full_volume")
        if storage_template is not None:
            storage_template.destroy()
        for label in (
            "interface",
            "q2_interface_matrix",
            "q2_S_V",
            "q2_V_GG",
            "q2_active_volume",
            "q2_full_volume",
        ):
            runtime.release_inventory(label)
        for index in range(42):
            runtime.release_inventory(f"internal_{index}")


def _q3_action_checks(
    runtime: _V14Runtime,
    core: Any,
    common: Mapping[str, Any],
    storage_template: Any,
) -> dict[str, Any]:
    """Check the matrix-free physical Gamma action before releasing ``S_V``."""

    runtime.set_phase("action_checks")
    gamma = core.V_GG.createVecRight()
    gamma_y = gamma.duplicate()
    gamma_mf = gamma.duplicate()
    gamma_explicit = gamma.duplicate()
    gamma_adjoint = gamma.duplicate()
    gamma_adj_explicit = gamma.duplicate()
    zero_storage = storage_template.duplicate()
    physical = physical_adjoint = recovered = native_output = None
    try:
        gamma.array[:] = np.arange(gamma.getLocalSize(), dtype=np.float64) + 0.25j
        gamma.array[:] /= max(float(gamma.norm()), 1.0)
        gamma_y.array[:] = 1.0 + 1j * np.arange(
            gamma_y.getLocalSize(), dtype=np.float64
        )
        gamma_y.array[:] /= max(float(gamma_y.norm()), 1.0)
        core.S_V.mult(gamma, gamma_explicit)
        core.apply_volume_schur(gamma, gamma_mf)
        core.S_V.multHermitian(gamma, gamma_adj_explicit)
        core.apply_volume_schur_adjoint(gamma, gamma_adjoint)

        zero_storage.set(0)
        recovered = core.recover(zero_storage, gamma)
        native_output = recovered.duplicate()
        common["p4"]["physical_action"].apply(recovered, native_output)
        native_gamma = np.asarray(
            native_output.array[core.partition.gamma_full_indices],
            dtype=np.complex128,
        )
        physical = core.apply_physical_schur(gamma)
        physical_difference = float(
            np.linalg.norm(native_gamma - physical.array)
        ) / max(float(physical.norm()), np.finfo(float).tiny)

        physical_adjoint = core.apply_physical_schur_adjoint(gamma)
        expected_adjoint = gamma_adj_explicit.duplicate()
        try:
            expected_adjoint.array[:] = gamma_adj_explicit.array
            for entry in core.port_data:
                value = np.dot(
                    np.conj(entry["b_values"]), gamma.array[entry["b_gamma"]]
                ) / np.conj(entry["normalization_h"])
                expected_adjoint.array[entry["d_gamma"]] += (
                    np.conj(entry["d_values"]) * value
                )
            physical_adjoint_difference = float(
                np.linalg.norm(physical_adjoint.array - expected_adjoint.array)
            ) / max(float(expected_adjoint.norm()), np.finfo(float).tiny)
        finally:
            expected_adjoint.destroy()

        block_input = np.empty((gamma.getLocalSize(), 2), dtype=np.complex128)
        block_input[:, 0] = gamma.array
        block_input[:, 1] = gamma_y.array
        block_output = core.apply_physical_schur_block(block_input)
        block_first_difference = float(
            np.linalg.norm(block_output[:, 0] - physical.array)
        ) / max(float(physical.norm()), np.finfo(float).tiny)
        physical_y = core.apply_physical_schur(gamma_y)
        try:
            block_second_difference = float(
                np.linalg.norm(block_output[:, 1] - physical_y.array)
            ) / max(float(physical_y.norm()), np.finfo(float).tiny)
        finally:
            physical_y.destroy()

        adjoint_y = core.apply_physical_schur_adjoint(gamma_y)
        try:
            lhs = complex(physical.dot(gamma_y))
            rhs_inner = complex(gamma.dot(adjoint_y))
            inner_scale = max(
                abs(lhs),
                abs(rhs_inner),
                float(physical.norm()) * float(gamma_y.norm()),
                np.finfo(float).tiny,
            )
            adjoint_inner_relative = abs(lhs - rhs_inner) / inner_scale
        finally:
            adjoint_y.destroy()

        facts = {
            "schema": "task039extra.v14.q3-action-checks.v1",
            "volume_explicit_vs_matrix_free": _vec_relative(
                gamma_explicit, gamma_mf
            ),
            "volume_adjoint_explicit_vs_matrix_free": _vec_relative(
                gamma_adj_explicit, gamma_adjoint
            ),
            "physical_schur_vs_native_carrier": physical_difference,
            "physical_schur_adjoint_formula": physical_adjoint_difference,
            "physical_block_first_column": block_first_difference,
            "physical_block_second_column": block_second_difference,
            "physical_schur_complex_inner_product_relative": float(
                adjoint_inner_relative
            ),
            "global_dense_schur_constructed": False,
            "interface_matrix_built": False,
            "matrix_free_block_action": True,
            "batch_columns": 32,
        }
        facts["limits"] = {
            "action_bridge": 1.0e-10,
            "physical_schur": 1.0e-10,
            "adjoint_inner_product": 1.0e-10,
        }
        facts["passed"] = bool(
            facts["volume_explicit_vs_matrix_free"] <= facts["limits"]["action_bridge"]
            and facts["volume_adjoint_explicit_vs_matrix_free"]
            <= facts["limits"]["action_bridge"]
            and facts["physical_schur_vs_native_carrier"]
            <= facts["limits"]["physical_schur"]
            and facts["physical_schur_adjoint_formula"]
            <= facts["limits"]["physical_schur"]
            and facts["physical_block_first_column"]
            <= facts["limits"]["physical_schur"]
            and facts["physical_block_second_column"]
            <= facts["limits"]["physical_schur"]
            and facts["physical_schur_complex_inner_product_relative"]
            <= facts["limits"]["adjoint_inner_product"]
        )
        runtime.marker("v14_q3_action_checks_complete", facts)
        runtime.sample("q3_action_checks_complete")
        return facts
    finally:
        for value in (
            gamma,
            gamma_y,
            gamma_mf,
            gamma_explicit,
            gamma_adjoint,
            gamma_adj_explicit,
            zero_storage,
            physical,
            physical_adjoint,
            recovered,
            native_output,
        ):
            if value is not None:
                value.destroy()


def _q3_representative_patches(
    patch_rows: tuple[np.ndarray, ...],
    port_data: list[Mapping[str, Any]],
) -> tuple[int, int, dict[str, Any]]:
    """Choose the two deterministic geometry/graph representative patches."""

    sizes = [int(rows.size) for rows in patch_rows]
    # Form the physical nonzero DtN support once.  Rebuilding a row set for
    # every port and every patch made representative selection needlessly
    # quadratic in Python and, more importantly, admitted zero carrier
    # entries as if they were physical support.
    nonzero_dtn_support: set[int] = set()
    for entry in port_data:
        for rows, values in (
            (entry["b_gamma"], entry["b_values"]),
            (entry["d_gamma"], entry["d_values"]),
        ):
            row_array = np.asarray(rows, dtype=np.int64).reshape(-1)
            value_array = np.asarray(values, dtype=np.complex128).reshape(-1)
            if row_array.size != value_array.size:
                raise ValueError("DtN representative support/value sizes differ")
            nonzero_dtn_support.update(
                int(row)
                for row, value in zip(row_array, value_array, strict=True)
                if abs(value) > 0.0
            )
    patch_sets = [set(np.asarray(rows, dtype=np.int64).tolist()) for rows in patch_rows]
    support_sets = [patch_set & nonzero_dtn_support for patch_set in patch_sets]
    support_counts = [len(values) for values in support_sets]
    largest = min(range(len(patch_rows)), key=lambda index: (-sizes[index], index))
    dtn_order = sorted(
        range(len(patch_rows)),
        key=lambda index: (-support_counts[index], -sizes[index], index),
    )
    dtn_patch = next((index for index in dtn_order if index != largest), None)
    if dtn_patch is None:
        raise ValueError("Q3 representative patch selection needs two distinct patches")
    facts = {
        "selection_rule": (
            "largest canonical seed/Gamma support; then largest nonzero DtN "
            "support, tie-broken by size and patch id, forced distinct"
        ),
        "largest_patch": largest,
        "dtn_patch": dtn_patch,
        "patch_sizes": sizes,
        "nonzero_dtn_support_counts": support_counts,
        "nonzero_dtn_support_union_count": len(nonzero_dtn_support),
        "largest_patch_rows_sha256": _sha256_bytes(
            np.ascontiguousarray(patch_rows[largest]).tobytes()
        ),
        "dtn_patch_rows_sha256": _sha256_bytes(
            np.ascontiguousarray(patch_rows[dtn_patch]).tobytes()
        ),
    }
    return largest, dtn_patch, facts


def _q3_delta_from_unweighted_p4_mass(
    runtime: _V14Runtime,
    common: Mapping[str, Any],
    partition: Any,
    resolved_payload: Mapping[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Reuse the qualified V13 p0 diagonal after current identity checks.

    The diagonal was already proved equivalent to the unweighted p4 mass in
    V13.  Q3 only loads that hash-bound packet and restricts it to the current
    Gamma map; it never reconstructs a second metric or cell-basis library.
    """

    from src.runners.physical_diagnostic_completion import load_packet
    from src.runners.physical_macro_controls import _mapping_identity_sha256
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.physical_macro_dd4 import _identity_hash_arrays

    runtime.set_phase("assembly")
    runtime.marker(
        "q3_unweighted_p4_mass_diagonal_started",
        {
            "definition": "V13 qualified integral conjugate(E) dot E; no material weight",
            "construction": "hash-bound p0 packet reuse; no metric rebuild",
        },
    )
    root = _repo_root()
    compact_path = root / "docs/task039_extra_physical_multilevel/outcomes/records/p4_direction_diagnosis_v13.json"
    p0_path = root / (
        "benchmarks/artifacts/task39extra/p4_direction_diagnosis_v13/"
        "e46fec48dc073a745e9b7e6c9186a147aefbc0a0/diagnosis/records/"
        "p0_metric_equivalence.json"
    )
    expected_physical = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
    expected_mode = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
    expected_p0_json_sha = "c05ff1a34a387e9a2a8a14f492349a4874e3ba160ed254ae11b8533243cfa3e9"
    expected_p0_npz_sha = "c0fc7ad54001f11033cea4c0340075da6569df828f2bd94430835580677a1e83"
    expected_map_summary_sha = "f175bfce77ca4a6811f12e800c213ade75afd0ce866ae57ae9f5449130cca0fe"
    expected_local_map_sha = "f788b961933cf814014feacea4a787ded7b8041bd51111a30424c042e4721cbd"

    compact = json.loads(compact_path.read_text(encoding="utf-8"))
    if (
        compact.get("source_sha") != "e46fec48dc073a745e9b7e6c9186a147aefbc0a0"
        or compact.get("physical_model_sha256") != expected_physical
        or compact.get("ordered_mode_sha256") != expected_mode
        or compact.get("p0", {}).get("record_sha256") != expected_p0_json_sha
    ):
        raise ValueError("V13 p0 compact identity is not the qualified physical packet")
    if _sha256_file(p0_path) != expected_p0_json_sha:
        raise ValueError("V13 p0 JSON packet hash changed")
    p0_record = json.loads(p0_path.read_text(encoding="utf-8"))
    array_meta = p0_record.get("arrays")
    if not isinstance(array_meta, Mapping):
        raise ValueError("V13 p0 packet has no hash-bound array archive")
    array_path = Path(array_meta["path"])
    if not array_path.is_file() or _sha256_file(array_path) != expected_p0_npz_sha:
        raise ValueError("V13 p0 fixed-diagonal archive hash changed")
    if array_meta.get("sha256") != expected_p0_npz_sha:
        raise ValueError("V13 p0 packet does not name the qualified array archive")

    actual_physical = resolved_payload.get("provenance", {}).get(
        "physical_model_sha256"
    )
    actual_mode = str(common["p4"]["mode_sha256"])
    if actual_physical != expected_physical or actual_mode != expected_mode:
        raise ValueError("current Q3 physical or ordered-mode identity differs from V13 p0")
    current_map = native_map_arrays(
        common["levels"]["spaces"][4], common["levels"]["floquets"][4]
    )
    current_map_summary_sha = _mapping_identity_sha256(current_map)
    current_local_map_sha = _identity_hash_arrays(
        {
            key: current_map[key]
            for key in (
                "dofmap",
                "slaves",
                "masters",
                "coefficients",
                "offsets",
                "independent_indices",
            )
        }
    )
    if current_map_summary_sha != expected_map_summary_sha:
        raise ValueError("current native p4 map summary differs from V13 p0")
    if current_local_map_sha != expected_local_map_sha:
        raise ValueError("current local p4 map identity differs from V13 p0")
    p0 = load_packet(p0_path)
    active_delta = np.ascontiguousarray(
        np.asarray(p0.get("fixed_diagonal_values"), dtype=np.float64)
    )
    if _sha256_bytes(active_delta.tobytes()) != p0_record["fixed_diagonal"]["sha256"]:
        raise ValueError("V13 p0 fixed diagonal content hash differs")
    if active_delta.shape != (partition.active_rows,):
        raise ValueError("V13 p0 Delta has an unexpected active-row shape")
    delta_gamma = np.ascontiguousarray(
        active_delta[partition.gamma_active_indices], dtype=np.float64
    )
    if (
        delta_gamma.shape != (partition.gamma_rows,)
        or not np.all(np.isfinite(delta_gamma))
        or np.any(delta_gamma <= 0.0)
    ):
        raise ValueError("unweighted p4 Delta is not finite and strictly positive")
    facts = {
        "definition": "V13 qualified unweighted p4 lossless mass diagonal restricted to Gamma",
        "material_weight_included": False,
        "reuse": True,
        "metric_rebuilt": False,
        "p0_json": str(p0_path),
        "p0_json_sha256": expected_p0_json_sha,
        "p0_npz": str(array_path),
        "p0_npz_sha256": expected_p0_npz_sha,
        "source_physical_model_sha256": expected_physical,
        "current_physical_model_sha256": actual_physical,
        "source_ordered_mode_sha256": expected_mode,
        "current_ordered_mode_sha256": actual_mode,
        "physical_model_sha256": actual_physical,
        "ordered_mode_sha256": actual_mode,
        "constraint_map_sha256": current_map_summary_sha,
        "constraint_map_identity": current_local_map_sha,
        "active_rows": int(active_delta.size),
        "gamma_rows": int(delta_gamma.size),
        "active_sha256": _sha256_bytes(active_delta.tobytes()),
        "gamma_sha256": _sha256_bytes(delta_gamma.tobytes()),
        "minimum": float(np.min(delta_gamma)),
        "maximum": float(np.max(delta_gamma)),
    }
    runtime.marker("q3_unweighted_p4_mass_diagonal_complete", facts)
    return delta_gamma, facts


def _q3_array_summary(value: Any) -> dict[str, Any]:
    array = np.ascontiguousarray(np.asarray(value))
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "norm": float(np.linalg.norm(array)),
        "sha256": _sha256_bytes(array.tobytes()),
    }


def _q3_interface_operation_audit(
    interface_facts: Mapping[str, Any],
    internal_factor_count: int,
) -> dict[str, Any]:
    """Audit one F_int against its explicit finite operation envelope.

    ``factor_solve_delta`` is deliberately a per-block list.  A single F_int
    performs one reduction, two interface-Schur actions and one recovery, so
    a complete route has four internal solves per block (168 for the frozen
    42-block p4 core), not one solve per block.  Keeping the list here also
    lets the checker distinguish an under-executed route from an over-budget
    route without trusting a pre-aggregated counter.
    """

    internal_count = int(internal_factor_count)
    if internal_count < 0:
        raise ValueError("internal_factor_count must be non-negative")
    raw_delta = interface_facts.get("factor_solve_delta")
    factor_delta: list[int] = []
    factor_delta_error = None
    if isinstance(raw_delta, (list, tuple, np.ndarray)):
        try:
            factor_delta = [int(value) for value in raw_delta]
        except (TypeError, ValueError, OverflowError) as exc:
            factor_delta_error = f"invalid factor_solve_delta values: {exc}"
    else:
        factor_delta_error = "factor_solve_delta is not a per-block list"

    def integer_fact(key: str) -> int:
        try:
            return int(interface_facts.get(key, -1))
        except (TypeError, ValueError, OverflowError):
            return -1

    internal_total = int(sum(factor_delta))
    internal_max = max(factor_delta, default=0)
    internal_expected = int(4 * internal_count)
    local_patch = integer_fact("local_patch_apply_count")
    local_smoother = integer_fact("local_smoother_apply_count")
    coarse = integer_fact("coarse_solve_count")
    complete_route = bool(
        factor_delta_error is None
        and len(factor_delta) == internal_count
        and all(value == 4 for value in factor_delta)
        and internal_total == internal_expected
    )
    within_upper_bounds = bool(
        factor_delta_error is None
        and len(factor_delta) == internal_count
        and all(0 <= value <= 4 for value in factor_delta)
        and internal_total <= internal_expected
        and 0 <= local_patch <= 84
        and 0 <= local_smoother <= 2
        and 0 <= coarse <= 1
    )
    return {
        "schema": "task039extra.v14.interface-operation-audit.v1",
        "internal_factor_count": internal_count,
        "factor_solve_delta": factor_delta,
        "factor_solve_delta_error": factor_delta_error,
        "internal_factor_solve_total": internal_total,
        "internal_factor_solve_max_per_block": internal_max,
        "internal_factor_solve_expected_total": internal_expected,
        "internal_factor_solve_limit_total": internal_expected,
        "internal_factor_solve_limit_per_block": 4,
        "local_patch_apply_count": local_patch,
        "local_patch_apply_limit": 84,
        "local_smoother_apply_count": local_smoother,
        "local_smoother_apply_limit": 2,
        "coarse_solve_count": coarse,
        "coarse_solve_limit": 1,
        "within_upper_bounds": within_upper_bounds,
        "complete_route": complete_route,
        "passed": bool(
            complete_route
            and local_patch == 84
            and local_smoother == 2
            and coarse == 1
        ),
    }


def _q3_local_setup_prediction(
    patch_rows: tuple[np.ndarray, ...],
    process_order: tuple[int, ...],
    representative_patch_ids: tuple[int, int],
    representative_durations: Mapping[int, float],
) -> dict[str, Any]:
    """Predict the remaining sequential local setup from measured patches.

    The first two patches are the frozen geometry/graph representatives.  The
    remaining work is estimated from the largest measured seconds-per-
    ``(rows**2 + rows)`` unit, which covers the dense extraction, LU and SVD
    work performed for every requested patch.  The result is a derived budget
    envelope, never a substitute for the later measured build time.
    """

    rows_tuple = tuple(np.asarray(rows, dtype=np.int64).reshape(-1) for rows in patch_rows)
    order = tuple(int(patch_id) for patch_id in process_order)
    representatives = tuple(int(patch_id) for patch_id in representative_patch_ids)
    if len(representatives) != 2 or representatives[0] == representatives[1]:
        raise ValueError("Q3 setup prediction needs two distinct representatives")
    if sorted(order) != list(range(len(rows_tuple))):
        raise ValueError("Q3 setup prediction process order is not a permutation")
    if any(
        patch_id < 0 or patch_id >= len(rows_tuple)
        for patch_id in representatives
    ):
        raise ValueError("Q3 setup prediction representative is outside patch rows")
    if any(patch_id not in order[:2] for patch_id in representatives):
        raise ValueError("Q3 representatives must be processed before remaining patches")

    structural_weight = {
        patch_id: int(rows_tuple[patch_id].size * (rows_tuple[patch_id].size + 1))
        for patch_id in range(len(rows_tuple))
    }
    durations: dict[int, float] = {}
    for patch_id in representatives:
        duration = float(representative_durations.get(patch_id, -1.0))
        if not np.isfinite(duration) or duration < 0.0:
            raise ValueError("Q3 representative duration must be finite and non-negative")
        durations[patch_id] = duration
    rates = [
        durations[patch_id] / max(structural_weight[patch_id], 1)
        for patch_id in representatives
    ]
    seconds_per_structure_unit = max(rates, default=0.0)
    remaining_patch_ids = tuple(
        patch_id for patch_id in order if patch_id not in set(representatives)
    )
    representative_structure_weight = int(
        sum(structural_weight[patch_id] for patch_id in representatives)
    )
    remaining_structure_weight = int(
        sum(structural_weight[patch_id] for patch_id in remaining_patch_ids)
    )
    measured_representative_seconds = float(sum(durations.values()))
    predicted_remaining_seconds = float(
        seconds_per_structure_unit * remaining_structure_weight
    )
    return {
        "schema": "task039extra.v14.q3-local-setup-prediction.v1",
        "classification": "derived_upper_envelope_not_measured",
        "representative_patch_ids": list(representatives),
        "representative_durations_seconds": {
            str(patch_id): durations[patch_id] for patch_id in representatives
        },
        "representative_structure_weight": representative_structure_weight,
        "remaining_patch_ids": list(remaining_patch_ids),
        "remaining_structure_weight": remaining_structure_weight,
        "patch_structure_weights": {
            str(patch_id): structural_weight[patch_id]
            for patch_id in order
        },
        "seconds_per_structure_unit_upper": seconds_per_structure_unit,
        "measured_representative_seconds": measured_representative_seconds,
        "predicted_remaining_seconds": predicted_remaining_seconds,
        "predicted_local_setup_seconds": (
            measured_representative_seconds + predicted_remaining_seconds
        ),
        "prediction_formula": (
            "sum(measured representative seconds) + max(measured seconds/"
            "(rows^2+rows)) * remaining structure weight"
        ),
    }


@contextmanager
def _v14_balanced_adapter(runtime, common, fint, *, capture_vectors=False):
    """Own H6 and its audit buffers; borrow the existing fixed interface stack."""

    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_physical_intermediate_runtime import AlgebraicOwnerTransfer
    from src.solvers.physical_interface_balanced import InterfaceBalancedCoupling
    from src.solvers.physical_light_setup import build_light_h6_setup

    n6 = int(common["fine"]["dtn_action"].carrier.global_rows)
    n4 = int(common["p4"]["dtn_action"].carrier.global_rows)
    # Same-degree positive setup uses the already-qualified H6 constructor.
    # The two existing physical component payloads and twelve fine vectors
    # provide a construction estimate; measured RSS remains independent.
    component_payload = sum(
        int(action.audit["retained_numeric_payload_local_bytes"])
        for action in common["fine"]["volume_action"].component_actions.values()
    )
    setup_estimate = 2 * component_payload + 12 * n6 * 16
    runtime.check_inventory_projected("v14_h6_setup", setup_estimate)
    runtime.check_projected("v14_h6_setup", setup_estimate, workspace_bytes=64 << 20)
    runtime.marker("v14_h6_setup_preallocation", {
        "classification": "derived_conservative_estimate",
        "inventory_estimate_bytes": setup_estimate,
        "temporary_allowance_bytes": 64 << 20,
        "basis": "two same-degree physical component payloads plus twelve fine vectors",
    })
    positive = pc = None
    live_workspaces = set()
    inventory_live = False
    try:
        runtime.reserve_workspace("v14_h6_build", 64 << 20)
        live_workspaces.add("v14_h6_build")
        positive = build_light_h6_setup(common["levels"], common["cfg"], runtime.marker)
        h6, shell = positive["h6"], positive["p6_shell"]
        transfer = AlgebraicOwnerTransfer(common["transfer"])
        components = dict(shell.action.audit["retained_numeric_payload_components"])
        components["h6_diagonal_bytes"] = int(shell.diagonal.array.nbytes)
        for name in ("_inv_sqrt", "_scaled_input", "_scaled_action", "_rhs_scaled",
                     "_residual", "_direction", "_solution", "_action"):
            components["h6" + name + "_bytes"] = int(getattr(h6, name).array.nbytes)
        components["algebraic_transfer_slave_indices_bytes"] = int(
            transfer.fine_slaves.nbytes + transfer.coarse_slaves.nbytes)
        runtime.reserve_inventory("v14_h6", components, check_rss=False)
        inventory_live = True
        runtime.release_workspace("v14_h6_build")
        live_workspaces.remove("v14_h6_build")
        # Fine work vectors, retained audit copies, p4 residual copies and
        # H6's bounded packed-kernel temporaries share the existing 1 GiB pool.
        fine_vectors = 64 if capture_vectors else 40
        coarse_vectors = 16 if capture_vectors else 12
        kernel_temp = int(positive["light_facts"]["kernel"]["temporary_budget_bytes"])
        pc_workspace = fine_vectors * n6 * 16 + coarse_vectors * n4 * 16 + kernel_temp
        runtime.reserve_workspace("v14_balanced_apply", pc_workspace)
        live_workspaces.add("v14_balanced_apply")
        runtime.marker("v14_balanced_workspace", {
            "fine_vector_upper_count": fine_vectors,
            "coarse_vector_upper_count": coarse_vectors,
            "kernel_temporary_bytes": kernel_temp,
            "workspace_upper_bytes": pc_workspace,
            "scope": "new PC/ledger/capture vectors; outer Krylov storage accounted separately",
        })
        pc = InterfaceBalancedCoupling(
            lambda x: apply_owned(common["fine"]["physical_action"], x),
            lambda x: apply_owned(common["p4"]["physical_action"], x),
            transfer, fint, h6.apply,
            save=lambda name, facts: _save_packet(
                runtime.directory / "inexact_balance", name, facts, runtime=runtime),
            checkpoint=lambda: runtime.sample("v14_balanced_checkpoint"),
            capture_vectors=capture_vectors,
        )
        runtime.sample("v14_balanced_adapter_ready")
        yield pc, positive
    finally:
        if pc is not None:
            pc.destroy()
        if positive is not None:
            positive["h6"].destroy()
            positive["p6_shell"].destroy()
        for label in live_workspaces:
            runtime.release_workspace(label)
        if inventory_live:
            runtime.release_inventory("v14_h6")


def _q3_balanced_p6_audit(runtime, common, fint):
    """Check the actual c1/H6-generated feedback and eps1-eps2 closure."""

    from src.runners.physical_recursive_controls import load_recursive_balanced_inputs
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.fullspace_physical_intermediate import apply_owned

    runtime.reserve_workspace("q3_balanced_inputs", 32 << 20)
    e = q = ae = z = az = None
    pc = None
    try:
        inputs = load_recursive_balanced_inputs(
            runtime.root / "benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json")
        item = inputs["inputs"]["A2R160"]
        p6_space = common["levels"]["spaces"][6]
        current_map = native_map_arrays(p6_space, common["levels"]["floquets"][6])
        if set(current_map) != set(inputs["maps"][6]) or any(
            not np.array_equal(value, inputs["maps"][6][key])
            for key, value in current_map.items()
        ):
            raise ValueError("Q3 p6 balanced input differs from the fresh native map")
        indices = np.asarray(current_map["independent_indices"], dtype=np.int64)
        if item["q"].shape != indices.shape or item["e"].shape != indices.shape:
            raise ValueError("Q3 p6 balanced input has an incompatible active layout")
        e = _new_storage_vector(p6_space)
        q = _new_storage_vector(p6_space)
        e.set(0)
        q.set(0)
        e.array[indices], q.array[indices] = item["e"], item["q"]
        ae = apply_owned(common["fine"]["physical_action"], e)
        q_norm = max(float(q.norm()), np.finfo(float).tiny)
        bridge = float(np.linalg.norm(ae.array[indices] - item["q"])) / q_norm
        runtime.marker("q3_balanced_p6_input_complete", {
            "name": "A2R160", "q_bridge_relative": bridge,
            "e1_audit_sha256": inputs["e1_audit_sha256"],
            "q": _q3_array_summary(item["q"]), "e": _q3_array_summary(item["e"]),
        })
        if not np.isfinite(bridge) or bridge > 1e-10:
            raise ValueError("Q3 frozen q differs from actual A6 e")
        # e is used only for this input identity check, never by the PC.
        ae.destroy()
        e.destroy()
        ae = e = None
        with _v14_balanced_adapter(runtime, common, fint, capture_vectors=True) as (pc, positive):
            fint_before = int(fint.apply_count)
            h6_before = int(positive["h6"].apply_count)
            runtime.begin_pc(1)
            try:
                z = pc.apply(q)
            except BaseException:
                runtime.finish_pc(completed=False)
                raise
            pc_finish = runtime.finish_pc()
            az = apply_owned(common["fine"]["physical_action"], z)
            output_relative = float(np.linalg.norm(q.array - az.array)) / q_norm
            balance = pc.last_apply_facts["inexact_balance"]
            closure = balance["audit"]
            counts = dict(pc.last_apply_facts["counts"])
            expected_counts = dict(C=2, smoother=1, A_structure=2,
                                   A_inner_true=0, PH_audit=0)
            calls = pc.coarse_calls
            work = []
            for call in calls:
                facts = call["interface_facts"]
                internal = np.asarray(facts["factor_solve_delta"])
                local = np.asarray(facts["local_patch_solve_delta"])
                valid = bool(
                    internal.shape == (42,) and local.shape == (42,)
                    and np.all((internal >= 0) & (internal <= 4))
                    and np.all((local >= 0) & (local <= 2))
                    and int(facts["coarse_solve_count"]) == 1
                    and int(facts["local_smoother_apply_count"]) == 2
                    and facts["inner_iteration_count"] == 0
                    and not facts["ksp_created"]
                )
                work.append({
                    "internal_backsolves": int(internal.sum()),
                    "local_backsolves": int(local.sum()),
                    "coarse_solves": int(facts["coarse_solve_count"]),
                    "passed": valid,
                })
            fint_delta = int(fint.apply_count) - fint_before
            h6_delta = int(positive["h6"].apply_count) - h6_before
            passed = bool(
                len(work) == 2 and all(row["passed"] for row in work)
                and counts == expected_counts and fint_delta == 2 and h6_delta == 1
                and pc.native_A4_count == 2 and balance["actual_audit"] == "PASS"
                and np.isfinite(closure["closure_relative"])
                and closure["closure_relative"] <= 1e-8
                and np.isfinite(output_relative)
            )
            facts = {
                "schema": "task039extra.v14.q3.balanced-p6-audit.v2",
                "input_name": "A2R160", "q_bridge_relative": bridge,
                "pc": pc.last_apply_facts, "pc_finish": pc_finish,
                "coarse_calls": calls, "work": work,
                "pc_counts": counts, "pc_counts_expected": expected_counts,
                "fint_apply_delta": fint_delta, "h6_apply_delta": h6_delta,
                "native_A4_action_count": pc.native_A4_count,
                "identity_A6_action_count": 1, "output_A6_action_count": 1,
                "ledger_A6_action_count": pc.ledger.A_count,
                "ledger_PH_action_count": pc.ledger.PH_count,
                "g2_source": "P64^H A6 H6(q-A6 P64 Fint(P64^H q))",
                "closure": closure, "output_residual_relative": output_relative,
                "passed": passed, "completed": True,
            }
            packet_arrays = {
                "q": q.array.copy(), "z": z.array.copy(), "A6z": az.array.copy(),
                "eps_difference": pc.ledger.last["difference"].array.copy(),
                **pc.last_apply_vectors,
            }
            for index, call in enumerate(pc.ledger.last["call_vectors"], 1):
                for name in ("g", "applied", "eps"):
                    packet_arrays[f"{name}{index}"] = call[name].array.copy()
            packet = _save_packet(
                runtime.directory / "q3_balanced_p6", "A2R160_BAL_H",
                {"schema": "task039extra.v14.q3-balanced-p6-packet.v2",
                 "facts": facts, **packet_arrays}, runtime=runtime)
            facts["packet"] = packet
            runtime.marker("q3_balanced_p6_audit_complete", facts)
            return facts
    except BaseException as exc:
        _save_packet(
            runtime.directory / "q3_balanced_p6", "A2R160_BAL_H_failure",
            {"error": {"type": type(exc).__name__, "message": str(exc)},
             "coarse_calls": [] if pc is None else pc.coarse_calls},
            runtime=runtime)
        raise
    finally:
        for vector in (az, z, ae, q, e):
            if vector is not None:
                vector.destroy()
        runtime.release_workspace("q3_balanced_inputs")


def _q3_interface_control(
    runtime: _V14Runtime,
    common: dict[str, Any],
    rhs_records: list[dict[str, Any]],
    resolved_payload: Mapping[str, Any],
    *,
    stage_started_monotonic: float | None = None,
) -> dict[str, Any]:
    """Build and exercise the fixed matrix-free Q3 interface candidate."""

    from src.solvers.physical_interface_schur import (
        InterfaceFintAdapter,
        build_interface_local_smoother,
        build_interface_partition,
        build_interface_coarse_pair,
        build_physical_interface_schur,
        build_interface_candidate_directions,
        interface_patch_rows_from_core,
        orthonormalize_paired_directions,
    )

    storage_rows = int(common["p4"]["dtn_action"].carrier.global_rows)
    if storage_rows != 53084:
        raise ValueError(f"V14 p4 carrier storage rows changed: {storage_rows}")
    full_volume = active_volume = storage_template = None
    core = smoother = coarse_pair = fint = paired = None
    raw_P = raw_Q = None
    reserved_labels: set[str] = set()
    reserved_workspaces: set[str] = set()
    q3_stage_start = (
        time.monotonic()
        if stage_started_monotonic is None
        else float(stage_started_monotonic)
    )
    try:
        carrier = common["p4"]["dtn_action"].carrier
        runtime.set_phase("assembly")
        full_volume = _assemble_volume(
            runtime, common, inventory_label="q3_full_volume"
        )
        partition, port_data = build_interface_partition(
            common["levels"]["spaces"][4],
            common["levels"]["floquets"][4],
            carrier,
            volume=full_volume,
        )
        runtime.marker("q3_partition_complete", partition.audit())
        full_info = full_volume.getInfo()
        full_rows = int(full_volume.getSize()[0])
        full_payload = _sparse_payload_bytes(full_info, full_rows)
        active_label = "q3_active_volume"
        runtime.check_projected(active_label, full_payload)
        runtime.reserve_inventory(
            active_label,
            {"matrix_payload_upper_bytes": full_payload},
            check_rss=False,
        )
        reserved_labels.add(active_label)
        storage_template = full_volume.createVecRight()
        active_volume = __import__(
            "src.solvers.physical_interface_schur",
            fromlist=["_submatrix"],
        )._submatrix(full_volume, partition.active_full_indices)
        active_info = active_volume.getInfo()
        active_payload = _sparse_payload_bytes(
            active_info, int(active_volume.getSize()[0])
        )
        runtime.replace_inventory(
            active_label,
            {"matrix_payload_bytes": active_payload},
        )
        full_volume.destroy()
        full_volume = None
        runtime.release_inventory("q3_full_volume")

        def allocation_gate(label: str, facts: Mapping[str, Any]) -> None:
            if label == "V_GG":
                allocation = int(facts["matrix_payload_bytes"])
                runtime.check_projected("q3_V_GG", allocation)
                runtime.reserve_inventory(
                    "q3_V_GG",
                    {"matrix_payload_upper_bytes": allocation},
                    check_rss=False,
                )
                reserved_labels.add("q3_V_GG")
                return
            if label.startswith("internal_coupling_"):
                block = int(facts["block_index"])
                coupling = int(facts["coupling_bytes"])
                index_bytes = int(facts["index_bytes"])
                workspace = int(facts["workspace_bytes"])
                runtime.check_inventory_projected(
                    f"q3_internal_{block}", coupling + index_bytes + workspace
                )
                runtime.check_projected(
                    f"q3_internal_coupling_{block}",
                    coupling + index_bytes,
                    workspace_bytes=workspace,
                )
                return
            if label == "S_V":
                allocation = int(facts["matrix_payload_bytes"])
                workspace = int(facts.get("workspace_bytes", 0))
                runtime.check_projected(
                    "q3_S_V", allocation, workspace_bytes=workspace
                )
                runtime.reserve_inventory(
                    "q3_S_V",
                    {"matrix_payload_upper_bytes": allocation},
                    check_rss=False,
                )
                reserved_labels.add("q3_S_V")
                if workspace:
                    runtime.reserve_workspace("q3_S_V_assembly", workspace)
                    reserved_workspaces.add("q3_S_V_assembly")
                return
            raise ValueError(f"unexpected Q3 Schur allocation gate: {label}")

        before, after = _factor_gates(runtime, local_limit=True)
        core = build_physical_interface_schur(
            active_volume,
            partition,
            carrier,
            port_data=port_data,
            resource_sample=lambda: runtime.sample("q3_internal_factor"),
            marker=runtime.marker,
            pre_numeric_gate=before,
            post_numeric_gate=after,
            allocation_gate=allocation_gate,
            owns_volume=True,
            build_interface_matrix=False,
        )
        active_volume = None
        for workspace_label in tuple(reserved_workspaces):
            runtime.release_workspace(workspace_label)
            reserved_workspaces.remove(workspace_label)
        runtime.replace_inventory(
            "q3_V_GG",
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    core.V_GG.getInfo(), int(core.V_GG.getSize()[0])
                )
            },
        )
        runtime.replace_inventory(
            "q3_S_V",
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    core.S_V.getInfo(), int(core.S_V.getSize()[0])
                )
            },
        )
        runtime.marker(
            "q3_local_core_complete",
            {
                "partition": partition.audit(),
                "internal_factor_count": len(core.internal),
                "factor_inventory": core.factor_facts,
                "interface_matrix_built": False,
            },
        )

        patch_rows = interface_patch_rows_from_core(
            core,
            common["levels"]["spaces"][4],
            common["levels"]["floquets"][4],
        )
        largest_patch, dtn_patch, representative_facts = _q3_representative_patches(
            patch_rows, core.port_data
        )
        runtime.marker("q3_representative_patches_selected", representative_facts)
        delta_gamma, delta_facts = _q3_delta_from_unweighted_p4_mass(
            runtime, common, partition, resolved_payload
        )
        all_deltas = {
            patch_id: delta_gamma[patch_rows[patch_id]]
            for patch_id in range(len(patch_rows))
        }
        remaining_patch_ids = tuple(
            patch_id
            for patch_id in range(len(patch_rows))
            if patch_id not in {largest_patch, dtn_patch}
        )
        process_order = (largest_patch, dtn_patch, *remaining_patch_ids)
        resources = runtime.contract["resources"]
        local_factor_cap = int(
            resources["local_factor_matrix_and_allocated_cap_bytes"]
        )
        shared_temp_cap = int(resources["shared_temp_workspace_cap_bytes"])
        scalar_bytes = np.dtype(np.complex128).itemsize
        index_bytes = np.dtype(np.int64).itemsize
        local_factor_patch_upper = [
            int(
                2 * rows.size * rows.size * scalar_bytes
                + 3 * rows.size * index_bytes
            )
            for rows in patch_rows
        ]
        local_factor_upper = int(sum(local_factor_patch_upper))
        q3_contract_workflow_seconds = float(
            resources["stage_budgets"]["Q3_INTERFACE_CONTROL"]["workflow_seconds"]
        )
        q3_reserved_workflow_seconds = float(
            getattr(runtime, "workflow_reserved_seconds", q3_contract_workflow_seconds)
        )
        q3_workflow_seconds = min(
            q3_contract_workflow_seconds, q3_reserved_workflow_seconds
        )
        q3_representative_seconds = 900.0
        if not (
            q3_workflow_seconds > 0.0
            and q3_reserved_workflow_seconds > 0.0
        ):
            raise ValueError("Q3 parent workflow reservation is invalid")
        q3_known_future_controls = {
            "three_fint_admission_seconds_upper": float(15.0 * len(rhs_records)),
            "balanced_pc_hard_seconds": float(resources["pc_hard_seconds"]),
            "candidate_S_action_count_upper": 496,
            "candidate_S_action_seconds": "unknown",
            "mgs_seconds": "unknown",
            "packet_save_seconds": "unknown",
            "classification": "known_limits_plus_unmeasured_components",
            "seconds_upper_excludes": [
                "candidate S-action time",
                "MGS/orthonormalization time",
                "packet save and hashing time",
            ],
        }
        q3_known_future_seconds = float(
            q3_known_future_controls["three_fint_admission_seconds_upper"]
            + q3_known_future_controls["balanced_pc_hard_seconds"]
        )

        workflow_clock_method = getattr(runtime, "workflow_clock_interval", None)

        def workflow_elapsed() -> tuple[float, dict[str, Any]]:
            interval_method = workflow_clock_method
            if callable(interval_method):
                interval = dict(interval_method())
                return float(interval["budget_seconds"]), interval
            elapsed = max(0.0, time.monotonic() - q3_stage_start)
            return elapsed, {
                "budget_seconds": elapsed,
                "source": "worker_start_fallback_for_direct_helper_use",
            }

        local_workspace = max(
            int(
                3 * rows.size * rows.size * scalar_bytes
                + 3 * rows.size * scalar_bytes
                + rows.size * index_bytes
            )
            for rows in patch_rows
        )
        paired_svd_workspace = max(
            int(
                12 * rows.size * rows.size * scalar_bytes
                + 8 * rows.size * scalar_bytes
            )
            for rows in patch_rows
        )
        local_workspace = max(local_workspace, paired_svd_workspace)
        if max(local_factor_patch_upper) > local_factor_cap:
            raise V14ResourceStop(
                "Q3 one local factor matrix inventory exceeds 512MiB: "
                f"{max(local_factor_patch_upper)} > {local_factor_cap}"
            )
        # The 512 MiB policy is per local patch.  The complete 42-patch
        # library is a separate live-inventory item and is checked against
        # Q3's 3 GiB stage cap below; comparing the aggregate to the
        # per-patch limit would reject a valid complete smoother.
        runtime.check_inventory_projected("q3_local_smoother", local_factor_upper)
        runtime.check_projected(
            "q3_local_smoother",
            local_factor_upper,
            workspace_bytes=local_workspace,
        )
        local_setup_stage_elapsed, local_setup_clock = workflow_elapsed()
        if local_setup_stage_elapsed + q3_known_future_seconds >= q3_workflow_seconds:
            raise V14ResourceStop(
                "Q3 local setup has no remaining workflow time after known controls"
            )
        runtime.reserve_workspace("q3_local_smoother_build", local_workspace)
        reserved_workspaces.add("q3_local_smoother_build")
        completed_representatives: set[int] = set()
        representative_started_local: dict[int, float] = {}
        representative_durations: dict[int, float] = {}
        representative_ids = (largest_patch, dtn_patch)
        setup_budget_facts: dict[str, Any] = {
            "schema": "task039extra.v14.q3-local-setup-budget.v1",
            "workflow_clock_source": (
                "parent_attempt.workflow_clock_start"
                if callable(workflow_clock_method)
                else "worker_start_fallback_for_direct_helper_use"
            ),
            "workflow_clock_start": dict(
                getattr(runtime, "workflow_clock_start", {})
            ),
            "reserved_workflow_seconds": q3_reserved_workflow_seconds,
            "contract_workflow_seconds": q3_contract_workflow_seconds,
            "workflow_limit_seconds": q3_workflow_seconds,
            "representative_limit_seconds": q3_representative_seconds,
            "known_future_controls": q3_known_future_controls,
            "known_future_controls_seconds": q3_known_future_seconds,
            "representative_patch_ids": list(representative_ids),
            "process_order": list(process_order),
            "elapsed_before_local_setup_seconds": local_setup_stage_elapsed,
            "clock_at_local_setup_start": local_setup_clock,
            "prediction": None,
        }

        def local_progress(progress: Mapping[str, Any]) -> None:
            event = str(progress["event"])
            patch_id = int(progress["patch_id"])
            local_elapsed = float(progress["elapsed_seconds"])
            stage_elapsed, stage_clock = workflow_elapsed()
            setup_budget_facts["last_stage_elapsed_seconds"] = stage_elapsed
            setup_budget_facts["last_workflow_clock_interval"] = stage_clock
            setup_budget_facts["last_local_builder_elapsed_seconds"] = local_elapsed
            runtime.sample(f"q3_local_patch_{patch_id}_{event}")
            if stage_elapsed >= q3_workflow_seconds:
                raise V14ResourceStop(
                    "Q3 workflow reached its 3600-second budget before local setup completed"
                )
            if stage_elapsed + q3_known_future_seconds >= q3_workflow_seconds:
                raise V14ResourceStop(
                    "Q3 local setup exhausted the known future-control budget"
                )
            if patch_id not in representative_ids:
                return
            if event == "patch_started":
                representative_started_local[patch_id] = local_elapsed
            elif event == "patch_completed":
                started_local = representative_started_local.get(patch_id)
                if started_local is None:
                    raise RuntimeError(
                        f"Q3 representative patch {patch_id} completed before it started"
                    )
                representative_durations[patch_id] = max(
                    0.0, local_elapsed - started_local
                )
                completed_representatives.add(patch_id)
                representative_elapsed = float(sum(representative_durations.values()))
                if representative_elapsed >= q3_representative_seconds:
                    raise V14ResourceStop(
                        "Q3 representative local setup reached its 900-second budget"
                    )
                if len(completed_representatives) == len(representative_ids):
                    prediction = _q3_local_setup_prediction(
                        patch_rows,
                        process_order,
                        representative_ids,
                        representative_durations,
                    )
                    prediction.update(
                        {
                            "stage_elapsed_at_representatives_seconds": stage_elapsed,
                            "elapsed_before_local_setup_seconds": max(
                                0.0, stage_elapsed - local_elapsed
                            ),
                            "known_future_controls_seconds": q3_known_future_seconds,
                            "predicted_workflow_total_seconds": (
                                max(0.0, stage_elapsed - local_elapsed)
                                + prediction["predicted_local_setup_seconds"]
                                + q3_known_future_seconds
                            ),
                        }
                    )
                    prediction[
                        "remaining_workflow_after_predicted_setup_and_known_controls_seconds"
                    ] = (
                        q3_workflow_seconds
                        - prediction["predicted_workflow_total_seconds"]
                    )
                    setup_budget_facts["prediction"] = prediction
                    runtime.marker("q3_local_setup_prediction", prediction)
                    if prediction[
                        "remaining_workflow_after_predicted_setup_and_known_controls_seconds"
                    ] <= 0.0:
                        raise V14ResourceStop(
                            "Q3 predicted complete local setup leaves no time for "
                            "the known future controls"
                        )

        smoother = build_interface_local_smoother(
            core.S_V,
            patch_rows,
            port_data=core.port_data,
            ambient_rows=partition.gamma_rows,
            max_rows=2048,
            max_workspace_bytes=local_factor_cap,
            paired_basis_workspace_bytes=shared_temp_cap,
            solve_rtol=1.0e-10,
            paired_patch_deltas=all_deltas,
            process_order=process_order,
            progress_callback=local_progress,
        )
        runtime.release_workspace("q3_local_smoother_build")
        reserved_workspaces.remove("q3_local_smoother_build")
        local_audit = smoother.audit()
        setup_budget_facts.update(
            {
                "completed": True,
                "measured_local_builder_seconds": float(
                    local_audit["build_elapsed_seconds"]
                ),
                "stage_elapsed_after_local_setup_seconds": (
                    workflow_elapsed()[0]
                ),
            }
        )
        setup_budget_facts[
            "workflow_remaining_after_local_setup_seconds"
        ] = q3_workflow_seconds - setup_budget_facts[
            "stage_elapsed_after_local_setup_seconds"
        ]
        runtime.marker("q3_local_setup_budget_complete", setup_budget_facts)
        if (
            setup_budget_facts["stage_elapsed_after_local_setup_seconds"]
            + q3_known_future_seconds
            >= q3_workflow_seconds
        ):
            raise V14ResourceStop(
                "Q3 completed local setup without enough time for known controls"
            )
        local_resident_bytes = int(
            local_audit["retained_factor_bytes"]
            + local_audit["retained_paired_basis_bytes"]
        )
        runtime.check_inventory_projected("q3_local_smoother", local_resident_bytes)
        runtime.reserve_inventory(
            "q3_local_smoother",
            {
                "retained_factor_bytes": int(local_audit["retained_factor_bytes"]),
                "retained_paired_basis_bytes": int(
                    local_audit["retained_paired_basis_bytes"]
                ),
            },
            check_rss=False,
        )
        reserved_labels.add("q3_local_smoother")
        if sorted(smoother.paired_bases) != list(range(len(patch_rows))):
            raise RuntimeError("Q3 local builder did not produce all 42 local SVD bases")
        local_audit["setup_budget"] = setup_budget_facts
        runtime.marker(
            "q3_local_smoother_complete",
            {
                "patch_rows": [int(rows.size) for rows in patch_rows],
                "representatives": representative_facts,
                "delta": delta_facts,
                "process_order": list(process_order),
                "local_factor_cap_bytes": local_factor_cap,
                "local_factor_cap_scope": "per_patch_matrix_plus_LU",
                "local_factor_patch_upper_bytes": local_factor_patch_upper,
                "shared_temp_cap_bytes": shared_temp_cap,
                "local_factor_upper_bytes": local_factor_upper,
                "local_workspace_upper_bytes": local_workspace,
                "setup_budget": setup_budget_facts,
                "audit": local_audit,
            },
        )
        action_checks = _q3_action_checks(runtime, core, common, storage_template)
        if not action_checks["passed"]:
            raise RuntimeError(f"Q3 explicit/matrix-free action gate failed: {action_checks}")

        candidate_workspace_label = "q3_candidate_mgs_coarse"

        def candidate_preallocation(facts: Mapping[str, Any]) -> None:
            workspace = int(facts["workspace_upper_bytes"])
            if workspace > shared_temp_cap:
                raise V14ResourceStop(
                    "Q3 candidate/MGS/coarse temporary workspace exceeds 1GiB: "
                    f"{workspace} > {shared_temp_cap}"
                )
            runtime.check_workspace_projected(candidate_workspace_label, workspace)
            runtime.marker("q3_candidate_preallocation_gate", dict(facts))
            runtime.reserve_workspace(candidate_workspace_label, workspace)
            reserved_workspaces.add(candidate_workspace_label)

        raw_P, raw_Q, candidate_mapping, candidate_facts = (
            build_interface_candidate_directions(
                patch_rows,
                smoother.paired_bases,
                core.port_data,
                delta_gamma,
                max_candidates=496,
                max_mgs_rows=512,
                preallocation_callback=candidate_preallocation,
            )
        )
        if not candidate_facts["all_42_local_bases"]:
            raise RuntimeError("Q3 candidate construction did not receive all 42 local bases")
        paired = orthonormalize_paired_directions(
            raw_P,
            raw_Q,
            pair_tol=1.0e-12,
            max_pairs=512,
        )
        paired_facts = paired.audit()
        del raw_P, raw_Q
        raw_P = raw_Q = None
        paired_capacity = int(
            paired_facts["checks"]["output_basis_capacity_bytes"]
        )
        if paired_capacity % 2:
            raise RuntimeError("Q3 paired P/Q capacity is not evenly split")
        runtime.check_inventory_projected("q3_paired_basis", paired_capacity)
        runtime.reserve_inventory(
            "q3_paired_basis",
            {
                "P_capacity_bytes": paired_capacity // 2,
                "Q_capacity_bytes": paired_capacity // 2,
            },
            check_rss=False,
        )
        reserved_labels.add("q3_paired_basis")
        runtime.marker(
            "q3_paired_candidates_complete",
            {
                "candidate": candidate_facts,
                "paired": paired_facts,
                "mapping": candidate_mapping,
            },
        )
        if paired.rank == 0:
            raise np.linalg.LinAlgError("COARSE_PAIR_UNSTABLE: paired candidate rank is zero")
        coarse_bound = int(
            3 * paired.rank * paired.rank * np.dtype(np.complex128).itemsize
            + 3 * paired.rank * np.dtype(np.complex128).itemsize
            + paired.rank * np.dtype(np.int64).itemsize
        )
        runtime.check_inventory_projected("q3_coarse_pair", coarse_bound)
        runtime.check_projected("q3_coarse_pair_factor", coarse_bound)

        # Release the construction-only global sparse Schur before forming E;
        # the retained V_GG/internal factors and carrier now define S_gamma.
        core.release_explicit_schur()
        runtime.release_inventory("q3_S_V")
        reserved_labels.discard("q3_S_V")
        runtime.release_inventory("q3_active_volume")
        reserved_labels.discard("q3_active_volume")
        coarse_pair = build_interface_coarse_pair(
            core.apply_physical_schur_block,
            paired.P,
            paired.Q,
            max_rows=512,
            max_workspace_bytes=int(
                runtime.contract["resources"]["interface_workspace_cap_bytes"]
            ),
            max_temp_workspace_bytes=shared_temp_cap,
            rcond_rtol=1.0e-12,
            solve_rtol=1.0e-10,
        )
        runtime.release_workspace(candidate_workspace_label)
        reserved_workspaces.remove(candidate_workspace_label)
        coarse_audit = coarse_pair.audit()
        coarse_resident_bytes = int(
            coarse_pair.E.nbytes
            + coarse_pair.lu.nbytes
            + coarse_pair.pivots.nbytes
        )
        runtime.check_inventory_projected("q3_coarse_pair", coarse_resident_bytes)
        runtime.reserve_inventory(
            "q3_coarse_pair",
            {
                "E_bytes": int(coarse_pair.E.nbytes),
                "LU_bytes": int(coarse_pair.lu.nbytes),
                "pivots_bytes": int(coarse_pair.pivots.nbytes),
            },
            check_rss=False,
        )
        reserved_labels.add("q3_coarse_pair")
        fint = InterfaceFintAdapter(core, smoother, coarse_pair)
        solution_arrays: list[np.ndarray] = []
        solve_records: list[dict[str, Any]] = []
        three_rhs_fint_apply_deltas: list[int] = []
        for reviewed in rhs_records:
            runtime.set_phase("solve")
            runtime.marker("q3_rhs_solve_started", {"stem": reviewed["stem"]})
            started = time.perf_counter()
            rhs = storage_template.copy()
            rhs.array[:] = reviewed["rhs"]
            result = None
            fint_apply_before = int(fint.apply_count)
            try:
                result = fint.solve_intermediate(rhs)
                solution = result["final_solution"]
                residual_decomposition = _physical_residual_decomposition(
                    common["p4"]["physical_action"],
                    rhs,
                    solution,
                    partition,
                )
                solution_array = np.asarray(solution.array).copy()
                solution_arrays.append(solution_array)
                interface_facts = {
                    key: value for key, value in result.items() if key != "final_solution"
                }
                operation_audit = _q3_interface_operation_audit(
                    interface_facts, len(core.internal)
                )
                operation_count_passed = bool(operation_audit["passed"])
                fint_apply_delta = int(fint.apply_count) - fint_apply_before
                three_rhs_fint_apply_deltas.append(fint_apply_delta)
                solve_record = {
                    "stem": reviewed["stem"],
                    "logical_rhs": reviewed["logical_rhs"],
                    "elapsed_seconds": time.perf_counter() - started,
                    "native_A4_relative_residual": residual_decomposition["total_relative"],
                    "native_A4_residual_decomposition": residual_decomposition,
                    "interface_facts": interface_facts,
                    "operation_audit": operation_audit,
                    "operation_count_passed": operation_count_passed,
                    "fint_apply_count_delta": fint_apply_delta,
                    "solution_sha256": _sha256_bytes(solution_array.tobytes()),
                    "reference_true_residual": reviewed["reference_true_residual"],
                }
                packet = _save_packet(
                    runtime.directory / "q3_rhs_packets",
                    reviewed["stem"],
                    {
                        "schema": "task039extra.v14.q3-rhs-packet.v1",
                        "identity": {
                            key: value
                            for key, value in reviewed.items()
                            if key
                            not in {
                                "rhs",
                                "reference_solution",
                                "reference_A4y",
                                "reference_map",
                            }
                        },
                        "solve": solve_record,
                        "x_storage": solution_array,
                    },
                    runtime=runtime,
                )
                solve_record["packet"] = packet
                solve_records.append(solve_record)
            finally:
                if result is not None:
                    result["final_solution"].destroy()
                rhs.destroy()
            runtime.sample(f"q3_rhs_{reviewed['stem']}_complete")

        field = _field_metrics(
            runtime,
            common,
            solution_arrays,
            [item["reference_solution"] for item in rhs_records],
        )
        for solve, field_record in zip(solve_records, field, strict=True):
            solve["field_metrics"] = field_record
        max_rho = max(item["native_A4_relative_residual"] for item in solve_records)
        max_field = max(
            max(
                item["field_metrics"]["field_l2_relative"],
                item["field_metrics"]["scaled_curl_relative"],
            )
            for item in solve_records
        )
        admission_by_stem = {
            item["stem"]: {
                "rho": item["native_A4_relative_residual"],
                "eta": item["field_metrics"]["field_l2_relative"],
                "eta_curl": item["field_metrics"]["scaled_curl_relative"],
                "elapsed_seconds": item["elapsed_seconds"],
                "passed": (
                    item["native_A4_relative_residual"] <= (
                        0.2 if item["stem"].endswith("_02") else 0.5
                    )
                    and item["field_metrics"]["field_l2_relative"]
                    <= (0.9 if item["stem"].endswith("_02") else 0.5)
                    and item["field_metrics"]["scaled_curl_relative"]
                    <= (0.9 if item["stem"].endswith("_02") else 0.6)
                    and item["elapsed_seconds"] <= 15.0
                    and item["operation_count_passed"]
                ),
            }
            for item in solve_records
        }
        admission_pass = all(item["passed"] for item in admission_by_stem.values())
        three_rhs_fint_count = int(sum(three_rhs_fint_apply_deltas))
        three_rhs_fint_count_passed = bool(
            len(three_rhs_fint_apply_deltas) == len(rhs_records)
            and all(delta == 1 for delta in three_rhs_fint_apply_deltas)
        )
        balanced_audit = _q3_balanced_p6_audit(runtime, common, fint)
        stage_pass = bool(
            admission_pass
            and three_rhs_fint_count_passed
            and balanced_audit["passed"]
        )
        record = {
            "schema": "task039extra.v14.q3-interface-control.v1",
            "status": "Q3_INTERFACE_CONTROL_PASS" if stage_pass else "INTERFACE_CONTROL_UNQUALIFIED",
            "stage_pass": stage_pass,
            "admission_pass": admission_pass,
            "official_result": False,
            "result_classification": (
                "diagnostic_interface_candidate_pass"
                if stage_pass
                else "controlled_negative_interface_candidate"
            ),
            "partition": partition.audit(),
            "core": core.factor_facts,
            "representative_patches": representative_facts,
            "delta": delta_facts,
            "local_smoother": local_audit,
            "action_checks": action_checks,
            "candidate": candidate_facts,
            "paired_basis": paired_facts,
            "coarse_pair": coarse_audit,
            "solve_records": solve_records,
            "admission": admission_by_stem,
            "balanced_p6_audit": balanced_audit,
            "gates": {
                "candidate_input_upper_bound": 496,
                "coarse_rows": 512,
                "coarse_rcond": 1.0e-12,
                "coarse_solve_residual": 1.0e-10,
                "difficult_rho": 0.5,
                "difficult_eta": 0.5,
                "difficult_eta_curl": 0.6,
                "feedback_rho": 0.2,
                "feedback_eta": 0.9,
                "feedback_eta_curl": 0.9,
                "single_fint_seconds": 15.0,
                "max_native_A4_relative_residual": max_rho,
                "max_field_l2_or_scaled_curl": max_field,
                "three_rhs_fint_apply_deltas": three_rhs_fint_apply_deltas,
                "three_rhs_fint_apply_count": three_rhs_fint_count,
                "three_rhs_fint_apply_expected": len(rhs_records),
                "three_rhs_fint_apply_count_passed": three_rhs_fint_count_passed,
            },
            "lifecycle": {
                "global_interface_matrix_built": False,
                "global_interface_factor_built": False,
                "global_dense_schur_constructed": False,
                "explicit_S_V_released_before_candidate_solves": True,
                "internal_factor_count": len(core.internal),
                "fint_apply_count": fint.apply_count,
                "three_rhs_fint_apply_deltas": three_rhs_fint_apply_deltas,
                "three_rhs_fint_apply_count": three_rhs_fint_count,
                "three_rhs_fint_apply_count_expected": len(rhs_records),
                "fint_apply_count_expected_after_balanced_audit": (
                    len(rhs_records) + 2
                ),
                "local_smoother": smoother.audit(),
                "coarse_pair": coarse_pair.audit(),
                "inventory_peak_bytes": runtime.inventory_peak_bytes,
                "workspace_peak_bytes": runtime.workspace_peak_bytes,
            },
        }
        runtime.marker("q3_interface_control_complete", record)
        return record
    finally:
        for workspace_label in tuple(reserved_workspaces):
            runtime.release_workspace(workspace_label)
        if raw_P is not None:
            del raw_P
        if raw_Q is not None:
            del raw_Q
        if fint is not None:
            fint.destroy()
        if coarse_pair is not None:
            coarse_pair.destroy()
        paired = None
        if smoother is not None:
            smoother.destroy()
        if core is not None:
            core.destroy()
        elif active_volume is not None:
            active_volume.destroy()
        if full_volume is not None:
            full_volume.destroy()
        if storage_template is not None:
            storage_template.destroy()
        for label in tuple(reserved_labels):
            runtime.release_inventory(label)
        for label in (
            "q3_coarse_pair",
            "q3_paired_basis",
            "q3_local_smoother",
            "q3_S_V",
            "q3_V_GG",
            "q3_active_volume",
            "q3_full_volume",
        ):
            runtime.release_inventory(label)


def _q0_core(runtime: _V14Runtime, common: dict[str, Any]) -> dict[str, Any]:
    volume = None
    try:
        volume = _assemble_volume(runtime, common)
        partition, _port_data = __import__(
            "src.solvers.physical_interface_schur", fromlist=["build_interface_partition"]
        ).build_interface_partition(
            common["levels"]["spaces"][4],
            common["levels"]["floquets"][4],
            common["p4"]["dtn_action"].carrier,
            volume=volume,
        )
        record = {
            "schema": "task039extra.v14.q0-core.v1",
            "status": "Q0_CORE_PASS",
            "official_result": True,
            "partition": partition.audit(),
            "levels": sorted(common["levels"]["spaces"]),
            "old_macro_objects_constructed": False,
            "old_p2_p1_levels_constructed": False,
            "global_dense_schur_constructed": False,
        }
        runtime.marker("q0_core_complete", record)
        return record
    finally:
        if volume is not None:
            volume.destroy()


def run_physical_p4_schur_v14(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
) -> dict[str, Any]:
    """Run one explicit V14 stage and return the Task38 adapter result."""

    from src.io.input_validation import simulation_config_3d_from_normalized

    directory = Path(run_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stage = resolved_payload.get("solver", {}).get("stage")
    contract = profile_facts(SCHUR_PROFILE)
    summary: dict[str, Any] = {
        "schema": "task039extra.v14.worker-summary.v1",
        "profile": SCHUR_PROFILE,
        "stage": stage,
        "source_sha": source_sha,
        "status": "STARTED",
        "official_result": None,
    }
    runtime = None
    handlers: dict[int, Any] = {}
    rhs_records: list[dict[str, Any]] | None = None
    try:
        if resolved_payload.get("dimension") != 3:
            raise ValueError("V14 requires dimension=3")
        if resolved_payload.get("method", {}).get("kind") != "full3d_iterative":
            raise ValueError("V14 requires method.kind=full3d_iterative")
        if resolved_payload.get("solver", {}).get("preconditioner") != SCHUR_PROFILE:
            raise ValueError("V14 worker received a different preconditioner")
        if resolved_payload.get("derived", {}).get("physical_intermediate_profile") != contract:
            raise ValueError("V14 resolved profile differs from the frozen contract")
        if not isinstance(source_sha, str) or len(source_sha) != 40:
            raise ValueError("V14 requires the complete launch source SHA")
        abi = _abi_facts()
        summary["abi"] = abi
        cfg = simulation_config_3d_from_normalized(resolved_payload)
        root = _repo_root()
        runtime = _V14Runtime(
            directory,
            str(stage),
            contract,
            root=root,
            source_sha=source_sha,
        )
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(
                signum, lambda _value, _frame: setattr(runtime, "stop_requested", True)
            )
        runtime.sample("preflight")
        if stage in {
            "Q0_CORE",
            "Q1_FULL_DIRECT",
            "Q2_SCHUR_DIRECT",
            "Q3_INTERFACE_CONTROL",
        }:
            # Only the common-cache estimate is checked before construction.
            # The Q1/Q2 matrix estimates are deliberately deferred until the
            # actual common core (and, for Q1/Q2, reviewed RHS packets) is
            # resident, immediately before volume allocation.
            _v14_known_preallocation_gate(
                runtime,
                str(stage),
                include_common=True,
                include_matrices=False,
            )
        if stage in {"Q4_ORIGINAL", "Q5_NOTCH", "Q6_FINALIZE"}:
            record = {
                "schema": f"task039extra.v14.{str(stage).lower()}.v1",
                "status": "NOT_RUN",
                "official_result": False,
                "stage_pass": False,
                "result_classification": "controlled_not_run_pending_prior_stage_qualification",
                "reason": "This execution slice does not include the later conditional stage",
            }
        else:
            cfg_common = _build_common(runtime, cfg)
            try:
                if stage == "Q0_CORE":
                    _v14_known_preallocation_gate(
                        runtime,
                        str(stage),
                        include_common=False,
                        include_matrices=True,
                    )
                    record = _q0_core(runtime, cfg_common)
                elif stage in {"Q1_FULL_DIRECT", "Q2_SCHUR_DIRECT"}:
                    rhs_records = _prepare_reviewed_rhs(
                        runtime,
                        cfg_common,
                        resolved_payload,
                        root,
                        53084,
                    )
                    _v14_known_preallocation_gate(
                        runtime,
                        str(stage),
                        include_common=False,
                        include_matrices=True,
                    )
                    if stage == "Q1_FULL_DIRECT":
                        record = _q1_full_direct(runtime, cfg_common, rhs_records)
                    else:
                        record = _q2_schur_direct(runtime, cfg_common, rhs_records)
                elif stage == "Q3_INTERFACE_CONTROL":
                    rhs_records = _prepare_reviewed_rhs(
                        runtime,
                        cfg_common,
                        resolved_payload,
                        root,
                        53084,
                    )
                    _v14_known_preallocation_gate(
                        runtime,
                        str(stage),
                        include_common=False,
                        include_matrices=True,
                    )
                    record = _q3_interface_control(
                        runtime,
                        cfg_common,
                        rhs_records,
                        resolved_payload,
                    )
                else:
                    raise ValueError(f"unsupported V14 stage {stage!r}")
            finally:
                _release_reviewed_rhs(rhs_records)
                runtime.set_phase("cleanup")
                _destroy_common(cfg_common, runtime)
                runtime.sample("post_common_cleanup")
        summary.update(record)
        summary["status"] = record["status"]
        summary["official_result"] = bool(record.get("official_result", False))
        summary["stage_pass"] = bool(
            record.get("stage_pass", summary["official_result"])
        )
        if "admission_pass" in record:
            summary["admission_pass"] = bool(record["admission_pass"])
        summary["result_classification"] = record.get(
            "result_classification",
            "DISCRETE_SOLVER_OUTPUT_PASS"
            if summary["official_result"]
            else record.get("status", "NOT_RUN"),
        )
    except V14ResourceStop as exc:
        summary.update(
            status="CONTROLLED_STOP",
            official_result=False,
            result_classification="RESOURCE_CONTROLLED_STOP",
            error=str(exc),
        )
    except Exception as exc:
        summary.update(
            status="FAILED",
            official_result=False,
            result_classification="WORKER_FAILED",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        _write_json(directory / "physical_p4_schur_v14_summary.json", summary)
        if runtime is not None:
            runtime.marker("v14_worker_complete", summary)
    return {
        "passed": bool(summary.get("stage_pass", summary.get("official_result"))),
        "errors": []
        if summary.get("stage_pass", summary.get("official_result"))
        else [str(summary.get("error", summary.get("status", "V14 stage did not pass")))],
        "summary": summary,
        "numerical_output_directory": str(directory / "numerical_output"),
    }


__all__ = ["run_physical_p4_schur_v14"]
