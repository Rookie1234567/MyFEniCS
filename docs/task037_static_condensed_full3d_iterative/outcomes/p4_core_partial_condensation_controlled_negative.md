# V3 p4-core 部分凝聚收口：R7b2b1 controlled negative

## 结论

本轮把 p6 单元的部分凝聚接到了真实 compiled-form 的 assembly-time、DtN 增广和 full-field recovery 路径，但在最后的 public DtN complement Gate 失败，因此分类固定为：

`CONTROLLED_NEGATIVE_NUMERICAL_AT_R7B2B1_COMPLEMENT_GATE`

这不是 production-qualified solver，也不是完整 p4-core 部分凝聚方案已经可用的证明。R7a、R7b1、R7b2a 的局部和 assembly-time 组件 Gate 通过；R7b2b1 的真实 public integration 在一个明确的 342 维 eliminated-complement residual Gate 停止。

## 术语与方法

静态凝聚是先在每个有限元单元内部消去一批内部未知量，再把较小的边界/trace 系统交给全局求解器；它能减少全局行数，但必须在最后恢复被消去的场并计算完整真残差。

本实验的普通 fully condensed 路径会在每个 p6 单元的 `882=432` 个局部 trace slots 加 `450` 个 interior 行中消去 interior；这里的 432 是每个单元的局部 trace slots，不是声称正式全局系统只有 432 行。本轮的 research-only 路径在完整 p6 代数中保留真实 exact-sequence 嵌入的 108 个 p4 core 行，再消去其余 342 个 p5/p6 complement 行。目标是在保留 p4 结构的同时降低局部求解压力和内存，而不是先投影到一个不等价的小有限元空间。

| 阶段 | 内容 | 结果 | source SHA |
|---|---|---|---|
| R7a | local p4 hierarchy、orientation、rank/nested/projector、partial Schur 与 recovery | PASS；误差量级 `1e-14–1e-15` | `ed871cbae51396e30ad5a3fd6bf32dc7601a4020` |
| R7b1 | global retained numbering、action/RHS、left functional、bilinear、recovery | PASS；最大约 `2.58e-15` | `b93b72bac9095273c838ff653ca3bbf93567123c` |
| R7b2a | 真实 compiled-form assembly-time retained system | PASS | `0c882e7a6da38b6a66625e002fe64fabe0a70674` |
| R7b2b1 | public DtN、matrix-free C/D、augmented action、full recovery/residual | CONTROLLED NEGATIVE；complement Gate FAIL | `6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a` |

## R7b2a 组件证据

| Gate | 结果 |
|---|---:|
| serial `test244` | `1 passed`, `132.33 s`, MaxRSS `548212 kB`, action `3.913e-16`，其余关键误差 `0` |
| MPI2 `test244` | passed, `129.36 s`, MaxRSS `536320 kB`, action `4.371e-16`，其余 `0` |
| serial `test243` | `1 passed`, `34.50 s` |
| partial Schur ledger | `9331200 bytes` |
| eliminated factor ledger | `3745584 bytes` |
| basis ledger | `15070464 bytes` |
| maps ledger | `37304 bytes` |
| numbering ledger | `864 bytes` |

这些是小型组件/compiled-form evidence，不是目标 p6/h10 full solve 的内存预测。CSV 通用修复由独立 commit `6bc7d1e397834e4c316eaa3c59d4d90640835424` 承载，只把异构 diffraction rows 的字段改为稳定并集，不改变物理方程或求解路径。

## Candidate D 历史负证据

Candidate D 是此前的 serial algebra-only 局部 p2 factor inner-preconditioner 对照，不是本轮 public DtN 结果。D0 的 low/high/mixed 三组均未达到 `improvement >= 1.5`，因此后续 D screen/full 不运行：

| source | p2/p6 inventory | low `rho_B4 / rho_D / improvement` | high `rho_B4 / rho_D / improvement` | mixed `rho_B4 / rho_D / improvement` |
|---|---|---:|---:|---:|
| `6f152a6e50f8e8fc475fc6b3e2bc39aca1bdf1d2` | p2 factors `2`，factor NNZ `4608`；p6 matrix/factor `0/0`；rows、aggregate bytes `not_recorded` | `0.24599945418880295 / 0.2540230551088513 / 0.9684138870126958` | `0.24651896436171644 / 0.26531876351572775 / 0.929142594723057` | `0.24612971921817314 / 0.2715867504171219 / 0.9062655628087525` |

因此 D 的 20/100/200、full、restart 和 MPI1 均为 `not_run_by_D0_gate`。这些是已核实的受控负证据，不是待重跑的当前候选。

## 最终 public integration Gate

`test245` 使用真实 compiled p6、两 hexa cells、真实 Floquet/DtN surface forms 和 public assembly-time flow；不是伪造 retained system 的单元测试。测试命令为（在已执行 `source scripts/activate_myfenics_wsl.sh` 的同一 qualified shell 中）：

```text
source scripts/activate_myfenics_wsl.sh && /usr/bin/time -v python -m pytest -q -s src/test/test_245_task037_retained_dtn_adapter.py
```

最终有效运行结果：`1 failed, 1 passed`，exit `1`，wall `88.15 s`，MaxRSS `661088 kB`，swap `0`。目标路径的 visible solver data 如下：

| 量 | 实测值 |
|---|---:|
| tiny augmented rows | `760` |
| KSP reason | `2` (`CONVERGED_RTOL`) |
| RHS norm | `11.707507837771832` |
| solution norm | `275.1048734370968` |
| full relative true residual | `4.271433780052363e-11` |
| independent reduced residual norm | `2.169086505997297e-12` |
| eliminated complement norm | `5.000737489099658e-10` |

硬 Gate 是：

```text
complement_norm / max(independent_reduced_norm, 1.0) <= 1e-11
```

实际值为 `5.000737489099658e-10`，限值为 `1e-11`，约为限值的 `50.00737489099658` 倍，失败位置为 [test245 line 435](../../../src/test/test_245_task037_retained_dtn_adapter.py:435)。这是真实数值负结果，不是资源终止，也没有通过调阈值、xfail 或 skip 掩盖。

断言顺序必须如实解释：在该断言之前没有错误报告的 effective-RHS、无显式 C/D、p6 zero-inventory、reduced/full consistency 检查，不能因此把它们写成整套 Gate PASS；断言之后的 independent recovery 与 MPC assertions 没有执行，状态为 `not_run_by_assert_order`。

## 实现边界与早期 blocker

下列问题都是实现接线 blocker，已经在进入最终 hard Gate 前逐一修正，不应与最终数值负结果混写：

| blocker | 性质 | 收口 |
|---|---|---|
| public backend 与部分 legacy booleans 同时设置 | public config contract | test fixture 删除两行 legacy flags |
| pending PETSc augmented RHS Vec | PETSc lifecycle | retained `b_aug` 在 combine 前 assemble |
| row semantics 漏掉 retained core | retained trace/core/aux bookkeeping | `_dof_row_semantics` 显式加入 core rows |
| heterogeneous diffraction CSV fields | 通用 postprocess schema | `6bc7d1e3` 用首次出现顺序的字段并集 |
| eliminated complement residual | numerical Gate | 未通过，保留为最终 controlled negative |

## 内存、official observables 与停止边界

R7b2b1 只保留 research-only action/operator 审计，ordinary defaults 未改变，`production_qualified=false`。本轮没有 official R/T/A，也没有正式 p6/h10 memory evidence；`661088 kB` 只是 tiny two-cell pytest process 的 MaxRSS，不能外推目标模型。

因为 complement Gate 失败，以下项目全部是 `not_run_by_gate`：

- R7b2b2 p2/PC integration；
- setup-only formal memory ledger；
- MPI2 `test245`；
- MPI8 20/100/200 screen；
- full solve 与 official R/T/A；

Candidate E 与 Candidate F 不属于上述 Gate 列表：Candidate E 为 `not_run_by_latest_user_sequence`；Candidate F addendum 的读取为 `not_read_pending_v3_closeout`。

没有运行 full repository pytest；这是用户效率政策下的明确边界，而不是 full-suite PASS。test245 的 hard failure 原样保留，没有 xfail、skip 或阈值放宽。

## provenance

clean numerical carrier 是 `6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a`，branch 为 `codex/20260803-task37-matrix-free-iterative-development`，carrier 时相对 upstream `d875ba538f8334c5fd9e026192cacbdcd11e0794` 为 ahead `5`、behind `0`、worktree clean。五个相关 commit 为：

| commit | 作用 |
|---|---|
| `ed871cbae51396e30ad5a3fd6bf32dc7601a4020` | R7a local p4-core oracle |
| `b93b72bac9095273c838ff653ca3bbf93567123c` | R7b1 global retained action |
| `0c882e7a6da38b6a66625e002fe64fabe0a70674` | R7b2a assembly-time integration |
| `6bc7d1e397834e4c316eaa3c59d4d90640835424` | generic diffraction CSV field-union fix |
| `6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a` | R7b2b1 research-only carrier |

本文件及同轮 JSON 是文档 evidence 变更，不改变上述 numerical carrier；文档自身不自指一个尚未确定的文档 commit SHA。
