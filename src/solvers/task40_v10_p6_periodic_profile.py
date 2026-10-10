"""Explicit Task40 p6 two-cell periodic-reference inventories.

These values are admission expectations, not proof of a runtime inventory.
``validate_runtime_inventory`` must receive actual Basix/dofmap counts before
any q matrix is factored. The V10 profile remains the default and preserves its
original B0 dimensions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Mapping


@dataclass(frozen=True)
class Task40V10P6PeriodicProfile:
    name: str = "task40extra_v10_p6_y_orbit_reference_v1"
    degree: int = 6
    global_cell_axes: tuple[int, int, int] = (4, 4, 5)
    global_cell_count: int = 80
    global_storage_rows: int = 55950
    global_independent_rows: int = 52992
    global_interior_rows: int = 36000
    global_trace_rows: int = 16992
    q_count: int = 4
    rows_per_q: int = 13248
    trace_rows_per_q: int = 4248
    local_y_cells: int = 2
    replication_count: int = 2
    local_cell_count: int = 40
    local_storage_rows: int = 28722
    local_independent_rows: int = 26496
    local_interior_rows: int = 18000
    local_trace_rows: int = 8496
    local_width_per_q: int = 13248
    q_port_counts: tuple[int, ...] = (76, 152, 152, 152)
    sector_port_counts: tuple[int, ...] = (228, 304)

    def __post_init__(self) -> None:
        if (
            self.q_count != len(self.q_port_counts)
            or self.q_count != self.global_cell_axes[1]
            or self.q_count != self.local_y_cells * self.replication_count
            or self.replication_count != len(self.sector_port_counts)
        ):
            raise ValueError("Task40 p6 profile q, mesh, and twist inventory do not close")
        expected_sectors = tuple(
            sum(self.q_port_counts[twist + branch * self.replication_count]
                for branch in range(self.local_y_cells))
            for twist in range(self.replication_count)
        )
        if self.sector_port_counts != expected_sectors:
            raise ValueError("Task40 p6 profile twist counts do not match its q inventory")

    @property
    def mode_count(self) -> int:
        return sum(self.q_port_counts)

    @property
    def augmented_rows_per_q(self) -> tuple[int, ...]:
        return tuple(self.trace_rows_per_q + n for n in self.q_port_counts)

    def identity(self) -> dict[str, object]:
        result = asdict(self)
        for key, value in result.items():
            if isinstance(value, tuple):
                result[key] = list(value)
        result.update(
            schema=(
                "task40extra.review_v22_p6_periodic_profile.v1"
                if self.name.startswith("task40extra_v22_")
                else "task40extra.review_v20_p6_periodic_profile.v1"
                if self.name.startswith("task40extra_v20_")
                else
                "task40extra.review_v18_ny8_p6_periodic_profile.v1"
                if self.name.startswith("task40extra_v18_")
                else "task40extra.review_v16_p6_periodic_profile.v1"
                if self.name.startswith("task40extra_v16_")
                else "task40extra.review_v15_p6_periodic_profile.v1"
                if self.name.startswith("task40extra_v15_")
                else "task40extra.review_v10_p6_periodic_profile.v1"
                if self.name.startswith("task40extra_v10_")
                else "task40extra.review_v11_p6_periodic_profile.v1"
            ),
            mode_count=self.mode_count,
            augmented_rows_per_q=list(self.augmented_rows_per_q),
            status="DERIVED_EXPECTATIONS_RUNTIME_READBACK_REQUIRED",
            all_q_required=True,
            all_four_q_required=self.q_count == 4,
            ordinary_default_changed=False,
        )
        return result

    def validate_runtime_inventory(self, observed: Mapping[str, int]) -> dict[str, object]:
        """Fail closed unless actual Basix/dofmap and modal counts match p6."""
        expected = {
            "degree": self.degree,
            "global_cell_count": self.global_cell_count,
            "global_storage_rows": self.global_storage_rows,
            "global_independent_rows": self.global_independent_rows,
            "global_interior_rows": self.global_interior_rows,
            "global_trace_rows": self.global_trace_rows,
            "q_count": self.q_count,
            "rows_per_q": self.rows_per_q,
            "trace_rows_per_q": self.trace_rows_per_q,
            "local_cell_count": self.local_cell_count,
            "local_storage_rows": self.local_storage_rows,
            "local_independent_rows": self.local_independent_rows,
            "local_interior_rows": self.local_interior_rows,
            "local_trace_rows": self.local_trace_rows,
            "local_width_per_q": self.local_width_per_q,
            **{
                f"q_port_count_{q}": self.q_port_counts[q]
                for q in range(self.q_count)
            },
        }
        actual = {key: int(observed[key]) for key in expected if key in observed}
        mismatches = {
            key: {"expected": value, "actual": actual.get(key)}
            for key, value in expected.items()
            if actual.get(key) != value
        }
        if mismatches:
            label = (
                "Task40 V22"
                if self.name.startswith("task40extra_v22_")
                else "Task40 V20"
                if self.name.startswith("task40extra_v20_")
                else "Task40 V18 Ny8"
                if self.name.startswith("task40extra_v18_")
                else "Task40 V10"
            )
            raise ValueError(f"{label} p6 runtime inventory mismatch: {mismatches}")
        return {"status": "RUNTIME_INVENTORY_MATCH", "observed": actual,
                "profile": self.identity()}


TASK40_V10_P6_PROFILE = Task40V10P6PeriodicProfile()

TASK40_V11_P6_GX560_PROFILE = Task40V10P6PeriodicProfile(
    name="task40extra_v11_p6_y_orbit_gx560_reference_v1",
    global_cell_axes=(10, 4, 14),
    global_cell_count=560,
    global_storage_rows=380040,
    global_independent_rows=365760,
    global_interior_rows=252000,
    global_trace_rows=113760,
    rows_per_q=91440,
    trace_rows_per_q=28440,
    local_cell_count=280,
    local_storage_rows=195132,
    local_independent_rows=182880,
    local_interior_rows=126000,
    local_trace_rows=56880,
    local_width_per_q=91440,
    q_port_counts=(68, 68, 136, 68),
    sector_port_counts=(204, 136),
)

TASK40_V11_P6_GX784_PROFILE = Task40V10P6PeriodicProfile(
    name="task40extra_v11_p6_y_orbit_gx784_reference_v1",
    global_cell_axes=(14, 4, 14),
    global_cell_count=784,
    global_storage_rows=530400,
    global_independent_rows=512064,
    global_interior_rows=352800,
    global_trace_rows=159264,
    rows_per_q=128016,
    trace_rows_per_q=39816,
    local_cell_count=392,
    local_storage_rows=272340,
    local_independent_rows=256032,
    local_interior_rows=176400,
    local_trace_rows=79632,
    local_width_per_q=128016,
    q_port_counts=(68, 68, 136, 68),
    sector_port_counts=(204, 136),
)

TASK40_V15_P6_B0_PROFILE = Task40V10P6PeriodicProfile(
    name="task40extra_v15_p6_y_orbit_b0_reference_v1",
)

TASK40_V15_P6_GX560_PROFILE = Task40V10P6PeriodicProfile(
    name="task40extra_v15_p6_y_orbit_gx560_reference_v1",
    global_cell_axes=(10, 4, 14),
    global_cell_count=560,
    global_storage_rows=380040,
    global_independent_rows=365760,
    global_interior_rows=252000,
    global_trace_rows=113760,
    rows_per_q=91440,
    trace_rows_per_q=28440,
    local_cell_count=280,
    local_storage_rows=195132,
    local_independent_rows=182880,
    local_interior_rows=126000,
    local_trace_rows=56880,
    local_width_per_q=91440,
    q_port_counts=(68, 68, 136, 68),
    sector_port_counts=(204, 136),
)

TASK40_V15_P6_E1_PROFILE = Task40V10P6PeriodicProfile(
    name="task40extra_v15_p6_y_orbit_e1_reference_v1",
    global_cell_axes=(10, 4, 19),
    global_cell_count=760,
    global_storage_rows=514710,
    global_independent_rows=495360,
    global_interior_rows=342000,
    global_trace_rows=153360,
    rows_per_q=123840,
    trace_rows_per_q=38340,
    local_cell_count=380,
    local_storage_rows=264282,
    local_independent_rows=247680,
    local_interior_rows=171000,
    local_trace_rows=76680,
    local_width_per_q=123840,
    q_port_counts=(84, 168, 168, 168),
    sector_port_counts=(252, 336),
)

TASK40_V16_P6_GX560_PROFILE = replace(
    TASK40_V15_P6_GX560_PROFILE,
    name="task40extra_v16_p6_y_orbit_gx560_reference_v1",
)
TASK40_V16_P6_E1_PROFILE = replace(
    TASK40_V15_P6_E1_PROFILE,
    name="task40extra_v16_p6_y_orbit_e1_reference_v1",
)
TASK40_V17_P6_B0_PROFILE = replace(
    TASK40_V15_P6_B0_PROFILE,
    name="task40extra_v17_p6_y_orbit_b0_reference_v1",
)
TASK40_V17_P6_GX560_PROFILE = replace(
    TASK40_V15_P6_GX560_PROFILE,
    name="task40extra_v17_p6_y_orbit_gx560_reference_v1",
)
TASK40_V17_P6_E1_PROFILE = replace(
    TASK40_V15_P6_E1_PROFILE,
    name="task40extra_v17_p6_y_orbit_e1_reference_v1",
)


TASK40_V18_P6_B0_Y8_PROFILE = replace(
    TASK40_V17_P6_B0_PROFILE,
    name="task40extra_v18_p6_y_orbit_b0_y8_reference_v1",
    global_cell_axes=(4, 8, 5),
    global_cell_count=160,
    global_storage_rows=110406,
    global_independent_rows=105984,
    global_interior_rows=72000,
    global_trace_rows=33984,
    q_count=8,
    rows_per_q=13248,
    trace_rows_per_q=4248,
    local_y_cells=2,
    replication_count=4,
    local_cell_count=40,
    local_storage_rows=28722,
    local_independent_rows=26496,
    local_interior_rows=18000,
    local_trace_rows=8496,
    local_width_per_q=13248,
    q_port_counts=(76, 76, 76, 76, 0, 76, 76, 76),
    sector_port_counts=(76, 152, 152, 152),
)

TASK40_V20_P6_E2_PROFILE = Task40V10P6PeriodicProfile(
    name="task40extra_v20_p6_y_orbit_e2_reference_v1",
    global_cell_axes=(10, 4, 22),
    global_cell_count=880,
    global_storage_rows=595512,
    global_independent_rows=573120,
    global_interior_rows=396000,
    global_trace_rows=177120,
    rows_per_q=143280,
    trace_rows_per_q=44280,
    local_y_cells=2,
    replication_count=2,
    local_cell_count=440,
    local_storage_rows=305772,
    local_independent_rows=286560,
    local_interior_rows=198000,
    local_trace_rows=88560,
    local_width_per_q=143280,
    q_port_counts=(100, 200, 200, 200),
    sector_port_counts=(300, 400),
)

TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE = Task40V10P6PeriodicProfile(
    name="task40extra_v20_p6_y_orbit_target_original_ny8_v1",
    global_cell_axes=(272, 8, 14),
    global_cell_count=30464,
    global_storage_rows=20181348,
    global_independent_rows=19897344,
    global_interior_rows=13708800,
    global_trace_rows=6188544,
    q_count=8,
    rows_per_q=2487168,
    trace_rows_per_q=773568,
    local_y_cells=2,
    replication_count=4,
    local_cell_count=7616,
    local_storage_rows=5252256,
    local_independent_rows=4974336,
    local_interior_rows=3427200,
    local_trace_rows=1547136,
    local_width_per_q=2487168,
    q_port_counts=(4076, 4052, 4028, 3984, 3856, 3984, 4028, 4052),
    sector_port_counts=(7932, 8036, 8056, 8036),
)

TASK40_V22_P6_TARGET_ORIGINAL_NY8_PROFILE = replace(
    TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE,
    name="task40extra_v22_p6_y_orbit_target_original_ny8_operator_probe_v1",
)

TASK40_P6_PERIODIC_PROFILES = {
    TASK40_V10_P6_PROFILE.name: TASK40_V10_P6_PROFILE,
    TASK40_V11_P6_GX560_PROFILE.name: TASK40_V11_P6_GX560_PROFILE,
    TASK40_V11_P6_GX784_PROFILE.name: TASK40_V11_P6_GX784_PROFILE,
    TASK40_V15_P6_B0_PROFILE.name: TASK40_V15_P6_B0_PROFILE,
    TASK40_V15_P6_GX560_PROFILE.name: TASK40_V15_P6_GX560_PROFILE,
    TASK40_V15_P6_E1_PROFILE.name: TASK40_V15_P6_E1_PROFILE,
    TASK40_V16_P6_GX560_PROFILE.name: TASK40_V16_P6_GX560_PROFILE,
    TASK40_V16_P6_E1_PROFILE.name: TASK40_V16_P6_E1_PROFILE,
    TASK40_V17_P6_B0_PROFILE.name: TASK40_V17_P6_B0_PROFILE,
    TASK40_V17_P6_GX560_PROFILE.name: TASK40_V17_P6_GX560_PROFILE,
    TASK40_V17_P6_E1_PROFILE.name: TASK40_V17_P6_E1_PROFILE,
    TASK40_V18_P6_B0_Y8_PROFILE.name: TASK40_V18_P6_B0_Y8_PROFILE,
    TASK40_V20_P6_E2_PROFILE.name: TASK40_V20_P6_E2_PROFILE,
    TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE.name: TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE,
    TASK40_V22_P6_TARGET_ORIGINAL_NY8_PROFILE.name: TASK40_V22_P6_TARGET_ORIGINAL_NY8_PROFILE,
}

TASK40_V15_SELECTOR_PROFILE_IDENTITIES = frozenset(
    {
        "task40extra_v15_p6_y_orbit_b0_reference_v1",
        "task40extra_v15_p6_y_orbit_gx560_reference_v1",
        "task40extra_v15_p6_y_orbit_e1_reference_v1",
        "task40extra_v16_p6_y_orbit_gx560_reference_v1",
        "task40extra_v16_p6_y_orbit_e1_reference_v1",
        "task40extra_v17_p6_y_orbit_b0_reference_v1",
        "task40extra_v17_p6_y_orbit_gx560_reference_v1",
        "task40extra_v17_p6_y_orbit_e1_reference_v1",
        "task40extra_v18_p6_y_orbit_b0_y8_reference_v1",
        TASK40_V20_P6_E2_PROFILE.name,
        TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE.name,
        TASK40_V22_P6_TARGET_ORIGINAL_NY8_PROFILE.name,
    }
)
