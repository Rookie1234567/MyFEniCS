"""Finite scientific JSON snapshots; arrays require explicit small conversion."""
from collections.abc import Mapping
import json
import math
import os
from pathlib import Path
import sys
import tempfile


def snapshot(value):
    np=sys.modules.get("numpy")
    if np is not None:
        if isinstance(value,np.ndarray):raise TypeError("ndarray requires explicit shape-bounded conversion")
        if isinstance(value,np.bool_):value=bool(value)
        elif isinstance(value,np.integer):value=int(value)
        elif isinstance(value,np.floating):value=float(value)
        elif isinstance(value,np.complexfloating):value=complex(value)
    if value is None or type(value) in (str,bool,int):return value
    if type(value) is float:
        if not math.isfinite(value):raise ValueError("nonfinite JSON scalar")
        return value
    if type(value) is complex:
        return {"real":snapshot(float(value.real)),"imag":snapshot(float(value.imag))}
    if isinstance(value,Mapping):
        if any(type(k) is not str for k in value):raise TypeError("JSON keys must be exact strings")
        return {k:snapshot(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [snapshot(v) for v in value]
    raise TypeError(f"unsupported JSON type: {type(value).__module__}.{type(value).__name__}")


def atomic_json(path,value):
    payload=(json.dumps(snapshot(value),sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+"\n").encode()
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix="."+path.name+".",delete=False) as f:
            temporary=Path(f.name);f.write(payload);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path);temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
