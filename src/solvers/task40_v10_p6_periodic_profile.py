"""Explicit Task40 V10 p6 two-cell periodic-reference inventory.

These values describe the W0 algebra fixture. They are admission expectations,
not proof of a runtime inventory; ``validate_runtime_inventory`` must receive
actual Basix/dofmap counts before any q matrix is factored.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
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
    q_port_counts: tuple[int, int, int, int] = (76, 152, 152, 152)
    sector_port_counts: tuple[int, int] = (228, 304)

    @property
    def augmented_rows_per_q(self) -> tuple[int, int, int, int]:
        return tuple(self.trace_rows_per_q + n for n in self.q_port_counts)

    def identity(self) -> dict[str, object]:
        result = asdict(self)
        result.update(
            schema="task40extra.review_v10_p6_periodic_profile.v1",
            augmented_rows_per_q=list(self.augmented_rows_per_q),
            status="DERIVED_EXPECTATIONS_RUNTIME_READBACK_REQUIRED",
            all_four_q_required=True,
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
            "q_port_count_0": self.q_port_counts[0],
            "q_port_count_1": self.q_port_counts[1],
            "q_port_count_2": self.q_port_counts[2],
            "q_port_count_3": self.q_port_counts[3],
        }
        actual = {key: int(observed[key]) for key in expected if key in observed}
        mismatches = {
            key: {"expected": value, "actual": actual.get(key)}
            for key, value in expected.items()
            if actual.get(key) != value
        }
        if mismatches:
            raise ValueError(f"Task40 V10 p6 runtime inventory mismatch: {mismatches}")
        return {"status": "RUNTIME_INVENTORY_MATCH", "observed": actual,
                "profile": self.identity()}


TASK40_V10_P6_PROFILE = Task40V10P6PeriodicProfile()
