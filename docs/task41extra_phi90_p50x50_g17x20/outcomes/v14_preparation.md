# Task41 V14 保存包候选准备记录

**状态：代码准备完成，本记录随主控准备提交冻结；真实运行仍待用户明确授权。** 本文只记录准备、接线和验证；没有创建 V14 authorization、T0、window 或 consumer contract，没有启动 V14 systemd service，也没有运行真实 candidate。没有创建 `response_v14.md` 或科学结果。

## 身份与范围

- 仓库：`/home/fenics/Projects/laptop_share`；分支：`task41extra_phi90_p50x50_g17x20`。
- 本次代码准备基线 HEAD：`2eed8b0ce87eb2f334321c1d2b758f04ff7d09d1`；执行者交包时这九个文件尚未提交；主控已取回同一 canonical 执行分支集中冻结。工作站显示领先 116 是其本地 remote-tracking ref 陈旧，不表示真实 GitHub 尚有 116 个未推送提交。执行者没有 commit/push 或 merge。最终源码以包含本文的准备提交为准。
- 执行范围按 [review_report_v14.md](../review_report_v14.md)：只针对保存 RHS 的有界同 LU 残差校正候选。首阶段 cells 360、446 × 两列、状态 j0/j3；四个非零 RHS 合计最多 12 次 GETRS（每个 RHS 初解一次、最多两次校正）。只有独立 checker 通过才开放同一小窗口内的既存 star/代表键覆盖；全程最多 12 个去重 key。局部/覆盖结果不构成全域 action、official 或 scientific PASS，也不授权全域重建、200q 或 FGMRES。
- 拟议窗口限额沿现有合同：6 小时总窗 21,600 秒，数值 20,400 秒，收口 1,200 秒；新小证据目标不超过 16 MiB（本次 candidate/checker 也执行此上限），沿用单包 512 MiB、累计原始证据 16 GiB，可用空间底线 2 GiB。资源限制沿既有 Task41 合同、qualified native complex128/int32、MPI1、数学线程 1、task swap 0。以上是范围/合同值，不是实测或批准。

## 冻结前文件身份

下表是本次未提交快照中八个实现与测试文件的 SHA-256；freeze 后必须以实际提交内容重算并绑定 consumer contract。

| 文件 | SHA-256 |
|---|---|
| `scripts/run_case_in_user_service.sh` | `283e241259a1870307fc9d9c6787d40bf5a8fc5996e4ecabf6d807ab436dbf3b` |
| `scripts/task40_v20_service_workflow.py` | `14ebf9743937f8d36cc7ff8586abd761137e4919b1e224157dde48c781e69533` |
| `src/runners/task41_p0_contract.py` | `cec189a563ff0041dd0b727d7433d4f4624e376ba75ab580af285fd28b8b605e` |
| `src/runners/task41_p0_v14_candidate_io.py` | `09e9f7d896c24eae8c12b633f482670ef134604348a8bd5a9c994560f3b83a6a` |
| `src/runners/task41_p0_v14_saved_rhs_candidate.py` | `c9fe7c2b7e711ef4a44f68e870528dc52c9d1275c52483cc9d383573eb2a054d` |
| `src/runners/task41_p0_v14_saved_rhs_checker.py` | `6a1ac75b53290d77f26caaf0366e11a6e16cf9d45e7f8d448e02ab0ec6ee8150` |
| `src/test/test_task41_p0_v14_saved_rhs_candidate.py` | `520e863e4931f228dc16ae376eb6ab232f10266dc2b37d78e9b35851652de7ca` |
| `src/test/test_task41_p0_v14_service_route.py` | `fc29ba5c3a00433f9d2a6cccae8945dfd604ef2fa0b8de952d601d62c4dacc03` |

## 已核对的保存输入

这些是只读核验到的既有输入身份，不是 V14 运行产物：

| 输入 | 路径／身份 |
|---|---|
| V11 producer report | `results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt03/task41_p0_v11_selected_trace_candidate_replay.json`；SHA-256 `2463e322ea72160bfcca7f3345d149ab20e5b017982f1f9ed55010df0afa9876` |
| Accepted V11 independent checker | 同一 `selected_incident_replay` 下 `attempt06/task41_p0_v11_candidate_replay_saved_array_check.json`；SHA-256 `cdbd2a0a8d6ae62b61ad1a45b8bd4f62dae4c69ebb1f0f7923205ac85e4c3739` |
| Accepted V11 service receipt | 同一目录下 `attempt06.service/task41_p0_service_receipt.json`；SHA-256 `0b28a0f2b57aa17d515627097978a5470c7787ca9c61b15c07a0d25b14ae217f` |
| Donor contract | `benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller/execution_contract_source_afbe91e5947ed18fb74d7105097e129c1b8b4cc7.json`；SHA-256 `9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c`。服务预检复用 `require_task41_p0_contract` 注册合同校验。 |
| Donor summary | `results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261019T053402.514018Z/task40_v10_p6_candidate_summary.json`；SHA-256 `651c7a84db27e02c02879b10a28fe5580911678d25b5c7b8018a882d467c98d9` |
| V9 compact report | `results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261022T052401.200732Z/task41_p0_b0_v9_compact_volume_audit.json`；SHA-256 `e4db4e42b8a4f3b407ed0b00add8029f7e066aad6c38a2945d60e33ffbde7d93` |
| V11 source window | SHA-256 `4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6`；consumer 必须创建并绑定一个不同的新 window。 |

Donor manifest 的只读 stat 检查找到 141 个唯一数组路径、总字节 `9,379,882,344`，且当前文件存在并匹配登记大小；没有读取或散列 NPY 内容。V11 report 绑定的 V9 compact 路径位于上述独立 V9 run 下，不在 donor run 子目录；服务校验因此按注册 results root 与冻结报告 SHA 检查，而不错误要求 compact 文件位于 donor summary 目录。未创建缺失输出目录。

## 验证记录

在 qualified native complex activation 下运行：

```bash
unset _MYFENICS_WSL_QUALIFIED_ACTIVATION
source scripts/task40_fresh_c1/activate_native_complex.sh "$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix" "$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json" "$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/jit_cache" native_linux
python -m pytest -q src/test/test_task41_p0_v14_service_route.py src/test/test_task41_p0_v14_saved_rhs_candidate.py
```

pytest 工具转录：`2 passed in 4.41s`。服务接线 fixture 使用 `tmp_path` 下稀疏合成证据、固定 hash stub 和 mock `supervise`；它验证精确 26 项后缀、registered donor verifier 调用、同一 window/accounting 下候选 worker 与 checker 的两次监督，以及完成的数值拒绝仍写入独立 checker receipt。它没有读取实际 NPY、创建 systemd unit 或执行真实候选。

同一 qualified shell 随后 `python -m compileall -q` 覆盖上表全部 Python 文件；`bash -n scripts/run_case_in_user_service.sh` 与 `git diff --check` 均退出 0。CLI 只读帮助验证通过：

```bash
python -m scripts.task40_v20_service_workflow --help
python -m scripts.task40_v20_service_workflow run-service --help
python -m src.runners.task41_p0_contract --help
python -m src.runners.task41_p0_contract --prepare --help
```

`prepare` 本身没有运行。没有通过 shell wrapper 的 `--help` 探测，因为 wrapper 会启动实际服务。

## 明确授权之后才可运行的命令模板

以下是准备好的命令，不是运行授权；当前不要复制执行。先由主控在用户明确批准后创建 V14 authorization JSON，再在代码冻结提交后的干净工作树执行 prepare 一次。prepare 会登记新的 T0/window/consumer contract，不能重复刷新。

```bash
set -euo pipefail
cd /home/fenics/Projects/laptop_share
test "$(git branch --show-current)" = task41extra_phi90_p50x50_g17x20
test -z "$(git status --porcelain --untracked-files=normal)"
export CONTROLLER="$PWD/benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller"
export AUTH="$CONTROLLER/saved_diagnostics_v14_same_lu_rhs_candidate_authorization.json"
test -s "$AUTH"  # 仅主控在明确批准后创建
export RUNTIME_PREFIX="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix"
export ABI_RECEIPT="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json"
export JIT_CACHE="$PWD/benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/jit_cache"
unset _MYFENICS_WSL_QUALIFIED_ACTIVATION
source scripts/task40_fresh_c1/activate_native_complex.sh "$RUNTIME_PREFIX" "$ABI_RECEIPT" "$JIT_CACHE" native_linux
python -m src.runners.task41_p0_contract --prepare --case B0 \
  --runtime-prefix "$RUNTIME_PREFIX" --abi-receipt "$ABI_RECEIPT" --jit-cache "$JIT_CACHE" \
  --b0-saved-diagnostics-instance v14_same_lu_rhs_candidate_6h
```

审核 prepare 输出后，标准 `run_case_in_user_service.sh` 会在新专用 user systemd unit 内设置 contract/cgroup并运行既有 V14 worker→independent-checker 路由。以下模板从 V14 consumer、固定 donor 和已接受 V11/V9 小报告派生；`SOURCE_SHA`、`WINDOW_SHA` 与 `CONSUMER` 仅在冻结和 prepare 完成后填写：

```bash
export REPO_ROOT=/home/fenics/Projects/laptop_share
export RESULTS="$REPO_ROOT/results/task41extra_phi90_p50x50_g17x20"
export CONTROLLER="$REPO_ROOT/benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller"
export SOURCE_SHA="$(git rev-parse HEAD)"
export CONSUMER="$CONTROLLER/execution_contract_source_${SOURCE_SHA}_v14_same_lu_rhs_candidate_6h.json"
export CONSUMER_SHA="$(sha256sum "$CONSUMER" | awk '{print $1}')"
export WINDOW="$CONTROLLER/execution_window_v14_same_lu_rhs_candidate_6h.json"
export WINDOW_SHA="$(sha256sum "$WINDOW" | awk '{print $1}')"
export ATTEMPT="$RESULTS/task41_p0_saved_diagnostics_6h/$WINDOW_SHA/selected_incident_replay/attempt01"
export DONOR_CONTRACT="$CONTROLLER/execution_contract_source_afbe91e5947ed18fb74d7105097e129c1b8b4cc7.json"
export DONOR_SHA=9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c
export DONOR_RUN="$RESULTS/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261019T053402.514018Z"
export V11_REPORT="$RESULTS/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt03/task41_p0_v11_selected_trace_candidate_replay.json"
export V11_CHECKER="$RESULTS/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt06/task41_p0_v11_candidate_replay_saved_array_check.json"
export V11_RECEIPT="$RESULTS/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt06.service/task41_p0_service_receipt.json"
export V9_COMPACT="$RESULTS/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261022T052401.200732Z/task41_p0_b0_v9_compact_volume_audit.json"
export DONOR_SUMMARY="$DONOR_RUN/task40_v10_p6_candidate_summary.json"
export UNIT="myfenics-case-task41-p0-v14-candidate-$(date -u +%Y%m%dT%H%M%S)"
bash scripts/run_case_in_user_service.sh --service-unit "$UNIT" \
  --task41-p0-execution-contract "$CONSUMER" \
  --task41-p0-saved-b0-evidence-audit \
  --donor-contract "$DONOR_CONTRACT" --donor-contract-sha256 "$DONOR_SHA" \
  --summary "$DONOR_SUMMARY" --numerical-output "$DONOR_RUN/numerical_output" \
  --output-dir "$ATTEMPT" --v14-saved-rhs-candidate \
  --v11-report "$V11_REPORT" --v11-report-sha256 2463e322ea72160bfcca7f3345d149ab20e5b017982f1f9ed55010df0afa9876 \
  --accepted-checker "$V11_CHECKER" --accepted-checker-sha256 cdbd2a0a8d6ae62b61ad1a45b8bd4f62dae4c69ebb1f0f7923205ac85e4c3739 \
  --accepted-receipt "$V11_RECEIPT" --accepted-receipt-sha256 0b28a0f2b57aa17d515627097978a5470c7787ca9c61b15c07a0d25b14ae217f \
  --donor-summary-sha256 651c7a84db27e02c02879b10a28fe5580911678d25b5c7b8018a882d467c98d9
```

服务命令只适用于上述批准的 6 小时保存候选范围；candidate 被拒绝也必须保留完整 checker 报告。所有结果 `official_result=false`、`scientific_qualified=false`，不能据此启动后续全域计算。

## 主控交包边界

当前已实现首阶段四个 RHS 的生产核心、逐步保存、独立读回和现有 service 两次监督接线。条件性旧 star/八键覆盖只登记其范围；尚未实际运行或资格化。owner/target/reference/recovery 的新策略配置尚未实施，须首阶段与保存覆盖通过后在批准范围内接续；不能据本准备提交称为生产策略已全面接通。原全域 action FAIL 保持。

准备阶段没有新数值窗口费用；工程准备实际发生，完整排他墙钟没有连续收据，记 UNKNOWN，不记零。测试时间是上述工具转录的 pytest 父时间，不等于全部工程准备成本。共享核心已由前置提交 `2eed8b0ce87eb2f334321c1d2b758f04ff7d09d1` 冻结，相关九项核心测试通过；本准备最后两项接线测试不与早期重复试验累加为新的科学证据。
