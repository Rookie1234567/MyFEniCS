#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
input_path="${1:-}"
unit="${2:-task44-sample-a.service}"
max_concurrent="${3:-1}"
smoke="${4:-}"
cap_bytes=137438953472
preflight_cap_bytes=4294967296

if [[ -z "$input_path" ]]; then
    echo "Usage: bash scripts/start_task44_native_sample.sh INPUT.dat [UNIT.service] [MAX_CONCURRENT] [--smoke]" >&2
    exit 2
fi
if [[ "$unit" != *.service || ! "$unit" =~ ^task44-sample-[a-z0-9-]+\.service$ ]]; then
    echo "Task44 service name must use the task44-sample-NAME.service form" >&2
    exit 2
fi
if [[ "$max_concurrent" != 1 && "$max_concurrent" != 2 ]]; then
    echo "MAX_CONCURRENT must be 1 or 2" >&2
    exit 2
fi
if [[ -n "$smoke" && "$smoke" != "--smoke" ]]; then
    echo "The optional fifth argument must be --smoke" >&2
    exit 2
fi
[[ "$input_path" == /* ]] || input_path="$repo_root/$input_path"
input_path="$(realpath -- "$input_path")"

cd -- "$repo_root"
artifact_dir="$repo_root/benchmarks/artifacts/task44_native_services/$unit"
if [[ -e "$artifact_dir" ]]; then
    echo "Task44 service artifact directory already exists; choose a unique unit: $artifact_dir" >&2
    exit 2
fi
sample_name="${unit#task44-sample-}"
sample_name="${sample_name%.service}"
cache_root="/tmp/myfenics-task44-native-cache-${UID}/${sample_name}"
if [[ -e "$cache_root" ]]; then
    echo "Task44 per-service cache root already exists; choose a unique unit: $cache_root" >&2
    exit 2
fi
export MYFENICS_TASK44_CACHE_ROOT="$cache_root"
source "$repo_root/scripts/activate_task44_native.sh"
mkdir -p "$artifact_dir"
printf '%s\n' "$cache_root" > "$artifact_dir/jit-cache-root.txt"
cpu_selection_json="$(python -c 'import json; from scripts.task44_native_service import select_idle_cpu; print(json.dumps(select_idle_cpu(), sort_keys=True, allow_nan=False))')"
printf '%s\n' "$cpu_selection_json" > "$artifact_dir/cpu-selection.json"
cpu_set="$(python -c 'import json, sys; print(json.load(sys.stdin)["selected_cpu"])' <<< "$cpu_selection_json")"
preflight_unit="task44-preflight-${sample_name}-${BASHPID}.service"
python scripts/task44_native_service.py \
    --resource-preflight --input "$input_path" --unit "$unit" \
    --cpu-affinity "$cpu_set" --max-concurrent "$max_concurrent" \
    --cap-bytes "$cap_bytes" | tee "$artifact_dir/resource-preflight.json"

systemd-run --user --wait --pipe --collect --expand-environment=no \
    --unit="$preflight_unit" --service-type=exec \
    --property=Restart=no \
    --property=KillMode=control-group \
    --property="MemoryMax=$preflight_cap_bytes" \
    --property=MemorySwapMax=0 \
    --property="CPUAffinity=$cpu_set" \
    --property="SystemCallFilter=~sched_setaffinity" \
    --property=SystemCallErrorNumber=EPERM \
    --property="WorkingDirectory=$repo_root" \
    --property="Environment=XDG_RUNTIME_DIR=/run/user/$UID" \
    --property="Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$UID/bus" \
    --property="Environment=MYFENICS_TASK44_CACHE_ROOT=$cache_root" \
    /usr/bin/bash -c '
        set -euo pipefail
        cd -- "$1"
        source scripts/activate_task44_native.sh
        exec python scripts/task44_native_service.py \
            --preflight --input "$2" --unit "$3" \
            --cpu-affinity "$4"
    ' task44-native-preflight "$repo_root" "$input_path" "$preflight_unit" \
    "$cpu_set" \
    | tee "$artifact_dir/preflight.json"

systemd-run --user --no-block --expand-environment=no \
    --unit="$unit" --service-type=exec \
    --property=Restart=no \
    --property=KillMode=control-group \
    --property="MemoryMax=$cap_bytes" \
    --property=MemorySwapMax=0 \
    --property="CPUAffinity=$cpu_set" \
    --property="SystemCallFilter=~sched_setaffinity" \
    --property=SystemCallErrorNumber=EPERM \
    --property="WorkingDirectory=$repo_root" \
    --property="StandardOutput=append:$artifact_dir/service.log" \
    --property="StandardError=append:$artifact_dir/service.log" \
    --property="Environment=XDG_RUNTIME_DIR=/run/user/$UID" \
    --property="Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$UID/bus" \
    --property="Environment=MYFENICS_TASK44_CACHE_ROOT=$cache_root" \
    /usr/bin/bash -c '
        set -euo pipefail
        cd -- "$1"
        source scripts/activate_task44_native.sh
        args=(--input "$2" --unit "$3" --cpu-affinity "$4" \
            --max-concurrent "$5" --cap-bytes "$6")
        if [[ "$7" == "--smoke" ]]; then args+=(--smoke); fi
        exec python scripts/task44_native_service.py "${args[@]}"
    ' task44-native-service "$repo_root" "$input_path" "$unit" "$cpu_set" \
    "$max_concurrent" "$cap_bytes" "$smoke"

task44_startup_decision() {
    python - "$1" "$artifact_dir/service_identity.json" "$artifact_dir/service_summary.json" "$unit" "$cap_bytes" "$cpu_set" <<'PY'
import json
import sys
from pathlib import Path

from scripts.task44_service_startup import classify_service_startup

state = sys.argv[1]
identity_path, summary_path = Path(sys.argv[2]), Path(sys.argv[3])
unit, cap_bytes = sys.argv[4], int(sys.argv[5])
cpus = [int(value) for value in sys.argv[6].split(",")]

def load_receipt(path):
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"_invalid_receipt": True}
    return value if isinstance(value, dict) else {"_invalid_receipt": True}

print(classify_service_startup(
    state, load_receipt(identity_path), load_receipt(summary_path),
    unit=unit, cap_bytes=cap_bytes, cpu_affinity=cpus,
))
PY
}

task44_verify_completed() {
    python - "$artifact_dir/service_identity.json" "$artifact_dir/service_summary.json" "$unit" "$cap_bytes" "$cpu_set" <<'PY'
import json
import sys
from pathlib import Path

from scripts.task44_service_startup import classify_service_startup

identity_path, summary_path = Path(sys.argv[1]), Path(sys.argv[2])
unit, cap_bytes = sys.argv[3], int(sys.argv[4])
cpus = [int(value) for value in sys.argv[5].split(",")]
identity = json.loads(identity_path.read_text(encoding="utf-8"))
summary = json.loads(summary_path.read_text(encoding="utf-8"))
if classify_service_startup(
    "inactive", identity, summary,
    unit=unit, cap_bytes=cap_bytes, cpu_affinity=cpus,
) != "completed":
    raise SystemExit(f"Task44 completion receipt does not match this unit invocation: {identity}")
print(json.dumps({
    "startup_identity": identity,
    "classification": summary.get("classification"),
    "task44_service": summary.get("task44_service"),
}, sort_keys=True))
PY
}

task44_startup_diagnostics() {
    systemctl --user show "$unit" --no-pager \
        -p ActiveState -p SubState -p MainPID -p InvocationID -p ControlGroup \
        -p MemoryMax -p MemorySwapMax -p CPUAffinity >&2 || true
    journalctl --user -u "$unit" --no-pager -n 40 >&2 || true
    if [[ -f "$artifact_dir/service_identity.json" ]]; then
        cat "$artifact_dir/service_identity.json" >&2
    else
        echo "service_identity.json not written yet" >&2
    fi
    tail -n 20 "$artifact_dir/service.log" >&2 2>/dev/null || true
}

task44_startup_pending_snapshot() {
    printf 'Task44 service status=startup_pending unit=%s pending_seconds=%s expected_cpus=%s\n' \
        "$unit" "$pending_seconds" "$cpu_set" >&2
    task44_startup_diagnostics
    main_pid="$(systemctl --user show --value --property=MainPID "$unit" 2>/dev/null || true)"
    if [[ "$main_pid" =~ ^[0-9]+$ ]] && (( main_pid > 1 )); then
        ps -p "$main_pid" -o pid=,ppid=,comm=,psr=,pcpu=,stat= >&2 || true
        taskset -pc "$main_pid" >&2 || true
    fi
}

task44_startup_monitor_failure() {
    task44_startup_diagnostics
    if [[ "$1" == active ]]; then
        systemctl --user stop "$unit" || true
    fi
    echo "Task44 startup state monitor failed; see the exact-unit diagnostics above" >&2
    exit 1
}

pending_seconds=0
next_pending_report=30
while true; do
    state="$(systemctl --user show --value --property=ActiveState "$unit" 2>/dev/null || true)"
    if ! decision="$(task44_startup_decision "$state")"; then
        task44_startup_monitor_failure "$state"
    fi

    if [[ "$decision" == "active_identity_ready" ]]; then
        if python - "$unit" "$artifact_dir/service_identity.json" "$cap_bytes" "$cpu_set" "$artifact_dir/startup_affinity_check.json" <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.task44_service_startup import observe_cgroup_cpu_affinity

unit, receipt_path, expected_cap = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
expected_cpus = set(int(value) for value in sys.argv[4].split(","))
affinity_receipt_path = Path(sys.argv[5])

def parse_cpu_list(value):
    result = set()
    for token in value.replace(",", " ").split():
        if "-" in token:
            low, high = (int(part) for part in token.split("-", 1))
            result.update(range(low, high + 1))
        elif token:
            result.add(int(token))
    return result

names = (
    "ActiveState", "MainPID", "InvocationID", "ControlGroup", "MemoryMax",
    "MemorySwapMax", "Restart", "KillMode", "WorkingDirectory", "CPUAffinity",
    "SystemCallFilter", "SystemCallErrorNumber",
)
args = ["systemctl", "--user", "show", unit, "--no-pager"]
for name in names:
    args.extend(("-p", name))
text = subprocess.run(args, check=True, capture_output=True, text=True).stdout
facts = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
pid = int(facts["MainPID"])
stat = Path(f"/proc/{pid}/stat").read_text()
start_ticks = int(stat[stat.rfind(")") + 2 :].split()[19])
expected = {
    "ActiveState": "active", "MemoryMax": str(expected_cap),
    "MemorySwapMax": "0", "Restart": "no", "KillMode": "control-group",
}
if any(facts.get(key) != value for key, value in expected.items()):
    raise SystemExit(f"Task44 service identity gate failed: {facts}")
if (
    facts["SystemCallFilter"].split() != ["~sched_setaffinity"]
    or facts["SystemCallErrorNumber"] not in {"EPERM", "1"}
):
    raise SystemExit(f"Task44 service seccomp properties mismatch: {facts}")
if parse_cpu_list(facts["CPUAffinity"]) != expected_cpus:
    raise SystemExit(f"Task44 systemd CPUAffinity mismatch: {facts}")
receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
if (
    not facts.get("InvocationID") or not facts.get("ControlGroup") or pid <= 1
    or receipt.get("service_unit") != unit
    or receipt.get("main_pid") != pid
    or receipt.get("main_pid_start_ticks") != start_ticks
    or receipt.get("invocation_id") != facts["InvocationID"]
    or receipt.get("control_group") != facts["ControlGroup"]
    or receipt.get("system_call_filter") != facts["SystemCallFilter"]
    or receipt.get("system_call_error_number") != facts["SystemCallErrorNumber"]
    or receipt.get("sched_setaffinity_filter_test", {}).get("status") != "pass"
    or receipt.get("sched_setaffinity_filter_test", {}).get("errno") != "EPERM"
    or receipt.get("cpu_affinity") != sorted(expected_cpus)
    or receipt.get("actual_process_cpu_affinity") != sorted(expected_cpus)
):
    raise SystemExit(f"live systemd identity differs from saved startup receipt: {facts} / {receipt}")
cgroup = Path("/sys/fs/cgroup") / facts["ControlGroup"].lstrip("/")
affinity_report = observe_cgroup_cpu_affinity(cgroup, expected_cpus)
affinity_receipt = {
    "unit": unit,
    "invocation_id": facts["InvocationID"],
    "service_pid": pid,
    "service_pid_start_ticks": start_ticks,
    "control_group": facts["ControlGroup"],
    "affinity_observation": affinity_report,
}
temporary_path = affinity_receipt_path.with_name(
    f".{affinity_receipt_path.name}.{os.getpid()}.tmp"
)
temporary_path.write_text(
    json.dumps(affinity_receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
    encoding="utf-8",
)
os.replace(temporary_path, affinity_receipt_path)
if affinity_report["stop"]:
    raise SystemExit(json.dumps(affinity_receipt, sort_keys=True))
print(json.dumps({"live_systemd": facts, "startup_identity": receipt,
                  "affinity_observation": affinity_report}, sort_keys=True))
PY
        then
            exit 0
        fi
        state="$(systemctl --user show --value --property=ActiveState "$unit" 2>/dev/null || true)"
        if ! decision="$(task44_startup_decision "$state")"; then
        task44_startup_monitor_failure "$state"
    fi
        if [[ "$decision" == "completed" ]]; then
            task44_verify_completed
            exit 0
        fi
        if [[ "$decision" == "active_identity_ready" || "$decision" == "identity_invalid" ]]; then
            task44_startup_diagnostics
            systemctl --user stop "$unit" || true
            echo "Task44 live service identity or CPU/resource gate failed" >&2
            exit 1
        fi
    fi

    case "$decision" in
        completed)
            task44_verify_completed
            exit 0
            ;;
        identity_invalid)
            task44_startup_diagnostics
            if [[ "$state" == active ]]; then
                systemctl --user stop "$unit" || true
            fi
            echo "Task44 service startup identity failed closed" >&2
            exit 1
            ;;
        failed)
            task44_startup_diagnostics
            echo "Task44 service failed before a matching completion receipt was saved" >&2
            exit 1
            ;;
        startup_pending)
            ;;
        active_identity_ready)
            ;;
        *)
            task44_startup_diagnostics
            echo "Unexpected Task44 startup classification: $decision" >&2
            exit 1
            ;;
    esac

    if (( pending_seconds < 30 )); then
        sleep_seconds=1
        pending_seconds=$((pending_seconds + 1))
    else
        sleep_seconds=5
        pending_seconds=$((pending_seconds + sleep_seconds))
    fi
    if (( pending_seconds >= next_pending_report )); then
        task44_startup_pending_snapshot
        next_pending_report=$((next_pending_report + 30))
    fi
    sleep "$sleep_seconds"
done
