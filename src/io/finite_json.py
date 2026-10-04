"""Strict finite JSON and durable publication for opt-in scientific evidence."""

import json
import math
import os
from pathlib import Path


def finite_value(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("NONFINITE_JSON_SCALAR")
        return value
    if isinstance(value, dict):
        if any(type(k) is not str for k in value):
            raise TypeError("JSON_OBJECT_KEYS_MUST_BE_STRINGS")
        return {k: finite_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_value(v) for v in value]
    # No top-level NumPy/Torch import in FE bootstrap. Only scalar .item()
    # conversion is allowed; complex numbers/large arrays stay in NPZ.
    if type(value).__module__.startswith("numpy") and getattr(value, "ndim", 0) == 0:
        return finite_value(value.item())
    raise TypeError("UNSUPPORTED_JSON_VALUE:" + type(value).__name__)


def atomic_json(path, value):
    path = Path(path)
    encoded = (
        json.dumps(finite_value(value), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as out:
        out.write(encoded)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    reopened = json.loads(
        path.read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))
    )
    if reopened != finite_value(value):
        raise ValueError("JSON_REOPEN_MISMATCH")
