"""Immutable V10 campaign-window loading and conservative budget helpers."""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from .workflow_timebase import (
    CONSERVATIVE_REALTIME,
    TimebaseInconsistency,
    checked_interval,
    clock_sample,
)


TASK40_V10_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_w10_wsl")
    / "campaign_window.json"
)
CAMPAIGN_SCHEMA = "task40extra.review_v10_campaign.v1"
CAMPAIGN_SECONDS = 86_400.0
CLOSEOUT_RESERVE_SECONDS = 600.0
CAMPAIGN_ACCOUNTING_NAME = "campaign_accounting_v10.jsonl"
TASK40_V22_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v22_wsl")
    / "campaign_window_v22.json"
)
TASK40_V22_CAMPAIGN_SHA256 = "a4da3d83c2a06672a2337a518dcc8a8bb5d12a446e995783e0f9dd406427d777"
TASK40_V22_CAMPAIGN_SECONDS = 21_600.0
TASK40_V22_CLOSEOUT_RESERVE_SECONDS = 600.0
TASK40_V22_CAMPAIGN_ID = "task40extra_v22_generated_production_operator"
TASK40_V22_REVIEW_SHA = "c2ec1e87cbbc88ba568537d6d1d591d76794611e"
TASK40_V22_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v22.md"
TASK40_V22_STAGE_SCOPE = (
    "implementation",
    "targeted_tests",
    "geometry_descriptor",
    "local_port_components",
    "target_operator_probe",
    "bounded_q_tiles",
    "checker",
    "persistence_readback",
    "closeout",
)
TASK40_V22_FORBIDDEN_SCOPE = (
    "all_target_q_csr",
    "target_global_factor",
    "target_ksp",
    "full_target_field",
)
TASK40_V22_PARENT_WINDOW = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json",
    "sha256": "b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0",
    "t0_utc": "2026-10-09T01:45:00.727771902Z",
    "deadline_utc": "2026-10-10T01:45:00.727771902Z",
    "verified_expired": True,
}
TASK40_V22_PARENT_LEDGER = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_accounting_v10.jsonl",
    "sha256": "7ea9e880520accf2fd87d8ee63b894c7e3e1ec366308dd0c8bb4492abd705a11",
    "last_persisted_cumulative_seconds": 66919.72841801553,
    "unsettled_interval": "UNKNOWN_RETAINED_UNMODIFIED",
    "historical_cleanup": "UNKNOWN_RETAINED_UNMODIFIED",
}


def _utc_ns(value: Any) -> int:
    from calendar import timegm
    from datetime import datetime, timezone

    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("campaign timestamps must be explicit UTC ISO strings")
    whole, dot, fraction = value[:-1].partition(".")
    instant = datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    nanos = int((fraction + "000000000")[:9]) if dot else 0
    if dot and (not fraction.isdigit() or len(fraction) > 9):
        raise ValueError("campaign timestamp precision must not exceed nanoseconds")
    return timegm(instant.utctimetuple()) * 1_000_000_000 + nanos


def _validate_v22_campaign_registration(
    resolved: Path, digest: str, payload: Mapping[str, Any]
) -> None:
    expected_path = (
        Path(__file__).resolve().parents[2] / TASK40_V22_CAMPAIGN_WINDOW
    ).resolve()
    if resolved != expected_path:
        raise ValueError("the V22 campaign window is not at its registered path")
    if digest != TASK40_V22_CAMPAIGN_SHA256:
        raise ValueError("the registered V22 campaign window SHA-256 changed")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": TASK40_V22_CAMPAIGN_ID,
        "authority": "User-authorized Review V22 section 7: independent six-hour work package",
        "active_review_sha": TASK40_V22_REVIEW_SHA,
        "active_review_path": TASK40_V22_REVIEW_PATH,
        "source_at_entry": TASK40_V22_REVIEW_SHA,
        "t0_utc": "2026-10-10T02:34:32Z",
        "deadline_utc": "2026-10-10T08:34:32Z",
        "campaign_seconds": TASK40_V22_CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": TASK40_V22_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(TASK40_V22_STAGE_SCOPE),
        "forbidden_scope": list(TASK40_V22_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "parent_window": TASK40_V22_PARENT_WINDOW,
        "parent_ledger": TASK40_V22_PARENT_LEDGER,
    }
    changed = [
        key for key, value in expected_fields.items() if payload.get(key) != value
    ]
    if changed:
        raise ValueError(f"registered V22 campaign identity or scope changed: {changed}")


@dataclass(frozen=True)
class FixedCampaignWindow:
    path: Path
    sha256: str
    payload: Mapping[str, Any]
    anchor: Mapping[str, Any]
    t0_utc_ns: int
    deadline_utc_ns: int
    total_seconds: float
    bootstrap_seconds: float
    closeout_seconds: float

    @property
    def cutoff_seconds(self) -> float:
        return self.total_seconds - self.closeout_seconds

    def observe(self, *, label: str = "campaign_observation") -> dict[str, Any]:
        record = CampaignAccount(self).record_sample(label=label)
        now = record["sample"]
        deadline_remaining = (self.deadline_utc_ns - int(now["utc_ns"])) / 1e9
        remaining = min(
            self.cutoff_seconds - float(record["cumulative_charged_seconds"]),
            deadline_remaining - self.closeout_seconds,
        )
        adjacent = float(record["adjacent_interval"]["budget_seconds"])
        cumulative = float(record["cumulative_charged_seconds"])
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "schema": CAMPAIGN_SCHEMA,
            "t0_utc_ns": self.t0_utc_ns,
            "deadline_utc_ns": self.deadline_utc_ns,
            "campaign_seconds": self.total_seconds,
            "closeout_reserve_seconds": self.closeout_seconds,
            "bootstrap_charged_seconds": self.bootstrap_seconds,
            "adjacent_charged_seconds": adjacent,
            "cumulative_charged_seconds": cumulative,
            "charged_seconds": cumulative,
            "remaining_numerical_seconds": max(0.0, float(remaining)),
            "accounting_record": record,
            "sample": now,
        }


def time_namespace_identity() -> dict[str, str]:
    """Read both Linux time-namespace identities used by the live process."""
    return {
        "time": os.readlink("/proc/self/ns/time"),
        "time_for_children": os.readlink("/proc/self/ns/time_for_children"),
    }


def _last_jsonl_record(stream) -> dict[str, Any] | None:
    stream.seek(0, os.SEEK_END)
    end = stream.tell()
    if end == 0:
        return None
    cursor = end - 1
    stream.seek(cursor)
    if stream.read(1) == b"\n":
        cursor -= 1
    line_start = 0
    while cursor >= 0:
        start = max(0, cursor - 4095)
        stream.seek(start)
        block = stream.read(cursor - start + 1)
        separator = block.rfind(b"\n")
        if separator >= 0:
            line_start = start + separator + 1
            break
        cursor = start - 1
    stream.seek(line_start)
    try:
        value = json.loads(stream.readline())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TimebaseInconsistency("campaign accounting tail is not valid JSON") from exc
    if not isinstance(value, dict):
        raise TimebaseInconsistency("campaign accounting tail is not an object")
    return value


class CampaignAccount:
    """Append-only adjacent clock accounting shared across service attempts."""

    def __init__(self, window: FixedCampaignWindow, path: str | Path | None = None):
        self.window = window
        self.path = Path(path or (window.path.parent / CAMPAIGN_ACCOUNTING_NAME)).resolve()

    def record_sample(
        self,
        sample: Mapping[str, Any] | None = None,
        *,
        label: str,
        namespace_identity: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            # Capture clocks and namespace only after the exclusive lock. This
            # keeps the single-writer sequence aligned with the sample order.
            current = dict(sample or clock_sample(include_boot_id=True))
            namespace = dict(namespace_identity or time_namespace_identity())
            if current.get("boot_id") != self.window.anchor.get("boot_id"):
                raise TimebaseInconsistency(
                    "campaign sample boot identity differs from the fixed window"
                )
            if set(namespace) != {"time", "time_for_children"} or any(
                not isinstance(value, str) or not value for value in namespace.values()
            ):
                raise TimebaseInconsistency(
                    "campaign time-namespace identity is incomplete"
                )
            previous = _last_jsonl_record(stream)
            if previous is None:
                previous_sample = dict(self.window.anchor)
                cumulative = self.window.bootstrap_seconds
                prior_namespace = namespace
                sequence = 0
            else:
                if (
                    previous.get("schema")
                    != "task40extra.review_v10_campaign_accounting.v1"
                    or previous.get("campaign_window_sha256") != self.window.sha256
                    or previous.get("boot_id") != self.window.anchor.get("boot_id")
                ):
                    raise TimebaseInconsistency(
                        "campaign accounting is bound to a different window or boot"
                    )
                previous_sample = previous.get("sample")
                cumulative = float(previous.get("cumulative_charged_seconds", -1.0))
                prior_namespace = previous.get("time_namespace_identity")
                sequence = int(previous.get("sequence", -1)) + 1
                if (
                    not isinstance(previous_sample, dict)
                    or cumulative < self.window.bootstrap_seconds
                    or prior_namespace != namespace
                ):
                    raise TimebaseInconsistency(
                        "campaign accounting clock or namespace chain is broken"
                    )
            interval = checked_interval(
                previous_sample, current, policy=CONSERVATIVE_REALTIME
            )
            cumulative += float(interval["budget_seconds"])
            record = {
                "schema": "task40extra.review_v10_campaign_accounting.v1",
                "sequence": sequence,
                "label": str(label),
                "campaign_window_sha256": self.window.sha256,
                "t0_utc_ns": self.window.t0_utc_ns,
                "deadline_utc_ns": self.window.deadline_utc_ns,
                "boot_id": self.window.anchor["boot_id"],
                "time_namespace_identity": namespace,
                "previous_sample": previous_sample,
                "sample": current,
                "adjacent_interval": interval,
                "bootstrap_charged_seconds": self.window.bootstrap_seconds,
                "cumulative_charged_seconds": cumulative,
                "cutoff_seconds": self.window.cutoff_seconds,
            }
            stream.seek(0, os.SEEK_END)
            stream.write(
                (
                    json.dumps(
                        record, sort_keys=True, separators=(",", ":"), allow_nan=False
                    )
                    + "\n"
                ).encode()
            )
            stream.flush()
            os.fsync(stream.fileno())
            return record


def read_campaign_state(
    window: FixedCampaignWindow,
    path: str | Path | None = None,
    *,
    sample: Mapping[str, Any] | None = None,
    namespace_identity: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Read worker-visible remaining time without appending to the shared ledger."""
    account_path = Path(path or (window.path.parent / CAMPAIGN_ACCOUNTING_NAME)).resolve()
    with account_path.open("rb") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_SH)
        previous = _last_jsonl_record(stream)
        current = dict(sample or clock_sample(include_boot_id=True))
        namespace = dict(namespace_identity or time_namespace_identity())
        if previous is None:
            raise TimebaseInconsistency("campaign worker started before the watchdog bound its clock")
        if (
            previous.get("schema") != "task40extra.review_v10_campaign_accounting.v1"
            or previous.get("campaign_window_sha256") != window.sha256
            or previous.get("boot_id") != window.anchor.get("boot_id")
            or previous.get("deadline_utc_ns") != window.deadline_utc_ns
        ):
            raise TimebaseInconsistency("campaign worker read a different fixed window or boot")
        if current.get("boot_id") != window.anchor.get("boot_id"):
            raise TimebaseInconsistency("campaign worker boot identity differs from the fixed window")
        if previous.get("time_namespace_identity") != namespace:
            raise TimebaseInconsistency("campaign worker time namespace differs from the watchdog")
        last_sample = previous.get("sample")
        cumulative = float(previous.get("cumulative_charged_seconds", -1.0))
        if not isinstance(last_sample, dict) or cumulative < window.bootstrap_seconds:
            raise TimebaseInconsistency("campaign worker read an incomplete accounting tail")
        adjacent = checked_interval(
            last_sample, current, policy=CONSERVATIVE_REALTIME
        )
        projected_cumulative = cumulative + float(adjacent["budget_seconds"])
        deadline_remaining = (window.deadline_utc_ns - int(current["utc_ns"])) / 1e9
        remaining = min(
            window.cutoff_seconds - projected_cumulative,
            deadline_remaining - window.closeout_seconds,
        )
        return {
            "path": str(account_path),
            "campaign_window_sha256": window.sha256,
            "t0_utc_ns": window.t0_utc_ns,
            "deadline_utc_ns": window.deadline_utc_ns,
            "accounting_record": previous,
            "sample": current,
            "adjacent_interval": adjacent,
            "projected_cumulative_charged_seconds": projected_cumulative,
            "remaining_numerical_seconds": max(0.0, float(remaining)),
            "read_only": True,
        }


def load_fixed_campaign_window(
    path: str | Path = TASK40_V10_CAMPAIGN_WINDOW,
    *,
    require_current_boot: bool = True,
) -> FixedCampaignWindow:
    resolved = Path(path).resolve()
    raw = resolved.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("schema") != CAMPAIGN_SCHEMA:
        raise ValueError("the fixed Task40 V10 campaign window schema is invalid")
    if payload.get("window_refreshed") is not False or payload.get(
        "old_costs_and_unknowns_preserved"
    ) is not True:
        raise ValueError("the fixed campaign window was refreshed or erased prior costs")
    digest = hashlib.sha256(raw).hexdigest()
    v22_path = (
        Path(__file__).resolve().parents[2] / TASK40_V22_CAMPAIGN_WINDOW
    ).resolve()
    is_v22 = resolved == v22_path
    if is_v22:
        _validate_v22_campaign_registration(resolved, digest, payload)
        expected_total = TASK40_V22_CAMPAIGN_SECONDS
    else:
        expected_total = CAMPAIGN_SECONDS
    total = float(payload.get("campaign_seconds", 0.0))
    if total != expected_total or payload.get("time_policy") != CONSERVATIVE_REALTIME:
        raise ValueError("the fixed campaign duration or clock policy differs from its registration")
    t0_ns = _utc_ns(payload.get("t0_utc"))
    deadline_ns = _utc_ns(payload.get("deadline_utc"))
    if deadline_ns - t0_ns != int(total * 1e9):
        raise ValueError("the fixed campaign deadline does not equal its registered T0 plus duration")
    initial = payload.get("first_full_three_clock_sample")
    if not isinstance(initial, dict):
        raise ValueError("the initial full monotone/UTC/boot sample is missing")
    anchor = {
        "monotonic": float(initial["monotonic"]),
        "boottime": float(initial["boottime"]),
        "utc_ns": int(initial["utc_ns"]),
        "boot_id": str(initial["boot_id"]),
    }
    if (
        not re.fullmatch(r"[0-9a-fA-F-]{36}", anchor["boot_id"])
        or payload.get("initial_boot_id") != anchor["boot_id"]
    ):
        raise ValueError("the initial boot identity is malformed or inconsistent")
    bootstrap_utc = float(payload.get("bootstrap_utc_elapsed_seconds", -1.0))
    bootstrap_boot = float(payload.get("bootstrap_boottime_elapsed_seconds", -1.0))
    if min(bootstrap_utc, bootstrap_boot) < 0:
        raise ValueError("campaign bootstrap accounting must be non-negative")
    bootstrap = max(bootstrap_utc, bootstrap_boot)
    if abs((anchor["utc_ns"] - t0_ns) / 1e9 - bootstrap_utc) > 1e-6:
        raise ValueError("the recorded UTC bootstrap debit does not match the immutable T0")
    if payload.get("bootstrap_time_treatment") is None:
        raise ValueError("campaign startup and preparation costs are not accounted")
    closeout = float(payload.get("closeout_reserve_seconds", CLOSEOUT_RESERVE_SECONDS))
    expected_closeout = (
        TASK40_V22_CLOSEOUT_RESERVE_SECONDS if is_v22 else CLOSEOUT_RESERVE_SECONDS
    )
    if closeout != expected_closeout or closeout >= total:
        raise ValueError("the fixed campaign closeout reserve changed")
    if require_current_boot:
        now = clock_sample(include_boot_id=True)
        if now.get("boot_id") != anchor["boot_id"]:
            raise TimebaseInconsistency("WSL boot identity changed during the active V10 campaign")
    return FixedCampaignWindow(
        path=resolved,
        sha256=digest,
        payload=payload,
        anchor=anchor,
        t0_utc_ns=t0_ns,
        deadline_utc_ns=deadline_ns,
        total_seconds=total,
        bootstrap_seconds=bootstrap,
        closeout_seconds=closeout,
    )


__all__ = [
    "CAMPAIGN_ACCOUNTING_NAME",
    "CAMPAIGN_SCHEMA",
    "CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V22_CAMPAIGN_WINDOW",
    "TASK40_V22_CAMPAIGN_SHA256",
    "TASK40_V22_CAMPAIGN_SECONDS",
    "TASK40_V22_CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V22_CAMPAIGN_ID",
    "TASK40_V22_REVIEW_SHA",
    "TASK40_V22_REVIEW_PATH",
    "TASK40_V22_STAGE_SCOPE",
    "TASK40_V22_FORBIDDEN_SCOPE",
    "TASK40_V22_PARENT_WINDOW",
    "TASK40_V22_PARENT_LEDGER",
    "CampaignAccount",
    "FixedCampaignWindow",
    "TASK40_V10_CAMPAIGN_WINDOW",
    "load_fixed_campaign_window",
    "read_campaign_state",
    "time_namespace_identity",
]
