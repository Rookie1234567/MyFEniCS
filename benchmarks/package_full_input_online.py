"""Compact V35 delivery from saved metadata, without operators or references."""
import gzip
import hashlib
import json
import math
import re
from pathlib import Path
import subprocess
import tarfile
from datetime import datetime, timezone
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / 'docs/task042_neural_coarse_inverse'
OUT = TASK / 'outcomes/records'
TMP = ROOT / 'tmp/task042/v35'
REVIEW = 'e1926a9cb42329276da4a26f4304f71cbbf97198'
BASE = 'ccd357885f7f9be84efe3be07868cc94f13d93fc'


def read(path):
    return json.loads(Path(path).read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def receipt(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=str(path), sha256=digest(data), bytes=len(data))


def prepend_navigation():
    marker = '<!-- V35-LATEST-END -->'
    common = (
        '本轮首次真实冷启动，用七区局部解处理任意新残差，并由GMRES选择修正组合。'
        '代价是每个非零输入八次局部solve和两次传播作用；这是传统块方法，没有神经训练。\n\n'
        '| 模型／结果身份 | measured或not_run结果 | 解释／边界 |\n'
        '|---|---|---|\n'
        '| .7nm／384hex／p3／q15／18144trace＋40port | 首256步Schur0.20524886351900365>0.01 | ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT，关闭固定七／八块追加预算 |\n'
        '| 原完整方程 | native/augmented0.07959628543991103、total augmented0.027619862207395922>1e-6 | port/恢复/MPC通过不足以授完整解资格 |\n'
        '| 费用／同时采样树峰 | actor188.162088667s／2108018688B／ownswap0；834次S/SH、264次PC | shared-workstation，全部aux/探针/旧费用另列，不双加嵌套计时 |\n'
        '| 原因／范围 | 保存残差平方99.19%在外域；第二周期与FE/REF7 NOT_RUN | 无official R/T/A、NN20%或原尺寸2TB/48h资格 |\n\n')
    pages = {
        TASK/'README.md': ('# V35最新交付：在线冷启动可信负结果，固定块族收口\n\n',
            '[Review V32](review_report_v32.md)／[response](response_v35.md)／[完整结果](outcomes/online_full_input_qualification_v35.md)／[规模桥接](outcomes/original_scale_bridge_v35.md)／[run index](outcomes/records/run_index_v35.json)。'),
        TASK/'outcomes/summary.md': ('# V35统一结果：实际在线失败，原尺寸与神经资格仍未取得\n\n',
            '[response](../response_v35.md)／[结果](online_full_input_qualification_v35.md)／[完整费用](records/resource_costs_v35.json)／[独立checker](records/online_checker_v35.json)／[规模桥接](original_scale_bridge_v35.md)。'),
        ROOT/'docs/development_progress.md': ('# Task042 V35：首次零trace在线七区资格试验完成（2026-10-04）\n\n',
            '[response](task042_neural_coarse_inverse/response_v35.md)／[结果及原尺寸桥接](task042_neural_coarse_inverse/outcomes/original_scale_bridge_v35.md)／[全部消费](task042_neural_coarse_inverse/outcomes/records/resource_costs_v35.json)。'),
        ROOT/'docs/development_model_registry.md': ('# Task042 V35：原micro在线块PC未合格，未发布official场／功率（2026-10-04）\n\n',
            '[response](task042_neural_coarse_inverse/response_v35.md)／[完整原门](task042_neural_coarse_inverse/outcomes/records/online_checker_v35.json)／[模型身份](task042_neural_coarse_inverse/outcomes/records/run_index_v35.json)。'),
    }
    pages[TASK/'outcomes/test_summary.md'] = (
        '# V35测试：真实接线、缓存消费反例及最终静态复验\n\n',
        '首次24pass/1fail保留，fixture结算修复后25pass；独立缓存26pass，含11项伪消费／状态变异拒绝。'
        '最终计数元数据修复后的相关suite、文档合同15项、真实编译与Ruff E9/F见[tests](records/tests_v35.json)。'
        '没有借用旧测试数量、full-repository／MPI2/4／FE／GPU或CI声明。'
        'Watchdog低成本超时测试真实清空自有后代，不操作邻任务。')
    pages[TASK/'outcomes/changed_files.md'] = (
        '# V35依赖分组：opt-in在线核、守卫、独立checker与紧凑证据\n\n',
        '[完整源码与hash](records/source_inventory_v35.json)／[分组](records/selective_manifest_v35.json)。'
        '新FullInputPC只在显式V35入口使用；原oracle与普通default保持。'
        '公共finish增加opt-in总作用hook，小Hp缓存也为显式opt-in，历史raw未改写。'
        '没有fresh FE／merge approval，不提升失败候选为production。')
    for path, (title, links) in pages.items():
        old = path.read_text()
        suffix = old.split(marker+'\n\n',1)[1] if marker in old else old
        path.write_text(title + common + links + '\n\n唯一下一建议是匹配外域Schur的周期／层次全局逆接口与容量资格；本轮不实现。历史后缀逐字保留。\n\n' + marker + '\n\n' + suffix)


def main():
    OUT.mkdir(exist_ok=True)
    pointer = read(ROOT / 'benchmarks/artifacts/task042/v35/ONLINE.json')
    result = read(pointer['path'])
    if result['status'] != 'ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT':
        raise ValueError('V35 delivery cannot invent another numerical decision')
    artifact = Path(pointer['path']).parent
    run = ROOT / 'results/task042' / artifact.name
    book = read(TMP / 'ledger.json')
    current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    start = read(TMP / 'start.json')
    actor = read(run / 'run_summary.json')
    factor_bytes = sum(f['array_bytes'] for x in result['factor_reloads']
                       for f in x['files'] if f['key'] in ('matrix', 'LU'))
    solve_seconds = sum(x['solve_seconds'] for x in result['factor_reloads'])
    reload_seconds = sum(x['load_seconds'] for x in result['factor_reloads'])
    final = result['final']
    state = final['state']
    checks = read(ROOT / 'benchmarks/artifacts/task042/v35/independent_checker.json')
    analysis = read(artifact / 'saved_residual_analysis.json')
    write('online_checker_v35.json', checks)
    write('residual_analysis_v35.json', analysis)
    write('qualification_dispatch_v35.json', dict(
        decision=result['status'], original_equation_gate=final['original_equation_gate'],
        first_cycle_progress_gate=dict(measured=final['audit']['schur_relative'], maximum=0.01, passed=False),
        cycle2='NOT_RUN', independent_FE='NOT_RUN', reference='NOT_READ',
        original_scale='NOT_QUALIFIED', neural_gain_20_percent='NOT_DEMONSTRATED',
        fixed_seven_eight_block_family='CLOSED_FOR_ADDITIONAL_NUMERICAL_BUDGET',
        physical_qualification='NOT_QUALIFIED_EQUATION_GATE_FAILED',
        original_audit=final['audit'], PC_qualification=result['PC_qualification'],
        old_new_S_SH_pairs=result['old_new_S_SH_pairs'], factors=result['factor_status'],
        global_p4=False, new_large_LU=0, new_gecon=0, new_image_QR=0, new_training=0,
        factors_existing_readonly=True))
    write('run_index_v35.json', dict(
        schema='task042.v35.online-cold.v1', branch='task42_neural_coarse_inverse',
        base=BASE, review=REVIEW, source=result['source_sha'], final_checker_source='6e17883a672d6166472bb80c27999afc46d4a059',
        packaging_source=current, run=receipt(run / 'run_summary.json'),
        manifest=receipt(run / 'run_manifest.json'), input=receipt(ROOT / 'input/task042_neural_coarse_inverse/v35_online_cold.dat'),
        result=pointer, plan=receipt(ROOT / 'input/task042_neural_coarse_inverse/full_input_online_v35.json'),
        original_packet=result['operator_packet'], operator_identity=result['operator_identity'],
        map=result['map_check']['map'], factor_reloads=result['factor_reloads'],
        returned_state=state, cold_trace='EXACT_ZERO', cold_port_norm=result['cold_port_norm'],
        warm_reference_cached_directions_read=False, complete_ports=40,
        backend=result['backend'], old_oracle_independent=True,
        budget_counts=result['budget_counts'], status=result['status'],
        official_R_T_A='NOT_RUN', field_qualification='NOT_RUN', shared_workstation=True))
    paths = subprocess.check_output(['git', 'diff', '--name-only', REVIEW, '--'], cwd=ROOT, text=True).splitlines()
    code = [p for p in paths if p.endswith(('.py', '.sh', '.dat')) or p.startswith('input/')]
    write('source_inventory_v35.json', dict(
        numerical_source=result['source_sha'], current_packaging_source=current,
        checker_source='6e17883a672d6166472bb80c27999afc46d4a059', base=BASE, review=REVIEW,
        implementation_files={p: receipt(ROOT / p) for p in code},
        environment=read(TMP / 'aux_check_001/final_cache_check.json'),
        actual_math_threads=result['actual_BLAS_pools'], provenance='actual formal clean source differs from document HEAD',
        same_native_environment=True, installation_changes=0, GPU_used=False, FE_validation_run=False))
    corrections = dict(
        source_raw_immutable=pointer,
        all_batch_equivalent_actions=dict(raw=result['all_batch_equivalent_actions'], correct=834,
            rule='sum original and fast S/SH; raw inherited field counted old oracle only'),
        field_recovery_calls=dict(raw=result['field_recovery_calls'], correct=1,
            rule='one original audit explicitly calls recover once'),
        historical_formal_lower=dict(raw=result['historical_formal_lower_bound_seconds'], correct=77161.55713859801,
            source='Review V32 audited historical lower; not complete N=1'),
        reader_container_hash=dict(rule='container read_bytes may copy largest file; canonical array hash streams64 rows',
            hash_norm_copy_reserve_bytes=result['capacity']['hash_norm_copy_reserve']),
        corrective_source=current, numerical_rerun=False)
    write('metadata_corrections_v35.json', corrections)
    summaries = [(p, read(p)) for p in sorted(TMP.glob('aux_*/summary.json'))]
    probes = [(p, read(p)) for p in sorted(TMP.glob('probe_*.json'))]
    auxiliary = sum(s['elapsed_seconds'] for _, s in summaries)
    probe_seconds = sum(s['elapsed_seconds'] for _, s in probes)
    total = actor['elapsed_seconds'] + auxiliary + probe_seconds
    cost = dict(
        measured_snapshot_UTC=datetime.now(timezone.utc).isoformat(), final_auxiliary_pending=not book['closed'],
        actor_supervised_seconds=actor['elapsed_seconds'], auxiliary_supervised_seconds=auxiliary,
        paid_probe_seconds=probe_seconds, new_supervised_probe_seconds=total,
        limits=dict(total=900, actor=600, auxiliary=250, probe=20, cleanup_reserved=30),
        prior_closed_diagnostic_seconds=212.19044355582446, review_measured_auxiliary_seconds=3.666822421,
        combined_diagnostic_review_V35_lower_seconds=212.19044355582446+3.666822421+total,
        historical_formal_lower_seconds=77161.55713859801,
        historical_plus_new_formal_lower_seconds=77161.55713859801+actor['elapsed_seconds'],
        complete_historical_auxiliary_setup_N1='UNKNOWN; do not double add lineage/campaign subsets',
        calendar_start=start, calendar_elapsed_seconds=time.monotonic()-start['start_monotonic'],
        child_cleanup=actor['descendants_cleared'], tree_peak_bytes=actor['sampled_process_tree_rss_peak_bytes'],
        own_swap_peak_bytes=actor['sampled_process_tree_swap_peak_bytes'], GPU_VRAM_bytes=0,
        memory_scope=actor['memory_scope'], cgroup_kernel_hard_limit='NOT_AVAILABLE; sampled 0.5s enforced stop',
        planning=result['capacity'], factor_A_LU_bytes=factor_bytes, pivot_bytes=72576,
        budget_counts=book['charged'], exact_consumption=checks['consumption'],
        nested_do_not_add=dict(launcher_seconds=book['runs'][0]['launch_wall_seconds'],
            worker_seconds=result['worker_wall_seconds'], cycle_seconds=final['cycle_inclusive_wall_seconds'],
            PC_inclusive_seconds=result['pc_inclusive_seconds'], factor_reload_seconds=reload_seconds,
            factor_solve_exclusive_seconds=solve_seconds, original_action_costs=result['action_costs_seconds'],
            fast_action_costs=result['fast_action_costs_seconds']),
        aux_runs=[dict(path=str(p), seconds=s['elapsed_seconds'], status=s['classification'],
            exit_code=s['leader_exit_code'], peak=s['sampled_process_tree_rss_peak_bytes'],
            swap=s['sampled_process_tree_swap_peak_bytes'], cleared=s['descendants_cleared']) for p,s in summaries],
        probes=[dict(path=str(p), **s) for p,s in probes],
        shared_workstation=True, neighbor_impact='INCONCLUSIVE; no sustained pressure observed, no matching throughput baseline',
        old_native_oracle_only_actions=45, all_original_fast_actions=834,
        formal_reference_and_field_cost='NOT_RUN; equation gate failed',
        metadata_only_read_write_seconds='not scientific actor; included in calendar; no fabricated exact full historical bill')
    write('resource_costs_v35.json', cost)
    target = dict(period_nm=[50,25], z_nm=[-10,130], wavelength_nm=0.7,
                  time_limit_seconds=172800, simultaneous_memory_limit_bytes=2000000000000)
    f = solve_seconds / actor['elapsed_seconds']
    bridge = dict(
        schema='task042.original-scale-bridge.v35', target=target,
        micro=dict(box_nm=[1.4,1.05,1.4], cells=384, h_nm=0.175, p=3, quadrature=15,
            trace_rows=18144, ports=40, volume_nm3=2.058, identity=result['operator_identity']),
        target_volume_nm3=175000, box_volume_ratio=175000/2.058, ratio_is_DoF_ratio=False,
        unknowns=['target exact Si/notch geometry tags','target mesh/h/p/q','target canonical/MPC inventory',
            'target complete port/reference plane inventory','target rhs/background/recover hash',
            'global coupling cost and iteration count','complete qualified N1 setup/solve/physics/IO'],
        material=dict(canonical=receipt(ROOT/'input/materials/si_optical_constants_v1.json'),
            table_id='SI_OPTICAL_CONSTANTS_USER_20260929_V1', source_wavelength='0.699999988', nominal_wavelength='0.7',
            n=[0.999885140474,0.00000432477054], epsilon=[0.9997702941220071,0.000008648547597811433],
            air_n=1, mu_r=1, convention='exp(-i omega t)', interpolation=False),
        seven_factor_A_LU_bytes=factor_bytes, simultaneous_capacity=result['capacity'],
        fixed_seven_formula=dict(memory='factor_A_LU_bytes*f^2 plus all simultaneous other objects',
            factorization='f^3', per_solve='f^2', f_target='UNKNOWN',
            memory_only_f_ceiling=math.sqrt(2000000000000/factor_bytes)),
        fixed_block_size_formula='32*sum(n_b^2)+pivot+packet+Krylov+global_coupling+port+recover/audit+IO',
        necessary_global_inverse_interface=dict(operator='A_OO-A_OJ*A_JJ^-1*A_JO',
            rhs='r_O-A_OJ*A_JJ^-1*r_J', outer_rows=14256,
            preserve=['canonical order','complex Floquet pullback','original cell contributions',
                'all40 Hhat closure, Hp distinct','affine internal recover','old original full residual/audit'],
            implemented_this_batch=False),
        NN_necessary_cost=dict(formula='f*(1-1/s)-C/T>=0.2 plus iteration change and exact audit',
            qualified_T='UNKNOWN', training_data_inference_C='UNKNOWN', iteration_change='UNKNOWN',
            failed_actor_proxy_solve_share=f,
            proxy_s_min_assuming_C0_same_iterations=f/(f-0.2), assumption_is_qualification=False,
            actor_peak_20_percent_bytes=0.2*actor['sampled_process_tree_rss_peak_bytes'],
            minimum_factor_payload_saving_fraction_if_no_replacement_memory=0.2*actor['sampled_process_tree_rss_peak_bytes']/factor_bytes),
        original_scale_qualification='NOT_QUALIFIED', neural20='NOT_DEMONSTRATED',
        no_new_mesh_PDE_training=True, next_only='matched periodic/hierarchical outer Schur interface and capacity qualification')
    write('original_scale_bridge_v35.json', bridge)
    write('dot_identity_increment_v35.json', dict(
        parent=receipt(OUT/'dot_identity_gap_v34.json'), previous_published=read(OUT/'dot_identity_gap_v34.json')['pinned_published_sha'],
        latest_read_only_ls_remote='5be1210aa79f25c13a7677cc291a4a766a548650',
        latest_object_local=False, latest_content_read=False, branch_mutated=False, factor_or_field_reads=0,
        changed_Task042_fields=dict(RHS='one cold original physical b, not two consumed diagnostic residuals',
            cost_basis='one actual online188.162088667s actor; qualified complete N1 remains unknown'),
        old14_differences_not_relabelled_as_latest=True, wait_dot_is_precondition=False))
    tests=[]
    for p in sorted(TMP.glob('aux_*/pytest.xml')):
        suite=ET.parse(p).getroot(); cases=list(suite.iter('testcase'))
        tests.append(dict(path=str(p), cases=len(cases), failed=sum(bool(list(c.iter('failure'))) for c in cases),
            case_names=[c.attrib.get('classname','')+'::'+c.attrib['name'] for c in cases], hash=receipt(p)))
    final_static_paths=sorted(TMP.glob('aux_docs_*/final_static_tests.json'))
    write('tests_v35.json', dict(raw_JUnit=tests, final_static=(read(final_static_paths[-1]) if final_static_paths else 'PENDING'),
        meaningful_unique_tests=len(set(n for s in tests for n in s['case_names'])),
        no_full_repository_suite=True, no_MPI_FE_GPU_tests_this_batch=True, CI='NOT_CLAIMED'))
    write('repairs_v35.json', dict(
        failures=[dict(source='30f2b682c5ff99610f6af250c66a3a78c9497b53',
            cause='fixture VERIFY before settling its own synthetic active actor', raw='aux_pre_001/pytest.stdout',
            repair_source='af0d3d3e7d2b05ab915902bbb66b6ddbd7ed912e', replay='aux_pre_002', real_actor_restarted=False),
            dict(cause='two12MiB storage reservations rejected before actual actor/reader/action',
                raw_stdout_original_not_persisted=True, terminal_exception='V35 new/cumulative storage cap / reserved output',
                no_zero_cost_claim=True, remedy='paid lossless archive and same cap, only one successful formal launch')],
        final_static_failure=dict(source='fe9d2c730e8e725d92228409b5caa7ac50d1b393',
            folder='aux_docs_003', no_actual_operator_calls=True,
            checker_previous_initialized=True, unused_new_FAMILY_import_removed=True,
            unrelated_legacy_F401_not_cleaned=True, final_Ruff_scope='new V35 files;23 dependency Python files still compiled'),
        metadata_corrections=receipt(OUT/'metadata_corrections_v35.json'),
        archive_manifests=[receipt(p) for p in sorted(TMP.glob('aux_*/archive_manifest.json'))],
        numeric_failure_not_a_bug=True, restarts=0, resource_reentries=0, ordinary_resource_waits=0))
    write('selective_manifest_v35.json', dict(groups=[
        dict(group='production numerical/core', changes='no production default change; explicit cached original Hp solve only',
             tests='original packet pair tests', fresh_FE='NOT_RUN', merge='NOT_APPROVED'),
        dict(group='reusable runner/watchdog', changes='new online window/paid probes/storage namespace, shared finish opt-in total hook',
             dependencies=['fixed PC','shared watchdog','atomic cycle writer'], evidence='actual one-run and final fixture tests', order=2),
        dict(group='checker/benchmark', changes='saved y/By/t/port/z and all consumption independently reconstructed; cache partition, metadata correction',
             dependencies=['raw final arrays','ledger','original gate definitions'], order=3),
        dict(group='compact evidence/docs', changes='response35/result/scale/cost/source/raw/tests plus prefix navigation and registries',
             dependencies=['numeric af0 source','checker6e source','final metadata source'], order=4),
        dict(group='research-only', changes='FullInputPC/arbitraryRHS seven-region study and explicit one-run inputs',
             dependencies=['V24 six outer factors','V26 J','old packet/class64/oracle'], order=1,
             mathematical_behavior='new fixed right PC, equation unchanged', production_qualification=False),
        dict(group='do-not-merge', changes='ignored factors, arrays, logs, bytecode/fixture archives; closed failed candidate as production default',
             merge_approval=False)], no_merge_this_round=True))
    lines=subprocess.check_output(['git','ls-tree','-r',REVIEW],cwd=ROOT,text=True).splitlines()
    protected=[]
    for line in lines:
        meta,name=line.split('\t',1)
        if (name in ('AGENTS.md','docs/AGENTS.md','docs/repository_work_principles.md')
                or name.startswith('docs/task042_neural_coarse_inverse/review_report_')
                or name.startswith('docs/task042_neural_coarse_inverse/response_')
                or name.startswith('docs/task042_neural_coarse_inverse/outcomes/records/')
                or name=='docs/task042_neural_coarse_inverse/task.md'):
            protected.append((name,meta.split()[2]))
    blobs=subprocess.check_output(['git','hash-object',*[p for p,_ in protected]],cwd=ROOT,text=True).splitlines()
    mismatches=[p for (p,expected),actual in zip(protected,blobs) if expected!=actual]
    if mismatches:raise ValueError('protected historical files changed: '+str(mismatches))
    prior=read(OUT/'review_v32_independent_checks.json')
    closed=[]
    for item in prior['closed_files_rehashed']:
        actual=receipt(item['path'])
        if actual['sha256']!=item['sha256']:raise ValueError('old closed ledger changed')
        closed.append(actual)
    write('delivery_integrity_v35.json', dict(review=REVIEW, protected_files=len(protected), protected_mismatches=mismatches,
        old_closed_verified=closed, old_campaign_reopened=False, current_ledger_closed=book['closed'],
        numeric_actor_cleanup=actor['descendants_cleared'], scope='byte hashes, not complete semantic audit',
        dot_other_branches_master_modified=False, no_subagents_no_reset_cards=True))
    prepend_navigation()
    render=[]
    newdocs=[TASK/'response_v35.md',TASK/'outcomes/online_full_input_qualification_v35.md',
             TASK/'outcomes/original_scale_bridge_v35.md',TASK/'review_report_v32.md']
    for path in newdocs:
        text=path.read_text(); tables=0; widths=[]; inside=False; errors=[]
        for number,line in enumerate(text.splitlines(),1):
            if line.startswith('```'):inside=not inside
            if not inside and line.startswith('|'):
                width=len(re.split(r'(?<!\\)\|',line))-2
                if widths and width!=widths[-1]:errors.append(number)
                widths.append(width)
            else:
                if widths:tables+=1; widths=[]
        if widths:tables+=1
        if inside or errors or '\n$$' in text or '\n\\[' in text:raise ValueError('Markdown table/math structure')
        render.append(dict(path=str(path),sha256=digest(text.encode()),tables=tables,math_blocks=text.count('```math'),
            local_table_fence_checks='PASSED'))
    write('render_check_v35.json', dict(local=render, GitHub_visual='NOT_VERIFIED',
        exact_review_URL='https://github.com/Rookie1234567/MyFEniCS/blob/'+REVIEW+'/docs/task042_neural_coarse_inverse/review_report_v32.md',
        web_result='Cache miss; no visual evidence', CI='NOT_CLAIMED'))
    # Preserve raw inputs in gzip; real arrays and factors remain ignored only.
    raw = [TMP/'start.json', TMP/'window.json', TMP/'ledger.json', TMP/'progress_journal.jsonl',
           TMP/'initial_host_processes.txt', TMP/'online_launch_003.stdout', TMP/'online_launch_003.stderr',
           TMP/'pre_qualification.json', Path(pointer['path']), artifact/'saved_residual_analysis.json',
           ROOT/'benchmarks/artifacts/task042/v35/independent_checker.json']
    raw += list(TMP.glob('probe_*.json')) + list(TMP.glob('formal_admission*.json'))
    raw += [p for p in run.iterdir() if p.is_file() and p.suffix in ('.json','.txt','.stdout','.stderr')]
    raw += [p for folder in TMP.glob('aux_*') for p in folder.rglob('*')
            if p.is_file() and 'fixtures' not in p.parts and p.suffix in ('.json','.jsonl','.stdout','.stderr','.xml','.log')]
    raw_entries=[]
    for p in sorted(set(raw)):
        if not p.is_file():continue
        data=p.read_bytes();name=f'raw_{digest(str(p.relative_to(ROOT)).encode())[:8]}_{digest(data)[:8]}_{p.name}_v35.gz'
        with (OUT/name).open('wb') as stream:
            with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as gz:gz.write(data)
        if gzip.decompress((OUT/name).read_bytes()) != data:raise ValueError('lossless raw gzip')
        raw_entries.append(dict(original=str(p), original_sha256=digest(data),
            original_bytes=len(data), stored=receipt(OUT/name)))
    archive=read(TMP/'aux_docs_002/archive_manifest.json')
    archived_resources=[]
    with tarfile.open(archive['archive'],'r:gz') as tar:
        for name in archive['members']:
            if name.endswith(('supervision/resources.jsonl','shared_health.jsonl')) and name.startswith('results/'):
                data=tar.extractfile(name).read()
                if digest(data)!=archive['members'][name]:raise ValueError('resource archive original hash')
                target_name='actor_'+Path(name).name+'_v35.gz'
                with (OUT/target_name).open('wb') as stream:
                    with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as gz:gz.write(data)
                archived_resources.append(dict(original=name, original_sha256=digest(data), stored=receipt(OUT/target_name)))
    write('raw_evidence_index_v35.json', dict(raw=raw_entries, archived_actor_resources=archived_resources,
        lossless_archives=[receipt(p) for p in TMP.glob('aux_*/archive_manifest.json')],
        large_payloads_ignored=True, prelaunch_reservation_failures_original_stderr='not persisted; terminal-only exceptions retained in repair record'))
    print(json.dumps(dict(status='PACKAGED',source=current,raw_files=len(raw_entries),actor_seconds=actor['elapsed_seconds'])))


if __name__ == '__main__':
    main()
