# 3D DtN 增广系统：完整追踪一个模式

本文沿一个 `(m,n,polarization,side)` 从 Floquet 波矢追踪到增广矩阵、入射 RHS、辅助幅值和 official R/T。当前 3D production 只实现 auxiliary DtN，不实现 explicit 端口外积求解。

## 1. 主要类型和入口

```text
common/modes_3d::DiffractionOrder3D
common/modes_3d::PortMode3D
common/modes_3d::enumerate_diffraction_orders_3d(cfg,...) -> list[DiffractionOrder3D]
common/modes_3d::outgoing_port_modes_3d(cfg) -> list[PortMode3D]
solvers/dtn_port_3d::solve_stage4_dtn_port_total_field(...) -> dict
```

`PortMode3D` 保存 side、m/n、polarization、`alpha/gamma/beta`、介质 n、vertical sign、E/k/H 向量、切向 E 范数、单位幅值功率、传播标记和 Rayleigh warning。

## 2. 第一步：横向 Floquet 波数

以 order `(m,n)` 为例：

$$\alpha_m=k_x+2\pi m/L_x,\qquad
\gamma_n=k_y+2\pi n/L_y.$$

`modes_3d::enumerate_diffraction_orders_3d` 分别计算 top/bottom 色散：

$$\beta_{top/bot}=\sqrt{(k_0n_{top/bot})^2-\alpha_m^2-\gamma_n^2}.$$

`positive_sqrt` 选择非负衰减/传播分支；`is_propagating` 允许 lossy complex beta，通过 `Re(beta)>0` 和色散实部判断；`near_rayleigh` 用 `|beta|/(|nk0|)` 标记截止邻域。

## 3. 第二步：side、极化和方向

`outgoing_port_modes_3d` 对每个 order 构造：

```text
top:    outward normal +z, vertical_sign=+1, medium=n_air
bottom: outward normal -z, vertical_sign=-1, medium=n_substrate
```

非退化横向波数使用

$$\mathbf s=(-\gamma,\alpha,0)/k_t,\qquad
\mathbf p=(\mathbf k/(k_0n))\times\mathbf s,$$

正入射退化点改用 x/y 基。`polarization_basis_3d` 归一化 E；`mode_eh_vectors` 形成

$$\mathbf k=(\alpha,\gamma,sign\,\beta),\quad
\mathbf H_{code}=\mathbf k\times\mathbf E/(k_0\mu_r).$$

`mode_power` 用 `0.5 Re(E x conj(H)) dot n` 乘单胞面积。auto policy 选择零阶以及传播阶；manual policy 还保留倏逝阶。

## 4. 第三步：边界相位与 surface vector

在该 side 的物理端口 `z_b`：

$$q_j(x,y,z_b)=\mathbf e_j
e^{i(\alpha x+\gamma y+sign\,\beta z_b)}.$$

`dtn_port_3d::_ReusableSurfaceComponentAssembler` 分别装配 x/y 表面分量，并对同一 `(side,m,n,beta)` 的两个极化复用。`_combine_owned_entries` 与 E 分量组合出 projection vector `ell_j`。

投影分母由 `_mode_projection_denominator` 给出：

$$d_j=L_xL_y\|\mathbf e_{t,j}\|^2
|e^{i k_{z,j}z_b}|^2.$$

因此辅助未知量是实际端口平面的 total-field modal projection，而不是任意归一化系数。

## 5. 第四步：traction

对于 plane wave，`curl E=i k x E`。代码：

```text
dtn_port_3d::_traction_vector
curl_vector = 1j * cross(mode.k_vector, mode.e_vector)
traction = cross(curl_vector, outward_normal(side))
```

用同一 surface component entries 与 traction 的 x/y 分量组合，得到 FE 方程中的列向量 `t_j`。法向随 top/bottom 改变，不能在两个端口复用同一符号。

## 6. 第五步：F/C/D/H block

Floquet MPC 装配后的 FE 块是 `F in C^(N_fe x N_fe)`。`_copy_base_matrix_to_augmented` 扩为 `(N_fe+N_aux)^2` AIJ；每个模式 j 插入：

```text
C[:,j] = -t_j
D[j,:] = -ell_j^H / d_j
H[j,j] = 1
```

于是当前实现的增广系统为

$$\begin{bmatrix}F&C\\D&I\end{bmatrix}
\begin{bmatrix}e\\a\end{bmatrix}
=\begin{bmatrix}f\\0\end{bmatrix},$$

其中符号已包含在 C/D 的插入定义中。H 不是稠密 modal block，当前严格为单位阵；checker 和 condensation 文档不得把它写成一般 dense coupling 的已实现版本。

## 7. 第六步：top incident RHS

`_incident_top_traction_form` 把已知 incident plane wave traction 组装到 FE RHS。对 top `(0,0)` 的相容极化，`_incident_projection_onto_top_mode` 还计算 total-field 中已知入射投影 `p_inc,j`；组装时把 `-t_j*p_inc,j` 加到 FE RHS。

bottom mode 和非零 top order 的 incident projection 为零。modal RHS 仍为零；入射信息全部在 FE RHS 与保存的 projection 中。

## 8. 第七步：求解与辅助幅值

`_solve_augmented_system` 或 assemble-only 分支处理 `A_aug,b_aug`。direct 成功后：

```text
_assign_fe_solution_from_augmented -> E_total Function
_gather_auxiliary_values -> replicated complex array length N_aux
_linear_residual -> ||A_aug x-b||/||b||
```

`E_total` 只复制前 `N_fe` 段并做 MPC backsubstitution；辅助行在矩阵中由最后一个 MPI rank 持有，`_gather_auxiliary_values` 再广播为可序列化数组。

## 9. 第八步：从 a 到 official R/T

`dtn_port_3d::_port_power_metrics` 定义：

```text
top outgoing amplitude    = a_j - incident_projection_j
bottom outgoing amplitude = a_j
```

`_mode_power_at_boundary` 重新乘实际 boundary phase，再用该 side 外法向计算正出射功率。只有 `mode.propagating=True` 的 channel 进入求和：top 贡献 R，bottom 贡献 T，最后除以 `incident_power_3d(cfg)`。

这解释了为何 top 必须扣入射而 bottom 不扣；也解释了 lossy bottom 的功率必须在实际端口面计算。

## 10. shape、ownership 和 target h5 示例

| 对象 | target h5 p2 |
|---|---:|
| `F` | 44,698 x 44,698 distributed sparse |
| `C` | 44,698 x 80 distributed sparse |
| `D` | 80 x 44,698 distributed sparse |
| `H` | 80 x 80 identity |
| augmented | 44,778 x 44,778 |
| auxiliary owner | 最后一个 rank 的 80 行 |
| MPI | 4 |

surface vector 每个 rank 只保存 owned nonzeros；小 auxiliary array 可复制。PETSc matrix/vector/KSP 必须在 RTA 和失败诊断结束后统一 destroy。

## 11. 输出与证据

输出包含 `dtn_auxiliary_amplitudes_3d.json`、order JSON/CSV、`port_power.json`、matrix stats、quadrature degree、mode cache timing 和 residual。Case020 验证平层 sanity，Case021 验证 direct target，Case031 验证凝聚后回代与 official RTA。

`test_14_stage4_dtn_modes.py` 检查 mode/power，`test_22_condensed_dtn.py` 检查 F/C/D/H 的代数凝聚。完整理论见 [`../../theory/dtn_modal_ports_and_condensation.md`](../../theory/dtn_modal_ports_and_condensation.md)。

## 12. 限制

- 3D Stage4 v1 只支持 `stage4_dtn_assembly=auxiliary`。
- 零阶正入射可进入 local Robin sanity 分支，不能拿其矩阵结构代表多 order target。
- H=I 是当前端口定义，不等于理论上所有 modal formulation 都必须是单位块。
- Rayleigh 附近、更多手动倏逝阶和新极化约定都要重新验证 quadrature 与功率归一化。
