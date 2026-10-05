"""Finish one failed tmux connection using its original clock and worker command.

Only the AF_UNIX address spelling changes (absolute -> root-relative, same
socket file). The existing durable launcher, live PID/socket identity checks,
inner fresh resource admission and watchdog remain in use. No worker rerun.
"""

import json
import os
from pathlib import Path
import shlex
import socket
import stat
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.io.finite_json import atomic_json  # noqa: E402
from src.io.w1_evidence import file_receipt, validate_A  # noqa: E402
from src.io.w1_receiver_contract import load_w1  # noqa: E402
from src.io.w1_versioned_input import digest  # noqa: E402
from src.runners import durable_terminal  # noqa: E402
from src.runners.fresh_component_receiver import set_own_low_priority  # noqa: E402
from src.runners.w1_admission_scope import validate_scope  # noqa: E402
from src.runners.w1_component_receiver import RECEIVER_FILES, remaining  # noqa: E402


def main():
    spec = load_w1(sys.argv[1])
    if spec["w1_receiver_schema"] != 2:
        raise ValueError("ONLY_EXPLICIT_V28_W1")
    namespace = "w1-receiver-" + Path(spec["output_root"]).name + "-" + spec["stage"]
    folder = ROOT / "tmp/task42extra/durable" / namespace
    if (folder / "terminal_identity.json").exists() or (folder / "tmux.sock").exists():
        raise ValueError("POSSIBLE_ACTIVE_JOB_DO_NOT_RECOVER")
    if (Path(spec["output_root"]) / spec["stage"]).exists():
        raise ValueError("WORKER_OR_RECEIVER_ALREADY_STARTED")
    clock = json.loads((folder / "launch_clock.json").read_text())
    facts = json.loads((folder / "prelaunch_admission.json").read_text())
    request = json.loads((folder / "launch.json").read_text())
    scope = facts["allowed_scope"]
    validate_scope(scope)
    remaining(json.loads(Path(spec["window_path"]).read_text()))
    if clock["input_sha256"] != spec["input_sha256"] or (
        clock["window_sha256"] != digest(spec["window_path"])
        or clock["allowed_scope_sha256"] != scope["body_sha256"]
    ):
        raise ValueError("ORIGINAL_LAUNCH_BINDING_CHANGED")
    validate_A(
        spec["A_qualification_path"], {p: digest(ROOT / p) for p in RECEIVER_FILES}
    )
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("CLEAN_IMPLEMENTATION_REQUIRED")
    expected = [
        "/bin/bash",
        "-c",
        "source scripts/activate_task42extra.sh pure && exec python scripts/run_case.py "
        + shlex.quote(spec["path"]),
    ]
    if (
        request["command"] != expected
        or request["session"] != "task42extra-" + namespace
    ):
        raise ValueError("NOT_THE_ORIGINAL_PUBLIC_ONE_RUN_COMMAND")
    absolute = folder / "tmux.sock"
    relative = str(absolute.relative_to(ROOT))
    if len(os.fsencode(str(absolute))) < 108 or len(os.fsencode(relative)) >= 108:
        raise ValueError("NOT_THE_QUALIFIED_AF_UNIX_LENGTH_ROOT_CAUSE")
    os.chdir(ROOT)
    set_own_low_priority()
    os.sched_setaffinity(
        0, {scope["preferred_cpu"]}
    )  # Management only; inner admission is fresh.
    # OS fixture: exact long address refuses, shorter spelling of the SAME file works.
    probe = folder / "probe.sock"
    with socket.socket(socket.AF_UNIX) as server:
        try:
            server.bind(str(probe))
        except OSError as error:
            absolute_error = dict(errno=error.errno, reason=str(error))
        else:
            raise ValueError("EXPECTED_LONG_ADDRESS_REFUSAL_NOT_OBSERVED")
        server.bind(str(probe.relative_to(ROOT)))
        server.listen(1)
        server.settimeout(2)
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(2)
            client.connect(str(probe.relative_to(ROOT)))
            peer, _ = server.accept()
            peer.close()
        if not stat.S_ISSOCK(probe.stat().st_mode):
            raise ValueError("RELATIVE_ADDRESS_IS_NOT_SAME_TASK_SOCKET_FILE")
    probe.unlink()  # Only the empty socket created by this fixture.
    record = dict(
        schema="w1-absolute-socket-launch-recovery.v28",
        original_origin_monotonic=clock["origin_monotonic"],
        recovery_monotonic=time.monotonic(),
        absolute_error=absolute_error,
        absolute_socket=str(absolute),
        actual_socket_address=relative,
        same_filesystem_socket=True,
        inner_admission_remains_fresh=True,
        previous_outer_sample_not_replaced=True,
        no_worker_previously_started=True,
        source=file_receipt(Path(__file__)),
        original_launch=file_receipt(folder / "launch.json"),
        original_job=file_receipt(folder / "job.sh"),
        source_sha=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
    )
    for name in ("launch.json", "job.sh"):
        old = folder / ("failed_absolute_socket_" + name)
        if old.exists():
            raise ValueError("RECOVERY_ALREADY_ATTEMPTED")
        (folder / name).rename(old)
    ready = folder / "relative_address_READY.json"
    guard = (
        "for ((n=0;n<200;n++)); do [[ -s "
        + shlex.quote(str(ready))
        + " ]] && break; sleep 0.05; done; [[ -s "
        + shlex.quote(str(ready))
        + " ]] && exec "
        + shlex.join(expected)
    )
    original = durable_terminal.subprocess

    def address(args):
        if args[:3] != ["tmux", "-S", str(absolute)]:
            raise ValueError("UNEXPECTED_LAUNCHER_SUBPROCESS")
        return args[:2] + [relative] + args[3:]

    durable_terminal.subprocess = types.SimpleNamespace(
        run=lambda args, **kw: original.run(address(args), cwd=ROOT, **kw),
        check_output=lambda args, **kw: original.check_output(
            address(args), cwd=ROOT, **kw
        ),
    )
    os.environ["TASK42EXTRA_DURABLE_NAMESPACE"] = namespace
    try:
        result = durable_terminal.launch_tmux(
            folder,
            request["session"],
            ["/bin/bash", "-c", guard],
            ROOT,
            management_supervised=True,
            allowed_scope=scope,
        )
        result["socket"] = (
            relative  # Must equal the real server argv, checked by the receiver.
        )
        atomic_json(folder / "launch_recovery_receipt.json", record)
        result["launch_recovery"] = file_receipt(
            folder / "launch_recovery_receipt.json"
        )
        atomic_json(folder / "terminal_identity.json", result)
        atomic_json(
            ready,
            dict(
                terminal_identity_sha256=digest(folder / "terminal_identity.json"),
                original_clock_preserved=True,
            ),
        )
        print(
            json.dumps({k: result[k] for k in ("socket", "session", "output", "scope")})
        )
    finally:
        durable_terminal.subprocess = original


if __name__ == "__main__":
    main()
