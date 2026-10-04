"""Explicit opt-in W1 identities; no FE imports, default paths or AUTO builder."""

import hashlib
import json
import math
from pathlib import Path
import tomllib

MATH_COMMIT = "c354afa449fb80cfb5012e7d2ff66a3e3e64e088"
MANIFEST_SHA = "52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d"
MANIFEST_BYTES = 36244923
KEY_SHA = "03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec"
PHYSICAL_SHA = "a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f"
INVENTORY_SHA = "39b457c3f0b9d8db5f85a8f1482734513d48670c017d4c8060cae734bdcd0c12"
LEDGERS = {
    "8dd917dbb7252bfb0abca81213f3d3cba93cd1f35010a55cbf8c27e2f32ecd4a": "original_v5",
    "92c6a0f458ffa2d84911744cd8d6138f93414e8b850dfae205093e9618e45ae2": "repaired_v5",
}
CHECKPOINT_SHA = "a475bba1618abd74981622a66e127b2fd88b43f52a2339f5087115ed9b1a82f8"
ROOT = Path(__file__).resolve().parents[2]
FIELDS = {
    "w1_receiver_schema",
    "component",
    "stage",
    "math_commit",
    "quadrature_degree",
    "manifest_path",
    "ledger_path",
    "output_root",
    "window_path",
    "source_manifest_path",
    "coordinate_convention",
    "ledger_translation_nm",
    "checkpoint_path",
}
STAGES = {
    "control",
    "boundary",
    "boundary_check",
    "p4_top",
    "p4_bottom",
    "p6_top",
    "p6_bottom",
    "p4_top_check",
    "p4_bottom_check",
    "p6_top_check",
    "p6_bottom_check",
}
OPTIONAL_FIELDS = {"A_qualification_path", "prerequisite_paths"}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def load_w1(path):
    path = Path(path)
    raw = path.read_bytes()
    if not raw.startswith(b"w1_receiver_schema = "):
        return None
    spec = tomllib.loads(raw.decode())
    if not FIELDS <= set(spec) or set(spec) - FIELDS - OPTIONAL_FIELDS:
        raise ValueError("W1_EXPLICIT_FIELDS_REQUIRED")
    if (
        spec["w1_receiver_schema"] != 1
        or spec["component"] != "original_size_boundary_w1"
        or spec["stage"] not in STAGES
        or spec["math_commit"] != MATH_COMMIT
        or type(spec["quadrature_degree"]) is not int
        or spec["quadrature_degree"] != 60
        or spec["coordinate_convention"] != "main_centered_nm"
        or spec["ledger_translation_nm"] != [25.0, 12.5, 0.0]
    ):
        raise ValueError("W1_FIXED_MATH_Q60_COORDINATE_CONTRACT")
    for field in (
        "manifest_path",
        "ledger_path",
        "window_path",
        "source_manifest_path",
    ):
        if not isinstance(spec[field], str) or not spec[field]:
            raise ValueError("W1_EXPLICIT_PATH_REQUIRED")
        spec[field] = str((ROOT / spec[field]).resolve())
    output = (ROOT / spec["output_root"]).resolve()
    if not output.is_relative_to(ROOT / "benchmarks/artifacts/task42extra/w1_receiver"):
        raise ValueError("W1_OUTPUT_ESCAPES_OWN_ARTIFACTS")
    spec["output_root"] = str(output)
    if "A_qualification_path" in spec:
        spec["A_qualification_path"] = str(
            (ROOT / spec["A_qualification_path"]).resolve()
        )
    if "prerequisite_paths" in spec:
        if (
            not isinstance(spec["prerequisite_paths"], dict)
            or set(spec["prerequisite_paths"]) - STAGES
        ):
            raise ValueError("W1_EXPLICIT_PREREQUISITE_STAGES")
        spec["prerequisite_paths"] = {
            k: str((ROOT / v).resolve()) for k, v in spec["prerequisite_paths"].items()
        }
        if any(
            not Path(v).is_relative_to(
                ROOT / "benchmarks/artifacts/task42extra/w1_receiver"
            )
            for v in spec["prerequisite_paths"].values()
        ):
            raise ValueError("W1_PREREQUISITE_ESCAPES_OWN_ARTIFACTS")
    if spec["checkpoint_path"]:
        spec["checkpoint_path"] = str((ROOT / spec["checkpoint_path"]).resolve())
    spec.update(path=str(path.resolve()), input_sha256=hashlib.sha256(raw).hexdigest())
    return spec


def validate_originals(spec):
    """One binding shared by worker/checker, including the selected ledger."""
    missing = [
        spec[k] for k in ("manifest_path", "ledger_path") if not Path(spec[k]).is_file()
    ]
    if missing:
        return {
            "status": "NOT_RUN_INPUT_UNAVAILABLE",
            "missing": missing,
            "received": False,
        }
    mpath, lpath = Path(spec["manifest_path"]), Path(spec["ledger_path"])
    if (
        mpath.stat().st_size != MANIFEST_BYTES
        or digest(mpath) != MANIFEST_SHA
        or digest(lpath) not in LEDGERS
    ):
        raise ValueError("W1_ORIGINAL_BYTES_HASH_OR_LEDGER_MISMATCH")
    document, ledger = json.loads(mpath.read_text()), json.loads(lpath.read_text())
    validate_inventory(document, ledger)
    selected = digest(lpath)
    return {
        "status": "INPUT_IDENTITY_PASS",
        "received": True,
        "manifest_path": str(mpath),
        "manifest_bytes": mpath.stat().st_size,
        "manifest_sha256": MANIFEST_SHA,
        "ledger_path": str(lpath),
        "ledger_bytes": lpath.stat().st_size,
        "ledger_sha256": selected,
        "ledger_variant": LEDGERS[selected],
        "ordered_key_sha256": KEY_SHA,
        "physical_identity_sha256": PHYSICAL_SHA,
        "inventory_identity_sha256": INVENTORY_SHA,
        "reopened": True,
    }


def validate_inventory(
    document,
    ledger,
    *,
    count=32060,
    key_sha=KEY_SHA,
    physical_sha=PHYSICAL_SHA,
    inventory_sha=INVENTORY_SHA,
):
    """Fixture-capable validator; the production caller never overrides constants."""
    rows = document.get("modes")
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError("W1_FULL_MODE_COVERAGE")
    keys = [[r["side"], r["m"], r["n"], r["polarization"]] for r in rows]
    if (
        len({tuple(k) for k in keys}) != count
        or hashlib.sha256(json.dumps(keys, separators=(",", ":")).encode()).hexdigest()
        != key_sha
    ):
        raise ValueError("W1_ORDERED_KEY_IDENTITY")
    if (
        ledger.get("target_mode_physical_identity_sha256") != physical_sha
        or ledger.get("original_size_ordered_mode_inventory_identity_sha256")
        != inventory_sha
    ):
        raise ValueError("W1_PHYSICAL_LEDGER_IDENTITY")
    for field, options in (("side", ("top", "bottom")), ("polarization", ("s", "p"))):
        if any(
            sum(r[field] == option for r in rows) != count // 2 for option in options
        ):
            raise ValueError("W1_SIDE_POLARIZATION_COVERAGE")
    for i, row in enumerate(rows):
        if (
            type(row["m"]) is not int
            or type(row["n"]) is not int
            or type(row.get("mode_index")) is not int
            or row["mode_index"] < 0
            or not math.isfinite(row["projection_denominator"])
            or row["projection_denominator"] <= 0
        ):
            raise ValueError("W1_MODE_SCALAR_ORDER_H")
        for field in ("k_vector", "e_vector", "traction_vector"):
            if len(row[field]) != 3:
                raise ValueError("W1_COMPLEX_LAYOUT")
            for z in row[field]:
                if (
                    not isinstance(z, dict)
                    or set(z) != {"real", "imag"}
                    or any(
                        type(z[v]) not in (int, float) or not math.isfinite(z[v])
                        for v in ("real", "imag")
                    )
                ):
                    raise ValueError("W1_COMPLEX_LAYOUT")
    return rows


def require_same_binding(binding, spec, *, consumer):
    expected = {
        k: spec[k]
        for k in (
            "manifest_path",
            "ledger_path",
            "math_commit",
            "quadrature_degree",
            "output_root",
            "input_sha256",
            "coordinate_convention",
            "ledger_translation_nm",
        )
    }
    if (
        binding.get("contract") != expected
        or binding.get("receiver_source_sha") is None
    ):
        raise ValueError("W1_CONSUMER_BINDING_MISMATCH:" + consumer)
    actual = validate_originals(spec)
    if actual != binding.get("original_inputs") or not actual["received"]:
        raise ValueError("W1_CONSUMER_ORIGINAL_CHANGED:" + consumer)
    return actual
