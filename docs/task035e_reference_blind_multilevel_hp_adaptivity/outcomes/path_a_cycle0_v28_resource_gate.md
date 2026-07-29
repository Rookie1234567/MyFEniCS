# Path A cycle 0 v28 资源 Gate 收口

## 1. 结论

v28 严格停在 Path A cycle 0 的 `current -> p-shadow -> h-shadow ->
actual DWR`。没有执行 `cellwise_partition`，也没有启动 Path B、selected
action、cycle 1、p7/level-3 saturation、Hybrid 或新的证据 schema。

本轮 h-shadow 完整完成，正式 process-tree RSS authority 为
`10.237281799 GiB`，比 `11.0 GiB` Gate 低 `781.023 MiB`，zero swap。
59/59 个目标的 actual signed DWR effectivity 全部通过，full explicit true
residual 为 `1.671518829e-12`。未发现新的数值、Floquet、hanging 或 MPI
失败。

这个结果证明 v28 不是只以几 MiB 擦线通过；但目前只有一次 v28 正式运行，
因此不能把 `781.023 MiB` 余量表述为跨多次运行的统计稳定性。

## 2. 身份与范围

| 项目 | v27 | v28 |
|---|---|---|
| numerical source SHA | `1fa06c93593e3b6a97b05e1138147999a4587074` | `f1ba5627f163da54fa383b43be58fd38c0da7bc9` |
| ABI SHA-256 | `922fea7a7954404255818e12f8856d0cfd437646a54b0e55d1d7a923f74ad9a6` | 同左 |
| MPI | 8 | 8 |
| current | pass | pass |
| p-shadow | pass | pass |
| h-shadow | `controlled_resource_stop` | pass |
| v28 后续 stage | 不适用 | `not_run_by_frozen_scope` |

v28 campaign runner 使用 `--maximum-new-stages 5`，实际只产生以下完成
receipt：

1. `path-a-bootstrap-initial_plan`
2. `path-a-cycle-0-current_solve`
3. `path-a-cycle-0-shadow_target_discovery`
4. `path-a-cycle-0-p_shadow_discovery`
5. `path-a-cycle-0-h_shadow_discovery`

runner 报告的 `next_stage_id=path-a-cycle-0-cellwise_partition` 仅表示静态 DAG
中的下一节点；该节点没有执行。

## 3. 时间

`stage wall` 为 watchdog 的 `environment_before -> environment_after`；
`solver elapsed` 为完成的 `run_summary.elapsed_seconds`。v27 h-shadow 在资源
Gate 提前终止，没有同口径的 solver elapsed。

| stage | v27 stage wall (s) | v28 stage wall (s) | v27 solver elapsed (s) | v28 solver elapsed (s) |
|---|---:|---:|---:|---:|
| current | 240.718 | 239.304 | 234.776 | 233.352 |
| p-shadow | 234.316 | 236.323 | 226.645 | 228.683 |
| h-shadow | 350.649，提前停止 | 395.487，完整完成 | not available | 385.179 |

v28 h-shadow 比 v27 的停止时刻多 `44.838 s`，但这包括 v27 未执行完的
field、59-goal/DWR 和记录收尾，不能解释为同工作量的性能退化。

## 4. RSS、PSS、USS 与 swap

单位均为 MiB。RSS 使用正式 simultaneous process-tree authority；PSS/USS
为八个 worker rank 的 simultaneous `smaps_rollup` 合计。

| stage | run | RSS | PSS | USS | swap | 各指标峰值阶段 |
|---|---|---:|---:|---:|---:|---|
| current | v27 | 8340.023 | 6486.619 | 6244.867 | 0 | RSS `final_cleanup`; PSS/USS `after_field_output` |
| current | v28 | 8368.988 | 6491.735 | 6234.652 | 0 | RSS/PSS `final_cleanup`; USS `after_field_output` |
| p-shadow | v27 | 8403.137 | 7018.788 | 6909.078 | 0 | RSS `final_cleanup`; PSS/USS `after_augmented_matrix_finalize` |
| p-shadow | v28 | 8345.027 | 6955.710 | 6847.707 | 0 | RSS `final_cleanup`; PSS/USS `after_official_rta` |
| h-shadow | v27 | 11311.359 | 9641.703 | 9391.297 | 0 | RSS/PSS/USS `after_official_rta` |
| h-shadow | v28 | 10482.977 | 9541.340 | 9394.934 | 0 | RSS/PSS/USS `after_official_rta` |

所有阶段的 process-tree swap、rank `smaps` swap 以及系统 `pswpin/pswpout`
增量均为 0。

v27 h-shadow 的 combined authority 为 `11.046249390 GiB`，超过 Gate
`47.359 MiB`；v28 为 `10.237281799 GiB`，低于 Gate `781.023 MiB`。
端到端 h-shadow 峰值 RSS 下降 `828.383 MiB`，PSS 下降 `100.363 MiB`，
USS 增加 `3.637 MiB`。

## 5. 内存改动的可归因边界

### 5.1 transfer 临时量提前释放

v28 h-shadow 的八 rank lifecycle audit 实测：

| cleanup phase | sum-rank RSS before (MiB) | after (MiB) | released (MiB) |
|---|---:|---:|---:|
| nonmatching interpolation 后、round-trip forms 前 | 10430.258 | 7114.441 | 3315.816 |
| transfer 最终清理 | 7958.828 | 7417.484 | 541.344 |

两个阶段的 `malloc_trim` 均为 8/8 rank 调用成功。这里的
`3315.816 MiB` 是该生命周期点释放的 sum-rank RSS，不等于端到端峰值下降，
也不能与 PSS/USS 混用。

### 5.2 field-gradient streaming

v28 将 field-gradient basis 从“缓存所有采样 cell”改为“一次只保留一个
cell basis”，同时又加入了上述 transfer early release。由于两个改动在同一
numerical source SHA 中生效，raw evidence 没有只切换 streaming 的正式 A/B
运行。因此：

- 可以证明组合改动令 h-shadow RSS authority 下降 `828.383 MiB`；
- 可以证明 streaming 的梯度数值保持在下面给出的容差内；
- **不能**把 `828.383 MiB` 或其他数值单独归因给 streaming。

## 6. 59-goal、梯度与 signed DWR

差异定义为 `abs(v28-v27)`；relative 使用
`abs(v28-v27)/max(abs(v27), abs(v28))`。

v27 h-shadow 在得到完整 endpoint/gradient/DWR artifact 前被资源 Gate
停止，因此严格的 v27/v28 直接比较只覆盖 current goal values 和 p-shadow
goal/gradient/DWR。v28 h-shadow 是首次完整的 h-side evidence，不能写成
“h-side 与 v27 数值不变”。

| 可比对象 | 最大绝对差 | 最大相对差 | 对应目标 |
|---|---:|---:|---|
| current 59 goal values | `5.115907697e-13` | `2.893256795e-10` | abs: `scalar/interface_probe_l2`; rel: `bottom:m-4:n0:co_amp_real` |
| p-shadow 59 goal values | `1.136868377e-12` | `2.608952421e-10` | abs: `scalar/volume_probe_l2`; rel: `top:m-4:n0:co_amp_imag` |
| p-shadow 59 gradient norms | `7.927339341e-14` | `3.033636386e-11` | `top:m-6:n0:power` / `top:m-5:n0:power` |
| p-shadow 7 active-full gradient norms | `2.708944180e-14` | `1.096623703e-14` | abs: `scalar/volume_probe_l2`; rel: `scalar/A_volume` |
| p-shadow 59 signed DWR | `7.773781618e-13` | `2.127077622e-10` | abs: `scalar/interface_probe_l2`; rel: `top:m-3:n0:co_amp_real` |

gradient content hash 对浮点末位敏感：p-shadow 的 34/59 reduced gradient
hash 完全一致，25/59 改变；7 个 active-full gradient 中 3 个 hash 一致，
4 个改变。上表的范数差说明这些 hash 改变是约 `1e-11` relative 或更小的
浮点顺序差异，不能把 hash 不同误判为数学梯度改变。定向有限差分测试也已在
提交 `f1ba5627f163da54fa383b43be58fd38c0da7bc9` 前通过。

v27 与 v28 的 p-shadow effectivity 均为 59/59 通过，没有 opposite-sign 或
factor-two 外目标。v28 h-shadow 也为 59/59 通过：

- actual adjoint/DWR：`true`
- synthetic：`false`
- reference-derived：`false`
- endpoint delta used as DWR：`false`
- signed DWR 与 actual endpoint delta 的最大绝对差：
  `1.804786111e-12`，目标 `scalar/interface_probe_l2`
- 最大相对差：`5.348897797e-7`，目标 `top:m-4:n0:power`

## 7. Cellwise marking

用已有 raw JSON 在内存中调用现有 validator/marker 重建，未写新 receipt、
JSON 或 checker，也未运行 PDE。

p-shadow 的 cellwise marking 在 v27/v28 完全一致：

1. `cell:r42:l1:i1:j0:k0`
2. `cell:r37:l0:i0:j0:k0`
3. `cell:r42:l1:i1:j1:k0`
4. `cell:r13:l0:i0:j0:k0`

两版 canonical target set、ranking order 和
`REFERENCE_BLIND_LOCAL_MARKING_PASS` 分类均相同。对绝对贡献至少 `1e-6`
的 cellwise 项，最大相对差为 `7.41155e-9`，没有改变选择。

v27 没有完整 h-side cellwise 输入；v28 h-side 离线结果为
`REFERENCE_BLIND_VERIFICATION_ONLY`，目标
`cell:r47:l1:i1:j0:k1`，与此前完整通过的 v26 h-side 结果一致。它没有被
提交为 selected action，且 frozen v28 scope 不允许进入 candidate solve。

## 8. 数值与结构 Gate

v28 h-shadow：

- watchdog status：`task035e_blind_candidate_full_solve_pass`
- return code：0
- qualification failures：空
- full explicit true relative residual：`1.671518829e-12`
- active condensed rows：22,189
- matrix NNZ used：11,821,621
- actual conforming active FE DoF：66,434
- 181 leaves，p4/p5/p6 = 24/157/0
- 27 hanging patches，3,988 hanging slave rows
- hanging relation maximum residual：`3.929734508e-15`
- Floquet x/y/corner mismatch：0/0/0
- Floquet face transform/pairing residual：0
- final PETSc row ownership、cross-rank hanging expansion 和 PDE launch
  ownership Gate：pass
- MPI size：8；正式 smaps 样本全部观察到 8 ranks
- KSP/direct MUMPS、official result、artifact hash、source-clean-after：
  全部 pass
- numerical、residual、energy、curl、Rayleigh、Floquet、hanging、MPI
  failure：无

## 9. 停止分类

v28 满足 h-shadow `<=11.0 GiB`、zero swap、59/59 signed DWR 和所有已执行
数值 Gate。在 v27 能够直接比较的 current/p-shadow 部分，goal、gradient 和
signed DWR 只出现浮点末位差异，cellwise p 选择完全一致。

由于 v27 h-shadow 没有完成，不能逐项证明“h-side 与 v27 不变”；本报告将其
准确分类为“v28 首次完整 h-side pass”，而不是伪造跨版本等价。按用户冻结
范围，本轮在此停止并等待审阅，不启动第一次 selected p/h action。

## 10. Raw evidence 索引

共同根目录：

```text
benchmarks/artifacts/task035e/
```

v27：

```text
formal_1fa06c9_reference_blind_v27/runtime/campaign/attempts/
```

v28：

```text
formal_f1ba562_reference_blind_v28/runtime/campaign/attempts/
```

每个 stage 的主要 authority 是：

```text
*-watchdog.json
run-*/run_summary.json
run-*/memory_timeline.csv
```

59-goal/DWR 与 lifecycle 的核心文件是：

```text
0003-...-p_shadow_discovery/attempt-000001/p-live-dwr-bridge.json
0003-...-p_shadow_discovery/attempt-000001/run-p-shadow/task035e_p_shadow_evaluation.json
0004-...-h_shadow_discovery/attempt-000001/h-live-dwr-bridge.json
0004-...-h_shadow_discovery/attempt-000001/run-h-shadow/task035e_h_shadow_evaluation.json
```
