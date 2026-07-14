# 光栅参数反演服务需求与前向模型技术路线

## 0. 文档身份

```text
status = project-level planning baseline
scope = measurement observables + inversion requirements + forward-model roadmap
current_reference_wavelength = 13.5 nm
target_service_wavelength = 0.7 nm
target_compute_memory = 1–2 TB
```

本文档用于统一项目最终服务需求、参数反演所需观测量、当前 FEniCS 前向模型能力、0.7 nm 波长下的资源瓶颈，以及后续 Task031–Task035 的技术路线。

本文档不是某一个 Task 的任务书。后续任务书必须与本文档保持一致；若实验测量能力或最终服务接口发生变化，应先更新本文档，再修改算法路线。

---

# 1. 项目最终目标

项目最终目标不是单次求解一个电磁场，而是建立一套可服务于光栅和周期纳米结构参数反演的计算系统：

```text
实验散射数据
→ 参数化结构模型
→ 高可信前向 Maxwell 求解
→ 结构参数优化或概率反演
→ 参数估计、置信区间和可辨识性报告
```

目标服务需要支持：

- 掠入射 X 射线；
- 目标波长约 `0.7 nm`；
- 多个入射角度；
- 波长变化导致的复折射率/介电常数色散；
- 周期光栅及其平均单胞；
- 后续可能出现的局部三维曲面、圆角、非均匀端部和材料三维变化；
- 1–2 TB 内存服务器；
- 大量重复前向计算，而不是只完成一个 benchmark；
- 最终与优化、MCMC、代理模型或其他反演框架连接。

因此，前向模型必须同时满足：

```text
正确性
+ 输出量完整
+ 参数化
+ 可重复批量运行
+ 资源可扩展
+ 数值误差可审计
```

---

# 2. 反演对象：需要重构哪些参数

最终反演参数向量可写为：

\[
\mathbf p =
(\mathbf p_{\mathrm{geometry}},
 \mathbf p_{\mathrm{material}},
 \mathbf p_{\mathrm{roughness}},
 \mathbf p_{\mathrm{calibration}}).
\]

## 2.1 平均周期单胞几何参数

第一阶段优先支持：

- 周期/pitch；
- 线宽或 critical dimension；
- 顶部宽度和底部宽度；
- 光栅高度；
- 沟槽深度；
- 占空比；
- 侧壁角；
- 顶部和底部圆角半径；
- 顶部残留层、底部残留层或覆盖层厚度；
- 多层结构中各层厚度；
- 结构在单胞中的横向偏移。

第二阶段可扩展：

- 非对称左右侧壁；
- 多段折线或 spline 轮廓；
- 多重图形单元；
- overlay；
- pitchwalk；
- 局部三维端部和曲面参数。

GISAXS 与严格 Maxwell 求解结合，已经被用于重构平均光栅线形、线宽和复杂 profile；相关工作也展示了 pitchwalk 等缺陷参数的反演。因此前向模型不能只输出总反射率，必须输出保留衍射级身份的散射数据。[R1, R2]

## 2.2 材料参数

材料通常写为：

\[
n(\lambda)=1-\delta(\lambda)+i\beta(\lambda),
\qquad
\varepsilon_r(\lambda)=n^2(\lambda).
\]

反演或不确定性分析可能涉及：

- 材料复折射率修正；
- 密度相对数据库值的缩放；
- 氧化层、污染层或混合层的有效材料参数；
- 材料界面渐变宽度；
- 波长相关色散数据的插值误差。

材料属性应优先作为波长的确定函数输入；只有实验和数据库不确定性不可忽略时，才将材料修正系数作为反演参数。

## 2.3 粗糙度和统计缺陷参数

严格周期单胞模型首先描述平均结构。若服务需要重构制造缺陷，还应考虑：

- line-edge roughness，LER；
- line-width roughness，LWR；
- RMS 粗糙度；
- 相关长度；
- 粗糙度分布模型；
- 线高变化；
- pitchwalk；
- 周期抖动；
- 单胞间随机差异。

这些参数通常不能只由理想周期结构的离散衍射峰强度完全确定。漫散射、峰宽、峰形和高阶衍射强度衰减对粗糙度更敏感。GISAXS 研究表明，粗糙度会系统改变衍射强度；简单 Debye–Waller 修正具有适用范围，复杂情况仍需更完整模型。[R3, R4]

## 2.4 实验校准和 nuisance 参数

实际反演必须允许同时处理：

- 入射掠角零点偏差；
- 方位角偏差；
- 样品倾斜；
- 波长/能量标定误差；
- 入射强度尺度；
- 探测器增益和几何标定；
- 背景和暗电流；
- beam divergence；
- 有限光斑和 footprint；
- 偏振纯度；
- 数据归一化尺度。

这些参数若被错误固定，几何参数可能吸收实验系统误差，产生看似收敛但物理错误的反演结果。

---

# 3. 反演需要哪些观测量

## 3.1 核心观测量：逐衍射级反射效率

最核心的前向输出应为：

\[
R_{mn}(\alpha,\phi,\lambda,s/p),
\]

其中：

- \((m,n)\) 是二维周期结构的衍射级；
- \(\alpha\) 是相对表面的掠入射角；
- \(\phi\) 是方位角；
- \(\lambda\) 是波长；
- `s/p` 是入射偏振。

若实验给出二维探测器图像，建议保留：

- 每个离散衍射峰的积分强度；
- 峰位置；
- 峰宽和峰形；
- 峰周围的漫散射；
- detector pixel 到 \((q_x,q_y,q_z)\) 的映射。

逐级强度包含不同空间频率下的结构信息，是重构线宽、高度、侧壁角、圆角和复杂轮廓的主要数据。已有 GISAXS 参数重构使用完整衍射图样、Maxwell 求解和概率采样获得亚纳米级参数不确定度。[R1]

## 3.2 镜面反射率或零级反射率

镜面/零级反射率：

\[
R_{00}(\alpha,\lambda,s/p)
\]

非常重要，但不能作为唯一反演数据。

它主要对以下量敏感：

- 平均电子密度；
- 表面和覆盖层厚度；
- 材料临界角；
- 层间粗糙度；
- 平均纵向密度分布。

单独的 `R00` 或总反射率通常缺乏足够的横向空间信息，难以唯一确定线宽、侧壁角和非矩形轮廓。因此服务需求中应将其定位为：

```text
重要观测量
+ 材料/层结构约束
+ 强度标定和一致性检查
≠ 完整光栅轮廓的唯一数据
```

## 3.3 多掠入射角扫描

推荐观测数据形式：

\[
\mathcal Y_{\mathrm{angle}}
=
\{R_{mn}(\alpha_j)\}_{j=1}^{N_\alpha}.
\]

多角度的作用是：

- 改变表面驻波和穿透深度；
- 改变不同高度区域的敏感性；
- 改变传播/衰减衍射级集合；
- 降低线宽、高度、侧壁角和材料参数之间的相关性；
- 在临界角和衍射截止附近提供额外信息。

初始工程验证可以使用稀疏代表角度，例如相对表面：

```text
1°, 2°, 3°, 5°, 7.5°, 10°
```

实际服务的角度范围和采样间隔必须根据实验设备确定。最终不应机械采用均匀角度步长，而应在以下区域自动加密：

- 材料临界角附近；
- 新衍射级出现/消失的 cutoff 附近；
- 强度对角度变化剧烈的区间；
- 反演灵敏度或 Fisher 信息较高的区间。

## 3.4 偏振信息

若实验允许，建议至少支持：

```text
s incident → s reflected
p incident → p reflected
```

并保留可选的交叉偏振：

```text
s → p
p → s
```

偏振信息有助于区分：

- 侧壁和高度效应；
- 材料复介电常数；
- 非对称或真正三维结构；
- 不同电场方向对几何特征的敏感性。

若仪器只能提供一种偏振，应将其作为明确服务约束，而不是在算法中默认两种偏振均可测。

## 3.5 波长或能量扫描

多波长数据：

\[
\mathcal Y_{\lambda}
=
\{R_{mn}(\lambda_k)\}_{k=1}^{N_\lambda}
\]

可以增强材料与几何参数的可辨识性，但代价是：

- 材料复折射率随波长变化；
- 传播衍射级数量变化；
- 中间截面本征模变化；
- 网格和求解难度变化。

第一版服务不必进行密集能量扫描，但前向接口必须从一开始将 `lambda` 和材料色散设为参数。

## 3.6 漫散射和峰宽

若需要反演粗糙度、随机缺陷和单胞间变化，应加入：

- off-specular intensity；
- diffuse scattering；
- diffraction peak width；
- peak asymmetry；
- 高阶峰的系统衰减。

理想周期单胞 FEM 给出离散 coherent diffraction orders。粗糙度模型可先采用：

```text
理想周期 Maxwell 结果
+ 统计 roughness correction
```

只有当该近似不能满足误差需求时，再升级为 supercell 或随机三维计算。[R3, R4]

## 3.7 透射率和吸收率

若实验几何允许测量透射，应保留：

\[
T_{mn}(\alpha,\lambda,p).
\]

对于厚基底反射式测量，透射可能不可获取。此时前向模型仍应计算：

- 总反射率；
- 体吸收率；
- 能量闭合；

但吸收率首先作为物理一致性和材料诊断量，不应自动假设实验可直接测量。

## 3.8 复振幅和相位

当前常规散射测量通常直接得到强度，而不是复相位。若后续实验采用 coherent diffraction imaging、ptychography 或干涉测量，复振幅/相位可以显著增强反演信息，并减少强度反演的非唯一性。

第一版服务应：

```text
内部始终计算 complex diffraction amplitudes
外部最低要求输出 intensities/efficiencies
预留 phase-aware measurement interface
```

相位信息属于增强能力，不作为当前最小可行服务的前置条件。掠入射 coherent reconstruction 需要正确考虑基底反射和多重散射，简单自由空间 Fourier phase retrieval 并不充分。[R5]

---

# 4. 最小可行反演数据集

在实验接口尚未最终确定前，项目采用以下最低假设：

## 4.1 必需数据

```text
- 已知或可校准的 wavelength；
- 已知 nominal material optical constants；
- 多个 grazing-incidence angles；
- 每个角度下所有可靠可测 reflected diffraction orders；
- 0th/specular order；
- detector background/noise estimate；
- 入射强度或可拟合的全局强度尺度；
- 测量不确定度或重复测量方差。
```

## 4.2 强烈推荐

```text
- s 和 p 两种偏振；
- 完整二维 detector pattern；
- diffraction peak width/shape；
- critical-angle 附近加密角度；
- 至少一个额外 wavelength/energy point；
- 样品方位角和角度零点校准数据。
```

## 4.3 可选增强

```text
- transmission orders；
- fluorescence / absorption-sensitive measurement；
- coherent phase retrieval；
- 多方位角或样品旋转；
- 局部照明或 ptychographic data。
```

---

# 5. 前向模型必须输出的标准数据合同

每个参数点 \(\boldsymbol\mu=(\lambda,\alpha,\phi,p,\varepsilon)\) 和结构参数 \(\mathbf p\) 应输出：

## 5.1 反演核心输出

- 每个传播反射级的复振幅 `r_mn`；
- 每个传播反射级的效率 `R_mn`；
- 若适用，每个透射级的 `t_mn/T_mn`；
- `R_total/T_total/A_volume`；
- detector/q-space 坐标；
- 模态 identity 和传播/衰减分类；
- 入射功率归一化方式。

## 5.2 数值可信度输出

- reported residual；
- explicit condensed true residual；
- explicit full augmented residual；
- 能量闭合误差；
- 模态截断误差估计；
- FEM 离散误差估计；
- 网格、阶次、DoF 和模式数；
- 内存、迭代次数和时间；
- commit、command、image digest 和材料数据版本。

## 5.3 反演增强输出

后续应支持：

- 对结构参数的 Jacobian/sensitivity；
- adjoint gradient；
- 参数点之间的 mode tracking；
- surrogate/reduced-order feature vector；
- 误差协方差和模型误差标签。

近场 `E/H` 是开发、验证和诊断的重要输出，但通常不是常规实验可直接测量的反演观测量。

---

# 6. 当前 FEniCS 前向模型能力

截至 Task030 合并，项目已经建立：

```text
- 2D/3D frequency-domain Maxwell framework；
- complex-valued Nedelec H(curl) discretization；
- matched hexahedral target mesh；
- double Floquet periodic boundary conditions；
- auxiliary Fourier-DtN modal ports；
- auto-propagating diffraction-order policy；
- per-order and total R/T；
- volume absorption A；
- exact auxiliary condensation A = F - C H^-1 D；
- direct reference solves；
- MPI4 physical-slab + 75D wave-coarse iterative solver；
- explicit condensed/full residual validation；
- benchmark, provenance and memory telemetry framework。
```

当前冻结 13.5 nm、p2、h=2 nm benchmark：

```text
FE DoF ≈ 615,108
direct reference peak ≈ 20.53 GB
Task030 compact iterative peak ≈ 9.37 GB
Task030 h2 iterations = 1,873
```

Task030 将内存降低约 54% 相对直接法、约 28% 相对 Task027 迭代基线，但最终成功机制仍是 Task27-derived physical-slab + 75D Floquet wave coarse，而不是真正 p/h multigrid。

Task031 将继续以内存为第一优先级，研究低存储 Krylov、真正 matrix-free `F`、对象提前释放、slab factor 精确去重和 overlap/slab 重构。

---

# 7. 0.7 nm 下的根本资源问题

若保持当前约 `50 × 25 × 140 nm` 计算域，并使用约 `0.1 nm` 的均匀三维网格：

```text
hexahedral cells ≈ 500 × 250 × 1400 = 1.75e8
p2 H(curl) DoF order ≈ several 1e9
one complex128 vector ≈ tens of GiB
Krylov basis alone can exceed multiple TiB
```

按当前每自由度内存直接外推，全域均匀 3D FEM 可能需要数十 TB，而目标服务器只有 1–2 TB。

因此，后续路线不能依赖：

```text
继续将同一个全域 3D FEM PC 再优化 20%–50%
```

必须至少同时实现：

```text
物理/维度降维
+ 局部 h/p 自适应
+ matrix-free/低存储迭代
```

---

# 8. 后续前向模型总体架构

真实服务结构预期可能包含：

```text
bottom 3D complex region
+ middle z-invariant region
+ top 3D complex region
```

其中中间大段满足：

\[
\varepsilon(x,y,z)=\varepsilon(x,y).
\]

推荐最终架构：

```text
local bottom 3D FEM
+ middle 2D eigenmode / modal propagation
+ local top 3D FEM
+ internal two-sided Modal-DtN / Schur coupling
```

中间规则区域不再沿 z 使用密集体网格，而由截面本征模沿 z 解析传播。上下局部复杂区保留完整三维 FEM，以支持后续曲面、圆角和三维材料变化。

---

# 9. 开发路线

## Task031：当前 full-3D PC 内存收口

目的：

- 将当前 compact physical-slab profile 的存储进一步压低；
- 验证低存储 Krylov；
- 尝试释放 assembled `F`；
- 为未来局部 3D block 提供可复用的低内存组件。

Task031 仍是现有 full-3D benchmark 的工程收口，不解决 0.7 nm 的根本维度问题。

## Task032：Hybrid FEM–Modal 直接法基线

仍使用当前规则物理模型和 13.5 nm 波长：

```text
bottom local 3D FEM
+ middle z-invariant modal region
+ top local 3D FEM
```

第一阶段使用直接法，验证：

- 截面本征模；
- 正向、反向和衰减模；
- 内部双面 Modal-DtN；
- 模态凝聚；
- hybrid 与完整 3D 的场和 R/T/A 一致性；
- 模态截断收敛；
- 多掠角和材料小扰动参数化。

当前 benchmark 的初步内存目标：

```text
acceptable <= 5 GB
target <= 3 GB
preferred <= 2 GB
```

这些是工程估算，不是预先保证。

## Task033：多参数 robust h/p 自适应直接法

只在上下局部 3D 区域进行 h/p 自适应，中间模态区保持解析传播。

自适应不能只针对单一 `80° from normal` 参数点，而应针对代表参数集合：

```text
multiple grazing angles
+ s/p representative polarization
+ nominal/material uncertainty points
```

采用 robust 指标，例如：

\[
\eta_K^{\mathrm{robust}}
=
\max_j \eta_K(\boldsymbol\mu_j).
\]

目标是形成可覆盖目标角度范围的公共网格，避免每个角度重新划分网格。

当前 benchmark 目标：

```text
same observable accuracy
DoF reduction >= 2x minimum
>= 3x preferred
>= 5x strong
```

## Task034：针对最终 hybrid-adaptive 系统的迭代法

在 Task033 已确定的最终离散系统上构造：

```text
bottom adaptive 3D block PC
+ top adaptive 3D block PC
+ exact/near-exact modal block
+ interface Schur correction
+ outer Krylov
```

必须支持：

- 参数点之间 continuation；
- 上一个角度解作为初值；
- PC 复用和自动重建；
- Krylov recycling；
- 内存、迭代数和时间统计；
- 失效检测和 fallback。

先自适应、后构造最终迭代法，避免在均匀网格上开发一次 PC，加入 h/p 自适应后再次重构。

## Task035：逐波长缩短至 0.7 nm

建议顺序：

```text
13.5 nm
→ 5 nm
→ 2 nm
→ 1 nm
→ 0.7 nm
```

每个波长：

- 更新材料色散；
- 更新传播衍射级；
- 更新截面本征模；
- 运行精简掠角集合；
- 记录局部 3D DoF、模式数、内存和时间；
- 建立 1–2 TB 资源预测；
- 验证参数变化下的数值鲁棒性。

## 后续反演任务

前向模型稳定后，再建立：

```text
measurement-data schema
+ geometry parameterization
+ objective / likelihood
+ deterministic optimizer
+ adjoint or Jacobian
+ Bayesian/MCMC uncertainty
+ surrogate or multi-fidelity acceleration
```

应先用 synthetic truth 验证：

- 参数是否可辨识；
- 哪些角度/衍射级最有信息；
- 噪声和材料误差对结果的影响；
- 是否存在多个等价解；
- 需要多少次前向计算。

---

# 10. 建议的反演数学接口

观测向量：

\[
\mathbf y_{\mathrm{obs}}
=
\left\{
I_{mn}^{\mathrm{obs}}(\alpha_j,\phi_j,\lambda_j,p_j)
\right\}.
\]

前向映射：

\[
\mathbf y_{\mathrm{sim}}
=
\mathcal F(\mathbf p,\boldsymbol\mu).
\]

初始确定性目标函数建议使用带不确定度和动态范围处理的形式：

\[
J(\mathbf p)
=
\sum_i
\frac{
\left[
\log(I_i^{\mathrm{sim}}+I_0)
-
\log(I_i^{\mathrm{obs}}+I_0)
\right]^2
}{\sigma_i^2}
+
\mathcal R(\mathbf p).
\]

原因：不同衍射级强度可能跨越多个数量级，直接使用未缩放的绝对平方误差会被最强峰支配。

后续 Bayesian 形式：

\[
p(\mathbf p\mid\mathbf y)
\propto
p(\mathbf y\mid\mathbf p)
p(\mathbf p).
\]

反演服务必须同时报告：

- 最优参数；
- 参数协方差或可信区间；
- 参数相关性；
- posterior predictive check；
- 数据残差按角度和衍射级的分布；
- 模型误差和数值误差。

---

# 11. 当前尚需与实验团队确认的需求

以下问题决定最终观测接口和算法优先级，必须尽早确认：

1. 实验实际输出是完整二维 detector image，还是已经积分后的 diffraction-order intensities？
2. 测量的是绝对强度，还是只能得到相对归一化强度？
3. 可用掠角范围、角度分辨率和角度零点精度是多少？
4. 是否可以测量 s/p 两种偏振？偏振纯度是多少？
5. 是否可以改变方位角或旋转样品？
6. 是否存在多波长/多能量数据？
7. 是否能测量透射、荧光或其他吸收相关信号？
8. detector 的动态范围、beam stop、饱和和背景水平如何？
9. 材料光学常数由哪一数据库或实验标定提供？不确定度是多少？
10. 最终优先反演哪些参数：线宽、高度、侧壁角、圆角、粗糙度、pitchwalk 还是材料？
11. 单次反演允许的总时间是多少？需要在线、小时级还是离线批处理？
12. 结构参数的合理先验范围和制造约束是什么？

在这些需求未确定前，项目先以“多掠角、逐反射衍射级强度、可选偏振、名义材料色散”为最小服务合同。

---

# 12. 项目级成功标准

最终项目不以“某个 benchmark 可以运行”为唯一成功标准，而应满足：

## 前向正确性

- 与完整 3D reference 在可计算尺度下一致；
- R/T/A、模式身份和能量闭合通过；
- 多角度、多材料点和多波长下稳定；
- 离散误差和模式截断误差可审计。

## 资源可行性

- 0.7 nm 目标问题在 1–2 TB 内存内可完成；
- 无不可控 swap；
- 前向计算时间可满足反演所需重复调用；
- 允许 continuation、缓存和多参数批处理。

## 反演可用性

- 输出逐级复振幅和效率；
- 与实验 detector/q-space 对接；
- 支持噪声、背景和校准参数；
- 支持梯度或高效参数扫描；
- 输出参数不确定度和可辨识性；
- 能识别模型不足，而不是强制返回一个貌似精确的结构。

---

# 13. 参考文献

- [R1] V. Soltwisch et al., *Reconstructing Detailed Line Profiles of Lamellar Gratings from GISAXS Patterns with a Maxwell Solver*, arXiv:1704.08032.
- [R2] M. Pflüger et al., *Extracting Dimensional Parameters of Gratings Produced with Self-Aligned Multiple Patterning Using GISAXS*, arXiv:1910.08532.
- [R3] A. Kato, S. Burger, F. Scholze, *Analytical modeling and 3D finite element simulation of line edge roughness in scatterometry*, arXiv:1208.4220.
- [R4] A. Fernández Herrero et al., *Applicability of the Debye-Waller damping factor for the determination of the line-edge roughness of lamellar gratings*, arXiv:1907.05307.
- [R5] Y. Yang, S. K. Sinha, *Three Dimensional Imaging using Coherent X-Rays at Grazing Incidence Geometry*, arXiv:2207.10813.

---

# 14. 当前统一结论

```text
最终目标：参数反演，而不是单次电磁场求解。

核心实验数据：
逐衍射级反射强度/效率
+ 多掠入射角
+ 零级反射率
+ 可选偏振、波长和漫散射。

当前路线：
Task031 full-3D PC 内存收口
→ Task032 hybrid FEM-modal direct
→ Task033 multi-parameter robust h/p adaptivity
→ Task034 hybrid-adaptive iterative solver
→ Task035 wavelength continuation to 0.7 nm
→ inversion / uncertainty / deployment。

关键原则：
不能依靠全域均匀 3D FEM 和继续节约几十个百分点内存解决 0.7 nm 问题；
必须采用中间规则区模态消元、局部 3D 自适应和低存储迭代的组合路线。
```
