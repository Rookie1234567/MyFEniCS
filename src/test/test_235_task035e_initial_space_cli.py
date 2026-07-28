from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.task035e_initial_space import write_initial_space_bundle


_SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"


@pytest.mark.parametrize(("path_id", "h_nm"), (("A", 20.0), ("B", 15.0)))
def test_initial_space_bundle_is_immutable_and_hash_bound(
    tmp_path: Path,
    path_id: str,
    h_nm: float,
) -> None:
    plan_path = tmp_path / f"path_{path_id.lower()}_plan.json"
    authority_path = tmp_path / f"path_{path_id.lower()}_authority.json"
    receipt = write_initial_space_bundle(
        path_id=path_id,
        source_sha=_SOURCE_SHA,
        plan_path=plan_path,
        authority_path=authority_path,
    )

    plan_bytes = plan_path.read_bytes()
    authority_bytes = authority_path.read_bytes()
    plan = json.loads(plan_bytes)
    authority = json.loads(authority_bytes)
    assert receipt.plan_sha256 == hashlib.sha256(plan_bytes).hexdigest()
    assert receipt.authority_sha256 == hashlib.sha256(
        authority_bytes
    ).hexdigest()
    assert authority["source_sha"] == _SOURCE_SHA
    assert authority["path_id"] == path_id
    assert authority["nominal_h_nm"] == h_nm
    assert authority["formal_mpi_size"] == 8
    assert authority["plan_file_sha256"] == receipt.plan_sha256
    assert authority["plan_content_sha256"] == (
        authority["plan_payload_sha256"]
    )
    assert plan["provenance"]["solved_field_inputs_consumed"] is False
    assert plan["provenance"]["goal_value_inputs_consumed"] is False
    assert plan["provenance"]["dwr_inputs_consumed"] is False
    assert plan["provenance"]["error_map_inputs_consumed"] is False
    assert (plan_path.stat().st_mode & 0o777) == 0o600
    assert (authority_path.stat().st_mode & 0o777) == 0o600

    with pytest.raises(FileExistsError):
        write_initial_space_bundle(
            path_id=path_id,
            source_sha=_SOURCE_SHA,
            plan_path=plan_path,
            authority_path=authority_path,
        )


def test_initial_space_bundle_rejects_non_mpi8_and_bad_source(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="MPI8"):
        write_initial_space_bundle(
            path_id="A",
            source_sha=_SOURCE_SHA,
            plan_path=tmp_path / "plan.json",
            authority_path=tmp_path / "authority.json",
            mpi_size=1,
        )
    with pytest.raises(ValueError, match="source_sha"):
        write_initial_space_bundle(
            path_id="A",
            source_sha="not-a-sha",
            plan_path=tmp_path / "plan.json",
            authority_path=tmp_path / "authority.json",
        )
