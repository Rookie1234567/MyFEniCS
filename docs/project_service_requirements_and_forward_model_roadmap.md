# 光栅参数反演服务需求与前向模型技术路线

## 0. 文档身份

```text
status = project-level planning baseline
scope = service requirements + inversion observables + forward-model roadmap
current_reference_wavelength = 13.5 nm
target_service_wavelength = 0.7 nm
target_grazing_angle_range = 1–10 deg from surface
target_compute_memory = 1–2 TB
```

本文档用于统一项目最终服务需求、参数反演所需观测量、当前 FEniCS 前向模型能力、0.7 nm 波长下的资源瓶颈，以及 Task031–Task036 的技术路线。

本文档不是某一个 Task 的任务书。后续任务书必须与本文档保持一致；若实验测量能力、材料数据来源或最终服务接口发生变化，应先更新本文档，再调整算法路线。

本文档中的独立公式统一使用 `$$...$$`，以保证 GitHub Markdown 和常用 Markdown 阅读器能够正常渲染。

---

# 1. 项目最终目标

项目最终目标不是只求解一次电磁场，而是建立一套服务于光栅和周期纳米结构参数反演的计算系统：

```text
实验散射数据
→ 参数化结构模型
→ 高可信前向 Maxwell 求解
→ 参数优化或概率反演
→ 参数估计、置信区间和可辨识性报告
```

最终服务预期支持：

- 掠入射 X 射线；
- 目标波长约 `0.7 nm`；
- 相对样品表面约 `1–10°` 的掠入射角；
- S/P 两种入射偏振；
- 波长变化对应的复折射率或介电常数色散；
- 周期光栅及其平均单胞；
- 后续可能出现的局部三维曲面、圆角、非均匀端部和材料三维变化；
- 1–2 TB 内存服务器；
- 大量重复前向计算，而不是只完成单个 benchmark；
- 最终与优化、MCMC、代理模型或其他反演框架连接。

因此，最终前向模型应具备：

```text
正确性
+ 参数化
+ 可重复批量运行
+ 资源可扩展
+ 输出量完整
+ 数值误差可审计
```

---

# 2. 当前阶段与最终阶段的服务边界

项目必须区分两个层次。

## 2.1 当前前向模型阶段

Task031–Task036 的主要目标是构造可靠、高效、参数化的 Maxwell 前向模型。当前阶段优先处理：

- 几何参数；
- 波长；
- 掠入射角；
- 方位角；
- S/P 入射偏振；
- 波长相关材料复折射率；
- 各反射和透射衍射级；
- 总反射、透射和吸收；
- 数值误差、内存和时间。

当前阶段**不要求**把以下实验层因素完整加入前向 Maxwell 求解器：

- 探测器绝对强度标定；
- 入射光强的绝对值；
- 探测器背景和暗电流；
- 测量噪声模型；
- 测量不确定度；
- detector gain；
- beam divergence；
- 数据缺失、beam stop 和饱和像素。

这些因素不会改变 Maxwell 场方程的核心求解，可以在前向模型稳定后，由实验数据层和反演似然层加入。

## 2.2 当前阶段必须预留的接口

虽然当前暂不建模绝对强度、背景和噪声，但前向数据合同必须：

- 使用明确、稳定的功率归一化；
- 输出复振幅和归一化衍射效率；
- 保存角度、波长、偏振和材料版本；
- 为后续全局强度尺度、背景项和测量协方差预留字段；
- 不把某一实验仪器的 counts 单位硬编码到 Maxwell 求解器中。

## 2.3 后续反演阶段

前向模型稳定后，再加入：

```text
实验数据读取和标定
+ absolute/relative intensity mapping
+ background/noise model
+ measurement uncertainty
+ objective/likelihood
+ optimizer or Bayesian inference
```

因此，绝对强度、背景、噪声和不确定性可以后补，不应阻塞当前前向模型开发。

---

# 3. 反演对象：需要重构哪些参数

最终反演参数向量可写为：

$$
\mathbf p =
\left(
\mathbf p_{\mathrm{geometry}},
\mathbf p_{\mathrm{material}},
\mathbf p_{\mathrm{roughness}},
\mathbf p_{\mathrm{calibration}}
\right).
$$

## 3.1 第一阶段几何参数

第一阶段优先支持：

- 周期或 pitch；
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

## 3.2 材料参数

材料通常写为：

$$
n(\lambda)=1-\delta(\lambda)+i\beta(\lambda),
\qquad
\varepsilon_r(\lambda)=n^2(\lambda).
$$

当前决定是：

- 材料种类和数据来源沿用项目现在使用的材料设置；
- 在当前 `13.5 nm` benchmark 中继续使用已经验证的复折射率；
- 波长改变时，必须从同一材料数据来源更新对应的 `n(λ)`，不能把 13.5 nm 的数值直接用于 0.7 nm；
- 第一阶段把材料色散视为确定输入，而不是主要反演参数；
- 后续只有在材料数据库或实际样品存在明显不确定性时，再引入密度缩放、氧化层或折射率修正参数。

## 3.3 粗糙度和统计缺陷参数

严格周期单胞模型首先描述平均结构。若后续需要反演制造缺陷，还可考虑：

- line-edge roughness，LER；
- line-width roughness，LWR；
- RMS 粗糙度；
- 相关长度；
- 线高变化；
- pitchwalk；
- 周期抖动；
- 单胞间随机差异。

这些参数通常需要漫散射、峰宽和峰形信息。当前规则周期单胞前向模型暂不把粗糙度反演作为 Task032–Task036 的硬目标。

## 3.4 实验校准和 nuisance 参数

后续反演可能需要同时估计：

- 入射掠角零点偏差；
- 方位角偏差；
- 样品倾斜；
- 波长或能量标定误差；
- 入射强度尺度；
- 探测器增益；
- 背景和暗电流；
- 偏振纯度；
- 数据归一化尺度。

这些参数属于反演和实验数据层。当前前向求解器只需提供稳定的归一化输出和参数化接口。

---

# 4. 反演需要哪些观测量

## 4.1 核心观测量：逐衍射级反射效率

最核心的前向输出为：

$$
R_{mn}(\alpha,\phi,\lambda,\mathrm{pol}),
$$

其中：

- `(m,n)` 是二维周期结构的衍射级；
- `α` 是相对样品表面的掠入射角；
- `φ` 是方位角；
- `λ` 是波长；
- `pol` 是 S 或 P 入射偏振。

逐衍射级数据保留不同空间频率的信息，是重构线宽、高度、侧壁角、圆角和复杂轮廓的主要信息源。

若实验最终提供二维探测器图像，后续数据层可进一步提取：

- 每个离散衍射峰的积分强度；
- 峰位置；
- 峰宽和峰形；
- 峰周围漫散射；
- detector pixel 到 q-space 的映射。

## 4.2 零级或镜面反射率

零级反射率为：

$$
R_{00}(\alpha,\lambda,\mathrm{pol}).
$$

它非常重要，主要约束：

- 平均电子密度；
- 表面层和覆盖层厚度；
- 材料临界角；
- 层间粗糙度；
- 平均纵向密度分布。

但 `R00` 或总反射率通常不足以唯一确定横向线宽、侧壁角和复杂轮廓。因此服务需求定位为：

```text
逐衍射级反射效率 = 结构反演核心
零级反射率 = 材料/层结构的重要约束和一致性检查
```

## 4.3 掠入射角范围

角度统一采用相对表面的掠角 `α`。与相对法向角 `θ` 的关系为：

$$
\alpha = 90^\circ-\theta.
$$

当前 `θ=80°` 等价于 `α=10°`。

第一版前向模型和鲁棒性验证采用完整工作区间：

```text
alpha_from_surface = 1°, 2°, 3°, 4°, 5°, 6°, 7°, 8°, 9°, 10°
```

这一范围可作为当前项目的默认掠入射服务域，基本覆盖从强掠入射到当前 10° benchmark 的需求。

但“覆盖 1–10°”不等于只计算十个整数点。后续应允许在以下位置自动加密：

- 材料临界角附近；
- 新衍射级出现或消失的 cutoff 附近；
- 反射强度随角度变化剧烈的区间；
- 反演灵敏度较高的区间；
- 迭代求解器明显变困难的区间。

建议开发阶段先使用：

```text
基础全区间：1° 间隔，共 10 个角度
低成本 smoke：1°, 2°, 3°, 5°, 7.5°, 10°
局部加密：由临界角、cutoff 或响应曲率触发
```

多角度数据可以改变穿透深度、驻波和各结构参数的敏感性，有助于降低线宽、高度、侧壁角和材料参数之间的相关性。

## 4.4 S/P 偏振

项目当前已经支持 S/P 入射偏振。因此后续 Task032–Task036 应将：

```text
S polarization
P polarization
```

作为正式参数化能力，而不是待开发功能。

当前最低目标是分别输出 S 入射和 P 入射下的各衍射级效率。交叉偏振通道 `S→P` 和 `P→S` 可作为真正三维非对称结构阶段的增强能力，不阻塞当前规则结构路线。

## 4.5 波长和材料色散

多波长观测可写为：

$$
\mathcal Y_{\lambda}
=
\left\{R_{mn}(\lambda_k)\right\}_{k=1}^{N_\lambda}.
$$

第一版反演服务不必进行密集能量扫描，但从 Task032 起，前向接口必须把 `lambda` 和材料色散设为参数。

Task036 的波长序列为：

```text
13.5 nm
→ 5 nm
→ 2 nm
→ 1 nm
→ 0.7 nm
```

每个波长都使用相同材料体系，但更新该波长对应的复折射率。

## 4.6 透射、吸收和能量闭合

若实验几何允许测量透射，应保留：

$$
T_{mn}(\alpha,\lambda,\mathrm{pol}).
$$

对于厚基底反射式测量，透射可能无法实验获取。前向模型仍应计算：

- 总反射率；
- 总透射率；
- 体吸收率；
- 能量闭合。

吸收率和能量闭合当前首先作为物理一致性、材料诊断和数值验证量。

## 4.7 复振幅和相位

第一版服务采用：

```text
内部始终计算 complex diffraction amplitudes
反演核心输出 normalized intensities / efficiencies
预留 phase-aware measurement interface
```

相位信息属于后续增强能力，不作为当前最小可行服务的前置条件。

## 4.8 漫散射、峰宽和粗糙度

漫散射和峰宽主要服务于 LER、LWR 和随机缺陷反演。当前规则周期单胞模型先输出 coherent diffraction orders；粗糙度统计模型、supercell 和随机三维模型放到后续阶段。

---

# 5. 当前最小可行前向模型合同

## 5.1 当前必需输入

```text
- parameterized geometry
- wavelength
- grazing angle alpha in 1–10 deg
- azimuth angle phi
- S or P polarization
- current material optical-constant data at the selected wavelength
- mesh/discretization controls
```

## 5.2 当前必需输出

- 每个传播反射级的复振幅 `r_mn`；
- 每个传播反射级的归一化效率 `R_mn`；
- 若适用，每个传播透射级的 `t_mn/T_mn`；
- `R_total/T_total/A_volume`；
- 模态 identity、传播/衰减分类和功率归一化；
- reported residual；
- explicit condensed true residual；
- explicit full augmented residual；
- 能量闭合误差；
- 模态截断误差估计；
- FEM 离散误差估计；
- 网格、阶次、DoF 和模式数；
- 内存、迭代次数和时间；
- commit、command、image digest 和材料数据版本。

## 5.3 当前不要求的实验层输入和输出

以下内容当前可以暂不实现：

```text
- absolute detector counts
- absolute incident intensity
- detector gain
- detector background
- dark current
- measurement noise distribution
- measurement covariance / uncertainty
- missing-pixel and saturation model
```

这些内容在前向模型稳定后，由 measurement-data schema 和 inversion likelihood 补充。

---

# 6. 后续实验数据与反演接口

实验强度与归一化模拟强度之间可在后续写成：

$$
I_i^{\mathrm{obs}}
=
s_i I_i^{\mathrm{sim}}+b_i+\epsilon_i,
$$

其中：

- `s_i` 表示强度尺度、曝光或探测器增益；
- `b_i` 表示背景；
- `ε_i` 表示测量噪声。

这说明绝对强度、背景和噪声可以在 Maxwell 计算之后加入，不要求进入当前 PDE 求解。

后续反演观测向量可写为：

$$
\mathbf y_{\mathrm{obs}}
=
\left\{
I_{mn}^{\mathrm{obs}}(\alpha_j,\phi_j,\lambda_j,\mathrm{pol}_j)
\right\}.
$$

前向映射为：

$$
\mathbf y_{\mathrm{sim}}
=
\mathcal F(\mathbf p,\boldsymbol\mu).
$$

实验接口明确后，再决定使用绝对强度、相对强度、对数强度、归一化峰强度或它们的组合。

---

# 7. 当前 FEniCS 前向模型能力

截至 Task030 合并，项目已经建立：

```text
- 2D/3D frequency-domain Maxwell framework
- complex-valued Nedelec H(curl) discretization
- matched hexahedral target mesh
- double Floquet periodic boundary conditions
- S/P incident polarization
- auxiliary Fourier-DtN modal ports
- auto-propagating diffraction-order policy
- per-order and total R/T
- volume absorption A
- exact auxiliary condensation A = F - C H^-1 D
- direct reference solves
- MPI4 physical-slab + 75D wave-coarse iterative solver
- explicit condensed/full residual validation
- benchmark, provenance and memory telemetry framework
```

当前冻结 `13.5 nm`、p2、`h=2 nm` benchmark：

```text
FE DoF ≈ 615,108
direct reference peak ≈ 20.53 GB
Task030 compact iterative peak ≈ 9.37 GB
Task030 h2 iterations = 1,873
```

Task030 将内存相对直接法降低约 54%，相对 Task027 迭代基线降低约 28%。最终成功机制仍是 Task27-derived physical-slab + 75D Floquet wave coarse，而不是真正 p/h multigrid。

Task031 继续以内存为第一优先级，研究低存储 Krylov、真正 matrix-free `F`、对象提前释放、slab factor 精确去重和 overlap/slab 重构。

---

# 8. 0.7 nm 下的根本资源问题

若保持当前约 `50 × 25 × 140 nm` 计算域，并使用约 `0.1 nm` 的均匀三维网格：

```text
hexahedral cells ≈ 500 × 250 × 1400 = 1.75e8
p2 H(curl) DoF order ≈ several 1e9
one complex128 vector ≈ tens of GiB
Krylov basis alone can exceed multiple TiB
```

按当前每自由度内存直接外推，全域均匀 3D FEM 可能需要数十 TB，而目标服务器只有 1–2 TB。

因此，后续路线不能依靠继续将同一个全域 3D FEM PC 优化几十个百分点。必须至少同时实现：

```text
物理/维度降维
+ 局部 h/p 自适应
+ matrix-free/低存储迭代
```

---

# 9. 后续前向模型总体架构

真实服务结构预期可能包含：

```text
bottom 3D complex region
+ middle z-invariant region
+ top 3D complex region
```

其中中间大段满足：

$$
\varepsilon(x,y,z)=\varepsilon(x,y).
$$

推荐最终架构：

```text
local bottom 3D FEM
+ middle 2D eigenmode / modal propagation
+ local top 3D FEM
+ internal two-sided Modal-DtN / Schur coupling
```

中间规则区域不再沿 z 使用密集体网格，而由截面本征模沿 z 解析传播。上下局部复杂区保留完整三维 FEM，以支持后续曲面、圆角和三维材料变化。

---

# 10. 开发路线

## Task031：当前 full-3D PC 内存收口

目标：

- 继续压低当前 compact physical-slab profile 的内存；
- 验证低存储 Krylov；
- 尝试释放 assembled `F`；
- 为未来局部 3D block 提供低内存组件。

Task031 仍是当前 full-3D benchmark 的工程收口，不解决 0.7 nm 的根本维度问题。

## Task032：Hybrid FEM–Modal 参数化直接法基线

仍使用当前规则物理模型和 `13.5 nm` 波长：

```text
bottom local 3D FEM
+ middle z-invariant modal region
+ top local 3D FEM
```

Task032 已在 13.5 nm 直接法 reference 上验证：

- 截面本征模；
- 正向、反向和衰减模；
- 内部双面 Modal-DtN；
- 模态凝聚；
- hybrid 与完整 3D 的场和 R/T/A 一致性；
- 模态截断收敛；
- `1–10°` 掠角参数化；
- S/P 偏振；
- 当前材料数据和小扰动验证。

当前 clean h5/h3 benchmark 结论：

```text
h3 augmented / Schur-fast / Schur-minimal = 3.853 / 3.998 / 3.224 GiB
h2 = not_run_by_gate
same-grid Hybrid/full3D = pass
parameter 1–10° S/P = API/interface smoke only
current direct implementation at 0.7 nm = not resource feasible
```

Hybrid 在 h5/h3 分别把 total rows 降低 68.62%/65.35%，assembled NNZ 降低
59.14%/59.68%。这证明架构有效，但 local LU、replicated dense modal arrays、all-mode
multi-RHS 和 all-modes shift-invert QEP 仍需重构。

## Task033：Hybrid local h/p adaptivity and interface-budget optimization

只在上下局部 3D 区域进行 h/p 自适应，中间模态区保持解析传播。

代表参数集合至少包括：

```text
alpha = 1–10 deg representative points
+ S/P polarization
+ nominal material data
+ limited material perturbation checks
```

采用 robust 指标，例如：

$$
\eta_K^{\mathrm{robust}}
=
\max_j \eta_K(\boldsymbol\mu_j).
$$

目标是形成可覆盖目标角度范围的公共网格，避免每个角度重新划分网格。

Task033 第一 Gate 在 13.5 nm direct reference 上比较相同 observable error。这里需要
区分分阶段指标：p2 graded-h 的 `3x` 只是 stretch 目标；组合使用 h/p/interface 优化后，
`3x` 才是工程目标，`5x` 是强目标，而不是把任一局部网格单独写成必须达到的最低门槛：

```text
p2 graded-h: 3x stretch target
combined h/p/interface optimization: 3x engineering target
combined h/p/interface optimization: 5x strong target
```

同时优化 interface position / buffer thickness，使 local 3D volume 与所需 evanescent M 联合受控；
未来上下复杂区域继续使用精确 complex 3D Nédélec FEM。

## Task034：Scalable generic 2D modal core

不依赖当前规则 benchmark 的 y 不变性，面向通用 `epsilon(x,y)`：

```text
distributed modal ownership
+ streamed/blocked right-left modes
+ adaptive modal truncation
+ block or matrix-free projection/Schur action
+ no replicated M^2 arrays
+ no all-mode dense multi-RHS
+ spectrum slicing / continuation
```

必须给出 13.5/5/2/1/0.7 nm 的模式数、QEP DoF、payload 和 1 TiB/2 TiB 预算。
pure-modal 或 y-sector 只允许作为当前简单几何的可选诊断/reference，不是未来服务 Gate。

## Task035：针对最终 hybrid-adaptive 系统的迭代法

在 Task033 + Task034 确定的最终离散系统上构造：

```text
matrix-free bottom/top adaptive 3D FEM
+ low-memory H(curl) multilevel/Schwarz
+ scalable modal/interface action
+ outer flexible Krylov
+ low-restart or validated low-storage alternative
```

必须支持：

- 参数点之间 continuation；
- 上一个角度解作为初值；
- PC 复用和自动重建；
- Krylov recycling；
- 内存、迭代数和时间统计；
- 失效检测和 fallback。

先完成自适应和 scalable modal core，再构造最终迭代法，避免在会被替换的均匀网格或复制
modal layout 上开发一次性 PC。whole-solver memory 以 `<=2 kB/FE DoF` 为优选目标，
`<=3 kB/FE DoF` 为探索硬上限；所有成功仍由 full explicit true residual 判定。

## Task036：逐波长缩短至 0.7 nm

建议顺序：

```text
13.5 nm
→ 5 nm
→ 2 nm
→ 1 nm
→ 0.7 nm
```

每个波长：

- 从当前材料数据体系更新对应波长的复折射率；
- 更新传播衍射级；
- 更新截面本征模；
- 运行 `1–10°` 范围的代表掠角集合；
- 记录局部 3D DoF、模式数、内存和时间；
- 建立 1–2 TB 资源预测；
- 验证参数变化下的数值鲁棒性。

---

# 11. 前向模型稳定后的反演开发

前向模型稳定后，再建立：

```text
measurement-data schema
+ geometry parameterization
+ absolute/relative intensity calibration
+ background/noise/uncertainty model
+ objective / likelihood
+ deterministic optimizer
+ adjoint or Jacobian
+ Bayesian/MCMC uncertainty
+ surrogate or multi-fidelity acceleration
```

先使用 synthetic truth 验证：

- 几何参数是否可辨识；
- 哪些角度和衍射级最有信息；
- 是否存在多个等价解；
- 需要多少次前向计算；
- 加入不同噪声和材料误差后，反演结果如何变化。

初始确定性目标函数可在后续采用适合大动态范围的形式，例如：

$$
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
$$

Bayesian 形式为：

$$
p(\mathbf p\mid\mathbf y)
\propto
p(\mathbf y\mid\mathbf p)
p(\mathbf p).
$$

这些公式属于后续反演阶段，不构成当前前向模型的阻塞条件。

---

# 12. 当前已统一的需求决定

```text
1. 当前核心目标仍是高可信、低内存的参数化前向模型。
2. 前向模型当前输出归一化复振幅、逐级效率和 R/T/A。
3. 绝对强度、背景、噪声和测量不确定性暂不进入 PDE 求解。
4. 上述实验层因素由后续 measurement/inversion layer 补充。
5. 默认掠角服务范围为相对表面 1–10°。
6. 开发阶段基础角度网格为 1° 间隔，并允许在关键区域自动加密。
7. 当前材料体系和数据来源继续沿用；改变波长时更新对应材料色散。
8. S/P 入射偏振已经支持，后续作为正式服务参数。
9. 逐反射衍射级效率是结构反演核心，R00 是重要辅助约束。
10. Task031–Task036 不因实验噪声模型尚未确定而暂停。
```

---

# 13. 仍需后续确认但不阻塞当前开发的问题

以下问题可以在前向模型开发期间并行确认：

1. 实验最终输出完整二维 detector image，还是积分后的 diffraction-order intensities？
2. 实验最终使用绝对强度还是相对归一化强度？
3. `1–10°` 范围内实际角度分辨率和角度零点精度是多少？
4. 是否需要交叉偏振通道？
5. 是否存在多方位角或样品旋转？
6. 是否存在多能量实验数据？
7. 是否能测量透射、荧光或其他吸收相关信号？
8. 最终优先反演哪些参数？
9. 单次反演允许的总时间是多少？
10. 结构参数的合理先验范围和制造约束是什么？

这些问题会影响后续反演接口和优化策略，但不影响当前 Task031–Task036 的主技术路线。

---

# 14. 项目级成功标准

## 前向正确性

- 与完整 3D reference 在可计算尺度下一致；
- R/T/A、模式身份和能量闭合通过；
- `1–10°` 掠角、S/P 偏振和波长相关材料下稳定；
- 离散误差和模式截断误差可审计。

## 资源可行性

- 0.7 nm 目标问题在 1–2 TB 内存内可完成；
- 无不可控 swap；
- 前向计算时间可满足反演所需重复调用；
- 允许 continuation、缓存和多参数批处理。

## 反演接口可扩展性

- 输出逐级复振幅和效率；
- 后续可与 detector/q-space 对接；
- 后续可加入绝对强度、背景、噪声和测量协方差；
- 支持梯度或高效参数扫描；
- 能报告参数不确定度和可辨识性；
- 能识别模型不足，而不是强制返回貌似精确的结构。

---

# 15. 参考文献

- [R1] V. Soltwisch et al., *Reconstructing Detailed Line Profiles of Lamellar Gratings from GISAXS Patterns with a Maxwell Solver*, arXiv:1704.08032.
- [R2] M. Pflüger et al., *Extracting Dimensional Parameters of Gratings Produced with Self-Aligned Multiple Patterning Using GISAXS*, arXiv:1910.08532.
- [R3] A. Kato, S. Burger, F. Scholze, *Analytical modeling and 3D finite element simulation of line edge roughness in scatterometry*, arXiv:1208.4220.
- [R4] A. Fernández Herrero et al., *Applicability of the Debye-Waller damping factor for the determination of the line-edge roughness of lamellar gratings*, arXiv:1907.05307.
- [R5] Y. Yang, S. K. Sinha, *Three Dimensional Imaging using Coherent X-Rays at Grazing Incidence Geometry*, arXiv:2207.10813.

---

# 16. 当前统一结论

```text
最终目标：参数反演，而不是单次电磁场求解。

当前前向核心数据：
逐衍射级复振幅和反射效率
+ 零级反射率
+ 1–10° 多掠角
+ S/P 偏振
+ 波长相关材料色散。

当前暂缓内容：
绝对探测器强度
+ 背景和噪声
+ 测量不确定性
+ 完整实验似然。

技术路线：
Task031 full-3D PC 内存收口
→ Task032 hybrid FEM-modal parameterized direct
→ Task033 local h/p adaptivity and interface-budget optimization
→ Task034 scalable generic 2D modal core
→ Task035 final Hybrid iterative solver
→ Task036 wavelength continuation to 0.7 nm
→ inversion / uncertainty / deployment。

关键原则：
不能依靠全域均匀 3D FEM 和继续节约几十个百分点内存解决 0.7 nm 问题；
必须采用中间 generic 2D 模态消元、精确复杂 3D 端部的局部 h/p 自适应、scalable modal
core 和低存储迭代的组合路线。1 TiB 是可信但高风险的 conditional opportunity，不是 Task032
已经证明的能力。
```
