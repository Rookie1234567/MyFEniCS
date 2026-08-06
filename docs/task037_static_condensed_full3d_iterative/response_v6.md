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

Selective merge 分组如下：bde08508 E0 telemetry/component 是 component-qualified、待最终集成审阅的 selective-review candidate；ba0e/7263 诊断与 Candidate E 是 do_not_merge / research-only / unqualified。轻量测试通过不能把后者提升为 production path。

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

本 record 的 publication 字段是 record-creation snapshot：当前 checkpoint 未 push；最终 carrier SHA 与 push 后 clean 状态按发布边界 out-of-band 报告，不写入自身以避免自引用。本轮等待主审快速 review。

## 附录：E0 首次 Error56 历史证据

以下内容原样保留初始 E0 formal 的失败链。它是历史实现失败；修复后的 bde08508 E0 PASS 不能删除或改写这段历史。

~~~text
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/home/Projects/MyFEniCS/benchmarks/run_task033_full3d_watchdog.py", line 5024, in <module>
    raise SystemExit(main())
                     ^^^^^^
  File "/home/Projects/MyFEniCS/benchmarks/run_task033_full3d_watchdog.py", line 5019, in main
    return _worker(args)
           ^^^^^^^^^^^^^
  File "/home/Projects/MyFEniCS/benchmarks/run_task033_full3d_watchdog.py", line 1513, in _worker
    run_stage4b_block_grating_3d_case(
  File "/home/Projects/MyFEniCS/src/solvers/solve_maxwell_3d_stage_4b_block_grating.py", line 44, in run_stage4b_block_grating_3d_case
    return run_prepared_3d_case_flow(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/Projects/MyFEniCS/src/solvers/common_3d_case_flow.py", line 1483, in run_prepared_3d_case_flow
    else _petsc_matrix_stats(system_A)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/Projects/MyFEniCS/src/solvers/common_3d_solve.py", line 391, in _petsc_matrix_stats
    info = A.getInfo()
           ^^^^^^^^^^^
  File "petsc4py/PETSc/Mat.pyx", line 805, in petsc4py.PETSc.Mat.getInfo
petsc4py.PETSc.Error: error code 56
[0] MatGetInfo() at ./src/mat/interface/matrix.c:3006
[0] No support for this operation for this object type
[0] No method getinfo for Mat of type python
--------------------------------------------------------------------------
Primary job  terminated normally, but 1 process returned
a non-zero exit code. Per user-direction, the job has been aborted.
--------------------------------------------------------------------------
--------------------------------------------------------------------------
mpiexec detected that one or more processes exited with non-zero status, thus causing
the job to be terminated. The first process to do so was:

  Process name: [[3818,1],0]
  Exit code:    1
--------------------------------------------------------------------------
~~~

旧 E0 formal 的逐 Gate 边界如下；在 probe audit 生成前退出的项目必须保持 NOT_OBSERVED，不能由修复后 PASS 倒填：

| Gate | 状态 | 数据分类 | 边界 |
|---|---|---|---|
| qualified ABI/authority/source | PASS | measured | activation、ABI、SHA、clean source 已通过 |
| 80-mode preparation | PASS | measured | 80；top/bottom 40/40；active rows 51192；FE DoFs 173802 |
| 完整 mode key/beta/polarization/power/Rayleigh identity | NOT_OBSERVED | not_observed | probe audit 未生成 |
| 3 deterministic seeds + physical active RHS | NOT_OBSERVED | not_observed | 4 source labels 未生成 |
| forward action <=1e-11 | NOT_OBSERVED | not_observed | 最大误差未生成 |
| auxiliary recovery <=1e-11 | NOT_OBSERVED | not_observed | 最大误差未生成 |
| physical RHS identity <=1e-12 | NOT_OBSERVED | not_observed | 误差未生成 |
| primary matrix-free / explicit C,D = 0/0 | NOT_OBSERVED | not_observed | audit materialization 未生成 |
| oracle explicit C,D = 1/1 | NOT_OBSERVED | not_observed | audit materialization 未生成 |
| primary/oracle profile 分离 | NOT_OBSERVED | not_observed | audit 未生成 |
| component-only/probe/ordinary-default summary | NOT_OBSERVED | not_observed | run summary 未生成 |
| factorization/KSP-specific solve event absence | NOT_OBSERVED | not_observed | 仅原始日志未见 KSP-specific event，completed Gate 未产生 |
| KSP iterations = 0 | NOT_OBSERVED | not_observed | completed solver summary 未生成 |
| official result/postprocess | NOT_OBSERVED | not_observed | completed solver summary 未生成 |
| no swap、非内存/非 timeout 停止 | PASS | measured | no_swap=true，termination flags 均 false |
| E0 overall | FAIL | derived | MATRIX_FREE_DTN_FORMAL_80MODE_GATE_FAILED |

## 后续修复与正式 E2 容量裁决补充

本文件前文是早期 E1 implementation checkpoint，包含当时的 Error 56、首列 mismatch 和受控停止历史，原文保留不变。随后 95b4c3b5 与 ddcc5ea8 等最小修复已经越过那些 implementation blockers；当前状态以本补充和对应 raw artifact 为权威，不把早期失败倒填成最终结果。

| 阶段 | 当前裁决 | 证据边界 |
|---|---|---|
| E0 | PASS | repaired MPI1 component action Gate |
| E1 | PASS | 同一 MPI8 request 内 240 列 M120 basis |
| E2 | capacity negative | implementation checks 全通过，late capacity Gate 6/6 失败 |
| E3–E5 | not_run | V6 硬停止 |
| E6 | closeout_drafted | 本补充与 compact record |

compact record：[task37_v6_e2_modal_capacity_closeout_v1.json](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_v6_e2_modal_capacity_closeout_v1.json)。

### E1 与 E2 的含义

“ideal capacity oracle” 是给一个候选 coarse basis 最有利的复数系数，直接计算它能把真实残差压到什么程度；它是容量上界，不是生产 solver。若连这个最有利的线性组合也只能改善约 0.3–0.4%，同一个 M120 coarse space 作为实际 PC 就不可能达到 V6 的 late-residual 门槛。

| E1 项 | 实测值 |
|---|---:|
| 完整列 / forward / backward | 240 / 120 / 120 |
| missing / extra / duplicate | 0 / 0 / 0 |
| 最大 repeat error | 1.0114502263711128e-13 |
| action rank / condition | 240 / 740.511230115312 |
| random action relative error | 6.53573490135987e-15 |
| 最大 bottom/top retained residual | 6.799167355834361e-13 / 9.287696356432755e-13 |
| 最大 stitch interface mismatch | 4.479212868666832e-11 |
| global A/F、official result、KSP | false / false / 0 |

E1 使用完整 condensed action F-C H^-1 D，不是只用 fine F；p6 retained factor count/NNZ 为 0/0，local factor 已释放。

| action space | columns | rank | condition | factorization | equations |
|---|---:|---:|---:|---:|---|
| 75D | 75 | 75 | 1520.2120206198704 | 1 | owner-local QR + root SVD |
| M120 | 240 | 240 | 740.5112301153121 | 1 | owner-local QR + root SVD |
| 75D+M120 | 315 | 315 | 9985.323201186875 | 1 | owner-local QR + root SVD |

所有 action space 的 normal_equations=false，同一次 request 内使用 owner-local basis；没有复制 global basis。

### 同次 B4 true residual 与容量 Gate

以下四点来自同一次冻结 B4 trajectory，||b||=13.197399418369043。rho 越小代表残差缩减越强；1/rho_M、rho_hat_M|B 和 rho_75/rho_75M 是 V6 late Gate 使用的三项量。

| iteration | true residual norm | relative | rho75 | rhoM | rho75M | rhoB | rhoBM | rho_hat_M|B |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 13.197399418369043 | 1.0 | .3523076473 | 1.0 | .3356959033 | 2.5454114777 | 2.3875865401 | .9379962969 |
| 20 | 5.596174034261749 | .4240361193 | .8943020663 | .9948007833 | .8862677949 | 1.4571445787 | 1.4129164173 | .9696473761 |
| 100 | 2.2498785337431007 | .1704789302 | .9714345633 | .9959977437 | .9638071822 | 1.1974356958 | 1.1696913824 | .9768302269 |
| 200 | 1.864887327107556 | .1413071824 | .9717247345 | .9969376898 | .9656838607 | 1.1564543805 | 1.1337134509 | .9803356449 |

| late Gate | threshold | k=100 actual / pass | k=200 actual / pass |
|---|---:|---:|---:|
| 1/rho_M | >= 1.5 | 1.0040183386743322 / false | 1.0030717167190784 / false |
| rho_hat_M|B | <= 0.67 | .9768302269439019 / false | .9803356448661497 / false |
| rho75/rho75M | >= 1.20 | 1.0079138039979252 / false | 1.00625553984881 / false |

因此容量 Gate 是 6/6 失败，正式分类为 M120_MODAL_COARSE_INSUFFICIENT_ON_FROZEN_LATE_RESIDUALS。E2 implementation checks 全部通过，implementation_failures=[]；这不是 implementation failure，也不是对所有 M120 coarse spaces 的普遍证明。

B4 solver 本身在 200 次迭代后 converged_reason=-3，final true residual=0.14130718242200643。该 B4 convergence negative 与 capacity oracle Gate 独立记录；不能把它写成 solver convergence success，也不能用它改写 E2 capacity 分类。

### 资源、停止与证据

| 项 | measured |
|---|---:|
| stage4 wall | 3682.42344509298 s |
| whole-run elapsed | 3691.709302290925 s |
| simultaneous process-tree peak | 12.094310760498047 GiB |
| simultaneous worker RSS / PSS / USS | 12369.968 / 10952.569 / 10778.551 MB |
| swap | 0 |
| warning / memory termination / timeout termination | true / false / false |

该峰值是本次 E1 basis + E2 audit whole-run 的实测资源，不是未来 production solver 的内存预测。E1 阶段约 2878 s、E2 阶段约 707 s 为 progress 时间戳的 derived wall interval。

Raw root：/tmp/task037-e1-diagnostic-tlvcVB/benchmarks/artifacts/task037/e2_modal_capacity_ddcc5ea8/mpi8/。

| raw file | bytes | SHA256 |
|---|---:|---|
| task037_e1_modal_basis_audit.json | 23617 | a4305d04037e4b1ea7940d365c6cfbe352883f0b25180e0ff6646c2f2e34e2dd |
| task037_e2_modal_capacity_audit.json | 26550 | 7962bb6ccf28307706cf0177da237b23bfde797618061468684228371078adb0 |
| watchdog_summary.json | 143585 | bb62f563722dd93e3cb8ef19778c5a334baaec315ac37f03e8c7f841c22209d5 |
| run_summary.json | 44577 | ec2101517dcfc7d96088a44cce2f5a0790f516d611cfb5fe59fca1d1d5112fea |
| progress_3d.jsonl | 47542 | ccdc0e704cb81a637e3de9a9107231f44b5664427fb011c234797682c115f0b0 |
| memory_timeline.csv | 52192997 | f9f7e9d06107e383b1c994ff502ead251ad65c36a913bc723fb6ec3f9db0dff0 |
| worker_stdout.txt | 4878 | d26d8aff0022db07992d91b24171def1968d2a5b3258061c4f11aeb1839b9a21 |

### 修复链、合入边界与停止

与本次 source SHA 相关的完整修复链为：

| commit | 作用 |
|---|---|
| d7335650dc47e8bc52a436f47f92444837f14ad4 | 近简并 modal subspace joint rotation |
| 769963b3f3cf9c95877be5d469e8bf611972125f | frozen B4 true-residual carrier |
| 723ac075dea53adcace1029b9fb5420b7b2dac90 | E1 使用完整 condensed action |
| 005db75b1b70e0193737a24d2dae91e9b1e90607 | same-run E2 modal capacity gate |
| 5baa0c732811f1f1ac348513f73dc2687dc24160 | formal E2 timeout admission |
| 57edf5185d013897c1031e19ff0234a7f3b169ab | matrix-free E2 telemetry |
| b4e532913a28cd5efeba999139af64683565c199 | same-run E2 budget |
| 95b4c3b51557e8879b3f273225b87e65e08f35a9 | matrix-free DtN block action projection |
| ddcc5ea87b56eeec5ae0a385d3dfac4237ce3877 | JSON scalar serialization fix |

Selective merge 仍须分组：通用 MatPython telemetry 与 matrix-free DtN action compatibility 可作为独立 selective-review candidate；E1/E2 Candidate E 的 modal basis、capacity oracle 及其负结果均为 research-only，不能整体合入 production，也不能改变 ordinary defaults。

本轮按 V6 关闭 Candidate E；E3–E5 均 not_run，没有 official result，没有 full pytest（文档/record 收口不重复运行全库测试）。本结果只关闭 frozen p6/h10、MPI8、同次 B4 late residual 上的 Candidate E，不证明 M120 coarse 在其他配置下没有容量。
