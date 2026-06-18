# Stage 1：3D 空气盒子快速运行指南

## 2026-06-18 更新：求解器 profile 怎么选

当前默认求解器仍然是原来的直接法：

```python
SOLVER_PROFILE_3D = "default"
```

`default` 等价于 `direct_lu`，内部仍然使用：

```text
ksp_type = preonly
pc_type = lu
```

也就是说，不改这个变量时，小规模空气盒子的基准行为不变。

如果压力测试遇到内存不足，可以先尝试这些迭代 profile：

```python
SOLVER_PROFILE_3D = "iterative_asm_ilu"
```

或者：

```python
SOLVER_PROFILE_3D = "iterative_bjacobi_ilu"
```

完整可选值如下：

| profile | 含义 | 适合用途 |
|---|---|---|
| `default` | 原来的直接法 | 小模型基准、确认公式和边界条件 |
| `direct_lu` | 显式直接法 | 和 `default` 一样，只是名字更明确 |
| `iterative_asm_ilu` | `fgmres + asm + local ilu` | 优先尝试的低内存并行方案 |
| `iterative_bjacobi_ilu` | `fgmres + bjacobi + local ilu` | 更简单的并行预条件方案 |
| `iterative_jacobi` | `fgmres + jacobi` | 很省内存的基线，主要用于判断迭代能不能推进 |
| `iterative_hypre` | `fgmres + hypre boomeramg` | 实验选项，检查当前 PETSc/HYPRE 对复数问题的支持 |

相关容差变量也放在 `src/main.py` 的 3D 区块：

```python
SOLVER_RTOL_3D = 1.0e-8
SOLVER_ATOL_3D = 1.0e-12
SOLVER_MAX_IT_3D = 1000
SOLVER_MONITOR_3D = False
```

命令行也可以临时覆盖：

```text
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox --case normal --solver-profile iterative_asm_ilu --solver-rtol 1e-8 --solver-max-it 1000
```

运行后重点看：

```text
solver_profile
solver_profile_resolved
solver_petsc_options
ksp_converged
ksp_converged_reason_name
ksp_iterations
solver_residual_norm
max_rss_mb
timings_seconds
```

这些字段会同时写入 `run_summary.json`，并在 `solver_log.txt` 中打印。

这个文件对应四步路线里的第一步：先建立一个最小 3D 全矢量 Maxwell 求解框架，并用均匀空气盒子里的解析平面波检查它。

## 运行哪个文件

2D 和 3D 现在统一从同一个入口运行：

```text
src/main.py
```

打开 `src/main.py`，用这个开关选择运行哪条路线：

```python
SIMULATION_DIMENSION = "2d"  # 原来的 2D 光栅路线
SIMULATION_DIMENSION = "3d"  # 新的 3D 分步路线
```

这样做的原因是：日常只需要记住一个 `main.py`，但 2D 和 3D 仍然在 runner/config/solver 层分开，不会互相改坏。

## PyCharm 里怎么改参数

打开 `src/main.py`，先把：

```python
SIMULATION_DIMENSION = "3d"
```

然后主要改这几个 3D 大写变量：

```python
AIRBOX3D_CASE = "both"        # "normal", "oblique", or "both"
INCIDENT_THETA_DEG_3D = None  # None 表示使用 normal/oblique 预设
INCIDENT_PHI_DEG_3D = None
POLARIZATION_KIND_3D = None   # None 表示使用预设；也可以是 "s" 或 "p"
NEDELEC_DEGREE_3D = 2
VISUALIZATION_DEGREE_3D = 2
MESH_TARGET_SIZE_3D = 140.0
UNIQUE_OUTPUT = True
```

建议刚开始保持默认值。默认会跑两个测试：

```text
normal  ：k = (0, 0, -k0)，p = (1, 0, 0)
oblique ：一个简单斜入射方向，偏振选成和 k 垂直
```

如果自己指定角度，约定是：

```text
INCIDENT_THETA_DEG_3D：从向下 -z 方向偏开的角度。0 度就是正入射。
INCIDENT_PHI_DEG_3D  ：在 x-y 平面里的方位角。0 度朝 +x，90 度朝 +y。
```

## 命令行怎么跑

在 Docker/DOLFINx 环境中可以运行：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox --case both
```

只跑正入射：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox --case normal
```

只跑斜入射：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox --case oblique
```

也可以从统一入口运行：

```bash
python3 fenics_vector_maxwell_floquet_demo_v2_parallel/src/main.py 3d --case both
```

## 输出看哪里

结果会写到类似下面的目录：

```text
results/3D_airbox_stage1_normal_oblique_p2_h140p0_YYYYMMDD_HHMMSS/
```

如果跑 `both`，里面会有两个子目录：

```text
airbox3d_normal/
airbox3d_oblique/
```

每个子目录里重点看：

```text
run_summary.json
solver_log.txt
fields_3d_for_paraview.vtu
```

在 ParaView 里打开：

```text
fields_3d_for_paraview.vtu
```

里面包含：

```text
E_V_per_m_real, E_V_per_m_imag, E_V_per_m_abs
E_exact_abs_V_per_m, E_error_abs_V_per_m
H_A_per_m_real, H_A_per_m_imag, H_A_per_m_abs
H_exact_abs_A_per_m, H_error_abs_A_per_m
domain_tag
```

ParaView 输出采用 COMSOL 风格的物理单位显示。默认 `incident_e0_v_per_m = 1.0`，所以：

```text
E_V_per_m = E_code * 1.0 [V/m]
H_A_per_m = H_code / eta0 [A/m]
eta0 = 376.730313668 ohm
```

`E_V_per_m_real/E_V_per_m_imag/H_A_per_m_real/H_A_per_m_imag` 是 3 分量 vector 数组。需要看 `Ex`、`Ey`、`Ez` 或 `Hx`、`Hy`、`Hz` 时，在 ParaView 里选择对应 vector component 即可，不再额外输出一大串分量变量。

## 验收看什么

先看 `solver_log.txt` 或 `run_summary.json`：

```text
PETSc ScalarType
mesh cells
3D N1curl dofs
solver residual norm
relative_max_abs_E_error
relative_max_abs_H_error
poynting_direction_cosine
paraview_file
```

现在 `solver_log.txt` 也会像总耗时一样打印各阶段耗时；`run_summary.json` 中对应字段是 `timings_seconds`：

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

MPI 并行运行时，这些阶段耗时会取所有 rank 里的最大 wall time，因此可以用来判断真正慢的是建网格、建立函数空间、线性求解，还是后处理。

`poynting_direction_cosine` 越接近 1，说明平均能流方向越接近设定的传播方向。

`relative_max_abs_E_error` 不是机器零，因为解析平面波不是有限元空间里的精确多项式；网格变细或 Nédélec 阶数提高后，它应该下降。
