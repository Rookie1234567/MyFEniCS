# COMSOL 3D 直接法与成功迭代法计算报告

**整理日期：** 2026-07-13  
**覆盖范围：** `3d_iterative_solver_task` 中的已保存 MPH 模型、批处理日志和结果表。本文只汇总已有记录，未重新网格化或求解。

## 1. 结论摘要

- 基准问题是一个约 **117.8 万自由度**的三维频域电磁波周期结构模型。实际参与计算的是 `mesh1` 的**自由四面体网格**；电场未知量采用 **curl-conforming Nédélec（edge/vector）单元**。此前日志中的“二次拉格朗日”仅指**几何形函数**，不是电场的有限元基函数。
- 直接参考解采用 **MUMPS**。同一基准系统的对比运行总耗时 **282 s**，峰值进程内存高水位为 **22.989 GB**；该解作为全部迭代法的数值参考。
- 内存最小的成功方案是 **右预条件 TFQMR + 几何多重网格（GMG）**：峰值 **8.992–9.010 GB**，较直接法降低约 **61%**，但总耗时为 **800–869 s**。
- 若希望在内存、时间和结果精度之间取得较好平衡，推荐 **右预条件 GMRES + GMG，restart=100**：峰值 **11.699 GB**、总耗时 **417 s**、`|Δ(R+T)|=1.95e-8`。
- 本报告的主对比全部采用**零级衍射**口径：未额外计算非零衍射级，适合比较线性求解器，但不应用于完整衍射谱分析。

## 2. 计算环境与统计口径

| 项目 | 已记录信息 |
|---|---|
| COMSOL | 6.4.0.293（win64） |
| 计算资源 | 1 个插槽、10 个内核；日志显示可用内存 32.38 GB |
| 求解类型 | `std1` 波长域研究，`sol1/s1` 稳态求解器，`fc1` Fully Coupled |
| 线性系统 | 复数、非对称矩阵；虽然求解器树使用稳态/全耦合节点，基准日志只出现 1 次全耦合迭代 |
| 结果量 | `ewfd.Rtotal`、`ewfd.Ttotal`、`ewfd.Atotal` 和 `ewfd.RTtotal=Rtotal+Ttotal` |
| 成功判据 | 与直接法相比，`abs(ΔRtotal/ΔTtotal/ΔRTtotal) <= 1e-3` |

**内存口径。** 性能 CSV 的“峰值内存”由脚本从 COMSOL 批处理日志提取，为“物理内存高水位”和 `Memory:` 行高水位中的较大者。因此它应理解为**峰值进程内存占用参考值**，不应一律解释为物理 RAM。下文在原始日志可用时另列“物理/虚拟内存”。

**时间口径。** “求解器阶段”是 COMSOL 稳态求解器节点的耗时；“总时间”是批处理日志的 `总时间`，包含编译方程、变量准备及类运行开销。跨不同运行的少量差异属于机器当时负载和重复运行差异。

## 3. 基准模型概括

### 3.1 几何、物理场和边界条件

| 项目 | 设置 |
|---|---|
| 模型文件 | `models/3D_benchmark_direct_source.mph` |
| 周期单元 | `L_x × L_y = 50 nm × 25 nm` |
| 几何 | 3 个实体：上方空气块 `50 × 25 × 130 nm`、下方基底 `50 × 25 × 10 nm`、居中的光栅块 `16 × 25 × 120 nm` |
| 波长与入射 | `λ0=13.5 nm`，P 偏振，入射角 `80°`，入射功率 `1 W/m` |
| 物理场 | `ewfd`：Electromagnetic Waves, Frequency Domain（电场波动方程） |
| 边界/端口 | 两个周期端口（端口 1 激励、端口 2 非激励），两个 Floquet 周期条件；模型中还定义了 PEC 条件 |
| 主未知量 | 复电场 `Ex,Ey,Ez`；零级结果的 S 参数状态 `S1x0,S2x0` |

### 3.2 实际使用的网格、单元和自由度

| 项目 | 记录值 |
|---|---|
| Study 实际引用网格 | `mesh1`（`std1` 明确引用 `geom1, mesh1`） |
| 网格生成方式 | `FreeTet`（自由四面体网格） |
| 网格尺寸 | `hmax=hmin=2.5 nm`；`hcurve=0.6`，`hnarrow=0.5`，`hgrad=1.5` |
| 实体单元数 | **182,393 个 tetrahedra** |
| 边界三角形数 | **12,260 个 triangles** |
| 几何形函数 | 日志明确为 **二次拉格朗日几何映射**；其用途是表示网格/几何，不是电场基函数 |
| 电场离散基函数 | `ewfd` 使用 **curl-conforming Nédélec（edge/vector）单元**。Study 设置为 `shapeOrder=comp1, component`，即采用物理场组件的默认阶数；COMSOL 6.4 的默认设置是二阶 curl/Nédélec 单元 |
| COMSOL 记录的自由度 | **1,178,238**（基准零级衍射算例） |

模型树还保留了 `mesh2`（扫掠六面体网格，96,000 个 hexahedra）的定义，但该研究实际引用的是 `mesh1`。因此本报告的基准性能和自由度均对应**自由四面体网格**，不能把 `mesh2` 的六面体数误当作本次计算的网格统计。
### 3.3 衍射级口径

第 6 节的直接法和首次迭代法探索均未额外加入非零衍射级：两个周期端口设置为 `AddDiffractionOrders=0`，且模型中没有 `DiffractionOrder` 节点。因此，`Rtotal=Rorder_0_0`、`Ttotal=Torder_0_0`，即报告中的 R/T 是**零级衍射结果**。

这不影响同一零级模型上直接法与迭代法的公平比较；但它**不是完整衍射谱**，不能据此分析各非零衍射级的能量分布。若要做完整的衍射级收敛或能量分配比较，必须在所有待比较模型中启用相同的衍射级集合，并重新报告自由度、R/T/A 和资源占用。

## 4. 直接法：MUMPS 参考解

### 4.1 求解器树与关键设置

`sol1/s1/fc1.linsolver = d1`，其中 `d1.linsolver = mumps`。主要设置如下。

| 类别 | 设置 |
|---|---|
| 直接求解器 | MUMPS；多线程分解和回代均启用 |
| 重排序 | `mumpsreorder=auto`；`preorder=nd`（Nested Dissection） |
| 内存/磁盘策略 | `mumpsalloc=1.2`；`ooc=auto`；`incore=auto`；`memfracooc=0.99`；`usetotmemory=0.8` |
| 数值稳定性 | 主元启用；`thresh=0.01`；`pivotperturb=1e-8`；`mumpsblr=off` |
| 复用 | `reusepattern=on`；`reusereorder=on` |
| 迭代改进 | `iterrefine=on`；最多 15 步 |

### 4.2 参考结果与资源占用

| 指标 | 数值 |
|---|---:|
| `Rtotal` | `8.2296654875e-4`（0.08229665%） |
| `Ttotal` | `0.6167277217`（61.67277217%） |
| `Atotal` | `0.3824493118`（38.24493118%） |
| `RTtotal` | `0.6175506882` |
| 求解器阶段 | 269 s |
| 总时间 | **282 s** |
| 物理/虚拟内存（该次对比运行结束时） | 19.79 / 22.99 GB |
| 峰值进程内存高水位 | **22.989 GB** |

直接法日志中的线性残差为 `6.3e-12`，作为本报告的参考解。较早一次保存在源 MPH 内的历史记录为 264 s、17.45 GB 物理内存和 23.08 GB 虚拟内存；为保证横向可比性，性能表统一使用 2026-07-08 的 282 s 对比运行。

## 5. 成功迭代法的共同 GMG 设置

所有成功的 GMG 案例均保持相同的物理、几何、网格和结果表达式，只替换 `fc1` 选用的线性求解器/预条件器。外层迭代节点为 `i1`。

### 5.1 外层 Krylov 迭代器

| 项目 | 共同设置 |
|---|---|
| 可选求解器 | `gmres`、`fgmres`、`tfqmr` |
| 预条件方向 | 默认 `prefuntype=right`；仅 `gmres_gmg_left` / `fgmres_gmg_left` 使用 `left` |
| 线性相对残差容差 | `irestol=0.01`；仅 “tight” 测试为 `0.001` |
| 最大线性迭代数 | `maxlinit=10000` |
| GMRES/FGMRES restart | 默认 300；成功测试还包括 100 和 50 |
| GCRO-DR | 默认 `gcrodr=on`；部分对照关闭 |
| 其他 | `usenlweights=on`，`iterm=tol`，`errorchk=auto`，`maxilinit=100` |

右预条件形式可写为 `A M^{-1}y=b`，再由 `x=M^{-1}y` 恢复原解；这里的 `M^{-1}` 由下面的 GMG 层次实现，而不是裸 GMRES/TFQMR。

### 5.2 GMG 预条件器详细配置

| 层级 | COMSOL 节点 | 关键设置 |
|---|---|---|
| 总体 | `i1/mg1` | 几何多重网格 `prefun=gmg`；V-cycle；5 层；`maxcoarsedof=5000`；并行粗化；组装矩阵；复用延拓算子 |
| 主变量块 | `i1/mg1` | 混合块 `[E, Sparam1, Sparam2]`，即 `Ex,Ey,Ez,S1x0,S2x0`；`matrixformat=auto` |
| 预平滑 1 | `i1/mg1/pr/soDef` | SOR：2 次，松弛系数 1，blocked，复用数据/模式 |
| 预平滑 2 | `i1/mg1/pr/va1` | Vanka（电场块）：1+1 次；stored local solve；`vankadirectmaxsize=150`；`vankatol=0.02`；restart 100；松弛 0.95 |
| 后平滑 1 | `i1/mg1/po/soDef` | SOR：2 次，松弛系数 1 |
| 后平滑 2 | `i1/mg1/po/sv1` | SOR Vector（电场块）：1+1 次，松弛系数 0.5 |
| 粗网格 | `i1/mg1/cs/dDef` | MUMPS 直接解；`itol=0.1`；主元阈值 0.01；扰动 `1e-8`；`preorder=nd` |

GMG 还启用了 `amgcompwise=on`、`loweramg=on`、`amgauto=3`、`strconn=0.01`、`strconnamgp=0.25`、`useaggressive=on`、常数零空间、标准插值和延拓截断 `0.1`。这些设置说明成功方案是“**Krylov 外迭代 + 几何多重网格 + 电场块平滑 + 粗层 MUMPS**”，不能简化为单独的 SOR、Vanka 或裸 Krylov 方法。

## 6. 同一基准系统上的直接法与成功迭代法对比

下表全部对应约 1,178,238 自由度、2.5 nm 自由四面体基准系统，且均为**仅零级衍射**口径。`ΔRT` 是相对直接法的 `abs(Δ(Rtotal+Ttotal))`；R/T/A 以百分数显示。所有条目均满足预先设定的 `1e-3` 成功阈值。

| 案例 | 外层方法与关键参数 | R / T / A (%) | `ΔRT` | 峰值内存 (GB) | 总时间 (s) | 结论 |
|---|---|---:|---:|---:|---:|---|
| `direct_mumps` | MUMPS 直接法 | 0.082297 / 61.672772 / 38.244931 | 0 | 22.989 | 282 | 直接参考解 |
| `gmres_gmg_default` | 右 GMRES，restart=300，GCRO-DR on | 0.082297 / 61.672815 / 38.244946 | `4.31e-7` | 13.376 | 232 | 稳定基线；本次运行快于直接法 |
| `gmres_gmg_restart100` | 右 GMRES，restart=100，GCRO-DR on | 0.082297 / 61.672773 / 38.244928 | `1.95e-8` | 11.699 | 417 | **推荐的 GMRES 折中方案** |
| `gmres_gmg_restart50` | 右 GMRES，restart=50，GCRO-DR on | 0.082297 / 61.672769 / 38.244930 | `3.20e-8` | 10.547 | 750 | GMRES 成功方案中内存最低，但较慢 |
| `gmres_gmg_left` | 左 GMRES，restart=300 | 0.082203 / 61.673963 / 38.245066 | `1.10e-5` | 11.994 | 152 | 最快，但相对误差明显大于右预条件版本 |
| `fgmres_gmg_default` | 右 FGMRES，restart=300 | 0.082297 / 61.672815 / 38.244946 | `4.31e-7` | 18.290 | 236 | 成功但内存偏高，未优于 GMRES |
| `tfqmr_gmg_default` | 右 TFQMR，GCRO-DR on | 0.082296 / 61.672783 / 38.244933 | `1.06e-7` | **8.992** | 869 | 筛选运行中内存最低 |
| `tfqmr_gmg_default`（保存模型复跑） | 右 TFQMR，默认 GMG | 0.082297 / 61.672768 / 38.244931 | `3.72e-8` | **9.010** | 800 | 已保存，见下节 |
| `gmres_pc_directpre` | GMRES + DirectPreconditioner | 0.082297 / 61.672772 / 38.244931 | `1.19e-13` | 23.110 | 337 | 精确但本质上回到直接分解，不节省内存 |

### 6.1 有原始日志可核对的内存细节

| 案例 | 物理 / 虚拟内存 (GB) | 线性迭代数 | 求解器阶段 / 总时间 (s) |
|---|---:|---:|---:|
| MUMPS 直接法 | 19.79 / 22.99 | 不适用 | 269 / 282 |
| GMRES + GMG，restart=100 | 11.11 / 11.70 | 544 | 404 / 417 |
| TFQMR + GMG（筛选运行） | 7.97 / 8.99 | 1241 | 856 / 869 |
| TFQMR + GMG（已保存模型复跑） | 8.05 / 9.01 | 1142 | 787 / 800 |

保存的最省内存模型为：`models/3D_benchmark_iterative_tfqmr_gmg_default.mph`。GMRES 基线保存模型为：`models/3D_benchmark_iterative_gmres_gmg_default.mph`。

## 7. 可执行建议

| 目标 | 建议配置 | 理由 |
|---|---|---|
| 最低内存、允许较长时间 | 右 TFQMR + 默认 GMG | 约 9 GB 峰值内存；结果与直接法的 `ΔRT` 为 `1e-7` 量级 |
| 自研 GMRES 的优先复现对象 | 右 GMRES + 默认 GMG，`restart=100` | 11.699 GB、417 s、`ΔRT=1.95e-8`，是较好的折中 |
| 进一步压低 GMRES 内存 | 右 GMRES + 默认 GMG，`restart=50` | 降至 10.547 GB，但时间增加到 750 s；不要同时关闭 GCRO-DR |
| 追求最快的本次记录 | 左 GMRES + GMG | 152 s，但 `ΔRT=1.10e-5`，不宜作为高精度参考解 |
| 需要直接参考 | MUMPS | 约 23 GB 峰值；对当前 32.38 GB 机器可运行，但余量有限 |
| 1.25 nm 细网格 | 建议至少 64 GB RAM | 虚拟内存已达 57.29 GB；32 GB 机器容易发生换页并显著拉长运行时间 |

不建议把独立 SOR、Vanka、SOR Vector、ILU 或裸 GMRES 当作主方案：已有测试表明它们没有形成可靠的成功解。成功的关键是完整的 GMG 层次（预/后平滑、延拓/粗化和粗层 MUMPS），而不是某个单独的平滑器。

## 8. 数据来源

- `results/iterative_solver_comparison.csv`、`results/iterative_solver_results.csv`
- `results/solver_settings_detail_zh.md`
- `results/3d_gmg_mesh_resource_rta_summary_zh.md`
- `results/inspect.stdout.txt`、`results/inspect_final_tfqmr.stdout.txt`、`results/inspect_geometry.stdout.txt`、`results/inspect_physics.stdout.txt`
- `logs/direct_mumps.log`、`logs/gmres_gmg_restart100.log`、`logs/tfqmr_gmg_default.log`
- COMSOL 官方说明：[Curl Elements](https://doc.comsol.com/6.3/doc/com.comsol.help.rf/rf_ug_radio_frequency.07.114.html)；[默认二阶 curl/Nédélec 单元的说明](https://doc.comsol.com/6.4/doc/com.comsol.help.models.rf.cavity_resonators/cavity_resonators.html)

上述来源均为本任务目录内已存在的模型检查、批处理或求解日志。带“估算”标签的数据（仅 5 nm 档）不可与已保存日志的精确值等同。
