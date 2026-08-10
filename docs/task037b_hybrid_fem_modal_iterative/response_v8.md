# Task37b M1–M10 内存优化结项

本轮把已经完成的 V6 MPI8 候选及其后续内存实验整理成一份可核验的结项。内存优化的含义是：在不改变方程、网格、预条件器和物理输出的前提下，让已经不再使用的矩阵、场数组或导出临时对象尽早失去引用，并让现有 PETSc/allocator 清理路径有机会归还页面。它不是更换求解算法，也不是降低精度。

所有原始 summary、solver record、timeline、stages 和 stdout 的路径与 SHA 以 [V6 memory closeout compact record](../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_memory_optimization_closeout_v1.json) 为主索引；重型 raw artifact 仍在 ignored 目录，不进入 Git。

## 1. 身份、范围与冻结条件

| 项目 | 结论 |
|---|---|
| 分支与 implementation/formal-source HEAD（文档前） | `codex/20260807-task37b-hybrid-iterative-development`，`b291f3dfdf5f0064ff243038f6809172f811d7aa` |
| V6 实现/正式数值源 | `ea132d8a31e5ccd6c45fb90bbb9b5f676cd78b0e`；唯一正式 V6 candidate，zero initial，无 retry、warm start、continuation |
| 冻结模型 | p6/h10、13.5 nm、S、10°、M120/240、每端 40 个 DtN mode、MPI8 |
| 算子与求解器 | exact monolithic Hybrid operator；双侧 fixed whole-endcap ILU(0)+Woodbury；right FGMRES，restart90，max_it1000，rtol `5e-9` |
| ordinary default | unchanged；所有优化均为研究性、显式候选链，不代表 production |
| master merge | not authorized |
| M11 | 只读可行性停止；无 commit、无 formal run |

没有开展 MPI 降级、continuum 收敛、mode-count 收敛、0.7 nm 资格化或新的物理算法研究。H1 direct-Hybrid 只作为冻结 M120 comparison authority，不冒充 mode-count 或 continuum convergence。

## 2. 优化阶梯与最终资源结论

| 阶段 | 主要作用 | process-tree RSS peak（MiB） | 结论 |
|---|---|---:|---|
| V6 original | tight residual/traction candidate | 7297.50390625 | numerical/physics pass，MPI8 resource negative |
| M1 | QEP 与 recovery 前 collective heap cleanup | 6188.55078125 | 数值等价，资源仍略超 6 GiB |
| M2 | 两端 recovery 之间 cleanup | 6156.65234375 | 数值等价，仍超线 |
| M3 | 两端 canonical packet heap 分侧 cleanup | 6161.02734375 | 数值等价，较 M2 增加 4.375 MiB；未证明内存收益 |
| M4 | canonical packet audited streaming | 6147.89453125 | 数值等价，接近但仍超线 |
| M5 | bounded one-cell trace expansion | 6128.7109375 | 数值等价，资源正 |
| M6 | compact full-field lookup | 6166.9921875 | 数值等价，资源负；ghost/local lookup 集合变大 |
| M7 | used-DoF scatter mask | 6144.15234375 | 数值等价，超 6 GiB `0.15234375` MiB |
| M8 | entity-position DoF mask | 6140.84765625 | 数值等价，资源正但余量很小 |
| M9 | cell-major active-trace streaming | 6140.44140625 | 数值等价，较 M8 仅 `-0.40625` MiB，负收益结果保留 |
| M10 | own-physics heap 在 canonical 前释放 | 6018.57421875 | 数值/物理/离线 authority 全通过，资源正 |

权威口径始终是同时存活 MPI process-tree RSS，不是 worker RSS sum，也不是 PSS/USS 或对象字节体积。M10 为 `5.877513885498047 GiB`，低于严格 `6144 MiB` 上限 `125.42578125 MiB`。相对 M9、M8、M5、V6 分别为 `-121.8671875`、`-122.2734375`、`-110.13671875`、`-1278.9296875 MiB`。

从 7.1265 GiB 降至 5.8775 GiB 不是单一“释放一个大矩阵”的结果，而是逐步缩短 QEP、recovery、canonical packet、trace expansion、DoF lookup 和 own-physics 临时对象的重叠生命周期。M9 的 cell-major 重排只带来 `-0.40625 MiB`，因此该负结果没有被包装成有效优化；M10 才提供了本阶梯中明确的有效余量。

## 3. M10 online 数值与物理

| 指标 | measured value | Gate |
|---|---:|---|
| outer iteration / reason | `792 / 2`，`CONVERGED_RTOL` | pass |
| reported residual | `3.578062165607276e-9` | `<=5e-9` |
| global residual | `3.578062144715876e-9` | `<=5e-9` |
| bottom residual | `4.921856578759462e-9` | `<=5e-9` |
| top residual | `2.6635965562403923e-9` | `<=5e-9` |
| modal residual | `1.4561321294580367e-15` | `<=5e-9` |
| exact traction bottom/top | `4.820141813913522e-9 / 2.6635965562403923e-9` | each `<=1e-8` |
| recovery / own physics / canonical / lifecycle | `true / true / true / true` | pass |

| R | T | A | A_volume | R+T+A_volume | closure |
|---:|---:|---:|---:|---:|---:|
| `0.0007628816277266691` | `0.6027016338728337` | `0.39653548449943965` | `0.39653548508184505` | `1.0000000005824054` | `5.82405457194568e-10` |

M10 own-grid、canonical 四角色和 selected interface/middle E/H 均由通过 residual Gate 的场产生；没有把 postsolve scalar 或近似 field 误当作 official output。

## 4. 离线 authority checker

M10 checker 只读取 immutable online evidence，与 online MPI8 RSS 分开计量；没有启动 MPI、PDE、direct export 或第二次 candidate。

| 比较组 | 结果 |
|---|---|
| checker | exit 0，`pass=true`，`failures=[]`，evidence integrity、candidate evidence、authority bindings 均通过 |
| q bottom/top | `3.1552581864833886e-9 / 4.059311187825597e-9` |
| orders | key/finite `80/80`；significant `12/12`；below-floor `68`；significant max power relative error `1.798107156229766e-6` |
| canonical | bottom/top active/full 四角色最大 relative L2 `1.3683141787825865e-8`，阈值 `1e-5` |
| selected E/H | 坐标对齐通过；各区域最大 relative L2 `3.6550910104971564e-9`，阈值 `5e-3` |
| modal | raw coefficient 为独立 QEP gauge diagnostic；magnitude relative L2 `1.4759171008539638e-9`，physical qualification pass |
| iterative vs frozen Full3D | analytic/power/amplitude `12/12`；最大 power/amplitude `1.5279985631812265e-10 / 4.140045890152348e-9` |
| direct-Hybrid vs frozen Full3D | analytic/power/amplitude `12/12`；最大 `1.984856723424855e-12 / 2.0684155314519094e-12` |

原始 checker 输出为 `benchmarks/artifacts/task037b/v6_m10_offline_qualification_checker_b291f3d.json`，SHA256 为 `feab4a65d5900c7afc9b7729aa9d80c8449a4ce3822c33c991f8c6baf36a3039`；checker wall `27.266378779080696 s`、RSS `110.63671875 MiB`，不计入 online authority。路径索引由 compact record 承担。

## 5. modal 系数的表示边界

raw modal coefficient relative L2 为 `1.1292458067631135`，状态是 `diagnostic_not_comparable_independent_qep_gauge`，不是 pass。两个独立 QEP 可能有不同的相位和近简并子空间基底；没有 shared basis fingerprint 或 transport 时，逐项系数并非 gauge-invariant。资格权威因此是坐标完全对齐的物理 E/H reconstruction，magnitude relative L2 为 `1.4759171008539638e-9`。

这保留了真实 raw mismatch，没有发明 transport、没有删除诊断值，也没有把 raw coefficient 差异静默改写为通过。这是对 Review V6 字面 raw modal-amplitude 比较要求的表示语义边界，不是数值阈值放宽。

## 6. M11 停止理由

M11 只读检查了 top-recovery peak 时的对象依赖。bottom/top recovered field 的已知 full payload 由每侧 `25986` 个 complex128 行推得约 `415776` bytes；local/ghost DOLFINx overhead 未记录。后续 joint validation、interface continuity、absorption 与 canonical export 仍需 systems/coupling、bases 和两端 recovered fields。QEP operators 与大因子已经在更早阶段释放。

因此顺序 recovery/export 方案 A 的可释放量不足以合理达到 `64 MiB` Gate；临时 artifact/reload 方案 B 会引入 serialization、hash、reload 和 DOLFINx 重建，成本与风险都不成比例；保留现状的 C 被选中。M11 formal not_run，后续不启动新的 candidate。

## 7. 最终边界

| 层次 | 结论 |
|---|---|
| numerical / physics | `PASS` |
| MPI8 resource | `MPI8_RESOURCE_POSITIVE`，process-tree RSS `6018.57421875 MiB` |
| 总结 | `DOUBLE_APPROXIMATE_MPI8_TIGHT_LINEAR_AND_PHYSICS_PASS_WITH_MPI8_RESOURCE_POSITIVE` |
| 生产资格 | `research-only`；ordinary defaults unchanged；master merge not authorized |
| 未运行 | full pytest、CI、M11 formal、MPI reduction |

完整阶段资源账本见 [resource ledger](outcomes/resource_ledger.md)，正式数值与生命周期见 [full MPI8 qualification](outcomes/full_mpi8_qualification.md)，变更依赖与选择性边界见 [changed files](outcomes/changed_files.md)，测试范围见 [test summary](outcomes/test_summary.md)。
