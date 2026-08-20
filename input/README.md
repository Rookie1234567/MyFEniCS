# Task38 public input manual (T7 ordinary preset migration)

本目录定义 Task38 的第一版公开输入合同。当前已提供纯 Python 的 `.dat` load/validate/resolve API、手写白名单、参数说明、四个 TOML 模板和 T3 薄 launcher。Full3D direct、Hybrid direct、Hybrid iterative 以及普通 2D 的 adapter 只在各自已审能力范围内接线；本轮 T7 迁移 preset 并不等于任何数值或 production qualification。

## 1. 使用边界

每个 `.dat` 文件只描述一次运行，格式是 Python 标准库 `tomllib` 可读的 TOML。文件不能包含 `runs`、`batch`、内部 PETSc 选项、authority 路径/hash、QEP/lifecycle 参数或任意 Python 表达式。复数使用 `[real, imag]` 两元素数组，例如 `n_air = [1.0, 0.0]`。

当前主命令为 `python scripts/run_case.py input/path/to/case.dat`，辅助命令为 `python scripts/run_case.py input/path/to/case.dat --validate-only` 与 `python scripts/run_case.py input/path/to/case.dat --dry-run`。缺少 `.dat` 时必须显示用法并退出，不能静默运行默认案例。T8 已将11个普通迁移 preset 收薄为同一 dat alias；`src.main --preset <migrated>` 仅作兼容入口，六个 research/history preset 仍保留旧内部 runner/replay。无参 `src.main` 只显示迁移提示并非零退出；直接 2D/3D legacy CLI facade 保留至 T9。

## 2. 顶层身份与九个 section

五个顶层身份键必须恰有一次：`schema_version`、`model_id`、`run_id`、`comparison_group`、`dimension`。其后必须恰有以下九个 section：`geometry`、`materials`、`incidence`、`discretization`、`boundary`、`method`、`solver`、`execution`、`output`。一个文件只表示一个 run；`comparison_group` 只用于把多个独立 run 置于同一比较组，不会自动触发批处理。

`dimension=2` 使用 `2d_scattered` 或 `2d_port`，并且一次只能选择一个 method；`dimension=3` 使用 Full3D/Hybrid method。二维入射角键是 `incidence.tilt_from_downward_y_deg`；代码约定 `kx=sin(theta), ky=-cos(theta)`。三维 Stage4 grating 使用 `grazing_angle_deg` 与 `azimuth_deg`，内部派生 `incident_theta_deg = 90 - grazing_angle_deg`；Stage1/airbox/Fresnel 使用语义明确的 `tilt_from_downward_z_deg`，二者互斥。

3D 现有 stage 映射由 geometry、Floquet 和边界组合决定：airbox + `strong_dirichlet` + 无 Floquet/PML 是 `stage1_airbox`；airbox + `strong_dirichlet` + 双 Floquet 是 `floquet_airbox`；airbox + PML 是 `pml_airbox`；`fresnel_interface` 必须使用 PML；`flat_layer` 映射 `stage4_flat_layer_sanity`；rectangular grating 映射 `stage4_block_grating`。这些是内部 stage 名，不是用户输入键。

`method.requested_modes_per_direction` 是 Hybrid 用户输入；candidate pool、实际动态 DtN 模数、40-mode K、Woodbury/Schur 尺寸、QEP 与生命周期都是 adapter 派生或 internal。`propagation_model`、`traction_model`、`side_residual_correction_steps` 只能取受审有限 enum/组合。`solver` 公开有限 direct profile 和已审 iterative controls；raw PETSc options、未审 PC、authority path/hash 不公开。

九个 section 的职责如下：

| section | 作用 |
| --- | --- |
| `geometry` | 周期、域边界、接口、空气/基底和 grating 尺寸 |
| `materials` | 复折射率、磁导率以及材料标签 |
| `incidence` | 波长、角度、方位、偏振和入射幅值 |
| `discretization` | 有限元阶次、网格形状、目标尺寸和装配约束 |
| `boundary` | Floquet、上下边界、DtN、背景和 PML 选项 |
| `method` | 2D/Full3D/Hybrid method 以及受审接口输入 |
| `solver` | 有限 solver identity 与受审 iterative controls |
| `execution` | MPI、资源告警/终止、超时和 swap policy |
| `output` | 结果目录、field/order/canonical/modal/reference-plane 导出 |

当前 public launcher 命令为（正式数值 adapter 仍按 method capability 受控）：

```text
python scripts/run_case.py input/path/to/case.dat
python scripts/run_case.py input/path/to/case.dat --validate-only
python scripts/run_case.py input/path/to/case.dat --dry-run
```

`--validate-only` 和 `--dry-run` 只做输入解析/计划输出，不启动 PDE；未接线的 method 会 fail closed，不会静默回退到旧 preset 或普通默认。

以下量由 T2/T3 adapter 从公开输入派生，不能写成普通输入键：

| 派生量 | 来源/原因 |
| --- | --- |
| `k0`、`omega`、k-vector | wavelength 与角度的物理派生 |
| S/P polarization vectors | polarization 与 k-vector 的归一化派生 |
| Floquet phases、epsilon | 周期、材料、角度和复折射率派生 |
| grating bounds、mesh counts、DoF | geometry/discretization 的网格构造结果 |
| actual order count | `dtn_order_policy` 与传播性筛选结果 |
| Woodbury K、Schur size、runtime lifecycle | Hybrid adapter/solver 内部容量与生命周期 |

建议的结果身份目录为 `results/<model_id>/<run_id>__<method>__mpi<N>__M<M-or-na>/<timestamp>/`。T3 bootstrap 应保存 `input_original.dat`、`resolved_config.json`、`run_manifest.json`、`input_sha256.txt`、`physical_model_sha256.txt`、`source_sha.txt` 和 `run_summary.json`。provenance bootstrap 属于 T3；solver-specific artifacts 属于 T4–T6，不在 T1 假定已经存在。

角度关系可写成：

```math
\theta_{\mathrm{stage4}} = 90^\circ - \mathrm{grazing\_angle\_deg}.
```

## 3. 参数表

表头固定为：完整键名、类型、单位、是否必填、默认值、允许值、适用范围、通俗含义、内部映射、跨字段限制、示例。`—` 表示没有全局默认或没有枚举限制；条件字段的必填语义写在“跨字段限制”中。下面的机器标记由 focused test 与 schema 精确比对，避免 README 漂移。

| 完整键名 | 类型 | 单位 | 必填 | 默认值 | 允许值 | 适用范围 | 含义 | 内部映射 | 跨字段限制 | 示例 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `schema_version` | `integer` | `version` | yes | `—` | 1 | all | 输入合同版本 | `schema_version` | — | `1` |
| `model_id` | `string` | `none` | yes | `—` | — | all | 模型/案例标识 | `model_id` | safe filename characters [A-Za-z0-9_.-]+ | `"task038_example"` |
| `run_id` | `string` | `none` | yes | `—` | — | all | 单次运行标识 | `run_id` | safe filename characters [A-Za-z0-9_.-]+; must not overwrite an existing result | `"example_run_001"` |
| `comparison_group` | `string` | `none` | yes | `—` | — | all | 可比较运行的分组标识 | `comparison_group` | safe filename characters [A-Za-z0-9_.-]+ | `"task038_examples"` |
| `dimension` | `integer` | `none` | yes | `—` | 2, 3 | all | 问题维数 | `dimension` | — | `3` |
| `geometry.geometry_kind` | `string` | `none` | yes | `—` | euv_grating_2d, layered_2d, airbox, fresnel_interface, flat_layer, rectangular_block_grating | 2d/3d | 形状模型名称 | `geometry_kind` | 2D uses euv_grating_2d/layered_2d; 3D uses airbox/fresnel_interface/flat_layer/rectangular_block_grating | `"rectangular_block_grating"` |
| `geometry.period_x_nm` | `float` | `nm` | yes | `—` | — | 2d/3d | x 方向周期 | `period_x` | > 0 | `50.0` |
| `geometry.period_y_nm` | `float` | `nm` | yes | `—` | — | 3d | y 方向周期 | `period_y` | > 0 | `25.0` |
| `geometry.z_min_nm` | `float` | `nm` | yes | `—` | — | 3d | 三维计算域下界 | `z_min` | < z_max_nm | `-10.0` |
| `geometry.z_max_nm` | `float` | `nm` | yes | `—` | — | 3d | 三维计算域上界 | `z_max` | > z_min_nm | `130.0` |
| `geometry.interface_z_nm` | `float` | `nm` | yes | `—` | — | 3d | 空气与基底接口 z 坐标 | `interface_z` | z_min_nm < value < z_max_nm | `0.0` |
| `geometry.air_height_nm` | `float` | `nm` | yes | `—` | — | 2d/3d | 接口上方空气厚度 | `air_height` | > 0 | `130.0` |
| `geometry.substrate_thickness_nm` | `float` | `nm` | yes | `—` | — | 2d/3d | 接口下方基底厚度 | `substrate_thickness` | >= 0 | `10.0` |
| `geometry.grating_width_x_nm` | `float` | `nm` | no | `—` | — | 2d/3d | grating x 方向宽度 | `2D grating_width / 3D grating_width_x` | >= 0; required only for grating geometry; optional or 0 for non-grating geometry | `17.0` |
| `geometry.grating_width_y_nm` | `float` | `nm` | no | `—` | — | 3d | grating y 方向宽度 | `grating_width_y` | >= 0; required only for 3D grating geometry; optional or 0 otherwise | `25.0` |
| `geometry.grating_height_nm` | `float` | `nm` | no | `—` | — | 2d/3d | grating 高度 | `grating_height` | >= 0; required only for grating geometry; optional or 0 for non-grating geometry | `120.0` |
| `materials.n_air` | `complex_pair` | `relative index` | yes | `—` | — | 2d/3d | 空气复折射率 [实部, 虚部] | `n_air` | — | `[1.0, 0.0]` |
| `materials.mu_r` | `complex_pair` | `relative permeability` | no | `[1.0, 0.0]` | — | 2d/3d | 相对磁导率 [实部, 虚部] | `mu_r` | — | `[1.0, 0.0]` |
| `materials.substrate_name` | `string` | `none` | no | `—` | — | 2d/3d | 基底材料名称 | `substrate_material_label` | optional descriptive label | `"Si / silicon"` |
| `materials.n_substrate` | `complex_pair` | `relative index` | no | `—` | — | 2d/3d | 基底复折射率 | `n_substrate` | required for 2D, Fresnel, flat-layer and block-grating; optional for airbox | `[0.999002304859, 0.00182649365]` |
| `materials.grating_name` | `string` | `none` | no | `—` | — | 2d/3d | grating 材料名称 | `grating_material_label` | optional descriptive label | `"Si / silicon"` |
| `materials.n_grating` | `complex_pair` | `relative index` | no | `—` | — | 2d/3d | grating 复折射率 [实部, 虚部] | `n_grating` | required for 2D and rectangular block-grating; optional for airbox, Fresnel and flat-layer | `[0.999002304859, 0.00182649365]` |
| `incidence.wavelength_nm` | `float` | `nm` | yes | `—` | — | 2d/3d | 真空波长 | `lambda0` | > 0 | `13.5` |
| `incidence.grazing_angle_deg` | `float` | `degree` | no | `—` | — | 3d | 相对表面的掠射角 | `incident_theta_deg = 90 - grazing_angle_deg` | required for Stage4 grating; 0 < value <= 90; mutually exclusive with tilt_from_downward_z_deg | `1.0` |
| `incidence.tilt_from_downward_z_deg` | `float` | `degree` | no | `—` | — | 3d | Stage1/airbox/Fresnel 使用的、相对向下 z 轴的倾角 | `incident_theta_deg` | finite; use for Stage1/Stage2 airbox/Fresnel, mutually exclusive with grazing_angle_deg | `10.0` |
| `incidence.azimuth_deg` | `float` | `degree` | yes | `—` | — | 3d | 入射方位角 | `incident_phi_deg` | finite; method-specific range | `0.0` |
| `incidence.tilt_from_downward_y_deg` | `float` | `degree` | yes | `—` | — | 2d | 二维相对向下 y 轴的显式倾角；代码使用 kx=sin(theta), ky=-cos(theta) | `incident_angle_deg` | finite; 2D convention only | `0.0` |
| `incidence.polarization` | `enum` | `none` | yes | `—` | tm, te, s, p, custom | 2d/3d | 偏振类型 | `polarization_kind / polarization_type` | 2D allows tm/te; 3D allows s/p/custom | `"s"` |
| `incidence.custom_polarization` | `complex_vector3` | `none` | no | `—` | — | 3d | custom 复偏振向量 | `custom_polarization` | 3D only; required exactly when polarization=custom | `[[1.0, 0.0], [0.0, 0.0], [0.0, 0.0]]` |
| `incidence.electric_amplitude` | `float` | `V/m relative` | no | `1.0` | — | 2d/3d | 入射电场幅值 | `incident_amplitude / incident_e0_v_per_m` | >= 0 | `1.0` |
| `discretization.nedelec_degree` | `integer` | `order` | yes | `—` | — | 2d/3d | Nedelec 有限元阶次 | `nedelec_degree` | >= 1 | `6` |
| `discretization.nedelec_trace_degree` | `integer` | `order` | no | `—` | — | 3d | 接口 trace 阶次 | `nedelec_trace_degree` | >= 1; must be supplied with interior degree | `6` |
| `discretization.nedelec_interior_degree` | `integer` | `order` | no | `—` | — | 3d | cell interior 阶次 | `nedelec_interior_degree` | >= 1; must be supplied with trace degree | `6` |
| `discretization.visualization_degree` | `integer` | `order` | no | `2` | — | 2d/3d | 可视化/导出阶次 | `visualization_degree` | >= 1 | `6` |
| `discretization.mesh_target_nm` | `float` | `nm` | yes | `—` | — | 2d/3d | 目标网格尺寸 | `mesh_target_size` | > 0 | `10.0` |
| `discretization.mesh_cell_type` | `enum` | `none` | yes | `—` | auto, triangle, quadrilateral, tetrahedron, hexahedron | 2d/3d | 网格单元类型 | `2D mesh_cell_shape / 3D mesh_cell_type` | 2D allows triangle/quadrilateral; 3D allows auto/tetrahedron/hexahedron | `"hexahedron"` |
| `discretization.mesh_spacing_mode` | `enum` | `none` | no | `auto` | auto, uniform_strict, boundary_fitted, local_refined | 3d | 三维网格尺寸分配策略 | `mesh_spacing_mode` | — | `"boundary_fitted"` |
| `discretization.mesh_refined_size_nm` | `float` | `nm` | no | `—` | — | 3d | 三维局部细化尺寸 | `mesh_refined_size` | > 0 when refinement is enabled | `5.0` |
| `discretization.mesh_refinement_radius_nm` | `float` | `nm` | no | `—` | — | 3d | 三维局部细化半径 | `mesh_refinement_radius` | > 0 when refinement is enabled | `25.0` |
| `discretization.lock_near_field_template` | `boolean` | `none` | yes | `—` | — | 2d | 是否锁定二维近场采样模板 | `mesh_lock_near_field_template` | — | `true` |
| `discretization.near_field_margin_x_nm` | `float` | `nm` | yes | `—` | — | 2d | 二维近场 x 向外扩边 | `near_field_margin_x` | >= 0; mesh-affecting when lock_near_field_template=true | `5.0` |
| `discretization.near_field_air_top_nm` | `float` | `nm` | yes | `—` | — | 2d | 二维近场空气侧上边界 | `near_field_air_top` | > 0; mesh-affecting when lock_near_field_template=true | `20.0` |
| `discretization.near_field_sub_depth_nm` | `float` | `nm` | yes | — | — | 2d | 二维近场基底侧深度 | `near_field_sub_depth` | > 0; mesh-affecting when lock_near_field_template=true | `10.0` |
| `discretization.assembly_backend` | `enum` | `none` | no | `standard_full` | standard_full, assembly_time_static_condensed | 3d | 矩阵装配后端 | `stage4_full3d_assembly_backend` | variable-p remains internal/research-only because no geometry-bound plan is public in v1 | `"assembly_time_static_condensed"` |
| `discretization.floquet_constraint_mode` | `enum` | `none` | no | `auto` | auto, topological_edges, sparse_facet, topological_trace_p2 | 3d | Floquet 约束模式 | `floquet_constraint_mode` | — | `"auto"` |
| `boundary.use_floquet_x` | `boolean` | `none` | no | `false` | — | 2d/3d | 是否施加 x 周期约束 | `2D periodic constraint contract / 3D use_floquet_xy` | 2D requires true; 3D may disable | `true` |
| `boundary.use_floquet_y` | `boolean` | `none` | no | `false` | — | 3d | 是否施加 y 周期约束 | `use_floquet_xy` | 3D y component; x/y values must agree | `true` |
| `boundary.vertical_boundary` | `enum` | `none` | yes | `—` | dtn_port, pml, robin0, strong_dirichlet, dtn, robin | 2d/3d | 上下边界模型 | `stage4_boundary_model / port_boundary_model` | 3D uses dtn_port/pml/robin0; airbox strong_dirichlet maps to Stage1/Floquet airbox, Fresnel requires pml; 2d_port uses dtn/robin; 2d_scattered uses pml | `"dtn_port"` |
| `boundary.scattering_background` | `enum` | `none` | no | `—` | air, layered | 2d/3d | 散射背景的介质层模型 | `scattering_background` | required for 2d_scattered and Stage4 3D; Stage4 currently requires layered; may be omitted for port-only methods | `"layered"` |
| `boundary.dtn_order_policy` | `enum` | `none` | no | `—` | zero_order, auto_propagating | 2d/3d | DtN 阶次选择策略 | `stage4_dtn_order_policy` | required only when vertical_boundary is dtn or dtn_port; 2D port maps to port_use_diffraction_orders; explicit 2D port accepts zero_order or auto_propagating; 2D TE + dtn currently accepts only zero_order; legacy manual is internal/not public v1 | `"auto_propagating"` |
| `boundary.dtn_assembly` | `enum` | `none` | no | `—` | auxiliary, explicit | 2d/3d | DtN 装配方式 | `stage4_dtn_assembly / port_dtn_assembly` | required only when vertical_boundary is dtn or dtn_port | `"auxiliary"` |
| `boundary.use_pml` | `boolean` | `none` | no | `false` | — | 2d/3d | 是否使用 PML | `2D scattered use_pml / 2D port port_use_pml / 3D use_pml` | compatible with vertical_boundary | `false` |
| `boundary.pml_top_thickness_nm` | `float` | `nm` | no | `—` | — | 2d/3d | 顶部 PML 厚度 | `pml_top_thickness` | >= 0; required when use_pml | `25.0` |
| `boundary.pml_bottom_thickness_nm` | `float` | `nm` | no | `—` | — | 2d/3d | 底部 PML 厚度 | `pml_bottom_thickness` | >= 0; required when use_pml | `25.0` |
| `boundary.pml_alpha` | `float` | `dimensionless` | no | `5.0` | — | 2d/3d | PML 吸收强度 | `pml_alpha` | > 0 when use_pml | `5.0` |
| `method.kind` | `enum` | `none` | yes | `—` | 2d_scattered, 2d_port, full3d_direct, full3d_iterative, hybrid_direct, hybrid_iterative | 2d/3d | 求解方法 | `method.kind / runner dispatch` | 2D uses exactly one of 2d_scattered or 2d_port; 3D uses full3d_direct/full3d_iterative/hybrid_direct/hybrid_iterative; no both/all mode | `"hybrid_iterative"` |
| `method.constraint_backend` | `enum` | `none` | yes | `—` | mpc_official, manual, mpc_auto | 2d | 二维约束后端 | `constraint_backend` | one backend only; no both/all compatibility mode | `"mpc_official"` |
| `method.bottom_interface_nm` | `float` | `nm` | yes | `—` | — | hybrid_direct/hybrid_iterative | Hybrid 底部接口位置 | `bottom_interface_nm` | required for Hybrid; < top_interface_nm | `10.0` |
| `method.top_interface_nm` | `float` | `nm` | yes | `—` | — | hybrid_direct/hybrid_iterative | Hybrid 顶部接口位置 | `top_interface_nm` | required for Hybrid; > bottom_interface_nm | `110.0` |
| `method.requested_modes_per_direction` | `integer` | `modes/direction` | yes | `—` | — | hybrid_direct/hybrid_iterative | 用户请求的每方向模态数 | `requested_modes` | required for Hybrid; candidate pool is derived | `120` |
| `method.propagation_model` | `enum` | `none` | yes | `—` | continuous_beta, full3d_uniform_cg | hybrid_direct/hybrid_iterative | Hybrid 内部传播模型 | `internal_propagation_model` | — | `"full3d_uniform_cg"` |
| `method.traction_model` | `enum` | `none` | yes | `—` | continuous_qep_beta, scalar_cg_discrete_derivative, full3d_one_cell_exact_schur | hybrid_direct/hybrid_iterative | Hybrid 接口 traction 模型 | `internal_traction_model` | — | `"full3d_one_cell_exact_schur"` |
| `solver.direct_solver_profile` | `enum` | `none` | yes | `—` | default, mumps_ooc, mumps_blr | full3d_direct/hybrid_direct | 有限 direct solver profile | `petsc_direct_solver_profile` | — | `"default"` |
| `solver.linear_solver` | `enum` | `none` | yes | `—` | direct, fgmres, iterative | 2d_scattered/2d_port/full3d_direct/full3d_iterative/hybrid_direct/hybrid_iterative | 线性求解器类型 | `linear_solver` | direct methods require direct; hybrid_iterative requires fgmres; full3d_iterative requires iterative | `"fgmres"` |
| `solver.ksp_type` | `enum` | `none` | yes | `—` | fgmres | full3d_iterative | Full3D 迭代求解器类型 | `ksp_type` | full3d_iterative fixed profile only | `"fgmres"` |
| `solver.preconditioner` | `enum` | `none` | yes | `—` | full3d_scalable_v1, hybrid_block_ldu_ilu0_dtn_woodbury | full3d_iterative/hybrid_iterative | 公开 preconditioner identity | `preconditioner` | only reviewed iterative identities are public | `"hybrid_block_ldu_ilu0_dtn_woodbury"` |
| `solver.restart` | `integer` | `iterations` | yes | `—` | — | full3d_iterative/hybrid_iterative | GMRES/FGMRES restart 长度 | `restart` | only iterative methods; > 0 | `90` |
| `solver.max_iterations` | `integer` | `iterations` | yes | `—` | — | full3d_iterative/hybrid_iterative | 最大迭代步数 | `max_it` | only iterative methods; > 0 | `4500` |
| `solver.relative_tolerance` | `float` | `relative residual` | yes | `—` | — | hybrid_iterative | 相对残差容差 | `rtol` | only hybrid_iterative; > 0 and finite | `5.0e-9` |
| `solver.absolute_tolerance` | `float` | `absolute residual` | yes | `—` | — | hybrid_iterative | 绝对残差容差 | `atol` | only hybrid_iterative; >= 0 and finite | `0.0` |
| `solver.initial_guess` | `enum` | `none` | yes | `—` | zero | hybrid_iterative | 初始向量策略 | `initial_guess` | — | `"zero"` |
| `solver.ilu_level` | `integer` | `level` | yes | `—` | — | hybrid_iterative | ILU fill level | `ilu_level` | >= 0 | `0` |
| `solver.ilu_shift` | `float` | `dimensionless` | yes | `—` | — | hybrid_iterative | ILU diagonal shift | `ilu_shift` | finite | `0.1` |
| `solver.subdomain_count_per_endcap` | `integer` | `subdomains/endcap` | yes | `—` | — | hybrid_iterative | 每个 endcap 的子域数 | `subdomain_count_per_endcap` | >= 1 | `1` |
| `solver.overlap_fraction` | `float` | `fraction` | yes | `—` | — | hybrid_iterative | 子域重叠比例 | `overlap_fraction` | 0 <= value < 1 | `0.0` |
| `solver.side_residual_correction_steps` | `integer` | `steps` | yes | `—` | 1, 2 | hybrid_iterative | 固定侧向残差修正次数 | `side_residual_correction_steps` | only hybrid_iterative; no fallback | `2` |
| `execution.mpi_size` | `integer` | `MPI ranks` | yes | `—` | — | 2d/3d | 外层 launcher 使用的 MPI 数 | `execution.mpi_size / MPI.COMM_WORLD.size check` | >= 1; worker size must match | `8` |
| `execution.warning_memory_gib` | `float` | `GiB` | yes | `—` | — | 2d/3d | 用户资源警告线 | `watchdog warning threshold` | > 0; generic policy, not authority hard gate | `10.0` |
| `execution.terminate_memory_gib` | `float` | `GiB` | yes | `—` | — | 2d/3d | 用户资源终止线 | `watchdog terminate threshold` | > warning_memory_gib | `14.0` |
| `execution.timeout_seconds` | `integer` | `seconds` | yes | `—` | — | 2d/3d | 单次运行时间上限 | `watchdog timeout` | > 0; generic policy, not authority hard gate | `7200` |
| `execution.memory_limit_gb` | `float` | `GiB` | no | `—` | — | 3d | Full3D 运行内存上限 | `memory_limit_gb` | > 0; required for full3d_iterative | `2.0` |
| `execution.require_zero_swap` | `boolean` | `none` | yes | `—` | — | 2d/3d | 是否要求 swap 为零 | `swap policy` | — | `true` |
| `output.results_root` | `path` | `filesystem path` | yes | `—` | — | 2d/3d | 结果根目录 | `results_root` | must not overwrite an existing run | `"results"` |
| `output.unique_output` | `boolean` | `none` | no | `true` | — | 2d/3d | 是否创建唯一结果目录 | `unique_output` | — | `true` |
| `output.export_fields` | `boolean` | `none` | no | `false` | — | 2d/3d | 导出场字段 | `field export policy` | — | `true` |
| `output.export_diffraction_orders` | `boolean` | `none` | no | `true` | — | 2d/3d | 导出衍射级 | `diffraction output policy` | — | `true` |
| `output.compute_power_metrics` | `boolean` | `none` | yes | `—` | — | 2d | 是否计算二维功率指标 | `compute_power_metrics` | — | `true` |
| `output.power_probe_num_points` | `integer` | `points` | yes | `—` | — | 2d | 二维功率探针采样点数 | `power_probe_num_points` | > 1 | `1001` |
| `output.generate_png_plots` | `boolean` | `none` | yes | `—` | — | 2d | 是否生成二维 PNG 图 | `generate_png_plots` | — | `false` |
| `output.export_canonical_vectors` | `boolean` | `none` | no | `false` | — | 3d | 导出 canonical 向量 | `canonical field export policy` | — | `true` |
| `output.export_modal_amplitudes` | `boolean` | `none` | no | `false` | — | 3d | 导出 modal amplitude | `modal export policy` | — | `true` |
| `output.export_reference_planes` | `boolean` | `none` | no | `false` | — | 3d | 导出 reference planes | `reference plane export policy` | — | `true` |
| `output.reference_plane_z_nm` | `float_array` | `nm` | no | `—` | — | 3d | reference plane 的 z 坐标 | `full3d_reference_plane_z` | required when export_reference_planes | `[10.0, 30.0, 60.0, 90.0, 110.0]` |
| `output.diffraction_sample_count_x` | `integer` | `samples` | no | `24` | — | 3d | 衍射级提取的 x 采样数（不同于 reference plane 采样） | `diffraction_sample_count_x` | > 0 | `24` |
| `output.diffraction_sample_count_y` | `integer` | `samples` | no | `24` | — | 3d | 衍射级提取的 y 采样数（不同于 reference plane 采样） | `diffraction_sample_count_y` | > 0 | `24` |
| `output.top_probe_z_nm` | `float` | `nm` | no | `—` | — | 3d | 顶部衍射探针 z 坐标 | `diffraction_top_probe_z` | optional explicit override | `110.0` |
| `output.bottom_probe_z_nm` | `float` | `nm` | no | `—` | — | 3d | 底部衍射探针 z 坐标 | `diffraction_bottom_probe_z` | optional explicit override | `10.0` |
| `output.probe_fraction` | `float` | `fraction` | no | `0.75` | — | 3d | 探针在相邻区域中的归一化位置 | `diffraction_probe_fraction` | 0 < value < 1; optional when explicit probes are set | `0.75` |
| `output.sample_count_x` | `integer` | `samples` | no | `40` | — | 3d | reference plane x 采样数 | `full3d_reference_sample_count_x` | > 0; required when export_reference_planes | `40` |
| `output.sample_count_y` | `integer` | `samples` | no | `20` | — | 3d | reference plane y 采样数 | `full3d_reference_sample_count_y` | > 0; required when export_reference_planes | `20` |
| `output.diffraction_order_max_m` | `integer` | `order` | no | `—` | — | 2d/3d | 最大 x 衍射级（后处理报告） | `2D diffraction_order_count / 3D reporting_diffraction_order_max_m` | >= 0; required when export_diffraction_orders; never selects PDE DtN modes | `2` |
| `output.diffraction_order_max_n` | `integer` | `order` | no | `—` | — | 3d | 最大 y 衍射级（后处理报告） | `3D reporting_diffraction_order_max_n` | >= 0; required when export_diffraction_orders | `2` |

## Machine-readable schema markers

The following marker block is intentionally outside the table so GitHub keeps all parameter rows in one continuous table. The focused test compares it exactly with the explicit T1 whitelist.

<!-- schema-field {"key":"schema_version","unit":"version","applicability":["all"]} -->
<!-- schema-field {"key":"model_id","unit":"none","applicability":["all"]} -->
<!-- schema-field {"key":"run_id","unit":"none","applicability":["all"]} -->
<!-- schema-field {"key":"comparison_group","unit":"none","applicability":["all"]} -->
<!-- schema-field {"key":"dimension","unit":"none","applicability":["all"]} -->
<!-- schema-field {"key":"geometry.geometry_kind","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"geometry.period_x_nm","unit":"nm","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"geometry.period_y_nm","unit":"nm","applicability":["3d"]} -->
<!-- schema-field {"key":"geometry.z_min_nm","unit":"nm","applicability":["3d"]} -->
<!-- schema-field {"key":"geometry.z_max_nm","unit":"nm","applicability":["3d"]} -->
<!-- schema-field {"key":"geometry.interface_z_nm","unit":"nm","applicability":["3d"]} -->
<!-- schema-field {"key":"geometry.air_height_nm","unit":"nm","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"geometry.substrate_thickness_nm","unit":"nm","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"geometry.grating_width_x_nm","unit":"nm","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"geometry.grating_width_y_nm","unit":"nm","applicability":["3d"]} -->
<!-- schema-field {"key":"geometry.grating_height_nm","unit":"nm","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"materials.n_air","unit":"relative index","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"materials.mu_r","unit":"relative permeability","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"materials.substrate_name","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"materials.n_substrate","unit":"relative index","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"materials.grating_name","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"materials.n_grating","unit":"relative index","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"incidence.wavelength_nm","unit":"nm","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"incidence.grazing_angle_deg","unit":"degree","applicability":["3d"]} -->
<!-- schema-field {"key":"incidence.tilt_from_downward_z_deg","unit":"degree","applicability":["3d"]} -->
<!-- schema-field {"key":"incidence.azimuth_deg","unit":"degree","applicability":["3d"]} -->
<!-- schema-field {"key":"incidence.tilt_from_downward_y_deg","unit":"degree","applicability":["2d"]} -->
<!-- schema-field {"key":"incidence.polarization","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"incidence.custom_polarization","unit":"none","applicability":["3d"]} -->
<!-- schema-field {"key":"incidence.electric_amplitude","unit":"V/m relative","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"discretization.nedelec_degree","unit":"order","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"discretization.nedelec_trace_degree","unit":"order","applicability":["3d"]} -->
<!-- schema-field {"key":"discretization.nedelec_interior_degree","unit":"order","applicability":["3d"]} -->
<!-- schema-field {"key":"discretization.visualization_degree","unit":"order","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"discretization.mesh_target_nm","unit":"nm","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"discretization.mesh_cell_type","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"discretization.mesh_spacing_mode","unit":"none","applicability":["3d"]} -->
<!-- schema-field {"key":"discretization.mesh_refined_size_nm","unit":"nm","applicability":["3d"]} -->
<!-- schema-field {"key":"discretization.mesh_refinement_radius_nm","unit":"nm","applicability":["3d"]} -->
<!-- schema-field {"key":"discretization.lock_near_field_template","unit":"none","applicability":["2d"]} -->
<!-- schema-field {"key":"discretization.near_field_margin_x_nm","unit":"nm","applicability":["2d"]} -->
<!-- schema-field {"key":"discretization.near_field_air_top_nm","unit":"nm","applicability":["2d"]} -->
<!-- schema-field {"key":"discretization.near_field_sub_depth_nm","unit":"nm","applicability":["2d"]} -->
<!-- schema-field {"key":"discretization.assembly_backend","unit":"none","applicability":["3d"]} -->
<!-- schema-field {"key":"discretization.floquet_constraint_mode","unit":"none","applicability":["3d"]} -->
<!-- schema-field {"key":"boundary.use_floquet_x","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"boundary.use_floquet_y","unit":"none","applicability":["3d"]} -->
<!-- schema-field {"key":"boundary.vertical_boundary","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"boundary.scattering_background","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"boundary.dtn_order_policy","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"boundary.dtn_assembly","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"boundary.use_pml","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"boundary.pml_top_thickness_nm","unit":"nm","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"boundary.pml_bottom_thickness_nm","unit":"nm","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"boundary.pml_alpha","unit":"dimensionless","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"method.kind","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"method.constraint_backend","unit":"none","applicability":["2d"]} -->
<!-- schema-field {"key":"method.bottom_interface_nm","unit":"nm","applicability":["hybrid_direct","hybrid_iterative"]} -->
<!-- schema-field {"key":"method.top_interface_nm","unit":"nm","applicability":["hybrid_direct","hybrid_iterative"]} -->
<!-- schema-field {"key":"method.requested_modes_per_direction","unit":"modes/direction","applicability":["hybrid_direct","hybrid_iterative"]} -->
<!-- schema-field {"key":"method.propagation_model","unit":"none","applicability":["hybrid_direct","hybrid_iterative"]} -->
<!-- schema-field {"key":"method.traction_model","unit":"none","applicability":["hybrid_direct","hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.direct_solver_profile","unit":"none","applicability":["full3d_direct","hybrid_direct"]} -->
<!-- schema-field {"key":"solver.linear_solver","unit":"none","applicability":["2d_scattered","2d_port","full3d_direct","full3d_iterative","hybrid_direct","hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.ksp_type","unit":"none","applicability":["full3d_iterative"]} -->
<!-- schema-field {"key":"solver.preconditioner","unit":"none","applicability":["full3d_iterative","hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.restart","unit":"iterations","applicability":["full3d_iterative","hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.max_iterations","unit":"iterations","applicability":["full3d_iterative","hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.relative_tolerance","unit":"relative residual","applicability":["hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.absolute_tolerance","unit":"absolute residual","applicability":["hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.initial_guess","unit":"none","applicability":["hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.ilu_level","unit":"level","applicability":["hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.ilu_shift","unit":"dimensionless","applicability":["hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.subdomain_count_per_endcap","unit":"subdomains/endcap","applicability":["hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.overlap_fraction","unit":"fraction","applicability":["hybrid_iterative"]} -->
<!-- schema-field {"key":"solver.side_residual_correction_steps","unit":"steps","applicability":["hybrid_iterative"]} -->
<!-- schema-field {"key":"execution.mpi_size","unit":"MPI ranks","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"execution.warning_memory_gib","unit":"GiB","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"execution.terminate_memory_gib","unit":"GiB","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"execution.timeout_seconds","unit":"seconds","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"execution.memory_limit_gb","unit":"GiB","applicability":["3d"]} -->
<!-- schema-field {"key":"execution.require_zero_swap","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"output.results_root","unit":"filesystem path","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"output.unique_output","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"output.export_fields","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"output.export_diffraction_orders","unit":"none","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"output.compute_power_metrics","unit":"none","applicability":["2d"]} -->
<!-- schema-field {"key":"output.power_probe_num_points","unit":"points","applicability":["2d"]} -->
<!-- schema-field {"key":"output.generate_png_plots","unit":"none","applicability":["2d"]} -->
<!-- schema-field {"key":"output.export_canonical_vectors","unit":"none","applicability":["3d"]} -->
<!-- schema-field {"key":"output.export_modal_amplitudes","unit":"none","applicability":["3d"]} -->
<!-- schema-field {"key":"output.export_reference_planes","unit":"none","applicability":["3d"]} -->
<!-- schema-field {"key":"output.reference_plane_z_nm","unit":"nm","applicability":["3d"]} -->
<!-- schema-field {"key":"output.diffraction_sample_count_x","unit":"samples","applicability":["3d"]} -->
<!-- schema-field {"key":"output.diffraction_sample_count_y","unit":"samples","applicability":["3d"]} -->
<!-- schema-field {"key":"output.top_probe_z_nm","unit":"nm","applicability":["3d"]} -->
<!-- schema-field {"key":"output.bottom_probe_z_nm","unit":"nm","applicability":["3d"]} -->
<!-- schema-field {"key":"output.probe_fraction","unit":"fraction","applicability":["3d"]} -->
<!-- schema-field {"key":"output.sample_count_x","unit":"samples","applicability":["3d"]} -->
<!-- schema-field {"key":"output.sample_count_y","unit":"samples","applicability":["3d"]} -->
<!-- schema-field {"key":"output.diffraction_order_max_m","unit":"order","applicability":["2d","3d"]} -->
<!-- schema-field {"key":"output.diffraction_order_max_n","unit":"order","applicability":["3d"]} -->

## 4. 常用组合与错误提示

| 组合 | 应该怎样写 | 常见错误 |
| --- | --- | --- |
| Stage4 3D grating | `grazing_angle_deg` + `azimuth_deg` + `geometry_kind` 为 grating；内部再派生 theta | 同时写 `incident_theta_deg`，或把内部 `incident_phi_deg` 当 public 键 |
| Stage1/2 airbox/Fresnel | `tilt_from_downward_z_deg`；不要填 grazing | 用含糊的 `theta`，或同时填两套角度 |
| 2D scattered PML | `kind="2d_scattered"`、`vertical_boundary="pml"`、PML 厚度 | 把 `use_floquet_y` 或 3D dtn 键带入 2D |
| 2D port | `kind="2d_port"`、`constraint_backend` 取一个 enum、vertical boundary 用 dtn/robin | 写 `both`/`all`，或同时选择多个约束后端 |
| Hybrid | 显式给 bottom/top、requested M、propagation/traction；candidate pool 由 adapter 派生 | 暴露 `candidate_modes`、`dtn_mode_count`、Woodbury size |
| complex value | `[real, imag]`，例如 `[1.0, 0.0]` | 写 `1+0j`、字符串表达式或三元数组 |
| memory policy | 每个 dat 显式给 warning/terminate/timeout/zero-swap | 把历史 authority hard gate 当成所有用户的 global default |

缺少 `.dat`、缺少顶层身份、section 重复、未知键、`grazing` 与 `tilt_from_downward_z` 同时出现、或把 2D/3D 专属字段混用，均由 T2 pure loader/validator 报错；T3 public launcher 会把这些输入错误以简洁非零状态返回。

## 5. 模板、preset 与 legacy 边界

五个模板本身就是完整的、可解析、每文件一 run 的示例；它们不是仅含片段的 skeleton：

| 模板 | 覆盖 | 状态 |
| --- | --- | --- |
| [ordinary_2d_example.dat](templates/ordinary_2d_example.dat) | 2D scattered + PML | 已连接ordinary 2D adapter，数值资格以正式 Gate 为准 |
| [full3d_direct_example.dat](templates/full3d_direct_example.dat) | Full3D direct | 完整 public schema 示例；完整 direct solve 由 capability 决定 |
| [full3d_iterative_example.dat](templates/full3d_iterative_example.dat) | Full3D iterative | T1 contract-only adapter stub；固定 13.5 nm，数值连接留到 T2 |
| [hybrid_direct_example.dat](templates/hybrid_direct_example.dat) | Hybrid direct | accepted finite method template |
| [hybrid_iterative_example.dat](templates/hybrid_iterative_example.dat) | Hybrid iterative、exact one-cell traction、two-pass | accepted research-extension template；不改变 ordinary default |

T0 审计的 preset 逐项处置如下；`migrate_to_dat` 表示迁移为显式输入或模板，不表示 production qualification：

| preset | 处置 |
| --- | --- |
| `2d_tm_pml_floquet_smoke` | `migrate_to_dat` → [input/smoke/2d_tm_pml_floquet_smoke.dat](smoke/2d_tm_pml_floquet_smoke.dat)；experimental smoke |
| `2d_tm_dtn_auxiliary_smoke` | `migrate_to_dat` → [input/smoke/2d_tm_dtn_auxiliary_smoke.dat](smoke/2d_tm_dtn_auxiliary_smoke.dat)；auxiliary DtN smoke |
| `2d_tm_dtn_explicit_smoke` | `migrate_to_dat` → [input/smoke/2d_tm_dtn_explicit_smoke.dat](smoke/2d_tm_dtn_explicit_smoke.dat)；explicit + auto-propagating legacy semantics |
| `2d_te_port_smoke` | `migrate_to_dat` → [input/smoke/2d_te_port_smoke.dat](smoke/2d_te_port_smoke.dat)；Robin port smoke |
| `2d_complex_absorption` | `migrate_to_dat` → [input/smoke/2d_complex_absorption.dat](smoke/2d_complex_absorption.dat)；complex-material public case，保留 evidence/status 边界 |
| `2d_euv_grating_direct` | `migrate_to_dat` → [input/examples/2d_euv_grating_direct.dat](examples/2d_euv_grating_direct.dat)；ordinary tutorial/example |
| `3d_stage1_airbox_smoke` | `migrate_to_dat` → [input/smoke/3d_stage1_airbox_smoke.dat](smoke/3d_stage1_airbox_smoke.dat)；experimental airbox smoke |
| `3d_stage2a_floquet_smoke` | `migrate_to_dat` → [input/smoke/3d_stage2a_floquet_smoke.dat](smoke/3d_stage2a_floquet_smoke.dat)；experimental Floquet smoke |
| `3d_stage2b_pml_smoke` | `migrate_to_dat` → [input/smoke/3d_stage2b_pml_smoke.dat](smoke/3d_stage2b_pml_smoke.dat)；experimental PML smoke |
| `3d_stage2c_fresnel_smoke` | `migrate_to_dat` → [input/smoke/3d_stage2c_fresnel_smoke.dat](smoke/3d_stage2c_fresnel_smoke.dat)；experimental Fresnel smoke |
| `3d_stage4a_flat_layer_direct` | `migrate_to_dat` → [input/smoke/3d_stage4a_flat_layer_direct.dat](smoke/3d_stage4a_flat_layer_direct.dat)；flat-layer direct smoke |
| `3d_stage4b_demo_direct_h5` | `keep_as_internal_factory`；legacy direct demo保留，未迁移 |
| `3d_stage4b_demo_direct_h3` | `keep_as_internal_factory`；legacy direct demo保留，未迁移 |
| `3d_stage4b_demo_mumps_ooc` | `research_only_not_public`；MUMPS OOC demo保留，未迁移 |
| `3d_stage4b_demo_mumps_blr` | `research_only_not_public`；MUMPS BLR demo保留，未迁移 |
| `3d_target_grating_direct_h5` | `keep_as_internal_factory`；target factory保留，物理值由已审 dat 显式承载 |
| `3d_target_grating_direct_h3` | `keep_as_internal_factory`；target factory保留，物理值由已审 dat 显式承载 |

另外，Task37c accepted MPI1 replay 示例为 [grazing1_phi0_hybrid_iterative_m120_mpi1.dat](official/grazing1_phi0_hybrid_iterative_m120_mpi1.dat)；它不是 ordinary preset，不计入上述 11 项迁移。

Task37b/c 的 `--frozen-m10`、authority path/hash、candidate pool、dynamic DtN count、QEP/lifecycle 与 raw PETSc options 是 legacy/internal/replay 资料，不是公开键。M10 的独立 geometry/material/incidence/discretization/method/solver/execution/output 值可迁入 official dat；这些值不是全局默认。`azimuth_deg`、`requested_modes_per_direction`、接口、传播和 traction 是独立 public inputs，但未审的函数、PC、自动扫描和批量 campaign 仍不是 public schema。

## 6. 输出与 provenance 计划

`output.export_fields`、`export_diffraction_orders`、`export_canonical_vectors`、`export_modal_amplitudes`、`export_reference_planes` 以及 reference-plane/采样字段是公开输出选择。authority record path/hash、checker comparison path、raw timeline、PETSc log 与大数组属于 internal provenance；未来 T4/T5 会把它们写入记录，但不会把它们变成用户输入。一个 dat 不表达 batch 或 sweep。

T2 已提供 schema 解析、严格字段与 cross-field 校验、角度派生和 default/conditional resolution；T3 已提供 `.dat` 必填、validate-only/dry-run 与 launcher 合同；T4–T6 已按各自受控能力接线。T7 的 preset 迁移只证明 legacy parser 与 dat runtime mapping 的静态等价边界，不声称任何 ordinary preset 已通过 PDE 数值资格化。

## 7. 维护规则

新增 public 字段必须同时修改 `src/io/input_schema.py`、本手册、至少一个适用模板和 focused coverage test；不能从 dataclass、argparse、PETSc option 或 preset 自动导出。保留的 legacy/research 入口只能在后续任务按已审 call graph 处理，不能因普通 dat 迁移而静默改变其 replay 行为。
