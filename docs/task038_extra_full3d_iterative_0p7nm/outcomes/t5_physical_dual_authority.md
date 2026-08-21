# T5 physical-dual authority and R4 controlled stop

## 结论

本批次的 `action` 是“给一个有限元向量，计算当前离散物理算子作用后的向量”；它是检查算子是否被正确实现的局部计算，不是求解 Maxwell 方程。`transmission` 是把两个 z-slab 之间的边界信息传给邻侧；T4 只证明了这一边界动作。`authority` 是能让历史数据安全进入当前算子的、可独立复核的物理身份链。`controlled stop` 是 watchdog 按预先冻结的资源上限主动终止进程并保留负证据，不等于数值失败或 OOM。

Review V2 要求的最终代码/证据源为
`ea7fc96b8c95eca13b5ee8055d7e0762f9ab02dc`。本文和 compact v2 文件尚未提交，因此最终文档 commit 不能在本文中自指；交付报告应另给最终 HEAD。

| stage | status | 具体结论 |
|---|---|---|
| R0 | `PASS` | branch、clean source、qualified WSL ABI、complex128/int32、单线程和 swap preflight 通过；正式源为 `ea7fc96…`。 |
| R1 | `PASS` | current structured identity 完整；old W5 mandatory physics/Floquet/orientation fields 不可用，same-physics claim 关闭，分类为 `HISTORICAL_W5_NOT_SAME_PHYSICAL_RHS`。 |
| R2 | `PASS` | p2/p3 与 frozen p6/h10 current dual component oracle 通过；不把 old RHS equality 当成 Gate。 |
| R3 | `PASS` | Path B `CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE` 通过 MPI1/MPI2 primal canonical、current action 和 residual closure。 |
| R4 | `FAIL / CONTROLLED_STOP_RESOURCE` | Candidate A 已有数值负结果；B 不具备 interior authority；C 在 worker 写 record 前超过 12 GiB watchdog 上限。 |
| R5 / T6-S | `not_run_by_R4_gate` | 没有运行 20/100/150/200 residual screen。 |
| T6-F、EH/RTA、T7–T9、full 0.7 nm | `not_run` | 未启动，也没有把缺失结果写成通过。 |

## R1：current/old physical identity

R1 clean evidence 使用 source `cd1ca8dfe6fdcc7a526d2794d2963dd6cd81a470`，compact identity 位于 `records/t5_physical_identity_v2.json`。current identity 的实际 artifact 为 76,966 bytes；old identity 为 7,774 bytes。两者都被 checker 读取并按字段判定，不能以 current 值补齐 old 缺失项。

| field | current | old W5 |
|---|---|---|
| wavelength | 13.5 nm | unavailable in old structured evidence |
| FE / mesh | N1E degree 6、h=10 nm、252 hexahedral cells、420 vertices；axis `[7,4,15]` | degree 6、h=10 nm、252 cells、420 vertices；几何 witness 与 current rebuild 相同 |
| geometry/connectivity | `e94ca5…` / `d9bc3d…` | 同值；这只证明网格实体身份，不证明 dual values |
| resolved config | 4076 bytes, SHA `78dc49b3…` | old config/bytes unavailable |
| ordered modes | 80，SHA `dee5c3ac…` | count 80，但 preserved ordered rows SHA `8d7c396b…`；逐 mode fields unavailable |
| Floquet, facet normal/tag, quadrature | finalized current contract；normal 为 top `z_max`，phase 由 MPC 一次施加 | phase、structured normal/tag 和 quadrature unavailable |
| materials / incident amplitudes | current resolved contract | epsilon/loss values、incident amplitudes unavailable；旧材料 tag coverage only |
| per-mode e/traction/H | current dynamic inventory | unavailable |
| MPC | 173,802 rows、9,210 constraints、relation digest `73920dca…` | row count/constraint count known，relation digest unavailable |
| RHS composition | incident top traction + negative mode traction, normalized by H | old manifest says incident top traction plus fixed outgoing projections，component sign/H rows unavailable |

因此 R1 的物理结论是：old/current packet key 可以对齐，但不能声称它们是同一物理 dual。old W5 的 exact mesh、same ABI、row count 和内部 manifest 仍保留为 provenance，不能替代缺失的 normal、Floquet、orientation、quadrature、H 与 coefficient semantics。

## R2：current dual component oracle

R2 raw/check 文件都在 ignored `benchmarks/artifacts/task038_extra_full3d_iterative_t5_authority_v2/r2_09b9264/`；tracked compact 记录只保存哈希和必要 Gate。独立 oracle 是 fresh direct component assembly；它分别按 component、side、polarization 和 all-mode total 重组，并检查 pre-MPC、owner-local、canonical 三个层次。

| case | max candidate/direct relative L2 | limit | max H error | all-mode/group recompose | repeat max | status |
|---|---:|---:|---:|---:|---:|---|
| p2/h50 MPI1 | `8.692664947436813e-15` | `1e-12` | `0` | `0` | `5.909031086016836e-17` | PASS |
| p3/h50 MPI1 | `2.5937308039595027e-14` | `1e-12` | `0` | `0` | `7.611020931512763e-17` | PASS |
| p6/h10 MPI1 | `4.559266389658486e-14` | `1e-11` | `3.2741809263825522e-15` | `0` | `4.8257303460951034e-17` | PASS |
| p6/h10 MPI2 | `4.559266389658486e-14` | `1e-11` | `3.2741809263825522e-15` | `0` | `4.8257303460951034e-17` | PASS |

这些 records 的 finite、duplicate/missing/extra、normal、negative traction、conjugation、H、slave exclusion、finalized MPC phase-once 和 no numeric allgather 均通过。R2 证明的是 current component path；它没有把 old W5 coefficients提升为 current authority。

## R3：current residual at the historical primal state

Path A 被明确标为 `NOT_QUALIFIED`，没有拟合 alpha、手工缩放、旧 PC replay 或 row-array 搬运。Path B 使用 old `m6b_iter200_solution.npy` 作为 primal state，经 current primal canonical API 映射，再由当前 `b_current - A_current x_old` 产生新 residual。正式 source 名称为
`CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE`；它不是 current PC 的 200-step residual。

| Gate | MPI1 | MPI2 / pair |
|---|---:|---:|
| old solution file SHA / array SHA | `d2a5a7e7…` / `620b5e49…` | MPI2 不读 old raw；只读 hash-bound MPI1 primal manifest |
| shape / dtype / finite | `[173802]` / complex128 / true | canonical reconstruction |
| primal roundtrip relative L2 | `1.3336463445521434e-17` | mapped primal cross-MPI `1.4389898139779045e-17` |
| current action repeat | `0` | `0` |
| residual recompute relative L2 | `2.381515544959568e-18` (limit `1e-11`) | same value；cross-MPI residual `1.145631881739048e-14` (limit `1e-12`) |
| key/count/duplicate | 164,592 keys; duplicate/missing/extra 0 | same |
| swap | 0 B | 0 B |

R3 的数值/authority Gate 通过，但该阶段只有 rank-local RSS/VmSwap 记录；process-tree watchdog provenance 未测，因此不宣称 R3 的 process-tree resource qualification。

Old residual本身仍有内部闭合：`rhs - outer_action` relative L2 为 `1.742722222852365e-20`。这只能证明旧运行自洽，不改变 Path A 不合格的结论。old residual 与 fresh current residual 的 diagnostic norm/angle/group energy 保留在 compact record；不用于 source Gate。

## R4：Candidate A/B/C

### Candidate A

Candidate A 是固定的一阶 impedance/Robin artificial transmission；每个 source 都执行真实 forward slab solve、exact current action residual propagation、backward sweep、PoU correction 和 fresh `b-A_delta` closure。它不是 T4 的单次 boundary apply。A 的 frozen source SHA 为 `1a4d495a4f7a78bafb389ab9b30d0b49fe7bd5be`。

| source / MPI | rho / limit | closure | repeat | process-tree peak | wall | swap | result |
|---|---:|---:|---:|---:|---:|---:|---|
| physical_rhs / 1 | `0.8145890334049838 / 0.60` | `1.2458376041083906e-16` | `0` | `5,145,784,320 B` | `2812.015165732999 s` | `0 B` | numerical FAIL |
| gradient / 1 | `0.8889127715646881 / 0.90` | `1.271047984953834e-19` | `0` | `1,323,728,896 B` | `2747.751835015006 s` | `0 B` | PASS |

physical source 的 closure/repeat/resource 都通过，只有 contraction `rho` 越界；所以这是 Candidate A 的数值 contraction 负结果，不是实现 defect。监督要求的 fail-fast 使其余 8 个 case（curl/checkerboard/long-tail MPI1 和五个 MPI2）为 `not_run_by_fail_fast`。

### Candidate B

B 分类为 `NOT_APPLICABLE / CANDIDATE_B_INTERIOR_MODAL_AUTHORITY_NOT_QUALIFIED`，不是数值 FAIL。当前 `interface_z` 是 mixed Si–Si / Si–air interior interface；T3 的 analytic modal authority只覆盖 exterior top/bottom DtN。不能把全局 Floquet mode 截到零散 homogeneous facets 后宣称 interior modal transmission 已被证明，因此 B 没有运行 rho 或 resource formal。

### Candidate C

C 的 focused fixed second-order local impedance authority/tests 通过；它只替换人工 PC transmission，不改变 exact physical action、Maxwell 弱式、材料或 Floquet phase。正式 C physical_rhs MPI1 使用 source `ea7fc96…`，在 worker 写 record 前被外部 watchdog停止，resource classification=`CONTROLLED_STOP_HARD_12_GIB`：

| resource field | measured value |
|---|---:|
| wall | `406.7977727999969 s` |
| process-tree peak RSS | `12,942,209,024 B` |
| decimal 6 GB limit | failed |
| hard 12 GiB limit | failed (`12,884,901,888 B`) |
| process-tree / dedicated-authority swap | `0 B` |
| return / stop | `-15` / `hard_stop_12_gib` |
| termination | SIGTERM, no SIGKILL required |

raw watchdog SHA 为 `cc1bee361712361af52414e1b0d76bb52fd9712b5eecb01b5375b81d2be23ff0`，compact SHA 为 `3102995f3d10170bb4a96f4890ac9fb919e140c570535a5fd38fb59447179a08`。worker 没有写 `record.json`；独立 R4 checker 已按命令尝试，但因 record 缺失 fail-closed，未产生伪造的 `check.json`。因此 C 的 rho、closure、repeat、finite、exact update counts、class manifest 和 formal payload 全部是 `not_run_by_resource_hard_stop`，不能称 C 数值失败，也不能称 192 B payload 已被 formal 验证。

## 资源、分类和未运行边界

| 分类 | 本批次事实 |
|---|---|
| measured | R1/R2/R3 identity and numerical gates；A 两个 MPI1 case；C watchdog raw/compact resource |
| derived | old/current relative RHS `10.934736136386151`、R2 group/repeat maxima、R3 pair identity |
| predicted | 没有把任何预测当 qualification；没有对 0.7 nm 做内存预测结论 |
| failed | R1 same-physics RHS bridge；Candidate A physical contraction `0.8145890334049838 > 0.60`；R4 overall resource closure |
| controlled_stop | Candidate C watchdog `hard_stop_12_gib`，不是 OOM kill、不是 SIGKILL、不是数值失败 |
| not_run | C formal numeric fields、A remaining 8 cases、B、R5/T6-S、T6-F/EH/RTA、T7–T9、full 0.7 nm |

A 的 cold peak `5.145 GB` 和 gradient 的 warm-like peak `1.324 GB`不等于完整 PDE 的内存证明；本批次没有运行 full Maxwell PDE，因此 `<2 GB` 战略目标没有达到。

## Evidence index and changed scope

新增 v2 compact records：

- `records/t5_physical_identity_v2.json`
- `records/t5_component_oracle_p2_mpi1_v2.json`
- `records/t5_component_oracle_p3_mpi1_v2.json`
- `records/t5_component_oracle_p6h10_mpi1_v2.json`
- `records/t5_component_oracle_p6h10_mpi2_v2.json`
- `records/t5_long_tail_authority_v2.json`
- `records/t5_sweep_candidate_a_v2.json`
- `records/t5_sweep_candidate_b_v2.json`
- `records/t5_sweep_candidate_c_v2.json`

原有 v1 negative evidence、92 MB old shard、canonical shards、mesh/JIT 和 watchdog raw 均未覆盖或复制进 Git。当前代码没有因本轮文档收口而改变；T1–T4 production APIs、T5 bridge core 和 Candidate C core仍由 `ea7fc96…` 约束。已有 focused/serial/MPI2/compileall/AST/diff 检查均为本地结果，不声称 CI。

下一轮不应授权 T6-F。必须先解决 Candidate C p6 JIT/process lifecycle hard stop，由新的 Review 授权；不得用预热、伪 watchdog 或删减监测来制造 pass。`outcomes/summary.md` 与 `docs/development_progress.md` 继续保持 T9 closeout 语义，不能提前伪造最终结项。
