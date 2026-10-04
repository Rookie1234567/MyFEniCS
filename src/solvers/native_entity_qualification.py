"""Explicit complete-evidence qualification, never a missing-field default."""

REQUIRED = (
    "BRIDGE1",
    "BRIDGE2",
    "BRIDGE4",
    "TOPOLOGY",
    "ORIENTATION",
    "ROUTING",
    "ACTIONS",
)


def _positive(record):
    return (
        isinstance(record, dict)
        and record.get("passed") is True
        and isinstance(record.get("checks"), list)
        and bool(record["checks"])
        and all(
            isinstance(c, dict) and c.get("passed") is True for c in record["checks"]
        )
    )


def complete_native_checks(checks):
    if not isinstance(checks, dict) or any(k not in checks for k in REQUIRED):
        return False
    for n in (1, 2, 4):
        r = checks["BRIDGE" + str(n)]
        if not isinstance(r, dict) or r.get("MPI_size") != n:
            return False
        if not r.get("fixtures") or not all(_positive(f) for f in r["fixtures"]):
            return False
        if not _positive(r.get("directions")):
            return False
    if not all(_positive(checks[k]) for k in ("TOPOLOGY", "ORIENTATION", "ROUTING")):
        return False
    if checks["ROUTING"].get("rows") != 378432:
        return False
    actions = checks["ACTIONS"]
    return (
        isinstance(actions, list)
        and len(actions) == 4
        and sorted(a.get("kind", "") for a in actions)
        == ["adjoint", "amplitudes", "forward", "modal"]
        and all(a.get("passed") is True for a in actions)
    )
