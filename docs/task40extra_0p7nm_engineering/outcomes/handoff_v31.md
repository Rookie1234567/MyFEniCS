# V31 窗口截止后的真实交接

本轮已批准并实际运行，下面旧 P0 的 PENDING 文本仅为历史。数值截止已触发且服务后代已清空；不得重放旧 full service 命令开启新窗口。

可复用的当前成果是 **q4 NUMERIC_COMPLETE_NATIVE_PENDING**（777424²，581086528 槽）。实际根、三数组及 pending 的完整 hash 见 [主控审计](records/review_v31_controller_closeout_audit.json)。q4 pending SHA256 为 `1938828321a57ee6eaaea0def485f73daddbd13432cc6ef8823d19bcc44640ad`，运行 source 为 `54cf6d367b07355c0ab08c8c10655ecac73cfc6a`，窗口 hash `57133ebfe54c109ca77af4e529df94708c29c2b4c79d301b862b01ee70cf8f56`。旧 donor source/window 保持原值。

下一窗口需明确批准后按既有 prepare/selector 导入 pending 和跨窗 consumer 身份，跳过 pattern/fill；只补必要 twist0 owner 和 q4 native。当前没有全八 q CSR/native、live factor bank、完整 reference 或 target field；不能运行 factor-only 假称 q4 已资格化。历史 q0 完整资格仍有效。先修正/评估 owner 准备的真实耗时，再依次新 twist，不为了包装问题重放已完成数值。

当前只读补检修复为 `c9c7f4af19917cbd2c0e4ecd5c0b167cab6752f5`。required checker 应使用原 input/summary/manifest/window 与原 run 的 numerical_output 定位，另写新补检输出；缺 footer 仍负。旧自动 checker 错误不得覆盖。精确已执行补检命令与结果记入本轮 run index；这份 handoff 不虚构尚未运行的下一窗口命令。

---

## 历史 P0 handoff

# Review V31 P0 handoff

P0 接线与定向测试已完成，交主控审核和源码冻结。生成本 handoff/test receipt 时，branch 为 `task40extra_0p7nm_engineering`，工作树含未提交 P0 修改，`HEAD=d7ffbfea952bc160742b18739369f2e3f656ee8e` 是 review 基线。主控随后集中冻结、提交/推送并回读真实 source SHA；源码文件 hash 已由 P0 compact 绑定。本交接没有启动 service、SSH、FE/JIT、payload 扫描、pattern/fill/native 或正式 q factor。

| 身份/状态 | 当前值 |
|---|---|
| Review | V31，commit `d7ffbfea952bc160742b18739369f2e3f656ee8e`，SHA-256 `d93625d435d4db47f2ae5ff2334558c17f4afec8523e63ee1cd2bc905eafe380` |
| 真实 V31 源码冻结 | 记录生成时待主控冻结；不得把当时 dirty worktree HEAD 当作批准源 |
| 新窗口审批 / T0 / window hash | PENDING / null / null；测试内临时 receipt、clock、window 均位于 pytest 临时目录，不是用户授权或运行窗口 |
| 旧 V30 | 到期；旧 T0、cutoff、deadline、失败、`NO_PARTIAL_FOOTER` 均保持原样 |
| 数值进度 | 本轮新增 q 矩阵/正式因子/场为 0；八 q、完整 reference、目标 PDE、R/T/A、2 TB/48 h 为 NOT_RUN/NOT_QUALIFIED。测试包含小型精确 MUMPS 单测，不属于 Task40 数值资格 |

最终五文件定向回归为 67 passed，原始日志与所有修改源码/测试文件 SHA-256 见 [P0 evidence index](records/review_v31_p0_evidence_index.json)。ABI receipt 为 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json`，SHA-256 `ac3a1120d8061fc91c818150177977e619de2fccb27fed1262cea45d90268426`。时间采用独立 UTC 与 monotonic 观察记录；两者及空闲时间边界均见 compact 和 `local_v31_preparation/p0_engineering_observations_v31.jsonl`。

## 主控冻结/部署后生成 P0 包

在已经登记的 workstation root 使用同一份资格化 native runtime。以下只生成 pending package，不创建 T0/window，也不启动数值服务：

```bash
cd /home/fenics/Projects/laptop_share
v31_source_sha="$(git rev-parse HEAD)"
v31_pending="benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_preparation/v31_pending_package/source_${v31_source_sha}"
source scripts/task40_fresh_c1/activate_native_complex.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache \
  native_linux
python scripts/task40_v20_service_workflow.py prepare-v31-p0 \
  --output-dir "$v31_pending" \
  --execution-root /home/fenics/Projects/laptop_share
```

命令由 `prepare_v31_pending_package` 实际生成；成功准备 fixture 使用同一个 builder，并校验其输出的合同路径、服务与 checker route。真正 package 的 `source_<sha>` 目录必须以主控冻结后读回的完整 SHA 为准。

## 只有用户明确批准新窗口后

主控收到新的直接批准后，才可在 pending package 内写入与真实用户答复绑定的 `user_approval_v31.receipt.json`，再调用下列 CLI。receipt 必须使用 review SHA、批准 scope、冻结 source SHA、执行根和真实原文；fixture receipt 不能复用。准备函数先固定三时钟 T0 与 43,200 s 窗口（42,000 s 数值、1,200 s 收口），再生成批准包。失败重试复用同一 anchor/window，不取新 T0。

```bash
cd /home/fenics/Projects/laptop_share
v31_source_sha="$(git rev-parse HEAD)"
v31_pending="benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_preparation/v31_pending_package/source_${v31_source_sha}"
source scripts/task40_fresh_c1/activate_native_complex.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache \
  native_linux
python scripts/task40_v20_service_workflow.py prepare-v31-approved \
  --pending-dir "$v31_pending" \
  --approval-receipt "$v31_pending/user_approval_v31.receipt.json"
```

`prepare-v31-approved` 的运行接线在临时成功 fixture 中通过了真实 `require_v31_execution_contract(current_root=...)`、`v31_launcher_values` 及 `load_fixed_campaign_window`/V31 campaign 校验。fixture 故意用批准字节和 clock 的假值，仅验证生命周期与身份绑定；不得将其中 T0 或合同移到真实工作站。

## 获批后由 builder 生成的运行与只读检查命令

下面是 pending builder 按冻结 SHA 生成并由 fixture 核对的命令模板。没有实际批准包、输出文件或服务运行；在新窗口批准前不得执行 service 命令。

```bash
cd /home/fenics/Projects/laptop_share
v31_source_sha="$(git rev-parse HEAD)"
v31_root="benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native/source_${v31_source_sha}"
v31_unit="myfenics-case-task40-v31-all-q-reference-${v31_source_sha:0:12}"
bash scripts/run_case_in_user_service.sh \
  --service-unit "$v31_unit" \
  "$v31_root/stage_inputs/full/target_original_ny8_resource_pilot_v20.dat" \
  --task40-v31-execution-contract \
  "$v31_root/execution_contract_v31.approved.json"
```

完整 official output 到达后，builder 生成的只读 checker route 为：

```bash
cd /home/fenics/Projects/laptop_share
source scripts/task40_fresh_c1/activate_native_complex.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache \
  native_linux
v31_source_sha="$(git rev-parse HEAD)"
v31_root="benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native/source_${v31_source_sha}"
v31_unit="myfenics-case-task40-v31-all-q-reference-${v31_source_sha:0:12}"
v31_outer="$v31_root/service_runs/$v31_unit/outer_workflow_record.json"
v31_summary="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_summary_path"])' "$v31_outer")"
v31_numerical_output="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["numerical_output_directory"])' "$v31_summary")"
python -m src.runners.task40_v10_output_checker \
  "$v31_numerical_output/v10_candidate_official_output.json" \
  --expected-channel-count 32060
```

若窗口在 full stage 受控停止，builder 生成的只读 partial checker 命令为：

```bash
cd /home/fenics/Projects/laptop_share
source scripts/task40_fresh_c1/activate_native_complex.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache \
  native_linux
v31_source_sha="$(git rev-parse HEAD)"
v31_root="benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native/source_${v31_source_sha}"
v31_unit="myfenics-case-task40-v31-all-q-reference-${v31_source_sha:0:12}"
v31_outer="$v31_root/service_runs/$v31_unit/outer_workflow_record.json"
v31_summary="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_summary_path"])' "$v31_outer")"
v31_manifest="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_manifest_path"])' "$v31_outer")"
v31_run_directory="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_directory"])' "$v31_outer")"
v31_numerical_output="$(python -c 'import json,sys; from pathlib import Path; p=Path(json.load(open(sys.argv[1]))["numerical_output_directory"]); print((p if p.is_absolute() else Path(sys.argv[2])/p).resolve())' "$v31_summary" "$v31_run_directory")"
python scripts/task40_v20_service_workflow.py check-partial \
  --input "$v31_root/stage_inputs/full/target_original_ny8_resource_pilot_v20.dat" \
  --summary "$v31_summary" \
  --manifest "$v31_manifest" \
  --numerical-output "$v31_numerical_output" \
  --stop-stage full \
  --output "$v31_root/service_runs/$v31_unit/partial_checker_result.manual.json"
```

official 与 partial checker 都只读原始输出，不补跑求解器；当前没有可检查的 V31 数值输出。上述路径/command 由 V31 builder 生成并在小 fixture 中核对，目标上真实生成的合同、window 和产物 hash 仍待主控冻结及之后的真实用户批准。

控制器冻结后只需回填实际 source SHA、approved contract/selector/input/window 哈希和真实 T0/cutoff/deadline。当前不得把这些待生成身份写成已知常量；不得改动旧 V30 文件，也不得以 P0 测试通过宣称科学阶段通过。
