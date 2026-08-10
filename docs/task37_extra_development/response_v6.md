# Task037-extra Response V6：H1R3 action-only 资格化交接

本文件是 Review V6 的 consolidated handoff。它只汇总已经完成的 action-only 证据，不把 derived 外推写成实测，不授权 H2，也不改变旧 response/outcome/record。

## 阶段总览

| 阶段 | source SHA | 状态 | 证据边界 |
|---|---|---|---|
| H1R3.0R | `5529a0159ac5b1500b4ccbd17ad962e2a875f3f1` | **PASS** | p6/h10 MPI1 single-source warm-repeat action |
| H1R3.1 | `c133a803d6086f6df8bf2cf703a53b43a79419c1` | **PASS** | p6/h10 MPI2 partition identity/action |
| H1R3.2 | `d25669db29a25608685cce3bfff1f63379885aa5` | **PASS** | p6/h5 MPI1 action-only scaling |
| H2 | — | `locked` | 不因三个 H1R Gate 通过而自动进入 |
| H3/H4/KSP/PDE/DtN/field/RTA | — | `not_run / locked` | 不在本轮范围 |

H1R3.2 的完整数值和 evidence 表见 [`h1r3_h5_scaling.md`](outcomes/h1r3_h5_scaling.md)，compact record 见 [`h1r3_h5_scaling.json`](../../benchmarks/cases/101_task37_extra_development/records/h1r3_h5_scaling.json)。

## 三阶段 evidence 索引

| 阶段 | outcome | record | record file SHA256 | embedded evidence SHA256 |
|---|---|---|---|---|
| H1R3.0R | [`h1r3_warm_repeat_v2.md`](outcomes/h1r3_warm_repeat_v2.md) | [`h1r3_warm_repeat_v2.json`](../../benchmarks/cases/101_task37_extra_development/records/h1r3_warm_repeat_v2.json) | `b2e347c1663df932ace40efdee898ca1c6a62790ce30b748e64fcb721bcac658` | `f86666a3a2c367ddd9b358a016b015e17ea8902ead912a1a451e12181dc80439` |
| H1R3.1 | [`h1r3_mpi2_partition_identity.md`](outcomes/h1r3_mpi2_partition_identity.md) | [`h1r3_mpi2_partition_identity.json`](../../benchmarks/cases/101_task37_extra_development/records/h1r3_mpi2_partition_identity.json) | `2e927f1734c676a9df48972e0d4e353cabee085b91772e78159d48628a33020c` | `2a5489e9e984f8805d435825079e4d65e8981067ac78a2f79651cc07f4305413` |
| H1R3.2 | [`h1r3_h5_scaling.md`](outcomes/h1r3_h5_scaling.md) | [`h1r3_h5_scaling.json`](../../benchmarks/cases/101_task37_extra_development/records/h1r3_h5_scaling.json) | `83224635e201d1f56ca91016e00bb437e46a68c2c78fd883d6563bc053dae7d9` | `76c8a538ad0f018336ab5d566694d426072ceb4a48a96a33441ee3f22cf08d41` |

历史边界：`response_v5.md` 中原 H1R3.0 因 audit key omission 的 `GATE_FAILED` 记录保持不变；这里的 H1R3.0R PASS 是 V6 授权的新 raw 与 v2 record，不是改写旧失败。

## H1R3.2 handoff 摘要

这次 action-only 测量验证的是“不保存全局矩阵，直接计算离散算子乘向量”的低存储路径。它不等同于把这个 action 放进 KSP 后就得到可收敛的 PDE 求解器。

| 指标 | 实测 / derived | Gate |
|---|---:|---|
| relative error | `2.868804640065144e-17` | `<=1e-11` PASS |
| finite / deterministic | `true / true` | PASS |
| retained payload / row | `33.9606954134006 B/row` | `<=45` PASS |
| packed temporary / row | `21.027155605932407 B/row` | `<=28` PASS |
| alpha payload | `0.9779306095631883` | `<=1.10` PASS |
| action seconds / row | `6.694560366078553e-6` | `<=1.03171980264e-5` PASS |
| b_peak | `312.42468700849327 B/row` | `<=512` PASS |
| process-tree peak | `638500864 B` | `<=805306368 B` PASS |
| swap / completion | `0 / 40.16706551914103 s` | PASS |

本次 rows/cells/axes/constraints 为 `1127502 / 1680 / (12,5,28) / 34542`。reference、candidate1、candidate2 时间为 `7.448299763025716 / 7.41738795908168 / 7.548130201874301 s`。canonical=false，canonical directory absent。

## 用户最终目标的边界

H1R3.2 的 h1 线性外推为 `P_h1_pred=36692207894.33216 B`，约 `36.692 GB` decimal、`34.172 GiB`。这是基于 h10/h5 action 数据的 derived action-only prediction，不是 h1 实测，也不是 full solver/PDE 内存资格化。

因此用户最终要求的“MPI1 PDE 小于 2 GB，并得到可比较的直接法物理结果”尚未达成。当前证据只证明了三个 H1 action Gate；没有运行 KSP、PDE、DtN、physical field、RTA 或 direct-method comparison，不能由 action PASS 推断这些结果。

## 冻结的研究边界

| 结论 | 状态 |
|---|---|
| G2 LOR-HX | `G2_FAIL`，冻结 |
| G3 additive LOR-HX | `prohibited` |
| old G4 sweep | `prohibited` |
| old H1.2 | `CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED`，历史事实保持 |
| ordinary default | `unchanged` |
| H2 | `locked` |

即使 H1R3.0R、H1R3.1、H1R3.2 全部 PASS，也不自动进入 H2；后续动作必须由新的 review 明确授权。本轮不自行扩展。

## Provenance、命令与证据

H1R3.2 formal source 为 `d25669db29a25608685cce3bfff1f63379885aa5`，start/end clean；watchdog 和 checker 各只运行一次，均 return code 0。详细复现命令、marker、Gate、raw SHA 和 compact evidence 见 [`h1r3_h5_scaling.md`](outcomes/h1r3_h5_scaling.md)。

实现/测试验证来自 qualified 环境：test285=`15 passed`；tests 280--285=`80 passed, 1 skipped`；compileall 与 `git diff --check` pass；Ruff=`unavailable`。这些是本地结果，不是 CI 结果。

一次非数值执行偏差已如实保留：checker 只运行一次，但初始 output parent 拼成了 `101_task037_extra_development`；没有重跑 checker、没有修改 raw，compact 原字节移动到合同固定的 `101_task37_extra_development`，错误空目录删除。该路径偏差不改变测量数值、SHA 或 PASS 分类。

## 交接状态

| 项目 | 状态 |
|---|---|
| action evidence | 已完成并通过 H1R3.0R/H1R3.1/H1R3.2 各自 Gate |
| full PDE / KSP / physical result | `not_run` |
| 用户 `<2GB` MPI1 PDE 目标 | 未达成、未测完整 PDE；action-only h1 derived 预测约 36.69 GB |
| 下一步 | 等待新的 review；不在本轮进入 H2/H3/H4 |
