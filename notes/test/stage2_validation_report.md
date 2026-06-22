# Stage 2 验证报告

## 2026-06-22 更新：h50/p1 下 2A、2B、2C 跑通性和误差评估

本轮命令使用统一设置：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage2_all \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

补充诊断：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case oblique \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct

mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case fresnel_interface \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct \
  --no-use-pml \
  --use-floquet-xy
```

结论先写在前面：

```text
1. 2A、2B、2C 都能跑通，PETSc direct 均收敛。
2. 新的 3D Floquet edge topology 约束构建稳定：
   max_masters_per_slave = 1
   edge pairing error = 0
   constraint memory 约 0.029 到 0.044 MB
3. 2A 的场幅值误差仍很大，normal/oblique 的 relative E max error 都约 10。
4. 2B 的 PML 空气盒能跑通，E max error 约 0.117，bottom PML 有明显衰减；top ratio > 1 与当前入射波穿过 top PML 的解析延拓口径有关。
5. 2C 默认 Floquet+PML Fresnel 能跑通但 R/T 完全不可信，R+T 约 52。
6. 2C 关掉 PML、保留 Floquet 后 R/T 仍不可信，R+T 约 10；因此当前 h50/p1 Fresnel 定量误差不能作为通过。
7. 临时直接检查解析平面波是否满足新的 edge constraints：有物理幅值的 dof 残差约 1e-14，说明大误差不是因为 Floquet edge 配对相位/方向符号错。
```

2A normal，`floquet_airbox`：

```text
result_dir = results/3D_stage2_all_normal_p1_h50p0_np2_20260622_055106/airbox3d_normal_floquet_airbox
case_status = completed
num_mesh_cells = 2160
num_nedelec_dofs = 7552
relative_max_abs_E_error = 9.986
relative_max_abs_H_error = 18.976
poynting_direction_cosine = 0.99998
floquet_num_constraints = 832
floquet_max_masters_per_slave = 1
floquet_estimated_constraint_memory_mb = 0.0286
elapsed = 3.83 s
max_rss = 364.7 MB
```

2A oblique 诊断：

```text
result_dir = results/3D_floquet_airbox_oblique_p1_h50p0_np2_20260622_055715
case_status = completed
relative_max_abs_E_error = 10.036
relative_max_abs_H_error = 13.288
poynting_direction_cosine = 0.99759
floquet_num_constraints = 832
floquet_max_masters_per_slave = 1
floquet_estimated_constraint_memory_mb = 0.0286
```

2B normal，`pml_airbox`：

```text
result_dir = results/3D_stage2_all_normal_p1_h50p0_np2_20260622_055106/airbox3d_normal_pml_airbox
case_status = completed
num_mesh_cells = 3360
num_nedelec_dofs = 11602
relative_max_abs_E_error = 0.1166
relative_max_abs_H_error = 2.209
pml_reflection_proxy = 0.0684
pml_reference_relative_error = 1.162
pml_decay_ratio_top = 123.249
pml_decay_ratio_bottom = 0.01999
floquet_num_constraints = 1282
floquet_max_masters_per_slave = 1
floquet_estimated_constraint_memory_mb = 0.0440
elapsed = 159.6 s
max_rss = 4087.6 MB
```

2C normal，默认 `fresnel_interface`，Floquet+PML：

```text
result_dir = results/3D_stage2_all_normal_p1_h50p0_np2_20260622_055106/airbox3d_normal_fresnel_interface
case_status = completed
num_mesh_cells = 3360
num_nedelec_dofs = 11602
relative_max_abs_E_error = 0.0921
relative_max_abs_H_error = 2.210
R_total = 15.166
T_total = 36.886
R_plus_T = 52.053
fresnel_R/T = 0.03374 / 0.96626
floquet_num_constraints = 1282
floquet_max_masters_per_slave = 1
floquet_estimated_constraint_memory_mb = 0.0440
elapsed = 156.6 s
max_rss = 4117.5 MB
```

2C normal，关 PML、保留 Floquet 的隔离诊断：

```text
result_dir = results/3D_fresnel_interface_normal_p1_h50p0_np2_20260622_055721
case_status = completed
relative_max_abs_E_error = 25.655
relative_max_abs_H_error = 17.437
R_total = 0.877
T_total = 9.258
R_plus_T = 10.135
fresnel_R/T = 0.03374 / 0.96626
```

本轮判断：

```text
跑通性：
  2A 通过
  2B 通过
  2C 通过

Floquet 约束构建：
  通过。h50/p1 下约束构建不再是内存瓶颈。

物理误差：
  2A 不通过定量误差验收。
  2B 只能作为 PML 路径 smoke，不作为严格吸收性能验收。
  2C 不通过 R/T 定量验收。
```

下一步建议：

```text
1. 先修 2A airbox 的场幅值误差，因为它是 2B/2C 的基础。
2. 保留当前 edge topology Floquet，不要回退到 probe/pinv；临时约束残差检查显示解析场满足新约束。
3. 2A 建议新增/保留一个测试：插值解析平面波后检查 MPC raw constraint residual，只统计 |dof| 足够大的自由度，避免零 dof 分母放大。
4. 2C 的 R/T 后处理暂时不要作为通过标准；等 2A 场幅值问题解决后，再分别重跑 Floquet-only、PML-only、Floquet+PML 三组隔离 case。
```

## 2026-06-22 更新：3D Floquet 显式边拓扑约束验证

本轮修改目标：正式禁用 probe function + pseudo-inverse / dense whole-plane transform，改为 degree=1 N1curl 的显式 mesh edge 周期配对。

基础检查：

```bash
python -m compileall -q src

. dolfinx-complex-mode
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 20 tests in 0.003s
OK (skipped=8)
```

硬验收 smoke：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果：

```text
result_dir = results/3D_floquet_airbox_normal_p1_h50p0_np2_20260622_035247
constraint_mode_resolved = topological_edges
mesh_cells = 2160
N1curl dofs = 7552
x/y/corner constraints seconds = 0.200 / 0.009 / 0.001
floquet_total = 0.212 s
slave_edges = matched_master_edges = constraints = 832
x/y/corner constraints = 370 / 444 / 18
max_edge_midpoint_pairing_error = 0
max_masters_per_slave = 1
estimated_constraint_memory_mb = 0.029
case_status = completed
max_rss = 367.1 MB
```

MPI 4 smoke：

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果：

```text
result_dir = results/3D_floquet_airbox_normal_p1_h50p0_np4_20260622_035311
x/y/corner constraints seconds = 0.178 / 0.009 / 0.001
floquet_total = 0.192 s
slave_edges = matched_master_edges = constraints = 832
max_masters_per_slave = 1
case_status = completed
max_rss = 356.5 MB
```

斜入射相位 smoke：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case oblique \
  --mesh-target-size 100 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果：

```text
result_dir = results/3D_floquet_airbox_oblique_p1_h100p0_np2_20260622_035337
beta_x = -0.213960199402 + 0.976842378827j
beta_y = 0.546635756127 + 0.837370497524j
beta_x * beta_y = -0.934937284142 + 0.354813013743j
constraints = 218
max_masters_per_slave = 1
case_status = completed
```

负向检查：

```bash
python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case normal \
  --mesh-target-size 300 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果：按预期直接报错：

```text
NotImplementedError:
3D explicit Floquet edge topology constraints currently support only degree=1 N1curl.
Requested degree=2.
```

判定：本轮解决的是 Floquet 约束构建阶段的内存复杂度。`h=50 nm, p=1, MPI 2/4` 已经不再死在 building/resolving 阶段；若后续更大模型 OOM，应优先区分为线性求解器或后处理内存，而不是 Floquet constraint 构建。

## 2026-06-22 更新：3D Floquet 三段约束计时验证

本轮只验证新增计时输出，不作为物理精度验收。

编译检查：

```bash
. dolfinx-complex-mode
python3 -m compileall -q src
```

单元测试：

```bash
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 20 tests in 0.003s
OK (skipped=8)
```

串行 smoke：

```bash
python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case normal \
  --mesh-target-size 900 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

关键输出：

```text
building 3D Floquet x-direction low-level constraints seconds = 0.012
building 3D Floquet y-direction low-level constraints seconds = 0.008
resolving 3D double-Floquet corner/master chain seconds = 0.000
finalizing 3D double-Floquet MPC seconds = 0.002
floquet_total = 0.022
```

MPI 2 smoke：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case normal \
  --mesh-target-size 900 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

关键输出：

```text
building 3D Floquet x-direction low-level constraints seconds = 0.006
building 3D Floquet y-direction low-level constraints seconds = 0.005
resolving 3D double-Floquet corner/master chain seconds = 0.000
finalizing 3D double-Floquet MPC seconds = 0.001
floquet_total = 0.013
```

对应 `run_summary.json` 已包含：

```text
floquet_constraint_timings_seconds
timings_seconds.floquet_build_x_constraints
timings_seconds.floquet_build_y_constraints
timings_seconds.floquet_resolve_corner_master_chains
timings_seconds.floquet_mpc_finalize
timings_seconds.floquet_total
```

## 2026-06-19 更新：Stage 2 第一轮小网格扫描补跑

在修复 MPI Floquet 之后，又补跑了 PML 角度/参数 smoke 和 Fresnel sanity 扫描。这里先记录结论：这些结果用于定位，不代表 Stage 2 已经完成最终定量验收。

测试框架状态：

```text
compileall + 默认单元测试:
  Ran 20 tests, OK, skipped=8

Level 10 PDE sanity:
  RUN_STAGE2_PDE_TESTS=1 python3 -m unittest src.test.test_10_stage2_combined
  Ran 2 tests, OK
  no PML/Floquet: R/T/R+T = 3.16e-4 / 1.0101 / 1.0105
  Floquet-only:    R/T/R+T = 2.12e-4 / 1.0078 / 1.0080
```

Floquet oblique MPI：

```text
floquet_airbox oblique, MPI 2, p1, h300:
  result_dir = results/3D_floquet_airbox_oblique_p1_h300p0_np2_20260618_233033
  floquet_x/y mismatch = 3.75e-15 / 4.73e-15
  elapsed = 65.979 s, max_rss = 311.3 MB
  判定：通过。非零 kx/ky 相位在 side-wide MPI 约束下稳定。
```

PML 小扫描：

```text
pml_airbox theta=30 deg, s, p1, h900:
  result_dir = results/3D_pml_airbox_normal_p1_h900p0_20260618_233215
  mismatch = 3.53e-15 / 3.17e-15
  pml_reflection_proxy = 0.4437
  bottom decay ratio = 0.1939

pml_airbox theta=60 deg, s, p1, h900:
  result_dir = results/3D_pml_airbox_normal_p1_h900p0_20260618_233353
  mismatch = 3.53e-15 / 3.17e-15
  pml_reflection_proxy = 0.5830
  bottom decay ratio = 0.1901

pml_airbox theta=0 deg, alpha=10, p1, h900:
  result_dir = results/3D_pml_airbox_normal_p1_h900p0_20260618_233541
  mismatch = 3.53e-15 / 3.17e-15
  pml_reflection_proxy = 0.5580
  bottom decay ratio = 0.0551

pml_airbox theta=0 deg, thickness=350 nm, p1, h900:
  result_dir = results/3D_pml_airbox_normal_p1_h900p0_20260618_233721
  mismatch = 3.53e-15 / 3.17e-15
  pml_reflection_proxy = 0.7118
  bottom decay ratio = 0.0451
```

PML 判断：

```text
1. PML case 中 Floquet mismatch 均在 1e-15 量级，周期约束不再是当前主要问题。
2. bottom decay ratio 对角度、alpha 和厚度有响应；厚度 350 nm 下 bottom decay 从默认约 0.056 降到约 0.045。
3. pml_reflection_proxy 仍偏大，不能作为“PML 已定量通过”的证据；后续要结合更细网格和更稳的平面波拟合位置继续看。
```

Fresnel sanity 和小扫描：

```text
n_sub=1.0, theta=0, s, p2, h900, Floquet+PML:
  R/T = 0.5026 / 0.1935，未通过

n_sub=1.0, theta=0, s, p2, h300, Floquet+PML:
  R/T = 0.0657 / 1.0783，明显改善但仍未过硬门槛

n_sub=1.0, theta=0, s, p2, h200, no PML, no Floquet:
  result_dir = results/3D_fresnel_interface_normal_p2_h200p0_20260618_234431
  R/T/R+T = 3.16e-4 / 1.0101 / 1.0105
  判定：硬 sanity 在无 PML/Floquet 隔离路径上通过

n_sub=1.45, theta=0, s, p2, h200, no PML, no Floquet:
  R/T = 0.0621 / 0.9648，解析 R/T = 0.0337 / 0.9663

n_sub=1.45, theta=0, p, p2, h200, no PML, no Floquet:
  R/T = 0.2106 / 0.9182，解析 R/T = 0.0337 / 0.9663，p 偏振 normal 仍偏差大

n_sub=1.45, theta=30, s, p2, h200, no PML, no Floquet:
  R/T = 0.0534 / 1.0287，解析 R/T = 0.0494 / 0.9506

n_sub=1.45, theta=30, p, p2, h200, no PML, no Floquet:
  R/T = 0.0368 / 0.9623，解析 R/T = 0.0209 / 0.9791，R+T = 0.9990
```

Fresnel 判断：

```text
1. n_sub=1 的无 PML/Floquet 隔离 sanity 通过，说明 Fresnel 体方程和 R/T 拟合方向不是完全错误。
2. 一旦加回 PML+Floquet，n_sub=1 仍有明显 R/T 偏差，后续应优先定位 PML 区域场拟合位置、总场边界和 R/T 采样平面的相容性。
3. n_sub=1.45 的 no PML/Floquet 小扫描显示 s/p、theta=0/30 都有趋势，但 p-normal 和 s-theta30 的误差仍需细网格或后处理修正。
```

进一步隔离：

```text
n_sub=1.0, theta=0, s, p2, h200, Floquet only:
  result_dir = results/3D_fresnel_interface_normal_p2_h200p0_20260618_234837
  R/T/R+T = 2.12e-4 / 1.0078 / 1.0080
  判定：通过，Floquet 本身不是 n_sub=1 失败源

n_sub=1.0, theta=0, s, p2, h300, PML only:
  result_dir = results/3D_fresnel_interface_normal_p2_h300p0_20260618_234912
  R/T/R+T = 0.0348 / 1.1811 / 1.2159
  pml_reflection_proxy = 0.0663
  判定：未通过，主要偏差来自 PML/总场解析延拓/采样口径

n_sub=1.45, theta=0, p, p2, h200, Floquet only:
  result_dir = results/3D_fresnel_interface_normal_p2_h200p0_20260619_015708
  R/T/R+T = 0.0522 / 0.9378 / 0.9900
  Fresnel analytic R/T = 0.0337 / 0.9663
  判定：比无 Floquet 的 p-normal 结果明显稳定，p 偏振 Fresnel 验收应优先使用周期边界
```

PML-only 定位结论：

```text
当前 PML 验证仍是总场形式：入射波从上方穿过 top PML 时，按 exp(i k·z_tilde) 的复坐标延拓会在 top PML 中增长，而不是衰减。这会造成 PML 区域场幅值很大，粗网格下 R/T 拟合容易被污染。

因此 Stage 2 当前硬 sanity 应以 no PML/Floquet 或 Floquet-only 的 n_sub=1 为准；PML+总场版本先记为待定位，不作为进入 Stage 3 的硬门槛。真正让 PML+Fresnel 成为硬门槛前，需要改成更合理的 scattered/source 口径，或重新定义远离 PML 入口的 R/T 拟合位置。
```

Stage 2 当前完成判定：

```text
2A Floquet airbox:
  normal/oblique、serial/MPI smoke 均通过，h300 MPI mismatch 在 1e-15 量级。

2B PML airbox:
  PML 张量、cell tags、ParaView domain_tag、上下衰减指标和参数响应均已验证到 smoke 级别。
  由于当前是 total-field manufactured 口径，PML reflection proxy 不作为最终能量验收。

2C Fresnel interface:
  no PML/Floquet 与 Floquet-only 的 n_sub=1 硬 sanity 通过。
  n_sub=1.45 的 s/p、theta=0/30 小扫描完成并有合理趋势。
  PML+Fresnel 仍保留为 smoke/诊断项，后续 Stage 4 modal/source 口径再升级为功率硬门槛。
```

## 2026-06-19 更新：MPI Floquet side-wide 约束修复后的验证结果

额度恢复后已经补跑上一轮未完成的验证。`src/constraints/floquet_3d.py` 现在在 MPI 下不再逐三角面配对，而是对整张周期侧面拟合一个 Nedelec slave-to-master 变换。这样可以避开 `create_box` 在相对侧面使用不同三角剖分时造成的 facet pairing 错误。

本轮已完成验证：

```text
compileall + 默认 unittest:
  Ran 19 tests, OK, skipped=7

floquet_airbox normal, MPI 2, p1, h500:
  result_dir = results/3D_floquet_airbox_normal_p1_h500p0_np2_20260618_231036
  elapsed = 3.412 s, max_rss = 310.9 MB
  floquet_x/y mismatch = 1.18e-15 / 1.34e-15
  判定：通过，已修复之前 h500 mismatch 约 0.57/0.68 的问题

floquet_airbox normal, MPI 2, p1, h300:
  result_dir = results/3D_floquet_airbox_normal_p1_h300p0_np2_20260618_231101
  elapsed = 3.084 s, max_rss = 310.7 MB
  floquet_x/y mismatch = 3.75e-15 / 4.72e-15
  判定：通过，已修复之前 h300 超时且无 summary 的问题

pml_airbox normal, MPI 2, p1, h900:
  result_dir = results/3D_pml_airbox_normal_p1_h900p0_np2_20260618_231124
  elapsed = 83.406 s, max_rss = 2672.8 MB
  floquet_x/y mismatch = 6.20e-16 / 7.13e-16
  pml_reflection_proxy = 0.8223
  pml_decay_ratio_bottom = 0.0561
  判定：并行 Floquet 约束通过；PML 路径可作为 2B MPI smoke，但 PML proxy 还不能作为最终吸收性能验收

fresnel_interface normal s, serial, p2, h300, Floquet+PML:
  result_dir = results/3D_fresnel_interface_normal_p2_h300p0_20260618_231312
  elapsed = 187.920 s, max_rss = 3344.7 MB
  floquet_x/y mismatch = 2.22e-15 / 2.27e-15
  R/T/R+T = 0.018669 / 0.935656 / 0.954324
  Fresnel analytic R/T = 0.033736 / 0.966264
  判定：串行回归与上一轮一致；仍属于粗网格 smoke，不是最终定量验收
```

当前结论：

```text
1. Stage 2 的 MPI Floquet 约束路径已经从“h500/h300 不可靠”修正为“h500/h300 smoke 通过”。
2. pml_airbox MPI 2 h900 的 Floquet mismatch 已恢复到约 1e-15，说明 PML case 的并行周期约束不再是主要问题。
3. Fresnel+PML 的定量误差仍需后续做更细网格或更稳后处理扫描；本轮没有把它标记为最终通过。
4. 后续可以继续 Stage 2 参数扫描，但应优先控制 p2/h150 以下的内存压力。
```

## 2026-06-18 历史记录：继续定位后的结论

按新规则，本轮没有因为超时或物理误差暂停，而是继续定位。

关键修正：

```text
3D 串行 mesh builder 改为 z 方向显式包含 physical_z_min、interface_z、physical_z_max。
MPI 下暂时回退到 dolfinx.mesh.create_box，避免当前 Docker/DOLFINx 栈中自定义分布式 mesh segfault。
PDE 测试默认参数从 p1/h700 调整为 p2/h300。
```

Fresnel 定位结果：

```text
无 PML、无 Floquet，normal s：
  p1 h300: R/T = 0.526980 / 0.048783，未通过
  p2 h300: R/T = 0.061439 / 1.229299，明显改善但 T 偏高
  p2 h200: R/T = 0.062094 / 0.964772，T 接近解析，R 偏高
  p2 h150: R/T = 0.037266 / 0.940779，R 接近解析，R+T=0.978

加回 Floquet、无 PML，p2 h300：
  Floquet mismatch ≈ 1e-15
  R/T = 0.018938 / 0.955782，R+T=0.9747

加回 Floquet + PML，p2 h300：
  Floquet mismatch ≈ 2e-15
  R/T = 0.018669 / 0.935656，R+T=0.9543
  PML bottom decay ratio = 0.0762
```

当前判断：

```text
2C Fresnel 串行路径不是公式完全错误，而是 p1/h700 太粗且旧网格没有对齐界面/PML入口。
p2/h150 无 PML/Floquet 已经表现出合理收敛趋势。
p2/h300 加 Floquet/PML 可作为粗网格 smoke，但还不是最终定量验收。
```

MPI 定位结果：

```text
floquet_airbox MPI 2 h900:
  completed，Floquet mismatch ≈ 4e-16，输出 parallel.pvd

floquet_airbox MPI 2 h500:
  completed，但 Floquet mismatch ≈ 0.57 / 0.68，不能验收

floquet_airbox MPI 2 h300:
  5 分钟超时，无 summary

pml_airbox MPI 2 h900:
  completed，但 Floquet mismatch ≈ 0.51 / 0.51，只能算路径 smoke，不能算物理通过
```

当前判断：

```text
MPI 运行路径已恢复，不再 segfault。
但是 3D MPI Floquet 低层约束只在极小 h900 网格可靠；h500 已出现明显 mismatch，h300 性能超时。
后续需要专门优化/修正 3D MPI Floquet facet pairing 和 probe transform。
```

## 2026-06-18 更新：2C smoke 已跑通但未通过，MPI h300 超时

本轮补跑结果：

```text
fresnel_interface normal s, p1, h700, direct, serial
  case_status = completed
  R_total/T_total = 0.584166 / 0.311086
  Fresnel R/T     = 0.0337359 / 0.966264
  R/T error       = 0.550430 / 0.655178
  relative E err  = 1.93276
  elapsed/RSS     = 64.96 s / 2672 MB
  判定：路径跑通，但 2C 物理未通过

fresnel_interface normal p, p1, h700, direct, serial
  case_status = completed
  R_total/T_total = 0.900598 / 0.286458
  Fresnel R/T     = 0.0337359 / 0.966264
  R/T error       = 0.866862 / 0.679806
  relative E err  = 1.88091
  elapsed/RSS     = 60.75 s / 2674 MB
  判定：路径跑通，但 2C 物理未通过

floquet_airbox normal, MPI 2, p1, h300, direct
  第一次命令使用 OpenMPI 参数 --allow-run-as-root，被 MPICH/Hydra 拒绝。
  第二次改用 mpiexec -n 2，5 分钟超时。
  结果目录只生成 mesh_3d.h5 和 mesh_3d.xdmf，没有 run_summary.json。
  判定：未完成；后续已继续用 h900/h500 定位
```

这条历史记录之后，本轮已经继续定位。更新后的当前结论见本文最上方。

```text
2C 串行 Fresnel 已有收敛趋势；
2B PML MPI h900 已补跑但只能算路径 smoke；
3D MPI Floquet 在 h500/h300 仍需修正。
```

## 2026-06-18 更新：默认测试已通过，PDE/MPI 待补跑

已运行：

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 19 tests in 0.009s
OK (skipped=7)
```

解释：

```text
Level 0-3 默认严格测试已通过。
Level 4-10 是 PDE/综合测试入口，默认跳过，需要 RUN_STAGE2_PDE_TESTS=1 或单独 Docker/MPI 命令。
```

## 2026-06-18 更新：上一轮遗留项及本轮处理状态

上一轮文档明确留下三项未完成实跑，本轮处理状态如下：

```text
早期 fresnel_interface p1/h700 已补跑 s/p，但物理未通过；p2/h150 串行已有收敛趋势
floquet_airbox MPI 2 h300     已尝试，5 分钟超时
pml_airbox MPI 2              h900 已跑通，但 Floquet mismatch 大，只能算路径 smoke
```

本轮还新增十层测试框架。结果会按“先公式、再 PDE、最后 MPI/扫描”的顺序补充到本文件顶部。

## 当前测试命令

编译检查：

```bash
python3 -m compileall -q src
```

默认单元测试：

```bash
python3 -m unittest discover -s src/test -p "test_*.py"
```

PDE 小算例测试：

```bash
RUN_STAGE2_PDE_TESTS=1 python3 -m unittest discover -s src/test -p "test_*.py"
```

## 结果表

| 时间 | 测试 | 参数 | 结果 | 备注 |
|---|---|---|---|---|
| 2026-06-19 | 默认单元测试 | compileall + unittest discover | 通过 | 20 tests, skipped 8 PDE |
| 2026-06-19 | Level 10 PDE sanity | no PML/Floquet + Floquet-only | 通过 | 2 tests OK, 固定 h200 |
| 2026-06-19 | floquet_airbox oblique MPI 2 h300 | oblique, p1, h300 | 通过 | mismatch=3.75e-15/4.73e-15 |
| 2026-06-19 | PML 角度扫描 | theta=30/60, s, p1, h900 | smoke 通过 | bottom decay≈0.194/0.190 |
| 2026-06-19 | PML 参数扫描 | alpha=10, thickness=350 | smoke 通过 | bottom decay≈0.055/0.045 |
| 2026-06-19 | Fresnel n_sub=1 sanity | no PML/Floquet, p2, h200 | 通过 | R/T=3.16e-4/1.010 |
| 2026-06-19 | Fresnel n_sub=1 + PML/Floquet | p2, h300 | 未通过 | R/T=0.0657/1.078，需要定位 |
| 2026-06-19 | Fresnel n_sub=1 Floquet only | p2, h200 | 通过 | R/T=2.12e-4/1.008 |
| 2026-06-19 | Fresnel n_sub=1 PML only | p2, h300 | 未通过 | R/T=0.0348/1.181，定位到 PML |
| 2026-06-19 | Fresnel n_sub=1.45 小扫描 | no PML/Floquet, p2, h200 | 趋势通过 | theta=0/30, s/p 均完成 |
| 2026-06-19 | Fresnel p-normal Floquet only | n_sub=1.45, p2, h200 | 趋势通过 | R/T=0.0522/0.9378，R+T=0.990 |
| 2026-06-19 | compileall + Level 0-3 单元测试 | `python3 -m compileall -q src && python3 -m unittest discover -s src/test -p "test_*.py"` | 通过 | 19 tests, skipped 7 PDE |
| 2026-06-19 | floquet_airbox MPI 2 h500 | normal, p1, h500 | 通过 | mismatch=1.18e-15/1.34e-15 |
| 2026-06-19 | floquet_airbox MPI 2 h300 | normal, p1, h300 | 通过 | mismatch=3.75e-15/4.72e-15 |
| 2026-06-19 | pml_airbox MPI 2 h900 | normal, p1, h900 | smoke 通过 | mismatch=6.20e-16/7.13e-16，bottom decay=0.0561 |
| 2026-06-19 | Fresnel+Floquet+PML 回归 | serial, s, p2, h300 | smoke 通过 | R/T=0.0187/0.9357，仍需定量扫描 |
| 2026-06-18 | compileall | `python3 -m compileall -q src` | 通过 | Docker complex 环境 |
| 2026-06-18 | Level 0-3 单元测试 | `python3 -m unittest discover -s src/test -p "test_*.py"` | 通过 | 19 tests, skipped 7 PDE |
| 2026-06-18 | fresnel_interface smoke s | serial, p1, h700 | 未通过 | 程序完成，但 R/T 偏差大 |
| 2026-06-18 | fresnel_interface smoke p | serial, p1, h700 | 未通过 | 程序完成，但 R/T 偏差大 |
| 2026-06-18 | floquet_airbox MPI 2 h300 | normal, p1, h300 | 历史未完成 | 修复前只生成 mesh 文件，无 summary |
| 2026-06-18 | pml_airbox MPI 2 h900 | p1 | 历史 smoke | 修复前 mismatch 约 0.51 |
| 2026-06-18 | Fresnel 收敛定位 | serial, s, p2, h150 | 趋势通过 | R/T=0.0373/0.9408 |
| 2026-06-18 | Fresnel+Floquet+PML | serial, s, p2, h300 | smoke 通过 | R/T=0.0187/0.9357 |
| 2026-06-18 | floquet MPI 2 h900 | p1 | 路径通过 | mismatch 约 1e-15 |
| 2026-06-18 | floquet MPI 2 h500 | p1 | 历史未通过 | 修复前 mismatch 约 0.57/0.68 |
| 2026-06-18 | pml MPI 2 h900 | p1 | 历史 smoke | 修复前 mismatch 约 0.51 |

## 判定口径

`case_status=completed` 只说明线性求解和后处理没有崩溃，不代表物理已经验收。

Stage 2 真正验收需要同时看：

```text
relative_max_abs_E_error
floquet_x_face_mismatch / floquet_y_face_mismatch
pml_reflection_proxy / pml_decay_ratio_*
R_total / T_total / R_plus_T
fresnel_R_error / fresnel_T_error
max_rss_mb / elapsed_seconds
```

如果 PDE 误差偏大，本文件必须标记为“未通过/待定位”，不能因为程序跑完就写成通过。
