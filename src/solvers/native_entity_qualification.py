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


def require_direction_coverage(required, witnesses):
    """A reused proof must explicitly cover every encountered native code."""
    needed = set(map(int, required))
    covered = set()
    for witness in witnesses:
        if not witness.get("source") or witness.get("passed") is not True:
            raise ValueError("missing positive direction proof/source")
        codes = witness.get("codes")
        if codes is None or not len(codes):
            raise ValueError("empty direction proof inventory")
        covered.update(map(int, codes))
    if not needed or not needed <= covered:
        raise ValueError("missing encountered direction proof")
    return {
        "passed": True,
        "required_codes": sorted(needed),
        "covered_codes": sorted(covered),
        "sources": [w["source"] for w in witnesses],
    }


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
