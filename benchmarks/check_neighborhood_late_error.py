"""Independent complete V44 heldout inventory; old 24-state checker unchanged."""


def require_inventory(rows):
    expected = {
        (i, r) for i in range(8) for r in ("R0", "NN-R", "NN-E", "RL-E", "CL-E")
    }
    actual = [(r["sample"], r["route"]) for r in rows if r["split"] == "heldout"]
    if len(rows) != 40 or len(actual) != 40 or set(actual) != expected:
        raise ValueError("exact 40-state unique sample/route/split inventory")
    return True


def require_model(actual, expected):
    if actual != expected:
        raise ValueError("candidate model differs from frozen validation selection")
