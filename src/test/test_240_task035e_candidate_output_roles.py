from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.task035e_candidate_output import (
    CandidateOutputError,
    adapt_candidate_output,
    main,
)
from src.test.test_232_task035e_candidate_output import (
    _rewrite_record,
    _write_candidate_run,
)


@pytest.mark.parametrize(
    ("cli_role", "authority_role"),
    (
        ("p-shadow", "blind_p_shadow_solve"),
        ("h-shadow", "blind_h_shadow_solve"),
    ),
)
def test_shadow_output_role_must_be_explicit_and_authority_bound(
    tmp_path: Path,
    cli_role: str,
    authority_role: str,
) -> None:
    record = _write_candidate_run(tmp_path)

    def set_role(payload: dict[str, object]) -> None:
        payload["task035e_blind_candidate"]["output_role"] = authority_role

    record = _rewrite_record(record, set_role)
    with pytest.raises(CandidateOutputError, match="authority is invalid"):
        adapt_candidate_output(record)

    adapted = adapt_candidate_output(record, output_role=cli_role)
    assert adapted.output_role == authority_role
    assert adapted.trial_id == "path-a-trial"
    assert adapted.cycle_index == 3


def test_candidate_output_cli_defaults_current_and_accepts_shadow_role(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    current = _write_candidate_run(tmp_path / "current")
    current_output = tmp_path / "current.json"
    assert main(
        [
            "--record",
            str(current.path),
            "--record-sha256",
            current.sha256,
            "--output",
            str(current_output),
        ]
    ) == 0
    current_receipt = json.loads(capsys.readouterr().out)
    assert current_receipt["output_role"] == "blind_current_solve"

    shadow = _write_candidate_run(tmp_path / "shadow")

    def set_role(payload: dict[str, object]) -> None:
        payload["task035e_blind_candidate"]["output_role"] = (
            "blind_p_shadow_solve"
        )

    shadow = _rewrite_record(shadow, set_role)
    shadow_output = tmp_path / "shadow.json"
    assert main(
        [
            "--record",
            str(shadow.path),
            "--record-sha256",
            shadow.sha256,
            "--output",
            str(shadow_output),
            "--output-role",
            "p-shadow",
        ]
    ) == 0
    shadow_receipt = json.loads(capsys.readouterr().out)
    assert shadow_receipt["output_role"] == "blind_p_shadow_solve"


def test_candidate_output_rejects_role_relabeling(
    tmp_path: Path,
) -> None:
    record = _write_candidate_run(tmp_path)
    with pytest.raises(CandidateOutputError, match="authority is invalid"):
        adapt_candidate_output(record, output_role="h-shadow")
    with pytest.raises(CandidateOutputError, match="output role"):
        adapt_candidate_output(record, output_role="reference")
