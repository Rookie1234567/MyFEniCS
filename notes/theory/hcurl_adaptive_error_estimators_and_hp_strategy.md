# H(curl) Maxwell 自适应误差估计与 hp 策略

## 1. 文档目的

本文为后续 Task035 提供理论和算法候选清单，针对 MyFEniCS 当前问题：

```text
3D time-harmonic Maxwell
+ complex lossy material
+ high-order Nédélec H(curl)
+ double Floquet periodicity
+ Fourier-DtN external ports
+ Hybrid local-3D / modal-middle coupling
+ hexahedral mainline
+ S-polarization first
```

Task034 已证明：

- p2/p3/p4 均匀网格序列、p3/h3 与 p4/h5 Full3D–Hybrid 同阶闭合可用；
- 提高单元阶次能明显降低达到相近精度所需的均匀网格密度；
- 仅按几何距离构造的三档 conforming graded-h 虽降低 raw DoF，却全部未通过 same-error physical Gate；
- 因而下一步不能继续手工猜网格，必须建立**场驱动、目标量驱动并能分离空间误差与模态截断误差**的自适应流程。

本文不是某一种 estimator 已被证明适用于当前复杂算例的声明。文中方法按：

```text
理论来源
→ 可计算形式
→ 与当前代码的适配风险
→ Task035 中的验证顺序
```

组织。所有方法必须先经过解析/manufactured fixture、均匀加密趋势和真实 observable error 验证，才可用于正式自适应。

---

## 2. 自适应对象与误差来源必须分开

当前 Hybrid 前向模型至少包含五类误差：

$$
 e_{\mathrm{total}}
 =
 e_{\mathrm{FEM,local3D}}
 +e_{\mathrm{FEM,QEP}}
 +e_{\mathrm{mode}}
 +e_{\mathrm{DtN}}
 +e_{\mathrm{algebra}}.
$$

其中：

| 误差 | 含义 | 主要控制量 |
|---|---|---|
| `e_FEM,local3D` | 上下局部三维 H(curl) 离散误差 | 局部 h、p、网格方向性 |
| `e_FEM,QEP` | 二维截面本征问题离散误差 | 截面 h、p、QEP residual |
| `e_mode` | 中部传播/衰减模截断误差 | 每方向模式数 M、分类与 tracking |
| `e_DtN` | 外部 Fourier-DtN 截断误差 | 外部传播/衰减阶数 |
| `e_algebra` | 线性/QEP/Schur 求解误差 | full explicit true residual、eigen residual |

任何“自适应成功”都必须说明到底减少了哪一项误差。特别是：

- 增加 `M` 不能修复局部三维空间离散误差；
- 局部细化不能修复 QEP 截面离散或错误的模态分类；
- `R+T+A=1` 不能证明空间场已收敛；
- algebraic residual 通过不等于 discretization error 足够小。

Task035 应采用分层误差预算，而不是把所有差异混成一个标量。

---

## 3. 连续问题与残差结构

以电场形式写：

$$

abla\times
\left(\mu_r^{-1}\nabla\times \mathbf E\right)
-k_0^2\varepsilon_r\mathbf E
=\mathbf f
\qquad\text{in }\Omega.
$$

对离散解 $\mathbf E_h$，单元体残差可定义为：

$$
\mathbf R_K
=
\mathbf f
+k_0^2\varepsilon_r\mathbf E_h
-
\nabla\times
\left(\mu_r^{-1}\nabla\times\mathbf E_h\right).
$$

公共面 $F$ 上，主要的切向通量跳量为：

$$
\mathbf J_F^{\mathrm{curl}}
=
\left[\!\left[
\mathbf n_F\times
\mu_r^{-1}\nabla\times\mathbf E_h
\right]\!\right].
$$

由于 curl 算子的梯度核，还应检查与 Gauss/charge 约束相关的标量残差，例如：

$$
r_K^{\mathrm{div}}
=
\nabla\cdot
\left(
\mathbf f+k_0^2\varepsilon_r\mathbf E_h
\right),
$$

以及材料界面上的法向通量或构成关系残差。具体形式取决于源项、材料分片正则性和弱式边界处理，不能机械照搬标量 Poisson estimator。

一个实验性 hp-scaled 局部指标可写成：

$$
\eta_K^2
=
\left(\frac{h_K}{p_K}\right)^2
\|\mathbf R_K\|_K^2
+
\left(\frac{h_K}{p_K}\right)^2
\|r_K^{\mathrm{div}}\|_K^2
+
\sum_{F\subset\partial K}
\frac{h_F}{p_F}
\|\mathbf J_F^{\mathrm{curl}}\|_F^2
+
\eta_{K,\mathrm{material}}^2
+
\eta_{K,\mathrm{boundary}}^2.
$$

对复数有损介质，范数使用复模平方，系数权重必须避免把高损耗区域或小系数区域无意义放大。该式只能作为 Task035 的候选骨架；其可靠性、效率和归一化要由 fixture 与 reference error 验证。

---

## 4. 可尝试方法总览

| 编号 | 方法 | 优点 | 主要风险 | Task035 优先级 |
|---|---|---|---|---|
| R1 | 标准 residual + face jump | 最容易实现、单元局部、可解释 | 高频粗网格上 effectivity 可能差 | 第一优先 |
| R2 | frequency-explicit residual scaling | 适合高频 Maxwell，揭示 pre-asymptotic 区 | 理论常数与当前 DtN/复材料需适配 | 第一优先 |
| R3 | recovery-type H(curl) estimator | 对材料跳跃较稳健，可重构磁化场 | 需要辅助 H(curl) 恢复或 patch solve | 第二优先 |
| R4 | equilibrated/Prager–Synge estimator | 可给 guaranteed upper bound，p-robust | 实现 patch constrained minimization 较复杂 | 第二优先 |
| R5 | hierarchical/two-level estimator | 直接利用局部富集空间，适合高阶 | 需要稳定的 bubble/p+1/local solve | 第一优先 |
| G1 | DWR goal-oriented estimator | 直接瞄准 R/T/A、R00、衍射级 | 需要 adjoint，多目标聚合困难 | 第一优先 |
| G2 | multi-goal robust DWR | 一个网格服务多个目标/角度 | 多 adjoint 成本高，权重敏感 | 第二阶段 |
| B1 | DtN truncation + FEM error split | 与当前 Fourier-DtN 最匹配 | 需推导当前辅助 DtN 的截断项 | 第一优先 |
| H1 | isotropic conforming h-refinement | 概念简单 | 三维高频下 DoF 可能增长过快 | 对照组 |
| H2 | anisotropic directional h-refinement | 适合边/角奇异和层状结构 | 六面体 conforming transition 难 | 高优先研究 |
| H3 | mesh regeneration by metric/size field | 不依赖 hanging-node 约束 | 周期 mate、材料面与接口需强制一致 | 高优先研究 |
| P1 | global p reranking on adaptive meshes | 当前 p2/p3/p4 已有基础 | 不是局部 p 自适应 | 低风险主线 |
| P2 | local p/hp candidate competition | 理论上效率最高 | 当前 variable-p H(curl) 未资格化 | 条件研究 |
| C1 | cost-aware marking | 同时优化 error/DoF/memory/time | 成本模型会偏，不能压过物理 Gate | 后期优化 |
| M1 | alternating spatial/M adaptation | 分离 FEM 与模态截断 | 流程更复杂，需要稳定 funnel | Hybrid 必需 |

Task035 不应一开始把所有方法都用于重型 p4/h5。应先在低成本 fixture 和 p2/p3 小点做 estimator bake-off，再把少数优胜方法升级到 p4/h5。

---

## 5. R1：residual-based H(curl) estimator

Beck、Hiptmair、Hoppe 与 Wohlmuth从 defect equation 和 Helmholtz-type decomposition 推导了 Nédélec 元的局部 residual estimator，并给出局部下界和全局上界。这一类方法是当前最直接的起点。

Task035 中应至少实现以下可分项记录：

```text
volume_curl_residual
scalar_divergence_residual
curl_flux_jump
material_interface_term
external_DtN_boundary_term
Floquet_pair_residual
Hybrid_interface_Et_residual
Hybrid_interface_Ht_residual
```

所有分项必须：

- finite、nonnegative；
- MPI reduction 后与 serial 一致；
- 可映射到 canonical global cell identity；
- 在均匀加密下呈合理下降趋势；
- 与真实 reference error 有正相关，而非只在尖角处数值很大。

文献：

- R. Beck, R. Hiptmair, R. H. W. Hoppe, B. Wohlmuth, “Residual based a posteriori error estimators for eddy current computation,” *ESAIM: M2AN* 34 (2000), 159–182, [DOI 10.1051/m2an:2000136](https://doi.org/10.1051/m2an:2000136)。
- Z. Chen, L. Wang, W. Zheng, “An Adaptive Multilevel Method for Time-Harmonic Maxwell Equations with Singularities,” *SIAM J. Sci. Comput.* 29 (2007), 118–138, [DOI 10.1137/050636012](https://doi.org/10.1137/050636012)。
- L. Zhong, L. Chen, S. Shu, G. Wittum, J. Xu, “Convergence and optimality of adaptive edge finite element methods for time-harmonic Maxwell equations,” *Math. Comp.* 81 (2012), 623–642, [DOI 10.1090/S0025-5718-2011-02544-5](https://doi.org/10.1090/S0025-5718-2011-02544-5)。

Zhong 等人的结论还提示：indefinite time-harmonic Maxwell 的自适应理论通常要求初始网格足够细。Task035 不得从极粗、明显未解析波长的网格启动后，因 estimator 给出数值就宣称可靠。

---

## 6. R2：frequency-explicit residual estimator

高频 Maxwell 的 estimator 可能在粗网格上出现随频率恶化的可靠性/效率常数。Chaumont-Frelet 与 Vega 的 frequency-explicit 分析表明：粗网格上的 estimator 常数可能很差，而当网格充分解析波数后，常数才趋于与频率无关。

对本项目的直接含义：

1. estimator fixture 必须包含多个 $k_0h/p$；
2. 需要记录每个单元的局部分辨率：

$$
\chi_K=\frac{k_K h_K}{p_K};
$$

3. 对 $\chi_K$ 过大的单元，indicator 只能标记为 pre-asymptotic diagnostic；
4. 不得用尚未解析波长的 coarse mesh 训练或调参后直接外推 0.7 nm；
5. p4 的优势应通过较小 $kh/p$ 与实际 observable error 共同确认。

文献：

- T. Chaumont-Frelet, P. Vega, “Frequency-Explicit A Posteriori Error Estimates for Finite Element Discretizations of Maxwell’s Equations,” *SIAM J. Numer. Anal.* 60 (2022), 1774–1798, [DOI 10.1137/21M1421805](https://doi.org/10.1137/21M1421805)。
- J. M. Melenk, S. A. Sauter, “Wavenumber-Explicit hp-FEM Analysis for Maxwell’s Equations with Impedance Boundary Conditions,” *Found. Comput. Math.* 24 (2024), 1871–1939, [DOI 10.1007/s10208-023-09626-7](https://doi.org/10.1007/s10208-023-09626-7)。

后者给出的典型高频 hp 分辨思想是 $kh/p$ 足够小，并且高频时 $p$ 不能过低。当前 DtN/Floquet/复材料问题并不完全等同于该论文边界条件，但它适合作为工程分辨率 Gate，而不是照搬为严格定理。

---

## 7. R3：recovery-type estimator

Cai、Cao 与 Falgout提出通过恢复辅助磁化场来构造 H(curl) recovery estimator，并强调对不均匀材料系数的稳健性。其核心思路是同时检查：

- 原方程的修改后单元残差；
- 电场与恢复磁化场之间的构成关系残差。

Task035 可测试两条路线：

### 7.1 global cheap recovery

在较低精度或少量平滑迭代下求一个辅助 H(curl) 恢复问题。优点是实现统一；缺点是又引入一个全局 solve。

### 7.2 local patch recovery

在 vertex/edge/element patch 上恢复磁场或 flux。优点是并行和局部；缺点是 patch 边界、周期配对和高阶 orientation 更复杂。

文献：

- Z. Cai, S. Cao, R. Falgout, “Robust a posteriori error estimation for finite element approximation to H(curl) problem,” *Comput. Methods Appl. Mech. Engrg.* 309 (2016), 182–201, [DOI 10.1016/j.cma.2016.06.007](https://doi.org/10.1016/j.cma.2016.06.007)。

该方法适合作为 residual estimator 的独立对照。如果两者标记区域完全不同，应先定位材料权重、divergence kernel 或界面项，而不是直接任选一个进入重型算例。

---

## 8. R4：equilibrated estimator

Chaumont-Frelet 的 equilibrated curl-curl estimator 基于 Prager–Synge 型关系，给出 constant-free guaranteed upper bound，并具有局部效率和 polynomial-degree robustness。构造需要 patch-wise divergence-constrained minimization，可自然并行。

对本项目的价值：

- 为 p3/p4 高阶空间提供比经验 residual 更可信的 effectivity；
- 可作为 Task035 中“reference estimator”；
- 可用于判断简单 residual 是否系统性漏掉梯度核或材料界面误差。

风险：

- 论文模型是 mixed curl-curl，当前有复系数、indefinite mass、Floquet、DtN 和 Hybrid 接口；
- guaranteed constant-free 结论不能未经重新推导直接移植；
- patch constrained spaces 和 MPI ownership 实现量较大。

因此 Task035 应先在正定/制造解 fixture 上实现最小版本，再判断是否扩展到真实 time-harmonic problem。

文献：

- T. Chaumont-Frelet, “An equilibrated estimator for mixed finite element discretizations of the curl-curl problem,” *IMA J. Numer. Anal.* 45 (2025), 329–353, [DOI 10.1093/imanum/drae007](https://doi.org/10.1093/imanum/drae007)。

---

## 9. R5：hierarchical / two-level estimator

对高阶元，实用方法之一是在每个 cell/patch 构造一个富集空间，例如：

```text
p -> p+1
或
current mesh -> locally refined reference patch
或
增加 bubble / face / edge hierarchical modes
```

然后局部求解 defect：

$$
a_K(\delta\mathbf E_K,\mathbf v)
=R_K(\mathbf v)
\qquad
\forall\mathbf v\in W_K^{\mathrm{enriched}}.
$$

以 $\|\delta\mathbf E_K\|$ 作为 indicator。这种方法的优势是：

- 不必手工平衡多个 residual 分量；
- 对 p3/p4 高阶离散更自然；
- 可直接比较 h-refinement、p-enrichment 和 anisotropic split 的候选收益。

主要风险：

- 当前 DOLFINx/Basix 的 local enriched H(curl) space、bubble、restriction 和 orientation 需要 capability audit；
- 局部问题的边界条件会影响 estimator；
- 不得让 local solve 成本接近一次完整全局 solve。

Task035 中建议把 two-level estimator 作为高阶主候选之一，即使最终不能形成严格上界，也可用于候选排序。

相关背景：

- A. Alonso Rodríguez 等以及 electromagnetic FEM–BEM 文献中的 p-hierarchical estimators；
- L. Demkowicz 的 reference-solution hp 策略，见第 14 节。

---

## 10. G1：DWR 目标量导向自适应

本项目最终关心的不是抽象能量范数，而是：

```text
R_total
T_total
A_volume
R00
significant diffraction-order powers
significant diffraction-order complex amplitudes
selected interface/plane fields
```

对目标泛函 $J(\mathbf E)$，DWR 使用伴随解 $\mathbf z$：

$$
a(\mathbf v,\mathbf z)=J'(\mathbf E_h)(\mathbf v).
$$

目标误差近似为：

$$
J(\mathbf E)-J(\mathbf E_h)
\approx
R(\mathbf E_h)(\mathbf z-\mathbf z_h),
$$

并分解到 cell/face 形成 $\eta_K^J$。

### 10.1 为什么适合本项目

Task034 的手工 graded-h 失败说明：减少局部 FE DoF 并不等于保持 R/T/A 与场。DWR 可以直接问：

> 哪些单元对当前 R00 或某个显著衍射级的误差贡献最大？

这比单纯按场幅值或几何距离细化更符合参数反演需求。

### 10.2 多目标策略

单个目标会产生“只对一个输出好”的网格。建议先为目标向量定义归一化：

$$
\widehat\eta_K^{(j)}
=
\frac{|\eta_K^{(j)}|}{\tau_j+s_j},
$$

再采用：

$$
\eta_K^{\mathrm{robust}}
=
\max_j \widehat\eta_K^{(j)},
$$

或平方和。$\tau_j$ 是物理容差，$s_j$ 防止近零量放大。权重必须预先冻结，不能看完结果后调整制造通过。

### 10.3 目标顺序

建议：

1. `R_total/T_total/A_volume`；
2. `R00_total`；
3. 主要传播级功率；
4. 主要传播级复振幅；
5. selected interface/plane field diagnostics。

文献：

- J. H. Song, M. Maier, M. Luskin, “Adaptive finite element simulations of waveguide configurations involving parallel 2D material sheets,” *Comput. Methods Appl. Mech. Engrg.* 351 (2019), 20–34, [DOI 10.1016/j.cma.2019.03.039](https://doi.org/10.1016/j.cma.2019.03.039)。该工作以 DWR 控制电磁能量传输目标。

DWR 的 adjoint 与当前非 Hermitian、复数、Floquet/DtN 系统必须使用正确的共轭伴随和端口导数；不能用转置或前向解替代。

---

## 11. B1：DtN 与模态截断误差必须单独自适应

Jiang 等针对三维双周期结构提出 adaptive edge FEM–DtN 方法，将误差分为：

$$
\eta^2
=\eta_{\mathrm{FEM}}^2+\eta_{\mathrm{DtN}}^2,
$$

其中 DtN 截断误差随截断参数增长而指数衰减。该问题与本项目的双周期 grating 和 transparent DtN 高度相关。

Task035 应建立类似的三层判定：

```text
spatial mesh error
external DtN truncation error
internal Hybrid mode truncation error
```

建议流程：

1. 固定外部 DtN 与内部 M 足够大，评估空间 estimator；
2. 固定空间，做 external-order funnel；
3. 固定空间，做 M80/M120/M160/条件 M240；
4. 只有三项都低于各自容差，才判断 candidate same-error pass；
5. 计算成本允许时交替更新 mesh 与 M，而不是每轮同时无条件增加。

文献：

- X. Jiang, P. Li, J. Lv, Z. Wang, H. Wu, W. Zheng, “An adaptive edge finite element DtN method for Maxwell’s equations in biperiodic structures,” *IMA J. Numer. Anal.* 42 (2022), 2794–2828, [DOI 10.1093/imanum/drab052](https://doi.org/10.1093/imanum/drab052)。

---

## 12. 标记策略

### 12.1 Dörfler bulk marking

选择尽量小的单元集合 $\mathcal M$，使：

$$
\sum_{K\in\mathcal M}\eta_K^2
\ge
\theta
\sum_K\eta_K^2.
$$

Task035 建议筛选：

```text
theta = 0.3, 0.5, 0.7
```

其中 $0.5$ 为主线，其他用于敏感性分析。

### 12.2 maximum marking

标记：

$$
\eta_K\ge\theta\max_T\eta_T.
$$

实现简单，可作为对照，但对长尾误差分布可能过少或过多细化。

### 12.3 cost-aware marking

对每个候选 refinement $c$ 定义：

$$
q_c
=
\frac{\widehat{\Delta e}_c}
{w_N\Delta N_c+w_M\Delta M_c+w_t\widehat{\Delta t}_c}.
$$

只在 estimator/物理有效性已经证明后，才用 $q_c$ 排序。成本模型只能选择同样物理可信的候选，不能因为便宜而接受更大误差。

---

## 13. h 自适应的网格实现候选

Task034 的 tensor-product graded profiles 本质上会把一个轴上的分割扩展为完整 strip/slab，局部性有限。Task035 应做 mesh-backend bake-off。

### H1：现有 tensor-product strip refinement

作用：负对照和低风险 baseline。

优点：

- 完全 conforming；
- 周期 trace 容易同步；
- Hybrid matching section 容易保持一致。

缺点：一个局部角点标记可能沿整条轴扩展，DoF 节省有限或误差分布失真。

### H2：multi-block conforming hexa regeneration

将单胞划分为若干几何块，在被标记块中沿 x/y/z 选择性加密，并用过渡块保持全六面体 conforming。

关键要求：

- 不产生未经资格化的 hanging-node H(curl) 约束；
- 周期 mate block 同步；
- 双周期角点/边/面拓扑一致；
- 材料界面与 Hybrid matching planes 精确；
- 相邻尺寸比和 Jacobian 有 Gate；
- 每轮由 indicator 生成新 mesh plan，而不是手工 profile。

### H3：各向异性 directional split

根据 estimator 的方向信息选择：

```text
split-x
split-y
split-z
split-xy
split-xz
split-yz
split-xyz
```

对当前 y 不变光栅，常见候选可能是 x/z 方向细、y 方向粗；但不能预先写死，必须由方向性 defect 或候选局部 solve 证实。

Nicaise 的研究说明 edge singularity 问题中 anisotropic edge-element meshes 具有理论和数值价值：

- S. Nicaise, “Edge Elements on Anisotropic Meshes and Approximation of the Maxwell Equations,” *SIAM J. Numer. Anal.* 39 (2001), 784–816, [DOI 10.1137/S003614290036988X](https://doi.org/10.1137/S003614290036988X)。

### H4：mesh-generator metric/size field regeneration

把 $\eta_K$ 投影为 size/metric field，调用 mesh generator 重新生成 conforming mesh。

优点：更容易获得真正局部拓扑；缺点：

- 必须验证周期两侧节点/边/面一一配对；
- hexahedral metric meshing 的可控性弱于 tetrahedral；
- re-meshing 后 field transfer 只能作初值，official 结果仍需新网格独立求解。

### H5：tetrahedral adaptive control lane

DOLFINx 的标记局部 refinement 主要沿 edge-bisection/simplicial 路线成熟；hexahedra 在 0.10 中明确支持 uniform refinement，但不能默认认为任意局部 hexa refinement 和 H(curl) hanging constraints 已经 production-ready。

可建立一个 tetrahedral Nédélec adaptive 对照 lane，目的仅是：

- 验证 estimator 和 marking 是否能产生正确 error reduction；
- 区分“indicator 错”与“hexa mesh backend 太受限”。

该 lane 不自动替代 hexa mainline，也不能直接与 hexa DoF/内存作等价比较。

---

## 14. p 与 hp 自适应

### 14.1 先做 global-p adaptive comparison

当前最稳妥的路线不是立即 cellwise variable-p，而是在同一自适应思想下分别运行：

```text
p2 h-adaptive
p3 h-adaptive
p4 h-adaptive
```

比较同误差下 DoF、rows、NNZ、factor、memory 和 time。这样可利用 Task034 已资格化的统一 p 空间，同时避免 unequal-p trace conformity。

### 14.2 smoothness sensor

对单元解的最高阶部分定义 projection defect：

$$
s_K
=
\frac{
\|\mathbf E_h^{(p)}-\Pi_{p-1}\mathbf E_h^{(p)}\|_K
}{
\|\mathbf E_h^{(p)}\|_K+\epsilon
}.
$$

或分析 hierarchical coefficient decay：

- 高频系数快速衰减：解较光滑，倾向 p-enrichment；
- 高频系数衰减慢：存在奇异/界面/未解析波，倾向 h-refinement。

传感器必须在解析平滑解、材料界面解和角点奇异解上验证，不能只凭阈值经验。

### 14.3 reference-solution candidate competition

Demkowicz 系列自动 hp 策略常以细 reference mesh / enriched space 为参考，对多个候选 refinement 计算投影误差下降与新增 DoF，选择最高收益候选。

Task035 可对每个被标记 block 试：

```text
h-isotropic
h-directional
p+1
hp mixed
```

并比较：

$$
\frac{
\|\mathbf E_{\mathrm{ref}}-\Pi_c\mathbf E_{\mathrm{ref}}\|^2_{\mathrm{before}}
-
\|\mathbf E_{\mathrm{ref}}-\Pi_c\mathbf E_{\mathrm{ref}}\|^2_{\mathrm{after}}
}{\Delta N_c}.
$$

文献：

- L. Demkowicz 等，“An hp-adaptive finite element method for electromagnetics: Part 1: Data structure and constrained approximation,” *Comput. Methods Appl. Mech. Engrg.* 187 (2000), 307–335, [DOI 10.1016/S0045-7825(99)00137-1](https://doi.org/10.1016/S0045-7825(99)00137-1)。
- “Fully automatic hp-adaptivity for Maxwell’s equations,” *Comput. Methods Appl. Mech. Engrg.* 194 (2005), 605–624, [DOI 10.1016/j.cma.2004.05.023](https://doi.org/10.1016/j.cma.2004.05.023)。
- “Convergence of an automatic hp-adaptive finite element strategy for Maxwell’s equations,” *Appl. Numer. Math.* 72 (2013), 188–204, [DOI 10.1016/j.apnum.2013.04.008](https://doi.org/10.1016/j.apnum.2013.04.008)。
- P. D. Ledger 等，“The development of an hp-adaptive finite element procedure for electromagnetic scattering problems,” *Finite Elem. Anal. Des.* 39 (2003), 751–764, [DOI 10.1016/S0168-874X(03)00057-X](https://doi.org/10.1016/S0168-874X(03)00057-X)。

### 14.4 当前 DOLFINx 边界

Basix 能定义高阶 Nédélec 元并处理 orientation，但“每个相邻 cell 使用不同 p 后仍自动满足 edge/face trace conformity、Floquet 周期约束和 MPI ownership”不是当前项目已资格化能力。

因此 local variable-p 必须分阶段：

1. API/capability audit；
2. 两单元 unequal-p analytic trace fixture；
3. 周期 mate unequal-p fixture；
4. MPI fixture；
5. 只有全部通过后才允许真实 PDE。

任何一步失败都保留为 `variable_p_not_qualified`，不阻塞 fixed-p h-adaptive 主线。

---

## 15. Hybrid 专用自适应

Hybrid 的上下局部 3D 网格、二维截面网格和模式数 M 彼此耦合。

### 15.1 接口必须保持匹配

- bottom/top local 3D interface trace topology 与 2D matching cross-section 必须一致；
- 若只在远离接口的局部区域细化，可保持 interface trace 冻结；
- 若 indicator 要求细化接口，必须同步重建 2D QEP mesh、bottom/top interface 和 mode projection；
- 每个新的 interface topology 都重新做 M funnel。

### 15.2 交替自适应策略

建议：

```text
固定 M 足够大
→ 适应 local 3D mesh
→ 固定 mesh
→ 适应 M / QEP cross-section
→ 检查 interface residual
→ 必要时再循环
```

而不是每轮同时增加 M 和细化 mesh，导致无法定位误差来源。

### 15.3 Hybrid interface indicators

至少记录：

$$
\eta_{\Gamma,E}
=\|\mathbf n\times(\mathbf E_{3D}-\mathbf E_{modal})\|_{\Gamma},
$$

$$
\eta_{\Gamma,H}
=\|\mathbf n\times(\mathbf H_{3D}-\mathbf H_{modal})\|_{\Gamma}.
$$

它们是接口一致性诊断，不自动等价于全局 a posteriori upper bound，但可用于判断：

- M 是否不足；
- interface trace mesh 是否不足；
- local 3D 网格是否在接口附近过粗；
- mode classification/tracking 是否异常。

---

## 16. 单参数到 robust common mesh

Task035 首先只对：

```text
13.5 nm
10° grazing
S incidence
fixed geometry
```

建立可信 adaptive loop。成功后再扩展：

```text
1° / 5° / 10° grazing
S incidence
```

对参数点 $\mu_j$ 的 cell indicator，采用：

$$
\eta_K^{\mathrm{robust}}
=
\max_j
\frac{\eta_K(\mu_j)}{\tau_j+s_j}.
$$

P 入射不作为 Task035 第一阶段重型矩阵；只有 S common mesh 通过后，才做一个低成本 P capability 检查或移交后续任务。

---

## 17. 验证指标

### 17.1 estimator quality

| 指标 | 含义 |
|---|---|
| reliability trend | estimator 不应随真实误差增大而系统减小 |
| efficiency trend | 不应比真实误差大几个不可控数量级 |
| effectivity index | $\eta/\|e\|$ 或 goal error ratio |
| rank correlation | cell indicator 与 reference cell-error proxy 的相关性 |
| marking stability | MPI/partition 改变不应改变 global marked set identity |
| refinement response | 标记后对应 error 应下降 |

### 17.2 physical same-error Gate

候选必须同时比较：

```text
R/T/A_balance/A_volume
R00_s/R00_p/R00_total
all significant propagating order powers
complex amplitudes
selected-plane E/H
bottom/top interface Et/Ht
full true residual
M funnel
```

### 17.3 资源与压缩

只在全部物理 Gate 通过后报告：

```text
DoF compression
rows compression
assembled NNZ compression
factor NNZ compression
peak-memory reduction
wall-time change
```

Task034 p4/h5 Full3D 约 340k rows。Task035 可把下列范围作为工程分类，而非预先保证：

| same-error p4 adaptive rows | 分类 |
|---:|---|
| 240k–300k | weak/mechanism positive |
| 150k–220k | useful/clear engineering positive |
| 100k–150k | strong result |
| <100k | exceptional，必须重点排查漏误差 |

不能为了达到某个压缩倍数而调宽物理容差。

---

## 18. 推荐的 Task035 方法筛选顺序

```text
A. clean fixtures and reference data
→ B. residual/frequency-scaled/two-level estimator bake-off
→ C. DWR R/T/A/R00 prototype
→ D. mesh-backend bake-off
→ E. p2/p3 low-cost adaptive cycles
→ F. p4/h5 S Full3D adaptive mainline
→ G. selected p4 Hybrid M funnel and closure
→ H. recovery/equilibrated estimator as independent check
→ I. anisotropic and global-p comparison
→ J. local variable-p capability audit only if unlocked
→ K. 1°/5°/10° S robust common mesh
```

每个箭头都有 stop Gate。不要在 estimator 尚未通过 fixture 时运行重型 p4；不要在 h-adaptive 尚未成功时启动 local hp；不要在单点 S 尚未成功时运行多角度 common mesh。

---

## 19. 主要参考文献

| 编号 | 文献 | Task035 用途 |
|---|---|---|
| A1 | Beck et al. 2000, [10.1051/m2an:2000136](https://doi.org/10.1051/m2an:2000136) | H(curl) residual estimator 基础 |
| A2 | Chen, Wang, Zheng 2007, [10.1137/050636012](https://doi.org/10.1137/050636012) | singular Maxwell adaptive + multilevel |
| A3 | Zhong et al. 2012, [10.1090/S0025-5718-2011-02544-5](https://doi.org/10.1090/S0025-5718-2011-02544-5) | arbitrary-order AEFEM convergence/optimality |
| A4 | M. Bürg 2012, [10.1016/j.apnum.2012.02.007](https://doi.org/10.1016/j.apnum.2012.02.007) | hp-explicit residual bounds |
| A5 | Chaumont-Frelet, Vega 2022, [10.1137/21M1421805](https://doi.org/10.1137/21M1421805) | frequency-explicit effectivity |
| A6 | Cai, Cao, Falgout 2016, [10.1016/j.cma.2016.06.007](https://doi.org/10.1016/j.cma.2016.06.007) | recovery estimator、材料稳健性 |
| A7 | Chaumont-Frelet 2025, [10.1093/imanum/drae007](https://doi.org/10.1093/imanum/drae007) | equilibrated p-robust estimator |
| A8 | Jiang et al. 2022, [10.1093/imanum/drab052](https://doi.org/10.1093/imanum/drab052) | 双周期 grating FEM/DtN 误差分离 |
| A9 | Song, Maier, Luskin 2019, [10.1016/j.cma.2019.03.039](https://doi.org/10.1016/j.cma.2019.03.039) | Maxwell DWR goal-oriented adaptivity |
| A10 | Nicaise 2001, [10.1137/S003614290036988X](https://doi.org/10.1137/S003614290036988X) | edge singularity anisotropic meshes |
| A11 | Demkowicz et al. 2000, [10.1016/S0045-7825(99)00137-1](https://doi.org/10.1016/S0045-7825(99)00137-1) | variable-order hp data/constrained approximation |
| A12 | Demkowicz 2005, [10.1016/j.cma.2004.05.023](https://doi.org/10.1016/j.cma.2004.05.023) | automatic hp candidate selection |
| A13 | Automatic hp convergence 2013, [10.1016/j.apnum.2013.04.008](https://doi.org/10.1016/j.apnum.2013.04.008) | automatic hp convergence |
| A14 | Ledger et al. 2003, [10.1016/S0168-874X(03)00057-X](https://doi.org/10.1016/S0168-874X(03)00057-X) | scattering-output hp procedure |
| A15 | Melenk, Sauter 2024, [10.1007/s10208-023-09626-7](https://doi.org/10.1007/s10208-023-09626-7) | high-frequency hp resolution conditions |

---

## 20. 当前结论

Task035 最有希望的主线不是单一 estimator，而是：

```text
frequency-aware residual / two-level estimator
+ DWR multi-goal correction
+ conforming anisotropic hexa regeneration
+ separate DtN and M truncation budgets
+ fixed-p p2/p3/p4 comparison
+ conditional hp candidate competition
```

第一目标是证明至少一种 field-driven adaptive sequence 在 13.5 nm、10°、S 入射下：

1. estimator 与真实 observable error 同向；
2. 每轮 refinement 后关键误差下降；
3. p4/h5 同误差下 DoF/rows/内存出现可复现减少；
4. selected Hybrid M funnel 与 Full3D reference 保持闭合；
5. 不依赖手工几何 profile 或放宽物理阈值。

只有这条主线成立后，才值得把自适应收益带入 0.7 nm 资源评估和后续低存储迭代求解器设计。
