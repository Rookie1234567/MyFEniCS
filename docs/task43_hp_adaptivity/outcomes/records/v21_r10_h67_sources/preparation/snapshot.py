"""Immutable launch identity for one V21 slot; stdlib and file bytes only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

repo = Path('/home/fenics/Projects/NN-Lab-V2')
prefix = repo / 'benchmarks/artifacts/task43/v21_r10_h67'
root, stage, contract = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

c = json.loads(contract.read_text())
assert c['authorization_review'] == '0dd5555f8795a68c7c9b1dc58387337d98fd76a5'
release_path = prefix / 'preparation' / f'{stage}_root_release.json'
release = json.loads(release_path.read_text())
assert release['decision'] == 'ALLOW_ONE_FIXED_SLOT' and release['stage'] == stage
assert release['actual_head'] == head and release['contract_sha256'] == sha(contract)
assert release['authorization_review'] == c['authorization_review']
assert Path(release['root']) == root
shutil.copyfile(release_path, root / 'root_release.json')
snapshot = root / 'snapshots'
snapshot.mkdir()
refs = {}
paths = set(c['source_paths']) | {str(contract.relative_to(repo)), 'benchmarks/subreaper_watchdog.py', 'scripts/activate_task40_phi90_pord64.sh'}
for rel in sorted(paths):
    path = repo / rel
    assert path.is_file() and not path.is_symlink(), rel
    assert path.read_bytes() == subprocess.check_output(['git', 'show', head + ':' + rel]), rel
    out = snapshot / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, out)
    refs[rel] = {'sha256': sha(path), 'bytes': path.stat().st_size}
launch_refs = {}
for name in ('stage_launch.sh', 'snapshot.py'):
    path = prefix / 'launch' / name
    archived = repo / 'docs/task43_hp_adaptivity/outcomes/records/v21_r10_h67_sources/preparation' / name
    assert not path.is_symlink() and path.read_bytes() == archived.read_bytes()
    assert archived.read_bytes() == subprocess.check_output(['git', 'show', head + ':' + str(archived.relative_to(repo))])
    out = snapshot / 'launch' / name
    out.parent.mkdir(exist_ok=True)
    shutil.copyfile(path, out)
    launch_refs[str(path)] = {'sha256': sha(path), 'bytes': path.stat().st_size}
inputs = {}
for role, binding in c['inputs'].items():
    path = repo / binding['path']
    assert path.is_file() and not path.is_symlink(), role
    actual = sha(path)
    assert actual == binding['sha256'], role
    inputs[role] = {'path': str(path.resolve()), 'sha256': actual, 'bytes': path.stat().st_size}
names = ['_MYFENICS_NATIVE_QUALIFIED_ACTIVATION', 'VIRTUAL_ENV', 'PATH', 'PYTHONPATH', 'LD_LIBRARY_PATH', 'PHYSICAL_NATIVE_CAPACITY', 'PHYSICAL_NATIVE_NODE_CAP_BYTES', 'TASK43_V21_RUN_ROOT', 'TASK43_V21_STAGE', 'TASK43_V11_ATTEMPT_ROOT', 'TASK43_V11_TRACE_PREFIX', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'BLIS_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS']
manifest = {'schema': 'task43.v21.run-manifest.v1', 'stage': stage, 'actual_head': head, 'authorization_review': c['authorization_review'], 'sources': refs, 'launch_files': launch_refs, 'inputs': inputs, 'contract': {'path': str(contract), 'sha256': sha(contract)}, 'worker_argv': sys.argv[5:], 'worker_wrapper': sys.argv[4], 'environment': {key: os.environ.get(key) for key in names}, 'worker_overrides': {'HWLOC_COMPONENTS': '-x86', 'OMPI_MCA_pml': 'ob1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}}
with (root / 'run_manifest.json').open('x') as stream:
    json.dump(manifest, stream, indent=2)
    stream.write('\n')
