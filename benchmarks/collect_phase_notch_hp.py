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


def sampling_receipt(path):
    count=0;previous=None;gap=0.;peak=swap=0
    if Path(path).exists():
        with Path(path).open() as source:
            for line in source:
                r=json.loads(line);now=r['elapsed_seconds'];count+=1
                if previous is not None:gap=max(gap,now-previous)
                previous=now;peak=max(peak,r['rss_bytes']);swap=max(swap,r['swap_bytes'])
    return dict(sample_count=count,actual_max_sample_gap_seconds=gap,
        sampled_tree_peak_bytes=peak,own_swap_peak_bytes=swap,sampled_not_cgroup=True)


def saved_checks(states,comparisons):
    from benchmarks.collect_phase_explicit_accuracy import vector_audit
    from src.solvers.scattering_anchor import relative
    from src.solvers.phase_notch_hp_modes import keyed_modes,compare_payloads
    rows=[];regions={};cache={};pair_gates={}
    for row in states.get('VERIFY_COST',{}).get('rows',[]):
        s=states[row['role']];v=checked_arrays(s['arrays']);b=s['boundary']['arrays'][1]
        if b['sha256'] not in cache:cache[b['sha256']]=checked_arrays(b)
        raw=checked_arrays(row['arrays']);checked=vector_audit(raw,v,cache[b['sha256']],s['degree'])
        vi,vt=raw['interior_only_volume_action'],raw['trace_only_volume_action']
        checked['recovery']['split_action_identity_operation_scale']=float(np.linalg.norm(vi+vt-raw['volume_action'])/max(np.linalg.norm(vi)+np.linalg.norm(vt),1e-30))
        modes=json.loads(Path(s['output']['fields']['path']).with_name('port_power.json').read_text())
        keyed_modes(modes,s['case_spec']['complete_modes'])
        rows.append(dict(role=row['role'],recalculated=checked,mode_count=len(modes['orders']),parent_array_sha256=s['arrays']['sha256'],
            direct_internal_target_pass=max(checked['audit'][k] for k in ('true','augmented','port'))<=1e-10))
    fields=('E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered')
    notch=np.asarray(plan_record()['physical_descriptor']['geometry']['notch_box_nm']).reshape(3,2)
    for name,p in comparisons.items():
        a=checked_arrays(p['arrays']);b=checked_arrays(p['q23_arrays']);sums=a['per_cell_integrals'].sum(axis=0)
        if a['per_cell_integrals'].shape[1:]!=(6,3) or not np.isfinite(sums).all() or np.any(sums<0):raise ValueError('complete physical integral inventory')
        components=a['per_cell_component_error_squared']
        if components.shape!=a['per_cell_integrals'].shape or not np.isfinite(components).all() or np.any(components<0) or not np.allclose(components.sum(axis=2),a['per_cell_integrals'][:,:,0],rtol=1e-12,atol=1e-26):raise ValueError('complete physical component squared inventory')
        actual=[];selected_values=[]
        for f,t in zip(fields,sums,strict=True):
            value=float(np.sqrt(t[0])/max(np.sqrt(t[1]),1e-12));actual.append(value)
            if not np.isclose(value,p['fields'][f]['relative'],rtol=1e-11,atol=1e-15):raise ValueError('physical relative from saved arrays')
            select=relative(a['selected_'+f+'_first']-a['selected_'+f+'_second'],a['selected_'+f+'_second'])
            selected_values.append(select)
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
        from src.solvers.phase_notch_hp import parent
        left,right=name.split('_');first=states['M']['projected_parent828'] if right=='M' else parent(left) if left=='B0' else states[left];second=states[right]
        payloads=[json.loads(Path(s.get('mode_power_path',Path(s['output']['fields']['path']).with_name('port_power.json'))).read_text()) for s in (first,second)]
        modal,_=compare_payloads(*payloads,len(payloads[0]['orders']))
        for k in ('outgoing_amplitude_at_boundary_relative','mode_power_max_absolute'):
            if not np.isclose(modal[k],p['modes'][k],rtol=1e-10,atol=1e-15):raise ValueError('complete physical mode comparison from saved output')
        power={k:abs(first['output']['port_metrics'][k]-second['output']['port_metrics'][k]) for k in ('R_total','T_total','A_balance')}
        power['A_volume']=abs(first['output']['volume_metrics']['A_volume_total']-second['output']['volume_metrics']['A_volume_total'])
        energy=[abs(s['output']['volume_metrics']['energy_closure_error_port_volume']) for s in (first,second)]
        qualify=all(np.isfinite(x) and 0<=x<=1e-4 for x in actual+selected_values+[modal['outgoing_amplitude_at_boundary_relative']]) and modal['mode_power_max_absolute']<=1e-6 and max(power.values())<=1e-5 and max(energy)<=1e-5 and qdef<=1e-10
        pair_gates[name]=dict(field_mode_power_pass=bool(qualify),field_max=max(actual),selected_max=max(selected_values),modal=modal,power=power,energies=energy,
            source_parent_array_sha256=p['parent_array_sha256'],reference_floor=1e-12,quadrature_operation=qdef)
        if bool(qualify)!=bool(p['pass_gate']):
            # A false equation/direct gate may validly restrict an otherwise
            # accurate pair, but a reported pass cannot override physical data.
            if p['pass_gate']:raise ValueError('reported pair pass conflicts with saved scientific values')
    return rows,regions,pair_gates


def collect():
    window.guard_worker_parent();folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);out=folder/'records';out.mkdir()
    pointers={r:json.loads((ARTIFACT/(r+'.json')).read_text()) for r in STAGES if (ARTIFACT/(r+'.json')).exists()}
    states={r:stage(r) for r in pointers};costs=[];sources={};arrays=[];identities=[];lifetimes=[]
    for run in window.ledger()['runs']:
        directory=Path(run['folder']);manifest=json.loads((directory/'run_manifest.json').read_text());summary=directory/('run_summary.json' if (directory/'run_summary.json').exists() else 'summary.json')
        s=json.loads(summary.read_text());role=run['role'];worker=ARTIFACT/directory.name
        result=json.loads((worker/'result.json').read_text()) if (worker/'result.json').exists() else {}
        timings=measured_timeline(worker/'events.jsonl') if (worker/'events.jsonl').exists() else {}
        resources=sampling_receipt(directory/'supervision/resources.jsonl')
        timed=sum(timings.get('exclusive_seconds',{}).values())
        costs.append(dict(role=role,folder=run['folder'],source_sha=run['source_sha'],classification=s['classification'],
            supervised_wall_seconds=run['elapsed_seconds'],cold_N1_dat_launch_lower_seconds=s['launch_wall_seconds'],
            timings=timings,peak_bytes=run['peak_bytes'],swap_bytes=run['swap_bytes'],
            recorded_disjoint_interval_seconds=timed,
            supervised_outside_timed_intervals_seconds=max(0.,run['elapsed_seconds']-timed),
            actual_calls=result.get('calls','unknown'),shared_workstation=True,resources=resources,
            cost_scope='supervision, failed work and postprocessing included; exclusive intervals must not be added twice',
            factor_cache='numeric factor cold per case; OS/JIT cache not cleared')))
        sources[run['source_sha']]=manifest['implementation_hashes']
        if (directory/'resolved_config.json').exists():
            resolved=json.loads((directory/'resolved_config.json').read_text())
            identities.append(dict(role=role,source_sha=run['source_sha'],input_sha256=manifest['input_sha256'],
                resolved_sha256=digest(directory/'resolved_config.json'),physical_sha256=manifest['physical_sha256'],
                CPU=manifest['cpu'],rank_cpus=manifest['rank_cpus'],MPI_size=manifest['MPI_size'],
                environment_mode=manifest['environment_mode'],
                physical={k:resolved[k] for k in ('geometry','materials','incidence','discretization','boundary')}))
        if (worker/'events.jsonl').exists():
            events=[json.loads(line) for line in (worker/'events.jsonl').read_text().splitlines()]
            lifetimes.append(dict(role=role,source_sha=run['source_sha'],
                release_events=[r for r in events if 'released' in r['event'] or 'saved' in r['event']],
                live_object_payload_not_RSS=True))
    for p in ARTIFACT.rglob('*.npz'):
        arrays.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=digest(p)))
    comparisons={p.stem:json.loads(p.read_text()) for p in (ARTIFACT/'comparisons').glob('*.json')}
    independent,regions,pair_gates=saved_checks(states,comparisons)
    checks=dict(cases={r:{k:v.get(k) for k in ('status','case_spec','equation_pass','direct_target_pass','original_audit','recovery','capacity')}
        for r,v in states.items() if r in SOLVES},comparisons=comparisons,
        independent_audits=independent,independent_pair_gates=pair_gates,decision=json.loads((window.TMP/'decision.json').read_text()),
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
    write_json(out/'physical_identity_bindings_v52.json',dict(runs=identities,
        canonical_material_path='input/materials/si_optical_constants_v1.json'))
    write_json(out/'object_lifetimes_v52.json',dict(routes=lifetimes))
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
