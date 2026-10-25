"""One authorized stdlib-only sanity; never execute probe top level or main."""
import ast
import hashlib
import json
import re
import sys
import time
import traceback
from pathlib import Path

OUT = Path('/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v9_resume_preparation/sanity_result.json')
PROBE = Path('/tmp/task43_v7_d3_proposal/probe_import_affinity.py')
CASES = [
    ('cpu1_success', '1234.001 sched_setaffinity(0, 128, [1]) = 0', [[1]], 0),
    ('non_cpu1_success', '1234.002 sched_setaffinity(27, 128, [3]) = 0', [[3]], 0),
    ('multi_cpu_success', '1234.003 sched_setaffinity(0, 128, [1 2]) = 0', [[1, 2]], 0),
    ('failed_call', '1234.004 sched_setaffinity(0, 128, [1]) = -1 EINVAL (Invalid argument)', [], 1),
    ('unfinished', '1234.005 sched_setaffinity(0, 128, [1] <unfinished ...>', [], 1),
    ('resumed', '1234.006 <... sched_setaffinity resumed>) = 0', [], 1),
    ('unknown_mask', '1234.007 sched_setaffinity(0, 128, [...]) = 0', [], 1),
    ('empty_mask', '1234.008 sched_setaffinity(0, 128, []) = 0', [], 1),
    ('pointer_mask', '1234.009 sched_setaffinity(0, 128, 0x1234) = 0', [], 1),
    ('stack_symbol', ' > /lib/libc.so.6(sched_setaffinity+0x12) [0x1234]', [], 0),
    ('unknown_token', 'unrecognized sched_setaffinity token', [], 1),
    ('non_setter', '1234.010 sched_getaffinity(0, 128, [1]) = 8', [], 0),
]
CHECKS = ['fixed_probe_identity', 'isolated_parser_extraction'] + [x[0] for x in CASES] + [
    'mixed_token_coverage', 'actual_pml_record_and_gate_order',
    'unknown_and_non_cpu1_vetoes', 'unchanged_other_functions', 'fixed_four_selectors',
]
result = {'kind': 'ONE_STDLIB_AST_SYNTHETIC_SANITY', 'checks': {x: 'NOT_RUN' for x in CHECKS},
          'samples': [{'name': x[0], 'line': x[1]} for x in CASES],
          'native_imports': False, 'probe_top_level_or_main_executed': False}

def save():
    OUT.write_text(json.dumps(result, indent=2) + '\n')

def check(name, ok, detail=None):
    result['checks'][name] = 'PASS' if ok else 'FAIL'
    if detail is not None:
        result.setdefault('details', {})[name] = detail
    save()
    if not ok:
        raise AssertionError(name)

def validate():
    data = PROBE.read_bytes()
    check('fixed_probe_identity', len(data) == 14891 and len(data.splitlines()) == 371 and
          hashlib.sha256(data).hexdigest() == 'fa0dea6e8e049134c77c68e356eb377afeabd6080246e11b2e6acf5fbad3e1d4')
    tree = ast.parse(data, filename=str(PROBE))
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    parser = functions['_successful_setters']
    check('isolated_parser_extraction', not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(parser)))
    scope = {'Path': Path, 're': re, 'json': json}
    exec(compile(ast.Module(body=[parser], type_ignores=[]), '<isolated setter parser>', 'exec'), scope)
    parse = scope['_successful_setters']
    for name, line, expected_masks, expected_unknown in CASES:
        found, unknown = parse([(Path('synthetic.17'), line)])
        masks = [json.loads(e['cpus']) for e in found]
        check(name, masks == expected_masks and len(unknown) == expected_unknown,
              {'masks': masks, 'unknown': unknown,
               'continuation_veto': bool(unknown) or any(m != [1] for m in masks)})
    found, unknown = parse([(Path('synthetic.17'), x[1]) for x in CASES])
    check('mixed_token_coverage', len(found) == 3 and len(unknown) == 7)
    snap = functions['_snapshot']
    record = next(n for n in ast.walk(snap) if isinstance(n, ast.Dict) and
                  any(isinstance(k, ast.Constant) and k.value == 'ompi_mca_pml' for k in n.keys))
    value = next(v for k, v in zip(record.keys, record.values) if isinstance(k, ast.Constant) and k.value == 'ompi_mca_pml')
    pml_gate = next(n for n in snap.body if isinstance(n, ast.If) and
                    ast.unparse(n.test) == "os.environ.get('OMPI_MCA_pml') != 'ob1'")
    append = next(n for n in snap.body if isinstance(n, ast.Expr) and
                  isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == '_append')
    first_return = pml_gate.body[0]
    pml_false = (isinstance(first_return, ast.Return) and isinstance(first_return.value, ast.Tuple)
                 and isinstance(first_return.value.elts[0], ast.Constant) and first_return.value.elts[0].value is False)
    check('actual_pml_record_and_gate_order', ast.unparse(value) == "os.environ.get('OMPI_MCA_pml')" and
          record.lineno < append.lineno < pml_gate.lineno and pml_false,
          {'record_line': record.lineno, 'append_line': append.lineno, 'gate_line': pml_gate.lineno})
    unknown_gate = next(n for n in snap.body if isinstance(n, ast.If) and ast.unparse(n.test) == 'unknown_setters')
    non_cpu_gate = next(n for n in snap.body if isinstance(n, ast.If) and
                       "json.loads(event['cpus']) != [1]" in ast.unparse(n.test))
    check('unknown_and_non_cpu1_vetoes', pml_gate.lineno < unknown_gate.lineno < non_cpu_gate.lineno and
          all(isinstance(n.body[0], ast.Return) and isinstance(n.body[0].value, ast.Tuple) and
              n.body[0].value.elts[0].value is False for n in [unknown_gate, non_cpu_gate]))
    old = Path('/home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/v7_affinity_driver_sources/d2/probe_import_affinity.py')
    old_functions = {n.name: n for n in ast.parse(old.read_bytes()).body if isinstance(n, ast.FunctionDef)}
    check('unchanged_other_functions', set(old_functions) == set(functions) and all(
          ast.dump(n) == ast.dump(old_functions[name]) for name, n in functions.items()
          if name not in {'_successful_setters', '_snapshot'}))
    nodes = next(n for n in tree.body if isinstance(n, ast.Assign) and
                 any(isinstance(t, ast.Name) and t.id == 'TARGETED_NODEIDS' for t in n.targets))
    expected = tuple('src/test/test_task43_v3_failure_safe_order.py::' + n for n in [
        'test_synthetic_joint_authority_fixture_passes_only_as_a_coherent_bundle',
        'test_synthetic_joint_authority_fixture_rejects_common_missing_identity',
        'test_synthetic_joint_authority_fixture_rejects_each_failure_independently',
        'test_a2_postprocess_writer_failures_keep_original_error_and_primary'])
    check('fixed_four_selectors', ast.literal_eval(nodes.value) == expected)

if __name__ == '__main__':
    started = time.monotonic()
    if OUT.exists():
        raise SystemExit('Refusing existing sanity result; no retry')
    save()
    code = 0
    try:
        validate()
        result['status'] = 'PASSED'
    except BaseException as exc:
        code = 1
        result.update(status='FAILED', exception=repr(exc), traceback=traceback.format_exc())
    result['elapsed_seconds'] = time.monotonic() - started
    result['exit_code'] = code
    save()
    print(json.dumps(result, indent=2), flush=True)
    sys.exit(code)
