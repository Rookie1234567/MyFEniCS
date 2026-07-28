from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

import pytest

from benchmarks.task035e_transition_producer import (
    TransitionProducerError,
    main,
    write_transition_bundle,
)
from src.adaptivity.task035e_hp_transition import (
    canonical_hp_cell_target_id,
)
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.adaptivity.task035e_plan_transition import (
    canonical_solver_content_sha256,
    rebuild_hp_transition_state_from_solver_plan,
)
from src.common.config_3d import target_stage4_config


_SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_plan_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _write_private_json(path: Path, payload: object) -> str:
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return _file_sha256(path)


@pytest.fixture(scope="module")
def initial_payload() -> dict[str, object]:
    result = build_task035e_initial_space_plan(
        target_stage4_config(degree=6, h_nm=20.0),
        path_id="A",
        source_sha=_SOURCE_SHA,
        comm_size=8,
    )
    return result.plan_payload()


def _current(
    tmp_path: Path,
    initial_payload: dict[str, object],
) -> tuple[Path, str, object]:
    path = tmp_path / "current.json"
    digest = _write_private_json(path, initial_payload)
    state = rebuild_hp_transition_state_from_solver_plan(
        target_stage4_config(degree=6, h_nm=20.0),
        current_plan=initial_payload,
        comm_size=8,
    )
    return path, digest, state


def _p4_target_ids(state: object, count: int = 1) -> tuple[str, ...]:
    rows = [
        (key, canonical_hp_cell_target_id(key))
        for key, degree in state.cell_degree_by_key.items()
        if degree == 4
    ]
    return tuple(value for _key, value in sorted(rows)[:count])


def test_producer_publishes_deterministic_replayable_private_bundle(
    tmp_path: Path,
    initial_payload: dict[str, object],
) -> None:
    current, current_sha, state = _current(tmp_path, initial_payload)
    targets = _p4_target_ids(state)
    first = write_transition_bundle(
        current_plan_path=current,
        current_plan_file_sha256=current_sha,
        source_sha=_SOURCE_SHA,
        action_kind="p-up",
        canonical_target_ids=targets,
        action_path=tmp_path / "action-one.json",
        next_plan_path=tmp_path / "plan-one.json",
    )
    second = write_transition_bundle(
        current_plan_path=current,
        current_plan_file_sha256=current_sha,
        source_sha=_SOURCE_SHA,
        action_kind="p-up",
        canonical_target_ids=targets,
        action_path=tmp_path / "action-two.json",
        next_plan_path=tmp_path / "plan-two.json",
    )

    assert first.action_id == second.action_id
    assert first.action_sha256 == second.action_sha256
    assert first.action_file_sha256 == second.action_file_sha256
    assert first.plan_file_sha256 == second.plan_file_sha256
    assert first.plan_content_sha256 == second.plan_content_sha256
    assert first.next_state_sha256 == second.next_state_sha256
    assert first.action_path.read_bytes() == second.action_path.read_bytes()
    assert first.plan_path.read_bytes() == second.plan_path.read_bytes()
    assert stat.S_IMODE(first.action_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(first.plan_path.stat().st_mode) == 0o600

    action = json.loads(first.action_path.read_text(encoding="utf-8"))
    plan = json.loads(first.plan_path.read_text(encoding="utf-8"))
    assert action["canonical_target_ids"] == list(targets)
    assert action["action_sha256"] == first.action_sha256
    assert plan["provenance"]["transition_action_sha256"] == (
        first.action_sha256
    )
    assert plan["provenance"]["goal_values_embedded"] is False
    assert plan["provenance"]["dwr_values_embedded"] is False
    assert plan["provenance"]["evaluator_inputs_consumed"] is False
    assert _file_sha256(first.action_path) == first.action_file_sha256
    assert _file_sha256(first.plan_path) == first.plan_file_sha256
    replayed = rebuild_hp_transition_state_from_solver_plan(
        target_stage4_config(degree=6, h_nm=20.0),
        current_plan=plan,
        comm_size=8,
    )
    assert replayed.state_sha256 == first.next_state_sha256
    assert replayed.stage_action_sha256s == (first.action_sha256,)


def test_producer_replays_one_real_h_refinement(
    tmp_path: Path,
    initial_payload: dict[str, object],
) -> None:
    current, current_sha, state = _current(tmp_path, initial_payload)
    target = next(
        canonical_hp_cell_target_id(cell.key)
        for cell in state.forest.leaves
        if cell.key.level == 1
    )
    receipt = write_transition_bundle(
        current_plan_path=current,
        current_plan_file_sha256=current_sha,
        source_sha=_SOURCE_SHA,
        action_kind="h-refine",
        canonical_target_ids=(target,),
        action_path=tmp_path / "h-action.json",
        next_plan_path=tmp_path / "h-plan.json",
    )

    action = json.loads(receipt.action_path.read_text(encoding="utf-8"))
    plan = json.loads(receipt.plan_path.read_text(encoding="utf-8"))
    assert action["kind"] == "h-refine"
    assert action["maximum_level"] == 2
    assert action["degree_deltas"] == []
    assert plan["refinement_stage_count"] == 2
    assert plan["multilevel_audit"]["actual_maximum_level"] == 2
    assert plan["multilevel_audit"]["true_multilevel"] is True


def test_producer_p_keep_needs_no_target_and_preserves_solver_content(
    tmp_path: Path,
    initial_payload: dict[str, object],
) -> None:
    current, current_sha, state = _current(tmp_path, initial_payload)
    receipt = write_transition_bundle(
        current_plan_path=current,
        current_plan_file_sha256=current_sha,
        source_sha=_SOURCE_SHA,
        action_kind="p-keep",
        canonical_target_ids=(),
        action_path=tmp_path / "keep-action.json",
        next_plan_path=tmp_path / "keep-plan.json",
    )

    action = json.loads(receipt.action_path.read_text(encoding="utf-8"))
    plan = json.loads(receipt.plan_path.read_text(encoding="utf-8"))
    assert receipt.action_kind == "p-keep"
    assert receipt.canonical_target_ids == ()
    assert action["canonical_target_ids"] == []
    assert action["degree_deltas"] == []
    assert action["requested_split_keys"] == []
    assert action["maximum_level"] is None
    assert canonical_solver_content_sha256(
        plan
    ) == canonical_solver_content_sha256(initial_payload)
    assert receipt.plan_content_sha256 != _canonical_plan_sha256(
        initial_payload
    )
    assert receipt.next_state_sha256 != state.state_sha256
    replayed = rebuild_hp_transition_state_from_solver_plan(
        target_stage4_config(degree=6, h_nm=20.0),
        current_plan=plan,
        comm_size=8,
    )
    assert replayed.state_sha256 == receipt.next_state_sha256
    assert replayed.stage_action_sha256s == (receipt.action_sha256,)


def test_producer_refuses_overwrite_and_preserves_existing_bytes(
    tmp_path: Path,
    initial_payload: dict[str, object],
) -> None:
    current, current_sha, state = _current(tmp_path, initial_payload)
    targets = _p4_target_ids(state)
    action = tmp_path / "immutable-action.json"
    plan = tmp_path / "immutable-plan.json"
    write_transition_bundle(
        current_plan_path=current,
        current_plan_file_sha256=current_sha,
        source_sha=_SOURCE_SHA,
        action_kind="p-up",
        canonical_target_ids=targets,
        action_path=action,
        next_plan_path=plan,
    )
    before = (action.read_bytes(), plan.read_bytes())

    with pytest.raises(FileExistsError, match="overwrite"):
        write_transition_bundle(
            current_plan_path=current,
            current_plan_file_sha256=current_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            canonical_target_ids=targets,
            action_path=action,
            next_plan_path=plan,
        )
    assert (action.read_bytes(), plan.read_bytes()) == before


def test_producer_refuses_broken_symlink_output(
    tmp_path: Path,
    initial_payload: dict[str, object],
) -> None:
    current, current_sha, state = _current(tmp_path, initial_payload)
    targets = _p4_target_ids(state)
    action = tmp_path / "symlink-action.json"
    action.symlink_to(tmp_path / "missing-action-target.json")

    with pytest.raises(FileExistsError, match="overwrite"):
        write_transition_bundle(
            current_plan_path=current,
            current_plan_file_sha256=current_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            canonical_target_ids=targets,
            action_path=action,
            next_plan_path=tmp_path / "unused-plan.json",
        )
    assert action.is_symlink()
    assert not (tmp_path / "missing-action-target.json").exists()


@pytest.mark.parametrize(
    ("mutation", "match"),
    (
        ("wrong-current-hash", "file SHA-256 mismatch"),
        ("wrong-source", "source SHA"),
        ("noncanonical-targets", "canonical order"),
        ("private-mode", "mode 0600"),
    ),
)
def test_producer_rejects_unbound_inputs(
    tmp_path: Path,
    initial_payload: dict[str, object],
    mutation: str,
    match: str,
) -> None:
    current, current_sha, state = _current(tmp_path, initial_payload)
    targets = _p4_target_ids(state, count=2)
    source = _SOURCE_SHA
    if mutation == "wrong-current-hash":
        current_sha = "0" * 64
    elif mutation == "wrong-source":
        source = "a" * 40
    elif mutation == "noncanonical-targets":
        targets = tuple(reversed(targets))
    elif mutation == "private-mode":
        current.chmod(0o644)

    with pytest.raises(TransitionProducerError, match=match):
        write_transition_bundle(
            current_plan_path=current,
            current_plan_file_sha256=current_sha,
            source_sha=source,
            action_kind="p-up",
            canonical_target_ids=targets,
            action_path=tmp_path / "rejected-action.json",
            next_plan_path=tmp_path / "rejected-plan.json",
        )
    assert not (tmp_path / "rejected-action.json").exists()
    assert not (tmp_path / "rejected-plan.json").exists()


def test_producer_rejects_reference_or_evaluator_payload(
    tmp_path: Path,
    initial_payload: dict[str, object],
) -> None:
    payload = json.loads(json.dumps(initial_payload))
    provenance = payload["provenance"]
    provenance["hidden_reference_values"] = {"R": 0.5}
    unhashed = dict(provenance)
    unhashed.pop("provenance_sha256")
    provenance["provenance_sha256"] = hashlib.sha256(
        json.dumps(
            unhashed,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    current = tmp_path / "leaking-current.json"
    current_sha = _write_private_json(current, payload)

    with pytest.raises(
        TransitionProducerError,
        match="unknown or missing data",
    ):
        write_transition_bundle(
            current_plan_path=current,
            current_plan_file_sha256=current_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            canonical_target_ids=("cell:r0:l0:i0:j0:k0",),
            action_path=tmp_path / "leak-action.json",
            next_plan_path=tmp_path / "leak-plan.json",
        )


def test_producer_rejects_hidden_data_in_known_initial_field(
    tmp_path: Path,
    initial_payload: dict[str, object],
) -> None:
    payload = json.loads(json.dumps(initial_payload))
    provenance = payload["provenance"]
    provenance["input_classes"] = [
        *provenance["input_classes"],
        "hidden_reference_values",
    ]
    unhashed = dict(provenance)
    unhashed.pop("provenance_sha256")
    provenance["provenance_sha256"] = hashlib.sha256(
        json.dumps(
            unhashed,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    current = tmp_path / "covert-current.json"
    current_sha = _write_private_json(current, payload)

    with pytest.raises(
        TransitionProducerError,
        match="deterministic authority",
    ):
        write_transition_bundle(
            current_plan_path=current,
            current_plan_file_sha256=current_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            canonical_target_ids=("cell:r0:l0:i0:j0:k0",),
            action_path=tmp_path / "covert-action.json",
            next_plan_path=tmp_path / "covert-plan.json",
        )


def test_producer_enforces_first_two_cycle_no_p_down(
    tmp_path: Path,
    initial_payload: dict[str, object],
) -> None:
    current, current_sha, state = _current(tmp_path, initial_payload)
    p5_target = next(
        canonical_hp_cell_target_id(key)
        for key, degree in state.cell_degree_by_key.items()
        if degree == 5
    )
    with pytest.raises(TransitionProducerError, match="first two"):
        write_transition_bundle(
            current_plan_path=current,
            current_plan_file_sha256=current_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-down",
            canonical_target_ids=(p5_target,),
            action_path=tmp_path / "down-action.json",
            next_plan_path=tmp_path / "down-plan.json",
        )


def test_cli_reports_closed_receipt(
    tmp_path: Path,
    initial_payload: dict[str, object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    current, current_sha, state = _current(tmp_path, initial_payload)
    target = _p4_target_ids(state)[0]
    action = tmp_path / "cli-action.json"
    plan = tmp_path / "cli-plan.json"

    status = main(
        [
            "--current-plan",
            str(current),
            "--current-plan-sha256",
            current_sha,
            "--verified-clean-sha",
            _SOURCE_SHA,
            "--action-kind",
            "p-up",
            "--target-id",
            target,
            "--action",
            str(action),
            "--next-plan",
            str(plan),
        ]
    )

    assert status == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "completed"
    assert receipt["action_kind"] == "p-up"
    assert receipt["canonical_target_ids"] == [target]
    assert receipt["action_file_sha256"] == _file_sha256(action)
    assert receipt["next_plan_file_sha256"] == _file_sha256(plan)


def test_cli_p_keep_succeeds_without_target(
    tmp_path: Path,
    initial_payload: dict[str, object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    current, current_sha, _state = _current(tmp_path, initial_payload)
    action = tmp_path / "cli-keep-action.json"
    plan = tmp_path / "cli-keep-plan.json"

    status = main(
        [
            "--current-plan",
            str(current),
            "--current-plan-sha256",
            current_sha,
            "--verified-clean-sha",
            _SOURCE_SHA,
            "--action-kind",
            "p-keep",
            "--action",
            str(action),
            "--next-plan",
            str(plan),
        ]
    )

    assert status == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "completed"
    assert receipt["action_kind"] == "p-keep"
    assert receipt["canonical_target_ids"] == []


def test_cli_non_keep_fails_without_target(
    tmp_path: Path,
    initial_payload: dict[str, object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    current, current_sha, _state = _current(tmp_path, initial_payload)
    action = tmp_path / "cli-missing-target-action.json"
    plan = tmp_path / "cli-missing-target-plan.json"

    status = main(
        [
            "--current-plan",
            str(current),
            "--current-plan-sha256",
            current_sha,
            "--verified-clean-sha",
            _SOURCE_SHA,
            "--action-kind",
            "p-up",
            "--action",
            str(action),
            "--next-plan",
            str(plan),
        ]
    )

    assert status == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "failed"
    assert "at least one canonical target" in receipt["error"]
    assert not action.exists()
    assert not plan.exists()


def test_cli_fails_without_creating_outputs(
    tmp_path: Path,
    initial_payload: dict[str, object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    current, current_sha, state = _current(tmp_path, initial_payload)
    target = _p4_target_ids(state)[0]
    action = tmp_path / "failed-action.json"
    plan = tmp_path / "failed-plan.json"

    status = main(
        [
            "--current-plan",
            str(current),
            "--current-plan-sha256",
            "0" * 64,
            "--verified-clean-sha",
            _SOURCE_SHA,
            "--action-kind",
            "p-up",
            "--target-id",
            target,
            "--action",
            str(action),
            "--next-plan",
            str(plan),
        ]
    )

    assert status == 2
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
    assert not action.exists()
    assert not plan.exists()
