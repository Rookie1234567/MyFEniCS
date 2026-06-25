# Stage 4 续接记录

## 2026-06-25 续接记录：MPI BUS error 已定位到 VTX 后处理，Floquet context 计时已拆分

本轮已完成：

```text
1. src/postprocessing/postprocess_3d.py
   - MPI 下默认跳过 3D VTX .bp，避免 ADIOS2/VTXWriter 在大并行向量场写出时触发 BUS error。
   - 串行仍写 E_3d_numerical.bp 和 H_3d_A_per_m_from_curl.bp。
   - summary 新增 vtx_3d_output_status 和 vtx_3d_output_files。

2. src/constraints/floquet_3d.py
   - 新增 floquet_build_topological_edge_context 计时。
   - x/y/corner 约束构建计时不再混入首次拓扑上下文构建。

3. src/solvers/dtn_port_3d.py
   - 保留上一轮可复用 surface component form 的 DtN 装配优化。
   - 撤回本轮中为 h=10 粗网格试探过的符号改动；h=10 对 lambda0=13.5 nm 太粗，不作为物理验收。
```

已运行：

```text
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
结果：Ran 37 tests, OK (skipped=8)

h=2.5 block, np=8, zero_order:
  results/3D_stage4_block_grating_normal_p1_h2p5_np8_20260625_092003
  R/T/R+T = 0.3189887183 / 0.6810112817 / 1.0000000000
  case_status = completed
  ParaView PVD 已写出
  VTX .bp 在 MPI 下被跳过

h=5 block, np=4, auto_propagating:
  results/3D_stage4_block_grating_normal_p1_h5p0_np4_20260625_093728
  R/T/R+T = 0.3661053 / 0.6338947 / 1.0000000
  floquet_build_topological_edge_context = 0.591 s
  stage4_dtn_port_assembly_and_solve = 13.487 s
```

未完成/后续建议：

```text
1. 若要继续物理验证，优先跑 h=2.5 + auto_propagating block；预计直接求解会明显慢于 zero_order。
2. 若继续优化性能，下一步看 MUMPS 直接求解时间和矩阵规模，而不是 Floquet 或 DtN modal loop。
3. 若想进一步压缩输出体积，可增加一个 config 控制 visualization_degree 或 rank*.vtu 写出。
```

## 2026-06-25 续接记录：额度中断前状态

本轮已完成并验证：

```text
1. 代码修改：
   - src/solvers/solve_maxwell_3d_common.py
     拆分 field_formulation_setup、floquet_constraint_setup_outer、boundary_condition_setup。
   - src/solvers/dtn_port_3d.py
     修正 DtN 弱式符号；
     增加可复用表面 form；
     端口 modal loop 改成每个 (side,m,n) 复用 x/y 分量。

2. 文档修改：
   - notes/README.md
   - notes/quick_start/stage4_3d_block_grating_usage_guide.md
   - notes/reference/code_walkthrough.md
   - notes/test/stage4_validation_report.md
   - notes/test/stage4_resume_log.md
   - notes/theory/stage4_3d_dtn_port.md

3. 已完成验证：
   - compileall：通过。
   - unittest：在清理未使用 helper 之前通过，Ran 37 tests, OK (skipped=8)。
   - h=5 block auto_propagating：
     results/3D_stage4_block_grating_normal_p1_h5p0_np4_20260625_074047
     elapsed = 15.637 s，stage4_dtn_modal_loop_seconds = 2.431 s，R+T = 1.000000。
   - h=2.5 flat n_sub=1：
     results/3D_stage4_flat_layer_sanity_normal_p1_h2p5_np8_20260625_074306
     R/T/R+T = 6.043954e-04 / 9.993956e-01 / 1.000000。
   - 清理未使用 helper 后又跑了一次 compileall：通过。
```

未完成：

```text
1. 清理未使用 helper 后的最终 unittest 重跑被 Codex/Docker 执行额度拦截。
2. 本轮改动尚未 git commit。
3. 下一轮恢复后先运行：
   . dolfinx-complex-mode && python3 -m unittest discover -s src/test -p "test_*.py"
   然后 git add/commit。
```

## 2026-06-25 续接记录：DtN 端口装配优化完成，下一轮重点转向直接求解器/精度

本轮已完成：

```text
1. 拆分计时：
   - field_formulation_setup
   - floquet_constraint_setup_outer
   - boundary_condition_setup
   - stage4_dtn_port_assembly_and_solve

2. 修正 3D DtN 弱式符号：
   - FEM block 使用 - q * ell * auxiliary
   - top incident RHS 使用 +2i beta 的等效边界向量
   - auxiliary 仍表示端口总场投影

3. 优化 DtN modal loop：
   - 每个 (side,m,n) 只装配 x/y 两个表面分量
   - 两个偏振通过线性组合得到 trace/traction
   - fem.Constant 更新 alpha/gamma/kz，避免每个级次重建 UFL form

4. 验证：
   - compileall 通过
   - unittest：Ran 37 tests, OK (skipped=8)
   - h=5 block auto_propagating：elapsed = 15.637 s，R+T = 1.000000
   - h=2.5 flat n_sub=1：R/T/R+T = 6.04e-4 / 0.999396 / 1.000000
```

本轮关键结果目录：

```text
results/3D_stage4_block_grating_normal_p1_h5p0_np4_20260625_074047
results/3D_stage4_flat_layer_sanity_normal_p1_h2p5_np8_20260625_074306
```

下一轮建议：

```text
1. 如果继续追求 h=2.5 block grating + auto_propagating：
   端口 modal loop 已不是瓶颈，重点看 MUMPS 直接求解时间和内存。

2. 如果要进一步优化：
   优先考虑矩阵装配/直接求解器策略，而不是继续改 DtN modal loop。

3. 如果要和 COMSOL 对照：
   先固定 dtn_port 主线，使用 dtn_port_power_metrics_3d.json 与 ParaView 的 E_total。
```

## 2026-06-25 续接记录：Stage 4 3D DtN 主线已跑通，下一步可做 h=2.5 block 或优化端口装配

本轮已完成：

```text
1. 修复 dtn_port 运行时问题：
   - PETSc index dtype 改为 PETSc.IntType。
   - 增广矩阵 Mat.createAIJ local/global size 修正。
   - 移除非 ghost Vec 的 ghostUpdate。

2. 修复 3D DtN auxiliary 端口符号：
   - 回到与 2D 端口同构的 auxiliary=端口总场投影。
   - top RHS 使用等价的 -2i beta 入射源。
   - R/T 使用 top(total_projection - incident_projection)、bottom(total_projection)。

3. 容器验证：
   - python3 -m compileall -q src：通过。
   - python3 -m unittest discover -s src/test -p "test_*.py"：
     Ran 37 tests, OK (skipped=8)。

4. PDE smoke：
   - flat, n_sub=1.0, h=2.5, np=8：
     R/T/R+T = 6.043954e-04 / 9.993956e-01 / 1.000000
   - flat, n_sub=1.45, h=2.5, np=8：
     R/T/R+T = 2.061463e-02 / 9.793854e-01 / 1.000000
   - block grating, h=5, np=4, auto_propagating：
     DtN modes = 1068
     R/T/R+T = 3.661053e-01 / 6.338947e-01 / 1.000000
```

当前结论：

```text
1. dtn_port 主线已替代旧 PML/probe 分支成为 Stage 4 可信 R/T 路径。
2. 旧 PML 分支中 R+T>1 的问题不再出现在 dtn_port 端口功率里。
3. h=5 block grating 只是 smoke，不是最终 COMSOL 对标精度。
4. h=2.5 block grating + auto_propagating 尚未跑；按 h=5 的 1068 模态装配耗时约 606 s 推测，
   h=2.5 会更久，应单独安排。
```

下一轮建议：

```text
1. 如果要提高物理精度：跑 h=2.5 block grating + auto_propagating，建议 np=8 或 np=16。
2. 如果要提高效率：优化 dtn_port_3d.py 中每个 mode 都重新 assemble_vector 的端口装配。
3. 如果要对 COMSOL：优先使用 dtn_port_power_metrics_3d.json 和 dtn_port_diffraction_orders_3d.csv/json。
```

## 2026-06-25 续接记录：Stage 4 3D DtN 总场端口实现中，容器实跑因额度限制暂停

本轮已完成：

```text
1. 新增共享 3D 模态模块：
   - src/common/modes_3d.py
   - 抽出 3D diffraction/DtN 共用的 (m,n) 枚举、s/p 偏振、Rayleigh warning、
     mode E/H 向量、单位振幅功率和入射功率计算。

2. 新增 Stage 4 DtN 总场端口初版：
   - src/solvers/dtn_port_3d.py
   - stage4_boundary_model="dtn_port"
   - stage4_dtn_order_policy="auto_propagating"
   - stage4_dtn_assembly="auxiliary"
   - 默认不使用上下 PML，x/y 仍使用低内存显式边拓扑 Floquet MPC。

3. 接入入口和配置：
   - src/common/config_3d.py
   - src/main.py
   - src/runners/run_3d_airbox.py
   - src/solvers/solve_maxwell_3d_common.py
   - Stage 4 默认边界模型改为 dtn_port；PML 分支保留为诊断历史。

4. ParaView 输出增加 DtN 入射端口诊断场：
   - src/postprocessing/postprocess_3d.py
   - 输出 E_total 和 E_incident_port；不新增伪造 E_exact。

5. 新增纯数学单元测试：
   - src/test/test_14_stage4_dtn_modes.py
   - 验证 auto_propagating 不受 diffraction_zero_order_only 截断；
     验证 zero_order、偏振横向性、出射功率正号和零级入射投影。

6. 已完成本机语法检查：
   python -m py_compile src/common/modes_3d.py src/solvers/dtn_port_3d.py \
     src/postprocessing/diffraction_3d.py src/postprocessing/postprocess_3d.py \
     src/solvers/solve_maxwell_3d_common.py src/test/test_14_stage4_dtn_modes.py
   结果：通过。
```

当前被额度限制阻断的验证：

```text
1. Docker compileall：
   docker run ... python3 -m compileall -q src
   结果：被 Codex/Docker 执行额度限制拦截。

2. Docker unittest：
   docker run ... python3 -m unittest discover -s src/test -p "test_*.py"
   结果：尚未运行。

3. PDE smoke：
   stage4_flat_layer_sanity + dtn_port
   stage4_block_grating + dtn_port, h=5 nm / h=2.5 nm
   MPI np=1/2/4/8/16 一致性对比
   结果：尚未运行。
```

下一轮建议先执行：

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_flat_layer_sanity \
  --stage4-boundary-model dtn_port \
  --mesh-target-size 5 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --unique-output
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --stage4-boundary-model dtn_port \
  --mesh-target-size 5 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --unique-output
```

注意：当前 DtN 装配还没有经过 DOLFINx/MPC 运行时验证，不能提交为可信物理结果；如果 `stage4_flat_layer_sanity` 不能给出接近 Fresnel 且 `R+T≈1`，应先修 DtN 边界符号、端口归一化和辅助变量块，而不是继续跑真实 grating。

## 2026-06-25 续接记录：E/H Fourier 修正完成，但目标案例仍失败

本轮已完成：

```text
1. 修正 Stage 4 官方衍射级 R/T 后处理：
   - 旧官方值：E-only Fourier。
   - 新官方值：per-order E/H Fourier，上下行模态分离。
   - 旧 E-only 字段保留为 diagnostic。

2. 新增单元测试：
   - flat-layer Fresnel 同时验证 E-only 与 E/H Fourier。
   - 人工同级次 up/down 波验证 E/H Fourier 能分离 transmitted/down 振幅。

3. 完整测试：
   python3 -m unittest discover -s src/test -p "test_*.py"
   结果：Ran 33 tests, OK (skipped=8)
```

关键结果：

```text
h=12.5, n=2, natural:
  results/3D_stage4_block_grating_normal_p1_h12p5_np4_20260625_013916
  E-only R+T = 1.008603
  E/H    R+T = 1.001129

h=6.25, n=2, natural:
  results/3D_stage4_block_grating_normal_p1_h6p25_np4_20260625_014118
  E-only R+T = 1.781313
  E/H    R+T = 1.398569
  net-flux R+T = 0.822158

h=6.25, n=2, PML=100 nm, alpha=30, zero_tangential:
  results/3D_stage4_block_grating_normal_p1_h6p25_np4_20260625_015707
  E/H R+T = 1.417659
  net-flux R+T = 0.867155

h=2.5, n=2, natural, np=16:
  results/3D_stage4_block_grating_normal_p1_h2p5_np16_20260625_020717
  E-only R+T = 2.602034
  E/H    R+T = 1.984750
  net-flux R+T = 1.882674
  case_status = failed_stage4_energy_balance
```

当前判断：

```text
1. E/H Fourier 后处理修正有效，但只解决了一部分透射率虚高。
2. h=2.5 的场解仍不可信，max |E_scat| 约 3.98，R+T 仍接近 2。
3. h=6.25 下加厚/增强 PML 没有修复，说明不能靠 PML 参数简单救回来。
4. 当前 p1/h=2.5 对 n=2 光栅材料内波长只有约 2.7 个单元/波长，
   不满足常用 6 个单元/波长经验要求。
```

下一步建议：

```text
1. 不要再把当前 p1/h=2.5 作为可信 COMSOL 对标结果。
2. 若继续做 EUV 目标案例，优先路线应是：
   - 支持更高阶 H(curl) 元素的低内存 Floquet 约束；
   - 或实现真正的 3D modal/DtN port，减少 PML 多级次回馈；
   - 或转到内存更大的服务器，尝试 h≈1.0-1.25 nm 的收敛测试。
3. 如果只想验证代码流程，可继续使用 flat-layer、n_grating=1、n_grating=1.2、h=12.5 这类 sanity。
```

## 2026-06-24 续接记录：h=2.5 nm、np=16 已跑完但能量失败

本轮已完成：

```text
1. Docker 全量单元测试重新执行：
   . dolfinx-complex-mode && python3 -m unittest discover -s src/test -p "test_*.py"
   结果：Ran 32 tests, OK (skipped=8)

2. stage4_block_grating, h=2.5 nm, p1, np=16, natural PML outer BC：
   results/3D_stage4_block_grating_normal_p1_h2p5_np16_20260624_124802
   R/T/R+T = 0.068117 / 2.534148 / 2.602265
   sampled net-flux R+T = 1.823622
   true relative residual = 9.12e-12
   elapsed = 2431.8 s

3. stage4_block_grating, h=2.5 nm, p1, np=16, zero_tangential PML outer BC：
   results/3D_stage4_block_grating_normal_p1_h2p5_np16_20260624_133711
   R/T/R+T = 0.069171 / 2.535508 / 2.604678
   sampled net-flux R+T = 1.870036
   true relative residual = 5.64e-12
   elapsed = 2432.7 s

4. 代码补充：
   src/solvers/solve_maxwell_3d_common.py
   - strong_z_boundary_dirichlet_dofs 改为 summary 全局 dof 数。
   - 新增/保留 raw 与 slave removal 后的全局 z-boundary dof 统计。
```

当前结论：

```text
1. h=2.5 当前版本可以跑完，不是 Floquet 构造阶段 OOM。
2. zero_tangential 和 natural 结果几乎一致，PML 最外边界类型不是当前 R+T 爆炸主因。
3. direct LU 残差很小，问题更可能在 Stage 4 弱式/PML 张量/分层背景源项/场分解的一致性。
4. 这两组结果都必须标记为 failed_stage4_energy_balance，不能用于物理结论或 COMSOL 定量比较。
```

下一轮建议：

```text
1. 先固定小但可解释的 flat/interface case，逐项验证 PML 张量弱式：
   - 无光栅 flat_layer：E_scat 应接近 0，R/T 为 Fresnel。
   - grating contrast -> 0：E_scat 应连续趋近 0。
   - pml_alpha = 0 且无 PML 区：检查弱式退化。

2. 对 Stage 4 source 做体积分项诊断：
   - grating source 是否只在 tag=3。
   - PML cell 是否完全没有 source。
   - eps_true / eps_bg 在 grating、air、substrate 的值是否逐 cell 正确。

3. 检查 PML 复拉伸张量：
   - curl-curl 项和 mass 项是否使用互逆张量组合。
   - top/bottom PML 的背景介质 eps 是否分别为空气/基底。
```

## 2026-06-24 续接记录：R/T 后处理修正完成，Docker 全量测试因额度限制暂停

本轮已完成：

```text
1. 代码中删除 solver_profile / --solver-profile 公开入口。
   影响文件：
   - src/common/config_3d.py
   - src/main.py
   - src/runners/run_3d_airbox.py
   - src/solvers/solve_maxwell_3d_common.py
   - src/test/stage2_test_utils.py
   - src/test/stage4_2p5d_compare.py

2. 3D 内部线性求解固定为 direct LU：
   ksp_type = preonly
   pc_type = lu
   MPI 时自动选择 mumps / superlu_dist / strumpack。

3. Stage 4 diffraction 后处理修正：
   - compute_diffraction_orders_3d(..., E_scattered=...)
   - 官方 R/T 使用 E_scat 数值采样 + 解析 E_bg_exact，而不是插值后的 E_total。
   - diffraction_zero_order_only=False 时自动补全所有传播衍射级。

4. 新增解析 flat-layer 单元测试：
   - src/test/test_11_stage4_diffraction_modes.py
   - test_flat_layer_fresnel_field_e_fourier_power_sanity

5. 中文文档已更新：
   - notes/README.md
   - notes/reference/code_walkthrough.md
   - notes/quick_start/stage4_3d_block_grating_usage_guide.md
   - notes/quick_start/pycharm_main_run_guide.md
   - notes/test/stage4_validation_report.md
```

已完成验证：

```text
python -m compileall -q src
结果：通过

rg -n "solver_profile|SOLVER_PROFILE|solver-profile|SUPPORTED_SOLVER|iterative_" src
结果：src 中无匹配

Docker 单测：
python3 -m unittest src.test.test_11_stage4_diffraction_modes
结果：Ran 6 tests, OK

stage4_flat_layer_sanity, h=12.5, p1, np=2:
results/3D_stage4_flat_layer_sanity_normal_p1_h12p5_np2_20260624_101122
R/T/R+T = 0.03373594 / 0.9662641 / 1.000000
结论：flat-layer 背景、Fresnel 归一化和 E-Fourier 后处理通过。

stage4_block_grating, h=12.5, p1, np=2, natural PML 25 nm:
results/3D_stage4_block_grating_normal_p1_h12p5_np2_20260624_102538
R/T/R+T = 0.034926 / 0.973677 / 1.008603
case_status = failed_stage4_energy_balance

stage4_block_grating, h=12.5, p1, np=2, natural PML 50 nm, alpha=8:
results/3D_stage4_block_grating_normal_p1_h12p5_np2_20260624_102938
R/T/R+T = 0.034938 / 0.973685 / 1.008623
case_status = failed_stage4_energy_balance
结论：粗网格 block-grating 仍不可信；PML 加厚不是 0.86% 超能量主因。
```

未完成：

```text
1. Docker 全量单元测试：
   . dolfinx-complex-mode && python3 -m unittest discover -s src/test -p "test_*.py"
   本轮调用时被额度限制拦截，未执行。

2. 修复版 h=2.5 nm 或 h=1.25 nm block-grating 正式验证。
   当前另有旧代码 h=1.25、np=8 Docker 任务仍在运行，且它使用旧后处理和 zero_tangential，不适合作为最终结果。

3. 如 h=2.5 修复版仍 R+T>1，需要继续查：
   - grating scattered field 在 probe plane 的横向性和 Fourier 残差
   - PML 张量对高角传播级的吸收
   - hexa p1 Nedelec 对 13.5 nm 高频问题的色散误差
   - 是否需要二阶单元或更细 h<=lambda_sub/6
```

下次建议命令：

```bash
# 先跑全量轻量测试
python3 -m unittest discover -s src/test -p "test_*.py"

# 资源空闲后，跑修复版 h=2.5
mpiexec -n 8 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 2.5 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --stage4-pml-outer-bc natural \
  --diffraction-sample-count-x 64 \
  --diffraction-sample-count-y 64 \
  --unique-output
```

## 2026-06-24 续接记录：13.5 nm 小周期、natural PML 外边界和 direct-only 清理

本轮修改：

```text
1. Stage 4 默认几何改为：
   lambda0 = 13.5 nm
   period_x = period_y = 100 nm
   block = 50 x 50 x 50 nm
   substrate_thickness = 50 nm
   air_height = 100 nm
   pml_top = pml_bottom = 25 nm
   mesh_target_size = 5 nm

2. Stage 4 PML 外边界新增变量：
   stage4_pml_outer_bc = "natural"          # 默认
   stage4_pml_outer_bc = "zero_tangential"  # 旧诊断

3. diffraction probe 默认从 0.95 改为 0.75：
   top_probe_z = 75 nm
   bottom_probe_z = -37.5 nm

4. 3D solver profile 清理为 direct-only。
   CLI 仍接受 --solver-profile direct/default/direct_lu，但迭代 profile 已从正式代码路径移除。

5. Stage 4 默认关闭旧 E/H modal diagnostic。
   正式 R/T 继续使用 E-Fourier diffraction orders。
```

h25/p1 smoke 结果：

```text
natural:
  results/3D_stage4_block_grating_normal_p1_h25p0_20260624_073407
  R/T/R+T = 0.045960 / 0.278516 / 0.324476
  max |E_scat| in PML = 3.12e-2
  linear_problem_setup ≈ 94 s

zero_tangential:
  results/3D_stage4_block_grating_normal_p1_h25p0_20260624_073105
  R/T/R+T = 0.045685 / 0.278052 / 0.323737
  max |E_scat| in PML = 7.02e-4
  linear_problem_setup ≈ 0.004 s
```

结论：natural 默认能更真实暴露 PML 截断残余场；正式 E-Fourier R/T 与 zero_tangential 在这个粗网格 smoke 中接近。natural 目前在 `dolfinx_mpc + no z Dirichlet + direct` 下 setup 明显更慢，后续如果要正式跑 h=5，需要优先在服务器或并行环境评估资源。

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
