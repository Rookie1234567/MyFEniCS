"""Exercise the real systemd-shell body with activation/exec stubs only."""

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("route", "source_sha", "expected"),
    [
        (
            "capture",
            "a" * 40,
            {
                "TASK41_P0_V19_NATIVE_RANK1": "1",
                "TASK41_P0_V19_CHECKER_ONLY": "<unset>",
                "TASK41_P0_V19_RECEIPT_SHA256": "<unset>",
                "TASK41_P0_V19_RECEIPT_PATH": "<unset>",
                "TASK41_P0_EXPECTED_SOURCE_SHA": "a" * 40,
            },
        ),
        (
            "checker",
            "b" * 40,
            {
                "TASK41_P0_V19_NATIVE_RANK1": "1",
                "TASK41_P0_V19_CHECKER_ONLY": "1",
                "TASK41_P0_V19_RECEIPT_SHA256": "c" * 64,
                "TASK41_P0_V19_RECEIPT_PATH": "/fixture/completed-receipt.json",
                "TASK41_P0_EXPECTED_SOURCE_SHA": "b" * 40,
            },
        ),
        (
            "default",
            "d" * 40,
            {
                "TASK41_P0_V19_NATIVE_RANK1": "<unset>",
                "TASK41_P0_V19_CHECKER_ONLY": "<unset>",
                "TASK41_P0_V19_RECEIPT_SHA256": "<unset>",
                "TASK41_P0_V19_RECEIPT_PATH": "<unset>",
                "TASK41_P0_EXPECTED_SOURCE_SHA": "d" * 40,
            },
        ),
    ],
)
def test_v19_systemd_shell_exports_capture_checker_and_default_modes(
    tmp_path, route, source_sha, expected
):
    """Parse real service args, source a stub activation, then exec a stub Python."""
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    (scripts / "task40_fresh_c1").mkdir(parents=True)
    (repo / "benchmarks/artifacts/user_services").mkdir(parents=True)
    wrapper = scripts / "run_case_in_user_service.sh"
    wrapper.write_text(
        (ROOT / "scripts/run_case_in_user_service.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    activation_capture = tmp_path / "activation.txt"
    activation = scripts / "task40_fresh_c1/activate_native_complex.sh"
    activation.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$@" > "$ACTIVATION_CAPTURE"\n'
        'export V19_TEST_ACTIVATION_REACHED=1\n',
        encoding="utf-8",
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    python3 = fake_bin / "python3"
    python3.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'printf "%s\\n" "$*" >> "$PYTHON3_CALLS"\n'
        '[[ "$1" == "-m" && "$2" == "src.runners.task41_p0_contract" && '
        '"$3" == "--launcher-values" ]] || exit 19\n'
        'printf "%s\\n" "$ROOT" "$RUNTIME" "$ABI" "$JIT" '
        '"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" '
        '"/fixture/window.json" '
        '"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" '
        '"1610612736" "67108864" "0" "unused" "$SOURCE_SHA"\n',
        encoding="utf-8",
    )
    python3.chmod(0o755)

    systemd_capture = tmp_path / "systemd-args.bin"
    systemd_run = fake_bin / "systemd-run"
    systemd_run.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'printf "%s\\0" "$@" > "$SYSTEMD_CAPTURE"\n',
        encoding="utf-8",
    )
    systemd_run.chmod(0o755)

    runtime = tmp_path / "runtime"
    (runtime / "bin").mkdir(parents=True)
    final_env_capture = tmp_path / "final-env.txt"
    final_args_capture = tmp_path / "final-args.bin"
    final_python = runtime / "bin/python"
    final_python.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'printf "TASK41_P0_V19_NATIVE_RANK1=%s\\n" "${TASK41_P0_V19_NATIVE_RANK1-<unset>}" > "$FINAL_ENV_CAPTURE"\n'
        'printf "TASK41_P0_V19_CHECKER_ONLY=%s\\n" "${TASK41_P0_V19_CHECKER_ONLY-<unset>}" >> "$FINAL_ENV_CAPTURE"\n'
        'printf "TASK41_P0_V19_RECEIPT_SHA256=%s\\n" "${TASK41_P0_V19_RECEIPT_SHA256-<unset>}" >> "$FINAL_ENV_CAPTURE"\n'
        'printf "TASK41_P0_V19_RECEIPT_PATH=%s\\n" "${TASK41_P0_V19_RECEIPT_PATH-<unset>}" >> "$FINAL_ENV_CAPTURE"\n'
        'printf "TASK41_P0_EXPECTED_SOURCE_SHA=%s\\n" "${TASK41_P0_EXPECTED_SOURCE_SHA-<unset>}" >> "$FINAL_ENV_CAPTURE"\n'
        '[[ "${V19_TEST_ACTIVATION_REACHED-}" == 1 ]] || exit 23\n'
        'printf "%s\\0" "$@" > "$FINAL_ARGS_CAPTURE"\n',
        encoding="utf-8",
    )
    final_python.chmod(0o755)
    contract = repo / "contract.json"
    contract.write_text("{}\n", encoding="utf-8")

    forwarded = ["fixture.dat", "--task41-p0-execution-contract", str(contract)]
    if route in ("capture", "checker"):
        forwarded.extend(
            ["--task41-p0-b0-v19-native-rank1", "--v19-output-directory", "/fixture/attempt01"]
        )
    if route == "checker":
        forwarded.extend(
            [
                "--task41-p0-b0-v19-checker-only",
                "--v19-receipt-sha256",
                "c" * 64,
                "--v19-receipt-path",
                "/fixture/completed-receipt.json",
            ]
        )

    python_calls = tmp_path / "python3-calls.txt"
    environment = dict(
        os.environ,
        PATH=f"{fake_bin}:{os.environ['PATH']}",
        ROOT=str(repo),
        RUNTIME=str(runtime),
        ABI="/fixture/abi.json",
        JIT="/fixture/jit",
        SOURCE_SHA=source_sha,
        PYTHON3_CALLS=str(python_calls),
        SYSTEMD_CAPTURE=str(systemd_capture),
        ACTIVATION_CAPTURE=str(activation_capture),
        FINAL_ENV_CAPTURE=str(final_env_capture),
        FINAL_ARGS_CAPTURE=str(final_args_capture),
    )
    launch = subprocess.run(
        ["bash", str(wrapper), *forwarded, "--service-unit=v19-wrapper-fixture"],
        cwd=repo,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert launch.returncode == 0, launch.stderr
    assert systemd_capture.is_file()

    service_argv = [value.decode() for value in systemd_capture.read_bytes().split(b"\0") if value]
    bash_index = service_argv.index("/usr/bin/bash")
    assert service_argv[bash_index + 1] == "-lc"
    shell_code = service_argv[bash_index + 2]
    assert "task41_v19_checker_only=0" in shell_code
    inner = subprocess.run(
        [
            "/bin/bash",
            "-c",
            shell_code,
            "task41-p0",
            str(repo),
            "v19-wrapper-fixture",
            str(contract),
            *forwarded,
        ],
        cwd=repo,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert inner.returncode == 0, inner.stderr
    assert activation_capture.read_text(encoding="utf-8").splitlines() == [
        str(runtime),
        "/fixture/abi.json",
        "/fixture/jit",
        "native_linux",
    ]
    actual_env = dict(
        line.split("=", 1)
        for line in final_env_capture.read_text(encoding="utf-8").splitlines()
    )
    assert actual_env == expected

    final_args = [value.decode() for value in final_args_capture.read_bytes().split(b"\0") if value]
    assert final_args[:2] == ["scripts/task40_v20_service_workflow.py", "run-service"]
    assert ("--task41-p0-b0-v19-native-rank1" in final_args) == (
        route in ("capture", "checker")
    )
    assert ("--task41-p0-b0-v19-checker-only" in final_args) == (route == "checker")
    assert ("--saved-output-continuation" in python_calls.read_text(encoding="utf-8")) == (
        route in ("capture", "checker")
    )
