# 3D 分阶段代码架构

## 包装器

六个 `solve_maxwell_3d_stage_*.py` 文件只做 stage guard 和调用共享核心：

| wrapper | 接受 `stage_case` |
|---|---|
| Stage 1 | `stage1_airbox` |
| Stage 2A | `floquet_airbox` |
| Stage 2B | `pml_airbox` |
| Stage 2C | `fresnel_interface` |
| Stage 4A | `stage4_flat_layer_sanity` |
| Stage 4B | `stage4_block_grating` |

错误 stage 在建网格前抛出，防止入口名与真实物理路径分离。

## `common_3d_case_flow.run_prepared_3d_case_flow`

主生命周期：

```text
log/profile -> mesh -> Nedelec V -> background/reference field
-> Floquet MPC + z boundary BC -> weak form
-> standard direct or Stage4 DtN augmented solve
-> field reconstruction -> residual/status -> postprocess/RTA
-> JSON/log/progress -> destroy PETSc/OOC cleanup
```

辅助函数分组：

| 函数 | 责任 |
|---|---|
| `_build_floquet_and_boundary_conditions` | 根据 stage 建 MPC/Dirichlet |
| `_solve_standard_linear_problem` | 非 DtN 普通 PETSc direct |
| `_assemble_unconstrained_matrix_stats` | 可选 pre-MPC 诊断，增加内存 |
| `_merge_volume_closure_into_dtn_port_outputs` | official port + A_volume |
| failure summary helpers | 即使失败也写阶段、PETSc 诊断和资源 |

## 共享模块

`common_3d_forms` 决定方程；`common_3d_fields` 决定 total/background/correction 场；`common_3d_solve` 决定空间与 direct；`common_3d_postprocess` 调用场/RTA；`common_3d_utils` 管理计时、RSS、progress、输出。

## 内部 API 债务

`stage4_runtime` 复用若干下划线函数组装 target 系统。这些依赖有测试保护但仍是内部接口；改名时应先提供稳定 facade，不能只改 benchmark import。

Stage 理论和资格见 `theory/3d_stages_and_validation_ladder.md`。
