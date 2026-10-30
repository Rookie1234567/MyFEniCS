#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
input_path="${1:-}"
cpu_set="${2:-}"
unit="${3:-task44-sample-a.service}"
max_concurrent="${4:-1}"
smoke="${5:-}"
cap_bytes=137438953472

if [[ -z "$input_path" || -z "$cpu_set" ]]; then
    echo "Usage: bash scripts/start_task44_native_sample.sh INPUT.dat CPUSET [UNIT.service] [MAX_CONCURRENT] [--smoke]" >&2
    exit 2
fi
if [[ ! "$cpu_set" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
    echo "CPUSET must be a comma-separated list of host-selected CPU numbers" >&2
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

source "$repo_root/scripts/activate_task44_native.sh"
artifact_dir="$repo_root/benchmarks/artifacts/task44_native_services/$unit"
if [[ -e "$artifact_dir" ]]; then
    echo "Task44 service artifact directory already exists; choose a unique unit: $artifact_dir" >&2
    exit 2
fi
mkdir -p "$artifact_dir"
python "$repo_root/scripts/task44_native_service.py" \
    --preflight --input "$input_path" --unit "$unit" \
    --cpu-affinity "$cpu_set" --max-concurrent "$max_concurrent" \
    --cap-bytes "$cap_bytes" | tee "$artifact_dir/preflight.json"

systemd-run --user --no-block --expand-environment=no \
    --unit="$unit" --service-type=exec \
    --property=Restart=no \
    --property=KillMode=control-group \
    --property="MemoryMax=$cap_bytes" \
    --property=MemorySwapMax=0 \
    --property="CPUAffinity=$cpu_set" \
    --property="WorkingDirectory=$repo_root" \
    --property="StandardOutput=append:$artifact_dir/service.log" \
    --property="StandardError=append:$artifact_dir/service.log" \
    --property="Environment=XDG_RUNTIME_DIR=/run/user/$UID" \
    --property="Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$UID/bus" \
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

for _ in {1..30}; do
    state="$(systemctl --user show --value --property=ActiveState "$unit" 2>/dev/null || true)"
    case "$state" in
        active) break ;;
        failed|inactive)
            if [[ -f "$artifact_dir/service_identity.json" && -f "$artifact_dir/service_summary.json" ]]; then
                python - "$artifact_dir/service_identity.json" "$artifact_dir/service_summary.json" "$unit" "$cap_bytes" "$cpu_set" <<'PY'
import json
import sys
from pathlib import Path

identity_path, summary_path = Path(sys.argv[1]), Path(sys.argv[2])
unit, cap_bytes = sys.argv[3], int(sys.argv[4])
cpus = sorted(int(value) for value in sys.argv[5].split(","))
identity = json.loads(identity_path.read_text(encoding="utf-8"))
summary = json.loads(summary_path.read_text(encoding="utf-8"))
if (
    identity.get("service_unit") != unit
    or identity.get("memory_max_bytes") != cap_bytes
    or identity.get("memory_swap_max_bytes") != 0
    or identity.get("restart") != "no"
    or identity.get("kill_mode") != "control-group"
    or identity.get("cpu_affinity") != cpus
    or not identity.get("invocation_id")
    or not identity.get("control_group")
    or identity.get("main_pid", 0) <= 1
    or not identity.get("main_pid_start_ticks")
    or summary.get("task44_service", {}).get("service_unit") != unit
):
    raise SystemExit(f"Task44 completed-service startup identity is incomplete or mismatched: {identity}")
if summary.get("classification") != "COMPLETED":
    raise SystemExit(f"Task44 service ended without a completed watchdog record: {summary.get('classification')}")
print(json.dumps({"startup_identity": identity, "completed_summary": summary}, sort_keys=True))
PY
                exit 0
            fi
            cat "$artifact_dir/service.log" >&2 2>/dev/null || true
            echo "Task44 service entered state $state before saving its startup identity" >&2
            exit 1
            ;;
    esac
    sleep 1
done
if [[ "$state" != active ]]; then
    cat "$artifact_dir/service.log" >&2 2>/dev/null || true
    echo "Task44 service did not become active" >&2
    exit 1
fi

if ! python - "$unit" "$artifact_dir/service_identity.json" "$cap_bytes" "$cpu_set" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

unit, receipt_path, expected_cap = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
expected_cpus = set(int(value) for value in sys.argv[4].split(","))
names = (
    "ActiveState", "MainPID", "InvocationID", "ControlGroup", "MemoryMax",
    "MemorySwapMax", "Restart", "KillMode", "WorkingDirectory", "CPUAffinity",
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
receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
if (
    not facts.get("InvocationID") or not facts.get("ControlGroup") or pid <= 1
    or receipt.get("service_unit") != unit
    or receipt.get("main_pid") != pid
    or receipt.get("main_pid_start_ticks") != start_ticks
    or receipt.get("invocation_id") != facts["InvocationID"]
    or receipt.get("control_group") != facts["ControlGroup"]
    or receipt.get("cpu_affinity") != sorted(expected_cpus)
):
    raise SystemExit(f"live systemd identity differs from saved startup receipt: {facts} / {receipt}")
print(json.dumps({"live_systemd": facts, "startup_identity": receipt}, sort_keys=True))
PY
then
    systemctl --user stop "$unit"
    exit 1
fi
