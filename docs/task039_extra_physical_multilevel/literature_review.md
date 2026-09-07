# Task39extra 文献报告：大规模不定 Maxwell 求解、物理多层与内存架构

审阅日期：2026-09-07。任务分支：`task39extra`。继承基线：`2dc2e7305f10dc391a13970c6f0f0340cb87b6ee`。

本文提供方法依据与公式，不是求解器通过报告。执行权限、冻结参数和停止条件以同目录 `task.md` 为准。历史依据见 `prior_attempts_retrospective.md`。所有方法均按三维体问题讨论；单元张量结构不等于全局几何可分离，内部辅助粗空间不等于把物理模型降为准二维。

## 1. 结论与证据等级

公开研究已经完成十亿乃至百亿未知量的三维频域电磁计算。共同点不是某个 Krylov 名称，而是完整的离散、全局纠错、局部近似逆和并行存储设计。超算上的可解性不能直接转换为单节点 2 TB 的可行性，更不能转换为本机 16 GB 的承诺。

本文使用三种文献证据等级：`PRIMARY_ABSTRACT` 为出版社或作者档案摘要已核；`PRIMARY_TEXT` 为原始论文正文可读；`UNVERIFIED_LEAD` 为只有检索线索、原始页面或全文未取得。理论公式若是本文推导，会明确写出假设，不冒充针对本项目的已证定理。PDF 文本可读但截图失败的表格不作资源资格依据。

| 文献 | 已核验内容 | 重要限制 | 本任务用途 |
|---|---|---|---|
| [L1] Chanaud 等，2014 | 三维时谐 Maxwell；几何 full multigrid；细层 matrix-free；最粗层并行稀疏直接解；摘要报告最高约 13 亿未知量 | 不是 factorization-free；总内存和最粗层规模本次未逐表复核 | 物理全局层的架构依据 |
| [L2] Liu 等，2020 | 三维散射 FEM-DDM；两级区域组织；接口 BD-SGS；摘要报告超过 100 亿未知量 | 全部资源、容差和局部逆细节未取得，不换算为 2 TB 保证 | 接口求解、通信和内存必须一体设计 |
| [L3] Lu、Xu，2016 | 时谐 Maxwell；稳定 CIP 粗修正与分层平滑器；外层 GMRES；局部 Fourier 分析 | 不是直接替换本仓库的离散；本文没有复现其算法 | 粗层稳定性和相位表示必须设计 |
| [L4] Bonazzoli 等，2019 | 高频有吸收 Maxwell 的 DD 分析及实验 | 理论受吸收、子域、重叠和粗尺度条件限制 | 区分真实弱损耗与辅助复移位 |
| [L5] Li、Hu，2026；作者稿 2025 | 局部 Maxwell-harmonic 空间的两级 weighted Schwarz；阈值控制粗空间；正文注明局部和粗解使用 MUMPS | 鲁棒性有假设；谱空间维数及 factor 成本不能忽略；不能与旧 positive-energy GenEO 混称 | 备用物理粗空间参考，不自动启动新 DD |
| [L6] HPS–Helmholtz，作者稿 2021、后续期刊版 | 三维标量 Helmholtz；高阶局部离散与迭代；作者稿涉及约十亿未知量 | 不是矢量 H(curl) Maxwell；本次 PDF 截图失败，不将表格内存/秒数作为本任务 Gate | 学习局部内核和存储组织 |
| [L7] Tsuji、Engquist、Ying，2012 | Maxwell 有限元 moving-PML sweeping 的原始研究 | 当前仓库一般 multiplicative double sweep 不是该算法完整复现 | 澄清 PML 与近似 Schur 消元的关系 |
| [L8] PETSc FGMRES | 允许变化或非线性 PC；只支持右预条件 | restart 不会修复无效的物理近似逆 | 外/内层 Krylov 的合法性 |
| [L9] hypre AMS | 针对正定/半正定 curl-plus-mass，需要离散梯度等结构 | 不能直接将适用结论推广到任意不定散射 | positive auxiliary 的正确定位 |
| [L10] MFEM partial assembly | 算子分解、单元限制、基函数计算和积分点系数分离 | 是实现参考，不替换 DOLFINx，不保证所有单元/后端同样快 | 避免高阶矩阵与巨型展开内核 |

### 1.1 对先前聊天中新预印本的纠偏

此前提及 `arXiv:2608.22903`、Shubin Fu、题为 *A Fully Matrix-Free Three-Grid Preconditioner for the Time-Harmonic Maxwell Equations at Extreme Scale* 的线索。本次对 arXiv abs、PDF、HTML 和 export 入口的读取未成功；检索镜像存在摘要，但没有取得可核对的原始全文。因此登记为 `UNVERIFIED_LEAD`，**不把所谓百亿规模、64 GPU 或几十秒结果作为已核验事实，不用它规定工程参数，不要求 Codex 因全文暂不可得而停止本任务**。以后取得原文，必须独立核对标量/矢量、精度、边界、计时、内存及代码再升级证据等级。

物理多层方案的基础是 [L1,L3,L4] 和本项目既有证据，而不是这一条未核实的最新性能宣传。

## 2. 从 Maxwell 到需要求解的矩阵

以下采用时间因子 `exp(-i omega t)`，实际代码必须核对其约定。以电场为未知量，示意强式为：

```math
\nabla\times(\mu_r^{-1}\nabla\times E)-k_0^2\epsilon_r E=f,
\qquad k_0=2\pi/\lambda_0.
```

复折射率写作 `n=1-delta+i beta` 时，在该约定下被动介质的正 beta 对应传播衰减；非磁材料有 `epsilon_r=n^2`。0.7 nm 的材料必须来自该波长的正式数据，不能沿用 13.5 nm 光学常数。

将 x/y Floquet 条件写为 `E(x+Lx,y,z)=exp(i kx Lx)E(x,y,z)` 及对应 y 条件。沿 z 使用 Fourier-DtN 时，弱式由体积分和边界作用组成：

```math
a(E,v)=\int_\Omega \mu_r^{-1}(\nabla\times E)\cdot\overline{\nabla\times v}\,dV
-k_0^2\int_\Omega\epsilon_r E\cdot\overline v\,dV
+t_{\rm DtN}(E,v)=\ell(v).
```

边界项的符号、法向、归一化和共轭按仓库已验证实现，不从本式另造一套。Nedelec H(curl) 元保持适当切向连续性，不是三个互不相关的标量 Lagrange 问题。

设约束展开为 `u_full=C u_ind`，则独立自由度上的代数系统为：

```math
A=C^H A_{\rm full}C,
\qquad b=C^H b_{\rm full},
\qquad A u=b.
```

真实残差用独立物理坐标或等价的合法 slave-zero 表示计算；不能把含人工 unit slave rows 的存储行误当独立物理 DoF。raw 数组长度、active rows、trace rows、auxiliary modes 应分别记录。

## 3. “不定”与“非 Hermitian”分别意味着什么

对实对称/Hermitian 矩阵，正定意味着所有非零向量都有正的二次型。不定意味着存在正、负方向。对有损、出射的复矩阵，“不定 Maxwell”通常描述其波动核心 `K-k0^2 M`；完整矩阵还可能非 Hermitian、非正规，不能把一个实对称特征值故事当作完整收敛理论。

非正规矩阵满足 `A^H A != A A^H`。此时特征向量条件数、数值域及伪谱都可能影响迭代行为。仅给条件数、最小特征值或一次残差比不足以判定所有 RHS 的 FGMRES 收敛。零空间/梯度子空间、材料界面、近截止通道也必须尊重。

对精确解与近似解，有：

```math
r=b-Au,\qquad e=u_*-u,\qquad Ae=r.
```

小残差不是小场误差的无条件保证；例如在相容范数中：

```math
\frac{\|e\|}{\|u_*\|}\le \kappa(A)\frac{\|r\|}{\|b\|}.
```

该上界只说明病态系统可能放大残差，不能用未测条件数宣称实际场误差。代数残差、离散误差、材料误差及端口截断误差须分开。

## 4. 预条件器是一个近似逆过程，不必是矩阵

设 `Q_j(v)` 为一次预条件作用。FGMRES 在每步形成：

```math
z_j=Q_j(v_j),\qquad w_j=A z_j,
\qquad u_m=u_0+Z_m y_m.
```

由 Arnoldi 小问题选择 `y_m`，目标仍为原始残差。内层迭代次数、最小残差接受系数等可能随输入变化，所以使用 flexible 外层是合法性要求 [L8]。固定做三步 GMRES 不会自动使 PC 成为线性算子。

PC 设计同时追求两点：每次作用便宜，以及返回方向能够有效处理原始误差。一次 PC residual contraction 并不是一般 FGMRES 的必要条件；但一个 PC 若长期返回与困难误差无关的方向，增加 restart 也不能代替机制改进。

## 5. 为什么用正定 B，以及它为什么可能不够

旧辅助形式概念上是：

```math
B=K_{\rm curl}+k_0^2 M_{|\epsilon|}.
```

它消除了正负项抵消，容易建立稳定多层、能量平滑和辅助空间结构 [L9]。若 B 正定、P 列满秩，则：

```math
y^H(P^HBP)y=(Py)^HB(Py)>0.
```

这不等于 `B^-1` 是高频物理 A 的强 PC。对无损、无 DtN 的理想化模型，设 `A=K-k^2 M`、`B=K+k^2 M`、`Kv=theta Mv`，可直接推导：

```math
B^{-1}Av=\frac{\theta-k^2}{\theta+k^2}v.
```

当 `theta` 接近 `k^2` 时，比值接近零；精确求解 B 也不会消掉该困难。这个推导解释一种失配机制，**不是本仓库矩阵的已测谱或唯一根因诊断**。

应分别检查 `Q≈B^-1` 的实现误差，以及 B 相对 A 的模型失配。继续增加正定平滑器的步数主要改善前者。AMS 对正定问题的可扩展性，不等于对后者也有波长鲁棒性。

## 6. 真实物理多层：允许什么，必须解决什么

### 6.1 物理中间层

设 `P:V_c -> V_f` 为相容延拓，可采用：

```math
A_c=P^H A_f P,\qquad r_c=P^H r_f,
\qquad A_c e_c=r_c,\qquad d_f=P e_c.
```

也可构造稳定的再离散粗算子，但应明确它是否等于 Galerkin 算子，不能将两者混用。物理层必须保留负质量、真实复材料、Floquet 及匹配的开放边界定义，不把 coarse 变成另一个更简单的散射物体。

不定性不会像正定性那样自动被 Galerkin 粗化保留。例如 `A=diag(1,-1)`、`P=(1,1)^T/sqrt(2)` 时细 A 可逆，但 `P^H A P=0`。这是简单反例，不是当前粗矩阵奇异的证据。

[L3] 的意义就在于同时设计粗层稳定性和不同层平滑器。**“真实 A 多层”不是把所有 B 字符替换成 A。**

### 6.2 p 粗化与 h 粗化

p 粗化在同一网格降低局部多项式阶次；h 粗化扩大单元。它们都会改变离散相位精度。物理传播分量的难误差不一定是几何低频；最低阶 p1 不一定有资格承担全局物理修正。

相位误差可用传播距离 L 上的累计偏差示意：

```math
\Delta\phi=(k_h-k)L.
```

本任务不会把固定 `h/lambda` 当充分精度条件，也不凭 p4 比 p3 高就宣称 coarse 合格。粗层选择应结合场/模式表示、材料界面、h/p 实测与总成本。固定 p4 只可作为一次有界研究起点。

### 6.3 复移位放在内部，真实中间方程不变

定义带正实权重质量矩阵 W 的辅助算子：

```math
\widehat A_c=A_c-i\sigma k_0^2 W_c,\qquad \sigma>0.
```

符号应与吸收约定一致。用 shifted 多层近似 `widehat A_c^-1` 来预处理求解 `A_c e_c=r_c` 的内层 Krylov，而外层仍解 `A_f u=f`。这样复移位不是更改真实材料。

sigma 增大通常改善内部可解性，却增大与真实 A 的差异；这是权衡，不是 sigma 越大越好。[L4] 对有吸收 Maxwell 的结果不能不带假设搬到弱损耗情形。任务中的固定 sigma 是工程试验值，不声称来自未核验论文的最优参数。

### 6.4 有限维最小残差接受

对已有候选修正 d，令 `w=A_f d`。在 w 非零时，最佳复标量为：

```math
\alpha=\frac{w^H r}{w^H w},
\qquad r_{\rm new}=r-\alpha w.
```

这是对一维最小二乘的直接推导，精确算术下不会比取 alpha=0 更差。多个有限方向可用稳定 QR/SVD，而不是病态正规方程。不得通过拟合最终 E/H 的整体相位来替代这种合法的求解过程。

它可以防止一次粗修正的过冲，但不能创造不存在于候选方向中的误差信息。alpha 接近零且长期无收益应如实报告，不能称“单调所以必将快速收敛”。任务只允许每次 PC 内有限个方向，不形成不断增长的全局 Z/AZ 库。

## 7. 区域分解、Schur 与 sweeping：不要混成一个名词

将自由度分成内部 I 和接口 Gamma，代数消元得到：

```math
S_\Gamma=A_{\Gamma\Gamma}-A_{\Gamma I}A_{II}^{-1}A_{I\Gamma}.
```

它代表内部对接口的反馈，包含真实传播、反射和多次散射。区域分解可以求接口方程，也可以直接作为全场 PC；Schur 补可显式或隐式作用；它们不是互相排斥的方法。

设局部逆近似为 `L_j^-1`，加法 Schwarz 示意为：

```math
Q_{\rm AS}=\sum_j R_j^H D_j L_j^{-1}R_j.
```

multiplicative 版本按顺序更新残差。PML 是局部边界工具；双扫是访问顺序；全局 coarse 是远程纠错结构。当前四子域 PML 双扫不等于 [L7] 的 moving-PML 近似块消元算法。

PML 减少的是人工截断引入的错误反射，不应消除真实材料反射。局部 PML 以材料延拓和吸收近似被截掉区域；复杂真实区域的全部返回反馈一般不包含在这一近似中。

[L2] 的大规模 FEM-DDM 证据表明，接口迭代器、层级划分和通信组织必须共同设计。[L5] 的粗空间则在真实局部 Maxwell-harmonic 空间选择方向，而不是默认 positive-energy 特征向量可以替代。两者都不能绕过粗维数和局部逆成本。

## 8. H(curl)、Floquet 与传递的数学要求

相容传递应尊重离散微分结构。例如边空间传递 `P_curl` 与标量空间传递 `P_0` 希望满足适当的交换关系：

```math
G_f P_0=P_{\rm curl}G_c,
\qquad C_f P_{\rm curl}=P_{\rm div}C_c.
```

此处 G、C 分别为相容离散梯度、旋度，不是 Floquet 约束矩阵。公式是结构目标；各元族和约束空间应给出实际定义。不能把一个任意结点插值当作 Nedelec 的合法高阶传递。

Floquet 下必须区分 primal prolongation、dual restriction 和 Hermitian 伴随。对合法测试向量，应验证：

```math
\langle P u,v\rangle=\langle u,P^H v\rangle.
```

必须核对 petsc4py 所用复 dot 的实际接口语义，不根据函数名称猜测共轭方向。历史任务已发生过这类问题，参见经验报告。

## 9. 高频精度：四类“收敛”不能合并

| 名称 | 所比较的量 | 不代表什么 |
|---|---|---|
| 线性求解收敛 | 同一 A,b 的 true residual | 不代表网格精度 |
| h/p 精度 | 同一连续几何和材料下 E/H、RTA、orders 随离散变化 | 不代表 PC 波长鲁棒 |
| 算法 h 鲁棒性 | 固定物理和 k，迭代/工作量随网格的变化 | 不代表不同 k 同样有效 |
| 波长鲁棒性 | 对应材料与合格离散下，k 增大后的工作量 | 不代表总内存一定可承受 |

必须同时检查几何表示变化。cell-tag notch 在细化时要保持同一实体几何，不能每个新网格重新按中心阈值选一组不同材料单元后称为 h 收敛。

## 10. 十亿 DoF 的内存账本

complex128 一个长向量为 `16N` bytes。FGMRES 仅两组基向量的常见存储模型约为：

```math
M_{\rm basis}\simeq16N(2m+1).
```

| 独立复未知量 N | 单向量 | m=20 的基向量模型 | m=64 的基向量模型 |
|---:|---:|---:|---:|
| 1e8 | 1.6 GB | 65.6 GB | 206.4 GB |
| 1e9 | 16 GB | 656 GB | 2064 GB |
| 3e9 | 48 GB | 1968 GB | 6192 GB |

全部为 decimal bytes 的 derived 值，不是 PETSc RSS；还要加 ghost、网格、转移、内层同时存活 Krylov、材料、端口与输出工作集。2 TB 与 2 TiB 必须区别，系统余量不能分给程序。

若 Z 和 AZ 都按全长稠密形式保存，成本是：

```math
M_{Z,AZ}=32Nr.
```

N=1e9、r=75 就是 2.4 TB。旧 sparse z-hat 不等于这个稠密布局；公式用于阻止未来无意识地构造全局稠密 coarse basis。

嵌套求解的峰值是同时存活对象之和，再对阶段取最大：

```math
M_{\rm peak}=\max_t\left(M_{\rm outer}(t)+M_{\rm inner}(t)+M_{\rm PC}(t)+M_{\rm FE}(t)+M_{\rm other}(t)\right).
```

不得取每个 MPI rank 各自历史峰值相加冒充同期总量，也不得把不同时间阶段的峰值相加。对于数十亿全局编号，须预先检查 64 位 PetscInt 和所有接口的 ABI [L11]。

## 11. 高阶内核、DtN 与后处理

partial assembly 可以写成单元求和的示意分解：

```math
A_{\rm vol}=\sum_e R_e^H B_e^H D_e B_e R_e.
```

B_e 包括基函数值/旋度评估，D_e 包括材料、Jacobian 和积分权重。复数情形和不同 test/trial 的返回映射应按实际弱式定义。张量积单元可利用 sum factorization，避免存储巨大的高阶稠密单元矩阵 [L10]。这是局部计算结构，不要求全局材料可分离。

真实 DtN 可示意为：

```math
T_{\rm DtN}u=\sum_m c_m\,t_m^H u.
```

实际归一化由代码 authority 决定。streaming 避免 FE×mode 全矩阵，但若逐 mode 重复高成本组装，时间仍可能不可接受。须分别报告 mode 数、trace rows、apply wall 和 retained bytes。不能因 PC coarse 较小而删除真实外层通道。

恢复 H、近场采样、衍射投影也可能创建大数组。必须先保存最终解、释放 PC/KSP/factors 后再恢复，所有后处理仍纳入同一 process-tree/cgroup 资源范围。

## 12. 面向本项目的取舍

主研究假设是：在便宜的 positive smoothing 之外，让完整物理中间层产生全局修正；中间方程由有限工作量 Krylov 求解，complex shift 只用于其内部 PC。它与旧一次 p3 粗修正的区别在于完整 pre/coarse/post 组合、真实外层检验、避免单位步长过冲，以及在更高表示阶次上检验中间层。**这是假设，不是波长鲁棒定理。**

第一版固定 p4 中间层只用于尽快作出真实模型判断。若精确中间解也无益，应关闭该具体表示/组合，而不是继续调 inner tolerance。若参考有效而迭代中间解失效，才研究内部近似逆。若只有规则结构成功，不能升级为任意三维。

本机阶段不启动另一个 PML、75D、FFT 背景或 GenEO 搜索。短波长阶段必须逐步改进物理层解析能力、最底层容量与分布式内核；不从 13.5 nm 的一次通过直接跳最大 0.7 nm。

## 13. 文献入口、核验范围与可追溯说明

| 编号 | 文献或官方文档 | 入口及本次核验 |
|---|---|---|
| L1 | Chanaud, Giraud, Goudin, Pesque, Roman. A Parallel Full Geometric Multigrid Solver for Time Harmonic Maxwell Problems. SISC 36, C119–C138, 2014 | https://doi.org/10.1137/130909512 ; PRIMARY_ABSTRACT |
| L2 | Liu, Yang, Wu, Sheng. Parallel hierarchical decomposition of finite element method with block diagonal symmetric Gauss-Seidel preconditioner for solving 3D problems with over ten billion unknowns. IJNM 33, e2744, 2020 | https://doi.org/10.1002/jnm.2744 ; PRIMARY_ABSTRACT |
| L3 | Lu, Xu. A Robust Multilevel Method for the Time-harmonic Maxwell Equation with High Wave Number. SISC 38, A856–A874, 2016 | https://doi.org/10.1137/15M1007033 ; PRIMARY_ABSTRACT |
| L4 | Bonazzoli 等. Domain decomposition preconditioning for the high-frequency time-harmonic Maxwell equations with absorption. Math. Comp., 2019 | https://arxiv.org/abs/1711.03789 ; PRIMARY_ABSTRACT；理论条件不可省略 |
| L5 | Li, Hu. A hybrid two-level weighted Schwarz method for time-harmonic Maxwell equations. JCAM 475,117015,2026；作者稿题名含 Schwartz 拼写 | https://doi.org/10.1016/j.cam.2025.117015 ; https://arxiv.org/abs/2501.18305 ; PRIMARY_TEXT，作者稿§1、§7；PDF截图未成功 |
| L6 | An iterative solver for the HPS discretization applied to three dimensional Helmholtz problems | https://arxiv.org/abs/2112.02211 ; PRIMARY_TEXT，标量问题；表格截图未成功，资源表不作本任务资格基线 |
| L7 | Tsuji, Engquist, Ying. A sweeping preconditioner for time-harmonic Maxwell's equations with finite elements. JCP 231,3770–3783,2012 | https://doi.org/10.1016/j.jcp.2012.01.025 ; 书目信息由L3出版社参考文献核对；本次DOI正文未取得 |
| L8 | PETSc KSPFGMRES | https://petsc.org/release/manualpages/KSP/KSPFGMRES/ ; 官方接口正文；运行仍绑定本机具体版本 |
| L9 | hypre AMS | https://hypre.readthedocs.io/en/latest/solvers-ams.html ; 官方方程及适用条件 |
| L10 | MFEM Performance and Partial Assembly | https://mfem.org/performance/ ; 官方算子分解说明；不是要求切换软件 |
| L11 | PETSc PetscInt | https://petsc.org/release/manualpages/Sys/PetscInt/ ; 官方索引说明 |

本文不是穷尽所有文献的系统综述，也没有复算论文实验。研究结论应由本项目完整、真实、非可分三维外层求解决定。必要的新原文可以后续补充，但不能因追求文献数量而拖延已定义的有限真实模型试验。
