"""One explicitly requested bounded job in its own native tmux server."""

import json
import os
from pathlib import Path
import shlex
import subprocess
from time import time


def launch_tmux(directory, session, command, root):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    if not directory.is_relative_to(root / "tmp/task42extra"):
        raise ValueError("durable terminal directory must be task-local")
    directory.mkdir(parents=True, exist_ok=True)
    request = directory / "launch.json"
    with request.open("x") as stream:
        json.dump(
            dict(command=command, session=session, time=time(), launch_pid=os.getpid()),
            stream,
        )
    socket = directory / "tmux.sock"
    shell = directory / "job.sh"
    proof = shlex.quote(str(directory / "terminal_identity.json"))
    shell.write_text(
        "#!/bin/bash\nset -euo pipefail\ncd "
        + shlex.quote(str(root))
        + "\nfor ((n=0; n<200; n++)); do\n  [[ -s "
        + proof
        + " ]] && break\n  sleep 0.05\ndone\n[[ -s "
        + proof
        + " ]]\nexec "
        + shlex.join(command)
        + " > "
        + shlex.quote(str(directory / "launcher.log"))
        + " 2>&1\n"
    )
    base = ["tmux", "-S", str(socket), "-f", "/dev/null"]
    subprocess.run(
        base
        + ["new-session", "-d", "-s", session, "exec bash " + shlex.quote(str(shell))],
        check=True,
    )
    identity = (
        subprocess.check_output(
            base + ["display-message", "-p", "#{pid} #{pane_pid}"], text=True
        )
        .strip()
        .split()
    )

    def observed(pid):
        proc = Path(f"/proc/{pid}")
        parts = proc.joinpath("stat").read_text().rsplit(")", 1)[1].split()
        return dict(
            pid=int(pid),
            ppid=int(parts[1]),
            start_ticks=int(parts[19]),
            session=int(parts[3]),
            process_group=int(parts[2]),
            cgroup=proc.joinpath("cgroup").read_text(),
            stdout=os.readlink(proc / "fd/1"),
            status=proc.joinpath("status").read_text(),
        )

    result = dict(
        socket=str(socket),
        session=session,
        server=observed(identity[0]),
        pane=observed(identity[1]),
        output=str(directory / "launcher.log"),
        mechanism="isolated native tmux; no service changes; server exits when job pane exits",
        scope="server/pane management overhead outside numerical watchdog tree; recorded separately",
    )
    temporary = directory / "terminal_identity.json.tmp"
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    os.replace(temporary, directory / "terminal_identity.json")
    return result
