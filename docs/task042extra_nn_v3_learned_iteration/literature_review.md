# NN-V3 文献调研与路线选择

检索/核对日期：2026-10-01。目标是0.7 nm、非可分三维周期 Maxwell 的准确有限元前向解，不是 R/T/A 黑盒回归。以下明确区分论文实际方法、本项目建议和未验证迁移；没有文献在本文中被当作本项目48小时/约2TB目标已经通过的证据。

## 1. 决定

建议让第三台 WSL 笔记本做 **算子条件化、缓存系数、多层残差修正**。同一个学习模块分别接入独立迭代和 FGMRES，先回答“修正是否有用、独立迭代是否收敛、作为 PC 是否更合算”。主设计借鉴 McMg 的 setup/apply 分离，而不是继续两个旧分支的坐标场表示或固定神经基空间求解。

这是本项目的研究选择，并非文献已证明它对本问题最佳。尤其要防止：高频全局传播没有处理好，却把局部模型微基准提速叫作全局求解提速；训练产生的平均残差下降，不能证明原 Maxwell 的所有困难误差均可消除。

## 2. 优先文献

| 文献与核对入口 | 实际学习对象 | 本任务取用与限制 |
|---|---|---|
| **McMg: A Learned Phase-Space Multi-channel Multigrid Preconditioner for Helmholtz Equations**；Jia、Liu、Wang、Xu；[arXiv:2606.30495v2](https://arxiv.org/html/2606.30495v2)，版本2026-07-02 | 介质相关准备系数，多通道层次平滑/传递；固定介质时残差到修正为线性 | 优先借鉴缓存和多通道层次思想。论文包含标量 Helmholtz 的二维及三维试验，不是复向量 Nédélec/Floquet/DtN。跨大域可涉及新增层级的微调，不能承诺无训练泛化 |
| **Accurate and scalable deep Maxwell solvers using multilevel iterative methods**；Mao、Fan；[arXiv:2509.03622v1](https://arxiv.org/html/2509.03622v1) | 子域残差到误差的神经算子，F-GMRES 和带粗空间的全局域分解 | 物理最接近；具体展示2D TE-FDFD，不是本任务3D H(curl) FE。训练使用大量子域/场数据，首轮不复制百万样本生成成本 |
| **Meta-MgNet: Meta Multigrid Networks for Solving Parameterized PDEs**；Chen、Dong、Xu；[arXiv:2010.14088v2](https://arxiv.org/html/2010.14088v2) | Meta-NN 根据算子和 RHS 生成适配的 smoother | 最接近“神经网络组织求解器并自行适配内部部件”。Poisson 的收敛保证不能外推为高频开放 Maxwell 的保证，不是任意求解器菜单选择 |
| **A Neural Multigrid Solver for Helmholtz equations with high wavenumber and heterogeneous media**；Cui、Jiang、Shu；[arXiv:2404.02493v1](https://arxiv.org/html/2404.02493v1)，Wave-ADR-NS | 可微分的 wave/ADR 两类校正循环及学习参数 | 是端到端神经增强迭代算法的具体例子；高波数实验为2D标量 Helmholtz。相位/包络拆分有启发，但不能直接把标量 ADR 公式用作向量 Maxwell 粗问题 |
| **Neural Preconditioning via Krylov Subspace Geometry**；Dimola、Coclite、Zunino；[arXiv:2507.15452v1](https://arxiv.org/html/2507.15452v1) | 静态残差预训练后，利用可微 FGMRES 和 Krylov 几何进行动态训练 | 支持“训练目标要对应实际迭代”。案例为3D-1D混合维问题，不是Maxwell；首轮只采用短展开残差训练，不直接实现所有角度损失 |
| **Learning Adaptive Coarse Spaces Using Transferable Neural Network Models for Linear and Nonlinear Overlapping Domain Decomposition Methods**；Klawonn、Lanser、Weber-Hamacher；[arXiv:2607.06261](https://arxiv.org/abs/2607.06261) | 回归模型预测粗基，分类模型预测所需粗基数量 | 很接近记忆中的“还能自己选择”，选择的是粗空间维数，并非求解器每一步全由网络取代。只作为后续自适应候选，不替代本轮残差修正资格 |

阅读深度：上述前五项核对了可访问的原文 HTML 方法段和适用范围；第六项核对原始摘要。没有把未读取的附件、开源代码运行或论文全部数值实验复现写成已完成。以上 arXiv 版本均为明确核对入口，不自动声称是所有作者目前最新期刊文本。

## 3. 扩展文献和不选作首轮主线的理由

| 文献 | 方法定位 | 为什么不是本轮主任务 |
|---|---|---|
| **DeepONet Based Preconditioning Strategies For Solving Parametric Linear Systems of Equations**；[arXiv:2401.02016](https://arxiv.org/abs/2401.02016) | 学习逆作用或利用 trunk basis 构造子空间预条件 | 可比较“逆作用”和“基空间”两种角色，但再做固定低维基不够区别于旧Task042 |
| **Blending Neural Operators and Relaxation Methods in PDE Numerical Solvers**；HINTS；[arXiv:2208.13273](https://arxiv.org/abs/2208.13273) | 神经算子修正与传统松弛混合 | 有助于理解不同误差成分互补；不是网络直接消灭所有迭代和离散误差 |
| **Fourier Neural Solver for large sparse linear algebraic systems**；[arXiv:2210.03881v1](https://arxiv.org/html/2210.03881v1) | Fourier/学习误差修正与迭代结合 | 本项目高阶FE系数不在规则标量图像上，不能按自由度编号做FFT并宣称物理等价 |
| **MGCFNN: A Neural MultiGrid Solver with Novel Fourier Neural Network for High Wave Number Helmholtz Equations**；[ICLR 2025论文页](https://openreview.net/forum?id=ThhQyIruEs) | 多层和 Fourier 神经修正 | 作为后续结构比较来源；本次只核对论文页/摘要，不把其具体实现或向量边界处理当成已审代码 |
| **NOWS: Neural Operator Warm Starts for Accelerating Iterative Solvers**；[arXiv:2511.02481](https://arxiv.org/abs/2511.02481) | 先由网络给初值，再由传统方法收敛 | 是另一种NN角色；用户希望探索迭代机制，且已有旧线校正研究，不把初值预测设为第三主线 |
| **A Fully Matrix-Free Three-Grid Preconditioner for the Time-Harmonic Maxwell Equations at Extreme Scale**；[arXiv:2608.22903](https://arxiv.org/abs/2608.22903) | 非神经、matrix-free的Maxwell多层路线 | 保留为传统方法对照设计参考；本次仅核对摘要，大规模多GPU硬件记录不是笔记本资源承诺 |

扩展表中除 FNS 的方法 HTML 外，以原始论文页/摘要为检索级核对；Codex若实际采用公式/实现，必须进一步阅读对应方法和代码许可并注明版本。不要用综述/宣传摘要中的性能倍数替代本地测量。

“Neural Solver Selection”可能也指组合优化/TSP的求解器选择，不应仅因标题含 solver/selection 就迁移到 Maxwell。本次没有唯一确认用户记忆中的原论文；Meta-MgNet、Wave-ADR-NS以及自适应粗空间数量预测是三个不同候选解释，不冒称找回了唯一原文。

## 4. 三个概念应当分开

**神经直接解映射**：由几何/介质/激励直接输出场或观测量。对本任务，输出看起来合理并不能代替原方程与离散精度检查。

**学习迭代算法**：网络学习每次残差修正、松弛系数或多层传递；展开后仍有原方程作用、矩阵向量乘、残差和停止准则。整个流程可被表示为一个可微网络，但不意味着无需 FEM 或数值验证。NN-V3的N/N-safe属于这一类。

**神经预条件器**：网络提供修正或搜索方向，外层Krylov选择组合。NN-V3的P属于这一类。非线性或可变PC需要匹配的灵活外层方法；[PETSc KSPFGMRES官方文档](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)明确区分了普通GMRES和FGMRES对PC的要求。本任务首轮刻意把残差路径做成固定复线性，FGMRES作为共同外壳，不把这称为普适收敛保障。

## 5. 从论文到本项目的必要改造

论文中的结构化 scalar stencil 必须变成明确的 FE trace/单元图映射。原 FE operator、约束、局部矩方向、端口和内部恢复保持准确；只有 preconditioner/latent correction 可以近似。粗层通道没有自动的H(curl)意义，必须用原方程评价其实际效果。

学习模型必须区分对介质的非线性和对残差的线性；复问题还要区分实线性与复线性。只在 setup 做网络计算可以降低重复开销，但 setup缓存、训练激活与多层图同样可能很大。必须实测并计入全流程，而不是从参数量直接推断容量。

主研究对象仍是有限资源下一个新0.7nm问题，不是无限多次查询摊销。借鉴论文的数据和训练方法前，先估计获得训练样本、算子作用、反向传播和验证的代价；不预先要求昂贵准确解来训练一个声称为昂贵准确解提速的模型。

本轮选择、资源、测试和晋级规则以 [task.md](task.md) 为准。下一轮是否做策略网络、Krylov-aware微调、更多传播方向或新的多层结构，应由当前证据定位，而不是继续堆叠论文名字。
