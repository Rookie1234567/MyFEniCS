"""FD admission and frozen raw paths only; no FE or numerical solver."""

import hashlib
import json
import subprocess
import sys

import pytest

from src.runners.saved_component_checker import canonical_saved_path, descriptor_budget


def test_descriptor_budget_does_not_raise_hard(monkeypatch):
    import src.runners.saved_component_checker as module
    actions = []
    monkeypatch.setattr(module.resource, "getrlimit", lambda _: (1024, 1048576))
    monkeypatch.setattr(module.resource, "setrlimit", lambda *args: actions.append(args))
    result = descriptor_budget(1619)
    assert result["soft_after"] == 2048 and result["hard_unchanged"] == 1048576
    assert actions == [(module.resource.RLIMIT_NOFILE, (2048, 1048576))]
    monkeypatch.setattr(module.resource, "getrlimit", lambda _: (512, 1024))
    with pytest.raises(RuntimeError, match="FD_CAPACITY_UNAVAILABLE"):
        descriptor_budget(1619)
    assert len(actions) == 1


def test_original_raw_paths_reject_escape_and_symlink(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    file = raw / (hashlib.sha256(b"row").hexdigest() + ".npy")
    file.write_bytes(b"fixture")
    reference = {"name": "row", "callback_reference": str(file)}
    assert canonical_saved_path(tmp_path, reference) == file
    reference["callback_reference"] = str(tmp_path / "outside")
    with pytest.raises(ValueError):
        canonical_saved_path(tmp_path, reference)
    file.unlink()
    file.symlink_to(tmp_path / "outside")
    reference["callback_reference"] = str(file)
    with pytest.raises(ValueError):
        canonical_saved_path(tmp_path, reference)


def test_actual_small_emfile_recovery_changes_only_child_limit(tmp_path):
    code = r'''
import gc, json, resource, sys
from pathlib import Path
import numpy as np
from src.runners.saved_component_checker import descriptor_budget
raw=Path(sys.argv[1]); paths=[]
for i in range(96):
 p=raw/(str(i)+'.npy');np.save(p,np.asarray([i],dtype=np.int64));paths.append(p)
soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE,(48,hard))
held=[];failed=False
try:
 for p in paths: held.append(np.load(p,mmap_mode='r',allow_pickle=False))
except OSError as error:
 assert error.errno==24;failed=True
assert failed
for value in held:value._mmap.close()
held.clear();gc.collect()
budget=descriptor_budget(96)
held=[np.load(p,mmap_mode='r',allow_pickle=False) for p in paths]
assert [int(a[0]) for a in held]==list(range(96))
assert resource.getrlimit(resource.RLIMIT_NOFILE)[1]==hard
print(json.dumps({'reproduced_EMFILE':failed,'mapped_after':len(held),'budget':budget}))
for value in held:value._mmap.close()
'''
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["reproduced_EMFILE"] and data["mapped_after"] == 96
    assert data["budget"]["soft_before"] == 48
