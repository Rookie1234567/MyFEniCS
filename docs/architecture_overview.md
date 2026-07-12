# 架构概览

本文是顶层摘要。逐文件、逐类/函数、对象所有权和 equation-to-code 映射见 [`../notes/reference/code_walkthrough.md`](../notes/reference/code_walkthrough.md)。

## 分层结构

| 层 | 目录 | 职责 | 不负责 |
|---|---|---|---|
| 配置 | `src/common` | 2D/3D 物理与数值参数 | 求解策略选择 |
| 几何 | `src/geometry` | mesh、cell/facet tags | 功率解释 |
| 约束 | `src/constraints` | x/y Floquet MPC | DtN 模态消元 |
| 变分形式 | `src/solvers/common_*_forms.py` | Maxwell/PML/material forms | benchmark policy |
| 端口 | `src/solvers/dtn_port_3d.py` | auxiliary DtN 与 modal power | workstation PC |
| 稳定代数 | `condensed_dtn.py` | exact condensation 与 back-sub | 几何 |
| 稳定 PC | `physical_slab_two_level.py` | fixed coarse、physical slabs、sm2 | 参数 qualification |
| Stage4 facade | `stage4_runtime.py` | 目标系统装配 | ordinary 默认切换 |
| ordinary runner | `src/runners` | 用户 staged direct workflow | 自动使用研究 PC |
| benchmark | `benchmarks` | opt-in profile、records、Gate | 普通结果目录 |
| 后处理 | `src/postprocessing` | official/diagnostic power 与场输出 | 伪造收敛 |

## 普通与 benchmark 边界

```text
ordinary CLI --results-root omitted -> results/
benchmark scripts --results-root set -> benchmarks/artifacts/
canonical compact evidence           -> benchmarks/records/
task/review/response evidence         -> docs/taskXXX_*/
theory and explanation                -> notes/
```

`--results-root` 是显式输出位置覆盖，不改变 ordinary 默认求解器、配置或目录。

## Stage4 迭代数据流

```text
workstation_p2.json
  -> validated CLI overrides + qualification flag
  -> mesh + N1curl p2 + x/y Floquet MPC
  -> augmented [F C; D H]
  -> exact matrix-free A_c = F-C H^-1D
  -> fixed 75D true-action Galerkin coarse
  -> complete overlapping z slabs
  -> balanced owner-computes shifted-F ILU1
  -> sm2 inner GMRES
  -> right FGMRES(100)
  -> reported + condensed + full residual
  -> auxiliary reconstruction
  -> official modal R/T + A_volume
  -> artifact + record + automatic Gate
```

## 生命周期与所有权

| 资源 | 创建者 | 销毁者 |
|---|---|---|
| augmented PETSc matrix/vector | `stage4_runtime` | benchmark 在 block extraction 后释放原 matrix，结束时释放 blocks |
| matrix-free shell operator | `condensed_dtn` | benchmark runner |
| coarse basis vectors | benchmark builder | 压缩后立即销毁 PETSc 临时向量 |
| local slab submatrices/KSP | `DistributedPhysicalSlabSmoother` | `destroy()`，允许重复调用 |
| outer KSP/solution | benchmark runner | 正常结束显式销毁 |
| field/mesh output | postprocessing | 文件系统，由用户清理 ignored artifacts |

异常路径的完整 context-manager 化仍是 P1 技术债；正式 runner 的 failure record 也应继续增强。目前正常路径和测试生命周期已覆盖。

## 依赖边界

`stage4_runtime.py` 仍依赖 `_build_variational_forms`、`_create_nedelec_space` 和 direct LU option helper；benchmark 后处理仍调用 `dtn_port_3d.py` 的若干内部函数。它们在当前树内由 full suite、import 和 smoke 保护，但不是承诺稳定的跨包公共 API。后续重构必须先建立公开 facade 并迁移 benchmark，不能直接重命名。

Task013-Task025 的 sampled-Schur、cached-Q、AMS/HX 原型和 Task027 的 spectral/GenEO/HPDDM 路线只保留在研究分支/文档，不进入 ordinary API。
