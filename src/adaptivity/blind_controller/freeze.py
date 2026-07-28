"""Content-bound frozen-candidate receipt emitted after blind stopping."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Mapping

from .contracts import FORMAL_GOAL_IDS
from .state_machine import (
    BlindTrial,
    validate_internal_certificate_payload,
)


_TWO_PATH_KEYS = frozenset(
    {
        "schema_version",
        "pass",
        "algorithm_id",
        "source_sha",
        "physical_identity_sha256",
        "left_trial_id",
        "right_trial_id",
        "left_initial_path_id",
        "right_initial_path_id",
        "left_initial_mesh_forest_sha256",
        "right_initial_mesh_forest_sha256",
        "left_cycle_chain_root_sha256",
        "right_cycle_chain_root_sha256",
        "left_output_sha256",
        "right_output_sha256",
        "maximum_normalized_goal_distance",
        "per_goal",
    }
)
_RESOURCE_AUTHORITY_KEYS = frozenset(
    {
        "schema_version",
        "active_dofs",
        "rows",
        "matrix_nnz",
        "factor_nnz",
        "solver_peak_bytes",
        "swap_peak_bytes",
        "mpi_size",
        "same_solver_lifecycle_telemetry",
    }
)


@dataclass(frozen=True, slots=True)
class FrozenCandidate:
    """Immutable identities needed before the evaluator is allowed to audit."""

    schema_version: str
    trial_id: str
    algorithm_id: str
    source_sha: str
    initial_path_id: str
    initial_mesh_forest_sha256: str
    cycle_chain_root_sha256: str
    cycle_index: int
    physical_identity_sha256: str
    mesh_forest_sha256: str
    degree_map_sha256: str
    output_sha256: str
    internal_certificate_sha256: str
    resource_inventory_sha256: str
    two_path_gate_sha256: str
    frozen_payload_sha256: str


def freeze_candidate(
    trial: BlindTrial,
    *,
    two_path_gate: Mapping[str, object],
    physical_identity_sha256: str,
    resource_authority: Mapping[str, object],
) -> FrozenCandidate:
    """Freeze a ready endpoint; no numerical input is accepted afterwards."""

    if not trial.results:
        raise ValueError("trial endpoint is not freeze-ready")
    endpoint = trial.results[-1]
    validate_internal_certificate_payload(
        endpoint.internal_certificate,
        expected_result=endpoint,
    )
    if endpoint.internal_certificate["freeze_ready"] is not True:
        raise ValueError("trial endpoint certificate is not freeze-ready")
    if set(two_path_gate) != set(_TWO_PATH_KEYS):
        raise ValueError("two-path gate does not use the closed schema")
    if (
        two_path_gate["schema_version"]
        != "task035e.two-path-freeze-gate.v1"
        or two_path_gate["pass"] is not True
    ):
        raise ValueError("independent-path agreement did not pass")
    if two_path_gate["algorithm_id"] != trial.algorithm_id:
        raise ValueError("two-path gate algorithm does not match the trial")
    if two_path_gate["source_sha"] != trial.source_sha:
        raise ValueError("two-path gate source does not match the trial")
    if (
        two_path_gate["physical_identity_sha256"]
        != trial.physical_identity_sha256
    ):
        raise ValueError("two-path gate physical identity does not match")
    if physical_identity_sha256 != trial.physical_identity_sha256:
        raise ValueError("freeze physical identity does not match the trial")
    if trial.trial_id not in {
        two_path_gate["left_trial_id"],
        two_path_gate["right_trial_id"],
    }:
        raise ValueError("two-path gate does not bind this trial ID")
    if trial.initial_path_id not in {
        two_path_gate["left_initial_path_id"],
        two_path_gate["right_initial_path_id"],
    }:
        raise ValueError("two-path gate does not bind this initial path")
    if trial.initial_mesh_forest_sha256 not in {
        two_path_gate["left_initial_mesh_forest_sha256"],
        two_path_gate["right_initial_mesh_forest_sha256"],
    }:
        raise ValueError("two-path gate does not bind this initial forest")
    if trial.cycle_chain_root_sha256 not in {
        two_path_gate["left_cycle_chain_root_sha256"],
        two_path_gate["right_cycle_chain_root_sha256"],
    }:
        raise ValueError("two-path gate does not bind this cycle chain")
    if not isinstance(two_path_gate["per_goal"], Mapping) or set(
        two_path_gate["per_goal"]
    ) != set(FORMAL_GOAL_IDS):
        raise ValueError("two-path gate must bind all formal goals")
    distances = tuple(
        float(two_path_gate["per_goal"][goal_id])
        for goal_id in FORMAL_GOAL_IDS
    )
    if any(
        not math.isfinite(value) or not 0.0 <= value <= 1.0
        for value in distances
    ):
        raise ValueError("two-path per-goal distance exceeds the blind tolerance")
    maximum = float(two_path_gate["maximum_normalized_goal_distance"])
    if (
        not math.isfinite(maximum)
        or not math.isclose(maximum, max(distances), rel_tol=0.0, abs_tol=1.0e-15)
        or maximum > 1.0
    ):
        raise ValueError("two-path maximum distance is invalid")
    for label, value in (
        ("physical_identity_sha256", physical_identity_sha256),
        ("complete_output_sha256", endpoint.complete_output_sha256),
    ):
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(
                character not in "0123456789abcdef"
                for character in value
            )
        ):
            raise ValueError(f"{label} must be a lowercase SHA-256")
    if endpoint.complete_output_sha256 not in {
        two_path_gate.get("left_output_sha256"),
        two_path_gate.get("right_output_sha256"),
    }:
        raise ValueError("two-path gate does not bind this endpoint output")
    if set(resource_authority) != set(_RESOURCE_AUTHORITY_KEYS):
        raise ValueError("resource authority does not use the closed schema")
    if (
        resource_authority["schema_version"]
        != "task035e.resource-authority.v1"
        or resource_authority["mpi_size"] != 8
        or resource_authority["same_solver_lifecycle_telemetry"] is not True
    ):
        raise ValueError("resource authority is not formally qualified")
    structural_names = (
        "active_dofs",
        "rows",
        "matrix_nnz",
        "factor_nnz",
        "solver_peak_bytes",
    )
    for name in (*structural_names, "swap_peak_bytes"):
        value = resource_authority[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"resource authority {name} must be nonnegative")
    if resource_authority["swap_peak_bytes"] != 0:
        raise ValueError("resource authority must prove zero swap")
    resource_authority_sha256 = hashlib.sha256(
        json.dumps(
            dict(resource_authority),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    if resource_authority_sha256 != endpoint.resource_inventory_sha256:
        raise ValueError(
            "resource authority does not bind the endpoint inventory"
        )
    two_path_gate_sha256 = hashlib.sha256(
        json.dumps(
            dict(two_path_gate),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    payload = {
        "schema_version": "task035e.hidden-audit-freeze-receipt.v1",
        "trial_id": trial.trial_id,
        "algorithm_id": trial.algorithm_id,
        "source_sha": trial.source_sha,
        "initial_path_id": trial.initial_path_id,
        "initial_mesh_forest_sha256": trial.initial_mesh_forest_sha256,
        "cycle_chain_root_sha256": trial.cycle_chain_root_sha256,
        "cycle_index": endpoint.cycle_index,
        "physical_identity_sha256": physical_identity_sha256,
        "mesh_forest_sha256": endpoint.mesh_forest_sha256,
        "degree_map_sha256": endpoint.degree_map_sha256,
        "output_sha256": endpoint.complete_output_sha256,
        "internal_certificate_sha256": (
            hashlib.sha256(
                json.dumps(
                    dict(endpoint.internal_certificate),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("ascii")
            ).hexdigest()
        ),
        "resource_inventory_sha256": resource_authority_sha256,
        "two_path_gate_sha256": two_path_gate_sha256,
    }
    frozen_sha = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    return FrozenCandidate(
        **payload,
        frozen_payload_sha256=frozen_sha,
    )


__all__ = ["FrozenCandidate", "freeze_candidate"]
