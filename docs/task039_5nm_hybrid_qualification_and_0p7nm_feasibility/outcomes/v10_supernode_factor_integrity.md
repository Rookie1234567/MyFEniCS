# V10-2：六层 supernode factor integrity 诊断

这一步回答一个很具体的问题：把相邻两层合成一个小组后，普通稀疏解法与“只保留因子、释放原矩阵”的路径，是否仍能对同一组右端稳定地完成 factor-only solve。它不是完整 Maxwell 求解，也没有把这个诊断结果当成新的默认求解器。

## 身份与范围

| 字段 | 实测/继承值 |
|---|---|
| schema / method | `task039.v10.h4.supernode.factor_integrity.v1` / `task039_v10_h4_supernode_factor_integrity` |
| source SHA | `606ec0d56b79748a5d6dc794a7b8d7260675aad3` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| model / MPI | `task039_5nm_v4_1deg_s5_hybrid_iterative_m480` / MPI8 / threads=1 |
| run root | `results/task039_v10_h4_supernode_factor_integrity_mpi8_606ec0d5`（ignored local raw） |
| exact spool | `results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output` |
| exit | parent/worker exit 0，`component_forensic_completed` |
| repeat / linearity | `not_run`；本阶段没有运行这两项，不能写成 pass |

本阶段严格只测试 bottom 的三组 `[0,1]`、`[2,3]`、`[4,5]`。每组先跑 conventional KSP，再销毁它；随后跑 detached factor-only，再销毁它；没有同时保留两条路径的 factor。空本地 rank 的 collective 也正常完成。

## 结果表

下面的 residual 是每组所有三个非零 RHS（deterministic random、modal traction positive、external DtN coupling）中的最大值；zero RHS 单独作为零映射边界记录，不混入非零 residual。

| supernode | layers | conventional 最大 residual | factor-only 最大 residual | finite | factor cleanup |
|---|---:|---:|---:|---|---:|
| B0 | [0,1] | `3.1708712957e-12` | `3.2209079435e-12` | true | 0 |
| B1 | [2,3] | `4.1630016438e-12` | `3.8754460126e-12` | true | 0 |
| B2 | [4,5] | `3.9332808829e-11` | `4.9924148301e-11` | true | 0 |

三组两条路径均为 `path_pass=true`，首次非有限阶段为 `null`。每组 zero RHS 输出范数为 `0.0`；它是 degenerate zero map，不构成非零 RHS 的 residual 证据。

| supernode | global shape | global NNZ | diagonal NNZ | factor-only matrix rows / NNZ | 空本地 rank |
|---|---:|---:|---:|---:|---|
| B0 | 49140×49140 | 35501760 | 49140 | 49140 / 158809032 | observed，collective completed |
| B1 | 41580×41580 | 28826280 | 41580 | 41580 / 140804928 | none，false |
| B2 | 41580×41580 | 28826280 | 41580 | 41580 / 153689256 | observed，collective completed |

## SN2-J 边界与生命周期

独立 boundary 记录显示：parent→group→parent round-trip 相对误差为 `0.0`；SN2-J 的 zero RHS 输出范数 `0.0`，one-group RHS 与 three-group RHS 均 finite，输出范数分别为 `8859.92364491418` 与 `20955.821641970975`。`first_nonfinite_stage=null`，`sgs_executed=false`。本阶段没有 repeat/linearity 试验。

三组 factor 的实际控制流是 `B0 A→destroy → B0 B→destroy → B1 A→destroy → B1 B→destroy → B2 A→destroy → B2 B→destroy`。空本地 rank 只在 B0 与 B2 观察到；B1 的 ownership ranges 全部非空。最终 marker 为 `v10_layer_supernode_bottom_cleanup`，记录 H/C/F/D、system 和 collective cleanup 完成，最终 factor count 为 0。父级没有 retained candidate，因此 retained 是 `not_applicable/not_run`，不是 retained resource pass。

顶层 raw 的 `factor_count_ready=0` 与三组 path-ready 记录并存；前者是 raw 顶层清理后快照，三组实际 factor 构造由每组 path 的 ready/cleanup 记录证明，最终 cleanup=0。该字段没有被本阶段改写或补猜。

## 资源 Gate

| authority | peak | limit | 结论 |
|---|---:|---:|---|
| parent process-tree construction/overall | `44127375360 B = 41.0968208313 GiB` | 45 GiB | pass |
| swap | `0 B` | 0 | pass |
| retained candidate | `not_applicable/not_run` | 30 GiB | 不适用，不判 pass |
| PSS / USS | `not_measured` | — | not measured |

V10 的 45 GiB 是本路线 authority；run summary 里保留的通用 224 GB budget 不是本次 V10 resource Gate。原始 samples、markers、ledger 与 worker JSON 均保留在 ignored root，compact record 为 [task039_v10_supernode_factor_integrity_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v10_supernode_factor_integrity_v1.json)。

## 边界

这次结果证明的是三组局部 factor integrity 和 SN2-J boundary 可测、可清理、资源低于 45 GiB；它不是 full-side solve，也没有运行 SGS、retained apply、outer/recovery、QEP、selected packet 或 global direct factor。后续是否允许 V10-3，必须另按 Review 的 SN2-J-only Gate 评估，不能把本记录解释为完整物理结果。
