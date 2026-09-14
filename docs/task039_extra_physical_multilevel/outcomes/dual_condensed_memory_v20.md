# Task39extra V20：双层凝聚的编译、缓存与生命周期结果

本报告记录 Review V20 只授权的一场 original。它研究的是一个固定的 13.5 nm、Full3D p6/h10、MPI1 三维单胞；目标是核对 V19 已通过的双层凝聚是否因编译器、identity 数组、p4 矩阵和求解对象同时存活而产生可避免的峰值。单元凝聚的作用是先解每个有限元单元内部未知量，只把相邻单元共享的 trace 和端口留给外层迭代，最后恢复完整场。

## 1. 正式身份和结果

| 字段 | 值 |
|---|---|
| source | `b337d215c3d278d0c1e715f53e28b69f7f0ee3fe` |
| profile | `physical_p6_trace_p4_condensed_lowmem_v20` |
| run id | `task39extra_v20_y3_lowmem_original` |
| input | `input/task39extra/v20_y3_lowmem_original.dat` |
| run root | `results/euv_grazing1_phi0/task39extra_v20_y3_lowmem_original__full3d_iterative__mpi1__Mna/20260914T163338.120918Z` |
| result | `Y3_ORIGINAL_FULLSPACE_OFFICIAL_PASS` |
| formal/replay | `1 / 0` |
| formulation | Full3D，p6/h10，13.5 nm，252 hex，MPI1，80 DtN modes |
| original A6 | independent `9.730817853580463e-7`；worker post-release `9.730817853580687e-7`，limit `1e-6` |
| physical comparison | R/T/A/`A_volume`、80 modes、E/H、curl、守恒和 absorption consistency pass |

独立记录 `y3_independent.json` 的 57 项检查和 24 个 physical subchecks 全部通过。正式后处理使用保存并核验过的完整场 packet；不是只拿 retained Schur vector 生成官方功率。

## 2. 编译和缓存

完整 p6 condensation form 在 `schur_factor_symbolic_started` 前准备。正式 cache 记录了 140 个 hardlink eligible files、`1417038702 B` eligible bytes、4 个旧 module family 文件共 `196161200 B` excluded bytes；没有复制文件。准备窗口峰值包含 `cc1`，共有 76 个含编译器的资源采样点；这不是 76 次编译。其余 p4 和 9 个评价内核调用为 cache hit。

| 项目 | measured 事实 |
|---|---:|
| p6 target cache miss 次数 | 1 |
| p6 target compile elapsed | `56.762399450992234 s` |
| compiler options | `-O2`, `-g0` |
| cffi debug | false |
| target module size | `43662736 B` |
| source cache | `/tmp/myfenics-xdg-cache-1000/fenics` untouched |

新旧 target 同 form signature/ABI/选项和 `108831921 B` generated-C source size，但 raw C SHA 不同、inode 不同，所以确实发生了新编译；本场 `.so` module size 是 `43662736 B`。现有诊断只支持“真实 cold miss/顺序被观测”，不支持“生成 C 逐字节相同”或“所有文本差异仅来自编译顺序”的更强结论。

## 3. identity payload 和 p4 后端依赖

identity 语义为 12 个逻辑 class 共用一个 450 阶、float64、只读 identity，服务于 RHS projection、solution embedding、residual projection。记录字段为：

```text
unique_storage_count = 1
unique_storage_bytes = 1620000
unique_numpy_bytes   = 183282224
p6_cache_descriptor_sha256 = c79e781afb4b866db0e38bcaafd92d80f8148c847e1de6bec594ebc4994db62e
```

V19 数值 cache baseline 为 `201102224 B`，因此本轮 payload 下降 `17820000 B`。这是 derived from two saved ledgers 的数组差，不是 full RSS 差。

PETSc/MUMPS 后端依赖核验结论为 `MATRIX_RETAINED_BACKEND_DEPENDENCY`。实际 v3.19.6 conversion 路径借用 SeqAIJ values pointer；没有 public detach 证明原矩阵可在 factor live 时销毁。小型非 Hermitian、非零 B/D 和 port RHS fixture 证明“先 destroy factor、矩阵仍存活”安全（四次 solve residual 最大 `2.835794086517554e-16`，linearity relative `3.6619314138395023e-16`），但没有执行不安全的 early free。正式 p4 矩阵保持：shape `21824×21824`、NNZ `8184464`、complex128；CSR/mapping/values content identities 在 factor boundary 保持不变。early-release saved bytes=`0`。

后端还记录了 MUMPS 的 upper accounting：allocated upper=`1463000000 B`、used upper=`838000000 B`、matrix=`232205060 B`。这些是后端分配/使用上界和矩阵账本，不是 simultaneous process-tree RSS，也不能解释成释放后已归还给操作系统。

## 4. 释放时间线和阶段资源

释放时间线是：`v20_complete_field_packet_saved` → `y3_independent_final_residual_complete` → `v20_release_gate_checked` → preconditioner release → p6 release → p4 factor release → post-release final residual → physical output comparison。释放后 RSS 没有被强行解释成等量 payload 归还：释放前最近样本 `2278993920 B`，p4 release 后最近样本 `2253828096 B`，下降约 `25165824 B`。

下表是同一连续 watchdog 树的 simultaneous sampled peaks。前四个阶段窗口互不重叠；最后一行是覆盖它们的全过程。编译器采样子集也与对应阶段重叠，各峰值不能相加。全过程峰值保留 compiler；PSS 列是相应 RSS 峰值采样时的 PSS。

| 阶段 | elapsed sample (s) | RSS (B) | PSS (B) | compiler descendants |
|---|---:|---:|---:|---:|
| preparation before factor | `95.26784548800788` | `2831749120` | `2797270016` | 1 |
| factor/H6/p6 cache setup | `301.13237249999656` | `2274676736` | `2244195328` | 0 |
| iteration/final residual | `1444.032242738991` | `2278993920` | `2248436736` | 0 |
| release/recovery/postprocess | `1476.8670740799862` | `2372825088` | `2342238208` | 0 |
| full workflow | — | `2831749120` | `2797270016` | 1 |

全流程 resource scope 是 continuous parent process tree，`inventory_peak_bytes=2013567110`、`workspace_peak_bytes=423441224`、swap peak=`0`，tree cap/reserve/cleanup/source-clean gates 通过。

## 5. 残差、官方量和 V18/V19 对照

worker 每 8 步保存一次 A6 checkpoint；independent checker 读取并重算这些保存值（不是 checker 另行保存一套残差）。去重后的 checkpoints 是：

```text
0   1.0000000000000004       8   7.149884433355884e-2
16  9.035909411932590e-3     24  1.7208335140301643e-3
32  2.844425452738279e-4     40  2.609402946038313e-4
48  1.276001157467142e-4     56  5.129021279317980e-5
64  1.769095465196477e-5     72  1.738066378245364e-5
80  1.262674366210474e-5     88  4.539202102579487e-6
96  1.493283570905824e-6     104 1.390201101210463e-6
112 9.730817853580463e-7
```

官方 current values 为 `R=0.3656258136701664`、`T=0.012990624019505325`、`A=0.6213835623103282`、`A_volume=0.6213833803349053`。相对既有离散参考（V19 同样使用）的最大 total power difference 为 `1.981579103027542e-7`，小于 `1e-5`；selected field 最大 relative difference 为 `8.291924787930399e-7`，小于 `1e-4`。完整场 L2/scaled-curl 误差为 `1.5860495296312503e-7 / 1.5359268899003175e-7`，均小于 `1e-4`。p4 全部 226 次在线 A4 检查通过，最大相对残差 `5.0455949355168026e-11 <= 1e-10`。

setup 诊断的 BAL_H/H6 各 1 次、p4 MatSolve 2 次；外层对应为 112/112/224 次。保持 `J M_aug J^H`、FGMRES32/max2048，未增加算法步骤。保存的完整 p6 x 与 V19 逐字节相同，SHA 为 `e077e0bd92fc93a54673aae4246fcc1d7c0dc3aceba9c3ee3fb48103c1e76cd3`。

| 指标 | V18 | V19 | V20 Y3 |
|---|---:|---:|---:|
| outer iterations | 564 | 112 | 112 |
| full tree RSS (B) | `2528460800` | `3965534208` | `2831749120` |
| full tree PSS (B) | `2494237696` | `3931141120` | `2797270016` |
| inventory (B) | `1830284886` | `2031387110` | `2013567110` |
| workspace (B) | `396129600` | `423441224` | `423441224` |
| full monotonic (s) | `6609.6613787800015` | `1352.0121227929922` | `1479.1772295139963` |

V20 相对 V19 的 full RSS 降 `1133785088 B`（`28.59098%`），full monotonic 时间增加 `127.1651067210041 s`（`9.4056%`）；相对 V18 的 RSS 增 `303288320 B`（`11.99498%`）。建议在本次固定 original、内存优先时采用显式 V20 lowmem，保留 V19 时间基线和 V18 较低 RSS 基线。没有新增必须低于 V18 峰值或快于 V19 的 Gate，普通默认不变。

| 阶段 RSS (B) | V19 旧事件推定窗口 | V20 新窗口 |
|---|---:|---:|
| 编译/准备 | `825548800` | `2831749120` |
| 分解/H6/p6 缓存构建 | `3965534208` | `2274676736` |
| 迭代/最终残差 | `2565308416` | `2278993920` |
| 恢复/后处理 | `2684796928` | `2372825088` |

V19 的 p6 编译发生在 setup，旧首个 checkpoint 也不是精确 KSP 起点。因此旧窗口只是有限边界重建，不能称各行严格同窗；全过程比较覆盖相同 original 的编译、求解、完整评价和清理。V20 的主要峰值仍在编译：树 RSS `2831749120 B` 中 cc1 为 `1576579072 B`。未实施的 p4 factor-live 矩阵提前释放按安全分支保留；本轮不再追查 detach，不重跑对照或 notch。

`run_summary.json` 的 conservative-realtime billing 为 `1611.2442379729905 s`，与 monotonic 的正差约 `132.068021 s`。它只用于保守费用；V19 的 `1474.858420017083 s`、旧政策占用和 unknown 字段继续独立保留。

## 6. 测试和范围边界

Y1 final focused 为 `116 passed / 1 skipped`，compileall/diff-check/ABI/frozen-contract 通过；Y4 文档合同为 `21 passed`。早期后端 fixture 的 int64→PETSc.Int32 cast 错误和 sandbox PMIx `errno=1` 工程现象均保留为非 PDE 记录；正式 PDE 没有 replay。未运行/未声称的项目包括 notch、5 nm/0.7 nm、MPI2/4 新资格、Ruff、full repository pytest、CI、GitHub 网页视觉核验和 allocator tuning。

机器可读证据：

- `benchmarks/artifacts/task39extra/dual_condensed_lowmem_v20/root_engineering/y3_independent.json`
- `benchmarks/artifacts/task39extra/dual_condensed_lowmem_v20/root_engineering/y3_root_lifecycle_review.json`
- `benchmarks/artifacts/task39extra/dual_condensed_lowmem_v20/root_engineering/y3_actual_v19_observable_comparison.json`
- `benchmarks/artifacts/task39extra/dual_condensed_lowmem_v20/root_engineering/y0_backend_dependency.json`
- `benchmarks/artifacts/task39extra/dual_condensed_lowmem_v20/root_engineering/y1_admission.json`
- `docs/task039_extra_physical_multilevel/outcomes/records/dual_condensed_memory_v20_compact.json`
