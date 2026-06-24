# Stage 4 续接记录

## 2026-06-24 续接记录：3D 求解器入口按 Stage 拆分

本轮是代码结构整理，不改变 Stage 4 的物理公式和已验证的 MPI/Floquet 修复结论。

完成内容：

```text
1. 原大文件 src/solvers/solve_airbox_maxwell_3d.py 已拆成：
   - src/solvers/solve_maxwell_3d_stage_1_airbox.py
   - src/solvers/solve_maxwell_3d_stage_2_no_grating.py
   - src/solvers/solve_maxwell_3d_stage_4_grating.py
   - src/solvers/solve_maxwell_3d_common.py

2. src/solvers/solve_airbox_maxwell_3d.py 保留为旧导入兼容层。

3. src/runners/run_3d_airbox.py 现在按 stage_case 显式分发到 Stage 1/2/4 solver。

4. src/main.py 的 3D PyCharm 输入拆成：
   - Stage1AirboxInputs3D
   - Stage2NoGratingInputs3D
   - Stage4GratingInputs3D
   当前只读取 ACTIVE_3D_INPUT_GROUP 选中的那一组。

5. 新增轻量回归测试：
   - src/test/test_13_3d_stage_entrypoints.py
   用于防止 Stage 1/2/4 入口再次混在一起。
```

验证结果：

```text
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
Ran 31 tests
OK (skipped=8)

Stage 1 tiny smoke:
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage1_airbox --case normal --mesh-target-size 600 \
  --nedelec-degree 1 --visualization-degree 1 --solver-profile direct --unique-output
结果：completed；用于验证 runner -> Stage 1 solver -> common engine 调用链。
```

下一轮如果继续 Stage 4 物理验证，优先看 `Stage4GratingInputs3D` 和
`solve_maxwell_3d_stage_4_grating.py`，不要再从旧兼容层开始读。

## 2026-06-24 续接记录：MPI 串并行一致性修复已完成

本轮接着上一条“MPI 串并行修复未完成”的断点继续。最终确认问题已经修复，可以从这里继续后续物理验证或 COMSOL 对比。

最终代码修复：

```text
src/constraints/floquet_3d.py
  根因修复：
    旧代码用未置换的 geometry edge 顺序构造 Nedelec Floquet orientation_sign。
    在 MPI 重编号后，这会让受约束矩阵出现分区相关的小差异，进而激发病态解。

  当前做法：
    1. 调用 mesh.topology.create_entity_permutations()。
    2. 使用 cpp.mesh.entities_to_geometry(..., permute=True)。
    3. local constraint 使用本 rank 装配 owned cells 所需的 local slave dof。
       dolfinx_mpc.add_constraint 的文档要求 slaves 是本进程 local numbering，
       因此 ghost slave 不是一律禁止；关键是边方向必须按 DOLFINx 拓扑方向一致。

src/solvers/solve_airbox_maxwell_3d.py
  1. MPI direct 显式选择并行 LU。
  2. Stage 4 PML 外边界对散射场施加零切向 E。
  3. summary 新增 RHS、线性系统残差、矩阵范数等诊断字段。

src/geometry/mesh_builder_3d.py
  cell tags 保持 owned cells 版本，避免积分标签依赖 ghost cells。
```

已完成验证：

```text
python3 -m compileall -q src：通过
python3 -m unittest discover -s src/test -p "test_*.py"：通过，29 tests, OK, skipped=8

stage4_block_grating h50/p1 normal:
  serial: R+T = 0.952741, max|E| = 1.911019
  np=2 : R+T = 0.952741, max|E| = 1.911019
  np=4 : R+T = 0.952741, max|E| = 1.911019
  np=8 : R+T = 0.952741, max|E| = 1.911019
  np=12: R+T = 0.952741, max|E| = 1.911019
  np=16: R+T = 0.952741, max|E| = 1.911019
```

关键结果目录：

```text
serial: results/3D_stage4_block_grating_normal_p1_h50p0_20260624_040509
np=2 : results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260624_034631
np=4 : results/3D_stage4_block_grating_normal_p1_h50p0_np4_20260624_034137
np=8 : results/3D_stage4_block_grating_normal_p1_h50p0_np8_20260624_035010
np=12: results/3D_stage4_block_grating_normal_p1_h50p0_np12_20260624_035345
np=16: results/3D_stage4_block_grating_normal_p1_h50p0_np16_20260624_035815
```

后续注意：

```text
1. 当前 h50/p1 的正式 E-Fourier R+T 小于 1，能量门槛通过。
2. sampled net-flux R+T 仍约 1.014，仅作为 H=curl(E) 诊断，不作为正式功率。
3. h50/p1 仍是粗网格；与 COMSOL 对比时应先看场分布形态和后续收敛趋势。
4. 如果继续提高阶数或改几何，仍需保持 hexa + degree=1 的限制，除非专门实现高阶 Nedelec 周期映射。
```

## 2026-06-24 续接记录：MPI 串并行修复未完成，因额度限制暂停

本轮目标是修复 Stage 4 在 MPI 下结果随 `np` 改变的问题。用户判断的重点是：当前 3D Floquet 低层约束可能把 ghost slave dof 也传给了 `dolfinx_mpc.MultiPointConstraint.add_constraint()`，导致同一个全局 slave 在多个 rank 上重复/错误约束。

已完成代码修改：

```text
src/constraints/floquet_3d.py
  1. owned_raw_maps 仍用于全局完整性检查。
  2. 传给 add_constraint 的 local_maps 改为只包含 owned slave dof。
  3. 在装配 slave_dofs 前增加 owned_dof_limit 检查：
     如果 ghost local dof 进入 add_constraint，立即 RuntimeError。
  4. 新增诊断：
     floquet_num_local_slave_records_seen
     floquet_num_local_ghost_slave_records_skipped
     floquet_num_global_ghost_slave_records_skipped

src/geometry/mesh_builder_3d.py
  _mark_cells 改成只给 owned cells 建 MeshTags，避免材料/PML 子域积分依赖 ghost cells。

src/solvers/solve_airbox_maxwell_3d.py
  1. summary 写出新增 Floquet ghost-slave 诊断字段。
  2. MPI direct 自动显式选择真正的并行 LU：
     优先 mumps，其次 superlu_dist，再其次 strumpack。
  3. 如果 MPI direct 没有可用并行 LU，直接禁用该算例，避免 preonly+lu 产出分区相关假结果。
  4. 日志/summary 新增：
     selected_parallel_lu_solver_type
     actual_pc_factor_solver_type
```

已完成实跑和结论：

```text
compileall：通过
python3 -m unittest discover -s src/test -p "test_*.py"：通过，28 tests, OK, skipped=8
```

关键测试：

```text
1. stage4_block_grating h50/p1 np=4，owned-only slave 后：
   results/3D_stage4_block_grating_normal_p1_h50p0_np4_20260624_022246
   local slave dofs = 404
   local slave records seen = 417
   local ghost slave records skipped = 13
   global ghost slave records skipped = 68
   R+T = 1.485862
   max |E| = 1.034255e+01
   结论：比旧 all-local ghost 路径 R+T=2.073427 有改善，但仍未恢复串行。

2. cell tags 改为 owned-only 后重跑同一 np=4：
   results/3D_stage4_block_grating_normal_p1_h50p0_np4_20260624_023003
   结果与上一条基本相同。
   结论：cell ghost tags 不是这个 Stage 4 MPI 爆场的主因，但 owned-only cell tags 仍是更安全写法。

3. floquet_airbox normal h300/p1 串行/np4：
   results/3D_floquet_airbox_normal_p1_h300p0_20260624_023511
   results/3D_floquet_airbox_normal_p1_h300p0_np4_20260624_023518
   两者 plane-wave error 都约 4e-15。
   结论：纯 Floquet MPC 在简单解析场中并行可用。

4. stage4_flat_layer_sanity h50/p1 串行/np4：
   results/3D_stage4_flat_layer_sanity_normal_p1_h50p0_20260624_023544
   results/3D_stage4_flat_layer_sanity_normal_p1_h50p0_np4_20260624_023921
   E_scat = 0，场幅值一致。
   结论：无 grating source 时，PML + layered background + Floquet 并行可用。

5. 当前代码重跑 stage4_block_grating 串行：
   results/3D_stage4_block_grating_normal_p1_h50p0_20260624_024101
   R+T = 0.9527755
   max |E| = 1.910820

6. MPI direct 显式选择 MUMPS 后，stage4_block_grating np=4：
   results/3D_stage4_block_grating_normal_p1_h50p0_np4_20260624_025120
   actual_pc_factor_solver_type = mumps
   R+T = 1.485862
   max |E| = 1.034255e+01
   结论：问题不是 PETSc 默认没选并行 LU。

7. 临时恢复 all-local slave（含 ghost）并用 MUMPS 重跑 np=4：
   results/3D_stage4_block_grating_normal_p1_h50p0_np4_20260624_025506
   local slave dofs = 417
   R+T = 2.073427
   max |E| = 2.361750e+01
   结论：all-local ghost slave 路径更差。临时改动已回退到 owned-only。

8. floquet_airbox oblique + p polarization h300/p1 串行/np4：
   results/3D_floquet_airbox_oblique_p1_h300p0_20260624_025852
   results/3D_floquet_airbox_oblique_p1_h300p0_np4_20260624_025857
   两者误差一致。
   结论：更复杂偏振下的 Floquet 约束仍表现为串并行一致；剩余问题集中在 Stage 4 block grating 的 volume source / grating perturbation / 近零模式。
```

未完成工作：

```text
1. 尚未找到 Stage 4 block grating MPI 爆场的最终根因。
2. 尚未运行 divergence_penalty 诊断；尝试运行时额度限制触发：
   You've hit your usage limit. Try again at 2:19 PM.
3. 当前代码未提交，且未在回退 owned-only 后重新 compileall。
```

下一轮建议顺序：

```bash
# 1. 先确认当前工作区和代码编译
git status --short
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"

# 2. 运行 divergence penalty 诊断
mpiexec -n 4 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct \
  --stage4-boundary-model pml \
  --divergence-penalty 1.0

# 3. 如果 penalty 让 np4 回到串行量级，再跑串行同 penalty 对照。
# 4. 如果 penalty 无效，下一步检查 MPC 体源 RHS 装配：
#    对比 constrained RHS 向量范数、局部 grating source dof 分布、以及 mpc.assemble_vector 对 ghost/master 的处理。
```

当前判断：

```text
owned-only ghost slave 修复是必要的防护，它把 np4 从 R+T=2.07 改善到 1.49，但不是充分修复。
Stage 4 MPI 的最终问题不是 flat PML、不是纯 Floquet、也不是 PETSc 未显式选择 MUMPS；
更可能是 block grating volume source 激发了 H(curl) 系统中的分区敏感梯度/近零模式，
或者 dolfinx_mpc 对带体源项的 constrained RHS 装配仍需要额外处理。
```

## 2026-06-23 继续验证记录：Docker 额度仍未恢复

本次续接后先检查了工作区，确认 Stage 4 的 PML/E_exact 口径修正仍在未提交状态，主要改动包括：

```text
src/postprocessing/postprocess_3d.py
src/solvers/solve_airbox_maxwell_3d.py
src/main.py
notes/README.md
notes/quick_start/stage4_3d_block_grating_usage_guide.md
notes/reference/code_walkthrough.md
notes/test/stage4_resume_log.md
```

随后尝试重新进入 Docker/DOLFINx 环境做编译验证：

```bash
python3 -m compileall -q src
```

但外部 Docker 执行仍被额度限制拦截：

```text
You've hit your usage limit. Try again at 1:59 PM.
```

因此本次未能补跑 Stage 4 smoke，也未能检查最新 `run_summary.json` 和 ParaView `fields_3d_for_paraview.vtu`。下一轮额度恢复后应先运行：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main
```

重点检查：

```text
exact_reference_available = false
paraview_e_field_arrays 包含 E_tot_V_per_m_* / E_b_V_per_m_* / E_sca_V_per_m_*
ParaView 中不再出现 E_exact/H_exact/error
pml_metric_field = E_scat
pml_scattered_decay_ratio_top/bottom 有数值
```

## 2026-06-23 更新：PML/E_exact 口径修正后因额度限制暂停

本轮目标：

```text
1. 检查当前 config_3d.py 和 main.py 的定义问题。
2. 参考 2D scattered-field 输出口径，修正 Stage 4 的场输出。
3. 解决 ParaView 中 E_exact 误导问题。
4. 让 PML 诊断改为看 E_scat，而不是看 E_total/E_b。
```

已完成代码修改：

```text
src/common/config_3d.py
  将 z_min 恢复为中性默认 -550 nm，避免基类默认值混入 Stage 4 案例参数。

src/main.py
  Stage 4 main 入口 PML 参数调回已验证过的默认：
    PML_TOP_THICKNESS_3D = 250.0
    PML_BOTTOM_THICKNESS_3D = 250.0
    PML_ALPHA_3D = 5.0

src/postprocessing/postprocess_3d.py
  Stage 4 不再输出 E_exact/H_exact/error。
  E_b 明确作为背景场输出，不再冒充精确解。
  ParaView 输出保留：
    E_tot_V_per_m_*
    E_b_V_per_m_*
    E_sca_V_per_m_*
  每个 E 场还增加 Ex/Ey/Ez 的 real/imag/abs/phase 分量数组。

src/solvers/solve_airbox_maxwell_3d.py
  新增 _stage4_scattered_pml_metrics(E_sca, cfg)。
  Stage 4 的 PML 指标改为：
    pml_metric_field = E_scat
    pml_scattered_decay_ratio_top
    pml_scattered_decay_ratio_bottom
  日志不再对 Stage 4 打印 plane-wave exact error。
```

已完成文档修改：

```text
notes/README.md
notes/quick_start/stage4_3d_block_grating_usage_guide.md
notes/reference/code_walkthrough.md
```

已运行验证：

```text
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"

结果：
Ran 27 tests in 1.462s
OK (skipped=8)
```

未完成验证：

```text
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main
```

未完成原因：

```text
Docker 外部执行被额度限制拒绝：
You've hit your usage limit. Try again at 1:59 PM.
```

下一轮建议先做：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main
```

然后检查最新结果目录的 `run_summary.json` 是否包含：

```text
exact_reference_available = false
exact_reference_note
paraview_e_field_arrays:
  E_tot_V_per_m_*
  E_b_V_per_m_*
  E_sca_V_per_m_*
pml_metric_field = E_scat
pml_scattered_decay_ratio_top
pml_scattered_decay_ratio_bottom
```

还需要完成：

```text
1. 跑 Stage 4 main smoke。
2. 确认 ParaView 文件中不再出现 E_exact/H_exact/error。
3. 视结果更新 notes/test/stage4_validation_report.md。
4. git status 检查后提交本轮 checkpoint。
```
