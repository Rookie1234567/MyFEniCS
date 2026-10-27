"""V16 saved-only launcher routing, without a service or numerical process."""
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("conflict", [None, "--task41-p0-b0-v15-full-acceptance", "--task41-p0-saved-b0-v16-vector-analysis"])
def test_v16_shell_requires_saved_contract_and_rejects_other_route(tmp_path, conflict):
    root = Path(__file__).resolve().parents[2]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    captured = tmp_path / "launch"
    calls = tmp_path / "validation"
    python = fake_bin / "python3"
    python.write_text(
        '#!/bin/bash\nset -eu\n'
        'printf "%s\\n" "$*" >> "$CALLS"\n'
        '[[ " $* " == *" --saved-output-continuation "* ]] || exit 19\n'
        'printf "%s\\n" "$ROOT" /fixture/runtime /fixture/abi /fixture/jit '
        'contract /fixture/window window 1610612736 67108864 0 unused source\n'
    )
    python.chmod(0o755)
    systemd = fake_bin / "systemd-run"
    systemd.write_text('#!/bin/bash\nprintf "%s\\0" "$@" > "$CAPTURE"\n')
    systemd.chmod(0o755)
    env = dict(os.environ, PATH=f"{fake_bin}:{os.environ['PATH']}", ROOT=str(root), CALLS=str(calls), CAPTURE=str(captured))
    command = ["bash", str(root / "scripts/run_case_in_user_service.sh"), "fixture.dat",
               "--task41-p0-execution-contract", str(tmp_path / "contract.json"),
               "--task41-p0-saved-b0-v16-vector-analysis"]
    if conflict:
        command.append(conflict)
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if conflict:
        assert result.returncode == 2, result.stderr
        assert not captured.exists()
        assert not calls.exists()
    else:
        assert result.returncode == 0, result.stderr
        args = captured.read_bytes().decode().split("\0")
        assert "--property=MemorySwapMax=0" in args
        assert "--property=MemoryMax=1610612736" in args
        assert "--task41-p0-saved-b0-v16-vector-analysis" in args
        # Validate the separate service-side argument parser reaches saved-contract
        # validation too; stop before activation or any actual process.
        shell_code = next(a for a in args if "task41_saved_output_continuation=0" in a)
        marker = "unset _MYFENICS_WSL_QUALIFIED_ACTIVATION"
        assert marker in shell_code
        shell_code = shell_code.split(marker, 1)[0] + '\nexit 0\n'
        inner = subprocess.run(["bash", "-c", shell_code, "task41-p0", str(root), "fixture",
                                str(tmp_path / "contract.json"), *command[2:]],
                               env=env, capture_output=True, text=True)
        assert inner.returncode == 0, inner.stderr
        assert len(calls.read_text().splitlines()) == 2


def test_v16_pending_metadata_reaches_supervised_route_without_loading_numpy(tmp_path):
    """Execute the actual service collector on a minimal, hash-bound file inventory."""
    import ast
    import hashlib
    import json
    import re
    from typing import Any, Mapping
    from types import SimpleNamespace

    root = Path(__file__).resolve().parents[2]
    source = (root / 'scripts/task40_v20_service_workflow.py').read_text()
    module = ast.parse(source)
    service = next(n for n in module.body if isinstance(n, ast.FunctionDef)
                   and n.name == '_run_task41_p0_saved_output_service')
    collector = next(n for n in service.body if isinstance(n, ast.FunctionDef)
                     and n.name == 'collect_v16_saved_vector_inputs')
    scope = tmp_path / 'results' / 'fixture'
    scope.mkdir(parents=True)
    def record(name, content):
        path = scope / name
        path.write_bytes(content)
        return dict(path=str(path), bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    report = record('report.json', json.dumps(dict(existing_evidence_bytes=1,
                    prior_new_evidence_bytes=2, new_evidence_bytes=3)).encode())
    # Deliberately not a valid NPY: this preflight is stat-only for arrays.
    arr = record('source.npy', b'not loaded at service preflight')
    active = dict(arr, dtype='<i8', shape=[5688000])
    manifest = dict(schema='task41.p0.b0.v16.saved_vector_manifest.v1', rows=5752120,
                    trace_rows=5688000, columns=[0, 1], metadata_pending=True,
                    producer_reports={k:report for k in (
                        'v9_audit', 'v15_audit', 'v15_checkpoint', 'v15_checker',
                        'v9_run_manifest', 'v15_run_manifest', 'v15_candidate_summary')},
                    arrays={k:[dict(arr), dict(arr)] for k in ('y9','g9','y15','g15')},
                    metadata_source=dict(active_original_rows=active,
                        active_original_rows_file_sha256=active['sha256'],
                        active_original_rows_values_sha256='a'*64))
    manifest_path = scope / 'input.json'
    def bind():
        manifest_path.write_text(json.dumps(manifest))
        ns['v16_manifest_sha256'] = digest(manifest_path)
    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    ns = dict(Path=Path, Any=Any, Mapping=Mapping, re=re,
              repo_root=tmp_path, contract={'case':{'model_id':'fixture'}},
              contract_path=Path(report['path']), input_path=Path(report['path']),
              window=SimpleNamespace(path=report['path']),
              v16_manifest_path=manifest_path, sha256_file=digest,
              read_json_object=lambda path,label:json.loads(Path(path).read_text()))
    exec(compile(ast.Module(body=[collector], type_ignores=[]), '<actual-service-collector>', 'exec'), ns)
    bind()
    paths, cumulative = ns['collect_v16_saved_vector_inputs']()
    assert cumulative == 6 and Path(arr['path']) in paths
    manifest['row_group_codes'] = {'fake':'completed'}
    bind()
    with pytest.raises(ValueError, match='must not claim'):
        ns['collect_v16_saved_vector_inputs']()
    manifest.pop('row_group_codes')
    manifest['metadata_source']['active_original_rows_file_sha256'] = 'b'*64
    bind()
    with pytest.raises(ValueError, match='identity or layout'):
        ns['collect_v16_saved_vector_inputs']()
    manifest['metadata_source']['active_original_rows_file_sha256'] = active['sha256']
    manifest['producer_reports']['v15_audit'] = dict(report, sha256='c'*64)
    bind()
    with pytest.raises(ValueError, match='SHA-256 differs'):
        ns['collect_v16_saved_vector_inputs']()


def test_v16_analysis_uses_numeric_cutoff_not_closeout_allowance():
    import ast
    root = Path(__file__).resolve().parents[2]
    module = ast.parse((root / 'scripts/task40_v20_service_workflow.py').read_text())
    service = next(n for n in module.body if isinstance(n, ast.FunctionDef)
                   and n.name == '_run_task41_p0_saved_output_service')
    calls = [n for n in ast.walk(service) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == 'supervise']
    call = next(n for n in calls if any(k.arg == 'wall_seconds' and
                isinstance(k.value, ast.IfExp) and isinstance(k.value.test, ast.Name)
                and k.value.test.id == 'b0_v16_saved_vector_analysis_mode' for k in n.keywords))
    from types import SimpleNamespace
    window = SimpleNamespace(cutoff_seconds=20400, closeout_seconds=1200)
    for mode in (True, False):
        ns = dict(window=window, b0_v16_saved_vector_analysis_mode=mode,
                  checker_authorization={'old':'closeout'})
        values = {k.arg:eval(compile(ast.Expression(k.value), '<watchdog-args>', 'eval'), ns)
                  for k in call.keywords if k.arg in ('wall_seconds','campaign_phase','campaign_phase_authorization')}
        assert values['wall_seconds'] == (20400 if mode else 1200)
        assert values['campaign_phase'] == ('numeric' if mode else 'closeout')
        assert values['campaign_phase_authorization'] == (None if mode else {'old':'closeout'})


def test_v16_saved_contract_uses_diagnostic_strategy_and_selector_first(tmp_path):
    """Exercise actual dispatcher and scope guard with the prepared V16 contract shape."""
    import ast
    root = Path(__file__).resolve().parents[2]
    module = ast.parse((root / 'scripts/task40_v20_service_workflow.py').read_text())
    service = next(n for n in module.body if isinstance(n, ast.FunctionDef)
                   and n.name == '_run_task41_p0_service')
    assignments = [n for n in service.body if isinstance(n, ast.Assign)]
    names = ('is_v16_saved_vector_analysis', 'saved_scope')
    scope_nodes = [n for n in assignments if any(isinstance(t, ast.Name) and t.id in names
                                               for t in n.targets)]
    matching = [n for n in service.body if isinstance(n, ast.If)
                and any(isinstance(x, ast.Name) and x.id == 'is_v16_saved_vector_analysis'
                        for x in ast.walk(n.test))]
    guard = next(n for n in service.body if isinstance(n, ast.If)
                 and isinstance(n.test, ast.BoolOp)
                 and any(isinstance(x, ast.Name) and x.id == 'saved_scope'
                         for x in ast.walk(n.test))
                 and any(isinstance(x, ast.Name) and x.id == 'b0_v16_saved_vector_analysis_mode'
                         for x in ast.walk(n.test)))
    scope = {'kind':'saved_vector_diagnostics_only'}
    window = Path('window-v16.json')
    ns = dict(repo_root=tmp_path, case_id='B0', contract={'execution_scope':scope},
              contract_window=tmp_path/window,
              strategy={'schema':'task41.p0.b0.internal_rhs_strategy.v1',
                        'internal_rhs_strategy':'same_lu_rhs_solve'},
              TASK41_B0_V16_SAVED_VECTOR_SCOPE=scope,
              TASK41_B0_V16_SAVED_VECTOR_WINDOW_RELATIVE=window,
              b0_v16_saved_vector_analysis_mode=True,
              **{name:False for name in ('b0_v9_failed_terminal_audit_mode',
                  'b0_saved_y_g_comparison_mode','b0_v14_saved_rhs_candidate_mode',
                  'v15_full_acceptance_selector','b0_v8_selected_trace_star_metadata_only_mode',
                  'b0_v8_selected_trace_star_candidate_replay_mode',
                  'b0_v11_candidate_report_replayed_read_only_mode')})
    code = compile(ast.Module(body=[scope_nodes[0], *matching, scope_nodes[1], guard],
                              type_ignores=[]), '<actual-v16-scope>', 'exec')
    exec(code, ns)
    assert ns['is_v16_saved_vector_analysis'] is True
    ns['strategy'] = {'schema':'wrong'}
    with pytest.raises(ValueError, match='exact fixed contract'):
        exec(code, ns)
    # Saved routes use selector first; the DAT is taken from the bound contract.
    dispatcher = next(n for n in module.body if isinstance(n, ast.FunctionDef)
                      and n.name == 'run_service')
    captured = {}
    def extract(args, option):
        index = args.index(option)
        return args[:index] + args[index+2:], Path(args[index+1])
    def target(**kwargs):
        captured.update(kwargs)
        return 0
    dispatch_ns = dict(Path=Path, ROOT=tmp_path, _extract_v29_path_arg=extract,
                       _run_task41_p0_service=target)
    exec(compile(ast.Module(body=[dispatcher], type_ignores=[]), '<actual-dispatch>', 'exec'), dispatch_ns)
    selector = '--task41-p0-saved-b0-v16-vector-analysis'
    args = [selector, '--manifest', '/saved/input.json', '--manifest-sha256', 'a'*64,
            '--output-dir', '/saved/attempt02', '--task41-p0-execution-contract', '/contract.json']
    assert dispatch_ns['run_service'](unit='fixture', runtime_prefix=tmp_path,
        abi_receipt=tmp_path, jit_cache=tmp_path, case_args=args, repo_root=tmp_path) == 0
    assert captured['case_args'][0] == selector
