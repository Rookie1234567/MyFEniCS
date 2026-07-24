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
    upgrade_multigoal_hp_classifier_v3,
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
    generator_source_commit: str | None = None,
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
        "generator_source": {
            "commit_sha": generator_source_commit,
            "verified_clean_sha": generator_source_commit,
        },
        "cell_geometry_priors": priors,
    }


def build_record_v3(
    v2_classifier: dict[str, Any],
    p6_projection: dict[str, Any],
    sequential_competition: dict[str, Any],
    *,
    v2_source: dict[str, str] | None = None,
    projection_source: dict[str, str] | None = None,
    competition_source: dict[str, str] | None = None,
    generator_source_commit: str | None = None,
) -> dict[str, Any]:
    """Upgrade one qualified v2 record with measured p6 signals."""

    classifier = upgrade_multigoal_hp_classifier_v3(
        v2_classifier,
        p6_projection,
        sequential_competition,
    )
    return {
        **classifier,
        "source_records": {
            "v2_classifier": v2_source,
            "p6_projection_signals": projection_source,
            "sequential_h_vs_p_competition": competition_source,
        },
        "generator_source": {
            "commit_sha": generator_source_commit,
            "verified_clean_sha": generator_source_commit,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-classifier-record", type=Path, required=True)
    parser.add_argument("--dwr-record", type=Path, required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--projection-record", type=Path)
    parser.add_argument("--competition-record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if (
        len(args.verified_clean_sha) != 40
        or any(
            character not in "0123456789abcdef"
            for character in args.verified_clean_sha.lower()
        )
    ):
        raise ValueError("--verified-clean-sha must be a full 40-hex commit")
    base_path = args.base_classifier_record.resolve()
    dwr_path = args.dwr_record.resolve()
    if (args.projection_record is None) != (
        args.competition_record is None
    ):
        raise ValueError(
            "--projection-record and --competition-record must be paired"
        )
    if args.projection_record is None:
        record = build_record(
            json.loads(base_path.read_text(encoding="utf-8")),
            json.loads(dwr_path.read_text(encoding="utf-8")),
            base_source={"path": str(base_path), "sha256": _sha256(base_path)},
            dwr_source={"path": str(dwr_path), "sha256": _sha256(dwr_path)},
            generator_source_commit=args.verified_clean_sha,
        )
    else:
        projection_path = args.projection_record.resolve()
        competition_path = args.competition_record.resolve()
        record = build_record_v3(
            json.loads(base_path.read_text(encoding="utf-8")),
            json.loads(projection_path.read_text(encoding="utf-8")),
            json.loads(competition_path.read_text(encoding="utf-8")),
            v2_source={
                "path": str(base_path),
                "sha256": _sha256(base_path),
            },
            projection_source={
                "path": str(projection_path),
                "sha256": _sha256(projection_path),
            },
            competition_source={
                "path": str(competition_path),
                "sha256": _sha256(competition_path),
            },
            generator_source_commit=args.verified_clean_sha,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
