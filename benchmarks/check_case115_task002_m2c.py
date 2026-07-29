"""Build/check compact Task002 Review-V3 M2C records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from src.forward_data.task002_full3d import task002_full3d_topology_identity
from src.forward_data.task002_schema import Task002ForwardParameters


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/cases/115_task002_full3d_hierarchy_qualification"
RECORDS = CASE / "records"
LF = "S_LF_FULL3D_STATIC_P4_H10"
HF = "S_HF_FULL3D_STATIC_P5_H10"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def build_topology_record() -> dict[str, Any]:
    rows = []
    for model_id in (LF, HF):
        for height in (115.0, 120.0, 125.0):
            for width in (16.0, 17.0, 18.0):
                parameters = Task002ForwardParameters(
                    height, width, 0.5, 0.0, model_id,
                )
                rows.append({
                    "height_nm": height, "width_x_nm": width,
                    "model_id": model_id,
                    "identity": task002_full3d_topology_identity(parameters),
                })
    invariant_keys = (
        "axis_cell_counts", "cell_count", "logical_connectivity_sha256",
        "material_tag_topology_sha256", "floquet_entity_topology_sha256",
        "dof_layout_identity_sha256", "material_region_cell_counts",
        "topology_element_hash",
    )
    per_fidelity = {}
    for model_id in (LF, HF):
        group = [row["identity"] for row in rows if row["model_id"] == model_id]
        per_fidelity[model_id] = {
            "geometry_count": len(group),
            "invariant": {key: len({json.dumps(item[key], sort_keys=True) for item in group}) == 1
                          for key in invariant_keys},
            "coordinate_hash_count": len({item["coordinate_sha256"] for item in group}),
            "all_material_planes_aligned": all(item["material_plane_alignment"] for item in group),
            "all_positive_axis_widths": all(item["positive_axis_widths"] for item in group),
        }
    return {
        "schema_version": "task002.case115-mesh-topology-identity.v1",
        "config_sha256": _sha(CASE / "config.json"),
        "expected_sha256": _sha(CASE / "expected.json"),
        "rows": rows, "per_fidelity_gates": per_fidelity,
        "gates": {
            "nine_geometries_each_fidelity": all(
                value["geometry_count"] == 9 for value in per_fidelity.values()
            ),
            "all_topology_fields_invariant": all(
                all(value["invariant"].values()) for value in per_fidelity.values()
            ),
            "coordinates_change_at_all_nine_geometries": all(
                value["coordinate_hash_count"] == 9 for value in per_fidelity.values()
            ),
            "material_planes_aligned": all(
                value["all_material_planes_aligned"] for value in per_fidelity.values()
            ),
            "positive_axis_widths": all(
                value["all_positive_axis_widths"] for value in per_fidelity.values()
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-topology", action="store_true")
    args = parser.parse_args()
    record = build_topology_record()
    if args.write_topology:
        RECORDS.mkdir(parents=True, exist_ok=True)
        (RECORDS / "mesh_topology_identity.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8",
        )
    print(json.dumps({"gates": record["gates"]}, indent=2))
    return 0 if all(record["gates"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
