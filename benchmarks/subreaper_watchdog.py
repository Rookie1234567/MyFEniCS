"""Linux whole-workflow watchdog, including orphaned compiler/MPI children.

Run this as a dedicated parent process. Subreaping keeps descendants inside
its tree after intermediate parents exit, including children that call setsid.
The existing process-tree sampler includes this parent in the memory scope.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Any, Mapping

from benchmarks.task034_wsl_resources import (
    cgroup_snapshot,
    current_cgroup_path,
    vmstat_swap_pages,
    wsl_memory_snapshot,
)
from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
from src.runners.workflow_timebase import (TimebaseInconsistency, budget_elapsed,
    clock_info, clock_sample, ClockBudget, STRICT, POLICY_VERSION)
from src.runners.physical_v14_budget import (
    V14_TIME_POLICY_ENFORCE,
    normalize_v14_time_policy,
    v14_time_gate_facts,
    v14_time_policy_facts,
)

LEGACY_MEMORY_POLICY = "LEGACY_STATIC_MEMORY_ENVELOPE"
PHYSICAL_MEMORY_PRESSURE_POLICY = "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23"
PHYSICAL_MEMORY_EVIDENCE_RESERVE_BYTES = 128 * 1024**2
CAMPAIGN_CLOSEOUT_PARENT_FLUSH_RESERVE_SECONDS = 30.0


def _sha256_file(path: str | Path, *, chunk_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_bytes), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_task41_consumer_source(contract: dict[str, Any], environment: dict[str, str]) -> bool:
    continuation = environment.get('TASK41_P0_SAVED_OUTPUT_CONTINUATION')
    consumer_sha = environment.get('TASK41_P0_CONSUMER_SOURCE_SHA')
    if continuation != '1':
        if consumer_sha is not None:
            raise ValueError('Task41 consumer source identity requires saved-output continuation mode')
        return False
    head = subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=Path.cwd(), check=True, capture_output=True, text=True
    ).stdout.strip()
    branch = subprocess.run(
        ['git', 'branch', '--show-current'], cwd=Path.cwd(), check=True, capture_output=True, text=True
    ).stdout.strip()
    status = subprocess.run(
        ['git', 'status', '--porcelain', '--untracked-files=normal'],
        cwd=Path.cwd(), check=True, capture_output=True, text=True
    ).stdout
    if environment.get('TASK41_P0_SAVED_B0_EVIDENCE_AUDIT') == '1':
        if (
            not re.fullmatch(r'[0-9a-f]{40}', str(consumer_sha or ''))
            or environment.get('TASK41_P0_CHECKER_SOURCE_SHA') != head
            or consumer_sha != head
            or head != contract.get('source', {}).get('sha')
            or branch != contract.get('branch')
            or status.strip()
        ):
            raise ValueError('Task41 B0 saved audit requires the clean current consumer/checker source')
        return True
    checker_only = environment.get('TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY') == '1'
    if checker_only:
        if not re.fullmatch(r'[0-9a-f]{40}', str(consumer_sha or '')):
            raise ValueError('Task41 saved consumer source SHA is invalid')
        ancestry = subprocess.run(
            ['git', 'merge-base', '--is-ancestor', str(consumer_sha), head],
            cwd=Path.cwd(), check=False, capture_output=True, text=True
        )
        if (
            environment.get('TASK41_P0_CHECKER_SOURCE_SHA') != head
            or consumer_sha == contract.get('source', {}).get('sha')
            or ancestry.returncode != 0
            or branch != contract.get('branch')
            or status.strip()
        ):
            raise ValueError('Task41 checker source must be clean and descend from the saved consumer source')
        return True
    if (
        not re.fullmatch(r'[0-9a-f]{40}', str(consumer_sha or ''))
        or head != consumer_sha
        or branch != contract.get('branch')
        or status.strip()
    ):
        raise ValueError('Task41 continuation consumer source is not the clean contracted branch head')
    return True


def _validate_campaign_closeout_authorization(
    *,
    command: list[str],
    campaign: Any,
    authorization: dict[str, Any] | None,
    worker_environment: dict[str, str] | None,
) -> dict[str, Any]:
    """Fail closed unless the command is the exact registered read-only checker."""
    if not isinstance(authorization, dict):
        raise ValueError('closeout phase requires an explicit checker authorization')
    schema = authorization.get('schema')
    if schema == 'task40extra.review_v31_closeout_checker_authorization.v1':
        contract_version = 30
        contract_key = 'v30_contract_sha256'
    elif schema == 'task40extra.review_v31_closeout_checker_authorization.v2':
        contract_version = 31
        contract_key = 'v31_contract_sha256'
    elif schema == 'task41.p0.closeout_checker_authorization.v1':
        contract_version = 41
        contract_key = 'task41_contract_sha256'
    else:
        raise ValueError('closeout checker authorization schema is not registered')
    required = {
        'schema', 'phase', 'purpose', 'checker_kind', 'command_sha256',
        'input_paths', 'input_sha256s', 'expected_channel_count',
        'campaign_window_sha256', contract_key, 'source_sha',
        'source_branch', 'source_clean',
    }
    if set(authorization) != required:
        raise ValueError('closeout checker authorization has an open or incomplete schema')
    argv = [str(value) for value in command]
    command_sha = hashlib.sha256(
        json.dumps(argv, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    ).hexdigest()
    contract_sha = authorization.get(contract_key)
    if (
        authorization.get('phase') != 'closeout'
        or authorization.get('purpose') != 'registered_read_only_required_checker'
        or authorization.get('command_sha256') != command_sha
        or authorization.get('campaign_window_sha256') != campaign.sha256
        or not re.fullmatch(r'[0-9a-f]{64}', str(contract_sha or ''))
        or not re.fullmatch(r'[0-9a-f]{40}', str(authorization.get('source_sha', '')))
        or not isinstance(authorization.get('source_branch'), str)
        or not authorization.get('source_branch')
        or authorization.get('source_clean') is not True
    ):
        raise ValueError('closeout checker authorization differs from its command/window/source')
    environment = dict(worker_environment or os.environ)
    if contract_version == 41:
        if (
            environment.get('TASK41_P0_STRICT_EXECUTION') != '1'
            or environment.get('TASK41_P0_CONTRACT_SHA256') != contract_sha
        ):
            raise ValueError('closeout checker is not bound to the Task41 P0 execution contract')
        contract_path = environment.get('TASK41_P0_CONTRACT_PATH')
        if not contract_path:
            raise ValueError('Task41 closeout authorization omits the contract path')
        from src.runners.task41_p0_contract import require_task41_p0_contract

        continuation_flag = environment.get('TASK41_P0_SAVED_OUTPUT_CONTINUATION')
        continuation = continuation_flag == '1'
        b0_evidence_audit = environment.get('TASK41_P0_SAVED_B0_EVIDENCE_AUDIT') == '1'
        if continuation_flag not in {None, '1'} or (
            continuation != (environment.get('TASK41_P0_CONSUMER_SOURCE_SHA') is not None)
        ) or (b0_evidence_audit and not continuation):
            raise ValueError('Task41 continuation source markers are incomplete')
        contract, actual_contract_sha = require_task41_p0_contract(
            contract_path,
            expected_sha256=str(contract_sha),
            current_root=Path.cwd(),
            check_current_source=(not continuation or b0_evidence_audit),
            require_clean_source=True,
        )
        if continuation:
            _validate_task41_consumer_source(contract, environment)
        window_path = contract['window']['path']
        window_sha = contract['window']['sha256']
    elif contract_version == 30:
        if (
            environment.get('TASK40_V30_STRICT_EXECUTION') != '1'
            or environment.get('TASK40_V30_CONTRACT_SHA256') != contract_sha
        ):
            raise ValueError('closeout checker is not bound to the V30 registered execution contract')
        contract_path = environment.get('TASK40_V30_CONTRACT_PATH')
        if not contract_path:
            raise ValueError('closeout checker authorization omits the V30 contract path')
        from src.runners.task40_v30_contract import require_authorized_contract

        contract, actual_contract_sha = require_authorized_contract(
            contract_path, expected_sha256=str(contract_sha), current_root=Path.cwd()
        )
        window_path = contract['execution']['campaign_window_path']
        window_sha = contract['execution']['campaign_window_sha256']
    else:
        if (
            environment.get('TASK40_V31_STRICT_EXECUTION') != '1'
            or environment.get('TASK40_V31_CONTRACT_SHA256') != contract_sha
        ):
            raise ValueError('closeout checker is not bound to the V31 registered execution contract')
        contract_path = environment.get('TASK40_V31_CONTRACT_PATH')
        if not contract_path:
            raise ValueError('closeout checker authorization omits the V31 contract path')
        from src.runners.task40_v31_contract import require_v31_execution_contract

        contract, actual_contract_sha = require_v31_execution_contract(
            contract_path, expected_sha256=str(contract_sha), current_root=Path.cwd()
        )
        window = contract['execution']['window']
        window_path = window['window_path']
        window_sha = window['window_sha256']
    if (
        actual_contract_sha != contract_sha
        or Path(str(window_path)).resolve() != campaign.path.resolve()
        or window_sha != campaign.sha256
    ):
        raise ValueError(f'closeout checker contract points at a different V{contract_version} campaign window')
    contract_file = Path(str(contract_path)).resolve(strict=True)

    if len(argv) < 3 or Path(argv[0]).resolve() != Path(sys.executable).resolve():
        raise ValueError('closeout checker must use the supervisor qualified interpreter')
    checker_kind = authorization.get('checker_kind')
    if checker_kind == 'task40_v10_independent_output_checker':
        if (
            len(argv) != 6
            or argv[1:3] != ['-m', 'src.runners.task40_v10_output_checker']
            or argv[4] != '--expected-channel-count'
            or not argv[5].isdigit()
            or int(argv[5]) <= 0
            or authorization.get('expected_channel_count') != int(argv[5])
            or Path(argv[3]).name != 'v10_candidate_official_output.json'
        ):
            raise ValueError('closeout command is not a supported official output checker')
        packet_path = Path(argv[3]).resolve()
        if not packet_path.is_relative_to(Path.cwd().resolve()):
            raise ValueError('official output packet escaped the registered repository')
        input_paths = [str(packet_path)]
    elif checker_kind == 'task40_v20_partial_receipt_checker':
        if (
            len(argv) != 15
            or Path(argv[1]).resolve()
            != (Path.cwd() / 'scripts/task40_v20_service_workflow.py').resolve()
            or argv[2] != 'check-partial'
            or argv[3::2]
            != ['--input', '--summary', '--manifest', '--numerical-output', '--stop-stage', '--output']
            or argv[12] != 'full'
        ):
            raise ValueError('closeout command is not the registered partial receipt checker')
        input_paths = [str(Path(argv[index]).resolve()) for index in (4, 6, 8)]
        if any(not Path(path).is_relative_to(Path.cwd().resolve()) for path in input_paths):
            raise ValueError('partial checker inputs escaped the registered repository')
        numerical_path = Path(argv[10]).resolve()
        numerical_output_missing = not numerical_path.is_dir()
        if numerical_output_missing and contract_version != 31:
            raise ValueError('partial checker numerical output directory is missing')
        output_path = Path(argv[14]).resolve()
        if not output_path.is_relative_to(Path.cwd().resolve()):
            raise ValueError('partial checker output path escaped the registered repository')
    elif checker_kind in {
        'task41_p0_independent_full_a6_checker',
        'task41_p0_a2_independent_p6_iterative_checker',
        'task41_p0_b0_independent_iterative_checker',
        'task41_p0_saved_output_continuation_checker',
        'task41_p0_b0_saved_evidence_audit_checker',
        'task41_p0_b0_v9_saved_star_screen_checker',
        'task41_p0_b0_v9_failed_terminal_audit_checker',
        'task41_p0_b0_saved_y_g_comparison_checker',
        'task41_p0_b0_v17_selected_two_cell_checker',
        'task41_p0_b0_v15_terminal_checker',
        'task41_p0_v11_selected_cell_saved_array_checker',
        'task41_p0_v13_saved_adjoint_diagnostic_independent_check',
    }:
        if contract_version != 41:
            raise ValueError('Task41 checker requires a Task41 P0 execution contract')
        root = Path.cwd().resolve()
        expected_python = (
            Path(str(contract.get('runtime', {}).get('runtime_prefix', '')))
            / 'bin/python'
        ).resolve()
        if checker_kind == 'task41_p0_b0_v15_terminal_checker':
            from src.runners.task41_p0_contract import TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE

            if (
                contract.get('execution_scope') != TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE
                or environment.get('TASK41_P0_V15_FULL_ACCEPTANCE') != '1'
                or len(argv) != 16
                or argv[1:4] != ['-m', 'src.runners.task41_p0_checker', '--v15-terminal-audit']
                or argv[4::2] != ['--run-root', '--summary', '--manifest', '--contract', '--contract-sha256', '--output']
                or argv[13] != contract_sha
                or authorization.get('expected_channel_count') is not None
            ):
                raise ValueError('V15 closeout requires the exact full-acceptance contract and command')
            run_root, summary_path, manifest_path = (Path(argv[i]).resolve() for i in (5, 7, 9))
            results_root = (root / 'results' / str(contract['case']['model_id'])).resolve()
            service_root = Path(str(contract['evidence']['service_directory']))
            if not service_root.is_absolute():
                service_root = root / service_root
            registered_output = (service_root / 'task41_p0_checker_result.json').resolve()
            requested_output = Path(argv[15]).resolve()
            if requested_output != registered_output:
                recheck_output = registered_output.with_name(
                    f"task41_p0_checker_result_recheck_{authorization['source_sha']}.json"
                )
                if (
                    not continuation
                    or environment.get('TASK41_P0_CONSUMER_SOURCE_SHA') != authorization['source_sha']
                    or requested_output != recheck_output
                    or requested_output.exists()
                    or not registered_output.is_file()
                ):
                    raise ValueError('V15 read-only recheck path/source is not registered')
                registered_output = recheck_output
            if (
                not run_root.is_relative_to(results_root)
                or summary_path != run_root / 'task40_v10_p6_candidate_summary.json'
                or manifest_path != run_root / 'run_manifest.json'
                or Path(argv[11]).resolve() != Path(str(contract_path)).resolve()
                or Path(argv[15]).resolve() != registered_output
            ):
                raise ValueError('V15 terminal audit paths differ from this run or service')
            input_paths = [str(summary_path), str(manifest_path)]
            product = run_root / 'task41_p0_b0_v9_compact_volume_audit.json'
            if not product.is_file():
                product = run_root / 'task41_p0_b0_v15_terminal_sufficient_checkpoint.json'
            if product.is_file():
                input_paths.append(str(product))
        elif checker_kind == 'task41_p0_b0_v17_selected_two_cell_checker':
            from src.runners.task41_p0_contract import (
                TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE,
                TASK41_B0_V17_SELECTED_TWO_CELL_WINDOW_RELATIVE,
                TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE,
                TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
                task41_case_id_for_run_id,
            )

            case = contract.get('case')
            scope = contract.get('execution_scope')
            window = contract.get('window')
            if (
                len(argv) != 18
                or Path(argv[0]).resolve() != expected_python
                or argv[1:4] != [
                    '-m', 'src.runners.task41_p0_checker',
                    '--v17-selected-two-cell-check',
                ]
                or argv[4::2] != [
                    '--v17-report', '--v17-report-sha256', '--manifest',
                    '--manifest-sha256', '--contract', '--contract-sha256', '--output',
                ]
                or authorization.get('expected_channel_count') is not None
                or not continuation
                or environment.get('TASK41_P0_V17_SELECTED_TWO_CELL_REPLAY') != '1'
                or environment.get('TASK41_P0_B0_V16_SAVED_VECTOR_ANALYSIS') is not None
                or environment.get('TASK41_P0_B0_SAVED_Y_G_COMPARISON') is not None
                or environment.get('TASK41_P0_V9_FAILED_TERMINAL_AUDIT') is not None
                or environment.get('TASK41_P0_SAVED_B0_EVIDENCE_AUDIT') is not None
                or environment.get('TASK41_P0_B0_V9_SAVED_STAR_SCREEN') is not None
                or environment.get('TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY') is not None
                or not isinstance(case, dict)
                or case.get('model_id') != 'task41extra_phi90_p50x50_g17x20'
                or task41_case_id_for_run_id(str(case.get('run_id', ''))) != 'B0'
                or scope != TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE
                or not isinstance(window, dict)
                or window.get('path') != TASK41_B0_V17_SELECTED_TWO_CELL_WINDOW_RELATIVE.as_posix()
                or window.get('sha256') != window_sha
                or contract.get('numerical_strategy', {}).get('internal_rhs_strategy')
                != 'same_lu_rhs_solve'
                or contract.get('source', {}).get('sha') != authorization.get('source_sha')
                or environment.get('TASK41_P0_CONSUMER_SOURCE_SHA')
                != authorization.get('source_sha')
                or environment.get('TASK41_P0_CHECKER_SOURCE_SHA')
                != authorization.get('source_sha')
                or authorization.get('source_sha') != contract.get('source', {}).get('sha')
                or authorization.get('source_branch') != contract.get('branch')
                or Path(argv[13]).resolve() != contract_file
                or argv[15] != contract_sha
                or Path(argv[13]).resolve()
                != Path(environment.get('TASK41_P0_CONTRACT_PATH', '')).resolve()
                or argv[15] != environment.get('TASK41_P0_CONTRACT_SHA256')
                or Path(argv[9]).resolve()
                != (root / TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE).resolve()
                or argv[11] != TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256
                or Path(argv[9]).resolve()
                != Path(environment.get('TASK41_P0_V17_V16_MANIFEST_PATH', '')).resolve()
                or argv[11] != environment.get('TASK41_P0_V17_V16_MANIFEST_SHA256')
                or Path(argv[5]).resolve()
                != (
                    Path(environment.get('TASK41_P0_V17_OUTPUT_DIRECTORY', ''))
                    / 'task41_p0_v17_selected_two_cell_worker.json'
                ).resolve()
            ):
                raise ValueError('V17 closeout checker is not bound to its exact B0 contract, report, and V16 manifest')

            report_path = Path(argv[5]).resolve(strict=True)
            manifest_path = Path(argv[9]).resolve(strict=True)
            output_path = Path(argv[17]).resolve()
            results_root = (root / 'results' / str(case['model_id'])).resolve()
            expected_parent = report_path.parent.with_name(report_path.parent.name + '.service')
            expected_window_root = (
                results_root / 'task41_p0_saved_diagnostics_6h'
                / str(window['sha256']) / 'selected_incident_replay'
            ).resolve()
            raw_paths = authorization.get('input_paths')
            raw_hashes = authorization.get('input_sha256s')
            if (
                not report_path.is_relative_to(expected_window_root)
                or not report_path.is_relative_to(results_root)
                or report_path.name != 'task41_p0_v17_selected_two_cell_worker.json'
                or re.fullmatch(r'attempt[0-9]{2,}', report_path.parent.name) is None
                or manifest_path
                != (root / TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE).resolve()
                or output_path.parent != expected_parent
                or output_path.name != 'task41_p0_v17_independent_check.json'
                or output_path.exists()
                or not output_path.is_relative_to(expected_window_root)
                or not isinstance(raw_paths, list)
                or not isinstance(raw_hashes, list)
                or len(raw_paths) != len(raw_hashes)
                or len(set(raw_paths)) != len(raw_paths)
                or not all(isinstance(value, str) for value in raw_paths)
                or not all(re.fullmatch(r'[0-9a-f]{64}', str(value)) for value in raw_hashes)
            ):
                raise ValueError('V17 checker input authorization or output path is malformed')
            for raw_path in raw_paths:
                path = Path(raw_path)
                if (
                    not path.is_absolute()
                    or path.resolve(strict=True) != path
                    or not path.is_file()
                    or not path.is_relative_to(root)
                ):
                    raise ValueError('V17 checker authorized input escaped the registered repository')
            authorized_hashes = dict(zip(raw_paths, raw_hashes, strict=True))
            required_inputs = (contract_file, campaign.path, manifest_path, report_path)
            for path in required_inputs:
                canonical = str(path.resolve(strict=True))
                if (
                    canonical not in authorized_hashes
                    or not path.is_file()
                    or not path.is_relative_to(root)
                ):
                    raise ValueError('V17 checker omitted a required hash-bound input')
            if (
                authorized_hashes[str(contract_file)] != contract_sha
                or authorized_hashes[str(campaign.path.resolve(strict=True))] != window_sha
                or authorized_hashes[str(manifest_path)] != argv[11]
                or authorized_hashes[str(report_path)] != argv[7]
            ):
                raise ValueError('V17 checker manifest/report hashes differ from its authorization')
            input_paths = raw_paths
        elif checker_kind in {
            'task41_p0_b0_v9_failed_terminal_audit_checker',
            'task41_p0_b0_saved_y_g_comparison_checker',
        }:
            from src.runners.task41_p0_contract import (
                TASK41_B0_SAVED_DIAGNOSTICS_SCOPE,
                TASK41_B0_SAVED_DIAGNOSTICS_WINDOW_RELATIVE,
                task41_case_id_for_run_id,
            )

            failed_terminal = checker_kind == 'task41_p0_b0_v9_failed_terminal_audit_checker'
            route_marker = (
                'TASK41_P0_B0_V9_FAILED_TERMINAL_AUDIT'
                if failed_terminal
                else 'TASK41_P0_B0_SAVED_Y_G_COMPARISON'
            )
            opposite_marker = (
                'TASK41_P0_B0_SAVED_Y_G_COMPARISON'
                if failed_terminal
                else 'TASK41_P0_B0_V9_FAILED_TERMINAL_AUDIT'
            )
            route_action = (
                'v9_failed_terminal_audit'
                if failed_terminal
                else 'v6_v9_saved_y_g_comparison'
            )
            case = contract.get('case')
            scope = contract.get('execution_scope')
            window = contract.get('window')
            if (
                Path(argv[0]).resolve() != expected_python
                or authorization.get('expected_channel_count') is not None
                or environment.get('TASK41_P0_SAVED_OUTPUT_CONTINUATION') != '1'
                or environment.get(route_marker) != '1'
                or environment.get(opposite_marker) is not None
                or environment.get('TASK41_P0_SAVED_B0_EVIDENCE_AUDIT') is not None
                or environment.get('TASK41_P0_B0_V9_SAVED_STAR_SCREEN') is not None
                or environment.get('TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY') is not None
                or environment.get('TASK41_P0_CONSUMER_SOURCE_SHA') != authorization.get('source_sha')
                or environment.get('TASK41_P0_CHECKER_SOURCE_SHA') != authorization.get('source_sha')
                or authorization.get('source_sha') != contract.get('source', {}).get('sha')
                or authorization.get('source_branch') != contract.get('branch')
                or not isinstance(case, dict)
                or not isinstance(scope, dict)
                or not isinstance(window, dict)
                or task41_case_id_for_run_id(str(case.get('run_id', ''))) != 'B0'
                or contract.get('numerical_strategy', {}).get('internal_rhs_strategy') != 'same_lu_rhs_solve'
                or scope != TASK41_B0_SAVED_DIAGNOSTICS_SCOPE
                or window.get('path') != TASK41_B0_SAVED_DIAGNOSTICS_WINDOW_RELATIVE.as_posix()
                or window.get('scope') != TASK41_B0_SAVED_DIAGNOSTICS_SCOPE
                or route_action not in scope.get('actions', [])
            ):
                raise ValueError('saved-diagnostics checker is not bound to its current-source B0 route')

            results_root = (root / 'results' / str(case['model_id'])).resolve()
            raw_paths = authorization.get('input_paths')
            raw_hashes = authorization.get('input_sha256s')
            if (
                not isinstance(raw_paths, list)
                or not raw_paths
                or not all(isinstance(value, str) for value in raw_paths)
                or len(set(raw_paths)) != len(raw_paths)
                or not isinstance(raw_hashes, list)
                or len(raw_hashes) != len(raw_paths)
                or not all(re.fullmatch(r'[0-9a-f]{64}', str(value)) for value in raw_hashes)
            ):
                raise ValueError('saved-diagnostics checker input authorization is malformed')
            authorized_hashes = dict(zip(raw_paths, raw_hashes, strict=True))
            for raw_path in raw_paths:
                path = Path(raw_path)
                if (
                    not path.is_absolute()
                    or path.resolve(strict=True) != path
                    or not path.is_file()
                    or not path.is_relative_to(root)
                ):
                    raise ValueError('saved-diagnostics authorized input escaped the repository')

            def require_registered_input(path: Path, *, expected_sha256: str | None = None) -> None:
                canonical = str(path.resolve(strict=True))
                if (
                    canonical not in authorized_hashes
                    or (expected_sha256 is not None and authorized_hashes[canonical] != expected_sha256)
                ):
                    raise ValueError('saved-diagnostics command input is not bound by its authorization hash')

            contract_file = Path(str(contract_path)).resolve(strict=True)
            if not contract_file.is_relative_to(root):
                raise ValueError('saved-diagnostics consumer contract escaped the repository')
            require_registered_input(contract_file, expected_sha256=str(contract_sha))
            case_input_raw = Path(str(case.get('input_path', '')))
            case_input = (case_input_raw if case_input_raw.is_absolute() else root / case_input_raw).resolve(strict=True)
            if not case_input.is_file() or not case_input.is_relative_to(root):
                raise ValueError('saved-diagnostics B0 source input escaped the repository')
            require_registered_input(case_input)
            input_paths = raw_paths

            if failed_terminal:
                if (
                    len(argv) != 20
                    or argv[1:4] != [
                        '-m', 'src.runners.task41_p0_checker', '--v9-failed-terminal-audit'
                    ]
                    or argv[4::2] != [
                        '--run-root', '--summary', '--manifest', '--contract',
                        '--contract-sha256', '--consumer-contract',
                        '--consumer-contract-sha256', '--output',
                    ]
                    or Path(argv[15]).resolve() != contract_file
                    or argv[17] != contract_sha
                    or Path(argv[15]).resolve()
                    != Path(environment.get('TASK41_P0_CONTRACT_PATH', '')).resolve()
                    or argv[17] != environment.get('TASK41_P0_CONTRACT_SHA256')
                    or Path(argv[5]).resolve()
                    != Path(environment.get('TASK41_P0_V9_PRODUCER_RUN_ROOT', '')).resolve()
                    or Path(argv[7]).resolve()
                    != Path(environment.get('TASK41_P0_V9_PRODUCER_SUMMARY_PATH', '')).resolve()
                    or Path(argv[9]).resolve()
                    != Path(environment.get('TASK41_P0_V9_PRODUCER_MANIFEST_PATH', '')).resolve()
                    or Path(argv[11]).resolve()
                    != Path(environment.get('TASK41_P0_V9_PRODUCER_CONTRACT_PATH', '')).resolve()
                    or argv[13] != environment.get('TASK41_P0_V9_PRODUCER_CONTRACT_SHA256')
                ):
                    raise ValueError('closeout command is not the registered V9 failed-terminal checker')
                run_root = Path(argv[5]).resolve(strict=True)
                summary_path = Path(argv[7]).resolve(strict=True)
                manifest_path = Path(argv[9]).resolve(strict=True)
                producer_contract_path = Path(argv[11]).resolve(strict=True)
                if (
                    not run_root.is_relative_to(results_root)
                    or summary_path.parent != run_root
                    or summary_path.name != 'task40_v10_p6_candidate_summary.json'
                    or manifest_path != run_root / 'run_manifest.json'
                    or not producer_contract_path.is_relative_to(root)
                ):
                    raise ValueError('V9 failed-terminal checker paths escaped their registered run')
                require_registered_input(summary_path)
                require_registered_input(manifest_path)
                require_registered_input(
                    producer_contract_path,
                    expected_sha256=str(environment.get('TASK41_P0_V9_PRODUCER_CONTRACT_SHA256')),
                )
                required_inputs = (summary_path, manifest_path, producer_contract_path, contract_file, case_input)
                output_index = 19
                mode_name = 'v9_failed_terminal_audit'
                expected_name = 'task41_p0_b0_v9_failed_terminal_audit.json'
                result_env = 'TASK41_P0_V9_FAILED_TERMINAL_AUDIT_RESULT_PATH'
            else:
                if (
                    len(argv) != 26
                    or argv[1:4] != [
                        '-m', 'src.runners.task41_p0_checker', '--saved-b0-y-g-comparison'
                    ]
                    or argv[4::2] != [
                        '--contract', '--contract-sha256', '--v6-report',
                        '--v6-report-sha256', '--v9-report', '--v9-report-sha256',
                        '--v9-summary', '--v9-summary-sha256', '--v9-service-receipt',
                        '--v9-service-receipt-sha256', '--output',
                    ]
                    or Path(argv[5]).resolve() != contract_file
                    or argv[7] != contract_sha
                    or Path(argv[5]).resolve()
                    != Path(environment.get('TASK41_P0_CONTRACT_PATH', '')).resolve()
                    or argv[7] != environment.get('TASK41_P0_CONTRACT_SHA256')
                ):
                    raise ValueError('closeout command is not the registered saved y/g checker')
                expected_bindings = (
                    (Path(argv[9]).resolve(strict=True), argv[11],
                     'TASK41_P0_SAVED_Y_G_V6_REPORT_PATH', 'TASK41_P0_SAVED_Y_G_V6_REPORT_SHA256'),
                    (Path(argv[13]).resolve(strict=True), argv[15],
                     'TASK41_P0_SAVED_Y_G_V9_REPORT_PATH', 'TASK41_P0_SAVED_Y_G_V9_REPORT_SHA256'),
                    (Path(argv[17]).resolve(strict=True), argv[19],
                     'TASK41_P0_SAVED_Y_G_V9_SUMMARY_PATH', 'TASK41_P0_SAVED_Y_G_V9_SUMMARY_SHA256'),
                    (Path(argv[21]).resolve(strict=True), argv[23],
                     'TASK41_P0_SAVED_Y_G_V9_SERVICE_RECEIPT_PATH',
                     'TASK41_P0_SAVED_Y_G_V9_SERVICE_RECEIPT_SHA256'),
                )
                expected_names = (
                    'task41_p0_v6_actual_qmetric_candidate.json',
                    'task41_p0_b0_v9_compact_volume_audit.json',
                    'run_summary.json',
                    'task41_p0_service_receipt.json',
                )
                allowed_roots = (results_root, results_root, results_root, root)
                for (path, digest, path_key, sha_key), name, allowed_root in zip(
                    expected_bindings, expected_names, allowed_roots, strict=True
                ):
                    if (
                        not path.is_relative_to(allowed_root)
                        or path.name != name
                        or environment.get(path_key) != str(path)
                        or environment.get(sha_key) != digest
                        or not re.fullmatch(r'[0-9a-f]{64}', str(digest))
                    ):
                        raise ValueError('saved y/g report path or hash differs from the service binding')
                    require_registered_input(path, expected_sha256=str(digest))
                v6_path, v9_path, summary_path, receipt_path = (
                    item[0] for item in expected_bindings
                )
                run_root = Path(environment.get('TASK41_P0_SAVED_Y_G_RUN_ROOT', '')).resolve(strict=True)
                if (
                    run_root != summary_path.parent
                    or summary_path.parent != run_root
                    or v9_path.parent != run_root
                    or not run_root.is_relative_to(results_root)
                    or environment.get('TASK41_P0_SAVED_Y_G_RUN_ROOT') != str(run_root)
                    or not receipt_path.is_relative_to(root)
                ):
                    raise ValueError('saved y/g inputs do not identify a registered B0 run')
                required_inputs = (contract_file, case_input, *(item[0] for item in expected_bindings))
                output_index = 25
                mode_name = 'saved_y_g_comparison'
                expected_name = 'task41_p0_b0_saved_y_g_comparison.json'
                result_env = 'TASK41_P0_SAVED_Y_G_RESULT_PATH'

            output_path = Path(argv[output_index]).resolve()
            window_output_root = results_root / 'task41_p0_saved_diagnostics_6h' / str(window.get('sha256', ''))
            if (
                any(not path.is_relative_to(root) for path in required_inputs)
                or any(str(path) not in authorized_hashes for path in required_inputs)
                or output_path.name != expected_name
                or output_path.parent.parent != window_output_root / mode_name
                or re.fullmatch(r'attempt[0-9]{2,}', output_path.parent.name) is None
                or output_path.exists()
                or not output_path.is_relative_to(results_root)
                or output_path != Path(environment.get(result_env, '')).resolve()
            ):
                raise ValueError('saved-diagnostics output or command inputs escaped their registered paths')
        elif checker_kind == 'task41_p0_v13_saved_adjoint_diagnostic_independent_check':
            from src.runners.task41_p0_contract import (
                TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE,
                TASK41_B0_V12_CANDIDATE_REPLAY_WINDOW_RELATIVE,
                require_task41_p0_contract,
                task41_case_id_for_run_id,
            )

            case = contract.get('case')
            scope = contract.get('execution_scope')
            window = contract.get('window')
            continuation = environment.get('TASK41_P0_SAVED_OUTPUT_CONTINUATION')
            checker_only = environment.get('TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY') == '1'
            if (
                contract_version != 41
                or len(argv) != 30
                or Path(argv[0]).resolve() != expected_python
                or argv[1:4] != [
                    '-m', 'src.runners.task41_p0_checker',
                    '--v13-saved-adjoint-diagnostic-check',
                ]
                or argv[4::2] != [
                    '--contract', '--contract-sha256', '--summary',
                    '--donor-summary-sha256', '--consumer-contract',
                    '--consumer-contract-sha256', '--checker-contract',
                    '--checker-contract-sha256', '--v11-report',
                    '--v11-report-sha256', '--v13-diagnostic',
                    '--v13-diagnostic-sha256', '--output',
                ]
                or authorization.get('expected_channel_count') is not None
                or continuation not in {None, '1'}
                or (checker_only and continuation != '1')
                or environment.get('TASK41_P0_SAVED_B0_EVIDENCE_AUDIT') is not None
                or environment.get('TASK41_P0_B0_V9_FAILED_TERMINAL_AUDIT') is not None
                or environment.get('TASK41_P0_B0_SAVED_Y_G_COMPARISON') is not None
                or environment.get('TASK41_P0_B0_V9_SAVED_STAR_SCREEN') is not None
                or environment.get('TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY')
                != ('1' if checker_only else None)
                or not isinstance(case, dict)
                or case.get('model_id') != 'task41extra_phi90_p50x50_g17x20'
                or task41_case_id_for_run_id(str(case.get('run_id', ''))) != 'B0'
                or not isinstance(scope, dict)
                or scope != TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE
                or not isinstance(window, dict)
                or window.get('path') != TASK41_B0_V12_CANDIDATE_REPLAY_WINDOW_RELATIVE.as_posix()
                or window.get('sha256') != window_sha
                or contract.get('numerical_strategy', {}).get('internal_rhs_strategy')
                != 'same_lu_rhs_solve'
                or contract.get('source', {}).get('sha') != authorization.get('source_sha')
                or environment.get('TASK41_P0_CHECKER_SOURCE_SHA') not in {
                    None, authorization.get('source_sha')
                }
                or authorization.get('source_branch') != contract.get('branch')
            ):
                raise ValueError(
                    'closeout command is not the registered V13 saved-adjoint diagnostic checker'
                )

            raw_paths = authorization.get('input_paths')
            raw_hashes = authorization.get('input_sha256s')
            if (
                not isinstance(raw_paths, list)
                or not raw_paths
                or not all(isinstance(value, str) for value in raw_paths)
                or len(set(raw_paths)) != len(raw_paths)
                or not isinstance(raw_hashes, list)
                or len(raw_hashes) != len(raw_paths)
                or not all(re.fullmatch(r'[0-9a-f]{64}', str(value)) for value in raw_hashes)
            ):
                raise ValueError('V13 independent checker input authorization is malformed')
            authorized_hashes = dict(zip(raw_paths, raw_hashes, strict=True))
            repository_root = Path.cwd().resolve()
            for raw_path in raw_paths:
                path = Path(raw_path)
                if (
                    not path.is_absolute()
                    or path.resolve(strict=True) != path
                    or not path.is_file()
                    or not path.is_relative_to(repository_root)
                ):
                    raise ValueError('V13 independent checker input escaped the registered repository')

            def require_v13_input(path: Path, *, expected_sha256: str) -> None:
                canonical = str(path.resolve(strict=True))
                if authorized_hashes.get(canonical) != expected_sha256:
                    raise ValueError('V13 checker command input is not bound by its authorization hash')

            donor_contract_path = Path(argv[5]).resolve(strict=True)
            donor_summary_path = Path(argv[9]).resolve(strict=True)
            consumer_contract_argument = Path(argv[13]).resolve(strict=True)
            checker_contract_argument = Path(argv[17]).resolve(strict=True)
            candidate_report_path = Path(argv[21]).resolve(strict=True)
            diagnostic_path = Path(argv[25]).resolve(strict=True)
            output_path = Path(argv[29]).resolve()
            results_root = (
                repository_root / 'results' / str(case['model_id'])
            ).resolve()
            expected_output_parent = (
                diagnostic_path.parent.parent / 'attempt10'
                if consumer_contract_argument != checker_contract_argument
                else diagnostic_path.parent
            )
            if (
                str(donor_contract_path) != argv[5]
                or str(donor_summary_path) != argv[9]
                or str(consumer_contract_argument) != argv[13]
                or str(checker_contract_argument) != argv[17]
                or str(candidate_report_path) != argv[21]
                or str(diagnostic_path) != argv[25]
                or checker_contract_argument != contract_file
                or Path(contract_path).resolve() != contract_file
                or argv[19] != contract_sha
                or argv[19] != environment.get('TASK41_P0_CONTRACT_SHA256')
                or donor_summary_path.name != 'task40_v10_p6_candidate_summary.json'
                or candidate_report_path.name != 'task41_p0_v11_selected_trace_candidate_replay.json'
                or diagnostic_path.name != 'task41_p0_v13_saved_adjoint_diagnostic.json'
                or not donor_contract_path.is_relative_to(repository_root)
                or not consumer_contract_argument.is_relative_to(repository_root)
                or not donor_summary_path.is_relative_to(results_root)
                or not candidate_report_path.is_relative_to(results_root)
                or not diagnostic_path.is_relative_to(results_root)
                or output_path.name
                != 'task41_p0_v13_saved_adjoint_diagnostic_independent_check.json'
                or output_path.parent != expected_output_parent
                or output_path.exists()
                or not output_path.is_relative_to(results_root)
            ):
                raise ValueError('V13 independent checker command paths differ from the saved-diagnostics route')

            consumer_contract, consumer_digest = require_task41_p0_contract(
                consumer_contract_argument,
                expected_sha256=argv[15],
                current_root=repository_root,
                check_current_source=False,
                require_clean_source=False,
                case_id='B0',
            )
            consumer_case = consumer_contract.get('case')
            consumer_window = consumer_contract.get('window')
            identity_fields = (
                'model_id', 'run_id', 'input_sha256', 'physical_model_sha256',
                'resolved_config_sha256',
            )
            consumer_window_path = Path(str(consumer_window.get('path', ''))) if isinstance(consumer_window, dict) else Path('')
            if not consumer_window_path.is_absolute():
                consumer_window_path = repository_root / consumer_window_path
            current_window_path = Path(str(window_path))
            if not current_window_path.is_absolute():
                current_window_path = repository_root / current_window_path
            if (
                not isinstance(consumer_case, dict)
                or task41_case_id_for_run_id(str(consumer_case.get('run_id', ''))) != 'B0'
                or any(consumer_case.get(key) != case.get(key) for key in identity_fields)
                or consumer_contract.get('execution_scope') != TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE
                or consumer_contract.get('numerical_strategy', {}).get('internal_rhs_strategy')
                != 'same_lu_rhs_solve'
                or not isinstance(consumer_window, dict)
                or consumer_window_path.resolve(strict=True) != current_window_path.resolve(strict=True)
                or consumer_window.get('sha256') != window_sha
                or not re.fullmatch(r'[0-9a-f]{40}', str(consumer_contract.get('source', {}).get('sha', '')))
                or argv[15] != consumer_digest
            ):
                raise ValueError('V13 original consumer contract differs from the current checker window/case')
            if checker_only:
                if (
                    consumer_contract_argument == contract_file
                    or environment.get('TASK41_P0_CONSUMER_SOURCE_SHA')
                    != consumer_contract.get('source', {}).get('sha')
                    or environment.get('TASK41_P0_CHECKER_SOURCE_SHA')
                    != authorization.get('source_sha')
                    or consumer_contract.get('source', {}).get('sha')
                    == authorization.get('source_sha')
                ):
                    raise ValueError('V13 checker-only command did not separate the saved consumer and current checker')
            elif (
                continuation is not None
                or consumer_contract_argument != contract_file
                or consumer_digest != contract_sha
                or consumer_contract.get('source', {}).get('sha')
                != authorization.get('source_sha')
                or environment.get('TASK41_P0_CONSUMER_SOURCE_SHA') is not None
            ):
                raise ValueError('V13 same-source closeout differs from its original consumer contract')

            require_v13_input(donor_contract_path, expected_sha256=argv[7])
            require_v13_input(donor_summary_path, expected_sha256=argv[11])
            require_v13_input(consumer_contract_argument, expected_sha256=consumer_digest)
            require_v13_input(checker_contract_argument, expected_sha256=contract_sha)
            require_v13_input(candidate_report_path, expected_sha256=argv[23])
            require_v13_input(diagnostic_path, expected_sha256=argv[27])
            require_v13_input(Path(str(window_path)).resolve(strict=True), expected_sha256=str(window_sha))
            input_paths = raw_paths
        elif checker_kind == 'task41_p0_v11_selected_cell_saved_array_checker':
            from src.runners.task41_p0_contract import (
                TASK41_B0_V12_CANDIDATE_REPLAY_INSTANCE,
                TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE,
                TASK41_B0_V12_CANDIDATE_REPLAY_WINDOW_RELATIVE,
                TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE,
                contract_relative_path,
                load_task41_p0_fixed_window,
                task41_case_id_for_run_id,
                require_task41_p0_contract,
            )
            from src.runners.task41_p0_v4_volume_only_audit import (
                TASK41_P0_V11_FFCX_C_SOURCE_SHA256,
            )

            case = contract.get('case')
            scope = contract.get('execution_scope')
            window = contract.get('window')
            read_only_candidate_replay = (
                environment.get('TASK41_P0_B0_V11_CANDIDATE_REPLAY_READ_ONLY') == '1'
            )
            if (
                Path(argv[0]).resolve() != expected_python
                or len(argv) != 20
                or argv[1:4]
                != ['-m', 'src.runners.task41_p0_checker', '--v11-candidate-replay-saved-check']
                or argv[4::2]
                != [
                    '--contract', '--contract-sha256', '--consumer-contract',
                    '--consumer-contract-sha256', '--summary', '--v11-report',
                    '--v11-report-sha256', '--output',
                ]
                or authorization.get('expected_channel_count') is not None
                or environment.get('TASK41_P0_SAVED_OUTPUT_CONTINUATION') != '1'
                or environment.get('TASK41_P0_SAVED_B0_EVIDENCE_AUDIT') != '1'
                or environment.get('TASK41_P0_B0_V8_SELECTED_TRACE_STAR_AUDIT')
                != ('1' if not read_only_candidate_replay else None)
                or environment.get('TASK41_P0_B0_V11_CANDIDATE_REPLAY_READ_ONLY')
                not in (None, '1')
                or environment.get('TASK41_P0_B0_V8_SELECTED_TRACE_STAR_METADATA_ONLY') is not None
                or (
                    not read_only_candidate_replay
                    and environment.get('TASK41_P0_B0_V8_FFCX_C_SOURCE_PATH') is None
                )
                or environment.get('TASK41_P0_B0_V9_SAVED_STAR_SCREEN') is not None
                or environment.get('TASK41_P0_B0_V9_FAILED_TERMINAL_AUDIT') is not None
                or environment.get('TASK41_P0_B0_SAVED_Y_G_COMPARISON') is not None
                or environment.get('TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY') is not None
                or environment.get('TASK41_P0_CONSUMER_SOURCE_SHA')
                != authorization.get('source_sha')
                or environment.get('TASK41_P0_CHECKER_SOURCE_SHA')
                != authorization.get('source_sha')
                or authorization.get('source_sha') != contract.get('source', {}).get('sha')
                or authorization.get('source_branch') != contract.get('branch')
                or not isinstance(case, dict)
                or not isinstance(scope, dict)
                or not isinstance(window, dict)
                or task41_case_id_for_run_id(str(case.get('run_id', ''))) != 'B0'
                or contract.get('numerical_strategy', {}).get('internal_rhs_strategy')
                != 'same_lu_rhs_solve'
                or scope != TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE
                or window.get('path') != TASK41_B0_V12_CANDIDATE_REPLAY_WINDOW_RELATIVE.as_posix()
                or window.get('scope') != TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE
            ):
                raise ValueError('V12 saved-array checker is not bound to its current-source B0 route')

            root = Path.cwd().resolve()
            results_root = (root / 'results' / str(case.get('model_id', ''))).resolve()
            donor_contract_path = Path(argv[5]).resolve(strict=True)
            donor_contract_sha256 = argv[7]
            consumer_contract_argument = Path(argv[9]).resolve(strict=True)
            summary_path = Path(argv[13]).resolve(strict=True)
            candidate_report_path = Path(argv[15]).resolve(strict=True)
            candidate_report_sha256 = argv[17]
            output_path = Path(argv[19]).resolve()
            if (
                consumer_contract_argument != contract_file
                or argv[11] != contract_sha
                or consumer_contract_argument
                != Path(environment.get('TASK41_P0_CONTRACT_PATH', '')).resolve()
                or argv[11] != environment.get('TASK41_P0_CONTRACT_SHA256')
                or Path(window.get('path', '')).is_absolute()
                or (root / window['path']).resolve(strict=True) != campaign.path.resolve()
                or window.get('sha256') != campaign.sha256
            ):
                raise ValueError('V12 checker consumer contract or fixed-window binding differs')

            donor_contract, donor_digest = require_task41_p0_contract(
                donor_contract_path,
                expected_sha256=donor_contract_sha256,
                current_root=root,
                check_current_source=False,
                require_clean_source=False,
                case_id='B0',
            )
            donor_case = donor_contract.get('case')
            if (
                not isinstance(donor_case, dict)
                or donor_digest != donor_contract_sha256
                or any(
                    donor_case.get(field) != case.get(field)
                    for field in (
                        'model_id', 'run_id', 'method', 'mpi_size', 'input_sha256',
                        'physical_model_sha256', 'resolved_config_sha256',
                    )
                )
            ):
                raise ValueError('V12 checker donor contract differs from the current B0 identity')

            donor_run = (root / TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE).resolve(strict=True)
            if (
                summary_path != donor_run / 'task40_v10_p6_candidate_summary.json'
                or not summary_path.is_relative_to(results_root)
            ):
                raise ValueError('V12 checker summary is not the registered V9 donor run')
            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            recovery = summary.get('b0_recovery_evidence')
            manifest_record = recovery.get('manifest') if isinstance(recovery, dict) else None
            if not isinstance(manifest_record, dict) or not isinstance(manifest_record.get('path'), str):
                raise ValueError('V12 checker donor summary omits its recovery manifest')
            manifest_raw = Path(manifest_record['path'])
            donor_manifest_path = (
                manifest_raw if manifest_raw.is_absolute() else donor_run / manifest_raw
            ).resolve(strict=True)
            if (
                not donor_manifest_path.is_relative_to(donor_run)
                or donor_manifest_path.stat().st_size != manifest_record.get('bytes')
                or _sha256_file(donor_manifest_path) != manifest_record.get('sha256')
            ):
                raise ValueError('V12 checker donor manifest path, size, or hash differs from its summary')

            attempt_root = candidate_report_path.parent.resolve(strict=True)
            window_output_root = (
                results_root / 'task41_p0_saved_diagnostics_6h' / str(window['sha256'])
            )
            output_root = Path(environment.get('TASK41_P0_B0_OUTPUT_DIR', '')).resolve()
            output_under_registered_attempt = (
                output_path.parent == output_root
                and output_root.parent == window_output_root / 'selected_incident_replay'
                and re.fullmatch(r'attempt[0-9]{2,}', output_root.name) is not None
                and output_root != attempt_root
            )
            valid_output_parent = (
                output_under_registered_attempt
                if read_only_candidate_replay
                else output_path.parent == attempt_root
            )
            if (
                candidate_report_path.name != 'task41_p0_v11_selected_trace_candidate_replay.json'
                or not candidate_report_path.is_relative_to(results_root)
                or _sha256_file(candidate_report_path) != candidate_report_sha256
                or not re.fullmatch(r'[0-9a-f]{64}', candidate_report_sha256)
                or output_path.name != 'task41_p0_v11_candidate_replay_saved_array_check.json'
                or not valid_output_parent
                or output_path.exists()
                or not output_path.is_relative_to(results_root)
                or attempt_root.parent != window_output_root / 'selected_incident_replay'
                or re.fullmatch(r'attempt[0-9]{2,}', attempt_root.name) is None
            ):
                raise ValueError('V12 checker candidate report or result path/hash differs')

            envelope = json.loads(candidate_report_path.read_text(encoding='utf-8'))
            replay = envelope.get('v11_selected_trace_candidate_replay')
            producer_contract_path = contract_file
            producer_contract_digest = contract_sha
            producer_source_sha = contract.get('source', {}).get('sha')
            if read_only_candidate_replay:
                producer_contract_path = Path(
                    environment.get('TASK41_P0_B0_V11_PRODUCER_CONTRACT_PATH', '')
                ).resolve(strict=True)
                producer_contract_digest = environment.get(
                    'TASK41_P0_B0_V11_PRODUCER_CONTRACT_SHA256'
                )
                producer_source_sha = envelope.get('consumer_source_sha')
                if (
                    not isinstance(producer_contract_digest, str)
                    or not re.fullmatch(r'[0-9a-f]{64}', producer_contract_digest)
                    or not isinstance(producer_source_sha, str)
                    or not re.fullmatch(r'[0-9a-f]{40}', producer_source_sha)
                    or environment.get('TASK41_P0_B0_V11_CANDIDATE_REPORT_PATH')
                    != str(candidate_report_path)
                    or environment.get('TASK41_P0_B0_V11_CANDIDATE_REPORT_SHA256')
                    != candidate_report_sha256
                    or environment.get('TASK41_P0_B0_OUTPUT_DIR') != str(output_root)
                ):
                    raise ValueError('V12 read-only checker route lacks its frozen producer/output bindings')
                producer_contract, producer_digest = require_task41_p0_contract(
                    producer_contract_path,
                    expected_sha256=producer_contract_digest,
                    current_root=root,
                    check_current_source=False,
                    require_clean_source=False,
                    case_id='B0',
                )
                expected_producer_path = (
                    root
                    / contract_relative_path(
                        producer_source_sha,
                        'B0',
                        saved_diagnostics_instance=TASK41_B0_V12_CANDIDATE_REPLAY_INSTANCE,
                    )
                ).resolve(strict=True)
                producer_case = producer_contract.get('case')
                producer_window = load_task41_p0_fixed_window(
                    producer_contract, current_root=root, require_current_boot=False
                )
                if (
                    producer_contract_path != expected_producer_path
                    or producer_digest != producer_contract_digest
                    or producer_contract.get('source', {}).get('sha') != producer_source_sha
                    or producer_contract.get('execution_scope') != scope
                    or producer_contract.get('numerical_strategy', {}).get('internal_rhs_strategy')
                    != 'same_lu_rhs_solve'
                    or not isinstance(producer_case, dict)
                    or any(
                        producer_case.get(field) != case.get(field)
                        for field in (
                            'model_id', 'run_id', 'method', 'mpi_size', 'input_sha256',
                            'physical_model_sha256', 'resolved_config_sha256', 'profile_identity',
                            'solver_stage', 'comparison_group', 'geometry_identity',
                        )
                    )
                    or producer_window.sha256 != campaign.sha256
                    or Path(producer_window.path).resolve() != campaign.path.resolve()
                ):
                    raise ValueError('V12 read-only producer contract is outside the current B0 replay window')
            if (
                envelope.get('schema')
                != 'task41.p0.v11.selected_trace_star_candidate_replay_receipt.v1'
                or envelope.get('status') != 'COMPLETED_LOCAL_CANDIDATE_REPLAY'
                or Path(str(envelope.get('consumer_contract_path', ''))).resolve()
                != producer_contract_path
                or envelope.get('consumer_contract_sha256') != producer_contract_digest
                or envelope.get('consumer_source_sha') != producer_source_sha
                or Path(str(envelope.get('donor_contract_path', ''))).resolve() != donor_contract_path
                or envelope.get('donor_contract_sha256') != donor_digest
                or Path(str(envelope.get('consumer_window_path', ''))).resolve() != campaign.path.resolve()
                or envelope.get('consumer_window_sha256') != campaign.sha256
                or Path(str(envelope.get('output_directory', ''))).resolve() != attempt_root
                or Path(str(envelope.get('volume_evidence_directory', ''))).resolve()
                != (attempt_root / 'selected_trace_star_candidate_replay').resolve(strict=True)
                or not isinstance(replay, dict)
                or replay.get('schema') != 'task41.p0.v11.selected_trace_star_candidate_replay.v1'
                or replay.get('status') != 'COMPLETED_LOCAL_CANDIDATE_REPLAY'
                or replay.get('scientific_qualified') is not False
                or not isinstance(replay.get('source_semantics'), dict)
                or replay.get('source_semantics', {}).get('official_result') is not False
                or replay.get('source_semantics', {}).get('formal_action_gate_changed') is not False
                or replay.get('selected_active_row') != 87567
                or replay.get('selected_original_row') != 250113
                or replay.get('incident_cell_order') != [360, 446]
                or replay.get('consumer_contract_sha256') != producer_contract_digest
                or replay.get('consumer_source_sha') != producer_source_sha
            ):
                raise ValueError('V12 checker worker receipt is incomplete or misbound')

            metadata_path = Path(str(replay.get('metadata_report_path', ''))).resolve(strict=True)
            compact_path = Path(str(replay.get('v9_compact_report_path', ''))).resolve(strict=True)
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            old_contract_path = Path(str(metadata.get('consumer_contract_path', ''))).resolve(strict=True)
            receipt_path = Path(str(replay.get('metadata_service_receipt_path', ''))).resolve(strict=True)
            expected_inputs = list(dict.fromkeys(str(path.resolve(strict=True)) for path in (
                contract_file,
                donor_contract_path,
                summary_path,
                donor_manifest_path,
                candidate_report_path,
                producer_contract_path,
                metadata_path,
                compact_path,
                old_contract_path,
                receipt_path,
                campaign.path,
            )))
            raw_paths = authorization.get('input_paths')
            raw_hashes = authorization.get('input_sha256s')
            if (
                raw_paths != expected_inputs
                or not isinstance(raw_hashes, list)
                or len(raw_hashes) != len(expected_inputs)
                or not all(re.fullmatch(r'[0-9a-f]{64}', str(value)) for value in raw_hashes)
            ):
                raise ValueError('V12 checker authorized inputs are not the complete fixed receipt set')
            authorized_hashes = dict(zip(raw_paths, raw_hashes, strict=True))
            if (
                authorized_hashes.get(str(donor_contract_path)) != donor_digest
                or authorized_hashes.get(str(contract_file)) != contract_sha
                or authorized_hashes.get(str(producer_contract_path)) != producer_contract_digest
                or authorized_hashes.get(str(candidate_report_path)) != candidate_report_sha256
                or replay.get('metadata_report_sha256') != authorized_hashes.get(str(metadata_path))
                or replay.get('v9_compact_report_sha256') != authorized_hashes.get(str(compact_path))
                or replay.get('metadata_service_receipt_sha256') != authorized_hashes.get(str(receipt_path))
            ):
                raise ValueError('V12 checker command/input hashes differ from the worker receipt')
            compact = json.loads(compact_path.read_text(encoding='utf-8'))
            if (
                metadata_path.name != 'task41_p0_v8_selected_trace_star_metadata.json'
                or not metadata_path.is_relative_to(results_root)
                or compact_path.name != 'task41_p0_b0_v9_compact_volume_audit.json'
                or not compact_path.is_relative_to(results_root)
                or metadata.get('schema') != 'task41.p0.v8.selected_trace_star_metadata_only_receipt.v1'
                or metadata.get('status') != 'COMPLETED_METADATA_ONLY'
                or compact.get('schema') != 'task41.p0.b0.v9.compact_volume_identity.v1'
                or compact.get('status') != 'GATE_FAILED'
                or compact.get('official_result') is not False
                or compact.get('internal_rhs_strategy') != 'same_lu_rhs_solve'
                or compact.get('donor_manifest_sha256') != manifest_record.get('sha256')
            ):
                raise ValueError('V12 checker metadata or compact donor receipt is not registered')
            if replay.get('ffcx_c_source_sha256') != TASK41_P0_V11_FFCX_C_SOURCE_SHA256:
                raise ValueError('V12 checker FFCx source differs from the frozen candidate receipt')
            ffcx_source_path = environment.get('TASK41_P0_B0_V8_FFCX_C_SOURCE_PATH')
            if ffcx_source_path is None:
                if not read_only_candidate_replay:
                    raise ValueError('live V12 checker route requires its registered FFCx source')
            else:
                ffcx_path = Path(ffcx_source_path).resolve(strict=True)
                if (
                    not ffcx_path.is_relative_to(root)
                    or _sha256_file(ffcx_path) != TASK41_P0_V11_FFCX_C_SOURCE_SHA256
                ):
                    raise ValueError('V12 checker FFCx source differs from the frozen candidate receipt')
            input_paths = expected_inputs
        elif checker_kind == 'task41_p0_b0_v9_saved_star_screen_checker':
            from src.runners.task41_p0_contract import (
                TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
                TASK41_B0_V9_WINDOW_RELATIVE,
                task41_case_id_for_run_id,
            )
            from src.runners.task41_p0_checker import (
                TASK41_P0_V9_V8_CHECKER_RESULT_SHA256,
                TASK41_P0_V9_V8_REPORT_SHA256,
            )

            if (
                len(argv) != 18
                or Path(argv[0]).resolve() != expected_python
                or argv[1:4] != ['-m', 'src.runners.task41_p0_checker', '--v9-saved-star-screen']
                or argv[4::2] != [
                    '--contract', '--contract-sha256', '--v8-report',
                    '--v8-report-sha256', '--v8-checker-result',
                    '--v8-checker-result-sha256', '--output',
                ]
                or argv[7] != contract_sha
                or authorization.get('expected_channel_count') is not None
                or environment.get('TASK41_P0_SAVED_OUTPUT_CONTINUATION') != '1'
                or environment.get('TASK41_P0_B0_V9_SAVED_STAR_SCREEN') != '1'
                or environment.get('TASK41_P0_SAVED_B0_EVIDENCE_AUDIT') is not None
                or environment.get('TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY') is not None
                or environment.get('TASK41_P0_CHECKER_SOURCE_SHA')
                != authorization.get('source_sha')
            ):
                raise ValueError('closeout command is not the registered V9 saved-star screen checker')
            case = contract.get('case')
            if (
                not isinstance(case, dict)
                or task41_case_id_for_run_id(str(case.get('run_id', ''))) != 'B0'
                or contract.get('numerical_strategy', {}).get('internal_rhs_strategy')
                != TASK41_B0_V9_INTERNAL_RHS_STRATEGY
                or contract.get('window', {}).get('path')
                != str(TASK41_B0_V9_WINDOW_RELATIVE)
                or authorization.get('source_sha') != contract.get('source', {}).get('sha')
                or authorization.get('source_branch') != contract.get('branch')
                or environment.get('TASK41_P0_CONSUMER_SOURCE_SHA')
                != authorization.get('source_sha')
                or Path(argv[5]).resolve() != Path(str(contract_path)).resolve()
                or Path(argv[9]).resolve()
                != Path(environment.get('TASK41_P0_B0_V9_V8_REPORT_PATH', '')).resolve()
                or argv[11] != TASK41_P0_V9_V8_REPORT_SHA256
                or argv[11] != environment.get('TASK41_P0_B0_V9_V8_REPORT_SHA256')
                or Path(argv[13]).resolve()
                != Path(environment.get('TASK41_P0_B0_V9_V8_CHECKER_RESULT_PATH', '')).resolve()
                or argv[15] != TASK41_P0_V9_V8_CHECKER_RESULT_SHA256
                or argv[15] != environment.get('TASK41_P0_B0_V9_V8_CHECKER_RESULT_SHA256')
            ):
                raise ValueError('V9 saved-star contract, V8 evidence binding, or route markers differ')
            results_root = (root / 'results' / str(case.get('model_id', ''))).resolve()
            report_path = Path(argv[9]).resolve()
            checker_result_path = Path(argv[13]).resolve()
            output_path = Path(argv[17]).resolve()
            if (
                report_path.name != 'task41_p0_v8_selected_trace_star_audit.json'
                or checker_result_path.name != 'task41_p0_b0_saved_evidence_audit.json'
                or output_path.name != 'task41_p0_b0_v9_saved_star_screen.json'
                or not report_path.is_relative_to(results_root)
                or not checker_result_path.is_relative_to(results_root)
                or not output_path.is_relative_to(results_root)
                or output_path != Path(environment.get('TASK41_P0_B0_V9_RESULT_PATH', '')).resolve()
                or output_path.exists()
            ):
                raise ValueError('V9 saved-star report/result paths differ from the registered B0 results tree')
            try:
                report = json.loads(report_path.read_text(encoding='utf-8'))
                checker_result = json.loads(checker_result_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError('V9 saved-star input reports are unavailable or malformed') from exc
            mesh_check = (
                checker_result.get('mesh_actual_exact_candidate_check')
                if isinstance(checker_result, dict)
                else None
            )
            counterfactual = (
                mesh_check.get('local_rhs_lu_counterfactual')
                if isinstance(mesh_check, dict)
                else None
            )
            report_arrays = report.get('persisted_evidence_arrays') if isinstance(report, dict) else None
            checker_arrays = (
                counterfactual.get('array_artifacts')
                if isinstance(counterfactual, dict)
                else None
            )
            if (
                not isinstance(report, dict)
                or report.get('schema') != 'task41.p0.v8.selected_trace_star_audit_receipt.v1'
                or report.get('status') != 'COMPLETED_SELECTED_TRACE_STAR_AUDIT'
                or not isinstance(checker_result, dict)
                or checker_result.get('schema') != 'task41.p0.b0.saved_evidence_audit.v1'
                or checker_result.get('status') != 'COMPLETE'
                or not isinstance(mesh_check, dict)
                or mesh_check.get('check_completed') is not True
                or not isinstance(report_arrays, list)
                or not report_arrays
                or not isinstance(checker_arrays, list)
                or not checker_arrays
                or hashlib.sha256(report_path.read_bytes()).hexdigest()
                != TASK41_P0_V9_V8_REPORT_SHA256
                or hashlib.sha256(checker_result_path.read_bytes()).hexdigest()
                != TASK41_P0_V9_V8_CHECKER_RESULT_SHA256
            ):
                raise ValueError('V9 saved-star input reports are incomplete or differ from their pinned identities')

            input_paths = [str(Path(argv[5]).resolve()), str(report_path), str(checker_result_path)]

            def append_saved_artifacts(entries: list[Any], *, base: Path, label: str) -> None:
                seen: set[Path] = set()
                for entry in entries:
                    if (
                        not isinstance(entry, dict)
                        or not isinstance(entry.get('path'), str)
                        or type(entry.get('bytes')) is not int
                        or not isinstance(entry.get('sha256'), str)
                        or not re.fullmatch(r'[0-9a-f]{64}', entry['sha256'])
                    ):
                        raise ValueError(f'V9 {label} array inventory is malformed')
                    raw_path = Path(entry['path'])
                    artifact_path = (raw_path if raw_path.is_absolute() else base / raw_path).resolve()
                    if (
                        artifact_path in seen
                        or not artifact_path.is_relative_to(base.resolve())
                        or not artifact_path.is_relative_to(results_root)
                        or not artifact_path.is_file()
                        or artifact_path.stat().st_size != entry['bytes']
                        or _sha256_file(artifact_path) != entry['sha256']
                    ):
                        raise ValueError(f'V9 {label} array path, size, or hash differs from its saved report')
                    seen.add(artifact_path)
                    input_paths.append(str(artifact_path))

            append_saved_artifacts(
                report_arrays, base=report_path.parent, label='V8 producer'
            )
            append_saved_artifacts(
                checker_arrays, base=checker_result_path.parent, label='V8 checker'
            )
        elif checker_kind == 'task41_p0_b0_saved_evidence_audit_checker':
            candidate_report_path = None
            candidate_report_sha256 = None
            if len(argv) == 22:
                if (
                    argv[18] != '--mesh-actual-exact-report'
                    or argv[20] != '--mesh-actual-exact-report-sha256'
                ):
                    raise ValueError('exact-geometry saved B0 checker report/hash options are malformed')
                candidate_report_path = Path(argv[19]).resolve()
                candidate_report_sha256 = argv[21]
            elif len(argv) != 18:
                raise ValueError('saved B0 evidence auditor command has an unexpected argument count')
            saved_v6_candidate_replay = (
                environment.get('TASK41_P0_B0_V6_SAVED_CANDIDATE_AUDIT') == '1'
            )
            v8_selected_trace_star = (
                environment.get('TASK41_P0_B0_V8_SELECTED_TRACE_STAR_AUDIT') == '1'
            )
            saved_v8_trace_star_replay = (
                environment.get('TASK41_P0_B0_V8_SAVED_TRACE_STAR_CHECKER') == '1'
            )
            v8_trace_star_report = v8_selected_trace_star or saved_v8_trace_star_replay
            exact_geometry_mode = candidate_report_path is not None
            v6_mode = (
                environment.get('TASK41_P0_B0_V6_ACTUAL_QMETRIC') == '1'
                or saved_v6_candidate_replay
            )
            if (
                environment.get('TASK41_P0_SAVED_B0_EVIDENCE_AUDIT') != '1'
                or environment.get('TASK41_P0_SAVED_OUTPUT_CONTINUATION') != '1'
                or environment.get('TASK41_P0_B0_V5_MESH_ACTUAL_EXACT')
                != (
                    '1'
                    if exact_geometry_mode
                    and not saved_v6_candidate_replay
                    and not v8_trace_star_report
                    else None
                )
                or environment.get('TASK41_P0_B0_V6_ACTUAL_QMETRIC')
                != ('1' if v6_mode and not saved_v6_candidate_replay else None)
                or (v8_trace_star_report and (not exact_geometry_mode or v6_mode))
                or (
                    v8_trace_star_report
                    and (
                        not isinstance(candidate_report_sha256, str)
                        or not re.fullmatch(r'[0-9a-f]{64}', candidate_report_sha256)
                        or environment.get('TASK41_P0_B0_V8_SELECTED_TRACE_STAR_REPORT_PATH')
                        != str(candidate_report_path)
                        or environment.get('TASK41_P0_B0_V8_SELECTED_TRACE_STAR_REPORT_SHA256')
                        != candidate_report_sha256
                        or (
                            v8_selected_trace_star
                            and environment.get('TASK41_P0_B0_V8_FFCX_C_SOURCE_PATH') is None
                        )
                        or (
                            saved_v8_trace_star_replay
                            and environment.get('TASK41_P0_B0_V8_FFCX_C_SOURCE_PATH') is not None
                        )
                    )
                )
                or (
                    not v8_trace_star_report
                    and (
                        environment.get('TASK41_P0_B0_V8_SELECTED_TRACE_STAR_REPORT_PATH')
                        is not None
                        or environment.get('TASK41_P0_B0_V8_SELECTED_TRACE_STAR_REPORT_SHA256')
                        is not None
                        or environment.get('TASK41_P0_B0_V8_FFCX_C_SOURCE_PATH') is not None
                    )
                )
                or (saved_v8_trace_star_replay and not exact_geometry_mode)
                or (saved_v8_trace_star_replay and v8_selected_trace_star)
                or (saved_v6_candidate_replay and not exact_geometry_mode)
                or (
                    saved_v6_candidate_replay
                    and (
                        not isinstance(candidate_report_sha256, str)
                        or not re.fullmatch(r'[0-9a-f]{64}', candidate_report_sha256)
                        or environment.get('TASK41_P0_B0_V6_CANDIDATE_REPORT_PATH')
                        != str(candidate_report_path)
                        or environment.get('TASK41_P0_B0_V6_CANDIDATE_REPORT_SHA256')
                        != candidate_report_sha256
                    )
                )
                or (
                    not saved_v6_candidate_replay
                    and (
                        environment.get('TASK41_P0_B0_V6_CANDIDATE_REPORT_PATH') is not None
                        or environment.get('TASK41_P0_B0_V6_CANDIDATE_REPORT_SHA256') is not None
                    )
                )
                or (v6_mode and not exact_geometry_mode)
                or Path(argv[0]).resolve() != expected_python
                or argv[1:3] != ['-m', 'src.runners.task41_p0_checker']
                or argv[3] != '--saved-b0-evidence-audit'
                or argv[4:18:2] != [
                    '--summary', '--numerical-output', '--contract', '--contract-sha256',
                    '--consumer-contract', '--consumer-contract-sha256', '--output',
                ]
                or argv[11] != environment.get('TASK41_P0_DONOR_CONTRACT_SHA256')
                or argv[13] != str(Path(str(contract_path)).resolve())
                or argv[15] != contract_sha
                or authorization.get('expected_channel_count') is not None
                or environment.get('TASK41_P0_CHECKER_SOURCE_SHA') != authorization.get('source_sha')
            ):
                raise ValueError('closeout command is not the registered saved B0 evidence auditor')
            from src.runners.task41_p0_contract import (
                require_task41_p0_contract, task41_case_id_for_run_id,
            )
            consumer_case = contract.get('case')
            donor_contract_path = Path(argv[9]).resolve()
            donor_summary_path = Path(argv[5]).resolve()
            donor_numerical_output = Path(argv[7]).resolve()
            output_path = Path(argv[17]).resolve()
            results_root = (root / 'results' / str(contract['case']['model_id'])).resolve()
            donor_contract_env = Path(environment.get('TASK41_P0_DONOR_CONTRACT_PATH', '')).resolve()
            donor_contract_sha = environment.get('TASK41_P0_DONOR_CONTRACT_SHA256')
            if (
                not isinstance(consumer_case, dict)
                or task41_case_id_for_run_id(str(consumer_case.get('run_id', ''))) != 'B0'
                or donor_contract_path != donor_contract_env
                or not re.fullmatch(r'[0-9a-f]{64}', str(donor_contract_sha or ''))
                or donor_summary_path != Path(environment.get('TASK41_P0_B0_SUMMARY_PATH', '')).resolve()
                or donor_summary_path.name != 'task40_v10_p6_candidate_summary.json'
                or donor_numerical_output != Path(environment.get('TASK41_P0_B0_NUMERICAL_OUTPUT_PATH', '')).resolve()
                or output_path != Path(environment.get('TASK41_P0_B0_RESULT_PATH', '')).resolve()
                or output_path.name != 'task41_p0_b0_saved_evidence_audit.json'
                or output_path.parent != Path(environment.get('TASK41_P0_B0_OUTPUT_DIR', '')).resolve()
                or not output_path.is_relative_to(results_root)
            ):
                raise ValueError('saved B0 evidence audit paths differ from the registered result directory')
            donor_contract, donor_digest = require_task41_p0_contract(
                donor_contract_path,
                expected_sha256=str(donor_contract_sha),
                current_root=root,
                check_current_source=False,
                require_clean_source=False,
            )
            donor_case = donor_contract.get('case')
            if (
                donor_digest != donor_contract_sha
                or not isinstance(donor_case, dict)
                or task41_case_id_for_run_id(str(donor_case.get('run_id', ''))) != 'B0'
                or any(donor_case.get(key) != consumer_case.get(key) for key in (
                    'model_id', 'method', 'mpi_size', 'input_sha256',
                    'physical_model_sha256', 'resolved_config_sha256',
                ))
            ):
                raise ValueError('saved B0 donor and consumer contract identities differ')
            donor_run_root = donor_summary_path.parent.resolve()
            donor_manifest = donor_run_root / 'run_manifest.json'
            donor_run_summary = donor_run_root / 'run_summary.json'
            resolved_config = donor_run_root / 'resolved_config.json'
            input_candidate = Path(str(consumer_case.get('input_path', '')))
            input_path = (input_candidate if input_candidate.is_absolute() else root / input_candidate).resolve()
            if (
                not donor_run_root.is_relative_to(results_root)
                or donor_numerical_output != (donor_run_root / 'numerical_output').resolve()
                or (donor_numerical_output.exists() and not donor_numerical_output.is_dir())
                or donor_run_root == output_path.parent
                or donor_run_root.is_relative_to(output_path.parent)
                or output_path.parent.is_relative_to(donor_run_root)
                or not donor_manifest.is_file()
                or not donor_run_summary.is_file()
                or not resolved_config.is_file()
                or not input_path.is_file()
                or hashlib.sha256(input_path.read_bytes()).hexdigest() != donor_case.get('input_sha256')
                or hashlib.sha256(resolved_config.read_bytes()).hexdigest() != donor_case.get('resolved_config_sha256')
            ):
                raise ValueError('saved B0 donor evidence paths or identity hashes are invalid')
            manifest_payload = json.loads(donor_manifest.read_text(encoding='utf-8'))
            summary_payload = json.loads(donor_run_summary.read_text(encoding='utf-8'))
            if (
                Path(str(manifest_payload.get('output_directory', ''))).resolve() != donor_run_root
                or Path(str(manifest_payload.get('numerical_output_directory', ''))).resolve() != donor_numerical_output
                or summary_payload.get('run_id') != donor_case.get('run_id')
            ):
                raise ValueError('saved B0 run manifest and summary do not identify the donor contract')
            input_paths = [str(path.resolve()) for path in (
                donor_contract_path, Path(str(contract_path)).resolve(), donor_summary_path,
                donor_manifest, donor_run_summary, input_path, resolved_config,
            )]
            if candidate_report_path is not None:
                if not v8_selected_trace_star:
                    from src.runners.task41_p0_v4_volume_only_audit import (
                        TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256,
                    )

                output_root = Path(environment.get('TASK41_P0_B0_OUTPUT_DIR', '')).resolve()
                expected_report_name = (
                    'task41_p0_v8_selected_trace_star_audit.json'
                    if v8_trace_star_report
                    else 'task41_p0_v6_actual_qmetric_candidate.json'
                    if v6_mode
                    else 'task41_p0_v5_mesh_actual_exact_attribution.json'
                )
                if (
                    candidate_report_path.name != expected_report_name
                    or not candidate_report_path.is_file()
                    or candidate_report_sha256 is None
                    or _sha256_file(candidate_report_path) != candidate_report_sha256
                    or (
                        not candidate_report_path.is_relative_to(results_root)
                        if saved_v6_candidate_replay or saved_v8_trace_star_replay
                        else not candidate_report_path.is_relative_to(output_root)
                    )
                ):
                    raise ValueError('exact-geometry candidate report path/hash differs from its registered route')
                candidate_report = json.loads(
                    candidate_report_path.read_text(encoding='utf-8')
                )
                candidate_identity = candidate_report.get('identity_audit')
                reference_path = (
                    None
                    if v8_trace_star_report
                    else Path(
                        str(candidate_report.get('geometry_reference_report_path', ''))
                    ).resolve(strict=True)
                )
                candidate_producer_contract_path = None
                candidate_producer_source_sha = None
                expected_candidate_contract_sha = contract_sha
                if saved_v6_candidate_replay or saved_v8_trace_star_replay:
                    from src.runners.task41_p0_checker import (
                        _task41_v6_candidate_producer_contract,
                    )

                    producer_contract, producer_digest = _task41_v6_candidate_producer_contract(
                        candidate_report_path,
                        expected_report_sha256=str(candidate_report_sha256),
                        consumer_contract=contract,
                        repo_root=root,
                    )
                    if not isinstance(producer_contract, dict) or not isinstance(producer_digest, str):
                        raise ValueError('saved V6/V8 candidate producer contract did not validate')
                    expected_candidate_contract_sha = producer_digest
                    candidate_producer_source_sha = producer_contract.get('source', {}).get('sha')
                    candidate_producer_contract_path = Path(
                        str(candidate_report.get('consumer_contract_path', ''))
                    ).resolve(strict=True)
                if (
                    candidate_report.get('schema')
                    != (
                        'task41.p0.v8.selected_trace_star_audit_receipt.v1'
                        if v8_trace_star_report
                        else 'task41.p0.v6.actual_qmetric_candidate_receipt.v1'
                        if v6_mode
                        else 'task41.p0.v5.mesh_actual_exact_attribution_receipt.v1'
                    )
                    or candidate_report.get('geometry_policy') != 'mesh_actual_exact'
                    or candidate_report.get('raw_tensor_evaluator')
                    != (
                        'actual_qmetric_blocked_gram'
                        if v6_mode or v8_trace_star_report
                        else None
                    )
                    or (v6_mode and not isinstance(candidate_identity, dict))
                    or (
                        v6_mode
                        and candidate_identity.get('candidate_evaluator_identity')
                        != 'task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1'
                    )
                    or candidate_report.get('donor_contract_sha256') != donor_digest
                    or candidate_report.get('consumer_contract_sha256')
                    != expected_candidate_contract_sha
                    or (
                        saved_v8_trace_star_replay
                        and candidate_report.get('consumer_source_sha')
                        != candidate_producer_source_sha
                    )
                    or (
                        not v8_trace_star_report
                        and (
                            reference_path is None
                            or reference_path.name != 'task41_p0_v4_geometry_pair_probe.json'
                            or not reference_path.is_relative_to(results_root)
                            or candidate_report.get('geometry_reference_report_sha256')
                            != TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256
                            or _sha256_file(reference_path)
                            != TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256
                            or environment.get('TASK41_P0_B0_V5_GEOMETRY_REFERENCE_PATH')
                            != str(reference_path)
                        )
                    )
                ):
                    raise ValueError('exact-geometry candidate report geometry/source identities are invalid')
                if v8_trace_star_report:
                    from src.runners.task41_p0_checker import (
                        _task41_v8_report_independent_checker_status,
                    )

                    selected_star = candidate_report.get('selected_trace_star_audit')
                    metadata = selected_star.get('metadata') if isinstance(selected_star, dict) else None
                    p3 = selected_star.get('p3_production_row_replay') if isinstance(selected_star, dict) else None
                    source_artifacts = selected_star.get('saved_operand_recomposition', {}).get('source_artifacts') if isinstance(selected_star, dict) and isinstance(selected_star.get('saved_operand_recomposition'), dict) else None
                    if (
                        candidate_report.get('status') != 'COMPLETED_SELECTED_TRACE_STAR_AUDIT'
                        or _task41_v8_report_independent_checker_status(
                            candidate_report,
                            expected_report_sha256=str(candidate_report_sha256),
                        ) != 'NOT_RUN'
                        or not isinstance(selected_star, dict)
                        or selected_star.get('schema') != 'task41.p0.v8.selected_trace_star_audit_result.v1'
                        or selected_star.get('status') != 'COMPLETED_SELECTED_TRACE_STAR_AUDIT'
                        or not isinstance(metadata, dict)
                        or not isinstance(p3, dict)
                        or p3.get('schema') != 'task41.p0.v8.selected_trace_star_p3_replay.v1'
                        or p3.get('complete_incident_cell_coverage') is not True
                        or type(p3.get('incident_cell_count')) is not int
                        or p3.get('incident_cell_count') < 1
                        or not isinstance(source_artifacts, dict)
                    ):
                        raise ValueError('V8 selected-star report receipt is incomplete')
                arrays = candidate_report.get('persisted_evidence_arrays')
                if not isinstance(arrays, list):
                    raise ValueError('exact-geometry candidate report lacks its persisted-array inventory')
                input_paths.append(str(candidate_report_path))
                if saved_v6_candidate_replay or saved_v8_trace_star_replay:
                    assert candidate_producer_contract_path is not None
                    input_paths.append(str(candidate_producer_contract_path))
                if not v8_trace_star_report:
                    assert reference_path is not None
                    input_paths.append(str(reference_path))
                array_root = (
                    candidate_report_path.parent.resolve()
                    if saved_v6_candidate_replay or saved_v8_trace_star_replay
                    else output_root
                )
                seen_array_paths = set()
                for artifact in arrays:
                    if not isinstance(artifact, dict) or not isinstance(artifact.get('path'), str):
                        raise ValueError('exact-geometry candidate persisted-array inventory is malformed')
                    artifact_path = Path(artifact['path']).resolve()
                    if (
                        not artifact_path.is_relative_to(array_root)
                        or artifact_path in seen_array_paths
                        or not artifact_path.is_file()
                        or artifact.get('bytes') != artifact_path.stat().st_size
                        or _sha256_file(artifact_path) != artifact.get('sha256')
                    ):
                        raise ValueError('exact-geometry candidate persisted-array path/size/hash is invalid')
                    seen_array_paths.add(artifact_path)
                    input_paths.append(str(artifact_path))
                if v8_trace_star_report:
                    from src.runners.task41_p0_v4_volume_only_audit import (
                        TASK41_P0_V8_V6_INDEX_SHA256,
                        TASK41_P0_V8_V6_REPORT_SHA256,
                        TASK41_P0_V8_V7_INDEX_SHA256,
                    )

                    source_artifacts = candidate_report['selected_trace_star_audit'][
                        'saved_operand_recomposition'
                    ]['source_artifacts']
                    expected_indexes = {
                        'v6_index': (
                            root / 'docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v6_actual_qmetric_hash_index_20261021.json',
                            TASK41_P0_V8_V6_INDEX_SHA256,
                        ),
                        'v7_index': (
                            root / 'docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v7_saved_attribution_20261021.json',
                            TASK41_P0_V8_V7_INDEX_SHA256,
                        ),
                    }
                    source_paths = {}
                    for key, (expected_path, expected_sha) in expected_indexes.items():
                        source_path = Path(str(source_artifacts.get(key, ''))).resolve()
                        if (
                            source_path != expected_path.resolve()
                            or source_artifacts.get(f'{key}_sha256') != expected_sha
                            or not source_path.is_file()
                            or _sha256_file(source_path) != expected_sha
                        ):
                            raise ValueError(f'V8 frozen {key} path/hash differs from its registered source')
                        source_paths[key] = source_path
                    for key in ('v6_report', 'v7_report'):
                        source_path = Path(str(source_artifacts.get(key, ''))).resolve()
                        source_sha = source_artifacts.get(f'{key}_sha256')
                        if (
                            not source_path.is_relative_to(results_root)
                            or not source_path.is_file()
                            or not isinstance(source_sha, str)
                            or not re.fullmatch(r'[0-9a-f]{64}', source_sha)
                            or _sha256_file(source_path) != source_sha
                        ):
                            raise ValueError(f'V8 saved {key} path/hash differs from its registered results tree')
                        source_paths[key] = source_path
                    # Source indexes/reports are authorized before their explicitly named arrays.
                    input_paths.extend(str(source_paths[key]) for key in ('v6_index', 'v6_report', 'v7_index', 'v7_report'))
                    for arrays_key in ('v6_arrays', 'v7_arrays'):
                        source_arrays = source_artifacts.get(arrays_key)
                        if not isinstance(source_arrays, dict) or not source_arrays:
                            raise ValueError(f'V8 {arrays_key} inventory is missing')
                        for artifact in source_arrays.values():
                            if not isinstance(artifact, dict) or not isinstance(artifact.get('path'), str):
                                raise ValueError(f'V8 {arrays_key} artifact is malformed')
                            artifact_path = Path(artifact['path']).resolve()
                            if (
                                not artifact_path.is_relative_to(results_root)
                                or not artifact_path.is_file()
                                or artifact.get('bytes') != artifact_path.stat().st_size
                                or not isinstance(artifact.get('sha256'), str)
                                or _sha256_file(artifact_path) != artifact.get('sha256')
                            ):
                                raise ValueError(f'V8 {arrays_key} path/size/hash differs from its registered results tree')
                            input_paths.append(str(artifact_path))
        elif checker_kind == 'task41_p0_saved_output_continuation_checker':
            checker_only = (
                environment.get('TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY') == '1'
            )
            authorized_input_hashes = authorization.get('input_sha256s')
            if (
                environment.get('TASK41_P0_SAVED_OUTPUT_CONTINUATION') != '1'
                or len(argv) != 11
                or Path(argv[0]).resolve() != expected_python
                or argv[1:3] != ['-m', 'src.runners.task41_p0_checker']
                or argv[3::2]
                != [
                    '--saved-output-continuation-input', '--contract',
                    '--contract-sha256', '--output',
                ]
                or argv[8] != contract_sha
            ):
                raise ValueError('closeout command is not the registered saved-output Task41 checker')
            snapshot_path = Path(argv[4]).resolve()
            results_root = (root / 'results' / str(contract['case']['model_id'])).resolve()
            output_path = Path(argv[10]).resolve()
            expected_output = (
                Path(environment.get('TASK41_P0_CHECKER_RESULT_PATH', '')).resolve()
                if checker_only
                else (
                    snapshot_path.parent / 'task41_p0_saved_output_checker_result.json'
                ).resolve()
            )
            if (
                snapshot_path.name != 'task41_p0_saved_output_checker_input.json'
                or not snapshot_path.is_relative_to(results_root)
                or output_path != expected_output
                or Path(argv[6]).resolve() != Path(str(contract_path)).resolve()
                or (
                    checker_only
                    and (
                        output_path.name != 'task41_p0_saved_output_checker_result.json'
                        or not output_path.is_relative_to(results_root)
                        or output_path.parent == snapshot_path.parent
                        or Path(environment.get('TASK41_P0_CHECKER_INPUT_PATH', '')).resolve()
                        != snapshot_path
                        or not isinstance(authorized_input_hashes, list)
                        or len(authorized_input_hashes) != 1
                        or environment.get('TASK41_P0_CHECKER_INPUT_SHA256')
                        != authorized_input_hashes[0]
                        or environment.get('TASK41_P0_CHECKER_SOURCE_SHA')
                        != authorization.get('source_sha')
                    )
                )
            ):
                raise ValueError('saved-output checker paths do not match the Task41 result directory')
            input_paths = [str(snapshot_path)]
        else:
            from src.runners.task41_p0_contract import (
                task41_case_id_for_run_id,
                task41_p0_checker_kind_for_case,
            )

            case = contract.get('case')
            if not isinstance(case, dict):
                raise ValueError('Task41 checker contract has no registered case identity')
            try:
                case_id = task41_case_id_for_run_id(str(case.get('run_id', '')))
            except ValueError as exc:
                raise ValueError('Task41 checker contract case is not registered') from exc
            expected_checker_kind = task41_p0_checker_kind_for_case(case_id)
            if checker_kind != expected_checker_kind:
                raise ValueError('closeout command is not the registered Task41 checker for its contract case')
            if (
                len(argv) != 17
                or argv[1:3] != ['-m', 'src.runners.task41_p0_checker']
                or argv[3::2]
                != [
                    '--input', '--summary', '--manifest', '--numerical-output',
                    '--contract', '--contract-sha256', '--output',
                ]
                or argv[14] != contract_sha
                or authorization.get('expected_channel_count') is not None
            ):
                raise ValueError('closeout command is not the registered Task41 checker for its contract case')
            input_path, summary_path, manifest_path = (Path(argv[index]).resolve() for index in (4, 6, 8))
            numerical_directory = Path(argv[10]).resolve()
            contract_case_input = Path(str(case.get('input_path', '')))
            expected_input_path = (
                contract_case_input if contract_case_input.is_absolute()
                else root / contract_case_input
            ).resolve()
            manifest_root = manifest_path.parent.resolve()
            results_root = (root / 'results' / str(case.get('model_id', ''))).resolve()
            expected_output = Path(str(contract.get('evidence', {}).get('service_directory', '')))
            if not expected_output.is_absolute():
                expected_output = root / expected_output
            expected_output = (expected_output / 'task41_p0_checker_result.json').resolve()
            if (
                Path(argv[0]).resolve() != expected_python
                or input_path != expected_input_path
                or not manifest_path.is_relative_to(results_root)
                or manifest_path.name != 'run_manifest.json'
                or not summary_path.is_relative_to(manifest_root)
                or not numerical_directory.is_relative_to(manifest_root)
                or numerical_directory.name != 'numerical_output'
            ):
                raise ValueError('Task41 checker command paths do not match the registered contract case')
            numerical_summary = (
                manifest_root / 'task40_v10_p6_candidate_summary.json'
                if case_id in {'A2', 'B0'}
                else numerical_directory / 'run_summary.json'
            )
            input_paths = [
                str(input_path), str(summary_path), str(manifest_path), str(numerical_summary)
            ]
            if any(not Path(path).is_relative_to(root) for path in input_paths):
                raise ValueError('Task41 checker inputs escaped the registered repository')
            if not numerical_directory.is_dir():
                raise ValueError('Task41 numerical-output directory is missing')
            if (
                Path(argv[12]).resolve() != Path(str(contract_path)).resolve()
                or Path(argv[16]).resolve() != expected_output
            ):
                raise ValueError('Task41 checker contract or output path differs from the contract')
    else:
        raise ValueError('numeric or arbitrary commands cannot use the closeout reserve')
    if authorization.get('input_paths') != input_paths:
        raise ValueError('closeout checker input paths differ from the authorized command')
    input_sha256s = authorization.get('input_sha256s')
    if not isinstance(input_sha256s, list) or len(input_sha256s) != len(input_paths):
        raise ValueError('closeout checker input hashes are incomplete')
    for raw_path, expected_sha in zip(input_paths, input_sha256s, strict=True):
        path = Path(raw_path)
        if (
            not path.is_file()
            or not re.fullmatch(r'[0-9a-f]{64}', str(expected_sha))
            or _sha256_file(path) != expected_sha
        ):
            raise ValueError('closeout checker input hash changed after service authorization')

    if checker_kind == 'task40_v20_partial_receipt_checker' and numerical_output_missing:
        from scripts.task40_v20_service_workflow import (
            _v31_missing_numerical_output_is_bound_worker_failure,
        )

        if not _v31_missing_numerical_output_is_bound_worker_failure(
            input_path=Path(argv[4]).resolve(),
            summary_path=Path(argv[6]).resolve(),
            manifest_path=Path(argv[8]).resolve(),
            numerical_path=numerical_path,
            repo_root=Path.cwd(),
            source_sha=str(authorization['source_sha']),
            campaign_sha256=str(campaign.sha256),
            campaign_window_path=Path(str(window_path)),
        ):
            raise ValueError(
                'missing partial checker numerical output is not bound to a V31 worker failure'
            )

    source_head = subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=Path.cwd(), check=True, capture_output=True, text=True
    ).stdout.strip()
    source_branch = subprocess.run(
        ['git', 'branch', '--show-current'], cwd=Path.cwd(), check=True, capture_output=True, text=True
    ).stdout.strip()
    source_status = subprocess.run(
        ['git', 'status', '--porcelain', '--untracked-files=normal'],
        cwd=Path.cwd(), check=True, capture_output=True, text=True
    ).stdout
    if (
        source_head != authorization['source_sha']
        or source_branch != authorization['source_branch']
        or source_status.strip()
    ):
        raise ValueError('closeout checker source changed after service authorization')
    return dict(authorization)


def memory_envelope(
    memory_policy: str = LEGACY_MEMORY_POLICY,
    *,
    host_reserve_bytes: int | None = None,
    task_cgroup_reserve_bytes: int | None = None,
    require_cgroup_memory_details: bool = False,
) -> dict:
    if memory_policy not in {
        LEGACY_MEMORY_POLICY,
        PHYSICAL_MEMORY_PRESSURE_POLICY,
    }:
        raise ValueError(f"unsupported watchdog memory policy: {memory_policy!r}")
    memory = wsl_memory_snapshot()
    total, available = memory["mem_total_bytes"], memory["mem_available_bytes"]
    if total is None or available is None:
        raise RuntimeError("physical memory authority unavailable")
    host_available = int(available)
    task_cgroup_available = None
    ancestors = []
    cgroup_memory_stats = []
    path = current_cgroup_path()
    while path is not None and path.is_relative_to('/sys/fs/cgroup'):
        maximum, current = path / 'memory.max', path / 'memory.current'
        raw_limit = None
        used = None
        if maximum.is_file():
            raw_limit = maximum.read_text().strip()
            if current.is_file():
                used = int(current.read_text())
        stat_values = None
        stat_path = path / 'memory.stat'
        if require_cgroup_memory_details and raw_limit is not None:
            if raw_limit != 'max' and (used is None or not stat_path.is_file()):
                raise RuntimeError(
                    f"required cgroup memory details are unreadable at {path}"
                )
            if used is not None and stat_path.is_file():
                stat_values = {}
                for line in stat_path.read_text(encoding='ascii').splitlines():
                    fields = line.split()
                    if len(fields) == 2 and fields[0] in {'anon', 'file', 'file_dirty'}:
                        try:
                            stat_values[fields[0]] = int(fields[1])
                        except ValueError as exc:
                            raise RuntimeError(
                                f"invalid cgroup memory.stat value at {path}"
                            ) from exc
            if raw_limit != 'max' and (
                stat_values is None
                or set(stat_values) != {'anon', 'file', 'file_dirty'}
            ):
                raise RuntimeError(
                    f"required anon/file/file_dirty counters are missing at {path}"
                )
            if stat_values is not None:
                cgroup_memory_stats.append(
                    {
                        'path': str(path),
                        'limit_bytes': None if raw_limit == 'max' else int(raw_limit),
                        'current_bytes': used,
                        'anon_bytes': stat_values['anon'],
                        'file_bytes': stat_values['file'],
                        'file_dirty_bytes': stat_values['file_dirty'],
                    }
                )
        if maximum.is_file():
            if raw_limit != 'max':
                limit = int(raw_limit)
                if used is None:
                    raise RuntimeError(f"cgroup memory.current is unreadable at {path}")
                total = min(total, limit)
                cgroup_available = max(0, limit - used)
                available = min(available, cgroup_available)
                task_cgroup_available = (
                    cgroup_available
                    if task_cgroup_available is None
                    else min(task_cgroup_available, cgroup_available)
                )
                ancestor = {'path': str(path), 'limit_bytes': limit, 'current_bytes': used}
                if require_cgroup_memory_details:
                    if stat_values is None:
                        raise RuntimeError(
                            f"required cgroup memory.stat counters are missing at {path}"
                        )
                    ancestor.update(
                        {
                            'anon_bytes': stat_values['anon'],
                            'file_bytes': stat_values['file'],
                            'file_dirty_bytes': stat_values['file_dirty'],
                        }
                    )
                ancestors.append(ancestor)
        if path == Path('/sys/fs/cgroup'):
            break
        path = path.parent
    if memory_policy == PHYSICAL_MEMORY_PRESSURE_POLICY:
        reserve = (
            PHYSICAL_MEMORY_EVIDENCE_RESERVE_BYTES
            if host_reserve_bytes is None
            else int(host_reserve_bytes)
        )
        if reserve < 0:
            raise ValueError("host reserve must be nonnegative")
        if task_cgroup_reserve_bytes is None:
            launch_cap = available - reserve
            task_cgroup_reserve = reserve
            reserve_reason = (
                "small watchdog/evidence-write reserve; no legacy 4GiB or "
                "15-percent reserve"
            )
            split_reserve_domains = False
        else:
            task_cgroup_reserve = int(task_cgroup_reserve_bytes)
            if task_cgroup_reserve < 0:
                raise ValueError("task cgroup reserve must be nonnegative")
            task_available = (
                host_available
                if task_cgroup_available is None
                else int(task_cgroup_available)
            )
            host_room = max(0, host_available - reserve)
            task_room = max(0, task_available - task_cgroup_reserve)
            launch_cap = min(host_room, task_room)
            reserve_reason = (
                "V29 separate domains: host MemAvailable minus host reserve; "
                "task/ancestor cgroup remaining minus task-cgroup reserve"
            )
            split_reserve_domains = True
        static_tree_cap = None
    else:
        reserve = (
            max(4 * 1024**3, int(.15 * total))
            if host_reserve_bytes is None
            else int(host_reserve_bytes)
        )
        if reserve < 0:
            raise ValueError("host reserve must be nonnegative")
        launch_cap = min(12_000_000_000, available - reserve)
        task_cgroup_reserve = reserve
        split_reserve_domains = False
        reserve_reason = "legacy max(4GiB,0.15*effective_total) reserve"
        static_tree_cap = 12_000_000_000
    if task_cgroup_available is None:
        task_cgroup_available = host_available
    result = {**memory, 'effective_total_bytes': total,
            'effective_available_bytes': available, 'host_mem_available_bytes': host_available,
            'task_cgroup_available_bytes': int(task_cgroup_available),
            'host_launch_available_bytes': max(0, host_available - reserve),
            'task_cgroup_reserve_bytes': (
                task_cgroup_reserve if split_reserve_domains else None
            ),
            'task_cgroup_launch_available_bytes': (
                max(0, int(task_cgroup_available) - task_cgroup_reserve)
                if split_reserve_domains
                else None
            ),
            'reserve_domains_separated': split_reserve_domains,
            'effective_available_after_reserves_bytes': max(0, int(launch_cap)),
            'effective_available_bytes': available, 'reserve_bytes': reserve,
            'launch_cap_bytes': launch_cap,
            'memory_policy': memory_policy,
            'reserve_reason': reserve_reason,
            'static_tree_cap_bytes': static_tree_cap,
            'cgroup_limits': ancestors}
    if require_cgroup_memory_details:
        result['cgroup_memory_stats'] = cgroup_memory_stats
    return result


def reserve_violation(envelope: Mapping[str, Any]) -> bool:
    """Return whether an available-memory reserve is actually exhausted.

    Split-domain envelopes keep host MemAvailable and task/ancestor cgroup
    headroom separate.  The host reserve applies only to the host domain;
    applying it again to ``effective_available_bytes`` would incorrectly
    compare it with whichever domain happens to be smaller.
    """
    if envelope.get("reserve_domains_separated") is True:
        return (
            int(envelope["host_mem_available_bytes"])
            < int(envelope["reserve_bytes"])
            or int(envelope["task_cgroup_available_bytes"])
            < int(envelope["task_cgroup_reserve_bytes"] or 0)
        )
    return int(envelope["effective_available_bytes"]) < int(
        envelope["reserve_bytes"]
    )


def _children() -> dict[int, tuple[int, int]]:
    """Current descendants with (parent, start ticks), excluding this parent."""
    records = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            records[int(entry.name)] = (int(fields[1]), int(fields[19]))
        except (FileNotFoundError, ProcessLookupError):
            continue
    descendants = {os.getpid()}
    while True:
        found = {pid for pid, (ppid, _) in records.items() if ppid in descendants}
        extended = descendants | found
        if extended == descendants:
            break
        descendants = extended
    descendants.remove(os.getpid())
    return {pid: records[pid] for pid in descendants}


def _signal_children(signum: int) -> None:
    # Re-discover every pass: no stale PID may target an unrelated process.
    for pid, identity in _children().items():
        try:
            fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[19]) == identity[1]:
                os.kill(pid, signum)
        except ProcessLookupError:
            pass
        except FileNotFoundError:
            pass


def _reap_adopted(leader_pid: int) -> None:
    for pid, (ppid, _) in _children().items():
        if ppid == os.getpid() and pid != leader_pid:
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass


def _request_cooperative_stop(phase: dict, leader_pid: int) -> dict:
    """Signal the registered application once, never its MPI launcher."""
    worker = phase.get('application_worker', {})
    pid, ticks = worker.get('pid'), worker.get('start_ticks')
    children = _children()
    if (not isinstance(pid, int) or not isinstance(ticks, int) or pid == leader_pid
            or pid not in children or children[pid][1] != ticks):
        raise RuntimeError('cooperative application identity is not in the current child tree')
    current = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    if int(current[19]) != ticks:
        raise RuntimeError('cooperative application identity changed before signal')
    os.kill(pid, signal.SIGTERM)
    return dict(worker_pid=pid, start_ticks=ticks, signal='SIGTERM', request_count=1,
                monotonic=time.monotonic(), timestamp_ns=time.time_ns())


def _cache_stamp(path: Path | None) -> str:
    """Metadata stability after all descendants are reaped, not a cache hash."""
    digest = hashlib.sha256()
    if path is not None and path.exists():
        for file in sorted(path.rglob('*')):
            try:
                info = file.stat()
                if file.is_file():
                    digest.update(f'{file.relative_to(path)}:{info.st_size}:{info.st_mtime_ns}\n'.encode())
            except FileNotFoundError:
                continue
    return digest.hexdigest()


def global_swap_stop(baseline, current, *, enabled=False):
    """V6 opt-in: global activity stops pressure without claiming attribution."""
    if not enabled:
        return None
    if any(baseline.get(k) is None or current.get(k) is None for k in baseline):
        return 'MONITORING_FAILED'
    if any(current[k] > baseline[k] for k in baseline):
        return 'GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED'
    return None


def _external_guard_stop_reason(first_reason, facts):
    """Apply an external stop without overwriting the first observed cause."""
    if not isinstance(facts, dict) or type(facts.get('stop')) is not bool:
        return first_reason or 'MONITORING_FAILED'
    if facts['stop'] is not True:
        return first_reason
    reason = facts.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        return first_reason or 'MONITORING_FAILED'
    return first_reason or reason


def stop_signal(reason, *, hard_stop_immediate, elapsed, grace_seconds):
    hard = hard_stop_immediate and reason in ('RESOURCE_CONTROLLED_STOP', 'MONITORING_FAILED', 'TIMEBASE_INCONSISTENCY', 'GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED', 'PC_TIME_CONTROLLED_STOP')
    return signal.SIGTERM if not hard and elapsed < grace_seconds else signal.SIGKILL


def runtime_tree_cap(start_cap_bytes: int, process_tree_rss_bytes: int,
                     envelope: dict, *, explicit_tree_cap_bytes: int | None = None,
                     memory_policy: str = LEGACY_MEMORY_POLICY) -> int:
    """Return a non-increasing runtime cap without double-counting RSS.

    ``memory_envelope()['launch_cap_bytes']`` is free memory after the
    reserve, whereas the process-tree sample is already occupied memory.
    Adding the two gives the current total-capacity estimate; comparing RSS
    directly with free memory would subtract the current job a second time.
    """
    if memory_policy not in {
        LEGACY_MEMORY_POLICY,
        PHYSICAL_MEMORY_PRESSURE_POLICY,
    }:
        raise ValueError(f"unsupported watchdog memory policy: {memory_policy!r}")
    if envelope.get('reserve_domains_separated') is True:
        current_capacity = int(process_tree_rss_bytes) + int(
            envelope['effective_available_after_reserves_bytes']
        )
    else:
        current_capacity = (
            int(process_tree_rss_bytes)
            + int(envelope['effective_available_bytes'])
            - int(envelope['reserve_bytes'])
        )
    if memory_policy == PHYSICAL_MEMORY_PRESSURE_POLICY:
        # V23 keeps a live available-memory limit; a caller may additionally
        # impose a fixed absolute RSS ceiling for a separately reviewed campaign.
        return (
            min(current_capacity, int(explicit_tree_cap_bytes))
            if explicit_tree_cap_bytes is not None
            else current_capacity
        )
    limits = [int(start_cap_bytes), current_capacity]
    if explicit_tree_cap_bytes is not None:
        limits.append(int(explicit_tree_cap_bytes))
    return min(limits)


def supervise(command: list[str], directory: Path, *, wall_seconds: float,
              interval: float = .25, grace_seconds: float = 2.0,
              cache_path: Path | None = None, phase_path: Path | None = None,
              solve_seconds: float | None = None, source_state: dict | None = None,
              worker_environment: dict | None = None, hard_stop_immediate: bool = False,
              cooperative_performance_stop: bool = False,
              timebase_guard: bool = False, timebase_policy: str = STRICT,
              stop_on_global_swap: bool = False,
              allow_swap_observation: bool = False,
              tree_cap_bytes: int | None = None,
              active_pc_seconds: float | None = None,
              time_policy: str = V14_TIME_POLICY_ENFORCE,
              memory_policy: str = LEGACY_MEMORY_POLICY,
              pss_sampling_policy: str = 'sampled',
              allow_physical_pressure_tree_cap: bool = False,
              external_guard=None,
              campaign_window_path: Path | None = None,
              campaign_window_sha256: str | None = None,
              campaign_accounting_path: Path | None = None,
              campaign_phase: str = 'numeric',
              campaign_phase_authorization: dict[str, Any] | None = None,
              require_job_cgroup_zero_swap: bool = False,
              require_cgroup_memory_details: bool = False,
              host_reserve_bytes: int | None = None,
              task_cgroup_reserve_bytes: int | None = None,
              tree_accounting_root_pid: int | None = None) -> dict:
    """Supervise one command, with an explicit workflow wall budget."""
    try:
        time_policy = normalize_v14_time_policy(time_policy)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if memory_policy not in {
        LEGACY_MEMORY_POLICY,
        PHYSICAL_MEMORY_PRESSURE_POLICY,
    }:
        raise ValueError(f"unsupported watchdog memory policy: {memory_policy!r}")
    if pss_sampling_policy not in {'sampled', 'disabled_by_profile'}:
        raise ValueError(
            f"unsupported watchdog PSS policy: {pss_sampling_policy!r}"
        )
    if not command or any(
        not math.isfinite(float(value)) or float(value) <= 0.0
        for value in (wall_seconds, interval, grace_seconds)
    ):
        raise ValueError('command and positive monitoring budgets are required')
    if solve_seconds is not None and (
        not math.isfinite(float(solve_seconds)) or float(solve_seconds) <= 0.0
    ):
        raise ValueError('solve_seconds must be finite and positive when supplied')
    if tree_cap_bytes is not None and int(tree_cap_bytes) <= 0:
        raise ValueError('tree_cap_bytes must be positive when supplied')
    if tree_accounting_root_pid is not None:
        if (
            type(tree_accounting_root_pid) is not int
            or tree_accounting_root_pid <= 0
        ):
            raise ValueError('tree_accounting_root_pid must be a positive PID')
        if tree_accounting_root_pid != os.getppid():
            raise RuntimeError(
                'tree_accounting_root_pid must be the current user-service parent'
            )
    if (
        memory_policy == PHYSICAL_MEMORY_PRESSURE_POLICY
        and tree_cap_bytes is not None
        and not allow_physical_pressure_tree_cap
    ):
        raise ValueError(
            'physical memory pressure policy requires explicit authorization '
            'before receiving a fixed tree_cap_bytes'
        )
    if allow_physical_pressure_tree_cap and memory_policy != PHYSICAL_MEMORY_PRESSURE_POLICY:
        raise ValueError(
            'fixed Task40 V10 tree cap authorization requires physical memory pressure policy'
        )
    if allow_swap_observation and stop_on_global_swap:
        raise ValueError(
            'swap observation-only mode cannot enforce the global swap gate'
        )
    if require_job_cgroup_zero_swap and allow_swap_observation:
        raise ValueError(
            'Task40 job cgroup zero-swap enforcement cannot be disabled by observation mode'
        )
    if type(require_cgroup_memory_details) is not bool:
        raise TypeError('require_cgroup_memory_details must be a bool')
    if external_guard is not None and not callable(external_guard):
        raise TypeError('external_guard must be callable when supplied')
    if campaign_phase not in {'numeric', 'closeout'}:
        raise ValueError('campaign phase must be numeric or closeout')
    if campaign_phase == 'closeout' and campaign_window_path is None:
        raise ValueError('Task40 closeout phase requires a fixed campaign window')
    if campaign_phase == 'numeric' and campaign_phase_authorization is not None:
        raise ValueError('numeric phase cannot carry a closeout checker authorization')
    if active_pc_seconds is not None and (
            not 0 < float(active_pc_seconds) < float('inf') or
            phase_path is None or not timebase_guard or not hard_stop_immediate):
        raise ValueError('active PC limit requires positive seconds, a phase file, '
                         'guarded clocks and immediate hard stopping')
    if cooperative_performance_stop and (phase_path is None or not hard_stop_immediate or grace_seconds > 60):
        raise ValueError('cooperative stop requires phase registration, immediate hard gates and grace <=60s')
    campaign = None
    campaign_account = None
    campaign_start_record = None
    if campaign_window_path is not None:
        from src.runners.task40_v10_campaign import CampaignAccount, load_fixed_campaign_window

        task41_environment = dict(worker_environment or {})
        if task41_environment.get('TASK41_P0_STRICT_EXECUTION') == '1':
            from src.runners.task41_p0_contract import (
                load_task41_p0_fixed_window,
                require_task41_p0_contract,
            )

            contract_path = task41_environment.get('TASK41_P0_CONTRACT_PATH')
            contract_sha = task41_environment.get('TASK41_P0_CONTRACT_SHA256')
            if not contract_path or not contract_sha:
                raise ValueError('Task41 watchdog environment omits its fixed contract')
            continuation_flag = task41_environment.get('TASK41_P0_SAVED_OUTPUT_CONTINUATION')
            continuation = continuation_flag == '1'
            if continuation_flag not in {None, '1'} or (
                continuation
                != (task41_environment.get('TASK41_P0_CONSUMER_SOURCE_SHA') is not None)
            ):
                raise ValueError('Task41 continuation source markers are incomplete')
            task41_contract, actual_contract_sha = require_task41_p0_contract(
                contract_path,
                expected_sha256=contract_sha,
                current_root=Path.cwd(),
                check_current_source=not continuation,
                require_clean_source=True,
            )
            if continuation:
                _validate_task41_consumer_source(task41_contract, task41_environment)
            campaign = load_task41_p0_fixed_window(
                task41_contract, current_root=Path.cwd(), require_current_boot=True
            )
            task41_resources = task41_contract['resources']
            if (
                actual_contract_sha != contract_sha
                or campaign_window_path.resolve() != campaign.path.resolve()
                or campaign_window_sha256 != campaign.sha256
                or Path(task41_environment.get('TASK41_P0_EXECUTION_WINDOW_PATH', '')).resolve()
                != campaign.path.resolve()
                or task41_environment.get('TASK41_P0_EXECUTION_WINDOW_SHA256')
                != campaign.sha256
                or task41_environment.get('TASK41_P0_TASK_MEMORY_MAX_BYTES')
                != str(task41_resources['task_memory_max_bytes'])
                or task41_environment.get('TASK41_P0_HOST_RESERVE_BYTES')
                != str(task41_resources['host_reserve_bytes'])
                or task41_environment.get('TASK41_P0_MEMORY_SWAP_MAX_BYTES')
                != str(task41_resources['memory_swap_max_bytes'])
            ):
                raise ValueError('Task41 watchdog window or resource bindings differ from contract')
        else:
            campaign = load_fixed_campaign_window(campaign_window_path)
        if campaign_window_sha256 != campaign.sha256:
            raise ValueError('campaign window hash differs from the run_case launch contract')
        if campaign_accounting_path is not None and campaign_accounting_path.resolve() != campaign.accounting_path:
            raise ValueError('campaign accounting path differs from the fixed window')
        if campaign_phase == 'closeout':
            campaign_phase_authorization = _validate_campaign_closeout_authorization(
                command=command,
                campaign=campaign,
                authorization=campaign_phase_authorization,
                worker_environment=worker_environment,
            )
        if not timebase_guard or timebase_policy != 'conservative_realtime':
            raise ValueError('Task40 V10 requires the existing conservative-realtime watchdog guard')
        if time_policy != V14_TIME_POLICY_ENFORCE:
            raise ValueError('Task40 V10 campaign time must be enforced')
        campaign_account = CampaignAccount(campaign, campaign_accounting_path)
        campaign_start_record = campaign_account.record_sample(
            label=f'watchdog_start_{campaign_phase}', phase=campaign_phase
        )
        now_utc_ns = int(campaign_start_record['sample']['utc_ns'])
        phase_termination_reserve = (
            float(grace_seconds) + CAMPAIGN_CLOSEOUT_PARENT_FLUSH_RESERVE_SECONDS
            if campaign_phase == 'closeout'
            else 0.0
        )
        budget_remaining = campaign.remaining_seconds(
            phase=campaign_phase,
            cumulative_charged_seconds=float(
                campaign_start_record['cumulative_charged_seconds']
            ),
            now_utc_ns=now_utc_ns,
            sub_budget_seconds=float(wall_seconds),
            termination_reserve_seconds=phase_termination_reserve,
        )
        wall_seconds = min(float(wall_seconds), budget_remaining)
        if not math.isfinite(wall_seconds) or wall_seconds <= 0.0:
            raise TimebaseInconsistency(
                f'Task40 campaign has no remaining time in {campaign_phase} phase'
            )
    job_cgroup_start = (
        cgroup_snapshot(os.getpid()) if require_job_cgroup_zero_swap else None
    )
    if require_job_cgroup_zero_swap and (
        not isinstance(job_cgroup_start, dict)
        or job_cgroup_start.get('dedicated_job_cgroup') is not True
        or job_cgroup_start.get('readable') is not True
        or not isinstance(job_cgroup_start.get('swap_current_bytes'), int)
        or isinstance(job_cgroup_start.get('swap_current_bytes'), bool)
    ):
        raise RuntimeError(
            'Task40 requires a readable dedicated service cgroup with swap.current authority'
        )
    if require_job_cgroup_zero_swap and job_cgroup_start['swap_current_bytes'] != 0:
        raise RuntimeError(
            'Task40 service cgroup has nonzero memory.swap.current before worker launch'
        )
    libc = ctypes.CDLL(None, use_errno=True)
    # PR_SET_CHILD_SUBREAPER; Linux-only, intentionally no platform fallback.
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'cannot enable child subreaper')
    if _children():
        raise RuntimeError('watchdog must be a dedicated parent with no existing children')
    directory.mkdir(parents=True, exist_ok=False)
    envelope = memory_envelope(
        memory_policy,
        host_reserve_bytes=host_reserve_bytes,
        task_cgroup_reserve_bytes=task_cgroup_reserve_bytes,
        require_cgroup_memory_details=require_cgroup_memory_details,
    )
    dynamic_cap = int(envelope['launch_cap_bytes'])
    if task_cgroup_reserve_bytes is not None:
        initial_tree = process_tree_snapshot(
            tree_accounting_root_pid if tree_accounting_root_pid is not None else os.getpid(),
            'watchdog_initial_resource_gate',
            pss_sampling_policy=pss_sampling_policy,
        )
        initial_tree_rss = initial_tree.get('rss_bytes')
        if (
            initial_tree.get('all_status_readable') is not True
            or initial_tree.get('identity_complete') is not True
            or type(initial_tree_rss) is not int
        ):
            raise RuntimeError("V29 initial process-tree memory authority is unavailable")
        dynamic_cap = runtime_tree_cap(
            int(tree_cap_bytes) if tree_cap_bytes is not None else dynamic_cap,
            int(initial_tree_rss),
            envelope,
            explicit_tree_cap_bytes=tree_cap_bytes,
            memory_policy=memory_policy,
        )
    cap = (
        min(dynamic_cap, int(tree_cap_bytes))
        if tree_cap_bytes is not None
        else dynamic_cap
    )
    if tree_cap_bytes is not None:
        envelope = {
            **envelope,
            'dynamic_launch_cap_bytes': dynamic_cap,
            'launch_cap_bytes': cap,
            'tree_cap_bytes': int(tree_cap_bytes),
            'cap_policy': (
                'min(split_domain_dynamic_process_tree_cap, explicit_tree_cap)'
                if task_cgroup_reserve_bytes is not None
                else 'min(dynamic_memory_envelope, explicit_tree_cap)'
            ),
        }
    if cap <= 0:
        raise RuntimeError('no safe launch memory budget')
    requested_signal = []
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda value, _frame: requested_signal.append(value))
    started = time.monotonic()
    stop_started = None
    classification = None
    peak_rss = peak_swap = 0
    samples = 0
    stable_since = None
    cache_stamp = None
    observed = set()
    observed_child_identities: set[tuple[int, int]] = set()
    sampled_child_identities: set[tuple[int, int]] = set()
    job_cgroup_swap_sample_count = 0
    job_cgroup_swap_peak_bytes = 0
    process_tree_all_status_readable = True
    process_tree_all_identity_complete = True
    process_tree_identity_sample_count = 0
    workflow_time_exceeded = False
    solve_time_exceeded = False
    pc_time_exceeded = False
    leader = None
    summary = {}
    clock_start = clock_sample() if timebase_guard else None
    clock_budget = ClockBudget(clock_start, policy=timebase_policy) if timebase_guard else None
    solve_budget = None
    pc_budget = None
    stop_clock = None
    if timebase_guard:
        summary.update(clock_info=clock_info(), clock_start=clock_start,
                       timebase_policy=timebase_policy, timebase_policy_version=POLICY_VERSION)
    if campaign is not None:
        summary['task40_v10_campaign'] = {
            'window_path': str(campaign.path),
            'window_sha256': campaign.sha256,
            'accounting_path': str(campaign_account.path),
            't0_utc_ns': campaign.t0_utc_ns,
            'deadline_utc_ns': campaign.deadline_utc_ns,
            'campaign_seconds': campaign.total_seconds,
            'numerical_cutoff_seconds': campaign.cutoff_seconds,
            'closeout_reserve_seconds': campaign.closeout_seconds,
            'phase': campaign_phase,
            'phase_sub_budget_seconds': float(wall_seconds),
            'phase_termination_reserve_seconds': (
                phase_termination_reserve if campaign is not None else 0.0
            ),
            'closeout_parent_flush_reserve_seconds': (
                CAMPAIGN_CLOSEOUT_PARENT_FLUSH_RESERVE_SECONDS
                if campaign_phase == 'closeout'
                else 0.0
            ),
            'phase_authorization': campaign_phase_authorization,
            'watchdog_start_accounting': campaign_start_record,
            'first_exact_monotonic_at_t0': 'NOT_CAPTURED',
        }
    summary.update(
        v14_time_policy_facts(time_policy),
        memory_policy=memory_policy,
        swap_policy=(
            'observe_only'
            if allow_swap_observation
            else 'require_zero_swap'
            if stop_on_global_swap
            else 'worker_defined'
        ),
        process_tree_swap_gate_enforced=not allow_swap_observation,
        global_swap_gate_enforced=bool(stop_on_global_swap),
        job_cgroup_swap_gate_enforced=bool(require_job_cgroup_zero_swap),
        job_cgroup_swap_start_bytes=(
            None if job_cgroup_start is None
            else int(job_cgroup_start['swap_current_bytes'])
        ),
        time_reference_seconds={
            'workflow': float(wall_seconds),
            'solve': None if solve_seconds is None else float(solve_seconds),
            'active_pc': None if active_pc_seconds is None else float(active_pc_seconds),
        },
    )
    if pss_sampling_policy == 'disabled_by_profile':
        summary.update(
            pss_sampling_policy=pss_sampling_policy,
            pss_status='DISABLED_BY_PROFILE',
            sampled_process_tree_pss_peak_bytes=None,
        )
    stage = 'launch'
    swap_baseline = vmstat_swap_pages()
    try:
        with (directory / 'worker.log').open('w') as output, (directory / 'resources.jsonl').open('w') as timeline:
            environment = os.environ.copy()
            environment.update(worker_environment or {})
            if pss_sampling_policy == 'disabled_by_profile':
                environment['PHYSICAL_WATCHDOG_PSS_POLICY'] = pss_sampling_policy
            if timebase_guard:
                clock_budget.update(clock_start)
                environment['PHYSICAL_TIMEBASE_GUARD'] = '1'
                environment['PHYSICAL_TIMEBASE_POLICY'] = timebase_policy
            if phase_path is not None:
                environment.update(PHYSICAL_WATCHDOG_PARENT_PID=str(os.getpid()),
                                   PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES=str(cap),
                                   PHYSICAL_WATCHDOG_PHASE_PATH=str(phase_path.resolve()))
            leader = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                      start_new_session=True, env=environment)
            while True:
                exit_code = leader.poll()
                _reap_adopted(leader.pid)
                children = _children()
                observed.update(children)
                observed_child_identities.update(
                    (int(pid), int(identity[1])) for pid, identity in children.items()
                )
                stage = 'resource_sample'
                sample = process_tree_snapshot(
                    (
                        tree_accounting_root_pid
                        if tree_accounting_root_pid is not None
                        else os.getpid()
                    ),
                    'workflow',
                    exit_code,
                    pss_sampling_policy=pss_sampling_policy,
                )
                job_cgroup = (
                    cgroup_snapshot(os.getpid())
                    if require_job_cgroup_zero_swap
                    else None
                )
                if job_cgroup is not None:
                    job_cgroup_swap_sample_count += 1
                    cgroup_swap = job_cgroup.get('swap_current_bytes')
                    if isinstance(cgroup_swap, int) and not isinstance(cgroup_swap, bool):
                        job_cgroup_swap_peak_bytes = max(
                            job_cgroup_swap_peak_bytes, cgroup_swap
                        )
                    sample['job_cgroup'] = job_cgroup
                process_tree_all_status_readable = (
                    process_tree_all_status_readable
                    and sample.get('all_status_readable') is True
                )
                process_tree_all_identity_complete = (
                    process_tree_all_identity_complete
                    and sample.get('identity_complete') is True
                )
                process_tree_identity_sample_count += int(
                    sample.get('identity_count') or 0
                )
                sampled_child_identities.update(
                    (int(member['pid']), int(member['start_ticks']))
                    for member in sample.get('members', [])
                    if (
                        member.get('pid') in children
                        if tree_accounting_root_pid is not None
                        else member.get('pid') != os.getpid()
                    )
                    and isinstance(member.get('pid'), int)
                    and isinstance(member.get('start_ticks'), int)
                )
                current = memory_envelope(
                    memory_policy,
                    host_reserve_bytes=host_reserve_bytes,
                    task_cgroup_reserve_bytes=task_cgroup_reserve_bytes,
                    require_cgroup_memory_details=require_cgroup_memory_details,
                )
                elapsed = time.monotonic() - started
                phase = json.loads(phase_path.read_text()) if phase_path is not None and phase_path.exists() else {}
                solve_observed = None
                solve_expired = False
                if solve_seconds is not None and phase.get('phase') == 'solve':
                    solve_observed = time.monotonic() - phase['phase_started_monotonic']
                    solve_expired = solve_observed >= solve_seconds
                clock_issue = None
                pc_expired = False
                pc_observed = None
                deadline_elapsed = elapsed
                if timebase_guard:
                    clock_now = clock_sample(include_boot_id=campaign_account is not None)
                    sample.update(parent_clock=clock_now, parent_clock_start=clock_start)
                    try:
                        sample['workflow_clock_interval'] = clock_budget.update(clock_now)
                        deadline_elapsed = sample['workflow_clock_interval']['budget_seconds']
                        if campaign_account is not None:
                            campaign_row = campaign_account.record_sample(
                                label=f'watchdog_sample_{campaign_phase}',
                                phase=campaign_phase,
                            )
                            sample['task40_v10_campaign_accounting'] = campaign_row
                            campaign_clock = campaign_row['sample']
                            if campaign.phase_expired(
                                phase=campaign_phase,
                                cumulative_charged_seconds=float(
                                    campaign_row['cumulative_charged_seconds']
                                ),
                                now_utc_ns=int(campaign_clock['utc_ns']),
                                termination_reserve_seconds=(
                                    phase_termination_reserve
                                    if campaign_phase == 'closeout'
                                    else 0.0
                                ),
                            ):
                                deadline_elapsed = max(deadline_elapsed, wall_seconds)
                        if phase.get('clock_error'):
                            raise TimebaseInconsistency(phase['clock_error'])
                        if phase.get('phase') == 'solve':
                            phase_start = phase.get('phase_started_clock', {})
                            if solve_budget is None or solve_budget.start != phase_start:
                                solve_budget = ClockBudget(phase_start, policy=timebase_policy)
                            sample['solve_clock_interval'] = solve_budget.update(clock_now)
                            solve_observed = sample['solve_clock_interval']['budget_seconds']
                            solve_expired = (solve_seconds is not None and
                                            solve_observed >= solve_seconds)
                        if active_pc_seconds is not None:
                            active_pc = phase.get('active_pc')
                            if active_pc is None:
                                pc_budget = None
                            else:
                                pc_start = active_pc['started_clock']
                                if pc_budget is None or pc_budget.start != pc_start:
                                    pc_budget = ClockBudget(pc_start, policy=timebase_policy)
                                sample['pc_clock_interval'] = pc_budget.update(clock_now)
                                sample['pc_limit_seconds'] = float(active_pc_seconds)
                                pc_observed = sample['pc_clock_interval']['budget_seconds']
                                pc_expired = pc_observed >= active_pc_seconds
                    except TimebaseInconsistency as exc:
                        clock_issue = str(exc)
                        sample['clock_error'] = clock_issue
                        summary.setdefault('clock_error', clock_issue)
                workflow_gate = v14_time_gate_facts(
                    deadline_elapsed, wall_seconds, time_policy, inclusive=True
                )
                solve_gate = (
                    None
                    if solve_seconds is None or solve_observed is None
                    else v14_time_gate_facts(
                        solve_observed, solve_seconds, time_policy, inclusive=True
                    )
                )
                pc_gate = (
                    None
                    if active_pc_seconds is None or pc_observed is None
                    else v14_time_gate_facts(
                        pc_observed, active_pc_seconds, time_policy, inclusive=True
                    )
                )
                workflow_time_exceeded = workflow_time_exceeded or workflow_gate["exceeded"]
                solve_time_exceeded = solve_time_exceeded or bool(
                    solve_gate is not None and solve_gate["exceeded"]
                )
                pc_time_exceeded = pc_time_exceeded or bool(
                    pc_gate is not None and pc_gate["exceeded"]
                )
                if memory_policy == PHYSICAL_MEMORY_PRESSURE_POLICY:
                    current_cap = runtime_tree_cap(
                        cap,
                        int(sample['rss_bytes']),
                        current,
                        explicit_tree_cap_bytes=tree_cap_bytes,
                        memory_policy=memory_policy,
                    )
                elif tree_cap_bytes is not None:
                    current_cap = runtime_tree_cap(
                        cap,
                        int(sample['rss_bytes']),
                        current,
                        explicit_tree_cap_bytes=tree_cap_bytes,
                    )
                else:
                    current_cap = cap
                if not sample['all_status_readable']:
                    reason = 'MONITORING_FAILED'
                else:
                    peak_rss = max(peak_rss, sample['rss_bytes'])
                    peak_swap = max(peak_swap, sample['swap_bytes'])
                    reason = (
                        'RESOURCE_CONTROLLED_STOP' if sample['rss_bytes'] >= current_cap
                        or reserve_violation(current)
                        or (sample['swap_bytes'] != 0 and not allow_swap_observation) else
                        'USER_CONTROLLED_STOP' if timebase_guard and requested_signal else
                        'TIMEBASE_INCONSISTENCY' if clock_issue else
                        'PC_TIME_CONTROLLED_STOP'
                        if pc_expired and time_policy == V14_TIME_POLICY_ENFORCE else
                        'PERFORMANCE_CONTROLLED_STOP'
                        if time_policy == V14_TIME_POLICY_ENFORCE
                        and (deadline_elapsed >= wall_seconds or solve_expired) else
                        'USER_CONTROLLED_STOP' if requested_signal else None)
                if require_job_cgroup_zero_swap and (
                    not isinstance(job_cgroup, dict)
                    or job_cgroup.get('dedicated_job_cgroup') is not True
                    or job_cgroup.get('readable') is not True
                    or not isinstance(job_cgroup.get('swap_current_bytes'), int)
                    or isinstance(job_cgroup.get('swap_current_bytes'), bool)
                ):
                    reason = 'MONITORING_FAILED'
                elif (
                    require_job_cgroup_zero_swap
                    and job_cgroup['swap_current_bytes'] != 0
                    and reason not in ('RESOURCE_CONTROLLED_STOP', 'MONITORING_FAILED')
                ):
                    reason = 'RESOURCE_CONTROLLED_STOP'
                if stop_on_global_swap or allow_swap_observation:
                    current_swap = vmstat_swap_pages()
                    sample['global_swap_pages'] = current_swap
                    swap_reason = global_swap_stop(
                        swap_baseline, current_swap, enabled=stop_on_global_swap
                    )
                    sample['global_swap_stop_reason'] = swap_reason
                    if swap_reason is not None and reason not in ('RESOURCE_CONTROLLED_STOP', 'MONITORING_FAILED'):
                        reason = swap_reason
                if external_guard is not None:
                    try:
                        external_facts = external_guard()
                        sample['external_guard'] = external_facts
                        reason = _external_guard_stop_reason(reason, external_facts)
                    except BaseException as exc:
                        sample['external_guard'] = {
                            'stop': True, 'reason': 'MONITORING_FAILED',
                            'exception_type': type(exc).__name__, 'exception_message': str(exc),
                        }
                        reason = reason or 'MONITORING_FAILED'
                sample.update({'elapsed_seconds': elapsed, 'memory_envelope': current,
                               'worker_phase': phase,
                               'launch_cap_bytes': current_cap,
                               'watchdog_tree_cap_bytes': tree_cap_bytes,
                               'memory_policy': memory_policy,
                               'warning': peak_rss >= .85 * cap,
                               'live_or_unreaped_children': sorted(children),
                               'time_policy': time_policy,
                               'time_gate_evaluated': time_policy == V14_TIME_POLICY_ENFORCE,
                               'time_gate_action': (
                                   'enforce'
                                   if time_policy == V14_TIME_POLICY_ENFORCE
                                   else 'observe_only'
                               ),
                               'time_reference_seconds': {
                                   'workflow': float(wall_seconds),
                                   'solve': None if solve_seconds is None else float(solve_seconds),
                                   'active_pc': None if active_pc_seconds is None else float(active_pc_seconds),
                               },
                               'time_exceeded': {
                                   'workflow': workflow_gate['exceeded'],
                                   'solve': bool(solve_gate is not None and solve_gate['exceeded']),
                                   'active_pc': bool(pc_gate is not None and pc_gate['exceeded']),
                               },
                               'time_gates': {
                                   'workflow': workflow_gate,
                                   'solve': solve_gate,
                                   'active_pc': pc_gate,
                               }})
                stage = 'timeline_write'
                timeline.write(json.dumps(sample, allow_nan=False) + '\n')
                timeline.flush()
                samples += 1
                if reason and classification is None:
                    classification, stop_started = reason, time.monotonic()
                    stop_clock = clock_sample() if timebase_guard else None
                    summary['stop_event'] = dict(reason=reason, monotonic=stop_started,
                        timestamp_ns=time.time_ns(), grace_seconds=grace_seconds)
                if classification is not None and children:
                    signum = stop_signal(classification, hard_stop_immediate=hard_stop_immediate,
                        elapsed=budget_elapsed(stop_clock, clock_sample()) if timebase_guard
                        else time.monotonic()-stop_started, grace_seconds=grace_seconds)
                    if (cooperative_performance_stop and classification == 'PERFORMANCE_CONTROLLED_STOP'
                            and signum == signal.SIGTERM):
                        if 'cooperative_stop_request' not in summary:
                            stage = 'cooperative_stop_identity_and_signal'
                            request = _request_cooperative_stop(phase, leader.pid)
                            summary['cooperative_stop_request'] = request
                            summary['first_SIGTERM'] = dict(monotonic=request['monotonic'],
                                timestamp_ns=request['timestamp_ns'], scope='registered application only')
                    else:
                        summary.setdefault('first_'+signal.Signals(signum).name, dict(
                            monotonic=time.monotonic(), timestamp_ns=time.time_ns(), scope='whole child tree'))
                        _signal_children(signum)
                if exit_code is not None and not children:
                    stage = 'cache_stability'
                    stamp = _cache_stamp(cache_path)
                    if stamp != cache_stamp:
                        cache_stamp, stable_since = stamp, time.monotonic()
                    if time.monotonic() - stable_since >= max(1.0, 2 * interval):
                        classification = classification or ('COMPLETED' if exit_code == 0 else 'WORKER_FAILED')
                        break
                else:
                    stable_since = None
                    cache_stamp = None
                if stop_started is not None and (budget_elapsed(stop_clock, clock_sample())
                        if timebase_guard else time.monotonic() - stop_started) > grace_seconds + 10:
                    raise RuntimeError('descendants did not clear after SIGKILL')
                time.sleep(interval)
        summary['cache_metadata_stable'] = True
    except BaseException as exc:
        if classification is None:
            classification = 'TIMEBASE_INCONSISTENCY' if isinstance(exc, TimebaseInconsistency) else 'MONITORING_FAILED'
        summary.update({'exception_stage': stage, 'exception_type': type(exc).__name__,
                        'exception_message': str(exc), 'cache_metadata_stable': False})
    finally:
        # Also close the tree if sampling, JSON writing, or the parent fails.
        deadline = time.monotonic() + grace_seconds + 10
        cleanup_clock = clock_sample() if timebase_guard else None
        while leader is not None and _children() and (budget_elapsed(cleanup_clock, clock_sample())
                < grace_seconds + 10 if timebase_guard else time.monotonic() < deadline):
            _signal_children(signal.SIGKILL)
            leader.poll()
            _reap_adopted(leader.pid)
            time.sleep(.02)
        if leader is not None:
            leader.poll()
        remaining = _children()
        swap_end = vmstat_swap_pages()
        swap_delta = {key: None if swap_baseline[key] is None or swap_end[key] is None
                      else swap_end[key] - swap_baseline[key] for key in swap_baseline}
        global_swap_unresolved = any(
            value is None or value != 0 for value in swap_delta.values()
        )
        if allow_swap_observation and peak_swap > 0:
            job_swap_activity = 'observed_process_tree_swap'
        elif global_swap_unresolved:
            job_swap_activity = 'UNRESOLVED_global_activity_cannot_be_attributed'
        else:
            job_swap_activity = 'zero_supported_by_zero_global_activity'
        summary.update({
            'classification': 'EVIDENCE_INCOMPLETE' if remaining else classification,
            'leader_exit_code': None if leader is None else leader.returncode,
            'descendants_cleared': not remaining, 'remaining_child_pids': sorted(remaining),
            'observed_child_pids': sorted(observed),
            'observed_child_identities': [
                {'pid': pid, 'start_ticks': start_ticks}
                for pid, start_ticks in sorted(observed_child_identities)
            ],
            'sampled_process_tree_rss_peak_bytes': peak_rss if samples else None,
            'sampled_process_tree_swap_peak_bytes': peak_swap if samples else None,
            'process_tree_samples': samples,
            'process_tree_all_status_readable': (
                bool(samples) and process_tree_all_status_readable
            ),
            'process_tree_all_identity_complete': (
                bool(samples) and process_tree_all_identity_complete
            ),
            'process_tree_identity_coverage': (
                'complete'
                if samples
                and process_tree_all_identity_complete
                and observed_child_identities.issubset(sampled_child_identities)
                else 'incomplete_or_not_sampled'
            ),
            'process_tree_identity_sample_count': process_tree_identity_sample_count,
            'observed_child_identity_coverage': (
                'complete'
                if observed_child_identities.issubset(sampled_child_identities)
                else 'incomplete'
            ),
            'memory_scope': 'dedicated subreaper parent plus all descendants; sampled simultaneous RSS',
            'swap_scope': 'same process tree sampled VmSwap; no global swap attribution',
            'global_swap_activity': {'scope': 'WSL-global diagnostic, not dedicated job',
                                     'baseline': swap_baseline, 'end': swap_end, 'delta': swap_delta},
            'job_swap_activity': job_swap_activity,
            'launch_envelope': envelope, 'samples': samples,
            'memory_policy': memory_policy,
            'elapsed_seconds': time.monotonic() - started,
            'cache_metadata_stamp': cache_stamp,
            'source_state': source_state if source_state is not None else 'development_worktree; not formal PDE provenance',
            'time_exceeded': {
                'workflow': workflow_time_exceeded,
                'solve': solve_time_exceeded,
                'active_pc': pc_time_exceeded,
            },
        })
        if require_job_cgroup_zero_swap:
            final_job_cgroup = cgroup_snapshot(os.getpid())
            summary['job_cgroup_swap'] = {
                'gate_enforced': True,
                'start_swap_current_bytes': int(
                    job_cgroup_start['swap_current_bytes']
                ),
                'peak_swap_current_bytes': job_cgroup_swap_peak_bytes,
                'sample_count': job_cgroup_swap_sample_count,
                'end': final_job_cgroup,
                'passed': bool(
                    job_cgroup_swap_sample_count > 0
                    and job_cgroup_swap_peak_bytes == 0
                    and isinstance(final_job_cgroup, dict)
                    and final_job_cgroup.get('dedicated_job_cgroup') is True
                    and final_job_cgroup.get('readable') is True
                    and final_job_cgroup.get('swap_current_bytes') == 0
                ),
            }
        if timebase_guard:
            summary['clock_end'] = clock_sample(include_boot_id=campaign_account is not None)
            try:
                summary['workflow_clock_interval'] = clock_budget.update(summary['clock_end'])
                if campaign_account is not None:
                    campaign_end = campaign_account.record_sample(
                        label='watchdog_end', phase=campaign_phase
                    )
                    summary['task40_v10_campaign']['watchdog_end_accounting'] = campaign_end
                if (time_policy == V14_TIME_POLICY_ENFORCE
                        and clock_budget.seconds >= wall_seconds and
                        summary['classification'] == 'COMPLETED'):
                    summary['classification'] = 'PERFORMANCE_CONTROLLED_STOP'
            except TimebaseInconsistency as exc:
                summary['final_clock_error'] = str(exc)
                summary['workflow_clock_interval'] = dict(budget_seconds=clock_budget.seconds,
                                                          budget_complete=False)
                if summary['classification'] in (None, 'COMPLETED'):
                    summary['classification'] = 'TIMEBASE_INCONSISTENCY'
        try:
            end_workflow_seconds = float(
                summary.get('workflow_clock_interval', {}).get(
                    'budget_seconds', summary['elapsed_seconds']
                )
            )
            end_workflow_gate = v14_time_gate_facts(
                end_workflow_seconds, wall_seconds, time_policy, inclusive=True
            )
            summary['time_end_observation'] = end_workflow_gate
            summary['time_exceeded']['workflow'] = bool(
                summary['time_exceeded']['workflow'] or end_workflow_gate['exceeded']
            )
        except (TypeError, ValueError) as exc:
            summary['time_end_observation_error'] = str(exc)
            if summary['classification'] in (None, 'COMPLETED'):
                summary['classification'] = 'TIMEBASE_INCONSISTENCY'
        (directory / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--wall-seconds', type=float, required=True)
    parser.add_argument('--interval', type=float, default=.25)
    parser.add_argument('--grace-seconds', type=float, default=2)
    parser.add_argument('--cache-path', type=Path)
    parser.add_argument('--timebase-guard', action='store_true')
    parser.add_argument(
        '--time-policy', choices=(V14_TIME_POLICY_ENFORCE, 'observe_only'),
        default=V14_TIME_POLICY_ENFORCE,
    )
    parser.add_argument(
        '--memory-policy',
        choices=(LEGACY_MEMORY_POLICY, PHYSICAL_MEMORY_PRESSURE_POLICY),
        default=LEGACY_MEMORY_POLICY,
    )
    parser.add_argument(
        '--pss-sampling-policy', choices=('sampled', 'disabled_by_profile'),
        default='sampled',
    )
    parser.add_argument('--timebase-policy', default=STRICT)
    parser.add_argument('--tree-cap-bytes', type=int)
    parser.add_argument('--allow-physical-pressure-tree-cap', action='store_true')
    parser.add_argument('--require-job-cgroup-zero-swap', action='store_true')
    parser.add_argument('--campaign-window', type=Path)
    parser.add_argument('--campaign-window-sha256')
    parser.add_argument('--campaign-accounting-path', type=Path)
    parser.add_argument('--source-branch')
    parser.add_argument('--source-sha')
    parser.add_argument('--source-clean', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    source_state = None
    if args.source_branch is not None or args.source_sha is not None or args.source_clean:
        source_state = {
            "branch": args.source_branch,
            "source_sha": args.source_sha,
            "clean": args.source_clean,
        }
    summary = supervise(command, args.directory, wall_seconds=args.wall_seconds,
                        interval=args.interval, grace_seconds=args.grace_seconds,
                        cache_path=args.cache_path, timebase_guard=args.timebase_guard,
                        time_policy=args.time_policy, timebase_policy=args.timebase_policy,
                        memory_policy=args.memory_policy,
                        pss_sampling_policy=args.pss_sampling_policy,
                        tree_cap_bytes=args.tree_cap_bytes,
                        allow_physical_pressure_tree_cap=args.allow_physical_pressure_tree_cap,
                        require_job_cgroup_zero_swap=args.require_job_cgroup_zero_swap,
                        campaign_window_path=args.campaign_window,
                        campaign_window_sha256=args.campaign_window_sha256,
                        campaign_accounting_path=args.campaign_accounting_path,
                        source_state=source_state)
    print(json.dumps(summary, allow_nan=False), flush=True)
    return 0 if summary['classification'] == 'COMPLETED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
