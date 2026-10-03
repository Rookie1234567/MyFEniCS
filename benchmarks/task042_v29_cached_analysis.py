"""Frozen JSON/gzip metadata analysis only; never loads a real ndarray."""
import csv,gzip,json
from pathlib import Path
from benchmarks.task042_admission_receipt import replay
from src.io.task042_profile import ROOT
from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import file_hash

RECORDS=ROOT/'docs/task042_neural_coarse_inverse/outcomes/records'


def cpu_reasons(output):
    summaries=[]
    for suffix,expected in [('accepted',[11,22,26]),('rejected',[])]:
        path=RECORDS/f'admission_{suffix}_v28.json.gz'
        d=json.loads(gzip.decompress(path.read_bytes()));answer=replay(d)
        assert answer['candidate_cpus']==expected
        threads={t['tid']:(p,t) for p in d['neighbor_processes'] for t in p['threads']}
        rows=[]
        for entry in d['cpu_decisions']:
            reasons=[]
            for peer,labels in entry['excluded_siblings'].items():
                for label in labels:
                    item=dict(excluded_cpu=int(peer),rule=label.split(':')[0])
                    if ':' in label:
                        tid=int(label.split(':')[1]);process,t=threads[tid]
                        item.update(pid=process['pid'],tid=tid,process_start_ticks=process['start_ticks'],
                            thread_start_ticks=t['start_ticks'],thread_last_cpu=t['cpu'],affinity=t['affinity'],
                            sampled_delta_ticks=d['thread_delta_ticks'].get(str(tid)),name=process['name'])
                    reasons.append(item)
            rows.append(dict(cpu=entry['cpu'],socket=entry['socket'],core=entry['core'],SMT_siblings=entry['siblings'],
                busy_fraction=d['cpu_busy_fractions'][str(entry['cpu'])],eligible=entry['eligible'],exclusions=reasons))
        assert [x['cpu'] for x in rows if x['eligible']]==expected
        out=output/f'cpu_exclusion_{suffix}_v29.json'
        write_json(out,dict(schema='task042.v29.frozen-cpu-reasons',snapshot_utc=d['utc'],snapshot_sha256=file_hash(path),
            no_live_sampling=True,candidates=expected,rows=rows))
        csv_path=output/f'cpu_exclusion_{suffix}_v29.csv'
        with csv_path.open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['cpu','socket','core','SMT','busy_fraction','eligible','excluded_peer','rule','pid','tid','process_start_ticks','thread_start_ticks'])
            for row in rows:
                for reason in row['exclusions'] or [{}]:
                    writer.writerow([row['cpu'],row['socket'],row['core'],'/'.join(map(str,row['SMT_siblings'])),row['busy_fraction'],row['eligible'],
                        *[reason.get(k,'') for k in ('excluded_cpu','rule','pid','tid','process_start_ticks','thread_start_ticks')]])
        summaries.append(dict(snapshot=suffix,candidates=expected,allowed_cpus=len(rows),
            snapshot=dict(path=str(path),sha256=file_hash(path)),table=dict(path=str(out),sha256=file_hash(out)),
            at_most_5_percent=sum(x['busy_fraction']<=.05 for x in rows),policy_unchanged=True))
    write_json(output/'cpu_exclusions_v29.json',dict(status='FROZEN_SNAPSHOTS_RECOMPUTED',snapshots=summaries,
        interpretation='historical admission policy exclusion, not continuous full CPU utilization'))


def cost_ledger(output):
    sources=[];stages=[]
    for version in range(24,29):
        p=RECORDS/f'resource_costs_v{version}.json';d=json.loads(p.read_text())
        sources.append(dict(path=str(p),sha256=file_hash(p),bytes=p.stat().st_size))
        formal=d.get('actor_supervised_wall_seconds',d.get('formal_supervised_wall_seconds',d.get('formal_actor_wall_seconds',d.get('numeric_actor_seconds',0.))))
        auxiliary=d.get('auxiliary_supervised_wall_seconds',d.get('supervised_auxiliary_wall_seconds',d.get('V28_supervised_auxiliary_seconds',0.)))
        stages.append(dict(version=version,formal_supervised_seconds=formal,auxiliary_supervised_seconds=auxiliary,
            source_role='measured historical research, not complete successful N=1',
            nonadditive_nested_timers=d.get('nonadditive_nested_timers',{})))
    v26=json.loads((RECORDS/'resource_costs_v26.json').read_text())
    v24=json.loads((RECORDS/'resource_costs_v24.json').read_text())
    thin=sum(v26['nonadditive_nested_timers']['thin_decomposition_seconds']);actor=v26['actor_supervised_wall_seconds']
    sizes=[2913,2676,2289,2076,2439,2220,1863,1668];outer=[0,1,2,3,4,6]
    payload=32*(3888**2+sum(sizes[b]**2 for b in outer))
    assert payload==1591420032
    table=[dict(item=k,status=s,value=v,unit=unit,scope=scope) for k,s,v,unit,scope in [
        ('upstream operator packet assembly','unknown',None,'seconds','full geometry-to-packet lineage not reconstructed'),
        ('V24 full setup run','measured',sum(x['supervised_wall_seconds'] for x in v24['formal_runs'] if x['stage']=='SETUP'),'seconds','includes qualification and audit nesting; not exclusive LU time'),
        ('V26 joint assembly','measured',v26['nonadditive_nested_timers']['assembly_seconds'],'seconds','nested, not added to actor'),
        ('V26 joint factorization','measured',v26['nonadditive_nested_timers']['factor_seconds'],'seconds','nested, not added to actor'),
        ('V26 factor hash+readonly reload','measured',v26['nonadditive_nested_timers']['readonly_factor_hash_reload_seconds'],'seconds','nested, not per-deployment benchmark'),
        ('V26 J solve','measured',v26['nonadditive_nested_timers']['joint_solve_seconds'],'seconds','nine historical solves, not predicted Bfull cost'),
        ('V26 original S/SH actions','measured',v26['nonadditive_nested_timers']['original_actions'],'seconds','nested original oracle timers'),
        ('V26 port chain','measured',v26['nonadditive_nested_timers']['port_chain'],'seconds','contains action nesting; not additive'),
        ('V26 two thin decompositions','measured',thin,'seconds','same diagnostic actor scope'),
        ('V24 old global image QR setup','unknown',None,'seconds','inherited T/U/R full lineage missing'),
        ('postprocessing/audit/IO independent exclusive costs','unknown',None,'seconds','nested records insufficient for exclusive partition'),
        ('seven A+LU payload','derived',payload,'bytes','stored arrays, not RSS or simultaneous peak'),
        ('Bfull qualified deployment time/peak','unknown',None,'seconds/bytes','not authorized or measured'),
        ('best qualified non-neural complete N=1 baseline','unknown',None,'seconds/bytes','no fully qualified solve available')]]
    write_json(output/'complete_cost_ledger_v29.json',dict(schema='task042.v29.cost-necessary-conditions',shared_workstation=True,
        sources=sources,historical_stages=stages,cost_table=table,nonadditive_nested_timers=True,
        historic_formal_research_lower_seconds=77161.55713859801,historical_other_auxiliary_and_single_solve_lineage='unknown retained',
        full_block_apply=dict(J_solves=2,outer_solves_each=1,outer_blocks=6,local_triangular_passes=16,original_A=2,
            final_true_residual_A_and_port_closure='additional',original_A_port_chain_cost='also included, nested not double added'),
        qualification=dict(required='seven source/hash/row witnesses plus original primal/adjoint/port consistency',time='unknown for Bfull'),
        lifecycle=dict(cold_setup='existing six outer factors plus joint preparation; full setup unknown',
            reload_each_apply='hash+mmap seven bundles each time; not benchmarked',resident_reuse='load once; no repeated hash; measured simultaneous RSS unknown',
            stored_A_LU_unique_bytes=payload,deploy_LU_only_payload_lower_bytes=payload//2,
            simultaneous_peak='unknown; include pages, copies, pivots, hash buffers, libraries, ports, workspace and overlap; bytes are not peak'),
        neural_threshold=.20,complete_baseline_qualified=False,neural_increment='NOT_DEMONSTRATED',
        time_necessary_condition='Tremoved - Tadded >= 0.20*Tbase',
        added_costs=['data generation','training','model setup/load','inference','extra exact correction','audit'],
        N=1,amortization_assumed=False,
        thin_only_upper_share=dict(seconds=thin,actor_seconds=actor,fraction=thin/actor,percent=100*thin/actor,
            verdict='even free replacement cannot reach 20% in this diagnostic scope; not a full-solve share'),
        possible_large_cost_replacement='factor setup/storage, action/repeated solves or new qualified directions require new evidence; feasibility unknown',
        fixed_space_coefficients='cannot beat the exact same-space residual minimum',
        peak_necessary_condition='Mnew_simultaneous <= 0.80*Mbase_simultaneous, with other resource metric compliant',
        peak_from_cumulative_object_volume_forbidden=True))


def main():
    output=RECORDS;cpu_reasons(output);cost_ledger(output)


if __name__=='__main__':main()
