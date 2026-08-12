# 2D Floquet、PML 与端口弱式

本文追踪 2D TM/TE 离散系统从网格、函数空间、Floquet 约束到 PML 或 port 边界。PML scattered-field 与 port total-field 是两种互斥的开边界配方。

## 1. 入口签名

```text
solve_vector_maxwell::run_case(cfg, out_dir, constraint_backend="manual") -> dict
solve_port_maxwell::run_port_case(cfg, out_dir, constraint_backend="manual",
                                  *, solution_observer=None) -> dict
solve_te_maxwell::run_te_case(cfg, out_dir, constraint_backend="manual") -> dict
solve_te_maxwell::run_te_port_case(cfg, out_dir, constraint_backend="manual") -> dict
```

`solution_observer` 只为 Case002 在内存中取得同一离散场作 explicit/auxiliary 比较，不写入普通用户接口。所有入口先要求 complex PETSc；TM 入口还要求 `polarization_type=TM`，TE 入口要求 `TE`。

## 2. 网格与空间

`mesh_builder::build_mesh(cfg,out_dir)` 返回 mesh、cell tags 和 facet tags。物理 cell 标签为 air/substrate/grating，PML cell 单独标记，左右和上下边界是 facet tags。

| 路线 | 未知量 | 元 | 全局规模 |
|---|---|---|---|
| TM | `(E_x,E_y)` | `N1curl`, degree=`nedelec_degree` | `V.index_map.size_global * bs` |
| TE | `E_z` | Lagrange, degree=`max(nedelec_degree,1)` | 同上 |

Nedelec 自由度带切向 orientation；Lagrange 自由度是标量节点值。两者不能共享一套约束系数或端口 admittance。

## 3. Floquet 约束

横向周期条件为

$$u(x+L_x,y)=e^{i k_xL_x}u(x,y).$$

TM 调用 `constraints/floquet_constraint.py::build_floquet_constraints(V,mesh_data,cfg)`，返回 slave/master DoF、复系数、orientation factor、pairing error 和 probe error。TE 调用 `constraints/floquet_scalar_constraint.py::build_scalar_floquet_constraints`。

manual 串行路径形成约束嵌入 `u=C u_r`，求解

$$C^HACu_r=C^Hb.$$

`dolfinx_mpc` 路径把相同主从关系保持为分布式 MPC；每个 rank 只拥有自己的行和向量片段。`dof_trace_mismatch` 在回代后检查解是否满足相位关系，它是约束 Gate，不是物理精度 Gate。

## 4. TM scattered-field + PML

`solve_vector_maxwell::run_case` 的真实顺序是：

```text
build_mesh -> N1curl V -> epsilon/epsilon_background
-> background_field_function -> build_floquet_constraints
-> UFL physical/PML forms -> manual or MPC solve
-> E_total=E_background+E_scat -> fields -> power metrics -> summary
```

物理域弱式为

$$a_{phys}(u,v)=\int curl\,u\,\overline{curl\,v}\,dA
-k_0^2\int\epsilon_r u\cdot\bar v\,dA,$$

右端为 `k0^2*(eps-eps_bg)*inner(E_background,v)`。代码锚点是 `solvers/solve_vector_maxwell.py::run_case`。

PML 区由 `common/pml.py::top_pml_tensors` 和 `bottom_pml_tensors` 提供变换后的 `epsilon`、`mu` 张量，分别使用空气和基座背景。UFL 仍装配到同一个 `A`，因此 PML cell 的 DoF 是系统未知量的一部分。

## 5. TE scattered-field + PML

`solve_te_maxwell::run_te_case` 使用标量梯度弱式：

$$a(u,v)=\int \nabla u\cdot\overline{\nabla v}\,dA
-k_0^2\int\epsilon_r u\bar v\,dA.$$

`common/pml.py::top_scalar_pml_coefficients` / `bottom_scalar_pml_coefficients` 返回梯度张量 `C` 与缩放质量系数。解得 `E_scat` 后逐自由度与背景场相加，并 scatter forward 形成 `E_total`。

## 6. Port total-field

port 路径直接在物理上下边界施加 Robin 或 Fourier-DtN，不装 PML。代码明确拒绝 `use_pml=True`，因为 port 弱式只对物理 cell 积分；若同时建立 PML cell，会留下未约束 Maxwell DoF。

TM Robin 零阶系数在 `run_port_case` 中计算：

```text
beta_air/sub = sqrt((k0*n)^2-kx^2)
q_top/sub = -i*(k0*n)^2/beta
top source = 2i*(k0*n_air)^2/beta_air * E_inc,x
```

TE 有独立的标量 Robin/DtN 系数。`port_boundary_model=dtn` 时 serial manual 路径支持 explicit 或 auxiliary；当前 nonlocal DtN 不支持 MPC backend。Robin 可走 MPC。

## 7. 矩阵、向量和 ownership

在 manual 路径：

1. DOLFINx 装配 full PETSc `A,b`；
2. 串行转换为 SciPy CSR/NumPy；
3. 加端口低秩项或增广模态行列；
4. 用 Floquet `C` 降阶；
5. SuperLU 解 reduced system；
6. 回填 full FE function。

在 MPC 路径，PETSc matrix/vector 依 communicator 分行持有，KSP 解后由 MPC backsubstitution 恢复 slave 值。普通 `fem.Function.x` 包含 owned+ghost local entries；写场或比较前必须 `scatter_forward()`。

## 8. 输入、输出和 shape

输入 `cfg` 是由 resolved dat 经 Task38 adapter 生成的内部 Python 配置；`V` 的全局 DoF 取决于 mesh 和阶次。输出 summary 至少包含：mesh cells、full/reduced DoF、reduced residual、solver backend、Floquet mismatch、field maxima、power metrics 和 elapsed time。

场文件将复数拆为 real/imag/abs；`run_summary.json` 与 `solver_log.txt` 由 rank 0 写。普通结果位于 `results/`，benchmark 的重型场位于 gitignored artifact root。

## 9. 一次真实调用顺序

```text
python scripts/run_case.py input/smoke/2d_tm_pml_floquet_smoke.dat
-> src.io.load_and_resolve
-> src.runners.task038_2d
-> run_cases::main
SimulationConfig
solve_vector_maxwell::run_case
postprocess::save_fields_and_plots
power_metrics::compute_power_metrics
```

port 对照可用 `2d_tm_dtn_auxiliary_smoke`。更改边界模型时不能只改 `port_boundary_model`；还要确认 `use_pml=False`、backend 支持、DtN order 和功率身份。

## 10. 测试与 benchmark

- Case001：TM + Floquet + PML 的 test-backed path smoke，尚非 PML 收敛证明。
- Case002：同网格 explicit/auxiliary 完整 solve 与 lossless closure。
- `test_05`：Floquet DoF 配对；相关 2D tests 覆盖约束和端口 helper。
- 成功 Gate：complex scalar、真残差、Floquet mismatch、无损能量关系；PML 还需厚度/强度/网格扫描。

## 11. 身份与限制

弱式与 residual 是 official 离散求解；probe RTA 是 diagnostic。manual 是串行参考路径，不能当作 MPI production。Stage2B 式的“能运行”不自动证明 PML 参数收敛。理论见 [`../../theory/maxwell_strong_weak_and_fem.md`](../../theory/maxwell_strong_weak_and_fem.md)、[`../../theory/floquet_periodicity.md`](../../theory/floquet_periodicity.md) 和 [`../../theory/pml_robin_and_open_boundaries.md`](../../theory/pml_robin_and_open_boundaries.md)。
