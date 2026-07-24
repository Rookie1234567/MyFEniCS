"""Build the Task035b same-mesh multi-goal h/p screening record."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from src.adaptivity.multigoal_hp_classifier import (
    build_cell_geometry_priors,
    classify_multigoal_hp_candidates,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_record(
    base_classifier: dict[str, Any],
    dwr_authority: dict[str, Any],
    *,
    base_source: dict[str, str] | None = None,
    dwr_source: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Rebuild the fixed h10 hexa mesh and join all available cell signals."""

    cfg = replace(
        target_stage4_config(degree=4, h_nm=10.0),
        mesh_cell_type="hexahedron",
        unique_output=False,
    )
    with tempfile.TemporaryDirectory(
        prefix="task035b-multigoal-classifier-"
    ) as directory:
        mesh_data = build_airbox_mesh_3d(cfg, Path(directory))
        priors = build_cell_geometry_priors(mesh_data, cfg)
    classifier = classify_multigoal_hp_candidates(
        base_classifier,
        dwr_authority,
        priors,
    )
    return {
        **classifier,
        "source_records": {
            "base_p4_p5_p6_classifier": base_source,
            "p4_p5_multigoal_dwr": dwr_source,
        },
        "cell_geometry_priors": priors,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-classifier-record", type=Path, required=True)
    parser.add_argument("--dwr-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    base_path = args.base_classifier_record.resolve()
    dwr_path = args.dwr_record.resolve()
    record = build_record(
        json.loads(base_path.read_text(encoding="utf-8")),
        json.loads(dwr_path.read_text(encoding="utf-8")),
        base_source={"path": str(base_path), "sha256": _sha256(base_path)},
        dwr_source={"path": str(dwr_path), "sha256": _sha256(dwr_path)},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
