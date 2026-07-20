# Task034 conforming graded-h 与 adaptive mechanism

## 当前结论

截至 clean source `70590b4f99a6c0e389ec69b7fcf10d1e421b4f7d`，第一层
`p2/h5` conforming graded-h mechanism 已在 WSL 原生环境以 MPI8 通过。该结论只证明：

- 六面体网格 conforming，未引入 hanging node；
- 材料面以及 bottom/top 的 10/110 nm matching trace 精确；
- x/y 周期 mate 共用完全相同的 trace topology；
- bottom、top 与 2D matching cross-section 的 x/y 网格身份一致；
- 已资格化的 p2 Floquet backend 能在该网格上生成稀疏 constraints；
- ordinary uniform default 未改变，新路径必须显式使用 graded 参数。

本阶段没有装配、分解或求解 Maxwell PDE，因此不声明等误差压缩，不声明真实 adaptive
loop 已通过，也不产生 official R/T/A。

## 实现边界

新实现位于 `src/geometry/task034_adaptive_mesh.py`，从 Task034 clean base 重新设计，未把
Task033 被排除的 research 文件提升为 production。网格采用显式非均匀 tensor-product
轴构造 conforming hexahedra；一次轴区间细分会沿另外两轴形成完整 strip，从结构上避免
hanging node。若被标记 cell 位于周期边界层，另一侧 mate 边界层同步细分。

`mechanism`、`conservative`、`balanced`、`aggressive` 是显式 opt-in profile；它们只控制
几何初始网格的远场 coarse factor 与材料面过渡带。几何 profile 不能冒充 adaptive。

## MPI8 p2/h5 机制证据

| 指标 | 结果 | 单位 | 数据身份 | evidence |
|---|---:|---|---|---|
| source | `70590b4f99a6c0e389ec69b7fcf10d1e421b4f7d` | SHA | measured | Case092 record |
| MPI size | 8 | ranks | measured | Case092 record |
| full plan | 11 × 3 × 18 | cells/axis | measured | `plan.mesh_cells` |
| full plan elements | 594 | hexahedra | measured | `plan.element_count` |
| min/max axis width | 3 / 10 | nm | measured | `plan.quality` |
| axis width ratio | 3.3333333333 | ratio | derived | `plan.quality` |
| bottom local mesh | 11 × 3 × 4 | cells/axis | measured | `local_meshes.bottom` |
| top local mesh | 11 × 3 × 4 | cells/axis | measured | `local_meshes.top` |
| local Nédélec DoF | 3916 each | DoF | measured | `local_meshes.*` |
| interface facets | 33 each | facets | measured | `local_meshes.*` |
| Floquet constraints | 484 each | rows | measured | `local_meshes.*.floquet` |
| max pairing/phase/fit error | 0 | absolute | measured | `local_meshes.*.floquet` |
| cross-section mixed DoF | 453 | DoF | measured | `cross_section` |
| mechanism wall time | 7.28619043 | s | measured | `runtime.wall_seconds` |

14 个 checker Gate 全部通过。构建器在 8 个 rank 上重新计算 plan hash，验证 rank ABI
身份、complex PETSc scalar、无 oversubscription、source before/after clean、稀疏 Floquet
constraint、无 full boundary gather、无 dense boundary square。独立 fresh-process 复跑没有
改变 Gate 结论。

轻量权威记录：

```text
benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/adaptive_mechanism_qualification.json
```

重型目录中的首次独立记录保留在：

```text
benchmarks/artifacts/cases/092/adaptive/p2_h5_mechanism_mpi8.json
```

## 场相关 indicator 与真实 adaptive 的 Gate

计划中的 complex lossy H(curl) cell indicator 为实验性组合：

$$
\eta_K^2 =
w_v \left|\frac{r_{K,\mathrm{volume}}}{s_v}\right|^2
+ w_c \left|\frac{j_{K,\mathrm{curl}}}{s_c}\right|^2
+ w_m \left|\frac{j_{K,\mathrm{material}}}{s_m}\right|^2
+ w_g \left|\frac{g_K}{s_g}\right|^2.
$$

其中 `volume_residual`、`curl_jump` 和 `material_interface` 是必需项，`goal_proxy` 是可选
实验项；尺度由全局数值 reduction 计算。当前已资格化的只是 finite/nonnegative 组合、
MPI-canonical cell identity、robust max aggregate 与 Dörfler marking/periodic mate 同步机制。
真实 FE solution 到各 cell component 的离散抽取、manufactured/analytic fixture、uniform
refinement trend 和 observable error reduction 尚未完成。随后在 clean source
`455128a2f777dbadd8e38430bbcd3a2ad10e5a7e` 上完成了 p2/h3 三档 graded-h 的正式
MPI8 Hybrid M80/M120/M160 funnel；这批计算用于决定是否解锁后续 heavy adaptive lane，
不能替代真正的 field-driven adaptive loop。

## p2/h3 measured graded-h compression 决策

三档候选均保持 exact material/matching planes、conforming hexahedra、同一 clean SHA、
同一 Full3D reference 与同一 watchdog。所有有效 shard 均通过资源、source、launch、
true residual、modal algebra、official R/T/A finite 和 volume energy closure Gate；未通过的
物理 Gate 原样保留。

| profile | M160 elements | local FE DoF sum | raw DoF ratio vs uniform | peak memory GiB | wall s | max Δ(R/T/A) vs Full3D | max middle E/H rel L2 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| conservative | 3978 | 43868 | 1.561x | 3.964 | 112.115 | 1.699e-2 | 0.306/0.315 | 不同误差 |
| balanced | 1885 | 21584 | 3.172x | 3.292 | 96.633 | 1.896e-1 | 1.673/1.672 | 不同误差 |
| aggressive | 600 | 7140 | 9.590x | 2.537 | 71.917 | 9.568e-1 | 1.079/1.078 | 不同误差，且 interface H 失败 |

这里的 raw ratio 仅表示 DoF 数量比。任务书规定只有全部同误差 Gate 通过后才允许把它称为
压缩倍数，因此三项 `qualified_compression_ratio` 均为 `null`，未给出 weak/useful/clear/
strong 分类。三档的 M120→M160 official R/T/A 变化均小于 `1e-5`，说明失败不是 modal
truncation；增加 modes 不能修复 graded spatial discretization error。

aggressive M80 首次调用在 `cross_section_eigen_assembly` 起点发生空 stdout 的瞬时 MPI/WSL
启动中断，未产生 solver record；失败 summary 被保留。相同 SHA、相同参数的独立 `retry1`
在 watchdog 下完整执行，后续汇总只使用该有效 shard，但不删除首次失败。

固定停止条件已经触发：所有 profile 都有关键 observable 超过等精度容差。因此没有启动
由这些候选派生的重型 field-driven adaptive、六参数 common-mesh 或 p3 adaptive PDE；这样
做是 fail-closed 结论，不是缺失结果，也没有放宽任何阈值。当前状态为：

```text
genuine_fixed_p_h_adaptivity = not_yet_qualified
equal_accuracy_compression = controlled_negative
robust_common_mesh_1_5_10_deg_s_p = stopped_before_heavy_run
p3_fixed_p_adaptive = stopped_before_heavy_run
```

结构化证据：

```text
docs/task034_workstation_wsl_adaptive_scalability/outcomes/adaptive_compression.csv
docs/task034_workstation_wsl_adaptive_scalability/outcomes/adaptive_compression.json
benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/adaptive_summary.json
```
