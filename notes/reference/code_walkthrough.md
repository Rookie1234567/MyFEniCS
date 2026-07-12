# 代码导览

## 普通工作流

| 文件 | 作用 |
|---|---|
| `src/main.py` | PyCharm 直接运行入口 |
| `src/runners/run_cases.py` | 2D CLI |
| `src/runners/run_3d_cases.py` | 3D staged CLI |
| `src/common/config_3d.py` | 3D 配置与材料常量 |
| `src/geometry/mesh_builder_3d.py` | 结构化3D网格 |
| `src/constraints/floquet_3d.py` | x/y Floquet MPC |
| `src/solvers/common_3d_forms.py` | Maxwell 变分形式 |
| `src/solvers/dtn_port_3d.py` | Stage4 DtN增广系统 |
| `src/postprocessing/rta_3d.py` | official R/T/A 与 A_volume |

## Task28 稳定求解组件

| 文件 | 公开职责 |
|---|---|
| `src/solvers/stage4_runtime.py` | 装配目标 p2 Stage4 系统，不选择求解器 |
| `src/solvers/condensed_dtn.py` | exact (F-C H^{-1}D)、RHS、转置作用与回代 |
| `src/solvers/physical_slab_two_level.py` | sparse fixed coarse、coarse认证、owner-computes slab smoother |
| `benchmarks/run_workstation_iterative.py` | 将稳定组件组合为显式 opt-in profile |

## Workstation 调用链

```text
assemble_target_stage4_system
  -> extract_petsc_condensed_blocks
  -> create_matrix_free_condensed_operator
  -> fixed Floquet hat basis (75D)
  -> SparseGalerkinTwoLevelPc
  -> DistributedPhysicalSlabSmoother
  -> FGMRES
  -> recover_petsc_auxiliary
  -> official modal R/T/A
```

`benchmarks` 不是普通默认入口。Task013-Task027 的失败研究 runner 保留在历史分支和任务文档，不在当前稳定源码树重复维护。
