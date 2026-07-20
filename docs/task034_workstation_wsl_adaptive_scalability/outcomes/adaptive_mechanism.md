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
refinement trend 和 observable error reduction 尚未完成，因此：

```text
genuine_fixed_p_h_adaptivity = not_yet_qualified
equal_accuracy_compression = not_yet_measured
robust_common_mesh_1_5_10_deg_s_p = not_yet_measured
p3_fixed_p_adaptive = not_yet_started
```

后续必须依次完成 p2/h3 三档 Hybrid M funnel、完整 observable vector 等误差 Gate、由真实场
驱动的 adaptive iteration、六参数 common mesh 复验，再允许计算压缩分类。任一 periodic、
residual、official R/T/A、observable 或资源 Gate 失败都保存为负结果，不放宽阈值。
