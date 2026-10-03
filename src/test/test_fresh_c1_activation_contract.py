"""Production shell serialization with a fake interpreter; no MPI/FE imports."""
import hashlib
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("import_exit", [0,7])
def test_stdout_diagnostic_cannot_corrupt_hash_or_override_failed_import(tmp_path,import_exit):
    script=Path(__file__).parents[2]/"scripts/task40extra_cloud_recovery/activate_fresh_cloud_complex.sh"
    manifest=tmp_path/"manifest.json";manifest.write_text('{"synthetic_test_only":true}\n')
    expected=hashlib.sha256(manifest.read_bytes()).hexdigest()
    prefix=tmp_path/"prefix";(prefix/"bin").mkdir(parents=True)
    fake=prefix/"bin/python"
    fake.write_text('''#!/usr/bin/env bash
input="$(cat)"
if [[ "$input" == *"MPI.Get_library_version"* ]]; then
  printf '%s\\n' 'UCX fixture diagnostic on stdout'
  exit '''+str(import_exit)+'''
fi
if [[ "$input" == *"hashlib.sha256"* ]]; then
  printf '%s\\n' '''+expected+'''
  exit 0
fi
exit 91
''');fake.chmod(0o755)
    env=dict(os.environ)
    for name in ("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION","_MYFENICS_CLOUD_ABI_MANIFEST_SHA256"):
        env.pop(name,None)
    result=subprocess.run(['bash','-c',
        'source "$1" "$2" "$3" && printf "BOUND_HASH=%s\\n" "$_MYFENICS_CLOUD_ABI_MANIFEST_SHA256"',
        'fresh-test',str(script),str(prefix),str(manifest)],env=env,text=True,capture_output=True)
    assert 'UCX fixture diagnostic on stdout' in result.stdout
    if import_exit:
        assert result.returncode!=0 and 'BOUND_HASH=' not in result.stdout
    else:
        assert result.returncode==0
        assert result.stdout.splitlines()[-1]=='BOUND_HASH='+expected
        assert len(result.stdout.splitlines()[-1].split('=',1)[1])==64
