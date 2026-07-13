# 2D DtN 与 R/T/A 后处理

本文从一个 2D Fourier order 追踪到矩阵、解、端口功率和体吸收，并用 Case002/003 的 canonical record 给出具体规模。

## 1. 关键入口

```text
solve_port_maxwell::_select_dtn_port_modes(cfg,log) -> dict
solve_port_maxwell::_build_dtn_trace_data(...) -> trace vectors
solve_port_maxwell::_add_fourier_port_operators_explicit(...) -> A,b,modes,traces
solve_port_maxwell::_add_fourier_port_operators_auxiliary(...) -> augmented A,b,...
solve_port_maxwell::run_port_case(...) -> summary

power_metrics::compute_dtn_port_power_metrics(...) -> trace RTA
power_metrics::compute_dtn_auxiliary_power_metrics(...) -> auxiliary RTA
power_metrics::compute_te_dtn_port_power_metrics(...) -> TE RTA
power_metrics::_volume_absorption_metrics(...) -> absorbed power and A_volume
```

TM 与 TE 都使用上下端口 Fourier order，但未知量和 admittance 不同；TE 的 scalar DtN 在 `solve_te_maxwell.py` 中独立装配。

## 2. 从 order 到传播常数

对横向周期 `L_x`：

$$\alpha_m=k_x+2\pi m/L_x,\qquad
\beta_m=\sqrt{(k_0n)^2-\alpha_m^2}.$$

`solve_port_maxwell::_positive_sqrt` 选择实部/虚部非负的分支。`_is_near_rayleigh` 标记 `|beta|` 接近零的截止级；`_is_clearly_propagating` 使用 `Re(beta)>0` 和色散量实部，而不是错误要求 `Im(beta)=0`。因此复折射率基座中的传播模仍能携带实功率。

## 3. Fourier trace 与两种装配

`_fourier_trace_vector(V,mesh_data,tag,alpha)` 装配边界投影向量 `ell_m`；`_compress_trace_vector` 只保留非零条目。设无端口 FE 块为 `F`、full FE DoF 为 `N`、选中模态数为 `M`。

explicit 路径把每个低秩外积直接加入 `N x N` CSR：

$$A_{exp}=F+\sum_m q_m\ell_m\ell_m^H.$$

auxiliary 路径引入 top/bottom 模态系数，形成 `(N+M) x (N+M)` 增广矩阵。其 FE/modal coupling 保持边界稀疏结构，解后 `_auxiliary_coefficients_by_side` 直接取得端口系数。

两条路径随后使用相同 Floquet 约束嵌入降阶。Case002 的 `solution_observer` 在写后处理前抓取 full FE coefficient array，使比较不受文件插值影响。

## 4. Case002 完整等价证据

相同 10 x 10 nm、无损、零材料对比、p1/h2 网格的结果为：

| 指标 | explicit | auxiliary |
|---|---:|---:|
| FE DoF | 139 | 139 |
| auxiliary DoF | 0 | 2 |
| full matrix rows | 139 | 141 |
| full nnz | 727 | 673 |
| reduced rows | 133 | 135 |
| reduced nnz | 721 | 667 |
| linear true residual | 2.168e-15 | 1.867e-15 |
| elapsed/s | 8.334 | 2.811 |

full FE field relative difference 为 `2.771e-15`，R/T/A 最大绝对差为 `1.221e-15`。两者均得到 `R=4.7765e-4`、`T=0.9995223452`，能量闭合在机器精度。证据文件是 [`../../../benchmarks/cases/002_2d_tm_dtn_equivalence/records/comparison.json`](../../../benchmarks/cases/002_2d_tm_dtn_equivalence/records/comparison.json)。

## 5. 端口平面功率

对实际端口平面的 coefficient `a_m(y_port)`，TM 模态功率写成

$$P_m=L_x\,\frac{\operatorname{Re}Y_m}{2}|a_m(y_{port})|^2.$$

代码锚点是 `power_metrics::_modal_power_on_plane`。`reflected_amp`/`transmitted_amp` 中去掉传播相位的版本用于报告界面等效相位，不得用于功率。对有损有限基座，若把 coefficient 反向搬回界面再算 T，会人为撤销传播吸收并与 `A_volume` 重复计数。

`_is_propagating(beta,dispersion_value)` 只让携带正实法向功率的级进入 R/T；倏逝级仍可出现在端口算子中，但其远场功率为零。

## 6. Official 与 diagnostic 路径

| 计算 | 函数 | 身份 |
|---|---|---|
| TM auxiliary amplitudes | `compute_dtn_auxiliary_power_metrics` | official/recommended |
| TM boundary trace | `compute_dtn_port_power_metrics` | explicit official 或 auxiliary cross-check |
| TE boundary trace | `compute_te_dtn_port_power_metrics` | official |
| volume `Im(epsilon)|E|^2` | `_volume_absorption_metrics` | official A |
| E/H probe line fit | `_compute_*_power_metrics_from_lines` | diagnostic_only |
| near-field integrals | `compute_near_field_integrals` | diagnostic |

`_attach_absorption_metrics` 同时写 `A_balance=1-R-T`、`A_volume`、两者差和 `R+T+A_volume`。probe 不得覆盖 official，即使 probe closure 看起来更接近 1。

## 7. Case003 有耗证据

两种偏振分别冻结真实 resolved config，不假设 TE/TM 使用同一网格：

| 指标 | TM complex | TE complex |
|---|---:|---:|
| 几何周期/air/substrate nm | 100/100/50 | 10/5/5 |
| FE + auxiliary DoF | 14,452 + 30 | 56 + 0 |
| residual | 3.323e-14 | 1.486e-15 |
| peak RSS/MB | 365.30 | 287.48 |
| R | 3.6625e-6 | 8.7456e-5 |
| T | 0.8821724521 | 0.9903457798 |
| A_volume | 0.1178238854 | 0.0095667639 |
| `1-R-T-A_volume` | -3.331e-15 | 5.829e-16 |
| probe closure，diagnostic | -0.021317 | 0.075125 |

TM auxiliary-vs-trace 最大差为 `1.221e-15`。canonical records 位于 [`../../../benchmarks/cases/003_2d_te_tm_complex_absorption/records`](../../../benchmarks/cases/003_2d_te_tm_complex_absorption/records)。

## 8. 数据 shape 与 ownership

manual 2D 路径是串行：PETSc full matrix 转 SciPy CSR，Floquet reduction 后由 SuperLU 求解。FE coefficient array 长度为 full DoF；auxiliary array 长度等于选中 side/order 数。trace bank 按 `side -> order -> compressed indices/values` 保存。

MPC backend 目前不用于 nonlocal DtN。普通场函数仍需要 `scatter_forward`；JSON 只在 rank 0 写。Case002/003 的轻量 record 提交 Git，完整 VTU、日志和临时解目录留在 gitignored `benchmarks/artifacts/cases/...`。

## 9. 一次真实调用顺序

```text
benchmarks.run_2d_canonical
-> SimulationConfig
-> run_port_case / run_te_port_case
-> select modes and assemble trace vectors
-> explicit or auxiliary matrix
-> Floquet reduction + direct solve
-> boundary coefficient / auxiliary extraction
-> official R/T + volume A
-> diagnostic probe
-> lightweight canonical record
```

## 10. 自动 Gate

`benchmarks/check_benchmarks.py` 检查 Case002 的两次 residual、field difference、R/T/A difference 和 lossless closure；检查 Case003 的 residual、R/T/A 非负、`A_balance≈A_volume`、closure、TM aux/trace 差，以及 probe 身份必须为 `diagnostic_only`。

lossless regression 还覆盖零对比 `R≈0,T≈1`、无损平界面 `R+T≈1`、截止级零功率和 lossy propagating order 正功率。

## 11. 限制

- 2D nonlocal DtN 目前是 serial manual；不能把它描述为 MPI production。
- near-Rayleigh order 的分类和功率对容差敏感，需单独扫描。
- algebraic closure 不等于网格收敛或材料实验准确性。
- 本轮 2D 有耗口径变化不重算 3D Task27 h5/h3/h2 records；3D official RTA 仍由其独立代码路径生成。

推导见 [`../../theory/dtn_modal_ports_and_condensation.md`](../../theory/dtn_modal_ports_and_condensation.md) 和 [`../../theory/official_and_diagnostic_rta_methods.md`](../../theory/official_and_diagnostic_rta_methods.md)。
