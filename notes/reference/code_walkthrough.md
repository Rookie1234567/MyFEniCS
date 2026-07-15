# 代码导读索引

本索引解释当前代码如何把参数、方程、约束、求解器和结果串起来。运行方法见 [`../quick_start/README.md`](../quick_start/README.md)，推导见 [`../theory/README.md`](../theory/README.md)，数值证据见 [`../../benchmarks/cases/README.md`](../../benchmarks/cases/README.md)。

Task28 V3 将 01、11、12、20-23、30-33 定为核心源码级章节：每篇都给出真实签名、对象 shape/ownership、公式映射、调用顺序、测试和限制，并由 `test_26_documentation_contract.py` 防止退化为函数摘要。Task29 direct telemetry 已同步到第 30、40、50 章。Task30 的 symmetric pre/post、local shift、factor-only storage、runner flags、H(curl) transfer/Galerkin 测试和 Case060 边界已同步到第 32、33、50 章；p/h coarse 的代数成功与 solver 负结果被明确分开。Task31 的 PC certificate、factor fingerprint、public MPC matrix-free fine action、external simultaneous RSS/watchdog、compact lifecycle 与 Case070 合同也已同步到第 32、33、50 章。Task32 Phase 1 的显式 full-3D 参考面导出、单侧接口取迹和小数据通信边界见第 41 章；Phase 2 的匹配截面、`N1curl x Lagrange` QEP、双 Floquet 降维与分布式 PEP 见第 42 章；Phase 3 的 Poynting 分类、伴随 QEP 双正交、近简并 block 和 overlap tracking 见第 43 章；Phase 4 的稳定 two-port 传播见第 44 章；Phase 5 的匹配 Nedelec 迹、法向和 left/right 投影见第 45 章；Phase 6a/6b 的上下局部 FEM 与单侧外端口 DtN 见第 46 章，Phase 6c 的内部模态稀疏块、牵引和 MPI 路由见第 47 章，Phase 6d 的 rank-major 单体 AIJ 与 MUMPS algebra Gate 见第 48 章。

| 顺序 | 文档 | 内容 |
|---:|---|---|
| 0 | [`code_walkthrough/00_repository_architecture.md`](code_walkthrough/00_repository_architecture.md) | 全目录和文件责任、正式/诊断/历史边界 |
| 1 | [`code_walkthrough/01_main_and_runner_dispatch.md`](code_walkthrough/01_main_and_runner_dispatch.md) | main preset、argparse、case dispatch |
| 2 | [`code_walkthrough/10_2d_config_mesh_material.md`](code_walkthrough/10_2d_config_mesh_material.md) | 2D config、网格、tag、材料 |
| 3 | [`code_walkthrough/11_2d_floquet_pml_port_forms.md`](code_walkthrough/11_2d_floquet_pml_port_forms.md) | TM/TE、Floquet、PML、Robin |
| 4 | [`code_walkthrough/12_2d_dtn_and_rta_postprocess.md`](code_walkthrough/12_2d_dtn_and_rta_postprocess.md) | 2D DtN、场与功率后处理 |
| 5 | [`code_walkthrough/20_3d_staged_architecture.md`](code_walkthrough/20_3d_staged_architecture.md) | Stage 1/2/4 包装与共享 flow |
| 6 | [`code_walkthrough/21_3d_floquet_and_pml.md`](code_walkthrough/21_3d_floquet_and_pml.md) | 3D 网格、MPC、PML |
| 7 | [`code_walkthrough/22_3d_dtn_augmented_system.md`](code_walkthrough/22_3d_dtn_augmented_system.md) | 模态、表面向量、增广矩阵 |
| 8 | [`code_walkthrough/23_3d_rta_and_field_reconstruction.md`](code_walkthrough/23_3d_rta_and_field_reconstruction.md) | total field、official RTA、ParaView |
| 9 | [`code_walkthrough/30_direct_solver_profiles.md`](code_walkthrough/30_direct_solver_profiles.md) | PETSc direct/OOC/BLR 与清理 |
| 10 | [`code_walkthrough/31_exact_condensation.md`](code_walkthrough/31_exact_condensation.md) | Schur block API 和生命周期 |
| 11 | [`code_walkthrough/32_physical_slab_two_level_pc.md`](code_walkthrough/32_physical_slab_two_level_pc.md) | sparse coarse、slab owner、sm2 |
| 12 | [`code_walkthrough/33_workstation_fgmres_runtime.md`](code_walkthrough/33_workstation_fgmres_runtime.md) | benchmark production runner 数据流 |
| 13 | [`code_walkthrough/40_output_schema_and_visualization.md`](code_walkthrough/40_output_schema_and_visualization.md) | JSON/CSV/VTU、RSS、字段口径 |
| 14 | [`code_walkthrough/41_task032_full3d_reference_export.md`](code_walkthrough/41_task032_full3d_reference_export.md) | Task032 参考平面、接口取迹、复杂场 NPZ |
| 15 | [`code_walkthrough/42_task032_cross_section_qep.md`](code_walkthrough/42_task032_cross_section_qep.md) | Task032 匹配截面、混合 QEP、双 Floquet 与分布式 PEP |
| 16 | [`code_walkthrough/43_task032_mode_classification.md`](code_walkthrough/43_task032_mode_classification.md) | Task032 Poynting 分类、伴随 QEP、双正交和 mode tracking |
| 17 | [`code_walkthrough/44_task032_stable_propagation.md`](code_walkthrough/44_task032_stable_propagation.md) | Task032 two-port 稳定传播、被动分支和 composition |
| 18 | [`code_walkthrough/45_task032_modal_trace_projection.md`](code_walkthrough/45_task032_modal_trace_projection.md) | Task032 匹配 Nedelec 接口迹、top/bottom 法向、left/right 投影与近简并子空间 |
| 19 | [`code_walkthrough/46_task032_hybrid_local_mesh.md`](code_walkthrough/46_task032_hybrid_local_mesh.md) | Task032 上下局部 FEM 网格、显式法向、p2 Floquet ownership 与单侧外端口 DtN |
| 20 | [`code_walkthrough/47_task032_hybrid_internal_modes.md`](code_walkthrough/47_task032_hybrid_internal_modes.md) | Task032 内部模态投影/牵引稀疏块、稳定传播与 MPI 点值路由 |
| 21 | [`code_walkthrough/48_task032_hybrid_augmented_direct.md`](code_walkthrough/48_task032_hybrid_augmented_direct.md) | Task032 rank-major 单体增广 AIJ、传播消元、MUMPS 与真残差 |
| 22 | [`code_walkthrough/50_tests_and_benchmark_contract.md`](code_walkthrough/50_tests_and_benchmark_contract.md) | test 编号、case contract、checker Gate |

## 一句话调用链

```text
main preset -> 2D/3D runner -> config -> mesh/tags -> function space
-> Floquet constraints -> weak form -> DtN/PML/open boundary
-> direct or explicit MPI4 iterative solve -> field reconstruction
-> residual gates -> official R/T/A -> results + benchmark record
```

`src/solvers/*_old.py` 和 `src/runners/*_old.py` 不在这条链上；保留它们只为历史对照。下划线函数若被 `stage4_runtime` 调用，会在相应章节明确列为“内部依赖”，不能仅凭下划线误判为未使用。
