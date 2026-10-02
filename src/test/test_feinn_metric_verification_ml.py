"""Select actual committed states by predeclared time/work, never error."""

from copy import deepcopy

import pytest

from src.solvers.feinn_metric_verification import PILOTS, selections


def routes_fixture():
    result = {}
    for stage, final in zip(PILOTS, (4, 3)):
        rows = []
        audits = []
        for n in range(1, final + 1):
            checkpoint = dict(name=f"committed_{n}.pt", sha256=f"{stage}-{n}")
            rows.append(
                dict(
                    accepted_outer=75 + n,
                    committed_elapsed_seconds=100 * n,
                    checkpoint=checkpoint,
                    native_relative=1 / n,
                )
            )
            audits.append(dict(checkpoint=checkpoint, native_relative=1 / n))
        result[stage] = dict(
            result=dict(
                new_accepted_outer=final,
                inherited_accepted_outer=75,
                accepted_history=rows,
                audits=audits,
                fixed_time_boundaries={
                    "1800": dict(status="RETAINED", actual_seconds=1750),
                    "3600": dict(status="RETAINED", actual_seconds=3550),
                    "5400": dict(status="NOT_RUN"),
                },
            )
        )
    return result


def test_common_states_use_times_and_accepted_count_without_error_selection():
    routes = routes_fixture()
    selected = selections(routes)
    assert [(kind, target) for kind, target, _ in selected] == [
        ("TIME", 1800),
        ("TIME", 3600),
        ("WORK", 3),
    ]
    work = selected[-1][2]
    assert all(point["accepted_outer"] == 78 for point in work)
    assert all(point["actual_seconds"] == 300 for point in work)
    changed = deepcopy(routes)
    for route in changed.values():
        for row in route["result"]["accepted_history"]:
            row["native_relative"] = 1e-12 if row["accepted_outer"] == 76 else 1e10
    assert selections(changed) == selected


def test_unreached_time_and_missing_history_are_not_replayed():
    routes = routes_fixture()
    routes[PILOTS[1]]["result"]["fixed_time_boundaries"]["3600"]["status"] = "NOT_RUN"
    routes[PILOTS[0]]["result"]["accepted_history"] = []
    assert [(kind, target) for kind, target, _ in selections(routes)] == [
        ("TIME", 1800)
    ]
    assert selections({PILOTS[0]: routes[PILOTS[0]]}) == []


def test_work_state_requires_the_matching_persisted_audit():
    routes = routes_fixture()
    routes[PILOTS[0]]["result"]["audits"] = []
    with pytest.raises(ValueError, match="COMMON_WORK_PERSISTED_AUDIT_NOT_RETAINED"):
        selections(routes)
