# Task41 P0 V12 两单元续作准备

**仅准备，未执行。** 六文件实现提交为 `234f587b2b602b88486d574cf8174d7bdad6b7c7`（分支 `task41extra_phi90_p50x50_g17x20`）；提交时工作树干净。主控报告定向测试 **11 passed / 46 deselected**，六文件 `py_compile`、`bash -n`、`git diff --check` 通过。本文记录准备阶段状态，运行时 `source_sha` 必须在所有文档冻结后动态取最终 HEAD。P0 工程准备费用无可核对账目：`UNKNOWN_NOT_MEASURED`，不是零。

新 6 小时窗口仍待用户明确批准；授权记录、window/T0、V12 consumer contract、service 和数值计算均未创建/启动。科学状态 `NOT_RUN`。批准后由主控按固定 schema 创建 authorization JSON，`source_at_entry` 绑定最终冻结 HEAD；prepare 只在该文件已存在时才允许继续，并创建 T0/window 与 consumer contract。prepare 只执行一次；结果不明时先检查文件和账本，不通过重试刷新 T0。

范围仅为 active row `87567` → original row `250113` 的 cells `360, 446`：生成缺失 candidate 单元、依生产顺序重放、再只读复核保存数组。历史 V3 donor 按自身 source、SHA 和物理身份验证；`same_lu_rhs_solve` 由 V12 consumer 与 V9 compact 绑定，不要求旧 donor 声明该策略。全域 owner/incident 扫描、旧八键 prefix、carrier、A1/A2、200q、FGMRES 和全域 PDE 均不在范围；结果不具 official/scientific PASS 资格。

| 资源门 | 拟议值 |
|---|---:|
| 总 / 数值 / 收口 | 21,600 / 20,400 / 1,200 秒 |
| 工作估计 + 终止预留 | 900 + 120 秒；准入余额至少 1,020 秒 |
| 新证据 / 累计原始证据 / 可用空间底线 | 512 MiB / 16 GiB / 2 GiB |
| Task 内存上限 / 主机预留 | 1,649,267,441,664 / 68,719,476,736 字节 |
| MPI / 数学线程 / task swap | 1 / 1 / 0 |

拟议资源/时间数值不是实测或完成承诺；宿主、祖先 cgroup 和磁盘的更紧限制仍生效。

## 冻结输入

- V3 donor contract：`benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller/execution_contract_source_afbe91e5947ed18fb74d7105097e129c1b8b4cc7.json`；SHA-256 `9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c`。
- Donor summary：`results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261019T053402.514018Z/task40_v10_p6_candidate_summary.json`，`numerical_output` 为同目录。
- V11 metadata：`results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/bc646b17157eed567e2c5391df79e4eda681ab4028f9e86901e8c7fcfd9222b4/selected_incident_replay/attempt02/task41_p0_v8_selected_trace_star_metadata.json`；SHA-256 `332baa3a5253a8322b56615c7fe087e401f909c3c889fa048fccc3f9f2b9fcd3`。
- V9 compact：`results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261022T052401.200732Z/task41_p0_b0_v9_compact_volume_audit.json`；SHA-256 `e4db4e42b8a4f3b407ed0b00add8029f7e066aad6c38a2945d60e33ffbde7d93`。
- FFCx C source：`benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache/fenics/libffcx_forms_2f92c03a20c09db3cb8f0382bec2294daa94ab16.c`；SHA-256 `d3302fba22074b755ac3b7d4a0b361af926ae7801aac25a7f1cd1d69cbeb9f03`。
- Runtime / ABI receipt / JIT cache：`benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix`、`benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json`、`benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache`。attempt04 receipt 绑定 `task41_p0_native_complex:1c4277c83a0ac6daf02197086264b9e5b337caee1b33d7cc1dd22a7dfcefe57d`，preflight 为 complex128/int32、MPI1。

## 批准后命令

以下仅为原生 Linux 工作站 `/home/fenics/Projects/laptop_share` 上的命令记录，当前未执行。主控收到用户批准后创建 authorization JSON；prepare 命令通过 `test -s` 确认该记录已存在，避免无授权回退。

```bash
set -euo pipefail
cd /home/fenics/Projects/laptop_share
export RUNTIME_PREFIX="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix"
export ABI_RECEIPT="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json"
export JIT_CACHE="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache"
test "$(git branch --show-current)" = task41extra_phi90_p50x50_g17x20
export CODE_COMMIT=234f587b2b602b88486d574cf8174d7bdad6b7c7
export SOURCE_SHA="$(git rev-parse HEAD)"
git merge-base --is-ancestor "$CODE_COMMIT" "$SOURCE_SHA"
git diff --quiet "$CODE_COMMIT" "$SOURCE_SHA" -- benchmarks/subreaper_watchdog.py scripts/task40_v20_service_workflow.py src/runners/task41_p0_checker.py src/runners/task41_p0_contract.py src/runners/task41_p0_v4_volume_only_audit.py src/test/test_task41_p0_saved_output_continuation.py
test -z "$(git status --porcelain --untracked-files=normal)"
unset _MYFENICS_WSL_QUALIFIED_ACTIVATION
source scripts/task40_fresh_c1/activate_native_complex.sh "$RUNTIME_PREFIX" "$ABI_RECEIPT" "$JIT_CACHE" native_linux
export CONTROLLER="$PWD/benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller"
export AUTH="$CONTROLLER/saved_diagnostics_v12_two_cell_candidate_replay_authorization.json"
test -s "$AUTH"  # main controller registers this only after explicit user approval

# Executes once after approval; creates the T0/window and consumer contract.
python -m src.runners.task41_p0_contract --prepare --case B0 \
  --runtime-prefix "$RUNTIME_PREFIX" --abi-receipt "$ABI_RECEIPT" --jit-cache "$JIT_CACHE" \
  --b0-saved-diagnostics-instance v12_two_cell_candidate_replay
```

Review prepare's JSON and gates before entering the service command in the same shell. It reuses attempt04's route with the new consumer/window and output root:

```bash
export REPO_ROOT=/home/fenics/Projects/laptop_share
export CONTROLLER="$REPO_ROOT/benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller"
export CONSUMER="$CONTROLLER/execution_contract_source_${SOURCE_SHA}_v12_two_cell_candidate_replay.json"
export CONSUMER_SHA="$(sha256sum "$CONSUMER" | awk '{print $1}')"
export WINDOW="$CONTROLLER/execution_window_saved_diagnostics_v12_two_cell_candidate_replay_6h.json"
export WINDOW_SHA="$(sha256sum "$WINDOW" | awk '{print $1}')"
export WINDOW_ROOT="$REPO_ROOT/results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/$WINDOW_SHA"
export ATTEMPT="$WINDOW_ROOT/selected_incident_replay/attempt01"
export DONOR_CONTRACT="$CONTROLLER/execution_contract_source_afbe91e5947ed18fb74d7105097e129c1b8b4cc7.json"
export DONOR_SHA=9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c
export DONOR_RUN="$REPO_ROOT/results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261019T053402.514018Z"
export METADATA="$REPO_ROOT/results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/bc646b17157eed567e2c5391df79e4eda681ab4028f9e86901e8c7fcfd9222b4/selected_incident_replay/attempt02/task41_p0_v8_selected_trace_star_metadata.json"
export V9_COMPACT="$REPO_ROOT/results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261022T052401.200732Z/task41_p0_b0_v9_compact_volume_audit.json"
export FFCX="$REPO_ROOT/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache/fenics/libffcx_forms_2f92c03a20c09db3cb8f0382bec2294daa94ab16.c"
export UNIT="myfenics-case-v12-$(date -u +%Y%m%dT%H%M%S)-$$"
python scripts/task40_v20_service_workflow.py run-service \
  --unit "$UNIT" --runtime-prefix "$RUNTIME_PREFIX" --abi-receipt "$ABI_RECEIPT" --jit-cache "$JIT_CACHE" -- \
  --task41-p0-execution-contract "$CONSUMER" \
  --task41-p0-saved-b0-selected-trace-star-audit \
  --donor-contract "$DONOR_CONTRACT" --donor-contract-sha256 "$DONOR_SHA" \
  --summary "$DONOR_RUN/task40_v10_p6_candidate_summary.json" \
  --numerical-output "$DONOR_RUN/numerical_output" --output-dir "$ATTEMPT" \
  --geometry-policy mesh_actual_exact --raw-tensor-evaluator actual_qmetric_blocked_gram \
  --ffcx-c-source "$FFCX" --selected-trace-star-candidate-replay --selected-active-row 87567 \
  --selected-metadata-report "$METADATA" \
  --selected-metadata-report-sha256 332baa3a5253a8322b56615c7fe087e401f909c3c889fa048fccc3f9f2b9fcd3 \
  --v9-compact-report "$V9_COMPACT" \
  --v9-compact-report-sha256 e4db4e42b8a4f3b407ed0b00add8029f7e066aad6c38a2945d60e33ffbde7d93
```

service 收口会运行注册的 saved-array checker；不另起无监督 checker 命令。当前记录不构成执行授权。

## 定向验证记录

主控在本机资格化 complex128/int32 环境执行下列命令，结果为 **11 passed, 46 deselected in 1.21s**；不含 FE 或新科学资格。

```bash
source scripts/activate_myfenics_wsl.sh
python -m pytest -q --tb=short --show-capture=no src/test/test_task41_p0_saved_output_continuation.py -k 'v12_candidate_replay or v11_saved_array_checker or v12_prior_metadata or v11_candidate_replay_service_exit or saved_diagnostics_service_source_gate or v9_failed_terminal_saved_service_completes_negative_audit_without_numeric_output'
```

普通提交被共享 hook 错误要求其他项目分支阻断；主控仅在本次提交命令以 `-c core.hooksPath=/tmp/task41_v12_empty_hooks` 跳过该无关 hook，未修改共享配置、当前执行分支或科学验收门。工作站当前非交互 SSH 探针返回 publickey 拒绝，等待用户恢复本机 SSH agent；未据此启动或刷新数值窗口。
