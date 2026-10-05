"""V50 compact evidence, source archival and disjoint cost; no new solve."""
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

from src.runners.task042_shared import write_json
from src.solvers.scattering_accuracy_scope import ROOT,ARTIFACT,STAGES,SOLVES,stage,window,implementation_hashes
from src.solvers.scattering_anchor_reporting import disjoint_timings
from benchmarks.collect_scattering_anchor import digest


def store(out,name,value):
    # Large independent per-mode/source inventories are compact, exact JSON gzip.
    p=out/(name+'.json')
    content=json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2).encode()
    if len(content)>200000:
        p=p.with_suffix('.json.gz')
        with gzip.GzipFile(filename=str(p),mode='wb',mtime=0) as f:f.write(content)
    else:write_json(p,value)
    return dict(path=str(p.relative_to(ROOT)),sha256=digest(p),bytes=p.stat().st_size)


def collect():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    if not folder.resolve().is_relative_to(window.TMP):raise ValueError('V50 collector namespace')
    pointers={p.stem:json.loads(p.read_text()) for p in ARTIFACT.glob('*.json')};stages={k:stage(k) for k in pointers}
    entries=[dict(stage=k,status=stages[k]['status'],source=stages[k]['source_sha'],worker_seconds=stages[k]['elapsed_worker_seconds'],pointer=pointers[k])
             if k in stages else dict(stage=k,status='not_run',reason='conditional stage not admitted or unavailable') for k in STAGES]
    store(out,'stage_index_v50',dict(rows=entries,window=window.snapshot(),old_ledgers_reopened=False))
    from src.solvers.scattering_accuracy_checks import check_boundary
    boundary=check_boundary(stages['BOUNDARY']);store(out,'boundary_independent_checks_v50',boundary)
    attribution=stages.get('ATTRIBUTION',{})
    store(out,'saved_field_attribution_v50',{k:v for k,v in attribution.items() if k not in ('saved_original_equation_rechecks',)})
    store(out,'saved_field_equation_rechecks_v50',dict(rows=[{k:v for k,v in r.items() if k!='tensor_checks'}|
        dict(tensor_summary={k:v for k,v in r['tensor_checks'].items() if k!='all_actual_classes'},
             raw_class_count=len(r['tensor_checks']['all_actual_classes']),
             full_tensor_record_path=str(Path(pointers['ATTRIBUTION']['path']).relative_to(ROOT)))
        for r in attribution.get('saved_original_equation_rechecks',[])]))
    store(out,'representation_screen_v50',stages.get('SCREEN',dict(status='not_run')))
    store(out,'complete_accuracy_checks_v50',stages.get('VERIFY',dict(status='not_run')))
    store(out,'opportunity_decision_v50',stages.get('COST',dict(status='not_run')))
    resources=[];maxgap=0.;peak=swap=samples_count=0
    for r in window.ledger()['runs']:
        p=Path(r['folder'])/'supervision/resources.jsonl'
        samples=[json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []
        times=[s['elapsed_seconds'] for s in samples];gap=max((b-a for a,b in zip(times,times[1:])),default=0.)
        maxgap=max(maxgap,gap);peak=max(peak,r['peak_bytes']);swap=max(swap,r['swap_bytes']);samples_count+=len(samples)
        resources.append({k:r[k] for k in ('role','source_sha','folder','classification','elapsed_seconds','peak_bytes','swap_bytes','descendants_cleared')}|
            dict(sample_count=len(samples),actual_max_sample_gap_seconds=gap))
    store(out,'resource_costs_snapshot_v50',dict(runs=resources,known_prior_lower_seconds=92100.10441544611,
        charged_before_collector_settlement_seconds=window.charged_wall(),sampled_tree_peak_bytes=peak,own_swap_peak_bytes=swap,
        actual_max_sample_gap_seconds=maxgap,sample_count=samples_count,historical_unknowns_retained=True,
        sampled_not_cgroup=True,shared_workstation=True,current_collector_and_final_checks_not_yet_settled=True))
    costs=[];lifetimes=[];identities=[]
    for role in SOLVES:
        r=stages.get(role)
        if r is None or r['status']!='COMPLETED':continue
        ad=Path(r['arrays']['path']).parent;rd=ROOT/'results/task042'/ad.name
        summary=json.loads((rd/'run_summary.json').read_text());manifest=json.loads((rd/'run_manifest.json').read_text())
        resolved=json.loads((rd/'resolved_config.json').read_text())
        events=[json.loads(x) for x in (ad/'events.jsonl').read_text().splitlines()];timing=disjoint_timings(events)
        costs.append(dict(stage=role,source=r['source_sha'],worker_wall_seconds=r['elapsed_worker_seconds'],
            complete_dat_launch_measured_lower_seconds=summary['launch_wall_seconds'],
            tree_peak_bytes=summary['sampled_process_tree_rss_peak_bytes'],
            **timing,build_audit=r['build_audit'],boundary=r['boundary'],tensor_checks_seconds=r['tensor_checks']['seconds'],
            additional_complete_VERIFY_cost='charged separately; attribution/qualification/setup/failed attempts remain research costs',
            numerical_objects_cold=True,OS_JIT_cache='not cleared; source namespace and inventory recorded',
            raw_tensor_checkpoint_reused=r['tensor_checks'].get('failed_prepare_checkpoint_reuse'),
            qualification_reference_cost='all independent original class checks and failed prepares retained in research ledger; reused tensors are not a free cold setup',
            performance='INCONCLUSIVE due changed q, clipping semantics, shared load and unequal cache/qualification work'))
        lifetimes.append(dict(stage=role,events=events,unique_owners_are_visible_numpy_lower_bounds_not_RSS=True,
            opaque_factor_workspaces='unknown, included in sampled tree RSS'))
        identities.append(dict(stage=role,physical_contract_sha256=r['physical_contract_sha256'],input_sha256=r['input_sha256'],
            physical_model={k:resolved[k] for k in ('geometry','materials','incidence','discretization','boundary')},
            resolved_file_sha256=digest(rd/'resolved_config.json'),mode_sha256=r['mode_sha256'],case=r['case'],degree=r['degree'],grid=r['grid'],
            applied_surface_rule='fixed q47 complete inventory; separate q63 verification',
            historical_resolved_rule_erratum='inherited descriptive max(10,2p+...) label superseded by explicit47 and numerical factory; original resolved bytes preserved',
            arrays=r['arrays'],returned_arrays=r['returned_arrays'],source_sha=r['source_sha'],capacity=r['capacity']))
    store(out,'cold_n1_costs_v50',dict(routes=costs,unknown_preactivation_and_historical_fine_phases_not_zero=True))
    store(out,'object_lifetimes_v50',dict(routes=lifetimes))
    store(out,'physical_identity_bindings_v50',dict(routes=identities,material_table_id='SI_OPTICAL_CONSTANTS_USER_20260929_V1',
        canonical_material_path='input/materials/si_optical_constants_v1.json',source_wavelength_nm='0.699999988',nominal_wavelength_nm='0.7'))
    store(out,'run_index_v50',dict(runs=[{k:r[k] for k in ('role','folder','source_sha','classification')} for r in window.ledger()['runs']],
        pointers=pointers,minimum_package=str(window.TMP/'minimum_result_cost_package.json')))
    store(out,'repair_journal_v50',dict(records=[dict(path=str(p.relative_to(ROOT)),sha256=digest(p))
        for p in sorted((window.TMP/'intake').glob('*.json'))],software_failures_preserved=True,scientific_negative_is_not_bug=True))
    arrays=[]
    for p in ARTIFACT.rglob('*.npz'):
        arrays.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=digest(p)))
    store(out,'array_inventory_v50',dict(files=arrays,member_shapes_dtypes_hashes_bound_in_parent_receipts=True))
    archive=ARTIFACT/('raw_'+folder.name);archive.mkdir();items=[];seen=set()
    roots=[window.TMP]+[Path(r['folder']) for r in window.ledger()['runs']]+[ARTIFACT]
    for root in roots:
        for p in root.rglob('*'):
            if not p.is_file() or p.is_relative_to(archive) or p.is_relative_to(out) or p in seen:continue
            seen.add(p)
            if p.suffix not in ('.json','.jsonl','.log','.stdout','.stderr','.txt','.dat','.py') or p.stat().st_size>8*2**20:continue
            if p.is_relative_to(window.TMP) and any(s in p.relative_to(window.TMP).parts for s in ('pycache','xdg','tmp','torch','uv','ruff','drafts')):continue
            h=digest(p);target=archive/h
            if not target.exists():shutil.copyfile(p,target)
            items.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=h,archived=str(target.relative_to(ROOT))))
    store(out,'raw_archive_index_v50',dict(files=items,scope='V50 new raw only; all failed/cancelled attempts preserved',
        scientific_arrays_and_JIT_referenced_not_copied=True,stderr='worker stdout/stderr merged unmodified in supervision/worker.log; outer errors explicitly retained'))
    versions={}
    for r in window.ledger()['runs']:
        p=Path(r['folder'])/'run_manifest.json'
        if not p.exists():continue
        m=json.loads(p.read_text())
        for name,h in m['implementation_hashes'].items():versions[r['source_sha'],name]=h
    requests=sorted(versions)
    data=subprocess.run(['git','-c','gc.auto=0','-c','maintenance.auto=false','cat-file','--batch'],cwd=ROOT,
        input=''.join(f'{sha}:{name}\n' for sha,name in requests).encode(),capture_output=True,check=True).stdout
    pos=0;source_rows=[]
    for sha,name in requests:
        end=data.index(b'\n',pos);header=data[pos:end].decode().split();pos=end+1
        if len(header)!=3 or header[1]!='blob':raise ValueError('Git source missing '+sha+':'+name)
        n=int(header[2]);content=data[pos:pos+n];pos+=n+1;h=hashlib.sha256(content).hexdigest()
        if h!=versions[sha,name]:raise ValueError('manifest/clean Git source mismatch '+name)
        target=archive/h
        if not target.exists():target.write_bytes(content)
        source_rows.append(dict(source_sha=sha,path=name,git_blob=header[0],bytes=n,sha256=h,archived=str(target.relative_to(ROOT))))
    if pos!=len(data):raise ValueError('source batch trailing inventory')
    store(out,'source_bindings_v50',dict(rows=source_rows,clean_Git_vs_run_hashes_verified=True,document_HEAD_is_not_run_source=True))
    print(json.dumps(dict(status='COMPLETED',records=str(out),stages=len(entries),sources=len(source_rows),raw_files=len(items))),flush=True)


def documents():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);task=ROOT/'docs/task042_neural_coarse_inverse'
    protected=[]
    for name in ('docs/task042_neural_coarse_inverse/README.md','docs/task042_neural_coarse_inverse/outcomes/summary.md',
                 'docs/development_progress.md','docs/development_model_registry.md'):
        old=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','show','da151228815b08126dc636d3e195673ba04fe45f:'+name],cwd=ROOT)
        if not (ROOT/name).read_bytes().endswith(old):raise ValueError('old history suffix changed '+name)
        protected.append(dict(path=name,bytes=len(old),sha256=hashlib.sha256(old).hexdigest()))
    checked=[]
    for p in (task/'review_report_v48.md',task/'response_v50.md',task/'outcomes/complete_physics_accuracy_cost_v50.md'):
        width=None;inside=False;tables=[];links=[]
        for i,line in enumerate(p.read_text().splitlines(),1):
            if line.startswith('```'):inside=not inside;continue
            if inside:continue
            if line.startswith('|'):
                count=len(re.split(r'(?<!\\)\|',line))-2
                if width is None:tables.append(dict(line=i,columns=count));width=count
                if width!=count:raise ValueError('table width '+str(p)+':'+str(i))
            else:width=None
            for target in re.findall(r'\]\(([^)]+)\)',line):
                if target.startswith(('http','app:','#')):continue
                if not (p.parent/unquote(target.split('#')[0])).exists():raise ValueError('missing link '+target)
                links.append(target)
        if inside:raise ValueError('unclosed fence')
        checked.append(dict(path=str(p.relative_to(ROOT)),sha256=digest(p),tables=tables,links=links))
    for name in implementation_hashes():
        if name.endswith('.py'):compile((ROOT/name).read_bytes(),name,'exec')
    commands=[[sys.executable,'-m','unittest','-q','src.test.test_26_documentation_contract'],
        ['/home/fenics/.cache/uv/archive-v0/hnQ1fNWmbidp7eU4/ruff-0.16.6.data/scripts/ruff','check','--select','E9,F63,F7,F82','benchmarks/collect_scattering_accuracy.py'],
        ['git','-c','gc.auto=0','-c','maintenance.auto=false','diff','--check']]
    rows=[]
    for i,c in enumerate(commands):
        begin=time.monotonic();r=subprocess.run(c,cwd=ROOT,capture_output=True,text=True)
        (folder/f'command{i}.stdout').write_text(r.stdout);(folder/f'command{i}.stderr').write_text(r.stderr)
        rows.append(dict(command=c,returncode=r.returncode,seconds=time.monotonic()-begin))
        if r.returncode:raise RuntimeError('final documentation/source test')
    write_json(folder/'documentation_checks.json',dict(status='PASSED_LOCAL',checked_actual_delivery_bytes=checked,
        old_history_suffixes=protected,commands=rows,GitHub_visual='NOT_VERIFIED_CACHE_MISS',CI='NOT_RUN'))
    print(json.dumps(dict(status='PASSED_LOCAL',documentation_tests=15)),flush=True)


if __name__=='__main__':
    if sys.argv[1:]==['--docs']:documents()
    elif not sys.argv[1:]:collect()
    else:raise ValueError('unknown collector argument')
