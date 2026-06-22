# Stage 2 续接日志

## 2026-06-22 3D Floquet 显式边拓扑约束已完成

本轮完成：

```text
1. src/constraints/floquet_3d.py 已改为正式使用 degree=1 N1curl mesh edge 拓扑配对。
2. probe function + pseudo-inverse / whole-plane dense transform 已从正式路径禁用。
3. corner edge 不再走 x 后 y 的 master chain，而是直接映射到 x=0,y=0，phase=beta_x*beta_y。
4. 每个 slave dof 只对应一个 master dof；max_masters_per_slave 实测为 1。
5. 如果 nedelec_degree > 1，直接 NotImplementedError。
6. run_summary.json 已新增：
   floquet_num_slave_edges
   floquet_num_matched_master_edges
   floquet_num_constraints
   floquet_max_edge_midpoint_pairing_error
   floquet_num_x_constraints
   floquet_num_y_constraints
   floquet_num_corner_constraints
```

已跑命令和结果：

```text
compileall + unittest:
  Ran 20 tests, OK, skipped=8

MPI 2, h=50 nm, p=1:
  result_dir = results/3D_floquet_airbox_normal_p1_h50p0_np2_20260622_035247
  x/y/corner seconds = 0.200 / 0.009 / 0.001
  constraints = 832
  estimated constraint memory = 0.029 MB
  max_masters_per_slave = 1

MPI 4, h=50 nm, p=1:
  result_dir = results/3D_floquet_airbox_normal_p1_h50p0_np4_20260622_035311
  x/y/corner seconds = 0.178 / 0.009 / 0.001
  constraints = 832
  estimated constraint memory = 0.029 MB
  max_masters_per_slave = 1

MPI 2, oblique, h=100 nm, p=1:
  result_dir = results/3D_floquet_airbox_oblique_p1_h100p0_np2_20260622_035337
  beta_x / beta_y / beta_x*beta_y 复相位路径通过。

degree=2 负向检查:
  按预期 NotImplementedError，不 fallback 到 dense。
```

当前注意事项：

```text
1. 只要 use_floquet_xy=True，当前 3D Floquet 正式路径就要求 nedelec_degree=1。
2. 后续若要支持 p=2，需要实现高阶 N1curl edge/face moment 的显式拓扑映射，不能恢复 probe/pinv 作为正式方法。
3. 当前 h=50 nm p=1 小模型 direct solver 也能跑完；更大模型如果 OOM，应先看 linear_problem_setup/solve/postprocess，而不是 Floquet building/resolving。
4. Stage 2 PML/Fresnel 的物理误差问题和本轮 Floquet 约束内存问题是两个问题，后续不要混在一起判断。
```

## 2026-06-19 Stage 2 小网格扫描补跑后的续接点

本轮在 `6f92eba Fix 3D MPI Floquet side constraints` 之后继续补跑了第一轮小网格扫描，并准备再提交文档记录。

最新测试状态：

```text
默认 compileall + unittest:
  Ran 20 tests, OK, skipped=8

Level 10 PDE sanity:
  no PML/Floquet 与 Floquet-only 两个 n_sub=1 测试均通过。
  测试代码固定使用 p2/h200，避免 h300 粗网格导致误判。
```

新增已跑结果：

```text
Floquet:
  oblique MPI 2 h300 通过，mismatch = 3.75e-15 / 4.73e-15

PML:
  theta=30 deg, s, p1/h900:
    proxy=0.4437, bottom decay=0.1939
  theta=60 deg, s, p1/h900:
    proxy=0.5830, bottom decay=0.1901
  alpha=10, theta=0, p1/h900:
    proxy=0.5580, bottom decay=0.0551
  thickness=350 nm, theta=0, p1/h900:
    proxy=0.7118, bottom decay=0.0451

Fresnel:
  n_sub=1.0, p2/h900, Floquet+PML:
    R/T=0.5026/0.1935，未通过
  n_sub=1.0, p2/h300, Floquet+PML:
    R/T=0.0657/1.0783，改善但仍未过硬门槛
  n_sub=1.0, p2/h200, no PML/Floquet:
    R/T=3.16e-4/1.0101，通过隔离 sanity
  n_sub=1.0, p2/h200, Floquet only:
    R/T=2.12e-4/1.0078，通过，Floquet 不是主要问题
  n_sub=1.0, p2/h300, PML only:
    R/T=0.0348/1.1811，未通过，问题主要指向 PML/总场口径
  n_sub=1.45, p2/h200, Floquet only, p-normal:
    R/T=0.0522/0.9378，R+T=0.9900，明显好于无 Floquet p-normal
  n_sub=1.45, p2/h200, no PML/Floquet:
    theta=0 s:  R/T=0.0621/0.9648
    theta=0 p:  R/T=0.2106/0.9182
    theta=30 s: R/T=0.0534/1.0287
    theta=30 p: R/T=0.0368/0.9623
```

当前最重要的剩余问题：

```text
1. Fresnel n_sub=1 在 no PML/Floquet 隔离路径通过，但加回 Floquet+PML 后仍不通过。
2. Floquet-only 也通过，PML-only 失败，说明主要问题来自 PML/总场解析延拓/采样口径。
3. p 偏振 normal incidence 在 Floquet-only 后明显改善，说明 Fresnel 验收应优先使用周期边界，不应依赖六面 Dirichlet 的无 Floquet p-normal 结果。
```

下一轮建议：

```text
1. Stage 2 基础边界条件工作可以收束，进入 Stage 3 前优先保持 Floquet-only Fresnel sanity 作为回归。
2. PML+Fresnel 的总场功率硬验收不要继续硬拧；后续应改成 scattered/source/modal port 口径后再升级为硬门槛。
3. 若后续修改 PML，必须重跑 n_sub=1 no-PML/Floquet、Floquet-only、PML-only 三组隔离 case。
```

## 2026-06-19 额度恢复后的完成情况

本轮从上一条“额度不足暂停点”恢复后，已完成验证并准备提交：

```text
已修改：
  src/constraints/floquet_3d.py
    - MPI 下改用 side-wide Floquet transform。
    - 不再逐三角 facet 配对，而是对整张周期侧面拟合 Nedelec 约束变换。

  notes/test/stage2_validation_report.md
  notes/test/stage2_resume_log.md
  notes/README.md
  notes/reference/code_walkthrough.md
  notes/theory/stage2_3d_floquet_pml_fresnel.md
    - 按“最新更新在上方”原则记录 h500/h300 修复结果。
```

已跑命令和结果：

```text
compileall + 默认 unittest:
  Ran 19 tests, OK, skipped=7

floquet_airbox MPI 2 h500:
  result_dir = results/3D_floquet_airbox_normal_p1_h500p0_np2_20260618_231036
  elapsed = 3.412 s
  floquet_x/y mismatch = 1.18e-15 / 1.34e-15

floquet_airbox MPI 2 h300:
  result_dir = results/3D_floquet_airbox_normal_p1_h300p0_np2_20260618_231101
  elapsed = 3.084 s
  floquet_x/y mismatch = 3.75e-15 / 4.72e-15

pml_airbox MPI 2 h900:
  result_dir = results/3D_pml_airbox_normal_p1_h900p0_np2_20260618_231124
  elapsed = 83.406 s
  floquet_x/y mismatch = 6.20e-16 / 7.13e-16
  pml_decay_ratio_bottom = 0.0561

fresnel_interface serial p2/h300, Floquet+PML:
  result_dir = results/3D_fresnel_interface_normal_p2_h300p0_20260618_231312
  R/T/R+T = 0.018669 / 0.935656 / 0.954324
```

当前未完成：

```text
1. 更细的 Fresnel+PML 定量扫描。
2. Stage 2 第一轮完整角度/偏振/PML 厚度参数扫描。
3. 更高阶或更细网格下 side-wide MPI Floquet 约束的内存和性能优化。
```

下一轮建议：

```text
1. 先做小网格参数扫描：theta = 0/30/60，s/p，PML 厚度和 alpha 各两组。
2. 对 Fresnel sanity 增加 n_sub=1 的 PDE 实跑，目标 R≈0、T≈1。
3. 再考虑 p2/h150 或更细的 Fresnel+PML 结果，注意内存。
```

## 2026-06-18 历史记录：额度不足暂停点

本轮停止原因：

```text
Docker 验证命令被系统拒绝，提示已达到 usage limit。
按用户规则：只有额度不足才暂停；因此本轮不再继续运行程序。
```

本轮已完成但尚未提交的代码/文档改动：

```text
src/geometry/mesh_builder_3d.py
  - 串行 3D mesh builder 改为 z 关键平面对齐。
  - MPI 下暂时 fallback 到 dolfinx.mesh.create_box，避免自定义分布式 mesh segfault。

src/test/stage2_test_utils.py
  - PDE 测试默认参数从 p1/h700 调整为 p2/h300。

notes/README.md
notes/reference/code_walkthrough.md
notes/theory/stage2_3d_floquet_pml_fresnel.md
notes/test/stage2_validation_report.md
notes/test/stage2_resume_log.md
  - 已记录串行 Fresnel 收敛趋势、MPI h500 mismatch、pml MPI h900 路径 smoke。

src/constraints/floquet_3d.py
  - 新增 MPI side-wide Floquet transform 方案：
    MPI 下不再逐三角 facet 配对，而是整张周期面一次拟合 slave-to-master 变换。
```

本轮已经验证过的结果：

```text
1. 修改 mesh builder 之前/之后，默认 compileall + unittest 曾通过。
2. 串行 Fresnel normal s：
   p2/h150, no PML, no Floquet -> R/T = 0.037266/0.940779
   Fresnel 解析 R/T = 0.0337359/0.966264
   说明串行 Fresnel 有收敛趋势。
3. 串行 Fresnel + Floquet + PML：
   p2/h300 -> R/T = 0.018669/0.935656
   可作为粗网格 smoke。
4. MPI fallback 到 create_box 后：
   floquet h900 completed, mismatch 约 1e-15
   floquet h500 completed, mismatch 约 0.57/0.68
   pml h900 completed, mismatch 约 0.51
```

尚未验证、下一轮必须先做：

```text
1. src/constraints/floquet_3d.py 的 MPI side-wide Floquet transform 代码尚未通过 compileall。
2. 尚未重跑默认 unittest。
3. 尚未重跑 floquet_airbox MPI 2 h500/h300 来验证 mismatch 是否被修复。
4. 尚未重跑 pml_airbox MPI 2 h900 来验证 2B 并行 smoke 是否改善。
5. 本轮未提交，因为额度不足发生在验证新 MPI Floquet 代码之前。
```

下一轮恢复后请从这里开始：

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
mpiexec -n 2 python3 -m src.runners.run_3d_airbox --stage-case floquet_airbox --case normal --nedelec-degree 1 --visualization-degree 1 --mesh-target-size 500 --solver-profile direct
mpiexec -n 2 python3 -m src.runners.run_3d_airbox --stage-case floquet_airbox --case normal --nedelec-degree 1 --visualization-degree 1 --mesh-target-size 300 --solver-profile direct
```

注意：

```text
如果 side-wide transform 编译或运行失败，优先修 src/constraints/floquet_3d.py。
如果 h500 mismatch 仍大，说明问题不只是三角 facet 配对，而可能是 side dof global ordering、probe span 或 Nedelec orientation 的 MPI 处理。
```

## 2026-06-18 继续定位后的续接点

按用户新规则，普通超时和物理误差不再暂停。本轮继续完成：

```text
1. 串行 3D mesh builder 改为 z 关键平面对齐：
   - physical_z_min
   - interface_z
   - physical_z_max

2. MPI 下暂时使用 create_box fallback：
   - 自定义分布式 z-aligned mesh 在当前 Docker/DOLFINx 栈中会 segfault。
   - fallback 先保证 MPI smoke 能运行。

3. PDE 测试默认参数改为 p2/h300，避免 p1/h700 作为错误验收入口。
```

新增定位结论：

```text
Fresnel serial:
  p2/h150, no PML, no Floquet: R/T = 0.037266/0.940779
  Fresnel 解析 R/T = 0.0337359/0.966264
  说明 2C 串行 Fresnel 有收敛趋势。

Fresnel + Floquet + PML serial:
  p2/h300: R/T = 0.018669/0.935656
  可作为粗网格 smoke，但还不是最终定量验收。

MPI Floquet:
  h900: mismatch 约 1e-15，路径通过。
  h500: mismatch 约 0.57/0.68，物理未通过。
  h300: 5 分钟超时。

PML MPI:
  h900: completed，但 Floquet mismatch 约 0.51，只能算路径 smoke。
```

当前未完成：

```text
1. 提交本轮 mesh/test/doc 更新。
2. 修正 3D MPI Floquet facet pairing/probe transform，使 h500/h300 也可靠。
3. 做 p2/h150 或更细的 Fresnel+PML 定量扫描。
4. 完整 Stage 2 参数扫描。
```

下一步建议：

```text
1. 优先修 MPI Floquet：h500 mismatch 大，说明约束构造在多 facet/多 rank 时不稳。
2. 在 MPI Floquet 修好前，不把 pml_airbox MPI 结果当物理验收。
3. 串行 Fresnel 可以继续 p2/h150、h120 收敛测试，但注意内存。
```

## 2026-06-18 规则更新：只有额度不足才暂停

用户已确认：除非遇到额度不足、工具调用被系统拒绝、或无法继续调用程序，否则不要因为普通失败、超时、误差大而暂停。后续处理规则改为：

```text
物理误差大       -> 继续定位
单个 case 超时   -> 降级网格/缩小 case/改诊断路径后继续
MPI 卡住或超时   -> 先跑更粗 MPI smoke，再定位并行瓶颈
额度不足或执行被拒绝 -> 写续接日志并暂停
```

## 2026-06-18 MPI 超时历史记录

这是规则更新前的历史记录。后续已经继续定位，并补跑了 h900/h500 和 pml_airbox MPI h900。

```text
floquet_airbox normal, MPI 2, p1, h300, direct
mpiexec -n 2 运行超过 5 分钟超时
结果目录只生成 mesh_3d.h5 和 mesh_3d.xdmf
没有 run_summary.json
```

本轮新增实跑结果：

```text
fresnel_interface normal s, p1, h700, serial
  completed，但 R_total/T_total = 0.584166/0.311086
  Fresnel R/T = 0.0337359/0.966264
  判定：2C 路径跑通，物理未通过

fresnel_interface normal p, p1, h700, serial
  completed，但 R_total/T_total = 0.900598/0.286458
  Fresnel R/T = 0.0337359/0.966264
  判定：2C 路径跑通，物理未通过
```

已提交：

```text
e9ea394 Refine 3D stage 2 metrics and comments
815dad0 Add 3D stage 2 test framework
b6629b7 Document 3D stage 2 test plan
62d79f6 Record 3D stage 2 smoke results
```

当前未完成：

```text
1. 修正 3D MPI Floquet h500/h300 的 mismatch/超时问题。
2. 继续串行 Fresnel+PML 更细网格定量扫描。
3. 完整扫描第一轮尚未跑。
```

下一轮建议不要直接继续大扫描，先定位：

```text
1. 先跑 fresnel_interface without PML / without Floquet 的 serial 小算例。
2. 检查 Fresnel total-field 边界是否与材料界面弱式相容。
3. 检查 R/T modal fitting 是否在 PML 或界面附近采样过粗。
4. MPI 先退回 h700 或 h900，确认能出 summary 后再尝试 h300。
```

## 2026-06-18 默认测试后续接点

已完成：

```text
1. Commit e9ea394：Refine 3D stage 2 metrics and comments
2. Commit 815dad0：Add 3D stage 2 test framework
3. Docker complex 环境中 compileall 通过。
4. 默认 unittest 通过：Ran 19 tests, OK, skipped=7。
```

尚未完成：

```text
1. fresnel_interface 物理偏差定位。
2. floquet_airbox MPI 2 h300 超时后的降级 smoke。
3. pml_airbox MPI 2。
4. 完整扫描第一轮。
```

下一轮或下一步优先命令：

```bash
python3 -m unittest discover -s src/test -p "test_*.py"
RUN_STAGE2_PDE_TESTS=1 python3 -m unittest discover -s src/test -p "test_*.py"
```

## 2026-06-18 当前续接点

本轮正在执行综合计划：

```text
Stage 2 收尾
Stage 2 重点代码结构注释
src/test 十层测试框架
notes/test 测试文档
补跑 fresnel_interface、floquet_airbox MPI 2 h300、pml_airbox MPI 2
```

已经完成：

```text
1. 修正 solve_airbox_maxwell_3d.py 的 2B/2C 指标路径：
   - PML reflection proxy 改为数值场上下行波拟合。
   - Fresnel R/T 改为从数值场拟合。
   - power_metrics_3d.json 只在存在数值 R/T 时写出。
   - summary 顶层补充 stage_case、mpi_size、mesh_target_size、nedelec_degree 等字段。

2. 新增 src/test/ 十层测试文件。

3. 新增 notes/test/ 测试说明、验证报告和续接日志。
```

尚未完成：

```text
1. Docker 编译检查。
2. Level 0-3 默认单元测试。
3. PDE 小算例测试。
4. fresnel_interface smoke test。
5. floquet_airbox MPI 2 h300。
6. pml_airbox MPI 2。
7. 回填 stage2_validation_report.md。
8. git commit 分阶段提交。
```

如果额度或 Docker 执行再次中断，下一轮从这里继续：

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

然后再补跑 Stage 2 的 Docker/MPI case。
# 2026-06-22 续接记录：3D Floquet 低内存重构中途暂停

## 当前暂停原因

Docker 验证命令触发额度/审批限制，无法继续运行容器实测。按约定，额度不足时暂停后续实跑，并先记录当前状态。

## 本轮已经修改的文件

```text
src/common/config_3d.py
src/runners/run_3d_airbox.py
src/main.py
src/geometry/mesh_builder_3d.py
src/constraints/floquet_3d.py
src/solvers/solve_airbox_maxwell_3d.py
notes/test/stage2_resume_log.md
```

注意：`src/main.py` 在本轮开始前已有用户未提交改动：

```text
NEDELEC_DEGREE_3D = 1
MESH_TARGET_SIZE_3D = 50.0
```

本轮只在这个区域追加了：

```text
MESH_CELL_TYPE_3D = "auto"
FLOQUET_CONSTRAINT_MODE_3D = "auto"
```

## 已完成的实现内容

```text
1. 新增 3D 配置字段：
   mesh_cell_type
   floquet_constraint_mode
   floquet_dense_memory_limit_mb
   floquet_dense_max_masters_per_slave

2. 新增 CLI 参数：
   --mesh-cell-type
   --floquet-constraint-mode

3. Stage 2 Floquet 默认 mesh_cell_type=auto 时解析为 hexahedron。
   hexahedron 网格会保证 Floquet smoke 至少 2x2x2 cells，避免 MPI rank 没有 cell 时卡住。

4. mesh builder 会输出：
   mesh_cell_type_resolved
   mesh_cells_resolved
   z_alignment_warnings

5. Floquet summary 新增：
   floquet_constraint_mode_resolved
   floquet_raw_map_nnz
   floquet_max_masters_per_slave
   floquet_estimated_constraint_memory_mb

6. 保留 dense_side_fit fallback，并加入 dense 内存阈值和每个 slave master 数截断。
```

## 已跑过且通过的命令

编译通过：

```bash
. dolfinx-complex-mode
python3 -m compileall -q src
```

单元测试通过：

```bash
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 20 tests
OK (skipped=8)
```

串行 hexa+sparse/floquet smoke 曾跑通：

```bash
python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case normal \
  --mesh-target-size 900 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

MPI 2 h900/p1 在 hexa+dense auto 调整前后曾跑通，关键现象：

```text
mesh cells resolved = (2, 2, 2)
floquet_build_x_constraints ≈ 0.04 s
floquet_build_y_constraints ≈ 0.04 s
floquet_resolve_corner_master_chains ≈ 0.00 s
floquet_mpc_finalize ≈ 0.001 s
```

MPI 2 h300/p1 hexa+dense_side_fit 回归通过，关键结果：

```text
floquet_constraint_mode_resolved = dense_side_fit
floquet_raw_map_nnz = 151
floquet_max_masters_per_slave = 9
floquet_estimated_constraint_memory_mb ≈ 0.004
floquet_x_face_mismatch ≈ 2.95e-15
floquet_y_face_mismatch ≈ 3.14e-15
```

## 已发现的问题

```text
1. dolfinx_mpc 内置 periodic helper 不可用：
   geometrical helper 对 Nedelec 报 Cannot evaluate dof coordinates。
   topological helper 对 vector valued periodic 报 not implemented。

2. hexa+p1 edge 一对一路径不可直接用：
   DOLFINx hexa Nedelec 在分区边上的 dof 数并不总是一条 edge 一个 dof。
   该辅助函数目前保留在 floquet_3d.py，但 active auto 路径不走它。

3. hexa+sparse_facet probe 小块路径内存低，但 h300/p1 的 x probe mismatch 仍约 0.7 到 0.9。
   因此它目前不能作为默认可信路径。

4. hexa+dense_side_fit 在 h300/p1 精度好，但 h50/p1 MPI 2 仍在 resolving corner/master chain 处被 signal 9 kill。
   初步判断：x/y raw maps 构建完成后，corner chain 展开时每个 slave 保留过多 master，角线复合导致内存峰值。
```

## 暂停前最后一个代码状态

已经把默认 `floquet_dense_max_masters_per_slave` 从 32 改成 8，但还没来得及验证。

下一轮第一件事应先跑：

```bash
. dolfinx-complex-mode
python3 -m compileall -q src
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case normal \
  --mesh-target-size 300 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

验收：

```text
确认 K=8 后 h300/p1 的 floquet_x/y_face_mismatch 是否仍接近 1e-15。
如果 mismatch 明显变差，需要把 K 调到 12 或 16 后重试。
```

然后再跑硬验收：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

判断标准：

```text
1. 必须完成 building x / building y / resolving corner-master chain / finalizing MPC。
2. 如果失败仍发生在 resolving corner/master chain，继续降低 K 或改 corner chain 解析为 bounded top-k 压缩。
3. 如果 Floquet 完成但 linear_problem_setup/solve OOM，则记录为直接求解器阶段问题，不再归因 Floquet。
```

## 下一轮建议

```text
优先实现 bounded corner-chain compression：
在 _resolve_mapping 或 _compress_terms 后增加 top-k 压缩，避免 8x8、16x16 的角线组合继续膨胀。
建议字段：
  floquet_corner_max_masters_per_slave = 16

然后再次验证 h300 和 h50。
```
