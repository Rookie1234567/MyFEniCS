"""Incremental V52 saved-state evidence and accounting, never a new solve."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import re
from urllib.parse import unquote
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers.phase_notch_hp_scope import ROOT,ARTIFACT,STAGES,SOLVES,window,stage,plan_record
from src.solvers.scattering_anchor_reporting import disjoint_timings
from src.solvers.scattering_anchor_checks import checked_arrays


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def measured_timeline(path):
    events=[json.loads(line) for line in Path(path).read_text().splitlines()]
    depth=0;boundary=0
    for i,e in enumerate(events):
        if e['event'].endswith('_begin'):depth+=1
        elif e['event'].endswith('_end'):depth-=1
        if depth<0:raise ValueError('unmatched timeline end')
        if depth==0:boundary=i+1
    t=disjoint_timings(events[:boundary])
    return dict(t,complete=boundary==len(events),unclosed_suffix_seconds='unknown' if boundary<len(events) else None)


def saved_checks(states,comparisons):
    from benchmarks.collect_phase_explicit_accuracy import vector_audit
    from src.solvers.scattering_anchor import relative
    from src.solvers.phase_notch_hp_modes import keyed_modes
    rows=[];regions={};cache={}
    for row in states.get('VERIFY_COST',{}).get('rows',[]):
        s=states[row['role']];v=checked_arrays(s['arrays']);b=s['boundary']['arrays'][1]
        if b['sha256'] not in cache:cache[b['sha256']]=checked_arrays(b)
        raw=checked_arrays(row['arrays']);checked=vector_audit(raw,v,cache[b['sha256']],s['degree'])
        vi,vt=raw['interior_only_volume_action'],raw['trace_only_volume_action']
        checked['recovery']['split_action_identity_operation_scale']=float(np.linalg.norm(vi+vt-raw['volume_action'])/max(np.linalg.norm(vi)+np.linalg.norm(vt),1e-30))
        modes=json.loads(Path(s['output']['fields']['path']).with_name('port_power.json').read_text())
        keyed_modes(modes,s['case_spec']['complete_modes'])
        rows.append(dict(role=row['role'],recalculated=checked,mode_count=len(modes['orders']),parent_array_sha256=s['arrays']['sha256']))
    fields=('E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered')
    notch=np.asarray(plan_record()['physical_descriptor']['geometry']['notch_box_nm']).reshape(3,2)
    for name,p in comparisons.items():
        a=checked_arrays(p['arrays']);b=checked_arrays(p['q23_arrays']);sums=a['per_cell_integrals'].sum(axis=0)
        if a['per_cell_integrals'].shape[1:]!=(6,3) or not np.isfinite(sums).all() or np.any(sums<0):raise ValueError('complete physical integral inventory')
        actual=[]
        for f,t in zip(fields,sums,strict=True):
            value=float(np.sqrt(t[0])/max(np.sqrt(t[1]),1e-12));actual.append(value)
            if not np.isclose(value,p['fields'][f]['relative'],rtol=1e-11,atol=1e-15):raise ValueError('physical relative from saved arrays')
            select=relative(a['selected_'+f+'_first']-a['selected_'+f+'_second'],a['selected_'+f+'_second'])
            if not np.isclose(select,p['selected'][f],rtol=1e-11,atol=1e-15):raise ValueError('fixed selected complex vector from saved arrays')
        qdef=float(np.max(np.abs(b['per_cell_integrals'].sum(axis=0)[:,:2]-sums[:,:2])/np.maximum(sums[:,1,None],1e-24)))
        centers=a['common_centers'];inside=np.all((centers>=notch[:,0])&(centers<=notch[:,1]),axis=1)
        # Region membership is frozen geometry/material, never an error-based mask.
        from src.solvers.phase_explicit_accuracy import configuration
        cfg=configuration('NOTCH',4);right=name.split('_')[1]
        labels=checked_arrays(states[right]['arrays'])['cell_tags'][a['parent_second']]
        si=labels==cfg.tags.grating;substrate=labels==cfg.tags.substrate;air=(labels==cfg.tags.air)&~inside
        masks=dict(air_excluding_notch=air,notch_air=inside,substrate=substrate,Si_block=si)
        if not np.all(np.sum(list(masks.values()),axis=0)==1):raise ValueError('disjoint physical region inventory')
        square={k:a['per_cell_integrals'][mask,:,0].sum(axis=0) for k,mask in masks.items()}
        if not np.allclose(sum(square.values()),sums[:,0],rtol=1e-12,atol=1e-30):raise ValueError('region error squared conservation')
        regions[name]=dict(counts={k:int(mask.sum()) for k,mask in masks.items()},fields={f:{k:dict(error_squared=float(square[k][i]),fraction=float(square[k][i]/max(sums[i,0],1e-30))) for k in square} for i,f in enumerate(fields)},
            component_squared=a['per_cell_component_error_squared'].sum(axis=0),quadrature_operation_recalculated=qdef,
            full_cross_terms=True,source_array_sha256=p['arrays']['sha256'])
        if qdef>1e-10:raise ValueError('common quadrature operation gate')
    return rows,regions


def collect():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    pointers={r:json.loads((ARTIFACT/(r+'.json')).read_text()) for r in STAGES if (ARTIFACT/(r+'.json')).exists()}
    states={r:stage(r) for r in pointers};costs=[];sources={};arrays=[]
    for run in window.ledger()['runs']:
        directory=Path(run['folder']);manifest=json.loads((directory/'run_manifest.json').read_text());summary=directory/('run_summary.json' if (directory/'run_summary.json').exists() else 'summary.json')
        s=json.loads(summary.read_text());role=run['role'];worker=ARTIFACT/directory.name
        result=json.loads((worker/'result.json').read_text()) if (worker/'result.json').exists() else {}
        timings=measured_timeline(worker/'events.jsonl') if (worker/'events.jsonl').exists() else {}
        costs.append(dict(role=role,folder=run['folder'],source_sha=run['source_sha'],classification=s['classification'],
            supervised_wall_seconds=run['elapsed_seconds'],cold_N1_dat_launch_lower_seconds=s['launch_wall_seconds'],
            timings=timings,peak_bytes=run['peak_bytes'],swap_bytes=run['swap_bytes'],
            actual_calls=result.get('calls','unknown'),shared_workstation=True))
        sources[run['source_sha']]=manifest['implementation_hashes']
    for p in ARTIFACT.rglob('*.npz'):
        arrays.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=digest(p)))
    comparisons={p.stem:json.loads(p.read_text()) for p in (ARTIFACT/'comparisons').glob('*.json')}
    independent,regions=saved_checks(states,comparisons)
    checks=dict(cases={r:{k:v.get(k) for k in ('status','case_spec','equation_pass','direct_target_pass','original_audit','recovery','capacity')}
        for r,v in states.items() if r in SOLVES},comparisons=comparisons,
        independent_audits=independent,decision=json.loads((window.TMP/'decision.json').read_text()),
        NN_training=0,NN20=False,target_qualified=False)
    # Only new arrays and records; old parent identities are references.
    write_json(out/'hp_accuracy_checks_v52.json',checks)
    write_json(out/'physical_error_regions_v52.json',dict(comparisons=regions))
    write_json(out/'run_index_v52.json',dict(runs=window.ledger()['runs'],pointers=pointers))
    write_json(out/'array_inventory_v52.json',dict(files=arrays))
    write_json(out/'resource_costs_v52.json',dict(costs=costs,charged_seconds=window.charged_wall(),clock=window.snapshot(),
        historical_loaded_known_lower_seconds=plan_record()['historical_loaded_known_lower_seconds'],
        historical_unmeasured_fees='unknown; never filled with zero',scope='shared-workstation measured supervised/launch bounds, not uncontended speed'))
    archive=ARTIFACT/('raw_'+folder.name);archive.mkdir();items=[];seen=set()
    for root in [window.TMP]+[Path(r['folder']) for r in window.ledger()['runs']]+[ARTIFACT]:
        for p in root.rglob('*'):
            if not p.is_file() or p.is_relative_to(archive) or p.is_relative_to(out) or p in seen:continue
            seen.add(p)
            if p.suffix not in ('.json','.jsonl','.log','.stdout','.stderr','.txt','.dat'):continue
            if p.is_relative_to(window.TMP) and any(s in p.relative_to(window.TMP).parts for s in ('edit','pycache','xdg','tmp','torch','uv','ruff')):continue
            h=digest(p);target=archive/h
            if not target.exists():shutil.copyfile(p,target)
            items.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=h,archived=str(target.relative_to(ROOT))))
    write_json(out/'raw_archive_index_v52.json',dict(files=items))
    source_archive=ARTIFACT/'source_archive';source_archive.mkdir(exist_ok=True);bindings=[]
    for sha,hashes in sources.items():
        for path,h in hashes.items():
            data=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','show',sha+':'+path],cwd=ROOT)
            if hashlib.sha256(data).hexdigest()!=h:raise ValueError('actual clean source bytes '+path)
            dest=source_archive/h
            if not dest.exists():dest.write_bytes(data)
            bindings.append(dict(source_sha=sha,path=path,sha256=h,archived=str(dest.relative_to(ROOT))))
    write_json(out/'source_bindings_v52.json',dict(files=bindings,document_HEAD_is_not_run_source=True))
    print(json.dumps(dict(status='V52_COLLECTED',records=str(out))))


def documents():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);authority=plan_record()['review_commit'];task=ROOT/'docs/task042_neural_coarse_inverse'
    targets=[];protected=[]
    for name in ('docs/task042_neural_coarse_inverse/README.md','docs/task042_neural_coarse_inverse/outcomes/summary.md',
        'docs/task042_neural_coarse_inverse/outcomes/test_summary.md','docs/task042_neural_coarse_inverse/outcomes/changed_files.md',
        'docs/development_progress.md','docs/development_model_registry.md'):
        old=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','show',authority+':'+name],cwd=ROOT);new=(ROOT/name).read_bytes()
        if not new.endswith(old):raise ValueError('historical suffix changed '+name)
        targets.append((ROOT/name,new[:-len(old)].decode()));protected.append(dict(path=name,sha256=hashlib.sha256(old).hexdigest()))
    targets += [(p,p.read_text()) for p in (task/'review_report_v50.md',task/'response_v52.md',task/'outcomes/phase_notch_hp_accuracy_v52.md')]
    checked=[]
    for p,body in targets:
        width=None;inside=False;tables=[];links=[]
        if '$$' in body or '\\[' in body:raise ValueError('unsupported display math')
        for i,line in enumerate(body.splitlines(),1):
            if line.startswith('```'):inside=not inside;continue
            if inside:continue
            if line.startswith('|'):
                count=len(re.split(r'(?<!\\)\|',line))-2
                if width is None:tables.append(dict(line=i,columns=count));width=count
                if width!=count:raise ValueError('table width '+str(p))
            else:width=None
            for link in re.findall(r'\]\(([^)]+)\)',line):
                if link.startswith(('http','app:','#')):continue
                if not (p.parent/unquote(link.split('#')[0])).exists():raise ValueError('missing evidence link '+link)
                links.append(link)
        if inside:raise ValueError('unclosed fence')
        checked.append(dict(path=str(p.relative_to(ROOT)),sha256=digest(p),tables=tables,links=links))
    began=time.monotonic();r=subprocess.run([sys.executable,'-m','unittest','-q','src.test.test_26_documentation_contract'],cwd=ROOT,capture_output=True,text=True)
    (folder/'documentation.stdout').write_text(r.stdout);(folder/'documentation.stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('focused documentation contract')
    write_json(folder/'documentation_checks.json',dict(status='PASSED_LOCAL',final_bytes=checked,history=protected,
        test_seconds=time.monotonic()-began,GitHub_visual='NOT_VERIFIED',CI='NOT_RUN'))
    print(json.dumps(dict(status='V52_DOCUMENTS_PASSED_LOCAL')))


if __name__=='__main__':
    if sys.argv[1:]==['--docs']:documents()
    elif not sys.argv[1:]:collect()
    else:raise ValueError('collector arguments')
