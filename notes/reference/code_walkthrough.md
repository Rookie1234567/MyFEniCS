## 2026-07-01 更新：MUMPS OOC 和 progress 日志阅读路径

如果你现在关心“h=1.5 为什么 LU 跑不下去”，按这个顺序读：

```text
1. src/runners/run_3d_cases.py
   看 --petsc-direct-solver-profile、--matrix-diagnostics-assemble-only
   以及开头打印的 3D case output directory。

2. src/solvers/common_3d_utils.py
   看 _write_progress_event。progress_3d.jsonl 就是在这里写的。

3. src/solvers/common_3d_solve.py
   看 _prepare_direct_lu_options_for_comm：
   - mumps_ooc
   - mumps_ooc_seq_analysis
   - mumps_ooc_parallel_analysis
   - mumps_ooc_requested_legacy
   也看 _prepare_mumps_ooc_runtime，它把 OOC 文件放到 case/mumps_ooc_files。

4. src/solvers/dtn_port_3d.py
   zero_order DtN 的 assemble-only 和 solve begin/end progress 在这里。

5. src/solvers/common_3d_case_flow.py
   看 run_summary.json 如何记录 matrix_stats、DirectSolveFailure 和 MUMPS OOC 状态。

6. src/studies/run_3d_matrix_scale.py
   看 --mpi-procs-list、--solver-profiles、--assemble-only 如何生成 CSV。
```

最新诊断结论写在：

```text
notes/test/3d_matrix_solver_diagnostics.md
```

## 2026-07-01 更新：矩阵和求解器诊断阅读路径

如果你现在关心“为什么 90 万自由度就内存爆掉”，按这个顺序读：

```text
1. src/runners/run_3d_cases.py
   看 --petsc-direct-solver-profile、--petsc-ksp-view、--petsc-log-view、
   --matrix-diagnostics-assemble-unconstrained 以及尾随 PETSc 参数如何进入 config。

2. src/common/config_3d.py
   看 petsc_direct_solver_profile、petsc_extra_options、
   matrix_diagnostics_assemble_unconstrained 这些诊断字段。

3. src/solvers/common_3d_solve.py
   看 _prepare_direct_lu_options_for_comm 和 _petsc_matrix_stats。
   这里决定 default / mumps_ooc / mkl_pardiso 等 PETSc 选项，并读取 Mat.getInfo()。

4. src/solvers/common_3d_case_flow.py
   看 unconstrained_matrix_stats、constraint_matrix_transform、
   matrix_stats 如何写入 run_summary.json。

5. src/solvers/dtn_port_3d.py
   看 dtn_base_matrix_stats、dtn_augmented_matrix_stats_after_finalize、
   dtn_auxiliary_block_stats。这里用于判断 DtN auxiliary 是否变成 dense block。

6. src/studies/run_3d_matrix_scale.py
   批量跑 MeshTargetSize = 20/15/12/10/8，并生成 matrix_scale.csv。
```

关键判断字段：

```text
matrix_stats.matrix_average_nnz_per_row
matrix_stats.matrix_nnz_used
matrix_stats.matrix_nnz_allocated
constraint_matrix_transform.explicit_chac_constructed
constraint_matrix_transform.dtn_augmented_to_base_nnz_ratio
stage4_dtn_auxiliary_block_stats.dtn_auxiliary_block_is_dense
```

## 2026-07-01 更新：Stage 4B p=2 开放后的阅读路径

如果你现在研究真实 3D grating 的二阶单元流程，按这个顺序读：

```text
1. src/runners/run_3d_cases.py
   看 _stage_defaults("stage4_block_grating") 和 CLI 参数如何生成 SimulationConfig3D。

2. src/solvers/solve_maxwell_3d_stage_4b_block_grating.py
   这是 Stage 4B 的清晰入口，只接受 stage_case="stage4_block_grating"。

3. src/solvers/common_3d_case_flow.py
   看 run_prepared_3d_case_flow 如何串起 mesh、Nedelec space、Floquet、DtN port、postprocess。

4. src/geometry/mesh_builder_3d.py
   看 _validate_stage4_hexa_geometry：Stage 4 现在允许 degree=1/2，p>=3 仍拒绝。

5. src/constraints/floquet_3d.py
   p=2 重点看 _build_double_floquet_mpc_p2_trace：
   - edge dofs 显式配对
   - face-interior dofs 用每个周期 face 的 4x4 local Nedelec moment fit
   - summary 新增 floquet_num_face_transform_fits 和 floquet_max_face_transform_fit_residual

6. src/solvers/dtn_port_3d.py
   看 Stage 4 DtN total-field port。zero_order 是低成本 sanity；auto_propagating 是正式多衍射级端口。

7. src/postprocessing/postprocess_3d.py
   看 ParaView 字段和 field component L2 diagnostics。
```

当前边界：

```text
p=1 Stage4B: 保持旧 edge dof Floquet 路径
p=2 Stage4B: 已开放 topological_trace_p2
p>=3 Stage4B: 仍未开放
tetra Stage4B: 仍未开放
```

对应验证记录在：

```text
notes/test/3d_high_order_floquet_validation_report.md
notes/quick_start/stage4_3d_block_grating_usage_guide.md
```

## 2026-07-01 更新：p=2 Floquet face-interior MPI 修复后的阅读路径

如果你现在研究二阶 3D Floquet，重点看这一条新路径：

```text
1. src/constraints/floquet_3d.py
   build_double_floquet_mpc(...)
     p=2 -> _build_double_floquet_mpc_p2_trace(...)

2. _build_topological_trace_context_p2(...)
   收集周期 edge records / face records。
   同时调用 _build_p2_trace_fit_values_by_global(...)，为 face-interior dof 准备局部 moment fitting 样本。

3. _build_p2_edge_constraints_for_kind(...)
   edge dof 仍然是显式拓扑配对，corner edge 只约束一次。

4. _build_p2_face_constraints_for_kind(...)
   face-interior dof 不再手写 Basix quadrilateral permutation。
   现在进入 _face_transform_fit_p2(...)，每个周期 face pair 解一个 4x4 局部 Nedelec moment transform。

5. src/test/diagnose_p2_mpc_constraints.py
   MPI 诊断脚本，用解析周期场检查 slave/master 系数残差。
```

这个修复的核心原则：face dof 不是点值，所以不能按点坐标硬配；但也不能恢复整张侧面的 dense probe/pinv。当前做法只在每个 face block 上做常数规模 moment fit，因此复杂度仍是 `O(N_trace)`。

## 2026-06-30 更新：p=2 Stage 4A flat-layer sanity 阅读路径

如果你现在研究二阶 Floquet 接入 Stage 4A，请按这个顺序读：

```text
1. src/runners/run_3d_cases.py
   --stage-case stage4_flat_layer_sanity 进入 Stage 4A，默认仍使用 DtN total-field port。

2. src/solvers/solve_maxwell_3d_stage_4a_flat_layer_sanity.py
   这是无光栅平层 sanity 的真实入口，只接受 stage4_flat_layer_sanity。

3. src/constraints/floquet_3d.py
   p=2 走 _build_double_floquet_mpc_p2_trace(...)，同时约束 edge dof 和 face-interior trace dof。

4. src/solvers/common_3d_case_flow.py
   只有在需要追踪 DtN auxiliary port 装配和 R/T summary 时再进入。
```

当前边界：Stage 4A p=2 已开放；Stage 4B block grating p=2 仍会明确报 `NotImplementedError`，避免真实 grating 在 flat-layer sanity 通过前提前混入高阶路径。

## 2026-06-30 更新：p=2 Stage 2B/2C Floquet 阅读路径

如果你现在研究二阶 3D Floquet 与 Stage 2B/2C 的组合，建议按这个顺序读：

```text
1. src/runners/run_3d_cases.py
   看 --stage-case pml_airbox / fresnel_interface 如何进入对应 Stage 2 配置。

2. src/common/config_3d.py
   看 nedelec_degree=2、floquet_constraint_mode="auto"、use_floquet_xy=True。

3. src/constraints/floquet_3d.py
   看 build_double_floquet_mpc(...) 如何分流：
     p=1 -> _build_double_floquet_mpc_p1_edges(...)
     p=2 -> _build_double_floquet_mpc_p2_trace(...)
   p=2 的 edge dof 和 face-interior dof 都在这里显式拓扑配对。

4. src/solvers/solve_maxwell_3d_stage_2_no_grating.py
   看 Stage 2A/2B/2C 怎样调用公共有限元流程。

5. src/solvers/solve_maxwell_3d_common.py
   只在需要追踪装配、PML/Fresnel 诊断字段、summary 字段时再进入。
```

p=2 的关键点：全局约束只由 owning rank 发出；出现在 owned cell 上的 ghost slave 会作为本 rank 的 local MPC map 参与装配。这样既避免重复 global emission，又保留 dolfinx_mpc 所需的本地单元装配信息。

## 2026-06-30 更新：3D p=2 高阶 Floquet trace 阅读路径

如果你现在研究二阶 3D Floquet 边界，建议按这个顺序读：

```text
1. src/common/config_3d.py
   看 floquet_constraint_mode：
     auto
     topological_edges_p1
     topological_trace_p2

2. src/constraints/floquet_3d.py
   核心入口：
     build_double_floquet_mpc(...)
       p=1 -> topological_edges_p1
       p=2 -> _build_double_floquet_mpc_p2_trace(...)

   p=2 关键函数：
     _build_topological_trace_context_p2(...)
       收集周期边界上的 edge records 和 face records。

     _build_p2_edge_constraints_for_kind(...)
       处理 edge dof，包含 x/y/corner 三类；corner 只约束一次。

     _build_p2_face_constraints_for_kind(...)
       处理 face-interior tangential dof，只属于 x-face 或 y-face。

     _face_transform_fit_p2(...)
       使用局部 Nedelec moment fit 处理 p=2 face-interior dof。

3. src/solvers/common_3d_case_flow.py
   看 summary 字段：
     floquet_num_edge_constraints
     floquet_num_face_constraints
     floquet_num_slave_faces
     floquet_max_face_midpoint_pairing_error

4. src/test/test_17_3d_high_order_floquet_trace.py
   看 p=2 dof layout、mode 分流和 PDE smoke 测试。
```

正式验证记录见：

```text
notes/test/3d_high_order_floquet_validation_report.md
```

## 2026-06-29 更新：3D 按案例求解器阅读路径

现在 3D 不再从一个巨大的 `solve_maxwell_3d_common.py` 开始读。建议按你正在研究的案例直接进入对应文件：

```text
1. src/main.py
   PyCharm 直接运行时先看 SIMULATION_DIMENSION 和 Stage4GratingInputs3D / 3D settings。

2. src/runners/run_3d_cases.py
   这是新的唯一 3D 单案例 runner。
   stage_case 只允许：
     stage1_airbox
     floquet_airbox
     pml_airbox
     fresnel_interface
     stage4_flat_layer_sanity
     stage4_block_grating
   --case 只允许 normal / oblique。

3. 按案例选择 solver：
   Stage 1:
     src/solvers/solve_maxwell_3d_stage_1_airbox.py
   Stage 2A:
     src/solvers/solve_maxwell_3d_stage_2a_floquet_airbox.py
   Stage 2B:
     src/solvers/solve_maxwell_3d_stage_2b_pml_airbox.py
   Stage 2C:
     src/solvers/solve_maxwell_3d_stage_2c_fresnel_interface.py
   Stage 4A:
     src/solvers/solve_maxwell_3d_stage_4a_flat_layer_sanity.py
   Stage 4B:
     src/solvers/solve_maxwell_3d_stage_4b_block_grating.py

4. 再按需要读公共积木：
   src/solvers/common_3d_utils.py
     计时、日志、summary/json 写出。
   src/solvers/common_3d_solve.py
     Nedelec 空间、直接求解器、矩阵和残差诊断。
   src/solvers/common_3d_fields.py
     入射场、背景场、场叠加、采样。
   src/solvers/common_3d_forms.py
     curl-curl 弱式、PML 弱式、RHS source norm。
   src/solvers/common_3d_postprocess.py
     Floquet/PML/Fresnel/Stage-4 指标。
   src/solvers/common_3d_case_flow.py
     每个案例共同使用的 FEM 流程积木；它不再按 stage_case 做大分流，而是由各案例文件传入明确的 formulation。
```

历史文件只作为参考保留：

```text
src/solvers/solve_maxwell_3d_common_old.py
src/solvers/solve_airbox_maxwell_3d_old.py
src/solvers/solve_maxwell_3d_stage_2_no_grating_old.py
src/solvers/solve_maxwell_3d_stage_4_grating_old.py
src/runners/run_3d_airbox_old.py
```

本轮重构的验证记录见：

```text
notes/test/3d_refactor_baseline_report.md
notes/test/3d_refactor_validation_report.md
```

## 2026-06-29 更新：2D EUV 光栅 DtN 代码阅读路径

如果本轮主要研究 2D EUV 矩形光栅，建议按下面顺序读：

```text
1. src/main.py
   先看 SIMULATION_DIMENSION = "2d"。
   再看 Inputs2D / EUVGratingInputs2D：
     period_x = 100 nm
     air_height = 100 nm
     substrate_thickness = 50 nm
     grating_width = 50 nm
     grating_height = 50 nm
     lambda0 = 13.5 nm
     n_substrate = 1.1
     n_grating = 1.2
     mesh_cell_shape = "triangle" / "quadrilateral"
     mesh_lock_near_field_template = True

2. src/runners/run_cases.py
   看 2D CLI 参数如何覆盖 SimulationConfig：
     --period-x
     --air-height
     --substrate-thickness
     --grating-width
     --grating-height
     --lambda0
     --n-substrate
     --n-grating
     --mesh-cell-shape
     --lock-near-field-template

3. src/common/config.py
   看 SimulationConfig 的 2D 几何属性：
     x_min/x_max
     substrate_y_min/substrate_y_max
     grating_x_min/grating_x_max
     grating_y_min/grating_y_max
   这里统一约定所有长度、波长、网格尺寸都是 nm。

4. src/geometry/mesh_builder.py
   看 mesh_axis_coordinates_2d(...)：
     生成结构化 x/y 坐标轴。
   看 material_tag_for_rect_2d(...)：
     不用 midpoint 近似，按分块矩形是否完全落入材料区域来打 tag。
   看 build_mesh(...)：
     triangle 保持历史 transfinite 三角网格；
     quadrilateral 对每个结构化面 setRecombine。

5. src/solvers/solve_port_maxwell.py
   这是 TM DtN 主线：
     run_port_case(...)
     _select_dtn_port_modes(...)
     _add_fourier_port_operators_auxiliary(...)
     compute_dtn_auxiliary_power_metrics(...)
   正式 R/T 优先看 dtn_auxiliary_power_metrics。

6. src/postprocessing/near_field_2d.py
   看 near_field_regions_2d(...) 和 near_field_reference_areas_2d(...)。
   这里定义：
     grating
     air_near
     sub_near

7. src/postprocessing/power_metrics.py
   看 compute_near_field_integrals(...)。
   这里实际装配：
     I_grating  = ∫_grating |E|^2 dΩ
     I_air_near = ∫_air_near |E|^2 dΩ
     I_sub_near = ∫_sub_near |E|^2 dΩ

8. src/studies/run_2d_euv_validation.py
   这是批量研究入口：
     method_compare
     mesh_convergence
     air_scan
     substrate_scan
     combined_scan

9. src/test/test_16_2d_euv_inputs_and_mesh.py
   看新增单元测试：
     dataclass 到 CLI 的映射；
     近场模板网格坐标；
     材料 tag 分类；
     近场积分区域面积。
```

当前验证结果见：

```text
notes/quick_start/2d_euv_grating_dtn_usage_guide.md
notes/test/2d_euv_validation_report.md
```

## 2026-06-26 更新：Stage 4 hexa 网格自动贴边代码阅读路径

如果本轮主要想看“任意 target size 如何生成可计算的 hexa 网格”，建议按下面顺序读：

```text
1. src/main.py
   看 Stage4GratingInputs3D：
     mesh_spacing_mode
     mesh_refined_size
     mesh_refinement_radius
   这里是 PyCharm 直接运行时最方便改的入口。

2. src/runners/run_3d_airbox.py
   看 _config_updates(...) 和 CLI：
     --mesh-spacing-mode
     --mesh-refined-size
     --mesh-refinement-radius
   _stage_defaults("stage4_block_grating") 里默认 mesh_spacing_mode="auto"。

3. src/common/config_3d.py
   看 SimulationConfig3D：
     mesh_spacing_mode_requested
     mesh_refined_size_resolved
     mesh_refinement_radius_resolved
   None 的默认含义在这里统一解析。

4. src/geometry/mesh_builder_3d.py
   这是本轮核心：
     _stage4_axis_plan(...)
       决定 auto/uniform_strict/boundary_fitted/local_refined。
     _subdivide_piecewise_axis(...)
       按材料面切段并逐段等分。
     _structured_hexa_mesh(...)
       用非均匀 x/y/z 轴生成 tensor-product hexa 单元。
     build_airbox_mesh_3d(...)
       strict uniform 继续走 create_box；fitted/local 走 custom hexa。

5. src/solvers/solve_maxwell_3d_common.py
   看 run_summary 输出：
     mesh_spacing_mode_resolved
     mesh_axis_cell_stats
     mesh_material_plane_alignment
     mesh_local_refinement_regions

6. src/test/test_15_stage4_hexa_mesh_spacing.py
   看新增单元测试：
     auto 可整除时保持 uniform；
     auto 不可整除时切到 boundary_fitted；
     uniform_strict 仍会拒绝不对齐网格；
     local_refined 在光栅附近实际使用小网格；
     boundary_fitted 能真实创建 DOLFINx hexa mesh。
```

读代码时要抓住一个原则：新网格仍是 tensor-product structured hexa。它不是 tetra，也不是非结构 AMR；因此 x/y 对面周期边界的 edge midpoint 和 tangent 仍能一一配对，`src/constraints/floquet_3d.py` 的显式 edge Floquet 约束不需要重写。

## 2026-06-25 更新：Stage 4 MPI 后处理与 Floquet 计时阅读路径

本轮如果要读代码，建议按这个顺序：

```text
1. src/constraints/floquet_3d.py
   build_double_floquet_mpc(...)
   先看 floquet_build_topological_edge_context，再看 x/y/corner 三段约束。
   h=2.5 时耗时主要来自边拓扑上下文，不是 DtN 边界影响 Floquet。

2. src/postprocessing/postprocess_3d.py
   save_airbox_3d_fields(...)
   MPI 下跳过 VTX .bp，写 vtx_3d_skipped_mpi.txt 和 fields_3d_for_paraview_parallel.pvd。
   这一步是为了绕开 ADIOS2/VTXWriter 的 BUS error。

3. src/solvers/dtn_port_3d.py
   _ReusableSurfaceComponentAssembler
   solve_stage4_dtn_port_total_field(...)
   这里是 DtN auxiliary modal port 的装配优化。
   每个 (side,m,n) 只装配 x/y 两个 surface component vector，两种偏振线性组合得到。

4. src/solvers/solve_maxwell_3d_common.py
   run_airbox_3d_case(...)
   这里把 field_formulation_setup、floquet_constraint_setup_outer、
   boundary_condition_setup、stage4_dtn_port_assembly_and_solve 分开计时。
```

对应验证结果见：

```text
notes/test/stage4_validation_report.md
notes/test/stage4_resume_log.md
```

## 2026-06-25 更新：Stage 4 DtN 性能优化后的阅读路径

如果你这轮主要关心 `boundary_condition_setup` 和 `Stage-4 DtN assembled/prepared ... auxiliary modes` 为什么耗时，按下面顺序读：

```text
1. src/solvers/solve_maxwell_3d_common.py
   看 _run_maxwell_3d_case_core(...) 中的计时拆分：
     field_formulation_setup
     floquet_constraint_setup_outer
     boundary_condition_setup
     stage4_dtn_port_assembly_and_solve

   现在 boundary_condition_setup 只表示强边界 dof/BC 对象设置；
   dtn_port 分支不施加 z 向强 Dirichlet，所以这里通常接近 0。

2. src/solvers/dtn_port_3d.py
   先看 _ReusableSurfaceComponentAssembler：
     用 fem.Constant 保存 alpha/gamma/kz；
     每个 top/bottom、x/y 分量只建一次 UFL form。

   再看 solve_stage4_dtn_port_total_field(...) 的 modal loop：
     每个 (side,m,n) 装配 x/y 两个表面向量；
     两个偏振通过 _combine_owned_entries(...) 线性组合；
     输出 stage4_dtn_modal_loop_seconds 和 component cache 统计。

3. results/.../dtn_port_power_metrics_3d.json
   看细分耗时：
     stage4_dtn_modal_loop_seconds
     stage4_dtn_modal_vector_assembly_seconds
     stage4_dtn_linear_solve_seconds
     stage4_dtn_component_vector_assemblies
     stage4_dtn_component_vector_cache_hits
```

本轮实测入口：

```text
block grating, h=5, np=4, auto_propagating:
  results/3D_stage4_block_grating_normal_p1_h5p0_np4_20260625_074047
  DtN modes = 1068
  stage4_dtn_modal_loop_seconds = 2.431 s
  elapsed = 15.637 s

flat, n_sub=1.0, h=2.5, np=8:
  results/3D_stage4_flat_layer_sanity_normal_p1_h2p5_np8_20260625_074306
  R/T/R+T = 6.043954e-04 / 9.993956e-01 / 1.000000
  慢在 stage4_dtn_linear_solve_seconds = 222.650 s，而不是端口模态装配。
```

## 2026-06-25 更新：Stage 4 3D DtN 总场端口阅读路线

当前新增的 Stage 4 DtN 主线建议按这个顺序读：

```text
1. src/main.py
   看 Stage4GratingInputs3D：
     stage4_boundary_model = "dtn_port"
     stage4_dtn_order_policy = "auto_propagating"
     stage4_dtn_assembly = "auxiliary"

2. src/runners/run_3d_airbox.py
   看 _stage_defaults("stage4_block_grating") 和 CLI：
     --stage4-boundary-model dtn_port
     --stage4-dtn-order-policy auto_propagating
     --stage4-dtn-assembly auxiliary

3. src/common/modes_3d.py
   这是 3D diffraction 后处理和 DtN 装配共用的模态目录：
     enumerate_diffraction_orders_3d(...)
     polarization_basis_3d(...)
     outgoing_port_modes_3d(...)
     incident_power_3d(...)

4. src/solvers/solve_maxwell_3d_common.py
   看 _use_stage4_dtn_port_formulation(...) 和 _run_maxwell_3d_case_core(...)：
     dtn_port 分支不加 z 向强 Dirichlet，不启用 PML；
     先建立 x/y Floquet MPC，再调用 solve_stage4_dtn_port_total_field(...)。

5. src/solvers/dtn_port_3d.py
   这是第一版 3D Fourier-DtN 总场端口：
     组装 FEM+MPC 基础块；
     为每个出射端口模态添加一个 auxiliary unknown；
     top port 额外加入入射基模；
     R/T 从 auxiliary outgoing amplitude 计算。

6. src/postprocessing/postprocess_3d.py
   ParaView 输出 E_total 和 E_incident_port。
   这里不输出伪造 E_exact；PML 历史字段只在旧 PML 分支里有诊断意义。

7. src/test/test_14_stage4_dtn_modes.py
   纯数学单元测试，不求解 Maxwell，用来锁住模态枚举、偏振横向性和功率符号。
```

当前验证状态：

```text
compileall：通过
完整单元测试：Ran 37 tests, OK (skipped=8)
flat n_sub=1.0, h=2.5：R+T = 1.000000
flat n_sub=1.45, h=2.5：R+T = 1.000000
block grating h=5, auto_propagating：R+T = 1.000000
```

因此 Stage 4 读代码时应优先跟踪 `dtn_port` 主线；旧 `pml` 分支保留为诊断历史，不再作为可信 R/T 结论来源。

## 2026-06-25 更新：Stage 4 E/H Fourier 后处理阅读路径

本轮 Stage 4 官方 R/T 已从 E-only 改成 E/H Fourier。读代码时重点看：

```text
src/postprocessing/diffraction_3d.py

1. _fit_directional_eh_amplitudes_for_order(...)
   对单个 (m,n) 级次，用 Fourier(E_x,E_y,H_x,H_y) 解 up/down/s/p 振幅。

2. _eh_fourier_order_powers(...)
   统计 top-up 反射和 bottom-down 透射，写出：
     R_total_from_eh_fourier
     T_total_from_eh_fourier
     R_plus_T_from_eh_fourier

3. _e_fourier_order_powers(...)
   仍保留为诊断字段：
     R_plus_T_from_e_fourier
   它不再是官方结果，因为 E-only 无法区分同级次的上行/下行波。

4. compute_diffraction_orders_3d(...)
   summary["diffraction_total_power_source"] 现在应为 "eh_fourier_orders"。
```

配套测试：

```text
src/test/test_11_stage4_diffraction_modes.py

test_flat_layer_fresnel_field_e_fourier_power_sanity
  同时验证 E-only 和 E/H Fourier 对解析 Fresnel flat-layer 都返回 R+T=1。

test_eh_fourier_separates_same_order_up_down_waves
  人工构造同一 (0,0) 级次的 down/up 波，确认 E/H Fourier 能分离 transmitted/down 振幅。
```

重要结论：这个后处理修正确实降低了虚高透射率，但 h=2.5 的 EUV block grating 仍然 `R+T=1.984750`，所以后续排查应转向离散精度、3D Maxwell 约束形式和更严格的边界/端口模型，而不是继续调 E-only 后处理。

## 2026-06-24 更新：h=2.5 诊断后下一步读代码重点

最新 h=2.5、np=16 的 Stage 4 结果仍然 `R+T>1`，但已经排除了几类问题：

```text
1. direct LU 正常收敛，true relative residual 约 1e-11。
2. Floquet 约束构建完成，约束数 12960，未再出现 building/resolving 阶段 OOM。
3. natural 与 zero_tangential PML outer BC 结果几乎一致。
4. zero_tangential 的 z 外边界 Dirichlet dof 已用全局统计确认确实施加。
```

继续排查时优先读这条路径：

```text
1. src/solvers/solve_maxwell_3d_stage_4_grating.py
   Stage 4 入口，只负责把 grating case 转到 common core。

2. src/solvers/solve_maxwell_3d_common.py
   重点看 _run_maxwell_3d_case_core 中的 layered_scattered 分支：
     E_total = E_scat + E_bg
     RHS = +k0^2 * (eps_true - eps_bg) * inner(E_bg, v)
   以及 PML 张量、source tag、boundary_condition_setup、summary 字段。

3. src/common/analytic_fields_3d.py
   看 stage4_layered_background_field 和 stage4_layered_background_value。
   这里定义了没有光栅时的 air/substrate Fresnel 分层背景。

4. src/common/pml_3d.py
   看 z 向复拉伸张量是否和弱式中的 curl-curl / mass 项匹配。

5. src/postprocessing/diffraction_3d.py
   看 probe plane 采样、传播级枚举、E-Fourier R/T 和 sampled net-flux 诊断。
```

本轮还修正了一个容易误读的 summary 字段：`strong_z_boundary_dirichlet_dofs` 现在记录 MPI 全局 dof 数，旧的 rank0 本地数不再作为主字段使用；原始全局数保留在 `strong_z_boundary_dirichlet_raw_dofs_global`。

## 2026-06-24 更新：Stage 4 R/T 修正后的阅读入口

本轮先看这几处：

```text
1. src/main.py
   Stage4GratingInputs3D 里不再有 solver_profile。
   当前只需要改 Stage 4 几何、PML、probe 和 diffraction 参数。

2. src/runners/run_3d_airbox.py
   CLI 已删除 --solver-profile。
   _stage_defaults("stage4_block_grating") 仍给出 Stage 4 默认几何和物理参数。

3. src/solvers/solve_maxwell_3d_common.py
   _direct_lu_petsc_options() 固定为 preonly + lu。
   Stage 4 仍用 layered_scattered：
     E_total = E_scat + E_bg
     RHS = +k0^2 * (eps_true - eps_bg) * inner(E_bg, v)

4. src/postprocessing/diffraction_3d.py
   compute_diffraction_orders_3d(..., E_scattered=...)
   现在官方 R/T 采样 E_scat，并在 probe plane 加解析 E_bg_exact。
   enumerate_diffraction_orders_3d() 会自动补全所有传播级，防止 EUV 多级次被 m,n=2 截断。

5. src/test/test_11_stage4_diffraction_modes.py
   test_flat_layer_fresnel_field_e_fourier_power_sanity
   这个测试不求解 Maxwell，只把解析 Fresnel 总场喂给同一套 E-Fourier R/T 后处理。
```

验证结论：

```text
flat-layer sanity:
  E_scat = 0
  R/T/R+T = 0.03373594 / 0.9662641 / 1.000000

block-grating h=12.5:
  R+T 仍约 1.0086，结果继续标记为 failed_stage4_energy_balance
  需要修复版 h=2.5 或更细网格验证
```

## 2026-06-24 更新：Stage 4 13.5 nm 案例阅读重点

当前 Stage 4 默认已经切到 100 nm x 100 nm 周期、50 nm 立方体、13.5 nm 波长。阅读时先看：

```text
1. src/main.py
   Stage4GratingInputs3D:
     lambda0 = 13.5
     period_x = period_y = 100
     grating_width_x/y/height = 50
     air_height = 100
     substrate_thickness = 50
     pml_top/bottom = 25
     mesh_target_size = 5
     stage4_pml_outer_bc = "natural"
     diffraction_probe_fraction = 0.75

2. src/runners/run_3d_airbox.py
   _stage_defaults("stage4_block_grating") 里有同一套 CLI 默认值。

3. src/solvers/solve_maxwell_3d_common.py
   看 boundary_condition_setup：
     stage4_pml_outer_bc="natural" 时，不对 z 外边界加零切向 E_scat；
     stage4_pml_outer_bc="zero_tangential" 时，恢复旧的零切向诊断。

4. src/postprocessing/diffraction_3d.py
   _probe_z_locations(cfg) 使用 cfg.diffraction_probe_fraction。
   现在默认 top/bottom probe 是 75 nm / -37.5 nm，并记录到 PML 入口的距离。
   默认跳过旧 E/H modal diagnostic，只保留正式 E-Fourier R/T，避免 13.5 nm 多衍射级后处理过慢。
```

当前求解器路径是 direct-only。旧迭代 profile 文档仅作为历史记录。

## 2026-06-24 更新：3D 求解器拆分后的阅读路径

现在 3D 求解器不再要求先读一个巨大的 `solve_airbox_maxwell_3d.py`。建议按你当前研究的阶段直接进入：

```text
Stage 1：最小 3D 空气盒
  1. src/main.py
     看 ACTIVE_3D_INPUT_GROUP = "stage1_airbox"
     看 Stage1AirboxInputs3D。
  2. src/runners/run_3d_airbox.py
     看 _run_stage_config(...) 如何分发到 Stage 1。
  3. src/solvers/solve_maxwell_3d_stage_1_airbox.py
     这是 Stage 1 正式入口。
  4. src/solvers/solve_maxwell_3d_common.py
     只在需要看有限元装配细节时再进入。

Stage 2：2A/2B/2C 无光栅验证
  1. src/main.py
     看 ACTIVE_3D_INPUT_GROUP = "stage2_no_grating"
     看 Stage2NoGratingInputs3D。
  2. src/solvers/solve_maxwell_3d_stage_2_no_grating.py
     这是 floquet_airbox / pml_airbox / fresnel_interface 的入口。
  3. src/common/analytic_fields_3d.py、src/common/pml_3d.py、src/constraints/floquet_3d.py
     分别看解析场、PML、Floquet 约束。

Stage 4：真实 3D 光栅
  1. src/main.py
     看 ACTIVE_3D_INPUT_GROUP = "stage4_grating"
     只改 Stage4GratingInputs3D。
  2. src/runners/run_3d_airbox.py
     看 _stage_defaults("stage4_block_grating") 和 _run_stage_config(...)。
  3. src/solvers/solve_maxwell_3d_stage_4_grating.py
     这是 Stage 4 正式入口。
  4. src/solvers/solve_maxwell_3d_common.py
     看 stage4_layered_background_field(...)、_build_variational_forms(...)、
     _stage4_lossless_energy_balance_check(...)。
  5. src/postprocessing/diffraction_3d.py
     看衍射级 R/T 后处理。
```

`src/solvers/solve_airbox_maxwell_3d.py` 现在只是旧脚本和旧测试的兼容调度层。新代码阅读时可以先跳过它。

## 2026-06-24 更新：Stage 4 MPI 修复后的代码阅读路径

这轮修复的是 Stage 4 在 MPI 下 `R+T>1`、场幅值随并行数变化的问题。阅读顺序建议如下：

```text
1. src/constraints/floquet_3d.py
   重点看 _build_topological_edge_context()：
     mesh.topology.create_entity_permutations()
     cpp.mesh.entities_to_geometry(..., permute=True)

   这里是根因修复点。3D Nedelec Floquet 约束的 orientation_sign 必须跟
   DOLFINx 拓扑边方向一致，不能用未置换的几何边顺序。

   再看 _build_constraints_for_kind()：
     每个 slave dof 仍只对应一个 master dof；
     local constraint 使用本 rank 装配 owned cells 所需的 local slave dof；
     summary 会记录 ghost slave constraints / skipped records。

2. src/solvers/solve_airbox_maxwell_3d.py
   看 _prepare_petsc_options_for_comm()：
     MPI direct 会显式选择 mumps / superlu_dist / strumpack。

   看 run_airbox_3d_case() 的 boundary_condition_setup：
     Stage 4 layered_scattered + pml 现在对上下 PML 外边界施加零切向 E_scat。

   看 _assembled_rhs_norm() 和 _linear_system_diagnostics()：
     summary 里会输出 RHS 范数、解范数、真实线性残差和矩阵范数，
     用于判断并行差异到底来自 RHS、矩阵还是后处理。

3. notes/test/stage4_validation_report.md
   顶部表格记录 h50/p1 串行与 MPI 2/4/8/12/16 的最终一致性结果。

4. src/test/test_12_stage4_floquet_orientation_regression.py
   这是一个轻量回归测试，防止以后误删 create_entity_permutations() 或
   entities_to_geometry(..., permute=True)。
```

当前结论：

```text
stage4_block_grating, h50, p1, normal:
  serial / np=2 / np=4 / np=8 / np=12 / np=16
  R+T = 0.952741
  max|E| = 1.911019
  linear system solution norm = 1266.870459
```

## 2026-06-24 更新：Stage 4 衍射级采样面代码路径

这轮只改 Stage 4 diffraction 后处理的默认 probe plane，不改 Maxwell 方程和网格。阅读顺序：

```text
1. src/postprocessing/diffraction_3d.py
   看 _probe_z_locations(cfg)：
     top_probe_z    = interface_z + 0.95 * (physical_z_max - interface_z)
     bottom_probe_z = interface_z + 0.95 * (physical_z_min - interface_z)
   对 interface_z=0 的常用 Stage 4 单胞，即 z=0.95*z_max 和 z=0.95*z_min。

   看 _validate_sample_counts(cfg, orders)：
     根据拟合级次的 max |m| / max |n| 记录最低 Fourier 采样点数；
     采样点数不足时直接报错。

2. src/test/test_11_stage4_diffraction_modes.py
   看 test_default_probe_planes_use_95_percent_of_physical_layers()。
   这个测试锁定 600/500 nm 案例的 top=807.5 nm、bottom=-332.5 nm 默认采样面。

3. run_summary.json / power_metrics_3d.json
   新增字段：
     diffraction_probe_position_fraction_from_interface_to_physical_boundary
     diffraction_sample_point_count_per_plane
     diffraction_min_sample_count_x_for_fit_orders
     diffraction_min_sample_count_y_for_fit_orders
```

## 2026-06-23 更新：600/500 nm Stage 4 COMSOL 对比代码路径

这轮主要改 Stage 4 输入、功率后处理和 COMSOL-like 图片工具。阅读顺序建议：

```text
1. src/main.py
   看 PyCharm 入口变量：
   PERIOD_X_3D / PERIOD_Y_3D
   AIR_HEIGHT_3D / SUBSTRATE_THICKNESS_3D
   GRATING_WIDTH_X_3D / GRATING_WIDTH_Y_3D / GRATING_HEIGHT_3D
   DIFFRACTION_ZERO_ORDER_ONLY_3D = False

2. src/runners/run_3d_airbox.py
   看 _stage_defaults("stage4_block_grating")。
   这里定义 Stage 4 默认几何、S 偏振 incident_phi_deg=0、PML 厚度和 direct solver。
   CLI 新增 --air-height、--substrate-thickness。

3. src/geometry/mesh_builder_3d.py
   看 _validate_stage4_hexa_alignment()。
   它保证 block 边界、interface、PML 入口都落在 hexa 网格面上。

4. src/solvers/solve_airbox_maxwell_3d.py
   看 _build_variational_forms() 和 run_airbox_3d_case()。
   Stage 4 仍是 layered_scattered：
   RHS = +k0^2 * (eps_true - eps_bg) * inner(E_bg, v)，source 只在 grating tag。
   lossless 能量门槛现在是 R+T <= 1 + 1e-8。

5. src/postprocessing/diffraction_3d.py
   看 enumerate_diffraction_orders_3d() 和 _e_fourier_order_powers()。
   新周期会打开基底高阶衍射，所以默认不再只算 0 级。
   正式 R/T 来自 e_fourier_orders；旧 E/H modal fit 只保留为 diagnostic。

6. src/tools/render_stage4_comsol_views.py
   输入 fields_3d_for_paraview.vtu，输出外表面、y-z 中心切面、x-z 中心切面三张 PNG。
   每张图单独取颜色范围，用于和 COMSOL 电场模截图做形态对比。
```

## 2026-06-23 更新：3D ParaView 输出瘦身后的代码路径

这轮只改 3D 后处理输出，不改求解方程。阅读时看：

```text
src/postprocessing/postprocess_3d.py
  _add_complex_vector(...)
    现在只写：
      <field>_real   # 3 分量 vector
      <field>_imag   # 3 分量 vector
      <field>_abs    # 模值 scalar

  save_airbox_3d_fields(...)
    不再写 E_V_per_m_*，只写 E_tot_V_per_m_*。
    不再写 *_physical_*、*_pml_*、is_physical_z_region、is_pml_z_region。
    仍保留 domain_tag，方便在 ParaView 里自己筛材料区域。
```

ParaView 中现在的阅读方式：

```text
看总电场模：选 E_tot_V_per_m_abs
看 Ex/Ey/Ez：选 E_tot_V_per_m_real 或 E_tot_V_per_m_imag，然后选 X/Y/Z component
看散射场：选 E_sca_V_per_m_abs / real / imag
看背景场：选 E_b_V_per_m_abs / real / imag
看磁场：选 H_A_per_m_abs / real / imag
筛选区域：用 cell data 里的 domain_tag
```

## 2026-06-23 更新：Stage 4 当前代码阅读路径，evanescent fitting 已接入

如果现在阅读 Stage 4，请按这个顺序：

```text
1. src/runners/run_3d_airbox.py
   看 _stage_defaults("stage4_block_grating")。
   stage4_boundary_model 默认是 "pml"。

2. src/common/config_3d.py
   看 stage4_boundary_model、diffraction_zero_order_only、
   diffraction_order_max_m/n、physical_z_min/max、domain_z_min/max。

3. src/geometry/mesh_builder_3d.py
   看 hexa 网格、air/substrate/grating/top_pml/bottom_pml tags。

4. src/constraints/floquet_3d.py
   看 build_double_floquet_mpc(...)。
   正式路径仍是 degree=1 N1curl edge topology，不使用 probe/pinv。

5. src/solvers/solve_airbox_maxwell_3d.py
   看 stage4_layered_background_field(...) 和 _build_variational_forms(...)。
   Stage 4 正式 PML 分支现在是：
     E_total = E_b + E_scat
     source 只在 grating tag
     PML 采用弱式吸收
     z 外边界不再额外强加 Dirichlet

6. src/postprocessing/diffraction_3d.py
   看 _orders_for_modal_fit(...)。
   默认 block grating 虽然只统计 0 级传播功率，但拟合时会加入邻近 evanescent 级次，
   防止近场谐波被误塞进 0 级 R/T。

7. src/postprocessing/postprocess_3d.py
   看 E_tot/E_sca/E_b 的 physical/PML mask 输出。
   ParaView 对照 COMSOL 时优先看 E_tot_physical_abs_V_per_m。

8. src/test/stage4_2p5d_compare.py
   这是 2.5D 对照脚本。当前 Ey 已接近 0，但 R/T 仍未完全对齐 2D TM。
```

最新 h50/p1 判定：

```text
serial block grating: R+T = 9.826341e-01，completed
MPI2 block grating:   R+T = 9.142503e-01，completed，但与串行仍有定量差异
2.5D serial:          Ey 接近 0，但 R+T = 1.042795，仍需继续修
```

## 2026-06-23 更新：Stage 4 当前阅读路径与已知失败点

如果现在阅读 Stage 4，请按这个顺序看，不要从旧 Stage 2 的 2B/2C 逻辑进入：

```text
1. src/test/stage4_2p5d_compare.py
   先看 2D TM reference 和 3D y-extruded config 如何对应。

2. src/runners/run_3d_airbox.py
   看 _stage_defaults("stage4_block_grating") 和 stage4_flat_layer_sanity。

3. src/geometry/mesh_builder_3d.py
   看 _validate_stage4_hexa_alignment(...) 和 _mark_cells(...)。

4. src/constraints/floquet_3d.py
   看 build_double_floquet_mpc(...)。当前正式路径是 degree=1 N1curl edge topology，
   dense probe/pinv 已禁用。MPI 下仍需重点排查本地 slave/ghost slave 约束一致性。

5. src/solvers/solve_airbox_maxwell_3d.py
   看 stage4_layered_background_field(...)、_build_variational_forms(..., layered_scattered)
   和 run_airbox_3d_case(...)。Stage 4 现在会：
   - 求解 E_scat；
   - E_b 在 PML 输出中置零；
   - E_total = E_b + E_scat；
   - PML 外边界施加零切向 E；
   - solve 后显式 scatter_forward；
   - lossless R+T > 1.01 时标记 failed_stage4_energy_balance。

6. src/postprocessing/postprocess_3d.py
   看 E_tot/E_b/E_sca 以及 physical/PML mask 数组如何写入 ParaView。

7. src/postprocessing/diffraction_3d.py
   看 0 级/多级 diffraction fitting。flat-layer sanity 已验证 0 级 Fresnel R+T=1，
   但真实 grating 仍不能作为可信物理结果。
```

最新实跑判定：`stage4_flat_layer_sanity` 通过；`stage4_block_grating` 和 `stage4_2p5d_compare` 失败。下一步修复目标是先让 3D y-extruded 与旧 2D TM 对齐。

## 2026-06-23 更新：Stage 4 现阶段应先读 2.5D 对照和能量守恒 guard

当前 Stage 4 block grating 的 `R+T > 1`，已经被判定为不可信。阅读代码时先看这些位置：

```text
src/test/stage4_2p5d_compare.py
  build_2d_reference_config(...)
    构造与 Stage 4 y-extruded 几何对应的 2D TM scattered config。
  build_3d_extruded_config(...)
    构造 y 方向完全拉伸的 3D Stage 4 config。
  main(...)
    依次运行 2D 和 3D，并写 stage4_2p5d_comparison.json。

src/solvers/solve_airbox_maxwell_3d.py
  stage4_layered_background_field(...)
    Stage 4 背景场只在物理 z 区域非零，PML 中置零。
  _stage4_lossless_energy_balance_check(...)
    lossless Stage 4 若 R+T > 1.01，标记为 failed_stage4_energy_balance。
  run_airbox_3d_case(...)
    Stage 4 layered_scattered 求解 E_scat，并在 PML 外边界施加零切向 E。
    summary/log 会输出 max |Ex|, |Ey|, |Ez|。

src/postprocessing/postprocess_3d.py
  save_airbox_3d_fields(...)
    写出 Ex/Ey/Ez 分量数组和 max_abs_E_sca_Ey 等 summary 字段。
```

当前判断：先不要从 `stage4_block_grating` 的 R/T 学物理结论；先用 2.5D 对照定位为什么 3D y-extruded 会出现明显 `Ey`。

## 2026-06-23 更新：Stage 4 物理区/PML区输出和功率诊断

本轮新增两个阅读点：

```text
src/postprocessing/postprocess_3d.py
  save_airbox_3d_fields(...)
    Stage 4 不输出 E_exact/H_exact/error。
    ParaView 同时写：
      E_tot_V_per_m_*
      E_b_V_per_m_*
      E_sca_V_per_m_*
    还额外写物理区/PML区标量：
      E_tot_physical_abs_V_per_m
      E_tot_pml_abs_V_per_m
      E_sca_physical_abs_V_per_m
      E_sca_pml_abs_V_per_m
      E_b_physical_abs_V_per_m
      E_b_pml_abs_V_per_m
      is_physical_z_region
      is_pml_z_region

src/postprocessing/diffraction_3d.py
  compute_diffraction_orders_3d(...)
    官方 R/T 来自 calibrated modal amplitudes。
    sampled net-flux 只作为 diagnostic-only，因为 H 来自 FE curl 重建，
    flat sanity 中它也不如 modal amplitude 稳定。
```

## 2026-06-23 更新：Stage 4 不再把背景场叫精确解

本轮把 Stage 4 的后处理口径改成和 2D scattered-field 一致：

```text
src/postprocessing/postprocess_3d.py
  save_airbox_3d_fields(...)
    Stage 4:
      不写 E_exact/H_exact/error
      写 E_tot_V_per_m_*
      写 E_b_V_per_m_*
      写 E_sca_V_per_m_*

src/solvers/solve_airbox_maxwell_3d.py
  _stage4_scattered_pml_metrics(E_sca, cfg)
    PML decay 指标使用 E_scat
    不再用 E_total 判断 Stage 4 PML
```

原因：真实矩形柱 grating 没有解析精确解；`E_b` 只是空气/基底平界面的分层背景场。PML 中的 `E_b` 和 `E_total` 是人工复坐标区域里的延拓场，不能要求它们为零。判断吸收层时看 `E_sca_V_per_m_abs`。

## 2026-06-23 更新：Stage 4 main.py 与 ParaView 输出路径

本轮修正了 `src/main.py` 与 `src/common/config_3d.py` 的职责分工：

```text
src/common/config_3d.py
  保持中性默认值，不默认打开 Stage 4 grating/PML/Floquet。

src/runners/run_3d_airbox.py
  _stage_defaults("stage4_block_grating") 给出 Stage 4 benchmark 默认值。

src/main.py
  只作为 PyCharm/直接运行入口，把你在顶部改的变量转换成 CLI 参数。
  Stage 4 的 period、block 尺寸、n_grating、diffraction 参数都在这里显式列出。
```

如果 `MESH_TARGET_SIZE_3D=30.0`，默认 Stage 4 几何会报 hexa grid alignment error。这个错误说明 block/interface 平面没有落在网格面上；默认建议用 `50.0`，需要更细时用 `25.0`。

ParaView 场变量来自：

```text
src/solvers/solve_airbox_maxwell_3d.py
  run_airbox_3d_case(...)
     E_total = E_background_layered + E_scat
     save_airbox_3d_fields(..., E_scattered=E_sca, E_background=E_background_layered)

src/postprocessing/postprocess_3d.py
  save_airbox_3d_fields(...)
     E_tot_V_per_m_*  总场
     E_b_V_per_m_*    背景场
     E_sca_V_per_m_*  散射场
```

## 2026-06-23 更新：Stage 4 真实 3D 矩形柱代码阅读路径

如果你现在要读 Stage 4，请先按这个顺序看，不要从旧的 2C Fresnel 诊断开始：

```text
1. src/runners/run_3d_airbox.py
   看 _stage_defaults("stage4_block_grating")
   这里定义默认几何、材料、PML、Floquet、求解器和 diffraction 参数。

2. src/common/config_3d.py
   看 SimulationConfig3D 的 grating_* 属性：
   grating_x_min/max, grating_y_min/max, grating_z_min/max,
   eps_grating, grating_background_eps。

3. src/geometry/mesh_builder_3d.py
   看 _validate_stage4_hexa_alignment(...)
   看 _mark_cells(...)
   这里负责 hexa 对齐检查和 air/substrate/grating/top_pml/bottom_pml cell tags。

4. src/common/analytic_fields_3d.py
   看 uses_layered_fresnel_background(...)
   看 electric_field_code_values(...)
   Stage 4 的 E_bg 复用 air/substrate 平界面 Fresnel 分层背景场。

5. src/constraints/floquet_3d.py
   看 build_double_floquet_mpc(...)
   当前正式路径是 degree=1 N1curl edge topology：
   slave_dof = phase * orientation_sign * master_dof。

6. src/solvers/solve_airbox_maxwell_3d.py
   看 _use_layered_scattered_formulation(...)
   看 _build_variational_forms(..., field_formulation="layered_scattered")
   看 run_airbox_3d_case(...)
   这里完成 E_scat 求解，并重建 E_total = E_bg + E_scat。

7. src/postprocessing/diffraction_3d.py
   看 enumerate_diffraction_orders_3d(...)
   看 fit_diffraction_amplitudes_from_samples(...)
   看 compute_diffraction_orders_3d(...)
   这里输出 diffraction_orders_3d.json/csv 和 R_total/T_total/A_balance。

8. src/postprocessing/postprocess_3d.py
   看 save_airbox_3d_fields(...)
   这里写 ParaView 用的 E/H 物理单位场和 domain_tag。
```

对应测试：

```text
src/test/test_11_stage4_diffraction_modes.py
```

对应文档：

```text
notes/quick_start/stage4_3d_block_grating_usage_guide.md
notes/theory/stage4_3d_block_grating_diffraction.md
notes/test/stage4_validation_report.md
```

当前第一版结论：flat-layer sanity 已经回到 Fresnel R/T；block grating h50/p1 能跑通并输出 diffraction 表，但 `R+T` 仍偏离 1，后续重点是 PML、网格和 modal port 收敛。

## 2026-06-22 更新：2C Fresnel 诊断代码路径

最新 2C 诊断不要先看 PDE 组装，先按下面路径确认后处理和 source 是否健康：

```text
src/solvers/solve_airbox_maxwell_3d.py
  run_fresnel_analytic_postprocess_sanity(cfg, out_dir)
     不求解 Maxwell
     构建同一个 mesh 和 Nédélec space
     插值完整 Fresnel analytic total field
     调用同一个 _fresnel_numerical_metrics(...)

  _fresnel_numerical_metrics(E, cfg)
     拟合 incident/reflected/transmitted 模态
     输出 R/T、fit residual、模态幅值和采样 z 范围

  _cell_tag_volumes(...)
     输出 air/substrate/top_pml/bottom_pml 的 cell tag 体积

  _build_variational_forms(..., field_formulation="incident_scattered")
     RHS 仍是 +k0^2*(eps_sub-eps_air)*inner(E_inc, v)
     source 只在 cfg.tags.substrate
```

对应的回归测试在：

```text
src/test/test_03_fresnel_coefficients.py
  test_fresnel_analytic_total_field_postprocess_sanity
```

这条测试说明：如果完整 Fresnel 解析场都拟合不回 Fresnel R/T，就先修 `_fresnel_numerical_metrics`；如果它通过，而 PDE 解不通过，就优先看 scattered-field source、PML 和边界条件。

## 2026-06-22 更新：2C incident-scattered Fresnel 代码路径

最新 2C `fresnel_interface` 已经不是 reference-correction。阅读代码时按这个路径看：

```text
src/solvers/solve_airbox_maxwell_3d.py
  _use_reference_correction_formulation(cfg)
     只保留 floquet_airbox / pml_airbox

  _use_incident_scattered_formulation(cfg)
     fresnel_interface 返回 True

  incident_air_plane_wave_field(V, cfg)
     只构造空气入射平面波 E_inc
     不包含 Fresnel 解析反射/透射场

  _build_variational_forms(..., field_formulation="incident_scattered", incident_field=E_inc)
     左端仍使用真实 material/PML
     右端只在 cfg.tags.substrate 上加 k0^2(eps_sub-eps_air) E_inc

  run_airbox_3d_case(...)
     E = problem.solve()         # 这里的 E 是 E_sca
     E_inc = incident_air_plane_wave_field(E.function_space, cfg)
     E_total = E_sca + E_inc
     save_airbox_3d_fields(..., E_total, ...)
     _fresnel_numerical_metrics(E_total, cfg)
```

关键 summary 字段：

```text
field_formulation = incident_scattered
incident_added_to_solution = true
reference_added_to_solution = false
fresnel_reference_used_for_solution = false
fresnel_reference_used_for_comparison_only = true
rhs_source_region = physical_substrate
rhs_source_norm
E_sca_norm / E_inc_norm / E_total_norm
```

当前 `h=50 nm, p=1, MPI 2` 的 2C physical benchmark 已经能跑通并收敛，`R+T` 约 `1.058`。这不是 previous reference sanity 的机器精度结果；后续要继续压误差，应看 PML 中 incident-field source/stretching 或 modal port/TFSF。

## 2026-06-22 历史记录：Stage 2 correction 与 Fresnel R/T 校准阅读路径

这一节记录的是上一版 reference-correction sanity 路径。最新代码中，2A/2B 仍沿用 correction 思路，但 2C `fresnel_interface` 已经改为本文最上方的 `incident_scattered` 路径；阅读 2C 时不要再从本节进入。

```text
src/solvers/solve_airbox_maxwell_3d.py
  _use_reference_correction_formulation(cfg)
     历史版本中 floquet_airbox / pml_airbox / fresnel_interface 返回 True
     最新版本只保留 floquet_airbox / pml_airbox

  _field_formulation_label(...)
     floquet_airbox    -> incident_correction
     pml_airbox        -> reference_correction
     fresnel_interface -> incident_scattered

  _add_reference_field_to_solution(E, cfg)
     在 E.function_space 中重新插值解析参考场
     再做 E += reference
     这是修复 MPI/MPC broadcast shape mismatch 的关键；最新 2C 不再走这一步

  _mode_basis(...)
     fresnel_interface 中非 p 一律按 s 基底拟合

  _fit_plane_wave_modes(...)
     先做普通最小二乘模态拟合
     再用 _interpolated_mode_field(...) 建立 FE 插值响应矩阵
     用这个小矩阵校准 p1 Nédélec 点采样造成的幅值偏差
```

对应输出字段：

```text
field_formulation
R_total / T_total / R_plus_T
fresnel_R / fresnel_T
fresnel_R_error / fresnel_T_error
pml_reflection_proxy
```

本轮关键回归：

```text
Docker unittest: Ran 22 tests, OK, skipped=8
2A h50 p1 MPI4 normal: E error = 2.77e-14
2B h50 p1 MPI2:        E error = 2.45e-14, proxy = 7.63e-16
2C reference-correction 历史结果: R+T = 1.0, R/T 与 Fresnel 解析一致
```

## 2026-06-22 更新：2A Floquet airbox 场幅值修复后的阅读路径

2A `floquet_airbox` 的场幅值误差已经改用 incident-correction 口径修正。阅读代码时按这个路径看：

```text
src/solvers/solve_airbox_maxwell_3d.py
  _use_reference_correction_formulation(cfg)
     当前正式路径只对 floquet_airbox / pml_airbox 返回 True

  run_airbox_3d_case(...)
     E_exact = plane_wave_electric_field(V, cfg)
     E_bc = 0 correction field
     bc = dirichletbc(E_bc, z-boundary dofs)
     E = problem.solve()
     E += E_exact
     summary["field_formulation"] = "incident_correction"
```

这个设计的含义是：线性系统求的是 `E_total - E_incident`，但后处理和 ParaView 仍然看 `E_total`。这一段是 2A 修复时的历史记录；最新实现中 2B 仍使用 `reference_correction`，2C 已切换到本文最上方的 `incident_scattered`。

本轮 `h=50 nm, p=1, MPI 2` 结果：

```text
normal:  relative_max_abs_E_error = 2.95e-14
oblique: relative_max_abs_E_error = 5.84e-02
```

## 2026-06-22 更新：3D Floquet 显式边拓扑约束阅读路径

最新 3D Floquet 正式路径已经禁用 probe function + pseudo-inverse，也禁用整张周期面 dense transform。阅读时先看 `src/constraints/floquet_3d.py`：

```text
build_double_floquet_mpc(...)
  -> _require_supported_topological_edges(...)
     只允许 hexahedron + degree=1 N1curl
  -> _build_topological_edge_context(...)
     从 cell->edge 和 N1curl entity_dofs 建立 mesh edge -> dof 映射
  -> _build_constraints_for_kind(..., "x")
     x=Lx -> x=0，phase=beta_x
  -> _build_constraints_for_kind(..., "y")
     y=Ly -> y=0，phase=beta_y
  -> _build_constraints_for_kind(..., "corner")
     x=Lx 且 y=Ly 的角边 -> x=0,y=0，phase=beta_x*beta_y
```

每个 slave dof 只允许一个 master dof。重点看这些字段：

```text
floquet_num_slave_edges
floquet_num_matched_master_edges
floquet_num_constraints
floquet_num_x_constraints
floquet_num_y_constraints
floquet_num_corner_constraints
floquet_max_masters_per_slave = 1
floquet_max_edge_midpoint_pairing_error
```

实跑结论：`h=50 nm, p=1, MPI 2/4` 已不再卡在 building/resolving 阶段；`degree=2` 会直接 `NotImplementedError`，不会 fallback 到 dense/probe。

## 2026-06-22 更新：3D Floquet 约束计时的代码路径

如果运行时卡在 3D Floquet 约束构建，先看这条代码路径：

```text
src/solvers/solve_airbox_maxwell_3d.py
  solve_airbox_maxwell_3d(...)
  -> build_double_floquet_mpc(V, mesh_data, cfg, log)

src/constraints/floquet_3d.py
  build_double_floquet_mpc(...)
  -> _build_constraints_for_kind(..., "x")
     打印 building 3D Floquet x-direction low-level constraints seconds
  -> _build_constraints_for_kind(..., "y")
     打印 building 3D Floquet y-direction low-level constraints seconds
  -> _build_constraints_for_kind(..., "corner")
     打印 resolving 3D double-Floquet corner/master chain seconds
  -> dolfinx_mpc.MultiPointConstraint.add_constraint/finalize()
     打印 finalizing 3D double-Floquet MPC seconds
```

这些计时都在 `src/constraints/floquet_3d.py` 内部用 MPI barrier 包住，并用所有 rank 的最大值作为输出。`DoubleFloquet3DData.timings_seconds` 会把这些时间带回求解器；`src/solvers/solve_airbox_maxwell_3d.py` 再把它们写入 `run_summary.json` 的 `floquet_constraint_timings_seconds`，同时合并进总的 `timings_seconds`。

排查顺序建议：

```text
1. x-direction 很慢：优先看 x=Lx 边自由度采集、edge midpoint 配对和 MPI allgather。
2. y-direction 很慢：同理检查 y=Ly 边自由度采集和 edge 配对。
3. corner/master chain 很慢：现在这里是角边 direct mapping，不再做 dense master-chain；若变慢，优先看角边数量和 owner-rank 约束发射。
4. finalize 很慢：优先看 dolfinx_mpc 约束装配、通信和内存峰值。
```

## 2026-06-22 更新：2A / 2B / 2C 代码阅读路径

最新更新放在文档最上方。Stage 2 的使用说明先看：

```text
notes/quick_start/stage2_2a_2b_2c_usage_guide.md
```

如果直接读代码，按下面三个路径看。

### 2A：`floquet_airbox`

```text
src/main.py
  看 STAGE_CASE_3D = "floquet_airbox" 以及入射角、网格、求解器变量。

src/runners/run_3d_airbox.py
  看 _stage_defaults("floquet_airbox") 如何设置 use_floquet_xy=True。

src/common/config_3d.py
  看 direction_vector、kx/ky、floquet_phase_x/y。

src/geometry/mesh_builder_3d.py
  看 x_min/x_max、y_min/y_max、z_min/z_max 外边界 tags。

src/constraints/floquet_3d.py
  2A 核心。build_double_floquet_mpc(...) 构造双周期约束。
  当前串行和 MPI 都看 _build_edge_dof_map_p1(...)。
  再看 _build_constraints_for_kind(..., "x" / "y" / "corner")。

src/solvers/solve_airbox_maxwell_3d.py
  看 build_double_floquet_mpc(...) 如何接入求解器，以及 floquet_x/y_face_mismatch 如何写入 summary。
```

### 2B：`pml_airbox`

```text
src/main.py
  看 PML_TOP_THICKNESS_3D、PML_BOTTOM_THICKNESS_3D、PML_ALPHA_3D。

src/runners/run_3d_airbox.py
  看 _stage_defaults("pml_airbox") 如何同时打开 use_floquet_xy 和 use_pml。

src/common/config_3d.py
  看 physical_z_min/max 与 domain_z_min/max 的区别。

src/geometry/mesh_builder_3d.py
  看 top_pml、bottom_pml cell tags 如何由 cell midpoint 标记。

src/common/pml_3d.py
  2B 核心。z_stretch_derivative_value(...) 定义 z 向复拉伸；
  z_pml_tensors(...) 把复拉伸写成 Maxwell 张量。

src/common/analytic_fields_3d.py
  看 pml_complex_z(...) 如何给解析参考场做复坐标延拓。

src/solvers/solve_airbox_maxwell_3d.py
  看 _build_variational_forms(...) 中 top/bottom PML 体积分；
  看 _pml_probe_metrics(...) 中 PML proxy 和 decay ratio 如何计算。
```

### 2C：`fresnel_interface`

```text
src/main.py
  看 N_SUBSTRATE_3D、POLARIZATION_KIND_3D、INCIDENT_THETA_DEG_3D。

src/runners/run_3d_airbox.py
  看 _stage_defaults("fresnel_interface") 如何设置 geometry_kind="fresnel_interface"。

src/common/config_3d.py
  看 s_polarization_vector、p_polarization_vector、substrate_index。

src/common/analytic_fields_3d.py
  2C 核心。fresnel_reference(...) 计算解析 R/T；
  electric_field_code_values(...) 生成平界面总场参考解。

src/geometry/mesh_builder_3d.py
  看 interface_z 如何进入 z-aligned mesh，以及 substrate cell tag 如何标记。

src/solvers/solve_airbox_maxwell_3d.py
  看 _fresnel_numerical_metrics(...) 如何从数值场拟合 R/T；
  看 _stage2_reference_metrics(...) 如何写出 power_metrics_3d.json。

src/test/test_10_stage2_combined.py
  看 n_sub=1 的 no-PML/Floquet 与 Floquet-only 硬 sanity。
```

## 2026-06-19 更新：Stage 2 MPI Floquet side-wide 约束阅读入口

历史记录：这一节记录的是 2026-06-19 的 side-wide 拟合方案，不是当前正式路径。2026-06-22 以后，3D Floquet 已改为显式 edge topology 配对；请优先看本文最上方的新段落。

建议按这个顺序读最新 3D Stage 2 并行路径：

```text
src/main.py
  先看 STAGE_CASE_3D、AIRBOX3D_CASE、SOLVER_PROFILE_3D。

src/runners/run_3d_airbox.py
  看 stage_case 如何自动打开 Floquet、PML 和 Fresnel 几何。

src/common/config_3d.py
  看周期相位、PML 厚度、物理区和计算域 z 范围。

src/geometry/mesh_builder_3d.py
  串行看 z-aligned mesh；MPI 下目前仍 fallback 到 create_box。

src/constraints/floquet_3d.py
  历史方案看 _axis_raw_maps(...) 和 _axis_raw_maps_plane(...)。
  当前方案看 _build_edge_dof_map_p1(...) 和 _build_constraints_for_kind(...)。

src/solvers/solve_airbox_maxwell_3d.py
  看 build_double_floquet_mpc(...) 如何接入求解器，以及 summary 如何记录 mismatch。

src/postprocessing/postprocess_3d.py
  看 ParaView 的 E_V_per_m、H_A_per_m 和 domain_tag 输出。
```

最新验证结果：

```text
floquet_airbox MPI 2 h500: mismatch = 1.18e-15 / 1.34e-15
floquet_airbox MPI 2 h300: mismatch = 3.75e-15 / 4.72e-15
pml_airbox MPI 2 h900:     mismatch = 6.20e-16 / 7.13e-16
```

## 2026-06-18 更新：Stage 2 mesh 和 MPI 状态

最新更新放在文档最上方。为了让 Fresnel 界面和 PML 入口在粗网格中也是真实单元面，串行 `src/geometry/mesh_builder_3d.py` 现在使用 z 关键平面对齐的结构化四面体网格。

MPI 下当前暂时回退到 `dolfinx.mesh.create_box`。原因是自定义分布式 z-aligned mesh 在当前 Docker/DOLFINx 栈中触发底层 segfault。这个 fallback 让 MPI smoke 可以继续跑，但 MPI Fresnel/PML 的定量验证仍然不能依赖 z-aligned mesh。

当前建议阅读顺序：

```text
src/geometry/mesh_builder_3d.py     先看串行 z-aligned mesh 和 MPI fallback
src/constraints/floquet_3d.py       再看 h500/h300 MPI Floquet 已修复的 side-wide 约束
src/solvers/solve_airbox_maxwell_3d.py
notes/test/stage2_validation_report.md
```

## 2026-06-18 更新：Stage 2 测试与注释阅读顺序

最新更新放在文档最上方。Stage 2 重点代码已经加入结构注释，建议按下面顺序读：

```text
src/main.py
src/runners/run_3d_airbox.py
src/common/config_3d.py
src/common/analytic_fields_3d.py
src/common/pml_3d.py
src/geometry/mesh_builder_3d.py
src/constraints/floquet_3d.py
src/solvers/solve_airbox_maxwell_3d.py
src/postprocessing/postprocess_3d.py
src/test/
```

新增测试目录：

```text
src/test/test_00_units_and_conventions.py
src/test/test_01_plane_wave_tools.py
src/test/test_02_pml_tensor.py
src/test/test_03_fresnel_coefficients.py
src/test/test_04_airbox_dirichlet_pde.py
src/test/test_05_floquet_dof_constraints.py
src/test/test_06_airbox_double_floquet_pde.py
src/test/test_07_pml_airbox_decay.py
src/test/test_08_fresnel_total_field.py
src/test/test_09_fresnel_pml.py
src/test/test_10_stage2_combined.py
```

Level 0 到 Level 3 是默认严格单元测试；Level 4 到 Level 10 是 PDE/综合测试入口，默认跳过，避免普通检查直接占用大量内存。

## 2026-06-18 更新：3D Stage 2 代码阅读顺序

最新更新放在文档最上方。Stage 2 新增 3D 双周期 Floquet、z 向 PML 和 Fresnel 平界面 manufactured reference。建议按下面顺序读：

1. `src/main.py`

先看 3D 区块：

```python
STAGE_CASE_3D = "floquet_airbox"
AIRBOX3D_CASE = "normal"
USE_FLOQUET_XY_3D = None
USE_PML_3D = None
SOLVER_PROFILE_3D = "direct"
```

`STAGE_CASE_3D` 决定跑哪一段：

```text
stage1_airbox
floquet_airbox
pml_airbox
fresnel_interface
stage2_all
```

2. `src/runners/run_3d_airbox.py`

这里把 `--stage-case` 展开成真正的 3D config。重点看 `_stage_defaults(...)`：

```text
floquet_airbox       自动打开 use_floquet_xy
pml_airbox           自动打开 use_floquet_xy 和 use_pml
fresnel_interface    自动设置 geometry_kind="fresnel_interface" 和 n_substrate=1.45
```

3. `src/common/config_3d.py`

这里新增了 Stage 2 的公共参数和派生量：

```text
stage_case
use_floquet_xy
use_pml
pml_alpha
physical_z_min / physical_z_max
domain_z_min / domain_z_max
floquet_phase_x / floquet_phase_y
```

`z_min/z_max` 仍表示物理区上下边界；如果打开 PML，真正计算域由 `domain_z_min/domain_z_max` 向外扩展。

4. `src/geometry/mesh_builder_3d.py`

Stage 2 后这个文件不再只是空气盒外边界标记。它还会生成 cell tags：

```text
air
substrate
top_pml
bottom_pml
```

并且 3D box 网格使用 `shared_facet` ghost mode，为 MPI 边界约束保留邻接信息。

5. `src/constraints/floquet_3d.py`

这是 2A 的核心。当前不能使用 `dolfinx_mpc` 高层 periodic helper，因为它不支持当前 Nedelec H(curl) 向量空间。2026-06-22 以后，3D 正式路线是显式边拓扑配对：

```text
mesh edge -> degree=1 N1curl dof
x/y/corner slave edge -> one master edge
slave = phase * orientation_sign * master
add_constraint(slaves, masters, coeffs, owners, offsets)
```

summary 里的 `floquet_x_face_mismatch` 和 `floquet_y_face_mismatch` 现在记录 edge midpoint pairing error；旧 probe residual 已不再作为 3D Floquet 正式指标。

6. `src/common/analytic_fields_3d.py`

这里集中放 3D 解析参考场：

```text
uniform plane wave
PML complex z coordinate
Fresnel reflection/transmission coefficients
Fresnel total E/H reference field
```

后处理和边界条件都复用这里，避免边界给的是一套公式、误差对比又是另一套公式。

7. `src/common/pml_3d.py`

这里生成 z-only PML 张量。PML 只沿 z 拉伸，x/y 仍然由 Floquet 约束处理。

8. `src/solvers/solve_airbox_maxwell_3d.py`

Stage 1 和 Stage 2 现在共用这个求解入口。阅读重点：

```text
plane_wave_electric_field(...)       插值当前 stage 的解析 E 场
_build_variational_forms(...)        根据 cell tags 装配 air/substrate/PML 弱式
build_double_floquet_mpc(...)        打开 x/y Floquet 时构造 MPC
_floquet_probe_metrics(...)          写入 Floquet mismatch
_pml_probe_metrics(...)              写入 PML proxy 和 decay ratio
_stage2_reference_metrics(...)       写入 Fresnel R/T 字段
```

如果 `use_floquet_xy=True`，强 Dirichlet 边界只施加在 z_min/z_max，且会排除 Floquet slave dof，避免强边界和周期约束互相冲突。

9. `src/postprocessing/postprocess_3d.py`

ParaView 输出继续使用：

```text
E_V_per_m_*
H_A_per_m_*
domain_tag
```

`domain_tag` 现在能区分 air/substrate/top_pml/bottom_pml。

### 已验证情况

本次已实跑：

```text
stage1_airbox serial p1 h300 direct
floquet_airbox normal serial p1 h300 direct
floquet_airbox oblique serial p1 h300 direct
floquet_airbox normal MPI 2 p1 h900 direct
pml_airbox normal serial p1 h350 direct
fresnel_interface normal serial p1 h700 direct, s/p
fresnel_interface normal serial p2 h150 direct, s
fresnel_interface normal serial p2 h300 direct, s, Floquet+PML
floquet_airbox normal MPI 2 p1 h900 direct
floquet_airbox normal MPI 2 p1 h500 direct
floquet_airbox normal MPI 2 p1 h300 direct
pml_airbox normal MPI 2 p1 h900 direct
```

未完成或未通过：

```text
早期 fresnel_interface p1/h700 已运行但 R/T 偏差很大，不能验收
fresnel_interface p2/h150 串行已有收敛趋势，但还需要更细定量扫描
pml_airbox MPI 2 h900 的 Floquet mismatch 已通过，但 PML proxy 仍需参数扫描解释
fresnel_interface p2/h300 Floquet+PML 目前只是粗网格 smoke，R/T 还不能作为最终定量验收
```

下一轮可以继续 Stage 2 小网格参数扫描；如果进入更细网格，应同时关注 side-wide Floquet transform 的内存和耗时。

## 2026-06-18 更新：3D 求解器 profile 修正

最新更新放在文档最上方。本次修正保留直接法，并把它明确为当前 3D 空气盒唯一可靠默认基准：

```text
direct                       当前可靠默认，preonly + lu
default                      兼容别名，等价于 direct
direct_lu                    兼容别名，等价于 direct
iterative_asm_lu             实验，fgmres + asm + local lu
iterative_asm_lu_overlap2    实验，overlap=2，更强但更吃内存
iterative_asm_ilu            诊断，已观察到不可靠收敛
iterative_bjacobi_ilu        诊断，已观察到不可靠收敛
iterative_jacobi             诊断，预条件太弱
iterative_hypre              禁用，避免 BoomerAMG 底层崩溃
```

阅读顺序建议如下：

1. `src/main.py`

先看 3D 区块新增的：

```python
SOLVER_PROFILE_3D = "direct"
SOLVER_RTOL_3D = 1.0e-8
SOLVER_ATOL_3D = 1.0e-12
SOLVER_MAX_IT_3D = 1000
SOLVER_MONITOR_3D = False
```

这些变量会被 `_pycharm_args_3d()` 转成命令行参数。`direct` 是当前可信基准；实验性迭代结果必须和 direct 对比。

2. `src/runners/run_3d_airbox.py`

再看命令行参数。这里新增 `--solver-profile`、`--solver-rtol`、`--solver-atol`、`--solver-max-it`、`--solver-monitor`，然后把覆盖项写入 `SimulationConfig3D`。

3. `src/common/config_3d.py`

然后看 `SimulationConfig3D`。求解器相关字段和几何、入射角、偏振放在同一个 3D 配置类里，后续 3D 光栅、Floquet、PML 会继续沿用这一套配置，不会另起一套入口。

4. `src/solvers/solve_airbox_maxwell_3d.py`

最后看核心实现。`_solver_profile_settings(...)` 把 profile 映射成 PETSc options 和可靠性状态；`run_airbox_3d_case(...)` 会记录请求的 profile、解析后的 profile、实际 PETSc options、KSP 类型、PC 类型、收敛原因、迭代步数、残差、矩阵统计、分阶段耗时和最大内存占用。如果 KSP 不收敛，它会把 case 标记为 failed，并跳过正式后处理和 ParaView 场输出。

`run_summary.json` 新增或重点字段：

```text
case_status
official_result
diagnostic_only
postprocess_skipped
solver_profile
solver_profile_resolved
solver_reliability
solver_experimental
solver_disabled
solver_petsc_options
actual_ksp_type
actual_pc_type
ksp_converged
ksp_converged_reason_name
ksp_iterations
solver_residual_norm
matrix_stats
max_rss_mb
timings_seconds
```

并行注意：这些 profile 仍然走 DOLFINx/PETSc 的分布式装配和求解路径；结果目录仍由 rank0 决定后广播；计时和最大内存用 MPI reduction 汇总。

## 2026-06-17 更新：3D Stage 1、nm 单位和 ParaView 物理单位显示

最新更新放在文档最上方。当前这一段主要记录五件事：

```text
1. 3D Stage 1 空气盒子最小 Maxwell 框架
2. 2D/3D 几何、网格、波长统一使用 nm
3. ParaView 输出按 COMSOL 风格显示 E[V/m] 和 H[A/m]
4. 最新 3D 空气盒和原始 2D 流程的 Python 阅读顺序
5. 3D 空气盒输出分阶段 wall time，便于定位网格、装配、求解和后处理耗时
```

新增或重点更新的 Python 文件如下：

| 文件 | 作用 |
|---|---|
| `src/common/config_3d.py` | 3D 配置入口。包含空气盒子、未来光栅/基座/PML 参数、入射角、偏振、`incident_e0_v_per_m`。 |
| `src/geometry/mesh_builder_3d.py` | 生成 Stage 1 结构化 3D 空气盒子网格，并标记 3D 外边界。 |
| `src/solvers/solve_airbox_maxwell_3d.py` | 3D Nedelec 全矢量 Maxwell 空气盒子求解器，用解析平面波切向边界做 manufactured-solution 验证，并打印分阶段耗时。 |
| `src/runners/run_3d_airbox.py` | 3D Stage 1 命令行 runner，支持 normal/oblique/both、角度、偏振、网格尺寸等覆盖参数。 |
| `src/postprocessing/postprocess_3d.py` | 3D ParaView 后处理，输出 `E_V_per_m_*`、`H_A_per_m_*`、误差数组和 Poynting 方向指标。 |
| `src/common/units.py` | 集中定义真空光速 `VACUUM_C` 和真空阻抗 `VACUUM_ETA0`。 |
| `src/common/config.py` | 2D 配置也统一到 nm，并新增 `incident_e0_v_per_m` 和电/磁场物理显示比例。 |
| `src/postprocessing/postprocess.py` | 2D VTU 中电场数组按 `V/m` 写出，并新增 `H_total_abs_A_per_m`。 |
| `src/main.py` | 保持唯一入口，通过 `SIMULATION_DIMENSION="2d"/"3d"` 切换 2D/3D 路线。 |

建议按下面顺序读代码。

### 最新 3D 空气盒 Stage 1 阅读顺序

1. `src/main.py`

先看 `SIMULATION_DIMENSION="3d"` 这一支。这里不会直接写求解公式，只负责把 PyCharm 顶部变量转成 3D runner 的命令行参数。

2. `src/runners/run_3d_airbox.py`

再看 3D runner 怎么选择 `normal`、`oblique` 或 `both`，以及如何把命令行覆盖项合并到 `SimulationConfig3D`。这个文件回答“这次要跑哪些 3D case，结果写到哪里”。

3. `src/common/config_3d.py`

然后看 3D 配置。重点是 `SimulationConfig3D`、`incident_theta_deg`、`incident_phi_deg`、`polarization_kind`、`direction_vector`、`wavevector`、`polarization_vector`。这里定义的是物理参数和派生量，不装配矩阵。

4. `src/geometry/mesh_builder_3d.py`

接着看 3D 空气盒网格。Stage 1 只生成一个均匀空气长方体，标记 `x_min/x_max/y_min/y_max/z_min/z_max` 六个外边界，后续双周期 Floquet 和上下 PML 会沿着这个边界标签体系继续长出来。

5. `src/solvers/solve_airbox_maxwell_3d.py`

这是 3D Stage 1 的核心。阅读顺序是 `plane_wave_electric_field(...)`，再到 `run_airbox_3d_case(...)`。这里建立 Nedelec 空间，构造解析平面波边界值，装配

```text
curl(mu^-1 curl E) - k0^2 eps_r E = 0
```

并用强切向电场边界做 manufactured-solution 验证。

这个文件还会在 MPI 同步后记录各阶段耗时。并行运行时，打印的是所有 rank 中最慢的 wall time，字段会同时写入 `run_summary.json` 的 `timings_seconds`：

```text
config_validation
mesh_build
function_space_setup
boundary_condition_setup
variational_form_setup
linear_problem_setup
linear_problem_solve
postprocess
elapsed_seconds
```

6. `src/postprocessing/postprocess_3d.py`

最后看 3D 后处理。这里把 Nedelec 解插值到可视化空间，写出 ParaView 文件，并计算 `E_V_per_m_*`、`H_A_per_m_*`、误差和 Poynting 方向指标。

7. `src/common/units.py`

如果只想理解单位显示，最后补看这个小文件。它只放真空常数，`E` 的显示比例来自 `incident_e0_v_per_m`，`H` 的显示比例来自 `incident_e0_v_per_m / eta0`。

### 原始 2D 流程阅读顺序

1. `src/main.py`

先看 `SIMULATION_DIMENSION="2d"` 这一支。这里的 `CALCULATION_METHOD`、`POLARIZATION_TYPE`、`CONSTRAINT_BACKEND`、`PORT_BOUNDARY_MODEL` 决定后面会走 2D 的哪条 solver 分支。

2. `src/runners/run_cases.py`

再看 2D runner。这个文件把用户选择展开成实际 case：例如 scattered、port_total、manual、mpc_official、TE、TM、Robin port、DtN port。它负责循环跑 case、创建输出目录、收集 `run_summary.json`。

3. `src/common/config.py`

然后看 2D 配置。这里定义周期、空气层、基底、光栅、PML、波长、入射角、材料折射率、Floquet 相位、`kx/ky`、`k0`、后处理单位比例。现在这些几何和波长参数都统一是 `nm`。

4. `src/geometry/mesh_builder.py`

接着看 2D Gmsh 网格。这个文件生成矩形周期单元，标记空气、基底、光栅、上下 PML，以及左右 Floquet 边界、上下外边界。

5. `src/common/materials.py` 和 `src/common/pml.py`

然后看材料和 PML。`materials.py` 决定每个区域的介电常数；`pml.py` 给 TM/TE、上/下 PML 生成复坐标拉伸张量或标量系数。

6. `src/constraints/floquet_constraint.py` 或 `src/constraints/floquet_scalar_constraint.py`

再看 Floquet 约束。TM 矢量场主要看 `floquet_constraint.py`；TE 标量场主要看 `floquet_scalar_constraint.py`。这里处理左右周期边界自由度配对和相位因子。

7. `src/solvers/solve_vector_maxwell.py`

如果读 2D TM scattered-field 路线，看这个文件。核心函数是 `run_case(...)`，它会调用 2D mesh、材料、PML、Floquet 约束，然后求散射场，最后和背景场合成总场输出。

8. `src/solvers/solve_port_maxwell.py`

如果读 2D TM port-total 路线，看这个文件。核心函数是 `run_port_case(...)`。Robin 端口和 Fourier DtN 端口都在这里；新的 auxiliary modal port 也是从这里开始理解。

9. `src/solvers/solve_te_maxwell.py`

如果读 2D TE 标量路线，看这个文件。它和 TM 共享很多配置、网格、PML、后处理思想，但未知量是 `Ez` 标量。

10. `src/postprocessing/postprocess.py` 和 `src/postprocessing/power_metrics.py`

最后看 2D 后处理。`postprocess.py` 写 ParaView 场数据和图片；`power_metrics.py` 计算 R/T、衍射级、Poynting 通量等能量诊断。

当前代码内部长度统一使用 `nm`：

```text
period_x, air_height, pml thickness, lambda0, mesh_target_size -> nm
k0 -> 1/nm
```

求解内部仍然使用归一化场，默认一个代码电场单位对应：

```python
incident_e0_v_per_m = 1.0
```

这个参数只控制后处理显示，不改变 Maxwell 方程的矩阵装配。ParaView 输出时使用：

```text
E_physical[V/m] = E_code * incident_e0_v_per_m
H_physical[A/m] = H_code * incident_e0_v_per_m / eta0
eta0 = 376.730313668 ohm
```

2D ParaView 里常看的数组现在是：

```text
E_total_abs            总电场模值，单位 V/m
E_total_Ex_real        Ex 实部，单位 V/m
E_total_Ey_real        Ey 实部，单位 V/m
H_total_abs_A_per_m    总磁场模值，单位 A/m
domain_tag             区域标签
```

3D ParaView 里常看的数组是：

```text
E_V_per_m_abs          电场模值，单位 V/m
H_A_per_m_abs          磁场模值，单位 A/m
E_error_abs_V_per_m    电场误差模值，单位 V/m
H_error_abs_A_per_m    磁场误差模值，单位 A/m
domain_tag             区域标签
```

## 2026-06-16 代码补充：DtN 辅助变量法

这次主要改动在三个文件。

### `src/common/config.py`

新增三个配置：

```python
port_dtn_assembly: str = "auxiliary"
port_use_diffraction_orders: bool = False
port_rayleigh_tolerance: float = 1.0e-6
```

`port_dtn_assembly` 控制 DtN 端口装配方式：

```text
explicit   旧的显式外积 Q^*YQ 方法
auxiliary  新的辅助变量块系统方法
```

`port_use_diffraction_orders=False` 时只选 0 级；`True` 时自动选择上、下端口各自明确传播的衍射级。

### `src/solvers/solve_port_maxwell.py`

阅读顺序建议如下。

1. `_select_dtn_port_modes(...)`

这个函数根据：

```text
alpha_m = kx + 2*pi*m/L
|alpha_m| < n_j*k0
```

分别判断顶部和底部哪些级次传播，并把候选级次、是否传播、是否接近 Rayleigh anomaly 写入 metadata。

2. `_build_dtn_trace_data(...)`

这个函数对选中的每个端口级次生成压缩投影向量：

```text
ell_m,i = integral_Gamma exp(i alpha_m x) conjugate(phi_i,x) dGamma
```

只保存非零自由度编号 `indices` 和对应复数值 `values`，避免保存完整 dense 向量。

3. `_add_fourier_port_operators_explicit(...)`

这是旧方法的新入口。它仍然装配：

```text
A_port,m = (q_m/L) ell_m ell_m^H
```

主要用于和新方法对照。

4. `_add_fourier_port_operators_auxiliary(...)`

这是新增方法。它引入辅助未知量 `a_m`：

```text
A u + q_m ell_m a_m = b
a_m - (1/L) ell_m^H u = 0
```

矩阵是块系统：

```text
[ A   B ] [ u ] = [ b ]
[ C   I ] [ a ]   [ 0 ]
```

消去 `a` 后会回到 explicit 的外积形式，因此两者应当给出相同解。

5. `_solve_manual_with_auxiliary(...)`

这个函数把 Floquet 约束只施加到有限元自由度 `u` 上，对辅助变量使用单位矩阵：

```text
C_aug = block_diag(C_fem, I_aux)
```

然后求：

```text
C_aug^H A_aug C_aug x = C_aug^H b_aug
```

### `src/postprocessing/power_metrics.py`

新增的共同计算核心是：

```python
_compute_tm_dtn_power_from_coefficients(...)
```

它只需要顶部和底部的端口模态幅值字典：

```python
top_ex_coeff[order]
bottom_ex_coeff[order]
```

然后按同一套公式计算 R/T。

`compute_dtn_port_power_metrics(...)` 从压缩 trace 向量重新计算：

```text
a_m = (1/L) ell_m^H u
```

`compute_dtn_auxiliary_power_metrics(...)` 直接读取辅助未知量 `a_m`。这两组结果在小模型中应当一致；如果不一致，优先检查块系统符号、端口投影归一化和线性求解残差。

### 小验证结论

粗网格验证中：

```text
explicit + 0级:    R+T = 1.000000000000
auxiliary + 0级:   R+T = 1.000000000000
explicit + auto:  R+T = 1.000000000000
auxiliary + auto: R+T = 1.000000000000
```

同一组衍射级下，explicit 和 auxiliary 的端口面 R/T 完全一致到显示精度。

## 2026-06-15 更新：新增 TE 分支和吸收后处理

本次代码主线变为：

```text
TM scattered:
  src/main.py -> run_cases.py -> solve_vector_maxwell.run_case()

TM port:
  src/main.py -> run_cases.py -> solve_port_maxwell.run_port_case()

TE scattered:
  src/main.py -> run_cases.py -> solve_te_maxwell.run_te_case()

TE port:
  src/main.py -> run_cases.py -> solve_te_maxwell.run_te_port_case()
```

重点文件：

| 文件 | 新增作用 |
|---|---|
| `src/solvers/solve_te_maxwell.py` | 新增 TE 标量 `Ez` 求解器，包含 scattered、Robin port、DtN port。 |
| `src/constraints/floquet_scalar_constraint.py` | 新增标量 Floquet 手写消元约束。标量 Lagrange dof 没有 Nedelec 方向符号，因此只按 y 坐标配对并乘 Floquet 相位。 |
| `src/common/pml.py` | 新增 `top_scalar_pml_coefficients()` 和 `bottom_scalar_pml_coefficients()`，用于 TE scalar PML。 |
| `src/postprocessing/postprocess.py` | 新增 `save_scalar_fields_and_plots()`，输出 `Ez_real/Ez_imag/E_total_abs` 等 ParaView 数组。 |
| `src/postprocessing/power_metrics.py` | `compute_power_metrics()` 现在会根据 `cfg.polarization_type` 在 TM 和 TE 后处理之间分支，并输出吸收率。 |
| `src/runners/run_cases.py` | 新增 `--polarization-type`，输出目录名新增 `tm` 或 `te`。 |
| `src/main.py` | 新增 `POLARIZATION_TYPE`，PyCharm 直接运行时可切换 TM/TE。 |

TE 的弱式核心是：

```text
int grad(Ez) . conj(grad(v)) dOmega
- k0^2 int epsilon_r Ez conj(v) dOmega
```

TE scattered 右端项是：

```text
k0^2 int (epsilon_actual - epsilon_background) Ez_background conj(v) dOmega
```

TE 端口后处理中使用：

```text
Hx_scaled = dEz/dy / i
Ez_down = 1/2 (Ez_m - Hx_scaled_m / beta_m)
Ez_up   = 1/2 (Ez_m + Hx_scaled_m / beta_m)
```

端口总场法现在会显式禁止：

```text
port_use_pml=True
```

因为当前端口弱式只在 `air/substrate/grating` 上装配体积分，没有给 PML 单元装配 Maxwell/PML 项。直接禁止比生成一个看似正常但自由度悬空的结果更可靠。

# 当前代码讲解

本文对应当前空气-基座-光栅算例。代码主线是：

```text
配置参数 -> Gmsh 网格 -> 材料函数 -> Nedelec 空间
-> 入射场 -> Floquet 约束 -> Maxwell 弱式 -> 两种后端求解
-> 输出图像和 JSON 摘要
```

## 总公式

未知量是散射场：

```text
E_scat = (Ex, Ey)
```

总场为：

```text
E_total = E_inc + E_scat
```

二维 Maxwell 散射场方程：

```text
curl(curl(E_scat)) - k0^2 epsilon_r E_scat
  = k0^2 (epsilon_r - epsilon_air) E_inc
```

二维 in-plane curl：

```text
curl(E) = dEy/dx - dEx/dy
```

Floquet 条件：

```text
E(x + period_x, y) = exp(i kx period_x) E(x, y)
```

## `src/common/config.py`

| 功能块 | 讲解 |
|---|---|
| `Tags` | 定义物理标签：空气、基座、光栅、上下 PML、左右 Floquet 边界、外上下边界。 |
| 几何和波长 | `period_x`、`air_height`、PML 厚度、光栅尺寸、`lambda0`、`mesh_target_size` 全部使用 `nm`。 |
| 材料 | `n_air`、`n_substrate`、`n_grating` 通过 `epsilon = n^2` 转成相对介电常数。 |
| 运行选择 | `calculation_method`、`constraint_backend`、`port_boundary_model`、`polarization_type` 控制散射场/端口法、官方 MPC/手写消元、TM/TE。 |
| 端口和衍射级 | `port_incident_amplitude` 是求解中的归一化入射幅值；`port_dtn_order_count` 和 `port_use_diffraction_orders` 控制 DtN 端口级次。 |
| 物理单位显示 | `incident_e0_v_per_m` 控制 ParaView 物理单位显示；默认 1 个代码电场单位显示为 `1 V/m`。 |
| 派生量 | `k0=2*pi/lambda0`，单位 `1/nm`；`omega` 用 `lambda0 * 1e-9` 换回 SI；`magnetic_field_scale_A_per_m = incident_e0_v_per_m / eta0`。 |
| Floquet | `kx`、`ky`、偏振向量和 `floquet_phase=exp(i*kx*period_x)` 都由入射角和周期自动计算。 |
| 几何边界 | 统一给出物理区域、PML 区域、周期边界、基座和光栅上下左右边界。 |
| `as_jsonable()` | 把复数拆成 `[real, imag]`，并记录 `length_unit=nm`、`electric_field_unit=V/m`、`magnetic_field_unit=A/m`。 |

## `src/geometry/mesh_builder.py`

| 行号 | 讲解 |
|---|---|
| 15-16 | 根据长度和目标网格尺寸估算 transfinite curve 节点数。 |
| 19-24 | 初始化 Gmsh 模型。 |
| 28-36 | 定义结构化分块坐标：x 方向为左边界、光栅左边、光栅右边、右边界；y 方向为下 PML、基座、光栅高度、上方空气、上 PML。 |
| 38-59 | 创建所有点、水平线和竖直线，并设置每段线的网格节点数。左右边界有相同纵向分段，方便 Floquet 配对。 |
| 61-67 | 准备按标签收集二维 surface。 |
| 68-79 | 遍历每个矩形小块，创建 surface。 |
| 81-95 | 给 surface 分类：最下层是 bottom PML，最上层是 top PML，基座层横向贯穿全周期，光栅只在中心列，其余是空气。 |
| 97-106 | 给二维区域添加 Gmsh physical group。 |
| 108-131 | 给左/右 Floquet 边界和上下外边界添加一维 physical group。 |
| 133-136 | 生成网格并转换为 DOLFINx mesh。 |
| 140-145 | 尝试写出 `mesh.xdmf`。 |

## `src/common/materials.py`

| 行号 | 讲解 |
|---|---|
| 10-13 | 创建 DG0 空间，每个单元一个常数介电常数。 |
| 14 | 所有单元先设为空气。 |
| 16-18 | 找到基座和光栅单元，分别写入 `eps_substrate` 和 `eps_grating`。 |
| 19 | 返回 `epsilon_r`。 |

## `src/common/pml.py`

| 行号 | 讲解 |
|---|---|
| 8-10 | 把二维 in-plane 场的 curl 写成三维向量 `(0,0,dEy/dx-dEx/dy)`。 |
| 13-14 | 把 `(Ex,Ey)` 扩展为 `(Ex,Ey,0)`。 |
| 17-22 | `_pml_coordinate` 实现官方 DOLFINx PML demo 中的复坐标公式 `x' = x + i alpha/k0 x (|x|-l_dom/2)/(l_pml/2-l_dom/2)^2`。 |
| 25-31 | `_y_pml_coordinate` 先把本项目的 y 坐标平移到物理区域中心，再套用官方公式，最后平移回原坐标。 |
| 34-40 | `_pml_tensors_from_coordinate_map` 对复坐标映射求 Jacobian，并由它得到各向异性的 `epsilon_pml` 和 `mu_pml`。 |
| 43-46 | 顶部 PML 使用空气介电常数，是空气向上的复坐标延拓。 |
| 49-52 | 底部 PML 使用基座介电常数，是基座向下的复坐标延拓。 |

## `src/constraints/floquet_constraint.py`

| 行号 | 讲解 |
|---|---|
| 14-21 | `FloquetConstraintData` 保存 slave dof、master dof、复系数、理论相位、方向符号和配对误差。 |
| 24-30 | `_facet_dof` 确认一阶 Nedelec 边界边只有一个边自由度。 |
| 33-52 | 读取左右边界 facet，按中点 y 坐标排序并配对。 |
| 54-62 | 构造探针场 `E_probe=(0, exp(i*kx*x))` 并插值到 Nedelec 空间。 |
| 70-81 | 对每对左右边求 `scale = dof_right(E_probe)/dof_left(E_probe)`。这个 scale 同时包含 Floquet 相位和 Nedelec 边方向符号。 |
| 83-90 | 返回约束数据。 |
| 93-120 | 手写矩阵消元：构造 `u=Cq`，求解 `C^H A C q = C^H b`，再恢复 `u`。 |
| 123-128 | 计算 Floquet mismatch：`||E_right-scale*E_left|| / characteristic_norm`。 |

## `src/solvers/solve_vector_maxwell.py`

| 行号 | 讲解 |
|---|---|
| 25-27 | 把 PETSc 矩阵转换为 SciPy CSR，供手写矩阵版本使用。 |
| 30-37 | JSON 序列化辅助函数。 |
| 40-52 | 构造入射场 `E_inc = p exp(i(kx x + ky y))`。 |
| 55-96 | 官方 `dolfinx_mpc` 后端。第 61 行创建 MPC 对象，第 67 行加入 slave/master/scale 约束，第 71-84 行用 `dolfinx_mpc.LinearProblem` 装配和求解。 |
| 99-147 | 官方自动周期 helper 探测后端。这个函数保留用于说明和测试，但当前 Nedelec 空间会触发 `Periodic conditions for vector valued spaces are not implemented`，所以不是正式运行后端。 |
| 150-158 | 手写矩阵后端调用 `solve_with_constraints`，返回 reduced residual。 |
| 161-184 | `run_case` 开始：创建输出目录、日志、检查 complex PETSc，并打印波矢、偏振和 Floquet 相位。 |
| 186-203 | 生成网格、创建 `N1curl` 空间、材料函数、入射场和 Floquet 约束数据。 |
| 205-211 | 创建 trial/test 函数和积分区域。物理区域包括空气、基座和光栅；顶部 PML 和底部 PML 分开积分。 |
| 213-214 | 生成顶部空气 PML 张量和底部基座 PML 张量。 |
| 215-223 | 建立 Maxwell 弱式。第 216-217 行是物理区 `curl curl - k0^2 epsilon E`；第 218-221 行分别加入顶部和底部 PML 贡献；第 223 行是散射源项。 |
| 225-232 | 选择官方 MPC 后端。正式双版本运行使用 `mpc_official`，不是 `mpc_auto`。 |
| 233-247 | 选择手写矩阵后端：装配完整矩阵和向量，再做消元。 |
| 251-253 | 计算总场 `E_total = E_inc + E_scat`。 |
| 255-259 | 输出图像和 VTX/BP 文件，并计算散射比、Floquet mismatch、耗时。 |
| 257-288 | 写入 `run_summary.json` 的内容。 |
| 290-305 | 写日志和 JSON 文件。 |

## `src/postprocessing/postprocess.py`

| 功能块 | 讲解 |
|---|---|
| PyVista plotter | 使用离屏渲染，适合 Docker 无显示器环境。 |
| 网格和材料图 | 保存 `mesh.png` 和 `material_domains.png`。 |
| 电场数组 | 给 ParaView 输出 `E_total_abs`、`E_total_Ex_real`、`E_total_real` 等完整前缀数组，数值按 `V/m` 显示。 |
| 区域数组 | 给 ParaView 输出 cell data，目前保存 `domain_tag` 和 `material_id`。 |
| 单位 metadata | 写入 `length_unit_nm`、`electric_field_unit_V_per_m`、`incident_e0_V_per_m`、`magnetic_field_unit_A_per_m`、`magnetic_field_scale_A_per_m`。 |
| 2D 磁场模 | TM 用 `Hz = curl(E)/(i*k0)`，TE 用平面内 `H = (dEz/dy, -dEz/dx)/(i*k0)`，再乘 `incident_e0_v_per_m/eta0`，写成 `H_total_abs_A_per_m`。 |
| 单文件输出 | 串行时保存 `fields_for_paraview.vtu`，这是当前推荐打开的 ParaView 文件。 |
| MPI 输出 | 并行时写出 `fields_for_paraview_parallel.pvd` 和 `fields_for_paraview_rankXXXX.vtu`。在 ParaView 中打开 `.pvd` 可看到完整分布式结果。 |
| TM 路径 | 把 Nedelec 场插值到 DG 向量空间，写出 `E_inc.bp`、`E_scat.bp`、`E_total.bp`，并保存 Ex/Ey、总场模值、散射场模值和箭头图。 |
| TE 路径 | 标量 Ez 后处理，写出 Ez 实虚部、总场模值、散射场模值，并额外输出 TE 的 `H_total_abs_A_per_m`。 |

## `src/postprocessing/postprocess_3d.py`

| 功能 | 讲解 |
|---|---|
| `_plane_wave_values()` | 解析电场按 `incident_e0_v_per_m` 缩放后写成 `V/m`。 |
| `_exact_h_values()` | 解析磁场先用 `k x p / k0` 得到代码单位，再乘 `incident_e0_v_per_m/eta0` 写成 `A/m`。 |
| `save_airbox_3d_fields()` | 将 Nedelec 解插值到 DG 向量空间；输出 `E_V_per_m_*`、`H_A_per_m_*`、误差数组和 `domain_tag`。 |
| `run_summary.json` | 记录 `max_abs_E`、`max_abs_H`、`mean_poynting_W_per_m2` 和 `poynting_direction_cosine`。 |

## `src/main.py`

| 行号 | 讲解 |
|---|---|
| 1-8 | 导入 `sys` 和 `Path`，为 PyCharm 直接以脚本方式运行做准备。 |
| 16-52 | PyCharm 直接运行时最常改的控制变量，例如 `CALCULATION_METHOD`、`CONSTRAINT_BACKEND`、`MESH_TARGET_SIZE`、`INCIDENT_ANGLE_DEG`。 |
| 55-66 | 自动把 v2 项目的上一级目录加入 `sys.path`，这样直接运行 `src/main.py` 也能正确导入包。 |
| 69-102 | 把上面的 Python 变量转换成和命令行完全一致的参数列表。 |
| 105-116 | 如果没有命令行参数，就使用 PyCharm 控制变量；如果有 `--help` 或其他命令行参数，就交给 `src/runners/run_cases.py` 正常解析。 |

## 两个单独入口

| 文件 | 作用 |
|---|---|
| `src/runners/run_grating_mpc_official.py` | 只运行官方 `dolfinx_mpc` 约束装配版本。 |
| `src/runners/run_grating_manual.py` | 只运行手写矩阵消元版本。 |

## `Dockerfile.mpc` 和脚本

| 文件 | 讲解 |
|---|---|
| `Dockerfile.mpc` | 基于 `ghcr.io/jorgensd/dolfinx_mpc:v0.10.5`，额外安装 `pyvista`。 |
| `run_demo_mpc.sh` | 如果镜像不存在就构建，然后运行 `run_cases --constraint-backend both`。 |
| `run_demo.sh` | 使用原 `code-dolfinx` compose 环境，只跑手写矩阵版本。 |

## 最重要的自检点

1. `solve_vector_maxwell.py` 第 191 行仍然是 `N1curl`。
2. `solve_vector_maxwell.py` 第 209 行物理域包含 `air/substrate/grating`。
3. `solve_vector_maxwell.py` 第 210-214 行把 top PML 和 bottom PML 分开，并分别使用空气和基座背景材料。
4. `solve_vector_maxwell.py` 第 216-223 行仍然是 Maxwell 散射场弱式。
5. `floquet_constraint.py` 第 70-81 行仍然用探针场处理 Nedelec 方向符号。
6. `run_summary.json` 里的 `floquet_mismatch_total_dof` 应接近 `1e-15`。
7. `backend_comparison.json` 里的两个后端最大场强差应接近 `1e-14` 量级。

## 2026-06-15 代码补充：DtN 端口面 R/T 后处理

本次新增的目标是：当端口法使用 `port_boundary_model="dtn"` 时，除了保留原来的水平探测线 R/T，还要直接复用 DtN 端口矩阵中的边界积分投影向量，计算一组端口模态 R/T。

主要改动在：

```text
src/postprocessing/power_metrics.py
src/solvers/solve_port_maxwell.py
```

### `power_metrics.py`

新增函数：

```python
compute_dtn_port_power_metrics(mesh_data, cfg, E_total, out_dir)
```

它只在 DtN 端口法中使用，输出：

```text
dtn_port_power_metrics.json
dtn_port_diffraction_orders.csv
dtn_port_diffraction_orders.json
```

计算步骤是：

```text
1. DtN 端口矩阵装配时，对每个级次 m 已经生成 ell_m 边界积分向量
2. 代码马上把 dense ell_m 压缩成 indices + values
3. 后处理复用压缩 ell_m，对有限元解向量 u 做内积，得到 Ex_top,m 和 Ex_bottom,m
4. 上端口：Ex_top,m 减去已知入射基模，得到反射模态幅值
5. 下端口：Ex_bottom,m 直接作为透射模态幅值
6. 用 Y_m = (k0 n)^2 / beta_m 把模态幅值转换成功率
```

对应公式：

```text
ell_m,j = ∫_port exp(i alpha_m x) conj(phi_j,x) ds
Ex_m = (1/period) sum_j u_j conj(ell_m,j)
R_amp,m = [Ex_top,m - delta_m0 Ex_inc,m] exp(-i beta_top,m y_top)
T_amp,m = Ex_bottom,m exp(i beta_bottom,m y_bottom)
P_m = period * 1/2 * Re(Y_m) * |amplitude_m|^2
```

这样做比“在端口附近再画一条采样线”更干净，因为后处理和 DtN 边界条件使用同一个投影算子，避免了额外点采样、插值和边界碰撞判断误差。

### 压缩 trace 向量

早期代码为了写起来简单，曾经直接保存：

```python
trace_vectors[side][order] = ell.copy()
```

其中 `ell` 是完整 dense 向量，长度等于整个有限元空间的自由度数。大规模算例中这个做法不合适，因为端口 trace 向量的非零项只集中在端口边界自由度附近。

现在代码改为：

```python
trace = _compress_trace_vector(ell)
trace_vectors[side][order] = trace
```

`trace` 内部只保存：

```text
indices  非零自由度编号
values   非零复数值
size     原始 dense 长度
cutoff   压缩阈值
```

矩阵外积由：

```python
_compressed_outer_trace_triplets(trace, coefficient)
```

生成 COO 三元组。它不再访问完整 `ell`，而是直接使用：

```text
rows = repeat(indices)
cols = tile(indices)
data = coefficient * values_i * conj(values_j)
```

早期写法是每个端口、每个级次都先生成一个稀疏矩阵，然后反复做：

```python
A_port = A_port + A_mode
```

这会制造很多中间稀疏矩阵副本。现在改为把所有级次的 `rows/cols/data` 暂存在列表里，最后一次性构造：

```python
A_port = sparse.coo_matrix((all_data, (all_rows, all_cols)), shape=A_csr.shape).tocsr()
```

这样总的非零项数学上不变，但减少了多次稀疏矩阵相加带来的临时内存峰值。

入射端口源项也使用：

```python
_add_compressed_trace_to_rhs(...)
```

只更新 `b_out[indices]`。DtN 端口 R/T 后处理同样只用压缩向量：

```text
Ex_m = (1/period) sum(solution[indices] * conj(values))
```

运行摘要 `run_summary.json` 的 `port_modes` 中会记录：

```text
num_trace_dofs
port_outer_nnz
dense_trace_size
trace_compression_ratio
trace_vector_storage
trace_cutoff
```

这些字段可以用来确认压缩是否生效。比如小网格验证中，`dense_trace_size=433`，`num_trace_dofs=8`，`port_outer_nnz=64`，压缩比例约为 `0.0185`。

### ParaView 后处理网格复用

早期 `postprocess.py` 在保存 ParaView 数据时，会为 `E_total`、`E_scat`、`E_inc` 各调用一次：

```python
plot.vtk_mesh(V_dg)
```

这会重复生成同一个 DG 可视化网格的拓扑、单元类型和坐标数组。现在改成：

```python
grid, coords = _field_grid(V_dg)
total_values = _field_values(E_total_dg, grid.n_points)
scat_values = _field_values(E_scat_dg, grid.n_points)
inc_values = _field_values(E_inc_dg, grid.n_points)
```

也就是可视化网格只构造一次，三个场只读取各自的系数数组。输出文件内容不变，但大网格后处理时少了两份重复的 VTK 网格临时数组。

### `solve_port_maxwell.py`

端口法求解完成后仍然先调用：

```python
power_metrics = compute_power_metrics(mesh_data, cfg, E_total, out_dir)
```

这会生成原来的水平探测线结果。

如果当前端口模型是 DtN，`_add_fourier_port_operators(...)` 会返回 `port_trace_vectors`，随后额外调用：

```python
dtn_port_power_metrics = compute_dtn_port_power_metrics(
    mesh_data, cfg, E_total, out_dir, port_trace_vectors
)
```

并把结果写进 `run_summary.json`：

```text
power_metrics                         水平探测线法
dtn_port_power_metrics                DtN 端口面法
dtn_port_vs_probe_power_difference    端口面法减去水平线法的 R/T 差值
```

因此，同一个 DtN 结果目录里现在会同时看到两套 R/T 数据。和 COMSOL 的 Periodic Port 对比时，优先看 `dtn_port_power_metrics.json`；调试内部场分解和采样线稳定性时，再看 `power_metrics.json`。

## 2026-06-09 代码补充：端口总场法

本文件前面的讲解以原来的散射场法为主。现在新增了端口总场法，代码主线变成：

```text
散射场法：src/main.py -> run_cases -> solve_vector_maxwell.run_case
端口法：  src/main.py -> run_cases -> solve_port_maxwell.run_port_case
```

新增或改动的文件如下。

| 文件 | 新增作用 |
|---|---|
| `src/solvers/solve_port_maxwell.py` | 直接求解 `E_total`，可选择 Robin 基模端口或 Fourier DtN 多级次端口。 |
| `src/common/output_paths.py` | 为每次运行生成带时间戳的唯一结果目录。 |
| `src/main.py` | PyCharm 直接运行入口；文件开头的大写变量会转换成运行参数，再调用 `src/runners/run_cases.py`。 |
| `src/common/config.py` | 集中定义运行选择、材料、几何、端口模型、DtN 级次数、唯一输出目录等参数。 |
| `src/geometry/mesh_builder.py` | 根据 `use_pml` 决定是否生成上下 PML 区域；上下外边界仍保留为端口边界标签。 |
| `src/runners/run_grating_manual.py` | 仍只运行手写矩阵版，但输出目录改为唯一目录。 |
| `src/runners/run_grating_mpc_official.py` | 仍只运行官方 MPC 版，但输出目录改为唯一目录。 |

端口法求解的强形式可以简写为：

```text
curl curl(E_total) - k0^2 epsilon_r E_total = 0
```

端口边界把上方入射波写入右端项。对当前二维 in-plane 电场，边界上的简化关系可写成：

```text
top:    curl(E_total) + q_air E_total,x = 2 q_air E_inc,x
bottom: curl(E_total) - q_sub E_total,x = 0
```

其中：

```text
q_air = -i k_air^2 / beta_air
q_sub = -i k_sub^2 / beta_sub
beta = sqrt(k^2 - kx^2)
```

完整的强形式、弱形式、端口符号为什么这样取，以及 `solve_port_maxwell.py` 的逐行讲解，见：

```text
../theory/port_total_formulation_and_run_management.md
```

如果命令行加入：

```text
--port-order-count N
```

会临时覆盖 `config.py` 里的 `port_dtn_order_count`。更推荐直接在 `config.py` 中设置：

```python
port_boundary_model = "dtn"
port_dtn_order_count = N
```

`solve_port_maxwell.py` 会额外启用下面几个函数：

| 函数 | 作用 |
|---|---|
| `_fourier_trace_vector` | 在端口边界上装配 `∫ exp(i alpha_m x) conj(v_x) ds`，得到每个 Floquet 级次的 trace 向量。 |
| `_sparse_outer_trace` | 用 trace 向量构造低秩端口矩阵块，避免把整个有限元矩阵做成稠密矩阵。 |
| `_add_fourier_port_operators` | 对上、下端口的 `m=-N...N` 级次求和，把非局部 Fourier 端口算子加到矩阵和右端项里。 |

多级次端口目前只支持：

```text
--constraint-backend manual
```

现在 `run_cases.py` 的默认值来自 `SimulationConfig`，也就是：

```python
calculation_method
constraint_backend
scattering_background
port_boundary_model
port_dtn_order_count
unique_output
```

所以 PyCharm 中可以只运行模块，不填参数。完整配置式运行说明见：

```text
../quick_start/config_driven_run_guide.md
```

## 2026-06-09 代码补充：反射率和透射率后处理

新增文件：

```text
src/postprocessing/power_metrics.py
```

它从 `E_total` 统一计算散射场法和端口总场法的：

```text
R_total
T_total
R_m / T_m
反射/透射复振幅相位
```

`solve_vector_maxwell.py` 和 `solve_port_maxwell.py` 都会调用：

```python
compute_power_metrics(mesh_data, cfg, E_total, out_dir)
```

所以两种求解方法输出同样格式的：

```text
power_metrics.json
diffraction_orders.csv
diffraction_orders.json
```

`run_cases.py` 会把每个 case 的 R/T 汇总进：

```text
backend_comparison.json
```

最常用的新命令是：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation port_total --constraint-backend both"
```

### 新版 `power_metrics.py` 的关键步骤

新版功率后处理的核心不是只看 `Ex`，而是先恢复缩放后的磁场：

```text
Hz_scaled = (dEy/dx - dEx/dy) / i
```

代码中对应的主要函数是：

```python
_line_field_and_scaled_hz(...)
```

早先临时尝试过在探测线附近用点值有限差分近似导数，但粗网格下误差偏大。现在正式实现改成：用 UFL 对有限元函数直接写出

```text
(dEy/dx - dEx/dy) / i
```

并把它插值到 DG 空间，生成 `Hz_scaled`。这样 `Hz` 来自有限元函数本身的单元内导数，而不是额外的点值差分。

采样 `E` 和 `Hz_scaled` 时，因为左右边界是 Floquet 准周期边界，靠近周期边界的横向坐标仍然要补上相位：

```text
E(x + period, y) = exp(i kx period) E(x, y)
```

这部分由：

```python
_wrap_x_values(...)
_sample_field_on_wrapped_line(...)
```

处理。

随后代码对 `Ex` 和 `Hz_scaled` 同时做 Fourier 投影：

```text
Ex_m = mean(Ex exp(-i alpha_m x))
Hz_m = mean(Hz exp(-i alpha_m x))
```

并用模态导纳：

```text
Y_m = (k0 n)^2 / beta_m
```

拆分上下行波：

```text
Ex_down = 1/2 (Ex_m + Hz_m / Y_m)
Ex_up   = 1/2 (Ex_m - Hz_m / Y_m)
```

顶部空气线上的 `Ex_up` 用来算反射，底部基座线上的 `Ex_down` 用来算透射。每个传播级次的功率为：

```text
P_m = period * 1/2 * Re(Y_m) * |Ex_m|^2
```

所以 `power_metrics.json` 里的：

```text
R_total
T_total
R_plus_T
```

现在来自 `Ex+Hz` 的模态功率，而不是旧版的单独 `Ex` 估算。

同时还会保存直接 Poynting 通量诊断：

```text
poynting_R_plus_T_from_net_flux
top_flux_y_weighted
bottom_flux_y_weighted
```

如果 `R_plus_T` 和 `poynting_R_plus_T_from_net_flux` 都接近 1，说明功率守恒比较可信；如果二者互相差很多，优先检查网格、探测线位置、衍射级次数和边界条件。

# v2 代码阅读提示

v2 已经把旧版 `src` 里的代码按功能拆开。阅读时建议先看：

```text
src/common/config.py
src/geometry/mesh_builder.py
src/constraints/floquet_constraint.py
src/solvers/solve_vector_maxwell.py
src/solvers/solve_port_maxwell.py
src/postprocessing/power_metrics.py
src/postprocessing/postprocess.py
src/runners/run_cases.py
```

顶层 `src` 现在只保留 `main.py` 作为 PyCharm/命令行统一入口，真正实现已经移动到各功能子目录。并行 Floquet 的重点在 `src/constraints/floquet_constraint.py`：MPI 下每个 rank 只约束自己拥有的右边界 slave，自由度 master 使用全局编号和 owner rank。
