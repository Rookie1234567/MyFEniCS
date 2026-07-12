# 代码导览

本文解释当前代码如何从参数走到可信结果。任务证据在 `docs/taskXXX_*`，这里不重复历史试验日志。

## 1. 2D 调用链

```text
src.runners.run_cases
  -> SimulationConfig + CLI 显式覆盖
  -> geometry.mesh_builder
  -> material assignment
  -> manual / dolfinx_mpc Floquet constraints
  -> TM Nedelec 或 TE scalar variational form
  -> scattered PML / Robin port / nonlocal DtN
  -> PETSc direct solve
  -> diffraction orders + total R/T/A + volume absorption
  -> results/ 或显式 benchmark artifact root
```

| 阶段 | 主要对象 | 生命周期 |
|---|---|---|
| 配置 | `SimulationConfig` | 每个 case 一份，CLI 只覆盖非空参数 |
| 网格 | DOLFINx mesh、cell/facet tags | 求解和后处理共享 |
| 场空间 | TM Nedelec 或 TE scalar space | 与约束、矩阵共同存活 |
| Floquet | manual map 或 `dolfinx_mpc.MultiPointConstraint` | 装配前建立，解后反映射 |
| DtN | explicit dense trace 或 auxiliary modal unknowns | port total-field 路径 |
| 输出 | summary、VTU/PVD、RTA JSON | rank0 写元数据，场按 MPI 规则写出 |

`run_cases` 的默认组合用于探索，不是快速 smoke。2D nonlocal DtN 的已验证组合是 `manual + port_total + auxiliary DtN`。

## 2. 3D 普通调用链

```text
src.runners.run_3d_cases
  -> SimulationConfig3D
  -> Stage1 / 2A / 2B / 2C / 4 dispatch
  -> mesh_builder_3d + material tags
  -> Nedelec H(curl) space
  -> double Floquet MPC in x/y
  -> common_3d_forms
  -> auxiliary DtN augmented system [F C; D H]
  -> ordinary PETSc/MUMPS direct solve
  -> FE field assignment + auxiliary modal amplitudes
  -> official DtN R/T + A_volume
  -> run_summary + mesh/field outputs
```

Stage1 只验证空气盒传播；Stage2A/B/C 分别逐步验证 Floquet、PML 和 Fresnel；Stage4 才组合真实材料、block grating、DtN port 和 R/T/A。不要用后阶段失败反推前阶段基础设施错误，也不要把前阶段 smoke 当成 Stage4 物理解。

## 3. Stage4 增广系统

线性系统按 FE 与 modal auxiliary 未知量分块：

```text
[F C] [u] = [f]
[D H] [a]   [g]
```

`F` 是 Floquet 约束后的 H(curl) FE 块，`H` 是很小的 modal block，`C/D` 连接端口模态与 FE trace。ordinary 路径直接解完整增广系统；Task28 迭代路径做精确静态凝聚：

```text
A_c = F - C H^{-1} D
b_c = f - C H^{-1} g
a   = H^{-1}(g-Du)
```

`condensed_dtn.py` 同时提供 dense algebra reference、PETSc block extraction、显式 condensed matrix、matrix-free action、转置/Hermitian action、RHS 和 back-substitution。它不依赖几何。

## 4. Task28 迭代调用链

```text
benchmarks.run_workstation_iterative
  -> load workstation_p2.json
  -> stage4_runtime.assemble_target_stage4_system
  -> PetscCondensedBlocks
  -> CondensedDtnMatContext
  -> 25 z nodes x 3 components = 75 fixed coarse vectors
  -> true-action Galerkin coarse matrix
  -> 16 complete overlapping physical z slabs
  -> balanced owner assignment
  -> owner-computes shifted-F ILU(1)
  -> two fixed inner GMRES steps (sm2)
  -> right-preconditioned FGMRES(100)
  -> condensed residual
  -> auxiliary back-substitution + full augmented residual
  -> official modal R/T + A_volume
  -> artifact + lightweight record
```

### 4.1 Coarse 数据

每个 coarse vector 以 `SparseCoarseVector(indices, values)` 压缩保存。`SparseGalerkinTwoLevelPc` 用真实 matrix-free action 构造 Galerkin coarse matrix；fresh 构造的 `coarse_action_relative_error` 为 `null/not_applicable`，只有加载缓存 coarse 时才做独立随机真作用认证并产生误差值。

### 4.2 Physical slabs

每个 rank 先根据本地 cells 生成 z slab DOF 片段，再由 `gather_global_subdomain_indices` 合并成完整全局子域。`balanced_subdomain_owners` 根据行数分配 owner；每个完整 slab 只在一个 owner 上提取和 ILU 分解。forward scatter 收集 RHS，reverse ADD scatter 累加重叠修正。

### 4.3 sm2

`DistributedPhysicalSlabSmoother._apply_once` 是一次 additive Schwarz。`smoother_iterations=2` 时，外面再建立一个固定两步、无 norm test 的 inner GMRES，以原算子 action 和一次 Schwarz 作为 PC。该分支现有显式小矩阵参考、sm1/sm2 区别、重复 apply、MPI1/MPI4 行为、action requirement 与 destroy 测试。

## 5. 结果可信度链

| 顺序 | 检查 | 不通过时 |
|---:|---|---|
| 1 | PETSc converged reason > 0 | 标记失败 |
| 2 | reported residual <= 1e-6 | 不做 official RTA |
| 3 | explicit condensed residual <= 1e-6 | 不做 official RTA |
| 4 | full augmented residual <= 1e-6 | 不做 official RTA |
| 5 | 三残差口径一致 | 调查 operator/monitor/back-substitution |
| 6 | official R/T/A 与能量闭合 | 才形成物理结果 |
| 7 | all-rank total peak RSS | 才形成工作站容量结论 |

## 6. 输出边界

`run_cases` 和 `run_3d_cases` 的 `--results-root` 默认为空，因此 ordinary 路径仍写仓库 `results/`。benchmark scripts 必须显式传入 `benchmarks/artifacts/...`。轻量 JSON/CSV 写 `benchmarks/records/`，checker 不读取重型场文件即可复核 Gate。

## 7. 内部依赖边界

`stage4_runtime.py` 目前仍调用 `common_3d_forms` 与 direct setup 中的少量下划线内部函数；benchmark 后处理也通过 `dtn_port_3d.py` 的既有内部函数恢复场和功率。这些依赖已由 import/full-suite/smoke regression 保护，但尚未全部升级为公共 API。普通模块重命名这些函数前必须先迁移稳定 facade，这是 Task28 保留的非阻断技术债。

## 8. 不在当前稳定树的路线

sampled-Schur、cached-Q、spectral/GenEO、HPDDM、FE-only AMS/HX 和 serial SciPy SPILU 保留在历史任务分支与任务证据中。它们用于解释失败边界，不作为普通用户选项，也不应重新复制到 production 模块。
