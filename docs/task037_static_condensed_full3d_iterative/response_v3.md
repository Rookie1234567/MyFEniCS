# Task037 Review V3 阶段回应：p4-core 部分凝聚收口

## 1. 当前结论

本轮 V3 只收口 p4-core 部分凝聚实验，不把 research-only 路径提升为 ordinary 或 production solver。普通静态凝聚是把每个单元的内部未知量先消去，使全局系统只保留 trace 与辅助变量；对每个局部 p6 `882=432 trace slots + 450 interior` block，本轮保留真实 exact-sequence 嵌入的 108 个 p4 core 行，再消去 342 个 p5/p6 complement 行。这里的 432 是每个单元的局部 trace slots，不是声称正式全局系统只有 432 行。

R7a、R7b1、R7b2a 的局部/全局组件 Gate 通过；R7b2b1 在真实 public DtN integration 的 eliminated-complement Gate 失败。最终分类为：

`CONTROLLED_NEGATIVE_NUMERICAL_AT_R7B2B1_COMPLEMENT_GATE`

这表示实现到达了真实 public path，但一个明确的数值质量门槛未通过；它不表示资源终止，也不表示已经得到可替代 direct 的收敛迭代解。

## 2. V3 §11 的12项回应

| 项 | review_report_v3 §11要求 | 本轮事实与状态 |
|---:|---|---|
| 1 | source/branch/environment/clean identity | numerical carrier=`6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a`；branch=`codex/20260803-task37-matrix-free-iterative-development`；carrier upstream=`d875ba538f8334c5fd9e026192cacbdcd11e0794`；ahead/behind=`5/0`；carrier clean；qualified activation、项目 `.venv`、PETSc complex128/int32、同一 Linux ABI。 |
| 2 | matrix-free DtN action、aux recovery、mode-key identity | `test230` 是 `n_aux=3` synthetic algebra fixture，serial/MPI2/MPI4 均通过；matrix-free action 断言 `<=1e-11`，aux recovery 断言 `<=1e-11`，已记录的 MPI2 aux-recovery actual=`3.2871030941353094e-12`，explicit C/D count=`0`。mode-key/beta/polarization/Rayleigh 是 structural identity：`matrix_free_dtn` 分支前后复用同一个 `outgoing_port_modes_3d(cfg)` `modes` 对象，后续 R/T 继续使用同一数据流；这不是实测 80-mode MF PDE identity。Case100 direct 80-mode artifact/既有 mode tests 只作 supporting boundary。H 仍为 `80x80` diagonal AIJ，`SmallDenseInverse` 仍有 dense replica，是未来数千 mode/0.7nm scaling debt，本轮未解决；formal 80-mode MF PDE=`not_run`。F5b 的 fine action=`9.230923702042441e-16`、337 iterations、12/12 power 与12/12 amplitude通过，只是历史 physical/full supporting evidence，不替代上述 component/structural evidence。 |
| 3 | Candidate D 局部 p2 slab rows、matrix/factor NNZ、总内存 | p2 factor count=`2`、factor NNZ=`4608`、p6 matrix/factor=`0/0`；rows、aggregate bytes=`not_recorded`；D为serial algebra-only，非PDE。 |
| 4 | D local low/high/mixed contraction | low `0.24599945418880295 / 0.2540230551088513 / 0.9684138870126958`；high `0.24651896436171644 / 0.26531876351572775 / 0.929142594723057`；mixed `0.24612971921817314 / 0.2715867504171219 / 0.9062655628087525`，顺序均为 `rho_B4 / rho_D / improvement`。 |
| 5 | D 20/100/200 residual history与screen Gate | D0 low/high/mixed 三组 improvement 均未达到 `1.5`；D 20/100/200均 `not_run_by_D0_gate`，没有可写的 screen residual history。 |
| 6 | full solve true residual、canonical field、12+12 channels、R/T/A | 当前 p4-core R7b2b1 没有新 full solve，以上均 `not_run_by_gate`；既有 F5b/V2 full evidence属于历史路径，不能冒充 p4-core public integration。 |
| 7 | restart | D0未通过，D restart `not_run_by_D0_gate`；没有 restart 数值。 |
| 8 | MPI1 minimum memory | D0未通过，MPI1 minimum-memory run `not_run_by_D0_gate`；没有该项实测值。 |
| 9 | 当前 partial-condensation evidence | R7a/R7b1/R7b2a组件 PASS；R7b2b1 tiny public compiled-form test在 complement Gate FAIL，详见 [controlled-negative outcome](outcomes/p4_core_partial_condensation_controlled_negative.md)。 |
| 10 | Candidate E modal basis/rank/condition/memory/residual | `not_run_by_latest_user_sequence`；最新顺序要求先完成 V3 收口，再转读 Candidate F addendum。 |
| 11 | 全部测试、未运行项、changed files | 见下方测试边界和 changed-files 索引；test245 hard failure原样保留，未运行项按 Gate/最新用户顺序区分。 |
| 12 | final classification | `CONTROLLED_NEGATIVE_NUMERICAL_AT_R7B2B1_COMPLEMENT_GATE`；不得称 production-qualified。 |

## 3. 阶段证据

| 阶段 | source SHA | 结果 | 关键证据 |
|---|---|---|---|
| R7a local hierarchy | `ed871cbae51396e30ad5a3fd6bf32dc7601a4020` | PASS | orientation/rank/nesting/partial Schur/recovery；误差约 `1e-14–1e-15` |
| R7b1 global retained system | `b93b72bac9095273c838ff653ca3bbf93567123c` | PASS | global action/RHS/left/bilinear/recovery 最大约 `2.58e-15` |
| R7b2a compiled-form assembly-time | `0c882e7a6da38b6a66625e002fe64fabe0a70674` | PASS | serial/MPI2 test244、serial test243；ledger完整 |
| R7b2b1 public DtN carrier | `6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a` | CONTROLLED NEGATIVE | test245 complement Gate FAIL |

R7b2a 的直接证据为：serial test244 `1 passed`, `132.33 s`, MaxRSS `548212 kB`，action `3.913e-16`；MPI2 test244 passed，`129.36 s`，MaxRSS `536320 kB`，action `4.371e-16`；serial test243 `1 passed`, `34.50 s`。2-cell ledger 为 partial Schur `9331200`、eliminated factor `3745584`、basis `15070464`、maps `37304`、numbering `864` bytes。

通用 diffraction CSV 修复独立提交为 `6bc7d1e397834e4c316eaa3c59d4d90640835424`，只把异构 row 的字段改成按首次出现顺序的稳定并集，没有改变物理或 solver。

## 4. R7b2b1 最终负证据

test245 使用 tiny 两-cell 真实 compiled p6 public flow，包含 Floquet constraints、真实 surface forms、DtnBlockAssembler、matrix-free C/D、retained action 和 public recovery path。最终命令（在已执行 `source scripts/activate_myfenics_wsl.sh` 的同一 qualified shell 中）：

```text
/usr/bin/time -v python -m pytest -q -s src/test/test_245_task037_retained_dtn_adapter.py
```

结果为 `1 failed, 1 passed`、exit `1`、wall `88.15 s`、MaxRSS `661088 kB`、swap `0`。可见 solver 数据：

| 量 | 值 |
|---|---:|
| augmented rows | `760` |
| KSP reason | `2` (`CONVERGED_RTOL`) |
| RHS norm | `11.707507837771832` |
| solution norm | `275.1048734370968` |
| full relative true residual | `4.271433780052363e-11` |
| independent reduced norm | `2.169086505997297e-12` |
| eliminated complement norm | `5.000737489099658e-10` |

权威 hard Gate 是：

```text
complement_norm / max(independent_reduced_norm, 1.0) <= 1e-11
```

实际值 `5.000737489099658e-10`，约为限值的 `50.00737489099658` 倍，失败位置为 [test245:435](../../../src/test/test_245_task037_retained_dtn_adapter.py:435)。test245 没有 xfail、skip 或阈值放宽。

由于 pytest 按顺序执行，失败前未报错的 effective-RHS、无显式 C/D、p6 zero-inventory、reduced/full consistency 断言不能被提升为完整 PASS；失败之后的 independent recovery 与 MPC assertions 是 `not_run_by_assert_order`。没有 official R/T/A，也没有正式 p6/h10 memory evidence；`661088 kB` 只属于 tiny two-cell test process，不能外推目标模型。

## 5. 已修正的实现 blocker

| blocker | 分类 | 处理 |
|---|---|---|
| public backend 与部分 legacy booleans 冲突 | fixture/public contract | 删除 test245 两行 legacy flags |
| pending augmented PETSc Vec | lifecycle | retained `b_aug` 在 combine 前 assemble |
| row closure 未计 retained core | bookkeeping contract | `_dof_row_semantics` 加 independent trace + retained core + auxiliary 闭合 |
| heterogeneous diffraction CSV keys | generic postprocess schema | `6bc7d1e3` 字段稳定并集 |
| 342D eliminated complement residual | numerical Gate | 未通过，作为最终 controlled negative 保留 |

早期 blocker 是实现修正，不应改写为数值通过；最后一个 complement failure 才是当前正式 stopping Gate。

## 6. 测试边界与未运行项

当前 source 的五文件 compileall、Ruff check、`git diff --check` 通过；test245 hard failure 原样保留。没有运行 full repository pytest，这是用户效率政策下的明确边界，不写成 full-suite PASS。

以下项目均因 R7b2b1 hard Gate 失败而 `not_run_by_gate`：

- R7b2b2 p2/PC integration；
- setup-only formal memory ledger；
- MPI2 test245；
- MPI8 20/100/200；
- full solve、official R/T/A；

Candidate E 为 `not_run_by_latest_user_sequence`；Candidate F addendum 为
`not_read_pending_v3_closeout`，最新顺序要求 V3 推送完成后才读取。二者不是
complement Gate 自动否决的项目。

## 7. changed files、provenance 与历史边界

§11 第11项的 changed-files 索引如下；每行是已核实的 commit→files 关系：

| commit | scope / files |
|---|---|
| `592f6307716c428e8eb87e164435233dafabd47d` | matrix-free DtN：`src/solvers/condensed_dtn.py`、`src/solvers/dtn_port_3d.py`、`src/test/test_230_task037_dtn_direct_blocks.py` |
| `6f152a6e50f8e8fc475fc6b3e2bc39aca1bdf1d2` | Candidate D：`src/solvers/static_factor_free_slab_pc.py`、`src/solvers/static_p2_slab_pc.py`、`src/test/test_237_task037_factor_free_slab_pc.py`、`src/test/test_241_task037_candidate_d_local_p2.py` |
| `ed871cbae51396e30ad5a3fd6bf32dc7601a4020` | R7a：`src/solvers/hcurl_p4_core_partial_condensation.py`、`src/test/test_242_task037_p4_core_partial_condensation.py` |
| `64b983f13b4191b4227a2b7d5d6fee6e84be2944` | Candidate D 基础实现：`src/solvers/static_p2_slab_pc.py`、`src/test/test_240_task037_p2_local_slab_pc.py` |
| `b93b72bac9095273c838ff653ca3bbf93567123c` | R7b1：`src/solvers/hcurl_p4_core_global_partial_condensation.py`、`src/solvers/hcurl_p4_core_partial_condensation.py`、`src/test/test_243_task037_p4_core_partial_condensation_integration.py` |
| `0c882e7a6da38b6a66625e002fe64fabe0a70674` | R7b2a：`src/solvers/hcurl_assembly_time_condensation.py`、global partial module、`src/test/test_244_task037_p4_core_assembly_time_integration.py` |
| `6bc7d1e397834e4c316eaa3c59d4d90640835424` | CSV修复：`src/postprocessing/diffraction_3d.py` |
| `6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a` | R7b2b1：`src/solvers/common_3d_case_flow.py`、`src/solvers/dtn_port_3d.py`、global partial module、`src/test/test_245_task037_retained_dtn_adapter.py` |

## 8. provenance 与历史边界

数值 carrier 为 `6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a`，branch 为 `codex/20260803-task37-matrix-free-iterative-development`，carrier 时 upstream 为 `d875ba538f8334c5fd9e026192cacbdcd11e0794`，ahead/behind=`5/0`，carrier worktree clean。相关 commit 为：

`ed871cbae51396e30ad5a3fd6bf32dc7601a4020`、`b93b72bac9095273c838ff653ca3bbf93567123c`、`0c882e7a6da38b6a66625e002fe64fabe0a70674`、`6bc7d1e397834e4c316eaa3c59d4d90640835424`、`6552385b1b4c4008a84bb5ffcfa90ffe196f7e8a`。

V2 和 Candidate D 的历史结果保留在既有 `response_v2.md`、outcomes 与 records 中；本回应不重写历史，也不读取 Candidate F addendum。当前 V3 文档只记录本次 p4-core carrier 的 measured、derived、not_run 和 controlled-negative 边界。

## 9. 结论与后续限制

R7 证明了 p4-core 组件和 assembly-time retained action 的代数可行性，但没有证明 public DtN integration 已达到 full residual Gate，也没有得到可替代 direct 的 production-qualified 迭代解。停止同一 p4-core/DtN 微调；本 V3 提交推送后按最新用户顺序读取 Candidate F addendum，先只执行 F0，后续严格受其 Gate 约束。此处不提前读取或解释 addendum。

## 10. Candidate F F0 implementation Gate 补充

### 10.1 身份与既有停止边界

Candidate F F0 的目标是一个局部容量 oracle：沿用 Candidate D 的 fully-condensed factor-free p6 action，用真实 exact-sequence degree-pair transfer 构造 p4 中间空间。它只允许临时 dense complex128 p4 LU，用于测量容量，不是 production solver。

此前 partial condensation 已收口为
`CONTROLLED_NEGATIVE_NUMERICAL_AT_R7B2B1_COMPLEMENT_GATE`；local p2 Candidate D 也仍是冻结负结果：

| source | rho_B4 | rho_D0 | improvement |
|---|---:|---:|---:|
| low | 0.24599945418880295 | 0.2540230551088513 | 0.9684138870126958 |
| high | 0.24651896436171644 | 0.26531876351572775 | 0.929142594723057 |
| mixed | 0.24612971921817314 | 0.2715867504171219 | 0.9062655628087525 |

测试绑定 tracked HEAD `2cea3b986303d1553e062f206da452e8f609642b`，branch 为
`codex/20260803-task37-matrix-free-iterative-development`。测试时 worktree 是 dirty；四个实现文件的 SHA256 见
[`task37_candidate_f_f0_v1.json`](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_candidate_f_f0_v1.json)。ABI 为 qualified 项目 `.venv`、PETSc `complex128/int32`、同一 Linux 栈。

### 10.2 Static 与唯一 serial 命令

最终 Ruff check、Ruff format-check、compileall、`git diff --check` 均通过。最初 format mismatch 只是机械格式修正，不是数值 Gate。

唯一 pytest 命令在同一 qualified shell 中执行：

```text
/usr/bin/time -v python -m pytest -q -s -x \
  src/test/test_246_task037_p4_capacity_oracle.py::test_f0_degree_pairs_preserve_floquet_orientation_identity \
  src/test/test_246_task037_p4_capacity_oracle.py::test_f0_p4_capacity_oracle_and_d0_comparison
```

结果是 `1 passed, 1 failed`、exit `1`、wall `18.65 s`、MaxRSS `287000 kB`、swap `0`；原始输出保存在 `/tmp/task37_f0_p4_capacity_oracle.log`，time 输出在 `/tmp/task37_f0_p4_capacity_oracle.time`。

### 10.3 Transfer Gate measured PASS

第一项专门测试实际经过 P24 与 P46 degree pairs，并通过真实 nontrivial orientation/Floquet 插值核对：

| 指标 | measured |
|---|---:|
| P24→P46 composition error | `3.512063090206927e-15` |
| P24 interpolation error | `8.326653945790752e-16` |
| P46 interpolation error | `6.595217588690049e-15` |
| P24 adjoint error | `1.1106734086056049e-15` |
| P46 adjoint error | `2.6080775955612308e-15` |
| nonzero orientation counts | P24/P46 = `21/21` |
| Floquet phase x | `0.8541859931542107-0.5199675846619236j` |
| Floquet phase y | `0.818001826003227+0.5752156227497531j` |

### 10.4 Capacity implementation Gate FAIL

第二项在 p4 oracle 构造前失败：`diagonal.getValues(p6_rows)` 收到 numpy int64 索引，而当前 PETSc ABI 要求 int32。完整异常原文为：

```text
TypeError: Cannot cast array data from dtype('int64') to dtype('int32') according to the rule 'safe'
```

失败位置是 `src/test/test_246_task037_p4_capacity_oracle.py:113`。因此本轮分类精确为：

```text
F0_IMPLEMENTATION_GATE_FAILED_PETSC_INDEX_DTYPE
```

这不是 `P4_INTERMEDIATE_SPACE_NOT_EFFECTIVE`，因为 high/mixed improvement Gate 尚未执行。projected-action、B4 闭合、F rho、D0 新比较、p4 rows/matrix NNZ/factor NNZ/LU payload/bytes 均为 `not_run_by_implementation_gate`。冻结 D0 数值只是对照，没有重跑。

潜在最小修复仅是将 PETSc `getValues` 索引对齐到 `PETSc.IntType`；本轮严格未实施，也没有重跑。

### 10.5 后续与资格边界

F1、MPI8 screen20/100/200、PDE 均为 `not_run_by_f0_gate`；没有调参、阈值变更或重跑。MaxRSS 只属于该 serial test 进程，不是 p4 容量或正式 PDE 内存证据。

四个实现/测试文件是 unqualified research draft，ordinary defaults 未改变；不得 selective merge，也不得称为 production-qualified。F0 失败后本轮停止在 implementation Gate，等待新的明确修复授权。

## B2 MPI1 长尾补充（受控停止）

本补充绑定正式运行 source `7aa77ed3f38dc036df77166d74b9d9d18ff0dbf6`、分支
`codex/20260803-task37-matrix-free-iterative-development` 与同一 qualified
Linux/PETSc `complex128/int32` 环境。冻结路径为 13.5 nm、p6/h10、S、theta
normal `80°`（10° grazing）、phi `0°`、252 cells、MPI1、16 slabs、overlap
`0.125`、partition weighting、local Krylov fixed `2`、p2 exact-sequence
auxiliary + one distributed MUMPS factor、75D wave coarse、right FGMRES restart
`90`、canonical export；p6 retained matrix/factor/NNZ=`0/0/0`，global A/F=
`false/false`。

唯一正式 parent 命令在已 activation 的同一 shell 中执行一次，原始 artifact 保存在
`/home/Projects/MyFEniCS/benchmarks/artifacts/task037/b2_factor_free_mpi1_long_full_p6_h10_7aa77ed3`；完整命令、全量残差历史、文件 SHA256/size 见 [B2 长尾 outcome](outcomes/b2_factor_free_mpi1_long_tail_controlled_stop.md) 与 [compact record](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_b2_factor_free_mpi1_long_tail_v1.json)。

`condensed_true_residual` 从 `i=0` 的 `1.0` 下降到 `i=2500` 的
`0.15630768102286852`；`i=2400` 为 `0.15660187375232723`，绝对下降
`0.00029419272945871433`，相对改善 `0.0018786028698736588` =
`0.18786028698736587%`，满足用户 `<=0.5%` 停止门槛。原 persistent session
`3735` 由 Ctrl-C 安全停止，return `1`，session 关闭且无 orphan；分类为
`controlled_stop_by_user_i2500_improvement_gate`。这不是 positive convergence，
也不是数值崩溃；没有运行到 `i=2600`。

最后可见 progress 是 setup 阶段
`stage4_dtn_augmented_matrix_finalized`，setup wall `318.10704500298016 s`，rank
historical RSS upper bound `661.76171875 MiB`（`0.6462516784667969 GiB`），rank
current RSS `662.01171875 MiB`，swap `0`。该 RSS 是 setup 阶段历史上界，不是最终
solve/整棵进程树峰值；PSS、USS、final process-tree RSS、normal watchdog summary、
positive KSP reason、official R/T/A、canonical vector 和 full-FE recovery 均
`not_generated`，`official_result=false`。derived time-to-i2500 为
`22974.670897739 s`，不冒充 whole-run final wall。

因此，factor-free 存储机制仍有 setup 证据，但当前 B2 预条件器长尾明显，在该用户
停止门槛下无法产出可用解；不得称为 production-qualified，也不据此断言数学上永不
收敛。
