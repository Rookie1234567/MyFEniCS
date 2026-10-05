"""Final local V48 docs checks and exact-byte history checks, no science."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

from src.runners.task042_shared import write_json
from src.solvers.bound_array_identity import file_hash
from src.solvers.vector_storage_scope import ROOT, guard_source, window


def main():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);source=guard_source(folder)
    d=ROOT/'docs/task042_neural_coarse_inverse';baseline=json.loads((window.TMP/'history_baseline.json').read_text())
    protected=[]
    for name,meta in baseline.items():
        body=(ROOT/name).read_bytes()
        if file_hash_tail(body,meta['old_bytes'])!=meta['sha256']:
            raise ValueError('old navigation/progress/registry history changed')
        protected.append(name)
    checked=[]
    for path in (d/'review_report_v45.md',d/'response_v48.md',d/'outcomes/lossless_vector_storage_v48.md'):
        width=None;inside=False;tables=[];links=[]
        for number,line in enumerate(path.read_text().splitlines(),1):
            if line.startswith('```'):
                inside=not inside;continue
            if inside:continue
            if line.startswith('|'):
                columns=len(re.split(r'(?<!\\)\|',line))-2
                if width is None:tables.append({'line':number,'columns':columns});width=columns
                if columns!=width:raise ValueError('table width: '+str(path)+':'+str(number))
            else:width=None
            for target in re.findall(r'\]\(([^)]+)\)',line):
                if target.startswith(('http','app:','#')):continue
                target=unquote(target.split('#')[0])
                if not (path.parent/target).exists():raise ValueError('missing local link: '+target)
                links.append(target)
        if inside:raise ValueError('unclosed markdown fence')
        checked.append({'path':str(path.relative_to(ROOT)),'sha256':file_hash(path),'tables':tables,'links':links})
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_26_documentation_contract'],
              [sys.executable,'-m','unittest','-q','src.test.test_lossless_vector_bank'],
              ['git','-c','gc.auto=0','-c','maintenance.auto=false','diff','--check']]
    results=[]
    for index,command in enumerate(commands):
        start=time.perf_counter();r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=False)
        (folder/f'command{index}.stdout').write_text(r.stdout);(folder/f'command{index}.stderr').write_text(r.stderr)
        results.append({'command':command,'returncode':r.returncode,'seconds':time.perf_counter()-start})
        if r.returncode:raise RuntimeError('final focused documentation/codec regression')
    write_json(folder/'documentation_checks.json',{'status':'PASSED_LOCAL','source':source,'checked':checked,'history_suffixes':protected,
              'commands':results,'GitHub_visual':'NOT_VERIFIED_CACHE_MISS','CI':'NOT_RUN','new_scientific_array_reads':0})
    print(json.dumps({'documentation_tests':15,'codec_tests':10,'history_suffixes':len(protected),'status':'PASSED_LOCAL'}),flush=True)


def file_hash_tail(body,length):
    import hashlib
    return hashlib.sha256(body[-length:]).hexdigest()


if __name__=='__main__':
    main()
