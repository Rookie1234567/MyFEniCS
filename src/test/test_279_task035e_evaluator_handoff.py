from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest

from benchmarks.task035e_evaluator_handoff import (
    EVALUATOR_HANDOFF_SCHEMA,
    EvaluatorHandoffError,
    run_evaluator_handoff,
)
from src.adaptivity.hidden_auditor import HiddenAuditContractError
from src.test.test_225_task035e_hidden_auditor import (
    _candidate_and_receipt,
)


def _private_json(path: Path, payload: object) -> Path:
    path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def test_evaluator_handoff_runs_only_after_frozen_files_exist(
    tmp_path: Path,
) -> None:
    candidate, receipt = _candidate_and_receipt()
    receipt_path = _private_json(tmp_path / "freeze.json", receipt)
    candidate_path = _private_json(tmp_path / "candidate.json", candidate)
    output_path = tmp_path / "handoff.json"

    handoff = run_evaluator_handoff(
        freeze_receipt_path=receipt_path,
        candidate_bundle_path=candidate_path,
        output_path=output_path,
    )

    assert handoff["schema_version"] == EVALUATOR_HANDOFF_SCHEMA
    assert handoff["status"] == "preflight_pass"
    assert handoff["pass"] is True
    assert handoff["sealed_reference_opened"] is False
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600
    assert json.loads(output_path.read_text(encoding="utf-8")) == handoff
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        run_evaluator_handoff(
            freeze_receipt_path=receipt_path,
            candidate_bundle_path=candidate_path,
            output_path=output_path,
        )


def test_evaluator_handoff_rejects_tamper_and_open_permissions(
    tmp_path: Path,
) -> None:
    candidate, receipt = _candidate_and_receipt()
    receipt_path = _private_json(tmp_path / "freeze.json", receipt)
    candidate["identity"]["cycle_index"] += 1
    candidate_path = _private_json(tmp_path / "candidate.json", candidate)
    with pytest.raises(HiddenAuditContractError):
        run_evaluator_handoff(
            freeze_receipt_path=receipt_path,
            candidate_bundle_path=candidate_path,
            output_path=tmp_path / "tampered-handoff.json",
        )

    candidate, _receipt = _candidate_and_receipt()
    candidate_path.write_text(
        json.dumps(candidate, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    candidate_path.chmod(0o644)
    with pytest.raises(EvaluatorHandoffError, match="mode-0600"):
        run_evaluator_handoff(
            freeze_receipt_path=receipt_path,
            candidate_bundle_path=candidate_path,
            output_path=tmp_path / "open-handoff.json",
        )
