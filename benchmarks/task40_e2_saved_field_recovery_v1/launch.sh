#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering
ENTRY=$ROOT/benchmarks/task40_e2_saved_field_recovery_v1
RUN_ROOT=$ROOT/results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_e2_manual_m2_growth_v1__full3d_iterative__mpi1__Mna/20261002T023827.030745Z
REPAIR_ROOT=$RUN_ROOT/postprocess_repair_v2
WATCHDOG_DIR=$REPAIR_ROOT/watchdog
LOG_DIR=$ROOT/benchmarks/artifacts/user_services
LOG=$LOG_DIR/task40-e2-saved-field-recovery-v2.log
UNIT=myfenics-task40-e2-saved-field-recovery-v2-$(date -u +%Y%m%dT%H%M%S)-$$
MODE=${1:-launch}

if [[ "$MODE" == service ]]; then
    exec >>"$LOG" 2>&1
    cd "$ROOT"
    source scripts/activate_myfenics_wsl.sh
    export BLIS_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
    export MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
    python -u -m benchmarks.task40_e2_saved_field_recovery_v1.supervise
    exit $?
fi

if [[ "$MODE" != launch ]]; then
    echo "usage: $0 [launch|service]" >&2
    exit 2
fi
cd "$ROOT"
source scripts/activate_myfenics_wsl.sh
test "$(git branch --show-current)" = task40extra_0p7nm_engineering
test -z "$(git status --porcelain)"
test ! -e "$REPAIR_ROOT"
test ! -e "$LOG"
test "$(systemctl --user is-active default.target)" = active
mkdir -p "$REPAIR_ROOT" "$LOG_DIR"
systemd-run --user --unit="$UNIT" --service-type=exec \
    --property="WorkingDirectory=$ROOT" \
    --property="StandardOutput=append:$LOG" \
    --property="StandardError=append:$LOG" \
    /usr/bin/bash "$ENTRY/launch.sh" service
printf 'Unit: %s.service\nWatchdog: %s\nLog: %s\n' "$UNIT" "$WATCHDOG_DIR" "$LOG"
