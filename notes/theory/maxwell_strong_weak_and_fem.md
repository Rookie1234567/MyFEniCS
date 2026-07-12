# Maxwell 强形式、弱形式与有限元

## 1. 时间谐波约定

项目采用

$$
\mathbf E(\mathbf x,t)=\Re\{\mathbf E(\mathbf x)e^{-i\omega t}\},\qquad
\mathbf H(\mathbf x,t)=\Re\{\mathbf H(\mathbf x)e^{-i\omega t}\}.
$$

无自由电流时 Maxwell 旋度方程为

$$
\nabla\times\mathbf E=i\omega\mu_0\mu_r\mathbf H,
\qquad
\nabla\times\mathbf H=-i\omega\epsilon_0\epsilon_r\mathbf E.
$$

消去 H，并用 `k0=omega/c`，得到项目求解的强形式

$$
\boxed{\nabla\times(\mu_r^{-1}\nabla\times\mathbf E)-k_0^2\epsilon_r\mathbf E=\mathbf f.}
$$

由第一式还原磁场：

$$
\mathbf H=\frac{1}{i\omega\mu_0\mu_r}\nabla\times\mathbf E.
$$

代码单位把公共常数移出，使用 `H_code=curl(E)/(i*k0*mu_r)`；所有归一化功率必须沿用同一约定。

## 2. 3D H(curl) 弱式

取测试函数 `v`，分部积分：

$$
\begin{aligned}
a(\mathbf E,\mathbf v)
&=\int_\Omega \mu_r^{-1}(\nabla\times\mathbf E)\cdot
\overline{\nabla\times\mathbf v}\,dV\\
&\quad-k_0^2\int_\Omega\epsilon_r\mathbf E\cdot\overline{\mathbf v}\,dV
+a_{\partial\Omega}(\mathbf E,\mathbf v),\\
L(\mathbf v)&=\int_\Omega\mathbf f\cdot\overline{\mathbf v}\,dV+L_{\partial\Omega}(\mathbf v).
\end{aligned}
$$

体积分逐材料 tag 装配；PML 用变换后的张量；Robin/DtN 进入边界项。源码是 `solvers/common_3d_forms.py::_build_variational_forms`。UFL `inner` 在复数模式下形成 Hermitian 测试内积，所以 PETSc 必须是 complex build。

### 为什么用 Nedelec

电场的物理连续量是界面切向分量。Nedelec H(curl) 元让切向迹跨单元相容，并允许法向分量按材料界面条件跳变；普通逐分量 H1 元会错误强化全部分量连续。`common_3d_solve._create_nedelec_space` 与 2D `solve_vector_maxwell.run_case` 创建 `N1curl` 空间。

## 3. 2D TM 约化

结构沿 z 不变，TM 路线未知量为面内电场

$$\mathbf E=(E_x,E_y,0),\qquad
\nabla\times\mathbf E=(0,0,\partial_xE_y-\partial_yE_x).$$

弱式仍是 curl-curl 形式：

$$
\int_\Omega \operatorname{curl}_{2D}\mathbf E\,
\overline{\operatorname{curl}_{2D}\mathbf v}\,dA
-k_0^2\int_\Omega\epsilon_r\mathbf E\cdot\overline{\mathbf v}\,dA.
$$

`common/pml.py::curl_3d` 把二维旋度嵌入三维，`solve_vector_maxwell.run_case` 组装 scattered-field 方程。

## 4. 2D TE 约化

TE 路线令 `E=(0,0,E_z)`，未知量是标量。强形式为

$$-\nabla\cdot(\mu_r^{-1}\nabla E_z)-k_0^2\epsilon_rE_z=f,$$

在 `mu_r=1` 时弱式为

$$
\int_\Omega\nabla E_z\cdot\overline{\nabla v}\,dA
-k_0^2\int_\Omega\epsilon_rE_z\overline v\,dA=L(v).
$$

因此 TE 用 Lagrange H1 元，见 `solve_te_maxwell.run_te_case/run_te_port_case`。TE 与 TM 的 Poynting 重构方向不同，不能混用后处理公式。

## 5. total、incident-scattered 与 layered-scattered

设 `E=E_b+E_s`，背景场满足背景介质算子。代入目标介质方程后：

$$
\mathcal L_{\epsilon}E_s=k_0^2(\epsilon-\epsilon_b)E_b.
$$

2D `solve_vector_maxwell` 和 `solve_te_maxwell` 用此式。3D Stage 2C 的源只在基座 contrast 区；Stage 4 layered-scattered 源只在光栅相对分层背景的 contrast 区。Stage 4 DtN 正式路径则组装 total-field + 端口源。

## 6. 复材料与吸收

项目令 `epsilon_r=n^2`。对当前时间约定，耗散密度为

$$p_{abs}=\frac{\omega\epsilon_0}{2}\operatorname{Im}(\epsilon_r)|E|^2.$$

因此 `Im(epsilon_r)>0` 才进入正吸收。代码在 `power_metrics._volume_absorption_metrics` 与 `rta_3d._region_absorbed_power` 中使用 `Im(epsilon_r)`，不是直接使用 `Im(n)`。

## 7. 离散系统与约束

不加周期约束时得到 `A u=b`。Floquet 主从映射写成 `u=C u_r`，降阶系统为

$$C^HAC\,u_r=C^Hb.$$

`manual` 后端显式形成该系统；`dolfinx_mpc` 在 MPI 中保持分布式约束。代数残差小只证明离散方程被求解，不证明网格、边界或物理模型正确。

## 8. 代码和测试

| 理论对象 | 源码 | 直接测试 |
|---|---|---|
| 单位/相位/H 重构 | `common/units.py`, configs, postprocess | `test_00`, `test_01` |
| 2D TM 弱式 | `solve_vector_maxwell.py` | 2D benchmark/validation |
| 2D TE 弱式 | `solve_te_maxwell.py` | TE/复材料 benchmark |
| 3D 弱式 | `common_3d_forms.py` | `test_04`, Stage 1 benchmark |
| 材料标签 | `materials.py`, mesh builders | `test_15`, `test_16` |

官方实现对照：DOLFINx 的 Maxwell scattering demo 给出同型 curl-curl 复数弱式，<https://docs.fenicsproject.org/dolfinx/main/python/demos/demo_scattering-boundary-conditions.html>。
