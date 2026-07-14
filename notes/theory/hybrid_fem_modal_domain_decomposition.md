# Hybrid FEM–Modal 域分解方法理论笔记

## 0. 目的与适用范围

本文供 Task032 实现参考，目标是把当前完整三维 Maxwell 计算域拆成：

```text
bottom local 3D FEM
+ middle z-invariant modal region
+ top local 3D FEM
```

中间区域满足：

$$
\varepsilon(x,y,z)=\varepsilon(x,y),
$$

因此无需沿 z 方向使用密集三维体网格，可以用二维横截面本征模沿 z 解析传播。

本文只讨论：

- 频域全矢量 Maxwell；
- 双 Floquet 横向周期；
- 有损复材料；
- 匹配接口网格；
- 直接法增广系统与 Modal-Schur；
- 稳定的双向模态传播；
- 内存友好的离散与对象生命周期。

本文不讨论 h/p 自适应、迭代法、非匹配 mortar、0.7 nm 材料色散和参数反演。

## 0.1 Phase 2 离散实现锚点

当前 Phase 2 代码把本文的截面问题落实为：

```text
src/modes/cross_section_spaces.py
src/constraints/cross_section_floquet.py
src/modes/quadratic_beta_eigenproblem.py
```

匹配二维网格复用 `stage4_axis_plan` 的 x/y 轴；横向场使用二维
`N1curl(p2)`，纵向分量使用 `Lagrange(p2)`。离散多项式保持
`K0 + beta K1 + beta^2 K2`，其中 `K2` 的纵向块为零，因此最高次矩阵
按物理设计奇异。双 Floquet 条件通过分布式 `u=Cq` 消元，每个系数矩阵
以 `C^H K C` 稀疏约化，再交给 SLEPc PEP/TOAR；没有 dense 全谱和 rank0
全本征向量聚集。

Phase 2 的 electric-L2 归一化只建立稳定的场尺度。本文后述的 Poynting
方向、left/right 双正交、`Q'(beta)` 与近简并子空间归一化仍属于 Phase 3，
不能用当前 L2 字段替代最终接口功率归一化。

## 0.2 Phase 3 分类与双正交实现锚点

当前 Phase 3 代码位于 `src/modes/mode_classification.py`。它从混合场按
`curl E = i omega mu H` 重构阻抗缩放 H，以截面平均 Poynting flux 优先分类
传播方向，并把有非零 flux 的右模归一到 `abs(Pz)=1`。near-zero flux 模式
按 `Im(beta)` 选择远离接口的衰减分支；仍无法判定的实 beta 被显式标为
cutoff/ambiguous。

合格镜像的 SLEPc PEP Python API 没有 two-sided left-vector 接口，因此代码
显式求解 `K0^H + lambda K1^H + lambda^2 K2^H`，以
`lambda approx conj(beta)` 配对左模。归一化使用
`left_i^H [K1 + (beta_i+beta_j)K2] right_j`；严格/近简并 block 只在小型
mode-count overlap 矩阵上做逆变换，奇异或条件数超过 `1e12` 时 fail closed。
完整左右向量继续按 PETSc ownership 分布，不在 rank0 聚集。

相邻参数 tracking 用 left/right QEP overlap 做最大权指派；近简并组另用
electric-mass Gram whitening 后的 principal angles 比较子空间。Phase 3
仍不包含 100 nm 稳定传播和 3D 接口投影。

---

# 1. 物理域和基本方程

设完整计算域为：

$$
\Omega
=
\Omega_b
\cup
\Omega_m
\cup
\Omega_t,
$$

其中：

- $\Omega_b$：底部局部三维 FEM 区域；
- $\Omega_m$：中间 z 不变模态区域；
- $\Omega_t$：顶部局部三维 FEM 区域。

内部接口：

$$
\Gamma_b=\partial\Omega_b\cap\partial\Omega_m,
$$

$$
\Gamma_t=\partial\Omega_t\cap\partial\Omega_m.
$$

频域 Maxwell 方程采用 $e^{-i\omega t}$ 或 $e^{+i\omega t}$ 约定均可，但代码、DtN、Poynting flux 和模态传播符号必须全项目一致。以下采用：

$$
\nabla\times\mathbf E
=
i\omega\mu\mathbf H,
$$

$$
\nabla\times\mathbf H
=
-i\omega\varepsilon\mathbf E.
$$

消去 $\mathbf H$：

$$
\nabla\times
\left(
\mu^{-1}\nabla\times\mathbf E
\right)
-
\omega^2\varepsilon\mathbf E
=
0.
$$

写成相对材料参数：

$$
\nabla\times
\left(
\mu_r^{-1}\nabla\times\mathbf E
\right)
-
k_0^2\varepsilon_r\mathbf E
=
0,
$$

其中：

$$
k_0=\frac{2\pi}{\lambda}.
$$

---

# 2. 横向 Bloch/Floquet 条件

当前结构在 x、y 方向周期，周期为 $L_x,L_y$。对给定横向 Bloch 波矢：

$$
\mathbf k_{\parallel}
=
(k_x,k_y),
$$

横截面模式满足：

$$
\mathbf e(x+L_x,y)
=
e^{ik_xL_x}\mathbf e(x,y),
$$

$$
\mathbf e(x,y+L_y)
=
e^{ik_yL_y}\mathbf e(x,y).
$$

对于相对表面的掠角 $\alpha$ 和方位角 $\phi$：

$$
k_x
=
k_0n_{\mathrm{inc}}
\cos\alpha\cos\phi,
$$

$$
k_y
=
k_0n_{\mathrm{inc}}
\cos\alpha\sin\phi.
$$

相对法向角 $\theta$ 与掠角关系：

$$
\alpha=90^\circ-\theta.
$$

Task032 第一主点：

$$
\alpha=10^\circ,
\qquad
\theta=80^\circ,
\qquad
\phi=0^\circ.
$$

横截面 eigenproblem 的 Bloch 类必须与局部 3D FEM 和外部端口使用的横向 Bloch 波矢一致。

---

# 3. z 不变区域的模态假设

在 $\Omega_m$ 中：

$$
\varepsilon_r=\varepsilon_r(x,y),
\qquad
\mu_r=\mu_r(x,y).
$$

将场分成横向和纵向分量：

$$
\mathbf E
=
\mathbf E_t+\mathbf e_zE_z,
$$

$$
\mathbf H
=
\mathbf H_t+\mathbf e_zH_z.
$$

设单个模式沿 z 传播：

$$
\mathbf E(x,y,z)
=
\mathbf e(x,y)e^{i\beta z},
$$

$$
\mathbf H(x,y,z)
=
\mathbf h(x,y)e^{i\beta z}.
$$

因此：

$$
\partial_z\rightarrow i\beta.
$$

将：

$$
\nabla
=
\nabla_t+\mathbf e_z\partial_z
$$

代入 curl 算子后，Maxwell 算子对 $\beta$ 至多二次，因此离散后得到二次本征问题：

$$
Q(\beta)\mathbf q
=
\left(
\beta^2K_2
+
\beta K_1
+
K_0
\right)\mathbf q
=
0.
$$

其中：

- $K_0$：不含 $\beta$ 的横向 curl、材料和质量项；
- $K_1$：横向/纵向耦合产生的一次项；
- $K_2$：两次 z 导数或纵向消元对应的二次项；
- $\mathbf q$：横向和纵向场自由度组合。

具体 $K_0,K_1,K_2$ 的符号取决于时间谐波和 $e^{i\beta z}$ 约定。实现时必须通过 homogeneous analytic case 验证，而不能只凭公式外观判断。

---

# 4. 为什么截面空间应混合使用 Nédélec 和 Lagrange

三维电场属于：

$$
\mathbf E\in H(\mathrm{curl},\Omega).
$$

在横截面上：

- 横向分量 $\mathbf E_t$ 的自然空间是二维 $H(\mathrm{curl})$；
- 纵向标量 $E_z$ 的自然空间更接近 $H^1$。

因此推荐：

$$
\mathbf E_t\in V_t^{\mathrm{N\acute edelec}},
$$

$$
E_z\in V_z^{\mathrm{Lagrange}}.
$$

组合空间：

$$
V_{\mathrm{mode}}
=
V_t^{\mathrm{N\acute edelec}}
\times
V_z^{\mathrm{Lagrange}}.
$$

这样可以：

- 正确表达横向切向连续性；
- 避免普通 nodal vector element 对 curl 场的伪模态；
- 便于与三维 Nédélec 接口 trace 对接；
- 保留纵向分量的标量连续性。

第一版不应把三个分量都放在 vector Lagrange 空间，也不应只求一个标量 Helmholtz 模式并假装是全矢量 Maxwell 模式。

---

# 5. 二次本征问题和线性化

标准 QEP：

$$
\left(
\beta^2K_2+
\beta K_1+
K_0
\right)\mathbf q=0.
$$

若使用支持 polynomial eigenproblem 的求解器，可直接提交 $K_0,K_1,K_2$。

若必须线性化，可引入：

$$
\mathbf y
=
\begin{bmatrix}
\mathbf q\\
\beta\mathbf q
\end{bmatrix}.
$$

一种 companion linearization 为：

$$
\begin{bmatrix}
0 & I\\
-K_0 & -K_1
\end{bmatrix}
\mathbf y
=
\beta
\begin{bmatrix}
I & 0\\
0 & K_2
\end{bmatrix}
\mathbf y.
$$

线性化会使代数规模约翻倍，并可能改变谱条件。因此：

- 优先使用稀疏分布式 QEP；
- 若线性化，必须记录 companion form；
- 必须检查无限特征值、零空间和伪模态；
- 不允许直接转换为 dense 全矩阵求全部 eigenpairs。

Task032 只需要一段目标谱区间中的模式，而不是所有模式。

---

# 6. 有损材料下的非 Hermitian 模态

当前 Si 折射率为复数，因此 $\varepsilon_r$ 为复数，离散矩阵通常不是 Hermitian。

右模满足：

$$
Q(\beta_m)\mathbf q_m^R=0.
$$

左模满足某种伴随/转置问题：

$$
\left(\mathbf q_m^L\right)^H
Q(\beta_m)=0,
$$

或者依据离散的 reciprocity bilinear form 定义测试模。

一般不能假设：

$$
\left(\mathbf q_m^R\right)^H
\mathbf q_n^R
=
\delta_{mn}.
$$

应建立双正交关系：

$$
\left(\mathbf q_m^L\right)^H
B
\mathbf q_n^R
=
\delta_{mn},
$$

其中 $B$ 由模式问题的物理双线性形式决定。

对于 QEP，常见归一化还会包含：

$$
Q'(\beta_m)
=
2\beta_mK_2+K_1.
$$

例如使用：

$$
\left(\mathbf q_m^L\right)^H
Q'(\beta_m)
\mathbf q_m^R
=
1.
$$

但具体选择必须与接口投影和功率定义一致，不能只为了数值方便任意设定。

工程上应同时保存：

- right mode；
- left/test mode；
- normalization scalar；
- eigen residual；
- biorthogonality matrix；
- condition estimate。

---

# 7. 模式方向和分类

## 7.1 传播模

传播模式的方向优先根据 z 向平均 Poynting flux：

$$
P_z
=
\frac12
\operatorname{Re}
\int_{\Gamma}
\left(
\mathbf E\times\mathbf H^*
\right)
\cdot\mathbf e_z
\,d\Gamma.
$$

分类：

```text
P_z > tolerance  -> forward / +z
P_z < -tolerance -> backward / -z
```

不能只根据 $\operatorname{Re}(\beta)$ 正负分类，因为：

- 有损材料中 phase velocity 和 energy flux 可能不完全同向；
- 某些模式接近 cutoff；
- 复杂各向异性情形下符号可能更微妙。

## 7.2 衰减模

若模式 flux 接近零，主要根据其空间衰减方向分类。

对于：

$$
e^{i\beta z},
\qquad
\beta=\beta'+i\beta'',
$$

有：

$$
e^{i\beta z}
=
e^{i\beta'z}e^{-\beta''z}.
$$

当 $\beta''>0$ 时，该表示沿 $+z$ 衰减。

必须保证：

- forward evanescent mode 沿 $+z$ 衰减；
- backward evanescent mode 沿 $-z$ 衰减；
- 不在传播算子中出现物理上向远离接口方向指数增长的分支。

## 7.3 cutoff 和近简并

当：

$$
|P_z|\approx0
$$

或多个 $\beta$ 很接近时，不应强制逐向量唯一匹配。应使用模式子空间：

$$
\mathcal V
=
\operatorname{span}
\{\mathbf q_1,\ldots,\mathbf q_r\}
$$

并比较子空间投影或 principal angles。

模式追踪可以使用 overlap matrix：

$$
O_{mn}
=
\left|
\left(\mathbf q_m^L(\mu_j)\right)^H
B
\mathbf q_n^R(\mu_{j+1})
\right|.
$$

---

# 8. 中间区域的稳定双向传播

中间长度：

$$
L_m=z_t-z_b.
$$

对第 m 个模式：

$$
p_m=e^{i\beta_mL_m}.
$$

正向振幅：

$$
a_{t,m}^{+}
=
p_m a_{b,m}^{+}.
$$

反向振幅：

$$
a_{b,m}^{-}
=
p_m a_{t,m}^{-},
$$

这里对反向模式的 $\beta_m$ 和 branch 已按物理衰减方向定义。

## 8.1 为什么不使用普通 transfer matrix

若将所有正反向振幅写成：

$$
\begin{bmatrix}
a_t^+\\
a_t^-
\end{bmatrix}
=
T
\begin{bmatrix}
a_b^+\\
a_b^-
\end{bmatrix},
$$

对强衰减模式，$T$ 可能同时包含：

$$
e^{-\gamma L_m}
$$

和：

$$
e^{+\gamma L_m}.
$$

后者会产生溢出和严重病态。

更稳定的是 scattering/two-port unknown：

```text
incoming  = [a_b+, a_t-]
outgoing  = [a_b-, a_t+]
```

中间均匀区域的传播块主要是衰减/相位对角矩阵，不需要指数增长逆传播。

## 8.2 传播组合测试

必须满足：

$$
P(L_1+L_2)
=
P(L_2)P(L_1).
$$

数值测试应比较：

- 一次传播 $L_1+L_2$；
- 两次传播 $L_1$、$L_2$；
- 强衰减模是否下溢但不溢出；
- 传播模相位是否连续。

---

# 9. 3D FEM 与模态的接口条件

Maxwell 材料无表面电流时，切向场连续：

$$
\mathbf n\times
(\mathbf E_1-\mathbf E_2)=0,
$$

$$
\mathbf n\times
(\mathbf H_1-\mathbf H_2)=0.
$$

在内部接口：

$$
\mathbf E_t^{\mathrm{FEM}}
=
\sum_m
(a_m^++a_m^-)
\mathbf e_{t,m},
$$

$$
\mathbf H_t^{\mathrm{FEM}}
=
\sum_m
(a_m^+\mathbf h_{t,m}^+
+a_m^-\mathbf h_{t,m}^-).
$$

第一版使用匹配接口网格，因此 2D mode trace 与 3D Nédélec face trace 可以通过明确的 entity/orientation mapping 对接。

必须特别处理：

- bottom 和 top 接口法向相反；
- Nédélec edge/face orientation sign；
- complex Bloch phase；
- periodic corner/edge ownership；
- MPI ghost 和 constrained DoF。

---

# 10. 接口投影与重构

设离散接口 trace：

$$
\mathbf u_{\Gamma}.
$$

模式 trace 矩阵：

$$
Q_{\Gamma}
=
\begin{bmatrix}
\mathbf q_{\Gamma,1}&
\cdots&
\mathbf q_{\Gamma,M}
\end{bmatrix}.
$$

若左测试模式矩阵为 $W_{\Gamma}$，可定义投影：

$$
\mathbf a
=
W_{\Gamma}^H B_{\Gamma}\mathbf u_{\Gamma}.
$$

重构：

$$
\widehat{\mathbf u}_{\Gamma}
=
Q_{\Gamma}\mathbf a.
$$

投影残差：

$$
\eta_{\mathrm{proj}}
=
\frac{
\|\mathbf u_{\Gamma}-\widehat{\mathbf u}_{\Gamma}\|_{B_{\Gamma}}
}{
\|\mathbf u_{\Gamma}\|_{B_{\Gamma}}
}.
$$

模式数不足时，$\eta_{\mathrm{proj}}$ 不会收敛到目标容差。

## 10.1 存储复杂度

若接口 DoF 数为 $N_{\Gamma}$、模式数为 M，合理存储应接近：

$$
O(N_{\Gamma}M)+O(M^2).
$$

不得显式形成：

$$
O(N_{\Gamma}^2)
$$

的全稠密接口算子。

投影矩阵可以是 distributed dense/sparse hybrid，也可以通过模式逐块 action 实现，但不得把所有大模式向量 allgather 到 rank 0。

---

# 11. Hybrid 增广系统

局部 FEM unknown：

$$
u_b,
\qquad
u_t.
$$

中间 modal unknown：

$$
a.
$$

增广系统：

$$
\begin{bmatrix}
A_b & 0 & C_b\\
0 & A_t & C_t\\
D_b & D_t & H_m
\end{bmatrix}
\begin{bmatrix}
u_b\\
u_t\\
a
\end{bmatrix}
=
\begin{bmatrix}
f_b\\
f_t\\
g
\end{bmatrix}.
$$

解释：

- $A_b,A_t$：上下局部三维 FEM 与外部 DtN；
- $C_b,C_t$：模态幅值对局部 FEM 边界方程的作用；
- $D_b,D_t$：局部 FEM trace 投影到模态方程；
- $H_m$：中间传播和双接口关系；
- $g$：可能的 modal source/incident contribution。

第一版直接求该系统，是最容易审计的 reference。

必须检查：

- block dimensions；
- signs and normals；
- symmetry/non-Hermitian identity；
- row/column ordering；
- full residual；
- interface continuity。

---

# 12. Modal-Schur 消元

局部方程：

$$
A_bu_b+C_ba=f_b,
$$

$$
A_tu_t+C_ta=f_t.
$$

回代：

$$
u_b=A_b^{-1}(f_b-C_ba),
$$

$$
u_t=A_t^{-1}(f_t-C_ta).
$$

代入 modal equation：

$$
D_bu_b+D_tu_t+H_ma=g.
$$

得到：

$$
S_ma=r_m,
$$

其中：

$$
S_m
=
H_m
-
D_bA_b^{-1}C_b
-
D_tA_t^{-1}C_t,
$$

$$
r_m
=
g
-
D_bA_b^{-1}f_b
-
D_tA_t^{-1}f_t.
$$

这与当前 auxiliary DtN condensation 在思想上相似，但被消元的是两个局部三维内部 unknown，对外留下 modal interface system。

## 12.1 多 RHS 构造

若 $C_b$ 有 M 列，构造：

$$
X_b=A_b^{-1}C_b
$$

应使用一次 factorization + block/multiple RHS solves，而不是 M 次重复 factor setup。

同理：

$$
X_t=A_t^{-1}C_t.
$$

然后：

$$
S_m=H_m-D_bX_b-D_tX_t.
$$

## 12.2 内存模式

### fast direct

同时保留：

- $A_b$ factor；
- $A_t$ factor；
- $X_b,X_t$；
- $S_m$。

优点：恢复场快；缺点：峰值较高。

### memory-minimal direct

顺序：

```text
factor A_b -> compute contribution -> release
factor A_t -> compute contribution -> release
solve S_m
refactor only when local field recovery is needed
```

优点：降低同时因子峰值；缺点：可能重复 factorization。

是否使用顺序因子必须由实测峰值和时间决定。

---

# 13. 中间区域场重构

给定 bottom 和 top modal coefficients，中间任意 z：

$$
\mathbf E(x,y,z)
=
\sum_m
\left[
a_{b,m}^+
e^{i\beta_m(z-z_b)}
+
a_{t,m}^-
e^{i\beta_m(z_t-z)}
\right]
\mathbf e_m(x,y).
$$

对应 $\mathbf H$ 同理。

为节省内存，默认只重构：

```text
z = 30 nm
z = 60 nm
z = 90 nm
```

或用户指定平面。

不得默认生成整个中间 100 nm 的 dense 3D volume field。完整 volume reconstruction 仅作为 heavy opt-in 输出。

---

# 14. 模式截断

中间模式必须包含：

- 所有重要传播模；
- 与接口场耦合显著的弱衰减模；
- 足够的局部强衰减模以重构接口近场。

仅保留传播模通常不足以满足接口场连续性。

定义模式数 M 的输出误差：

$$
\Delta R^{(M_1,M_2)}
=
|R^{(M_2)}-R^{(M_1)}|.
$$

逐级混合误差：

$$
\eta_{mn}
=
\frac{
|R_{mn}^{(M_2)}-R_{mn}^{(M_1)}|
}{
\max(R_{mn}^{(M_2)},R_{\mathrm{floor}})
}.
$$

还应检查：

- projection residual；
- interface continuity；
- middle-plane field；
- truncated mode coupling norm；
- propagation factor magnitude。

模式排序不应简单按 $|\beta|$。可以综合：

```text
propagating priority
+ attenuation length
+ interface coupling strength
+ eigen residual
```

---

# 15. 与完整 3D FEM 的验证

Hybrid 方法必须在可计算尺度与完整 3D reference 比较。

## 15.1 物理量

比较：

$$
r_{mn},
\quad
t_{mn},
$$

$$
R_{mn},
\quad
T_{mn},
$$

$$
R_{\mathrm{total}},
\quad
T_{\mathrm{total}},
\quad
A.
$$

## 15.2 场

比较：

- $z=10$ 的 tangential trace；
- $z=110$ 的 tangential trace；
- 中间 $z=60$ 截面；
- 选定中心线；
- near-interface planes。

全局相位可能不同，因此场比较需要：

- 固定同一 incident amplitude/phase convention；
- 或先进行最佳全局 complex scalar alignment；
- 对近简并模式比较重构总场，而不是单个 eigenvector。

## 15.3 代数残差

Hybrid augmented direct：

$$
\eta_{\mathrm{aug}}
=
\frac{
\|b_{\mathrm{aug}}-A_{\mathrm{aug}}x_{\mathrm{aug}}\|
}{
\|b_{\mathrm{aug}}\|
}.
$$

Modal-Schur：

$$
\eta_{\mathrm{Schur}}
=
\frac{
\|r_m-S_ma\|
}{
\|r_m\|
}.
$$

回代后还必须重新计算 full hybrid residual，不能只看 Schur residual。

---

# 16. 外部 Fourier-DtN 与内部 eigenmodes 的区别

外部端口模式通常基于均匀半空间中的 Fourier diffraction orders：

$$
k_{x,m}=k_x+\frac{2\pi m}{L_x},
$$

$$
k_{y,n}=k_y+\frac{2\pi n}{L_y}.
$$

内部中间模式则是包含 Si/空气截面结构的 FEM eigenmodes：

$$
\mathbf e_j(x,y),
\qquad
\beta_j.
$$

两者不同：

```text
external modes = homogeneous port diffraction basis
internal modes = structured cross-section eigenbasis
```

因此：

- 外部 80 个 DtN auxiliary unknowns 不等于内部 M 个模式；
- 两类模式的 normalization 和 admittance 不同；
- 外部 R/T 后处理不能直接用于内部接口系数；
- 内部模式只负责连接两个局部 3D 区域。

---

# 17. 能量、无源性和互易性诊断

对于无源材料，应满足：

$$
R+T+A\approx1.
$$

有损中间模式传播应满足物理衰减，不能产生无源系统中的净增益。

可以检查传播因子：

$$
|p_m|\le1
$$

对沿所选物理方向传播的无源衰减模应成立。传播模可能 $|p_m|$ 接近 1，有损传播模小于 1。

互易性只作为 diagnostic，因为：

- Bloch wavevector 反转；
- interface normal；
- loss；
- mode ordering

都会影响简单矩阵对称外观。不得仅凭 Schur matrix 非对称就判断错误。

---

# 18. 内存复杂度分析

## 18.1 完整 3D FEM

若横截面单元数尺度为 $N_{xy}$，z 向层数为 $N_z$：

$$
N_{\mathrm{3D}}
\sim
O(N_{xy}N_z).
$$

稀疏 direct factor 存储通常超线性增长。

## 18.2 Hybrid

局部 3D 只保留上下端部：

$$
N_{\mathrm{local}}
\sim
O\left[N_{xy}(N_b+N_t)\right].
$$

中间区域存储：

$$
O(N_{xy}M)+O(M^2).
$$

总目标：

$$
N_{\mathrm{hybrid}}
\ll
N_{\mathrm{3D}}.
$$

但如果：

- M 太大；
- 每个 rank 复制所有模式；
- 构造 $N_{\Gamma}^2$ dense operator；
- 同时保留上下 direct factors；
- 保存完整中间体场；

则理论降维收益会被实现抵消。

## 18.3 必须记录的对象

```text
K0/K1/K2
linearized eigen matrices if used
right/left eigenvectors
mode metadata
Q_gamma/W_gamma
bottom/top matrices and factors
X_b/X_t multiple-RHS solutions
H_m/S_m
recovery vectors
selected reconstructed planes
```

每个对象都应有 shape、dtype、distributed ownership 和 estimated bytes。

---

# 19. 常见失败模式

## 19.1 伪模态

原因：

- 不合适的 nodal vector space；
- divergence/gradient nullspace；
- QEP 线性化无限 eigenvalues；
- 不正确 Floquet constraint。

处理：

- analytic homogeneous benchmark；
- eigen residual；
- curl/divergence diagnostic；
- physical flux；
- mesh/order convergence。

## 19.2 模态方向错误

表现：

- 无源传播出现指数增长；
- R+T+A 失衡；
- 接口 reflection 异常；
- 随中间长度增加结果爆炸。

处理：

- flux classification；
- evanescent branch tests；
- propagation composition；
- normal convention tests。

## 19.3 双正交错误

表现：

- coefficient round trip 失败；
- mode count 增加反而恶化；
- near-degenerate modes 突变；
- Schur condition 极差。

处理：

- left/right overlap matrix；
- block normalization；
- subspace tracking；
- projection residual。

## 19.4 接口 orientation 错误

表现：

- top/bottom 一侧符号相反；
- 场值接近但 H 条件失败；
- 反射率不守恒。

处理：

- 单接口 trace round trip；
- edge/face orientation tests；
- 明确法向；
- MPI periodic corner tests。

## 19.5 transfer matrix 病态

表现：

- 强衰减模 overflow；
- condition 随 L 指数增长；
- 少量模式即 NaN。

处理：

- scattering/two-port；
- 不形成增长指数；
- 对数幅值 diagnostic；
- 模式截断。

## 19.6 内存降维未兑现

表现：

- eigenvectors rank0 gather；
- dense interface operator；
- 同时保留 full reference；
- 上下 factor 同时常驻；
- 全 volume reconstruction。

处理：

- distributed storage；
- object ledger；
- sequential factor option；
- selected planes only；
- external simultaneous memory sampler。

---

# 20. 推荐验证阶梯

```text
Step 1  homogeneous air cross-section analytic beta
Step 2  homogeneous lossy cross-section
Step 3  current structured cross-section eigen residual
Step 4  forward/backward/evanescent classification
Step 5  propagation composition and no-growth test
Step 6  mode trace round trip
Step 7  one-interface manufactured coupling
Step 8  full two-interface augmented direct h5
Step 9  augmented vs Schur h5
Step 10 full-3D vs Hybrid h5
Step 11 mode truncation convergence
Step 12 h3 qualification
Step 13 angle/S-P smoke
Step 14 memory prediction
Step 15 conditional h2
```

不得跳过前四层直接运行 h2。

---

# 21. Task032 后与 Task033/Task034 的连接

若 Task032 成功，Task033 应：

- 保持内部接口 trace 网格和模式空间可控；
- 只对上下局部 3D interior 做 h/p 自适应；
- 为多个掠角和 S/P 构造 robust common mesh；
- 检查自适应后接口 projection 是否仍稳定。

Task034 的最终块系统应围绕：

```text
bottom adaptive 3D block
+ top adaptive 3D block
+ modal two-port block
+ interface Schur
```

设计迭代法，而不是继续求解原来的全域 3D 矩阵。

---

# 22. 当前统一结论

```text
Hybrid 方法的核心不是用一个更强的迭代器处理同一个大矩阵，
而是从物理和离散层面消除中间 100 nm 的三维体自由度。

第一步必须建立可信的二维全矢量截面模式；
第二步必须使用稳定双向传播；
第三步必须正确耦合两个局部 3D FEM 接口；
第四步用增广 direct 和 Modal-Schur direct 双重验证；
最后才评价内存收益。

正确性 Gate 高于内存 Gate，
但实现从第一天禁止 rank0 全局聚集、N_interface^2 dense 存储和完整中间 volume 默认重构。
```
