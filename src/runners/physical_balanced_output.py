"""Posterior matched-reference checks, called only after solver-stack release."""
import hashlib
import json
from pathlib import Path

import numpy as np


def compare_balanced_output(fine, solution, outputs, directory, payload, *, marker, sample):
    from .physical_intermediate import _atomic_json
    if payload['derived']['physical_intermediate_profile'].get('native_capacity'):
        from .native_capacity_output import compare_wsl_observables
        return compare_wsl_observables(fine, outputs, directory, payload)
    if payload['geometry'].get('cell_notch'):
        return dict(status='REFERENCE_AUTHORITY_LIMITED',
                    reason='conditional notch direct reference requires separate capacity gate')
    from .actual_error_diagnosis import checked_json
    from .physical_diagnostic_completion import load_packet
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.physical_error_diagnostics import metric_square
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import recover_p0_outputs
    binding = json.loads(Path('input/task39extra/actual_error_evidence.json').read_text())
    audit = checked_json(binding['reference_audit'], binding['reference_audit_sha256'])
    hashes = {x['path']:x['sha256'] for x in audit['artifact_hashes']}
    source = Path(binding['reference_root'])/'reference_full_residual.json'
    checked_json(source, hashes[str(source)])
    ref = load_packet(source)
    if (ref['identity']['original_physical_sha256'] != payload['provenance']['physical_model_sha256'] or
            ref['identity']['mode_sha256'] != fine['mode_sha256']):
        raise ValueError('posterior reference physical/mode identity mismatch')
    if np.linalg.norm(ref['b']-ref['ax'])/np.linalg.norm(ref['b']) > 1e-10:
        raise ValueError('posterior reference raw residual gate failed')
    from src.solvers.condensed_fine_reference import native_map_arrays
    map_path=Path(binding['reference_root'])/'reference_native_map.json'
    checked_json(map_path,hashes[str(map_path)])
    reference_map=load_packet(map_path)
    current_map=native_map_arrays(fine['setup']['spaces'][6],fine['setup']['floquets'][6])
    if any(not np.array_equal(value,reference_map[key]) for key,value in current_map.items()):
        raise ValueError('posterior native map identity mismatch')
    marker('posterior_reference_started', {})
    sample()
    metric = LosslessFEMetric(fine['setup'], 6, fine['cfg'].k0, ref['quadrature'])
    try:
        indices = metric.mass.indices
        x = ref['x_ref'][indices]; delta = solution.array[indices]-x
        field_norms = {name:dict(absolute_error_norm=float(np.sqrt(metric_square(action,delta))),
                                reference_norm=float(np.sqrt(metric_square(action,x))))
                       for name,action in [('L2',metric.mass),('scaled_curl',metric.curl)]}
        field = {name:v['absolute_error_norm']/v['reference_norm'] for name,v in field_norms.items()}
    finally:
        metric.destroy()
    # One output recovery from the existing saved reference, never a refactor.
    cache = Path('benchmarks/artifacts/task39extra/v5_balanced/reference_output')
    manifest = cache/'binding.json'
    reference_hash = hashes[str(source)]
    output_identity = hashlib.sha256(json.dumps(payload['output'],sort_keys=True).encode()).hexdigest()
    if not manifest.exists():
        cache.mkdir(parents=True, exist_ok=False)
        vector = solution.duplicate()
        try:
            vector.array[:] = ref['x_ref']
            ref_output = recover_p0_outputs(fine, vector, cache, export_all_port_modes=True)
            files = {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in cache.iterdir() if f.is_file()}
            _atomic_json(manifest, dict(reference_sha256=reference_hash, output_identity_sha256=output_identity, outputs=ref_output, files=files))
        finally:
            vector.destroy()
    saved = json.loads(manifest.read_text())
    if saved['reference_sha256'] != reference_hash or saved.get('output_identity_sha256') != output_identity:
        raise ValueError('posterior reference output binding mismatch')
    for name,digest in saved['files'].items():
        if hashlib.sha256((cache/name).read_bytes()).hexdigest() != digest:
            raise ValueError('posterior reference output hash mismatch')
    comparisons = compare_modal_files(Path(directory)/'numerical_output', cache)
    comparisons.update(compare_power_totals(outputs,saved['outputs']))
    facts = dict(status='MATCHED_REFERENCE_PASS' if max(field.values()) <= 1e-4 and
                 comparisons['power_max_absolute_difference'] <= 1e-6 and
                 comparisons['amplitude_relative_difference'] <= 1e-4 and
                 max(comparisons['total_absolute_differences'].values()) <= 1e-5 else 'MATCHED_REFERENCE_FAIL',
                 field_relative=field, field_norms=field_norms, field_limit=1e-4, reference_sha256=reference_hash,
                 reference_output_binding=str(manifest), **comparisons)
    _atomic_json(Path(directory)/'matched_reference.json', facts)
    return facts


def compare_modal_files(current, reference):
    def key(row):
        return row['side'], row['m'], row['n'], row['polarization']
    def read(root, filename, orders=False):
        data = json.loads((root/filename).read_text())
        rows = data['orders'] if orders else data
        values = {key(x):x for x in rows}
        if len(values) != len(rows):
            raise ValueError('duplicate modal keys')
        return values
    a = read(current,'dtn_port_diffraction_orders_3d.json',True)
    b = read(reference,'dtn_port_diffraction_orders_3d.json',True)
    c = read(current,'dtn_auxiliary_amplitudes_3d.json')
    d = read(reference,'dtn_auxiliary_amplitudes_3d.json')
    if a.keys() != b.keys() or a.keys() != c.keys() or a.keys() != d.keys():
        raise ValueError('full observable mode inventory mismatch')
    def number(value):
        if isinstance(value,dict):
            return complex(value['real'],value['imag'])
        return complex(*value) if isinstance(value,list) else complex(value)
    keys = sorted(a)
    x = np.array([number(c[k]['outgoing_amplitude_at_boundary']) for k in keys])
    y = np.array([number(d[k]['outgoing_amplitude_at_boundary']) for k in keys])
    return dict(mode_count=len(keys), phase_fitting=False,amplitude_convention='outgoing_amplitude_at_boundary',
        power_max_absolute_difference=max(abs(a[k][v]-b[k][v]) for k in keys for v in ('R','T')),
        amplitude_relative_difference=float(np.linalg.norm(x-y)/max(np.linalg.norm(y),np.finfo(float).tiny)),
        power_limit=1e-6, amplitude_limit=1e-4)


def compare_selected_eh(reference_directory, current_directory):
    """Compare the existing bounded complex E/H carrier without phase fitting."""
    reference_directory = Path(reference_directory)
    current_directory = Path(current_directory)
    reference_archive = reference_directory / 'full3d_reference_samples.npz'
    current_archive = current_directory / 'full3d_reference_samples.npz'
    if not reference_archive.is_file() or not current_archive.is_file():
        raise ValueError('selected E/H reference archive is missing')
    with np.load(reference_archive) as reference, np.load(current_archive) as current:
        for key in ('x_nm', 'y_nm', 'z_nm'):
            if key not in reference or key not in current or not np.array_equal(reference[key], current[key]):
                raise ValueError(f'selected E/H coordinate identity mismatch: {key}')
        fields = {}
        passed = True
        for name in ('E_V_per_m', 'H_A_per_m'):
            if name not in reference or name not in current or reference[name].shape != current[name].shape:
                raise ValueError(f'selected E/H field identity mismatch: {name}')
            ref = np.asarray(reference[name], dtype=np.complex128)
            candidate = np.asarray(current[name], dtype=np.complex128)
            difference = np.abs(candidate - ref)
            ref_norm = float(np.linalg.norm(ref.ravel()))
            relative = float(np.linalg.norm((candidate - ref).ravel()) / ref_norm) if ref_norm > 0.0 else None
            scale = max(float(np.max(np.abs(ref))), 1.0e-30)
            near_zero = np.abs(ref) <= 1.0e-12 * scale
            near_zero_absolute = float(np.max(difference[near_zero])) if np.any(near_zero) else 0.0
            fields[name] = {
                'relative_l2_difference': relative,
                'absolute_max_difference': float(np.max(difference)),
                'near_zero_count': int(np.count_nonzero(near_zero)),
                'near_zero_absolute_max_difference': near_zero_absolute,
                'reference_l2_norm': ref_norm,
            }
            passed = passed and relative is not None and relative <= 1.0e-4
    return {
        'status': 'SELECTED_EH_PASS' if passed else 'SELECTED_EH_FAIL',
        'phase_fitting': False,
        'coordinate_identity': 'exact_array_match',
        'field_limit': 1.0e-4,
        'fields': fields,
        'reference_archive': str(reference_archive),
        'current_archive': str(current_archive),
    }


def compare_notch_reference(native, solution, witness, directory, *, native_opt_in=False):
    """After the conditional reference LU release, compare all saved outputs."""
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import recover_p0_outputs
    from src.solvers.fullspace_physical_intermediate_runtime import fine_volume_quadrature_metadata
    from src.solvers.physical_error_metric import LosslessFEMetric
    from src.solvers.physical_error_diagnostics import metric_square
    from .physical_intermediate import _atomic_json
    quadrature, _ = fine_volume_quadrature_metadata(native['setup'], native['cfg'])
    metric = LosslessFEMetric(native['setup'], 6, native['cfg'].k0, quadrature)
    try:
        x = solution.array[metric.mass.indices]
        delta = witness['control']['x']-x
        field_norms = {name:dict(absolute_error_norm=float(np.sqrt(metric_square(action,delta))),
                                reference_norm=float(np.sqrt(metric_square(action,x))))
                       for name,action in [('L2',metric.mass),('scaled_curl',metric.curl)]}
        field = {name:v['absolute_error_norm']/v['reference_norm'] for name,v in field_norms.items()}
    finally:
        metric.destroy()
    output = recover_p0_outputs(native, solution, Path(directory)/'numerical_output', export_all_port_modes=True)
    comparisons = compare_modal_files(Path(witness['directory'])/'numerical_output',Path(directory)/'numerical_output')
    candidate = json.loads((Path(witness['directory'])/'physical_intermediate_summary.json').read_text())['official_result']
    comparisons.update(compare_power_totals(candidate,output))
    selected_eh = None
    if native_opt_in:
        selected_eh = compare_selected_eh(Path(directory)/'numerical_output',
                                           Path(witness['directory'])/'numerical_output')
    selected_eh_pass = selected_eh is None or selected_eh['status'] == 'SELECTED_EH_PASS'
    facts = dict(status='MATCHED_REFERENCE_PASS' if max(field.values()) <= 1e-4 and
        comparisons['power_max_absolute_difference'] <= 1e-6 and
        comparisons['amplitude_relative_difference'] <= 1e-4 and
        max(comparisons['total_absolute_differences'].values()) <= 1e-5 and
        selected_eh_pass else 'MATCHED_REFERENCE_FAIL',
        field_relative=field, field_norms=field_norms, reference_output=output, **comparisons)
    if selected_eh is not None:
        facts['selected_eh'] = selected_eh
    _atomic_json(Path(directory)/'matched_reference.json',facts)
    return facts


def compare_power_totals(current, reference):
    def values(output):
        p=output['port_metrics']
        return dict(R=p['R_total'],T=p['T_total'],A=p['A_balance'],
                    A_volume=output['volume_metrics']['A_volume_total'])
    a,b=values(current),values(reference)
    return dict(total_absolute_differences={k:abs(a[k]-b[k]) for k in a},
                total_current=a,total_reference=b,total_absolute_limit=1e-5)


def _r13_pair_binding_errors(q4, q3):
    """Validate the two run identities before any FE post-processing."""
    errors = []
    expected = ((q4, "dual_condensed_balh_native_13p5_q4_v5", 4),
                (q3, "dual_condensed_balh_native_13p5_q3_v5", 3))
    for facts, profile, degree in expected:
        if facts.get("profile_identity") != profile:
            errors.append(f"wrong R13 profile for q{degree}")
        if facts.get("coarse_degree") != degree:
            errors.append(f"wrong coarse degree for q{degree}")
        for key in ("run_directory", "run_id", "source_sha", "input_sha256",
                    "physical_model_sha256", "mode_sha256"):
            if not facts.get(key):
                errors.append(f"q{degree} identity missing {key}")
        supervision = facts.get("supervision", {})
        if (supervision.get("classification") != "COMPLETED" or
                supervision.get("leader_exit_code") != 0 or
                supervision.get("descendants_cleared") is not True or
                supervision.get("remaining_child_pids") not in ([], None)):
            errors.append(f"q{degree} watchdog is not a clean completed run")
        if supervision.get("resource_stop_policy") != "measured_tree_rss_only_v3":
            errors.append(f"q{degree} did not use the V5 RSS-only watchdog")
        if supervision.get("rss_hard_limit_bytes") != 1_300_000_000_000:
            errors.append(f"q{degree} watchdog RSS Gate is not 1300000000000 bytes")
        peak = supervision.get("sampled_process_tree_rss_peak_bytes")
        if not isinstance(peak, int) or peak >= 1_300_000_000_000:
            errors.append(f"q{degree} watchdog RSS peak is missing or reaches the hard Gate")
        parent_identity = supervision.get("parent_identity", {})
        worker_identity = supervision.get("worker_identity", {})
        if (not isinstance(parent_identity.get("pid"), int) or
                not isinstance(parent_identity.get("start_ticks"), int) or
                parent_identity.get("pid", 0) <= 1 or parent_identity.get("start_ticks", 0) <= 0):
            errors.append(f"q{degree} watchdog parent identity is missing")
        if (not isinstance(worker_identity.get("pid"), int) or
                not isinstance(worker_identity.get("start_ticks"), int) or
                worker_identity.get("pid", 0) <= 1 or worker_identity.get("start_ticks", 0) <= 0 or
                worker_identity.get("pid") == parent_identity.get("pid")):
            errors.append(f"q{degree} worker PID/start_ticks identity is missing")
        if facts.get("runtime_fingerprint") is None:
            errors.append(f"q{degree} runtime fingerprint is missing")
        solution_identity = facts.get("native_solution_identity", {})
        for key in ("residual_arrays_sha256", "final_solution_sha256",
                    "operator_identity_sha256"):
            if not solution_identity.get(key):
                errors.append(f"q{degree} saved native solution identity missing {key}")
    for key in ("source_sha", "physical_model_sha256", "mode_sha256"):
        if q4.get(key) != q3.get(key):
            errors.append(f"q3/q4 {key} mismatch")
    if (q4.get("native_solution_identity", {}).get("operator_identity_sha256") !=
            q3.get("native_solution_identity", {}).get("operator_identity_sha256")):
        errors.append("q3/q4 operator identity mismatch")
    if q4.get("input_sha256") == q3.get("input_sha256"):
        errors.append("q3 and q4 input identities must be distinct")
    if q4.get("run_directory") == q3.get("run_directory"):
        errors.append("q3 and q4 must use distinct timestamped output directories")
    if (q4.get("runtime_fingerprint") is None or
            q4.get("runtime_fingerprint") != q3.get("runtime_fingerprint")):
        errors.append("q3/q4 runtime or ABI fingerprints differ")
    return errors


def _r13_source_identity_errors(manifest, watchdog):
    """Bind successful launcher and watchdog source snapshots to the run SHA."""
    expected = manifest.get("source_sha")
    errors = []
    for label, state in (
            ("launcher source_after", manifest.get("source_after")),
            ("watchdog source_state", watchdog.get("source_state"))):
        if not isinstance(state, dict):
            errors.append(f"{label} record is missing")
            continue
        if state.get("source_sha") != expected:
            errors.append(f"{label} SHA differs from the run source SHA")
        if state.get("tracked_and_nonignored_untracked_clean") is not True:
            errors.append(f"{label} is not recorded clean")
    return errors


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def _observer_pair_receipt(path, run_directory):
    """Read the existing observer's start identity; notification is diagnostic only."""
    path = Path(path).resolve()
    with path.open("rb") as stream:
        first = stream.readline(1024 * 1024 + 1)
    if len(first) > 1024 * 1024 or not first.endswith(b"\n"):
        raise ValueError(f"observer start record is missing or too large: {path}")
    started = json.loads(first)
    if (started.get("kind") != "observer_started" or
            Path(started.get("run_dir", "")).resolve() != Path(run_directory).resolve()):
        raise ValueError("observer start record is not bound to this run directory")

    identities = started.get("identities", {})
    parsed = {}
    for role in ("root", "worker"):
        item = identities.get(role)
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"observer start record lacks {role} PID/start_ticks")
        pid, ticks = item
        if (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1 or
                not isinstance(ticks, int) or isinstance(ticks, bool) or ticks <= 0):
            raise ValueError(f"observer start record has invalid {role} PID/start_ticks")
        parsed[role] = {"pid": pid, "start_ticks": ticks}
    if parsed["root"]["pid"] == parsed["worker"]["pid"]:
        raise ValueError("observer root and worker identities are not distinct")

    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            stream.seek(max(0, size - 64 * 1024))
            tail = stream.read(64 * 1024)
    except OSError:
        tail = b""
    rows = []
    for line in tail.splitlines():
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue  # The tail can start in the middle of the terminal evidence row.
        if isinstance(row, dict):
            rows.append(row)
    finished = next((row for row in reversed(rows)
                     if row.get("kind") == "observer_finished"), None)
    terminal_ack = any(row.get("kind") == "event_ack" and
                       row.get("event") == "run_terminal" for row in rows)
    return {
        "path": str(path),
        "run_directory": str(Path(run_directory).resolve()),
        "root": parsed["root"],
        "worker": parsed["worker"],
        "observer_started_record_sha256": hashlib.sha256(first).hexdigest(),
        "observer_finished_record_sha256": hashlib.sha256(
            _json_line_bytes(finished)
        ).hexdigest(),
        "observer_finished": bool(finished and finished.get("reason") == "terminal"),
        "terminal_notification_acknowledged": terminal_ack,
    }


def _json_line_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _canonical_key_inventory(directory, official, reconstructed_packets):
    """Verify saved packets against the existing FE exporter and hash their keys."""
    from itertools import zip_longest

    from benchmarks.canonical_vector_artifacts import _decode_canonical_packet_line

    descriptor = official.get("canonical_vector", {})
    filename = descriptor.get("filename")
    if not isinstance(filename, str) or not filename:
        raise ValueError("official output lacks the canonical FE packet filename")
    numerical = (Path(directory) / "numerical_output").resolve()
    path = (numerical / filename).resolve()
    if not path.is_relative_to(numerical) or not path.is_file():
        raise ValueError("canonical FE packet path is missing or outside numerical_output")
    expected_file_sha = descriptor.get("file_sha256")
    expected_count = descriptor.get("packet_count")
    file_digest = hashlib.sha256()
    key_digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        sentinel = object()
        for raw_line, reconstructed in zip_longest(stream, reconstructed_packets,
                                                   fillvalue=sentinel):
            if raw_line is sentinel or reconstructed is sentinel:
                raise ValueError("saved canonical packet count differs from native-map reconstruction")
            file_digest.update(raw_line)
            packet, key_bytes = _decode_canonical_packet_line(raw_line)
            value = complex(packet[1])
            if reconstructed[0] != packet[0] or complex(reconstructed[1]) != value:
                raise ValueError("saved solution does not reproduce its canonical FE packet")
            if not np.isfinite([value.real, value.imag]).all():
                raise ValueError("canonical FE packet contains a non-finite value")
            key_digest.update(len(key_bytes).to_bytes(8, "little"))
            key_digest.update(key_bytes)
            count += 1
    if file_digest.hexdigest() != expected_file_sha or count != expected_count:
        raise ValueError("canonical FE packet file hash/count differs from official manifest")
    return {
        "filename": filename,
        "file_sha256": expected_file_sha,
        "packet_count": count,
        "ordered_key_inventory_sha256": key_digest.hexdigest(),
    }


def _load_r13_pair_run(directory, expected_q, observer_log):
    """Read one completed V5 R13 run and bind its saved numerical evidence."""
    from src.io.input_validation import load_and_resolve
    from src.io.native_capacity_profile import native_profile_facts

    directory = Path(directory).resolve()
    manifest_path = directory / "run_manifest.json"
    resolved_path = directory / "resolved_config.json"
    input_path = directory / "input_original.dat"
    summary_path = directory / "physical_intermediate_summary.json"
    checker_path = directory / "checker.json"
    watchdog_path = directory / "watchdog" / "summary.json"
    residual_path = directory / "final_residual_arrays.npz"
    required = (manifest_path, resolved_path, input_path, summary_path,
                checker_path, watchdog_path, residual_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"R13 run evidence is missing: {missing}")

    manifest = _read_json(manifest_path)
    resolved = _read_json(resolved_path)
    summary = _read_json(summary_path)
    checker = _read_json(checker_path)
    watchdog = _read_json(watchdog_path)
    specification = load_and_resolve(input_path)
    profile = str(specification.solver.get("preconditioner", ""))
    expected_profile = f"dual_condensed_balh_native_13p5_q{expected_q}_v5"
    input_sha = _sha256_file(input_path)
    resolved_sha = _sha256_file(resolved_path)
    if profile != expected_profile:
        raise ValueError(f"{directory.name} input is not the expected {expected_profile}")
    if Path(manifest.get("output_directory", "")).resolve() != directory:
        raise ValueError(f"{directory.name} manifest output_directory mismatch")
    specification_snapshot = specification.as_jsonable()
    if (manifest.get("run_id") != specification_snapshot.get("run_id") or
            summary.get("source_sha") != manifest.get("source_sha")):
        raise ValueError(f"{directory.name} model run/source identity mismatch")
    if manifest.get("input_sha256") != input_sha or specification.input_sha256 != input_sha:
        raise ValueError(f"{directory.name} input SHA identity mismatch")
    if manifest.get("physical_model_sha256") != specification.physical_model_sha256:
        raise ValueError(f"{directory.name} physical identity mismatch")
    if manifest.get("resolved_config_sha256") != resolved_sha:
        raise ValueError(f"{directory.name} resolved-config hash mismatch")
    resolved_provenance = resolved.get("provenance", {})
    if (resolved_provenance.get("input_sha256") != input_sha or
            resolved_provenance.get("physical_model_sha256") != specification.physical_model_sha256):
        raise ValueError(f"{directory.name} resolved-config provenance mismatch")
    if (summary.get("provenance", {}).get("input_sha256") != input_sha or
            summary.get("provenance", {}).get("physical_model_sha256") != specification.physical_model_sha256):
        raise ValueError(f"{directory.name} worker summary provenance mismatch")
    if int(specification.solver.get("coarse_degree", -1)) != expected_q:
        raise ValueError(f"{directory.name} resolved coarse degree mismatch")

    profile_facts = native_profile_facts(profile)
    resources = profile_facts["resources"]
    screen = profile_facts["outer"]["screen"]
    if (resources["workflow_seconds"] is not None or resources["solve_seconds"] is not None or
            screen.get("progress_only") is not True or screen.get("stop_on_screen") is not False):
        raise ValueError(f"{directory.name} current V5 profile contract is not the approved no-deadline contract")

    if (not isinstance(checker, dict) or
            checker.get("independent_output_gates_passed") is not True or
            checker.get("gate_failures") != [] or
            checker.get("classification") not in ("BALANCED_OUTPUT_AUTHORITY_LIMITED", "BALANCED_OUTPUT_PASS")):
        raise ValueError(f"{directory.name} independent output checker did not pass")
    matched = summary.get("matched_reference", {})
    compact = matched.get("source_compact_comparison", {})
    if (matched.get("status") != "REFERENCE_AUTHORITY_LIMITED" or
            compact.get("status") != "SOURCE_COMPACT_OBSERVABLES_PASS" or
            compact.get("profile_q") != f"q{expected_q}"):
        raise ValueError(f"{directory.name} q-specific source compact comparison did not pass")
    official = summary.get("official_result")
    if not isinstance(official, dict) or official.get("port_metrics", {}).get("dtn_port_mode_count") != 80:
        raise ValueError(f"{directory.name} does not contain exactly 80 DtN modes")

    if (manifest.get("status") != "finished" or manifest.get("exit_status") != 0 or
            manifest.get("result_classification") != "worker_exit0"):
        raise ValueError(f"{directory.name} launcher terminal/source result is not successful")
    source_errors = _r13_source_identity_errors(manifest, watchdog)
    if source_errors:
        raise ValueError(f"{directory.name} launcher/watchdog source identity is invalid: "
                         + "; ".join(source_errors))
    if (watchdog.get("classification") != "COMPLETED" or
            watchdog.get("leader_exit_code") != 0 or
            watchdog.get("descendants_cleared") is not True or
            watchdog.get("remaining_child_pids") != [] or
            watchdog.get("resource_stop_policy") != "measured_tree_rss_only_v3" or
            watchdog.get("rss_hard_limit_bytes") != 1_300_000_000_000 or
            watchdog.get("time_limit_mode") != "none" or
            watchdog.get("workflow_deadline_seconds") is not None or
            watchdog.get("solve_deadline_seconds") is not None):
        raise ValueError(f"{directory.name} parent watchdog did not complete under the approved contract")
    rss_peak = watchdog.get("sampled_process_tree_rss_peak_bytes")
    samples = watchdog.get("samples")
    if (not isinstance(rss_peak, int) or rss_peak >= 1_300_000_000_000 or
            not isinstance(samples, int) or isinstance(samples, bool) or samples <= 0):
        raise ValueError(f"{directory.name} watchdog RSS/sample-count evidence is incomplete or over the Gate")
    resource_rows_path = directory / "watchdog" / "resources.jsonl"
    if not resource_rows_path.is_file() or resource_rows_path.stat().st_size <= 0:
        raise ValueError(f"{directory.name} watchdog resource detail log is missing")
    observer = _observer_pair_receipt(observer_log, directory)

    isolation = manifest.get("native_capacity_isolation", {})
    worker_cpu = isolation.get("worker_affinity")
    parent_cpu = isolation.get("supervisor_affinity")
    memory_policy = isolation.get("worker_memory_policy", {})
    if (parent_cpu != [9] or worker_cpu != [24] or
            isolation.get("native_memory_policy") != "preferred_node1" or
            memory_policy.get("mode") != "preferred" or
            memory_policy.get("preferred_node") != 1 or
            memory_policy.get("fallback") != "allowed_mems"):
        raise ValueError(f"{directory.name} launch identity does not record CPU9/CPU24/preferred-node1")

    abi = summary.get("abi", {})
    threads = abi.get("threads", {})
    if (abi.get("integer") != "int64" or abi.get("scalar") != "complex128" or
            abi.get("python") != manifest.get("environment", {}).get("python_executable") or
            not all(threads.get(key) == "1" for key in
                    ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"))):
        raise ValueError(f"{directory.name} runtime ABI/thread identity is not qualified")
    if int(specification.execution.get("mpi_size", -1)) != 1:
        raise ValueError(f"{directory.name} is not MPI1")
    command = manifest.get("worker_command")
    if not isinstance(command, list):
        raise TypeError(f"{directory.name} worker command lacks CPU24/preferred-node1")
    taskset_index = next((index for index, token in enumerate(command)
                          if Path(str(token)).name == "taskset"), None)
    numactl_index = next((index for index, token in enumerate(command)
                          if Path(str(token)).name == "numactl"), None)
    mpi_index = next((index for index, token in enumerate(command)
                      if Path(str(token)).name in {"mpiexec", "mpirun"}), None)
    if (taskset_index is None or command[taskset_index + 1:taskset_index + 3] != ["-c", "24"] or
            numactl_index is None or "--preferred=1" not in command[numactl_index + 1:] or
            mpi_index is None or command[mpi_index + 1:mpi_index + 3] != ["-n", "1"] or
            "src.runners.task038_input_worker" not in command):
        raise ValueError(f"{directory.name} worker command differs from CPU24/MPI1/preferred1 contract")
    command_contract = {
        "taskset_cpu": 24,
        "numactl_policy": "--preferred=1",
        "mpi_size": 1,
        "worker_module": "src.runners.task038_input_worker",
    }
    if not manifest.get("environment", {}).get("native_qualified_activation"):
        raise ValueError(f"{directory.name} lacks native qualified activation identity")
    expected_execution = profile_facts.get("native_execution", {})
    if (expected_execution.get("supervisor_cpu") != 9 or
            expected_execution.get("worker_cpu") != 24 or
            expected_execution.get("mpi_size") != 1 or
            expected_execution.get("math_threads") != 1 or
            expected_execution.get("native_memory_policy") != "preferred_node1" or
            specification.execution.get("native_memory_policy") != "preferred_node1"):
        raise ValueError(f"{directory.name} resolved profile execution contract differs")

    raw_facts = summary.get("residual_arrays", {})
    raw_name = raw_facts.get("filename")
    if raw_name != residual_path.name:
        raise ValueError(f"{directory.name} residual-array filename differs from the V5 contract")
    operator_identity = raw_facts.get("operator_identity_sha256")
    residual_sha = _sha256_file(residual_path)
    if (not isinstance(operator_identity, str) or len(operator_identity) != 64 or
            residual_sha != raw_facts.get("sha256") or
            raw_facts.get("input_sha256") != input_sha or
            raw_facts.get("physical_model_sha256") != specification.physical_model_sha256):
        raise ValueError(f"{directory.name} residual-array artifact identity/hash mismatch")
    solution_sha = summary.get("final_solution_sha256")
    with np.load(residual_path, allow_pickle=False) as arrays:
        if not {"rhs", "action", "solution"}.issubset(arrays.files):
            raise ValueError(f"{directory.name} residual archive lacks rhs/action/solution")
        solution = np.asarray(arrays["solution"], dtype=np.complex128)
        if (solution.ndim != 1 or not np.isfinite(solution).all() or
                hashlib.sha256(solution.tobytes()).hexdigest() != solution_sha):
            raise ValueError(f"{directory.name} final solution hash/finite check failed")
        solution_shape = [int(item) for item in solution.shape]
    space_identity = summary.get("retained_runtime", {}).get("space_identity", {})
    if space_identity.get("fine_mode_sha256") != summary.get("mode_sha256"):
        raise ValueError(f"{directory.name} p6 space/mode identity mismatch")
    if space_identity.get("fine_global_rows") != solution_shape[0]:
        raise ValueError(f"{directory.name} saved solution rows differ from the recorded p6 space")
    canonical_descriptor = official.get("canonical_vector", {})
    canonical_name = canonical_descriptor.get("filename")
    if not isinstance(canonical_name, str) or not canonical_name:
        raise ValueError(f"{directory.name} official canonical-vector identity is missing")

    mode_sha = summary.get("mode_sha256")
    retained = summary.get("retained_runtime", {})
    if not mode_sha or retained.get("mode_sha256") != mode_sha:
        raise ValueError(f"{directory.name} retained mode identity mismatch")
    return {
        "directory": directory,
        "run_directory": str(directory),
        "profile_identity": profile,
        "coarse_degree": expected_q,
        "run_id": manifest["run_id"],
        "source_sha": manifest["source_sha"],
        "input_sha256": input_sha,
        "physical_model_sha256": specification.physical_model_sha256,
        "mode_sha256": mode_sha,
        "specification": specification,
        "summary": summary,
        "official": official,
        "checker": checker,
        "watchdog": watchdog,
        "observer": observer,
        "canonical_descriptor": canonical_descriptor,
        "native_solution_identity": {
            "residual_arrays_sha256": residual_sha,
            "final_solution_sha256": solution_sha,
            "solution_shape": solution_shape,
            "fine_global_rows": space_identity["fine_global_rows"],
            "operator_identity_sha256": operator_identity,
        },
        "runtime_fingerprint": {
            "interpreter": {
                "environment_python": manifest["environment"].get("python_executable"),
                "abi_python": abi.get("python"),
                "platform": manifest["environment"].get("platform"),
                "native_activation": manifest["environment"].get("native_qualified_activation"),
            },
            "libraries": {
                key: abi.get(key) for key in
                ("scalar", "integer", "petsc_version", "mpi_version", "module_paths")
            },
            "math_threads": dict(threads),
            "mpi_size": int(specification.execution["mpi_size"]),
            "worker_command_contract": command_contract,
            "cpu_numa_contract": {
                "supervisor_affinity": parent_cpu,
                "worker_affinity": worker_cpu,
                "memory_policy": isolation["native_memory_policy"],
                "worker_memory_policy": memory_policy,
            },
            "resource_contract": {
                "policy": watchdog["resource_stop_policy"],
                "rss_hard_limit_bytes": watchdog["rss_hard_limit_bytes"],
                "workflow_deadline_seconds": watchdog["workflow_deadline_seconds"],
                "solve_deadline_seconds": watchdog["solve_deadline_seconds"],
            },
        },
        "supervision": {
            "classification": watchdog["classification"],
            "leader_exit_code": watchdog["leader_exit_code"],
            "descendants_cleared": watchdog["descendants_cleared"],
            "remaining_child_pids": watchdog["remaining_child_pids"],
            "resource_stop_policy": watchdog["resource_stop_policy"],
            "rss_hard_limit_bytes": watchdog["rss_hard_limit_bytes"],
            "sampled_process_tree_rss_peak_bytes": rss_peak,
            "sample_count": samples,
            "resources_jsonl": str(resource_rows_path),
            "parent_identity": observer["root"],
            "worker_identity": observer["worker"],
            "observer_receipt": observer,
            "watchdog_summary_sha256": _sha256_file(watchdog_path),
        },
        "artifact_hashes": {
            "run_manifest.json": _sha256_file(manifest_path),
            "resolved_config.json": resolved_sha,
            "input_original.dat": input_sha,
            "physical_intermediate_summary.json": _sha256_file(summary_path),
            "checker.json": _sha256_file(checker_path),
            "final_residual_arrays.npz": residual_sha,
            "canonical_vector": canonical_descriptor.get("file_sha256"),
            "full3d_reference_samples.npz": _sha256_file(directory / "numerical_output" / "full3d_reference_samples.npz"),
            "dtn_port_diffraction_orders_3d.json": _sha256_file(directory / "numerical_output" / "dtn_port_diffraction_orders_3d.json"),
            "dtn_auxiliary_amplitudes_3d.json": _sha256_file(directory / "numerical_output" / "dtn_auxiliary_amplitudes_3d.json"),
        },
    }


def compare_r13_pair(q4_directory, q3_directory, *, q4_observer_log, q3_observer_log):
    """Compare completed R13 q4/q3 outputs and emit release-ready facts.

    This is a read-only post-run route: it never launches a solver or modifies
    either run directory.  The CLI writes the returned small record separately.
    """
    try:
        q4 = _load_r13_pair_run(q4_directory, 4, q4_observer_log)
        q3 = _load_r13_pair_run(q3_directory, 3, q3_observer_log)
    except Exception as exc:
        return {"status": "PAIR_EVIDENCE_INVALID",
                "release_status": "PENDING_NUMERICAL_AND_EXTERNAL_QUALIFICATION",
                "gate_failures": [f"run evidence invalid: {type(exc).__name__}: {exc}"]}
    q4_binding = {key: q4[key] for key in (
        "profile_identity", "coarse_degree", "run_directory", "run_id", "source_sha",
        "input_sha256", "physical_model_sha256", "mode_sha256", "runtime_fingerprint",
        "native_solution_identity", "supervision")}
    q3_binding = {key: q3[key] for key in (
        "profile_identity", "coarse_degree", "run_directory", "run_id", "source_sha",
        "input_sha256", "physical_model_sha256", "mode_sha256", "runtime_fingerprint",
        "native_solution_identity", "supervision")}
    errors = _r13_pair_binding_errors(q4_binding, q3_binding)
    if errors:
        return {"status": "PAIR_EVIDENCE_INVALID",
                "release_status": "PENDING_NUMERICAL_AND_EXTERNAL_QUALIFICATION",
                "gate_failures": errors}
    if q4["canonical_mapping_identity"]["ordered_key_inventory_sha256"] != \
            q3["canonical_mapping_identity"]["ordered_key_inventory_sha256"]:
        return {"status": "PAIR_EVIDENCE_INVALID",
                "release_status": "PENDING_NUMERICAL_AND_EXTERNAL_QUALIFICATION",
                "gate_failures": ["q3/q4 canonical FE key inventories differ"]}

    try:
        from dolfinx import fem
        from mpi4py import MPI
        from src.io.input_validation import simulation_config_3d_from_normalized
        from src.solvers.condensed_fine_reference import native_map_arrays
        from src.solvers.fullspace_physical_intermediate_runtime import (
            fine_volume_quadrature_metadata,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
            _build_same_mesh_levels,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            restore_p0_full_field,
        )
        from src.solvers.hcurl_canonical_vector_dolfinx import (
            iter_canonical_full_fe_packets,
        )
        from src.solvers.physical_error_diagnostics import metric_square
        from src.solvers.physical_error_metric import LosslessFEMetric

        levels_by_q = {}
        cfg_by_q = {
            4: simulation_config_3d_from_normalized(q4["specification"].as_jsonable()),
            3: simulation_config_3d_from_normalized(q3["specification"].as_jsonable()),
        }
        metric = None
        try:
            for degree in (4, 3):
                cfg = cfg_by_q[degree]
                levels_by_q[degree] = _build_same_mesh_levels(
                    cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=False
                )
            maps = {
                degree: native_map_arrays(
                    levels_by_q[degree]["spaces"][6],
                    levels_by_q[degree]["floquets"][6],
                )
                for degree in (4, 3)
            }
            if set(maps[4]) != set(maps[3]) or any(
                    not np.array_equal(maps[4][name], maps[3][name]) for name in maps[4]):
                raise ValueError("q3/q4 actual p6 native maps differ")
            map_digests = {}
            for degree in (4, 3):
                digest = hashlib.sha256()
                for name in sorted(maps[degree]):
                    value = np.ascontiguousarray(maps[degree][name])
                    digest.update(name.encode("utf-8") + b"\0")
                    digest.update(str(value.dtype).encode("ascii") + b"\0")
                    digest.update(np.asarray(value.shape, dtype=np.int64).tobytes())
                    digest.update(value.tobytes())
                map_digests[degree] = digest.hexdigest()

            solutions = {}
            for degree, run in ((4, q4), (3, q3)):
                with np.load(run["directory"] / "final_residual_arrays.npz",
                             allow_pickle=False) as arrays:
                    solutions[degree] = np.array(arrays["solution"],
                                                 dtype=np.complex128, copy=True)
                space = levels_by_q[degree]["spaces"][6]
                index_map = space.dofmap.index_map
                storage_size = int(index_map.size_local + index_map.num_ghosts) * int(
                    space.dofmap.index_map_bs
                )
                if solutions[degree].shape != (storage_size,):
                    raise ValueError(f"q{degree} saved solution length differs from its actual p6 DOF map")
                independent = np.asarray(maps[degree]["independent_indices"], dtype=np.int64)
                slaves = np.setdiff1d(np.arange(storage_size, dtype=np.int64),
                                      independent, assume_unique=True)
                if np.any(solutions[degree][slaves] != 0.0):
                    raise ValueError(f"q{degree} saved solution violates the actual exact-zero slave map")
                field = restore_p0_full_field(
                    levels_by_q[degree]["floquets"][6], solutions[degree],
                    name=f"R13_q{degree}_recovered",
                )
                try:
                    reconstructed_packets = iter_canonical_full_fe_packets(
                        space, field, levels_by_q[degree]["floquets"][6]
                    )
                    run["canonical_mapping_identity"] = _canonical_key_inventory(
                        run["directory"], run["summary"]["official_result"],
                        reconstructed_packets,
                    )
                finally:
                    del field
                if degree == 3:
                    # Keep only copied native-map arrays and canonical facts
                    # while the q4 metric remains live.
                    levels_by_q.pop(3).clear()
                    space = None

            if (q4["canonical_mapping_identity"]["ordered_key_inventory_sha256"] !=
                    q3["canonical_mapping_identity"]["ordered_key_inventory_sha256"]):
                raise ValueError("q3/q4 canonical FE key inventories differ")

            quadrature, quadrature_records = fine_volume_quadrature_metadata(
                levels_by_q[4], cfg_by_q[4]
            )
            metric = LosslessFEMetric(levels_by_q[4], 6, cfg_by_q[4].k0, quadrature)
            q4_solution = solutions[4]
            q3_solution = solutions[3]
            if q4_solution.shape != q3_solution.shape:
                raise ValueError("q3/q4 full p6 storage solution shapes differ")
            expected_size = (metric.space.dofmap.index_map.size_local +
                                 metric.space.dofmap.index_map.num_ghosts) * metric.space.dofmap.index_map_bs
            if q4_solution.shape != (expected_size,):
                raise ValueError("saved solution is not the reconstructed full p6 storage vector")
            if not np.isfinite(q4_solution).all() or not np.isfinite(q3_solution).all():
                raise ValueError("saved q3/q4 solution contains non-finite values")
            native_map = maps[4]
            indices = np.asarray(native_map["independent_indices"], dtype=np.int64)
            if not np.array_equal(indices, np.asarray(metric.mass.indices, dtype=np.int64)):
                raise ValueError("native canonical map and FE metric use different p6 independent rows")
            slave = np.setdiff1d(np.arange(expected_size, dtype=np.int64), indices, assume_unique=True)
            if (np.any(q4_solution[slave] != 0) or np.any(q3_solution[slave] != 0)):
                raise ValueError("saved full-space solution violates exact zero-slave convention")
            ref = q4_solution[indices]
            candidate = q3_solution[indices]
            delta = candidate - ref
            field = {}
            for name, action in (("L2", metric.mass), ("scaled_curl", metric.curl)):
                error_norm = float(np.sqrt(metric_square(action, delta)))
                reference_norm = float(np.sqrt(metric_square(action, ref)))
                if not np.isfinite(reference_norm) or reference_norm <= 0:
                    raise ValueError(f"q4 reference {name} norm is not positive finite")
                relative = error_norm / reference_norm
                field[name] = {
                    "relative_difference": relative,
                    "absolute_error_norm": error_norm,
                    "q4_reference_norm": reference_norm,
                    "limit": 1e-4,
                    "passed": bool(np.isfinite(relative) and relative <= 1e-4),
                }
        finally:
            if metric is not None:
                metric.destroy()
                metric = None
            # The task's pinned dolfinx_mpc MultiPointConstraint has no
            # destroy() method.  Its C++ wrapper is owned by the Python MPC;
            # drop metric/level owners only after metric actions are destroyed.
            for levels in levels_by_q.values():
                levels.clear()
            levels_by_q.clear()

        selected_eh = compare_selected_eh(
            q4["directory"] / "numerical_output", q3["directory"] / "numerical_output")
        modal = compare_modal_files(
            q3["directory"] / "numerical_output", q4["directory"] / "numerical_output")
        totals = compare_power_totals(q3["official"], q4["official"])
        if modal["mode_count"] != 80:
            raise ValueError(f"R13 q3/q4 modal inventory is {modal['mode_count']}, expected 80")
        if selected_eh["status"] != "SELECTED_EH_PASS":
            errors.append("selected E/H comparison failed")
        if modal["amplitude_relative_difference"] > 1e-4:
            errors.append("80-channel complex-amplitude relative difference exceeds 1e-4")
        if modal["power_max_absolute_difference"] > 1e-6:
            errors.append("80-channel per-mode power difference exceeds 1e-6")
        if any(value > 1e-5 for value in totals["total_absolute_differences"].values()):
            errors.append("R/T/A/A_volume difference exceeds 1e-5")
        if any(not row["passed"] for row in field.values()):
            errors.append("full-field FE L2/scaled-curl difference exceeds 1e-4")
        numerical_pass = not errors
        return {
            "status": "NUMERICAL_PAIR_PASS" if numerical_pass else "NUMERICAL_PAIR_FAIL",
            "release_status": (
                "PENDING_COMMON_PATH_AND_SUSTAINED_HARDWARE_REVIEW"
                if numerical_pass else "BLOCKED_NUMERICAL_PAIR"
            ),
            "automatic_r13_release": False,
            "gate_failures": errors,
            "phase_fitting": False,
            "mode_count": modal["mode_count"],
            "field_comparison": {
                "metric": "LosslessFEMetric; q3/q4 canonical packet keys prove identical saved p6 map",
                "quadrature_records": quadrature_records,
                "fields": field,
                "native_map_sha256": {f"q{degree}": map_digests[degree]
                                      for degree in (4, 3)},
                "native_map_independent_rows_sha256": hashlib.sha256(
                    np.asarray(indices, dtype=np.int64).tobytes()
                ).hexdigest(),
                "canonical_key_inventory_sha256": q4["canonical_mapping_identity"][
                    "ordered_key_inventory_sha256"
                ],
            },
            "selected_eh": selected_eh,
            "all_80_modal_comparison": modal,
            "rta_comparison": totals,
            "runs": {
                "q4": {key: q4[key] for key in (
                    "profile_identity", "coarse_degree", "run_id", "source_sha", "input_sha256",
                    "run_directory", "physical_model_sha256", "mode_sha256", "supervision",
                    "native_solution_identity", "canonical_mapping_identity", "artifact_hashes")},
                "q3": {key: q3[key] for key in (
                    "profile_identity", "coarse_degree", "run_id", "source_sha", "input_sha256",
                    "run_directory", "physical_model_sha256", "mode_sha256", "supervision",
                    "native_solution_identity", "canonical_mapping_identity", "artifact_hashes")},
                "runtime_fingerprint_sha256": hashlib.sha256(json.dumps(
                    q4["runtime_fingerprint"], sort_keys=True, separators=(",", ":"),
                    allow_nan=False).encode("utf-8")).hexdigest(),
            },
        }
    except Exception as exc:
        return {"status": "PAIR_COMPARISON_INVALID",
                "release_status": "PENDING_NUMERICAL_AND_EXTERNAL_QUALIFICATION",
                "gate_failures": [f"pair comparison invalid: {type(exc).__name__}: {exc}"],
                "runs": {"q4": q4_binding, "q3": q3_binding}}


def compare_retained_5nm_output(outputs, current_directory, *, fine=None, solution=None):
    """Compare the V20 retained route with the tracked old 5 nm output.

    This deliberately uses the existing full modal/E-H/RTA comparison
    helpers.  It never calls the short-wave ``compare_wsl_observables`` path.
    """

    root = Path(__file__).resolve().parents[2]
    reference = root / (
        'results/euv_grazing1_phi0/'
        'original_5nm_si_p6h4_balanced_h6_p4_native__full3d_iterative__mpi1__Mna/'
        '20260911T065955.813489Z'
    )
    current_directory = Path(current_directory)
    summary_path = reference / 'physical_intermediate_summary.json'
    if not summary_path.is_file():
        return {
            'status': 'REFERENCE_AUTHORITY_LIMITED',
            'reason': 'tracked old 5 nm reference summary is unavailable',
            'reference_directory': str(reference),
        }
    try:
        old_summary = json.loads(summary_path.read_text())
        reference_output = old_summary.get('official_result')
        if reference_output is None:
            raise ValueError('old 5 nm official output is unavailable')
        modal = compare_modal_files(current_directory, reference / 'numerical_output')
        if modal['mode_count'] != 600:
            raise ValueError(f"expected 600 modal channels, got {modal['mode_count']}")
        selected_eh = compare_selected_eh(reference / 'numerical_output', current_directory)
        power = compare_power_totals(outputs, reference_output)
        if fine is None or solution is None:
            raise ValueError('full-field witness or current solution is unavailable')
        witness_audit_path = reference / 'notch_reference_witness.json'
        witness_audit = json.loads(witness_audit_path.read_text())
        witness_path = Path(witness_audit['arrays']['path'])
        if not witness_path.is_absolute():
            witness_path = reference / witness_path
        witness_sha = witness_audit['arrays']['sha256']
        if hashlib.sha256(witness_path.read_bytes()).hexdigest() != witness_sha:
            raise ValueError('full-field witness hash mismatch')
        from src.solvers.condensed_fine_reference import native_map_arrays
        from src.solvers.fullspace_physical_intermediate_runtime import (
            fine_volume_quadrature_metadata,
        )
        from src.solvers.physical_error_diagnostics import metric_square
        from src.solvers.physical_error_metric import LosslessFEMetric
        with np.load(witness_path, allow_pickle=False) as witness:
            mapping = native_map_arrays(
                fine['setup']['spaces'][6], fine['setup']['floquets'][6]
            )
            for name, descriptor in witness_audit['map'].items():
                if not np.array_equal(mapping[name], witness[descriptor['array_key']]):
                    raise ValueError(f'full-field native map mismatch: {name}')
            reference_field = np.asarray(
                witness[witness_audit['control']['x']['array_key']],
                dtype=np.complex128,
            )
            current_field = np.asarray(
                solution.getValues(mapping['independent_indices']),
                dtype=np.complex128,
            )
            if current_field.shape != reference_field.shape:
                raise ValueError('full-field independent storage shape mismatch')
            quadrature, _ = fine_volume_quadrature_metadata(fine['setup'], fine['cfg'])
            metric = LosslessFEMetric(fine['setup'], 6, fine['cfg'].k0, quadrature)
            try:
                delta = current_field - reference_field
                field_norms = {}
                for name, action in (('L2', metric.mass), ('scaled_curl', metric.curl)):
                    error_norm = float(np.sqrt(metric_square(action, delta)))
                    reference_norm = float(np.sqrt(metric_square(action, reference_field)))
                    field_norms[name] = {
                        'absolute_error_norm': error_norm,
                        'reference_norm': reference_norm,
                        'relative': error_norm / max(reference_norm, np.finfo(float).tiny),
                    }
            finally:
                metric.destroy()
        full_field = {
            'status': 'FULL_FIELD_PASS' if max(
                item['relative'] for item in field_norms.values()
            ) <= 1e-4 else 'FULL_FIELD_FAIL',
            'phase_fitting': False,
            'field_limit': 1e-4,
            'fields': field_norms,
            'witness_sha256': witness_sha,
            'witness_audit': str(witness_audit_path),
            'native_map_identity': 'exact_array_match',
        }
        passed = (
            full_field['status'] == 'FULL_FIELD_PASS'
            and modal['mode_count'] == 600
            and selected_eh['status'] == 'SELECTED_EH_PASS'
            and modal['amplitude_relative_difference'] <= modal['amplitude_limit']
            and modal['power_max_absolute_difference'] <= modal['power_limit']
            and max(power['total_absolute_differences'].values()) <= power['total_absolute_limit']
        )
        return {
            'status': 'MATCHED_REFERENCE_PASS' if passed else 'MATCHED_REFERENCE_FAIL',
            'reference_kind': 'old_5nm_same_physics_full_field_and_600_modal',
            'reference_directory': str(reference),
            'phase_fitting': False,
            'full_field': full_field,
            'modal': modal,
            'selected_eh': selected_eh,
            'power': power,
        }
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return {
            'status': 'REFERENCE_AUTHORITY_LIMITED',
            'reason': f'old 5 nm comparison unavailable: {type(exc).__name__}: {exc}',
            'reference_directory': str(reference),
        }


def compare_retained_v5_output(
    profile_identity,
    outputs,
    current_directory,
    *,
    fine=None,
    solution=None,
    current_run_identity=None,
):
    """Apply the reference policy for the specific V5 wavelength/coarse case."""

    from src.io.native_capacity_profile import (
        V5_EXPECTED_MODE_COUNTS,
        V5_R13_PROFILES,
    )

    expected_modes = V5_EXPECTED_MODE_COUNTS.get(profile_identity)
    if expected_modes is None:
        raise ValueError(f"unknown V5 output profile: {profile_identity}")
    if profile_identity == "dual_condensed_balh_native_5nm_v5":
        return compare_retained_5nm_output(
            outputs, current_directory, fine=fine, solution=solution
        )
    if profile_identity in V5_R13_PROFILES:
        root = Path(__file__).resolve().parents[2]
        compact_path = root / (
            "docs/task39extra_para_workstation_capacity/outcomes/records/"
            "v5_r13_source_compact_observations_v1.json"
        )
        q_name = "q3" if "_q3_" in profile_identity else "q4"
        try:
            compact_bytes = compact_path.read_bytes()
            source = json.loads(compact_bytes)
            if source.get("source_commit") != "55ceb4c84a9041f715dc0c34c72fca689e753cce":
                raise ValueError("R13 source compact commit identity mismatch")
            reference = source[q_name]
            reference_values = reference["official_observations"]
            port = outputs["port_metrics"]
            volume = outputs["volume_metrics"]
            values = {
                "R_total": float(port["R_total"]),
                "T_total": float(port["T_total"]),
                "A_balance": float(port["A_balance"]),
                "R00_s": float(port["R00_s"]),
                "R00_p": float(port["R00_p"]),
                "R00_total": float(port["R00_total"]),
            }
            if "A_volume_total" in reference_values:
                values["A_volume_total"] = float(volume["A_volume_total"])
            limits = source["reference_limits"]
            comparisons = {}
            for key, current in values.items():
                target = float(reference_values[key])
                difference = abs(current - target)
                limit_key = (
                    "zero_order_power_absolute"
                    if key in {"R00_s", "R00_p", "R00_total"}
                    else "aggregate_power_absolute"
                )
                limit = float(limits[limit_key])
                comparisons[key] = {
                    "current": current,
                    "source_compact": target,
                    "absolute_difference": difference,
                    "limit": limit,
                    "passed": bool(np.isfinite(difference) and difference <= limit),
                }
            compact_pass = all(item["passed"] for item in comparisons.values())
            return {
                "status": (
                    "REFERENCE_AUTHORITY_LIMITED"
                    if compact_pass
                    else "MATCHED_REFERENCE_FAIL"
                ),
                "reason": (
                    "available source compact observables match; full source arrays are absent"
                    if compact_pass
                    else "available source compact observable mismatch"
                ),
                "reference_kind": "R13_q_specific_compact_observables",
                "source_compact_comparison": {
                    "status": "SOURCE_COMPACT_OBSERVABLES_PASS" if compact_pass else "FAIL",
                    "profile_q": q_name,
                    "observable_scope": "R/T/A/A_volume_and_zero_order_R00_s_p_total",
                    "source_commit": source["source_commit"],
                    "source_record_path": reference["record_path"],
                    "source_record_blob": reference["record_blob"],
                    "source_record_sha256": reference["record_sha256"],
                    "source_input_sha256": reference["input_sha256"],
                    "source_run_id": reference["run_id"],
                    "compact_file_sha256": hashlib.sha256(compact_bytes).hexdigest(),
                    "current_run_identity": dict(current_run_identity or {}),
                    "comparisons": comparisons,
                    "zero_order_power_limit": float(
                        limits["zero_order_power_absolute"]
                    ),
                    "aggregate_power_limit": float(
                        limits["aggregate_power_absolute"]
                    ),
                    "phase_fitting": False,
                    "missing_authority": [
                        "full source E/H field arrays",
                        "per-channel source complex amplitudes and powers",
                    ],
                },
                "expected_mode_count": expected_modes,
                "phase_fitting": False,
                "pair_gate": "PENDING_R13_PAIR_RELEASE",
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            return {
                "status": "REFERENCE_EVIDENCE_INVALID",
                "reason": f"R13 compact reference evidence invalid: {type(exc).__name__}: {exc}",
                "reference_kind": "R13_q_specific_compact_observables",
                "expected_mode_count": expected_modes,
                "current_run_identity": dict(current_run_identity or {}),
            }
    if profile_identity == "dual_condensed_balh_native_2nm_v5":
        return {
            "status": "REFERENCE_AUTHORITY_LIMITED",
            "reason": "no matched legacy full-field reference is contracted for F2",
            "reference_kind": "no_legacy_full_field_reference",
            "expected_mode_count": expected_modes,
            "phase_fitting": False,
        }
    raise ValueError(f"V5 reference policy is undefined for {profile_identity}")
