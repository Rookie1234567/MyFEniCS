# Task037 V6：Candidate E 实现失败结项

## 1. 结论先行

本文件是 V6 的证据结项，不表示 Task037 数值任务完成。E0 已在修复后的源码上通过；E1 原始正式运行发现首列 top interface mismatch，随后一次局部 owned+ghost 修复的 formal 又在首列之前被冻结的近简并模态分组 Gate 阻止。因此，E1 没有得到新的 top mismatch 数值，不能声称 0.3581035899568693 已降到 1e-10 以下。

| 阶段 | 状态 | 精确结论 |
|---|---|---|
| E0 | completed_pass | MATRIX_FREE_DTN 80-mode component/action Gate 通过 |
| E1 原始 formal | controlled failure | M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED，首列 top mismatch 0.3158 |
| E1 ba0e 诊断 | controlled diagnostic | bottom 6.037930876831123e-15，top 0.3581035899568693 |
| E1 7263 修复 formal | controlled failure | 首列前 NearDegenerateBlockPartitionSplitError |
| E2 capacity | not_run | 没有 B4 late residual capacity 结论 |
| E3–E5 | not_run | V6 implementation Gate 失败后的硬停止 |
| E6 | completed_closeout | 本 record 与本 response 形成 evidence-only checkpoint |

Candidate E 的结论是 M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED，不是 M120_MODAL_COARSE_INSUFFICIENT_ON_FROZEN_LATE_RESIDUALS。因此没有证明 M120 coarse 没有容量，也没有开始 E2。

Selective merge 仍为 do_not_merge / not_qualified。7263 的代码修复是 research-only；轻量测试通过不能把它提升为 production path。

## 2. 冻结范围、身份与 ABI

所有正式运行都使用当前 V6 anchor：p6/h10、13.5 nm、S polarization、phi=0、80° 入射、assembly_time_static_condensed、Full3D action-only 方向和既定 M120 合同。未改变 near-degenerate threshold、mode ordering、M120 选择、传播公式、1e-10 interface Gate 或 ordinary defaults。

| 项目 | 数值 |
|---|---|
| branch | codex/20260803-task37-matrix-free-iterative-development |
| remote Task37 ref | 4a0f33297fc4d0c909b15613eb6e12d2513e798e |
| repair source SHA | 7263da792dccc174055df983298d543a48be417f |
| repair parent | ba0e260498e98ebd982465ebff697e4c89615db9 |
| temporary clone | /tmp/task037-e1-diagnostic-tlvcVB |
| activation | _MYFENICS_WSL_QUALIFIED_ACTIVATION=1 |
| Python | /home/Projects/MyFEniCS/.venv/bin/python |
| PETSc | complex128 / int32 |
| ordinary defaults | unchanged |

主仓库没有被本轮写入，仍是 4a0f3329...、ahead/behind 0/0，保留主对话原有的两个 modified Python 文件。7263 修复 commit 只存在于临时 clone，未 push。

## 3. E0：初始 Error 56 与修复后 PASS

初始 E0 的 PETSc Error 56 仍作为历史记录保留在现有 record 中：MatPython 不支持 Mat.getInfo()，因此旧运行在 probe audit 之前失败。它不代表修复后的 E0 结果。

修复后同一 MPI1 frozen formal 通过，直接测得：

| Gate | 实测值 |
|---|---:|
| selected modes / top-bottom | 80 / 40-40 |
| active rows / FE DoFs | 51192 / 173802 |
| forward action maximum | 1.2367630350859273e-15 |
| auxiliary recovery maximum | 1.1141146096537195e-15 |
| physical RHS identity | 0.0 |
| source labels | seed_17037、seed_27037、seed_37037、physical_active_rhs |
| primary matrix-free / explicit C,D | true / 0,0 |
| explicit oracle / C,D | false / 1,1 |
| profiles separate | true |
| global A/F | false / false |
| factorization / KSP / official result | false / 0 / false |
| case status | diagnostic_assemble_only |
| elapsed / process-tree RSS / swap | 298.23167246207595 s / 675.4453125 MB / 0 |

E0 的 MatPython telemetry 是 metadata-only：类型为 python，矩阵尺寸 51272 x 51272；NNZ、memory、norm、PETSc-info 等不适用字段均为 not_applicable，不是伪造的零值。

## 4. E1 原始 formal：top mismatch

原始 E1 使用 source SHA 4a0f33297fc4d0c909b15613eb6e12d2513e798e、MPI8，并在 forward j=0 的第一列停下：

~~~text
ValueError: top interface mismatch exceeds tolerance: 3.158e-01
~~~

原始 audit 的 column_count=null；global A/F 为 false，p6 retained factor/NNZ 为 0/0，KSP 为 0，official result 为 false。该运行没有产生完整 240 列、Y、rank 或 capacity evidence。资源是 timeline 最后 elapsed 411.69451796798967 s、process-tree RSS 11573.484375 MB、swap 0；warning 曾触发，但不是 memory 或 timeout termination。

## 5. ba0e 首列诊断证据

ba0e commit ba0e260498e98ebd982465ebff697e4c89615db9 只增加了 forward j=0 的 pre-stitch 诊断，没有改变 stitch Gate。

| 对比 | expected/common/missing | local norm | middle norm | absolute L2 | relative L2 |
|---|---:|---:|---:|---:|---:|
| bottom | 1350/1350/0 | 1.443671302489733 | 1.4436713024897332 | 8.716787533297764e-15 | 6.037930876831123e-15 |
| top | 1350/1350/0 | 1.2200752308042857 | 1.1391621129064402 | 0.4369133201684706 | 0.3581035899568693 |

排除链：

- top best global scalar 是 [1.0000000000000102, 4.1570100046689895e-17]，去掉全局复数比例后 residual 仍为 0.3581035899568693，不是 global scalar。
- stable factor 与 pointwise expected factor 完全相同：[-0.11634979868607903, 0.8370724185654409]，relative difference 0。
- factor magnitude 0.8451198196571228，log magnitude -0.1682768632666114，roundoff_growth_clipped=false。
- top edge relative error 0.41578485549225014，face relative error 0.340070411606694；不是 edge-only 或 face-only。
- top scale 1.2200752308042857，norms_near_underflow=false，numerically_identifiable=true；不是极小向量舍入误差。
- 1350 个接口 key 全部 common、missing 为 0；这不是 key coverage 缺失。

因此该诊断的最窄分类是 non-scalar cross-mesh trace-shape mismatch：传播因子、全局比例、下溢和单一 edge/face orientation 假设均未解释它。它仍不等于已经定位了唯一 production 修复。

## 6. 7263 owned+ghost 局部修复与 formal

修复只修改 static_modal_coarse_basis.py：middle interpolation cell selection 从 owned cells 扩展到 owned+ghost cells；owned_middle_cell_count 和 global reduction 仍只统计 owned cells；原有 scatter_forward 与 MPC 顺序保持不变。没有加入 reverse INSERT、fallback、owner protocol、阈值或新框架。

轻量 Gate：

| 检查 | 结果 |
|---|---|
| 指定 serial middle-column test | 1 passed |
| mpiexec -n 2 指定 test | 两 rank 各 1 passed |
| test250 + test251 | 12 passed |
| Ruff check / format check | pass |
| compileall | pass |
| git diff --check | pass |

上述 MPI2 wrapper 使用现有 test250 fixture；该 fixture 的 target mesh 仍为 COMM_SELF，所以这不是独立的跨 rank ownership proof，只是获准的轻量 regression。

唯一 repair formal 使用同一冻结参数、MPI8、verified-clean-sha 7263da792dccc174055df983298d543a48be417f，但在 _build_e1_column 之前的 negative modal basis 构造阶段失败：

~~~text
NearDegenerateBlockPartitionSplitError:
near_degenerate_block_partition_split:
identity_row_norm=2.154747e-06,
identity_max_entry=1.773428e-06,
cross_block_max=1.773428e-06,
limit=1.000000e-06,
indices=[50, 53],
group_ids=[17, 18],
relative_beta_distance=1.580086e-06
~~~

因此 repair formal 没有新的 top/bottom interface comparison，column_count=null，不能声称该 patch 已修好 0.3581035899568693，也不能把这次停止误写成新的 capacity negative。该运行的 raw audit 仍为 M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED；process-tree RSS 6624.3515625 MB、timeline 最后 elapsed 154.10333659802563 s、swap 0，warning、memory termination、timeout termination 均为 false。

## 7. 为什么在这里停止

这不是 Git blocker、不是内存停止，也不是因为已经证明 M120 没有 coarse capacity。真正的停止原因是 frozen implementation Gate 在首列前被近简并 block partition split 阻止。raw audit 给出的后续方向是：

~~~text
DEFERRED_ARCHITECTURE_REQUIRED_joint_subspace_rotation
~~~

Review V6 冻结 near-degenerate grouping、1e-6 threshold、mode ordering，并禁止自动重跑或放宽 Gate。joint-subspace rotation 会超出本轮局部证据驱动修复的授权，因此不实现、不测试、不再次 formal。

## 8. 证据索引与阶段边界

完整 source SHA、命令、ABI、每个 raw 文件的 bytes/SHA256 均在：

[task37_v6_e1_implementation_closeout_v1.json](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_v6_e1_implementation_closeout_v1.json)

| 运行 | raw artifact 目录 | 关键 audit | watchdog SHA256 |
|---|---|---|---|
| E0 repaired PASS | /home/Projects/MyFEniCS/benchmarks/artifacts/task037/e0_v6_matrix_free_dtn_bde08508/mpi1 | run_summary.json 56328 bytes，58fc64368f1196ffd0a0d86aed472d6aab9601ee2b50d412786f969d7654e821 | fa2753f94c310dd12be03ae4a8e8f2aa40d8d75d22fb3c3f85db86bc59d73ea1 |
| E1 original | /home/Projects/MyFEniCS/benchmarks/artifacts/task037/e1_v6_modal_basis_4a0f3329/mpi8 | task037_e1_modal_basis_audit.json 782 bytes，ea7cb254086955a75464bd190719abc2333d8400791742e71a693ea4243a4eef | 093c39a8966b996d9ace3501ea732cd95319819dce59ae8b051e1081dd40789c |
| ba0e diagnostic | /home/Projects/MyFEniCS/benchmarks/artifacts/task037/e1_v6_first_column_diagnostic_ba0e2604/mpi8 | task037_e1_first_column_diagnostic.json 34515 bytes，8c12921c469592b2337e3951c97278aded02afafd3706158bf4c59ab56f20575 | ba1180078fb70c1b01c6bf82adfb2845f1d8f510093817e9ee27625e95016053 |
| 7263 repair | /home/Projects/MyFEniCS/benchmarks/artifacts/task037/e1_v6_first_column_fix_7263da79/mpi8 | task037_e1_modal_basis_audit.json 986 bytes，a74c487f77eb18dc7ef938b3bd9625326037b1956403e1771d3418b4e082a251 | 97179c66077cce0158b8255d9a76b4a26c39a19a5ca2a89a6807b6ab571a7672 |

现有 task037_v6_e0_matrix_free_dtn_formal_failure.json 未修改，保留初始 Error 56 历史。E0 修复后 raw 目录的当前 hashes 以本 closeout record 为准；不把历史失败 record 的旧 hash 误当作 repaired PASS evidence。

## 9. 最终边界

本轮没有运行 E2 B4 residual carrier、ideal capacity oracle、E3 coarse PC、E4 funnel 或 E5 full solve。没有 MPI2/4 formal、没有 full pytest、没有 0.7 nm PDE。Candidate E 按 frozen implementation failure 停止；不得继续在 Task037 内发明 Candidate G/H。

本 checkpoint 只包含 response 与 compact evidence record，repair commit 未 push。publication carrier SHA 不写入自身，避免自引用；本轮等待主审快速 review 后再决定是否发布。
