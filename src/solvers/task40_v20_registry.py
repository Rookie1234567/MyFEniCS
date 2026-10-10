"""Small exact registry for the two reviewed Task40 V20 cases."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from src.geometry.task40_nonseparable_plan import (
    TASK40_E2_P6_V20_RUN_ID,
    TASK40_TARGET_ORIGINAL_NY8_V20_RUN_ID,
)
from src.io.physical_intermediate_profile import (
    TASK40_V20_P6_E2_PROFILE,
    TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE,
)


TASK40_V20_MODEL_ID = "task40extra_nonseparable_0p7nm"
TASK40_V22_TARGET_OPERATOR_PROFILE = "task40extra_v22_p6_y_orbit_target_original_ny8_operator_probe_v1"
TASK40_V22_TARGET_OPERATOR_RUN_ID = "task40extra_0p7nm_target_original_ny8_operator_probe_v22"


V20_STOP_STAGES = (
    "preflight",
    "geometry_inventory",
    "local_port_components",
    "build_and_symbolic",
    "one_q_numeric",
    "full",
)


@dataclass(frozen=True)
class Task40V20Case:
    model_id: str
    run_id: str
    profile: str
    mesh_id: str
    solver_stage: str
    input_path: str
    qualification_scope: str
    allowed_stop_stages: tuple[str, ...] = V20_STOP_STAGES


TASK40_V20_CASES_BY_PROFILE = MappingProxyType(
    {
        TASK40_V20_P6_E2_PROFILE: Task40V20Case(
            model_id=TASK40_V20_MODEL_ID,
            run_id=TASK40_E2_P6_V20_RUN_ID,
            profile=TASK40_V20_P6_E2_PROFILE,
            mesh_id="E2",
            solver_stage="V20_E2_REFERENCE",
            input_path=(
                "input/task40extra_0p7nm_engineering/"
                "nonseparable_e2_p6_reference_v20.dat"
            ),
            qualification_scope=(
                "E2 p6 reference growth case; target-original solver qualification is separate"
            ),
        ),
        TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE: Task40V20Case(
            model_id=TASK40_V20_MODEL_ID,
            run_id=TASK40_TARGET_ORIGINAL_NY8_V20_RUN_ID,
            profile=TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE,
            mesh_id="TARGET_ORIGINAL_NY8",
            solver_stage="V20_TARGET_NY8_RESOURCE_PILOT",
            input_path=(
                "input/task40extra_0p7nm_engineering/"
                "target_original_ny8_resource_pilot_v20.dat"
            ),
            qualification_scope=(
                "original-size resource/solver pilot; full-field accuracy is not qualified"
            ),
        ),
        TASK40_V22_TARGET_OPERATOR_PROFILE: Task40V20Case(
            model_id=TASK40_V20_MODEL_ID,
            run_id=TASK40_V22_TARGET_OPERATOR_RUN_ID,
            profile=TASK40_V22_TARGET_OPERATOR_PROFILE,
            mesh_id="TARGET_ORIGINAL_NY8",
            solver_stage="V22_TARGET_OPERATOR_PROBE",
            input_path=(
                "input/task40extra_0p7nm_engineering/"
                "target_original_ny8_operator_probe_v22.dat"
            ),
            qualification_scope=(
                "explicit V22 original-size generated B/D and bounded q-tile probe; "
                "full mode coverage and full-field accuracy remain pending"
            ),
            allowed_stop_stages=("preflight", "geometry_inventory", "target_operator_probe"),
        ),
    }
)
TASK40_V20_CASES_BY_RUN_ID = MappingProxyType(
    {case.run_id: case for case in TASK40_V20_CASES_BY_PROFILE.values()}
)


def task40_v20_case(*, run_id: str | None = None, profile: str | None = None) -> Task40V20Case:
    if (run_id is None) == (profile is None):
        raise ValueError("provide exactly one V20 run_id or profile")
    cases = TASK40_V20_CASES_BY_RUN_ID if run_id is not None else TASK40_V20_CASES_BY_PROFILE
    key = run_id if run_id is not None else profile
    try:
        return cases[str(key)]
    except KeyError as exc:
        raise ValueError(f"unregistered Task40 V20 case identity: {key!r}") from exc


__all__ = [
    "TASK40_V20_MODEL_ID",
    "TASK40_V22_TARGET_OPERATOR_PROFILE",
    "TASK40_V22_TARGET_OPERATOR_RUN_ID",
    "TASK40_V20_CASES_BY_PROFILE",
    "TASK40_V20_CASES_BY_RUN_ID",
    "V20_STOP_STAGES",
    "Task40V20Case",
    "task40_v20_case",
]
