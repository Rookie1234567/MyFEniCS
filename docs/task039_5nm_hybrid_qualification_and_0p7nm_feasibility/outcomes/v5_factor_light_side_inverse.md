# V5-7 compressed-factor side inverse：两 profile 资源负结果

## Compressed-factor family

这里的 compressed factor（压缩稀疏直接因子）是对每个 Hybrid 侧面矩阵做一次 MUMPS
直接分解，并尝试用 BLR 压缩降低因子存储。它替代的是侧面稀疏因子的存储方式，不是
把整个侧面问题变成无因子的迭代法，也不是减少 resident `W`。两次裁决都由 bottom 资源
结果决定；第二轮在 bottom 完成后只出现了 top exact begin，未完成 top。没有完成 outer
solve、recovery、field 或 R/T/A。

固定代数关系仍为：

```math
K = H - D F^{-1} C, \qquad z = F^{-1}r, \qquad y = z + F^{-1}(C K^{-1}Dz).
```

两个 profile 都是 research-only、显式 opt-in；ordinary default、物理参数、M480、packet
和数学方程不变。

## 结论先行

| profile | BLR controls | bottom candidate peak | limit | resource Gate | 数值 Gate |
|---|---|---:|---:|---|---|
| `mumps_blr_v5_h4` | ICNTL35=1, CNTL7=1e-5, ICNTL14=80 | 75.89627456665039 GiB | 59.7638938904 GiB | fail | not_available |
| `mumps_blr_v5_h4_1e3` | ICNTL35=1, CNTL7=1e-3, ICNTL14=80 | 95.39834594726562 GiB | 59.7638938904 GiB | fail | not_available |

因此 BLR compressed-factor family 在这两个预先冻结的 profile 后关闭：不增加第三个
profile，不进入 V5-8 BLR full formal。资源负结果不是把数值结果改写成失败；对于第二个
profile，candidate apply 已执行，但逐 probe 数值报告没有在受控停止前持久化。

## 共同身份与证据

固定范围为 5 nm、1° grazing、phi=0°、S、p6/h4、M480、MPI8、shared packet、streaming
batch=8。packet consumer marker 记录 `qep_calls=0`；manifest SHA256 为
`2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067`，external keys 为
600 个，hash 为 `ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a`。

本证据文档由 HEAD `7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f` 生成；两个 formal run
各自的源码 SHA 在对应 profile 小节中单独列出。compact record 中的
`formal_run_preflight_clean=true` 只表示正式运行启动前的 clean preflight，不表示当前
文档编辑后的 worktree 状态。当前分支仍为 upstream 0/0。
原始 artifact 保持在 ignored results 目录，compact 索引为
[factor-light compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_factor_light_side_inverse_v1.json)。

## Profile 1：`mumps_blr_v5_h4`（CNTL7=1e-5）

原始目录为 `results/task039_v5_h4_mumps_blr_side_component_mpi8_2f1e6581`。该轮 bottom
candidate closed interval 的 process-tree RSS peak 为 75.89627456665039 GiB，已经高于
59.7638938904 GiB，因此 resource Gate 独立失败。该轮后来还遇到已修复的 spool
Mat→Vec tuple-shape implementation bug；这不是数值 probe failure，数值 Gate 必须写
`not_available`。

该 formal run 的源码 SHA 为 `2f1e65812f25b91cc22f5bd01debe7bd77790c08`。

K rank=296，condition=8.406536759948988，setup=259.3729111700086 s。MUMPS controls
实际读回 ICNTL35=1、CNTL7=1e-5、ICNTL14=80。raw `run_summary` 为
`exit_status=2/worker_nonzero`；不能用它宣称数值失败。

## Profile 2：`mumps_blr_v5_h4_1e3`（CNTL7=1e-3）

原始目录为 `results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3`。主进程
在 bottom resource Gate 已充分失败后受控停止；watchdog 的 parent session 返回 130，
但完整 MPI 进程组已清理。raw `run_summary.json` 因中断 finalizer 仍为
`status=launching`、`exit_status=null`，必须保持原样，不能伪造成正常 worker exit。
该 formal run 的源码 SHA 为 `7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f`。

| 字段 | measured evidence |
|---|---:|
| bottom interval | 6850.724118696002–8073.42587975401 s |
| bottom interval measured samples | 4805 |
| bottom peak | 102433193984 B = 95.39834594726562 GiB |
| overall process-tree peak | 111036112896 B = 103.41043853759766 GiB |
| swap | 0 |
| factor NNZ | 1230486984 |
| K rank / condition | 296 / 66984.51457458506 |
| K setup | 243.44643826101674 s |
| apply / base solves | 13 / 26 |
| apply wall | 21.315801888122223 s |
| cleanup factors | exact/compressed/global = 0/0/0 |

W 不驻留；streaming batch 的 local dense response buffer peak 为 1,994,496 B，最大
rank-local batch peak 为 2,334,720 B。这些是对象/局部 buffer 证据，不与 process-tree RSS
相加，也不能解释为 RSS 节省。当前高水位出现在 compressed sparse factor resident 的
阶段；cleanup 后 factor counts 已归零，aligned RSS 约为 90.6263 GiB，低于 direct
baseline `93.377006531 GiB`。但这不能消除 candidate 闭区间内已经测得的 95.39834594726562
GiB 峰值，所以 component Gate 仍失败；失败依据是历史闭区间峰值，不是 cleanup 终点 RSS。

Candidate 在 cleanup marker 中记录 13 次 apply、26 次 base solve、D/C 各 13 次，且 action
和 factor count 已清理。六组 bottom reference RHS/exact-output spool 均已完成；candidate
逐 probe 的 finite、repeat、linearity 和 full side true residual 没有持久化，所以数值
Gate 为 `not_available`，不是 pass，也不是 fail。top 在 bottom resource Gate 后不再运行，
记录为 `not_run_due_bottom_resource_gate`；raw 中已有 top begin-only marker，不添加假的 top
ready/cleanup marker。

## 六组 reference spool

每组都有 8 个 rank-local RHS 文件和 8 个 rank-local exact-output 文件，dtype 为 complex128、
global size=132300。`physical_side_rhs` 的 `system.b` norm=0，标为
`degenerate_uninformative`；其余五组是 mandatory non-degenerate probes。

| label | source | source norm | RHS global identity | exact-output global identity |
|---|---|---:|---|---|
| `physical_side_rhs` | `system.b` | 0 | `280c00e1df3df3d2c07d5cd8bf1766a0860a1b895e1dff3e059ac99dd2e4bbae` | `af2a2ab51645d9ecc9ced26021d5c9f63145a14e6a828a92a15ee3944f02f96d` |
| `modal_traction_positive` | `positive_traction` | 5.203888364374478 | `fbb08a8c70a92505f8146b52ef046d568d745f2caf948fbd63eadcdb48295413` | `3100fd4f186ba720ef8ef030e4fc45749d6726927e420102884d71016b0fe8cb` |
| `modal_traction_negative` | `negative_traction` | 4.617843033490231 | `b9eaee3ee19c1f269eb0498250ae5660fef6d75918942a080d9d319a53618a70` | `a7a42879e64d78e3de3f956747806b628f01fa482bece281a8b20bda1bf065e4` |
| `external_dtn_coupling` | `pre_action_components.C` | 107.45953654437677 | `27dcd213b93c08657247b27edd97525b474a425422fef533a7b3a8e701554b1d` | `f0f1c970644aebe13a7fe94806205f83c02c5ea90554ccc2987bd5720d7c37f8` |
| `fixed_random_repeat_0` | `fixed_owner_range_formula` | 363.932277457305 | `5fdd169ff2bb3ee10c3546332c9f81be0f9c4125a1fdc3c82c48538cc1ae3f6e` | `5322aabafa153d073e635fd80aa1f729f7e1c9c98dab2032ef3f2a67d6860baa` |
| `fixed_random_repeat_1` | `fixed_owner_range_formula` | 363.3362600209126 | `bdd51ab7843f1560a6866de738a312cfbd89a01d9eabe794f3e12abbf3097b63` | `51429f3bd4db63c6cb870d10b7e6f757ac82255fa8871bb4af9d8449eeaa2c93` |

每组 rank0000 的 RHS/exact-output array SHA，以及全部 raw timeline SHA，见 compact record；
这里的 global identity 不是 process-tree RSS，也不把数组内容当成物理 Gate。

## 资源边界与下一 family

两 profile 都未达到 `<=59.7638938904 GiB` 的 bottom candidate setup resource Gate；
第二 profile 的 bottom peak 也高于既有 Hybrid direct baseline `93.377006531 GiB`。
因此不能把该 family 写成“压缩成功”，也不能进入 BLR V5-8 full formal 或增加第三个
profile。没有产生 Full3D、outer solve、recovery 或 observable 结论。

Review V5 §14.1 的下一步只保留 physics-aware fixed-budget side Krylov component：它应是
一个 bottom-first、单一冻结预算的 research component，以当前 packet/spool 的固定 RHS 和
同一 side true-residual 公式做小规模/受控验证；不能复用已否定的 ordinary ILU scan，不能
扫描 seed/rank/depth/tolerance，也不改变 ordinary defaults。这个设计阶段不等于已运行或已
通过。

## Raw SHA 索引

| profile | run_summary | memory_stages | marker stream | process-tree samples |
|---|---|---|---|---|
| `mumps_blr_v5_h4` | `8fd398f2c002cc3234c0a8cae60a47aacd88019e4f5700c66edf1f562e9e2af6` | `0116f18b9d2c21ba7692adec5980eeec10065057a20e8f4062cabe22312c3c32` | `fcb4fc8a7c6dcd022e8ef7233218fea9e34fd9f64f95f39fad4ea4c261f9026a` | `00494ff7a07a5c073b9cd64d1ffae55ca6b394827a91b4b7861dfe1612009a41` |
| `mumps_blr_v5_h4_1e3` | `e0f04e112b99d4b96b78e9f083cfa0e8aad0d8d2e7c070a7eb1e1a4030ae9342` | `85a074096459a82e162fa0b8b63f9365bc6dafed215a00c8f130662c2a4a66c6` | `a2390feee04b852b6299f50ba49b7c5ecb7e88adfaab14ced5d84b9641475d7a` | `ef1896483272fcb052ba8bba04e8269f5090b5506666d6a97b335703888c50f5` |

## Fixed-budget physics-aware side Krylov family

压缩因子路线的两个冻结 profile 已经耗尽且均未通过资源门；Review V5 §14.1 的第二个、也是最后一个 family 是固定预算的 bottom side Krylov 组件。它只用固定预算 `32` 尝试近似侧逆，不是普通 ILU 扫描，也不是新的 production solver。

正式 raw 为 [`fixed-budget bottom raw`](../../../results/task039_v5_h4_fixed_budget32_bottom_sideonly_component_mpi8_ff89f07b)。该轮在两个非退化 traction probe 上得到真实数值负结果，随后按 numerical Gate 停止；没有把未运行的 probe 或 cleanup 伪写成通过。

| 项目 | measured / derived evidence | 裁决 |
| --- | --- | --- |
| fixed budget / scope | `32`, bottom-only, p6/h4, M480, MPI8, packet QEP calls `0` | frozen research component |
| setup closed interval | `23275851776 B = 21.677326202393 GiB`, interval `[184.573611289,492.894576008] s` | setup resource sample pass；不是完整 run resource qualification |
| physical RHS | `degenerate_uninformative=true`, residual/repeat `0/0` | informational only |
| modal traction + | true residual `0.748109402736452`，limit `0.01` | fail |
| modal traction - | true residual `0.737754681505050`，limit `0.01` | fail |
| external/random probes | external 只有 begin；两组 random 未运行 | not_run |
| factor identity | ILU0 base `1`；exact/global direct `0/0` | observed before stop |
| cleanup | 无 final cleanup marker；factor-after-destroy/action cleanup | not_available |

最终分类为 `TASK039_V5_FIXED_BUDGET_SIDE_KRYLOV_NUMERICAL_NEGATIVE_CONTROLLED_STOP`。这不是资源超限：setup sample 低于 `59.7638938904 GiB`，但 mandatory numerical Gate 已失败，不能进入 top/outer/recovery，也不能生成 official R/T/A。完整字段、raw SHA 与 `status=launching`/`exit_status=null`/`ledger=in_progress` 的边界见 [fixed-budget compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_fixed_budget_side_krylov_component_v1.json)。
