# Review V8：接受 p4 authority，开展全参数阻尼 Gauss–Newton 与 p5 精度续审

## 0. 决定、身份和本批消除的 blocker

**接受 Response V8 的等价装配、p4 准确参考、完整 plain/phase 对照和负结果。相位表示改善了有限场近似，但没有把原 p3 方程求合格；p3/p4 又显示约百分之一量级的离散敏感性。下一批不简单延长原 Adam/L-BFGS，不回到冻结末层续扫。授权两个独立工作流：A 续审一次 p4/p5 精度；B–E 用同一无标签 Adam500 起点，改为全参数、matrix-free、带阻尼与可选低秩内层预条件的 Gauss–Newton，对照后按需要自动做隔离诊断。工程故障先修复，单项受阻不结束整批。**

本批对应的 blocker 是：（1）可靠参考的离散精度尚不充分；（2）已有相位表示下，原残差优化没有转化为准确解。A 是准确性基准审计，B–E 是训练方法研究；不能互相替代，也不能用 p 误差解释 NN 未解出同一 p3 方程。

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42extra_feinn_5nm
worktree                   = /home/fenics/Projects/NN-Lab-V2
review_date                = 2026-10-01
reviewed_HEAD              = 52e65aa24de3c22ae9af1ae42d25706cf51b395c
latest_commit              = docs(task42extra): bind V8 actual rendered view and final resource ledger
latest_commit_UTC          = 2026-09-30T23:45:24Z
original_base_SHA          = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
previous_review            = review_report_v7.md @ cee68ef5e8219858e3a9b733ffe454334683836b
response_reviewed          = response_v8.md
V8_C_D_source              = bc052a3744528277f00a7a9a5566aa4a6d7393ed
V8_p4_reference_source     = d0b82d7a165be89d9fa90b03be3151db9a9c3869
next_batch                 = V9_P_LADDER_AND_MATRIX_FREE_DAMPED_GN
response_required          = response_v9.md
new_batch_budget_seconds   = 43200
solver_production_merge    = NOT_APPROVED
```

最终目标仍是约 2 TB 整机内存内，真空波长 0.7 nm、周期单胞内任意非可分三维 Maxwell 的准确、稳定、可复现计算。当前是 5 nm 小型 M5 研究。小规模直接法只作 authority；NN、Gauss–Newton 或本批低秩辅助均不自动构成可扩展的 0.7 nm 生产方案。通用 Full3D 的分布式、matrix-free、可扩展 iterative 主线不变。

本次审阅通过 GitHub 读取当前分支、完整任务目录清单、最新 response/summary、authority、训练与公平记录、run/resource 索引及相关源码，核对前次 review 后的 8 个提交。未改动 task/规则及旧 review 以当前 blob 与此前全文对应；最新 Review V7 的本地完整副本与远程 blob 核对一致，未发现额外补充合同。没有 SSH 实测或下载工作站 ignored 大数组。本文 measured 指仓库已提交记录；公式、计数与建议分别是推导和 not_run，不是新的 M5 测量。

本报告明确允许：一次 p5 authority；同任务 C/D 的限定无标签/有标签阶段边界复用；新 GN/内层 CG/低秩参数预条件；相应失败后的有据修复和恢复。覆盖以前对此操作的禁止，但不修改旧 task、review、response、失败费用或 qualified 字段。先读根/目录 AGENTS、[仓库原则](../repository_work_principles.md)、[task](task.md)、历次 review、[Response V8](response_v8.md)和本报告。

## 1. 最新结果及不能跨越的结论边界

依据：[p4 与 p 比较](outcomes/authority_recovery_v8.md)、[相位完整试验](outcomes/phase_feinn_v8.md)、[公平记录](outcomes/records/common_work_comparison_v8.json)、[资源账](outcomes/records/resource_costs_v8.json)。场误差相对原同 p3 参考；候选功率均 diagnostic。

| measured | plain | phase | 审阅判断 |
|---|---:|---:|---|
| C：4000 次计费 closure 后 native 残差 | 1.055409537 | 1.319288666 | 均远高于 1e-6；phase 未改善终态原残差 |
| C：散射 E L2 / curl 相对误差 | 0.998945 / 0.998966 | 0.213467 / 0.214539 | 相位显著改善场近似，仍非求解合格 |
| C：独立能量闭合绝对差 | 0.4156885892 | 0.0270002712 | 均高于 1e-5 |
| D：1500 closure 的 G / 散射 E / curl 误差 | 0.0250916 / 0.0257295 / 0.0250753 | 0.0104089 / 0.0100572 / 0.0104176 | phase 更容易拟合；三项仍未均小于 0.01，不放宽阈值 |
| C 完整 launcher wall / s | 9294.134800 | 8747.323512 | 未达到相同资格，不能据此宣称方法提速 |

接受相位/完整矩/VJP/非单位 Floquet/求积/标签隔离的已测资格；不把有限样本检查称为消除了所有实现错误。C 与 D 分属无标签原方程训练和监督拟合，不能把 D 权重回流 C。原 `PHASE_RESEARCH_SIGNAL=false` 保留，同时如实记录相位的有限场改善。

p4 已取得 75264 独立复 FE、40 端口的合格原方程参考。native/augmented 约 4.29e-12，独立 DOLFINx total 约 4.35e-12，体吸收闭合约 1.11e-12。原慢路径在已有缓存下 form/JIT 约 0.00168s，MPC assemble_matrix 300s 未返回；内部原因仍 unknown。等价装配完成后一次 p4 参考 launcher 约 57.86s，树 RSS 峰 3.62GiB。**以后不再重跑旧 MPC 装配长超时来证明同一瓶颈，也不重求 p4 来补日志。**

p3/p4 的散射 L2/curl 差为 0.0149860/0.0190206，R 差 0.00372680；两者都能非常准确地满足各自方程和能量，却仍有明显场差。因此 p3 只作已固定的代数研究基准，p4 是更高阶的 best available discrete reference，不是连续精确解；h 和端口截断仍未资格化。

当前 summary 把 V8 追加在文末，页首仍是 V7 的 blocked 历史。新交付应在最前加“当前 V9 结果导航＋V8 已关闭事项”，不删除或改写旧段，避免读者把历史 p4 未完成误当现状。源码 `d_G` 未单独落盘的 V8 事实保持；新 GN 运行必须保存实际标量，不能回填为历史实测。

## 2. 一批做完的依赖与自主修复

```text
共同身份/资源/既有数据
  ├─ A：p5容量/跨阶资格 → 准确参考 → p3/p4/p5对照
  └─ B：JVP/VJP/GN与边界资格 → C：plain/phase无标签GN
                              └─ D：需要时同方法的监督诊断
所有实际终态 → E：独立物理检查、公平成本、下一步判断
```

逻辑独立不表示并行占用硬件，数值阶段仍串行。A 未完成不阻止原 p3 上的 B/C/D。C 一条失败继续另一条；只有共同算子、ABI、身份或安全失效才暂停共同依赖。可做的独立测试、代码与文档继续完成，不以一个 import、schema 或渲染问题结束整批。

每个可定位工程根因允许最多 3 次有改动证据的修复重试，记录 `failure → hypothesis → change → test → retry`；不原样盲重启。每条 C/D 最多 2 次故障恢复，恢复时间/已计算子工作继承。数值停滞不是 bug；GN 的阻尼、内层预条件和 Cauchy 备选按第5节自动处理，不临时改 loss、学习率族、网络或精度标准。p5 numeric 最多 3 次有据尝试，成功一次后不再分解同题。

缺索引先用本任务原 manifest/副本和 hash 恢复，不扫描其他项目。损坏检查点不能伪造；允许按第4节重建无标签 Adam 前缀。权限/ABI/换页/监督/资源硬线失败先停止自身受影响树，不改邻任务，不绕过安全策略，不无限等候抢跑。

## 3. A：一次 p5 authority，延伸而非重置 p 序列

### A0：冻结范围与容量

仍为 M5：5nm Si/air，原三维缺口、384 hex/h1.25nm、1° grazing/phi0/s、双 Floquet、完整40端口、体/DtN q15。唯一改量 p4→p5；原 p3/p4 解均只读复用。沿用 V8 已核验的独立积分和等价装配；扩展通用 degree 参数，不复制每阶一套大 runner，不再用慢 MPC 双线性装配作默认。

p5 的推导数量：边6240、面48000、内部92160，独立复 FE 合计146400，加端口146440行；局部540维。原始全cell 540×540 complex128直展约1,791,590,400B，仅为 derived payload，不是 RSS/factor。准确消去单元内部后预计54240个 trace，加40端口为54280行。现场核实，不为符合推导而删自由度。

在任何大数组前同时估算局部张量、端口、COO/CSR排序/复制、PETSc转换、factor及后处理重叠。仍取12GiB内部保守准入、16GiB整树停止线。**优先选择有资格的准确 assembly-time static condensation，或在完整预估可容纳时采用全系统直接法；不先分配已知超线的全 CSR 再等 OOM。** 局部消元允许复用同类单元因子，恢复保留完整 FE/端口效应，不引入 shift、低秩物理近似、降积分或截断。

### A1：最小新资格与求解

只测 p5 新增部分：小网格 p4→p5 非零复场嵌入、公共点 E/curl、orientation/MPC；小型凝聚与未凝聚系统等价；M5 p5 独立积分/A/A*与非零内部/端口配对。操作归一差≤1e-10。独立积分不能读取装配使用的同一 F 表作为“独立”依据；明确共同 Basix/几何/材料输入。

装配/CSR/rhs或凝聚恢复packet先落盘，symbolic 后真实 factor/workspace 估计准入。native、增广和独立 total 原残差各≤1e-10；恢复/MPC≤1e-10；独立体吸收能量/吸收一致性≤1e-5。solve→真残差→最小恢复packet→释放 KSP/PC/factor 和无用矩阵并确认 RSS 下降→后处理。全场恢复/验算分块，不把所有高阶表达式和两套大模型同时常驻。

p5 仅 `REFERENCE_ONLY`，`training_reference_allowed=false`；B–D 不读取它。若没有安全完成路径，报告 A 的实际容量/时间 blocker 并继续 B–E。

### A2：冻结后比较

比较 p4/p5 为主，复用 p3/p4 历史并可追加 p3/p5 的直接差值，不重求已有参考。公共积分点/兼容嵌入，后者须通过场/curl配对；不同长度系数不直接相减。报告 total/scattered E/H/curl、六点复场、四类40级复通道、逐级功率、R/T/A_balance/A_volume、R00_s/p/total和原材料/界面区域。

主分母是 p5 同量范数并保留绝对差/两边范数/近零自然尺度；不拟合整体复相位。沿旧 p 审计门限：主要场/复样本/通道≤1e-3，功率差≤1e-4，区域单列；最多一次差值积分 q30 检查，不重求 PDE。比较不同 p 步的衰减时也给绝对差或统一 p5 分母，不能直接将分母不同的相对数值当收敛率。

三阶序列仍不证明连续、h、端口或几何泛化精度。允许 `P4_P5_SMALL_CHANGE_LIMITED`、`P4_P5_SENSITIVITY_OBSERVED`、`LOCAL_SENSITIVITY_REMAINS`；不自动 p6/h 加密。无论 A 的结论如何，C/D 的研究基准仍为原 p3，不偷换标签或算子。

## 4. B：从同一阶段起点比较，而非重复从零算500步

原 C 的 plain/phase 都从同 seed421001、同实参数与零散射开始，完成500次无标签 Adam 后才进入 L-BFGS。本批复用这两个**各自的 C-Adam500**作为新 GN 起点，保持参数/buffers/完整矩。这样只改变后续更新规则，避免重复已测前缀。

| C 起点 / V8原测 | 文件字节SHA256 | native / loss / 前缀wall秒 |
|---|---|---|
| plain，完整500边界 | e976d3e629c433c1f1dc6b7ae3c343acaa5dfa5cd948818231e93a3a9298f9a0 | 1.50462435428 / 0.448518766103 / 1097.641308126 |
| phase，完整500边界 | 07c77c468c175edc9455025651a058ac589f2313fc1f15d9b38c3c6628daffae | 1.11442009288 / 0.365338941649 / 1144.848724030 |

从 V8 `checkpoint_index` 找到唯一文件并核对上表、参数顺序、阶段、计数、source、labels和对应 `c`。不是 V8-D 的有标签 Adam500，不是 V4/V5/V6或 best/last_trial。元数据 `used_for_initialization=false` 是历史事实；本review仅为同一原p3非生产试验授权这个边界复用，不改旧文件。

加载模型和buffer，重算完整c、loss和原残差与历史配对≤1e-10（原残差按记录有效位容差），重新建立本路线 fresh Gram 因子；本批保存实际 d_G、Gsolve真残差与全部费用。GN 不继承 Adam/L-BFGS 动量或历史，不声称“精确恢复L-BFGS”。标 `initialization_kind=PDE_ONLY_ADAM500_PREFIX_REUSE`、`inherited_Adam_updates=500`、`new_Adam_updates=0`。

若该固定点字节丢失，先找有 hash 的本任务保留副本；仍缺失可从原 seed/原实现无标签重算恰好500更新一次，与历史 c/loss/算子身份配对，所有新增费用照计。不改用终态或监督权重顶替；若不能等价，标起点未资格化，允许从零重建完整无标签路径但必须单列 `REBUILT_PREFIX_NOT_BITWISE_REPLAY`，不再宣称是严格相同起点的算法对照。物理身份错误不可这样绕过。

训练数据始终白名单：原p3 native/G/完整矩、对应 C 边界、固定物理相位。p3 reference、D模型、p4/p5解以及旧监督 Phi/Q禁止读取。

## 5. B/C：全参数 matrix-free 阻尼 Gauss–Newton

### 5.1 方法改变哪一步

当前目标不改。网络和完整 Nédélec 插值把8966个实参数映射为31968个复系数；记其参数导数为 J。Gauss–Newton 先计算“参数小改动将怎样改变原方程残差”，求一个受限制的改动，再用真实非线性目标验证。这与冻结隐藏层只解195个末层系数不同：本次隐藏层和末层全部可更新。

```math
r(\theta)=A c(\theta)-f,\qquad d_G=f^*G^{-1}f,\qquad L(\theta)=\frac{r^*G^{-1}r}{2d_G},\qquad J=\frac{\partial c}{\partial\theta}.
```

```math
g=\frac{\mathrm{Re}(J^*A^*G^{-1}r)}{d_G},\qquad
K_\theta v=\frac{\mathrm{Re}(J^*A^*G^{-1}A(Jv))}{d_G},\qquad
(K_\theta+\mu I)s=-g.
```

参数、s/v/g/K为实数意义，FE/端口为complex128，星号为共轭转置。`Re(g_c^H dc)`约定与原VJP一致，不漏实部、不多乘2。G仍为原正定FE残差度量，K为参数空间的半正定 GN 曲率；不得混叫同一个“Gram”。A虽然不定且非Hermitian，K的二次型仍非负；加正阻尼后可用实CG。**K不是一般非线性loss的完整Hessian，不可用“梯度差分必须等于K v”作错误测试。**

相关依据：[Jnini等的Gauss–Newton研究](https://arxiv.org/abs/2402.10680)、[matrix-free NGD及内层病态研究](https://arxiv.org/html/2505.11638v1)。这里只借用算法结构，不引用其流体/Poisson结果证明本Maxwell问题通过。后者也提醒：不形成矩阵并不保证CG快，故本批明确定义内层失败处理，而非任意扫描PC。

### 5.2 JVP/VJP和资源实现

新增 `Jv` 为参数方向导数，不是空间导数。优先用已安装CPU PyTorch的 `torch.func.jvp/functional_call`，只对网络和矩映射的torch子链求导，A/G仍走现有数组作用。可选用本MLP的解析切线传播作为等价fallback：线性层的切线包含权重/偏置方向和输入切线，tanh导数为1−tanh²；固定相位只乘一次。两种实现须配对，不用长期有限差分代替正式JVP。官方接口依据：[JVP](https://docs.pytorch.org/docs/stable/generated/torch.func.jvp.html)。不为接口升级环境。

沿用≤8cell分块；不把 `.numpy()` 或 `no_grad` 的旧forward直接套进自动微分而得到零JVP。冻结θ的一次CG内模型/buffers、相位和G因子不变。可在预算内缓存确定性的局部激活或固定几何来加速，但须与重算路径配对，并记录内存；不保留全网格AD图，不显式存31968×8966复Jacobian或8966平方K，不形成A*A或全局Maxwell逆。

本批C仍采用 `RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR`：每条新路线的全局稀疏G因子及setup/solve/释放全部计费。因此这里的matrix-free只指J/K和既有A作用，不是整套架构已无全局因子，更不是0.7nm容量证明。

一次 K v 计一次完整JVP、A、Gsolve、A*、VJP；每个内部批不能偷算为新完整一次，也不能把32方向matmat当一次以隐去代价。记录网络前向、JVP、VJP、A/A*、Gsolve、K-action、CG迭代、试探loss和审核的独立计数与嵌套时间。

### 5.3 必需资格

先小型非Hermitian复数线性/非线性模型，用显式实Jacobian构造对应K作为独立对照，测试秩亏、零末层、纯虚方向和阻尼。然后仅在两个真实C边界上作有界检查。

| Gate | 要求 |
|---|---|
| JVP | hidden/last/random三个非零实方向，中心差分h=1e-4/1e-5/1e-6；连续两档操作尺度相对≤1e-5 |
| 实伴随恒等式 | `Re(w^H Jv)=v^T VJP(w)`，至少3个复w/实v，操作相对≤1e-10 |
| K作用与对称/正性 | 小模型显式K配对≤1e-10；真实vᵀKw与wᵀKv相对≤1e-8；vᵀKv与(AJv)*G^-1(AJv)/d_G配对≤1e-8；明显负值不是可直接取abs的舍入 |
| Gsolve | 原真实相对残差≤1e-11，固定准确因子；记录实际d_G |
| batch1/8与输入冻结 | c/JVP/VJP/目标相对≤1e-10；探针不改变真实起点或buffer |
| GN与恢复 | 线性合成问题上实际/预测下降一致，阻尼解与显式solve配对；非线性拒绝步完整回滚；原子保存/中途加载后后续步骤一致 |

轻测试通过不能直接替代真实完整c/残差身份。JVP API故障可改解析切线或分块调用后复测，不重新安装栈。共同K/伴随资格失败不能进入C碰运气，但A与不依赖K的交付继续。

### 5.4 固定的阻尼与接受策略

先用固定seed421901、6次幂作用估计初始K的尺度h0（不是条件数或严格谱界），有限正值才准入；μ0=1e-3 h0，区间[1e-12 h0,1e6 h0]。出现全零/不可分辨曲率先核验JVP，若真实驻点则报告，不加任意epsilon伪造通过。

每个outer在固定θ上用实CG近似解阻尼系统，初始s=0，真线性残差目标0.01×norm(g)，默认最多40次。内层未完全达标但s有限、gᵀs<0、预测下降为正时可进入真实目标试验，记录inexact，不把CG未达标直接当整批blocked。

```math
\mathrm{pred}=-g^Ts-\tfrac12s^TK_\theta s,\qquad
\mathrm{ared}=L(\theta)-L(\theta+s),\qquad
\eta=\mathrm{ared}/\mathrm{pred}.
```

只在ared>0且eta≥0.1时接受；eta>0.75令μ除以3，0.1≤eta<0.25令μ乘2，其余保持；拒绝步μ乘10并重算，参数不变。阻尼是局部步长控制，不加进正式L或物理方程。每outer最多8次阻尼试探，pred/ared用原真实目标，不用标签或最终验收字段选择步。

连续3次CG触及40次且真相对线性残差>0.01时，先触发第5.5节有界参数PC。仍无有效下降时允许一次Cauchy方向备选：s沿−g，用已计算K确定正的二次模型步长，再以1、1/2、1/4至多3档验证真实L。它仅是当前GN的下降保护，所有评估计费；不改网络或loss。如果仍不能接受，记录 `GN_MODEL_STAGNATION`、曲率/梯度/原残差，结束此路线后继续另一条/条件D。不要反复重置阻尼到初值来刷预算。

每路线最多120个接受outer、4000次K-action、8000次完整JVP+VJP合计、512次真实试探loss，且受第8节时间限制，取先到者。每5个接受outer及起末审核原native/augmented/total/port；严格原残差有希望通过时立即冻结进入独立审核，不以小梯度或optimizer success判PDE通过。

### 5.5 内层慢时的唯一预条件后备

这不是全局Maxwell PC，而是8966实参数空间的小辅助。触发时在当前固定θ上，以固定seed421902生成32列实高斯Omega，逐列计算Y=K Omega，经济QR得U；再计算T=UᵀKU并对称化、作小型eigh。保留数值正的方向，形成正交V和非负Lambda；只允许舍入尺度内的负特征值置零，显著负值先查K资格。秩阈值固定1e-12，零秩则跳过并记录，不扫rank。

```math
P=\mu I+V\Lambda V^T,\qquad
P^{-1}v=\mu^{-1}(v-VV^Tv)+V(\Lambda+\mu I)^{-1}V^Tv.
```

这是明确的随机range/Ritz低秩辅助，不冒称完整复现文献Nyström算法或其保证。一次建立最多64个K作用，基矩阵8966×32实数约2.2MiB（derived），不是整个训练RSS。每路线最多建立2次，记录setup费用；一次PCG内固定P，θ接受更新后可将旧P作为固定SPD辅助继续用，但不得称它仍是当前K的精确近似。下一次触发且距上次至少5个接受outer才重建。新PC建立后的内层上限可为80次；全K/时间预算不增加。

PCG用真实线性残差复核，PC的显式小合成逆/SPD测试先完成。不形成大K、不保存大Jacobian，不用G或A的全局逆假装这项小PC。PC有代码问题可退回已资格的无PC阻尼GN并继续；数值收益未证明，不承诺波长鲁棒性。

## 6. C：两条无标签GN与原L-BFGS公平比较

新路线为 `V9-PLAIN-DAMPED-GN` 和 `V9-PHASE-DAMPED-GN`。保持原p3 A/f/G、完整FE/端口、3×64 tanh/6输出/8966实参数、q15矩、单已知相位与FP64，只改Adam500之后的优化方法。

两条都使用同一GN/阻尼/触发规则，各自从第4节对应边界开始，内部串行。原V8的L-BFGS后段作为已有对照，**不为了表格重新跑两次长L-BFGS**。这不是新的盲测，声明 `benchmark_previously_seen=true`；参考不进入训练，`reference_used_for_training=false`、`features_reference_exposed=false`、`pde_only_solve=true`、`production_initialization_allowed=false`。

报告分两本账：（1）本批新增工作；（2）从零可复现实验路径的前缀归属＋本段setup/训练/审核。历史前缀只在全项目账计一次，但每条“从零路径成本”必须包含；本批fresh G因子也真实计入，不把旧因子看作仍常驻。禁止把GN outer与LBFGS closure等同，按共同累计wall窗口和A/A*/Gsolve/JVP/VJP等多维工作量列对照，不虚构一个通用等价closure。

主比较用最终committed和各自真实保存的共同时间之前最近committed态，给出时间差；没有对应物理审核写未记录，不插值造场。严格通过仍要求完整原残差≤1e-6、场/复通道≤1e-4、功率/能量≤1e-5、逐级功率≤1e-6、MPC/恢复≤1e-10。

研究正信号另列：同一表示、相同可比较累计时间内，相对V8至少降低native与augmented各10倍，且散射L2与curl均≤0.1、并优于对应V8同口径值，才记 `GN_RESEARCH_SIGNAL`。该信号不是严格PASS。只有loss下降、监督拟合改善或总场背景掩盖误差不算。每个实际冻结状态都要保存真实未过量，不能只报改进倍数。

本轮不把残差最小状态换成“最佳场”作为正式终态；最小native的已保存中间态可单列诊断，禁止利用参考场选checkpoint。C两条冻结及独立比较完成后，才启动D。

## 7. D/E：不收敛时自动区分训练与表示，不再停在一句失败

**D触发：C-phase未严格通过，共同JVP/G/数据资格与资源仍合格。** 对plain/phase各做一条 `V9-*-FIT-GN-DIAGNOSTIC`。复用V8-D各自恰好Adam500的模型边界；路径/hash从原D checkpoint_index唯一取得，并在新设计中冻结。严禁误用C锚点后声称同起点对照。D起点缺失可按原固定seed/原目标重建前500步并计费；不得加载V4多轮拟合权重或p4/p5标签。

D优化原监督目标，GN构造相应替换为：

```math
 e=c(\theta)-c_{\rm ref},\qquad d_{\rm ref}=c_{\rm ref}^*Gc_{\rm ref},\qquad
 J_{\rm fit}=\frac{e^*Ge}{2d_{\rm ref}},\quad
 g_{\rm fit}=\frac{\mathrm{Re}(J^*Ge)}{d_{\rm ref}},\quad
 K_{\rm fit}v=\frac{\mathrm{Re}(J^*GJv)}{d_{\rm ref}}.
```

这里不调用A/A*或Gsolve做训练，只有G乘法和JVP/VJP。与C使用同一阻尼/接受规则，最多60个接受outer、1000次K作用、2500次JVP+VJP、256次试探loss及每条1h逻辑路径时间；PC后备每条最多建立1次，setup工作计入。三项G/L2/curl均≤1e-3为表示正见证，均≤1e-2为部分；不改阈值。

D保持 `reference_used_for_training=true`、`features_reference_exposed=true`，PDE-only/production initialization/official固定false。D的全部权重/方向/标签不得回流C、Task042或新物理问题。条件未满足跳过D，不为跑满预算做训练；C共同数值错误不靠监督拟合掩盖。

E对C/D实际终态独立ML重建q15完整c，并用q30复核≤1e-8；FE compare-only读取原p3参考，重算total/scattered E/H/curl、六点复场、四类40通道与分母、逐级功率、R/T/A/A_volume/R00、材料/界面区域与全原残差。不重求p3/p4、不新建Maxwell因子作候选fallback。独立代码验算不等于未知测试数据；p5只属于A，不更换评分基准。

最终至少区分：有效GN下降但仍未合格；内层线性求解成本主导；真实目标与局部模型不一致；出现可信驻点但仍非PDE解；监督可拟合而PDE困难；两类目标都未取得足够表示。一次D失败仍不是数学表达极限。根据实测给一个下一步建议，不自动新增载波/宽度、VarPro、其他loss或新PC扫描。

## 8. 时间、内存、保全与精确计费

本次新增12h=43200s执行预算，不借用V8未用时间叠加。V8最终旧累计74341.02060587064s、其中V8为25333.743970519048s；旧失联3284s及全部重放/参考/Gram费用保留。新总账为旧账＋本批实际新增，历史未计尾段如有再补，不追改旧结果。本批是研究成本，不是0.7nm生产用时。

| 子包 | 新增有载/辅助分配上限 | 条件 |
|---|---:|---|
| A：p5资格/准确解/比较/修复 | 7200s | 不让高阶参考吞掉NN预算；单次长阶段≤3600s，可保存分段 |
| B：GN/JVP/PC/边界资格 | 3600s | 最小定向测试与必要M5探针；不full pytest |
| C：两条PDE GN | 合计21600s | 每条逻辑路径≤10800s；包括继承Adam前缀和新setup/训练/保存 |
| D：条件两条FIT GN | 合计7200s | 每条逻辑路径≤3600s；继承/重建的D-Adam前缀同样计入 |
| E：独立验收/修复/交付辅助 | 3600s | 至少保留1200s，不挪作候选续训 |

C默认新段有效时间上限为10800减去对应已测前缀wall（plain1097.641308126、phase1144.848724030）；前缀不是本批新增费，但计入逻辑路径公平预算。D从其实际旧记录计算同理。若前缀重建，实耗与历史归属不得双计为同一段运行；逻辑路径按实际重建耗时计算并明确非逐位回放。共同时间比较必须反映这些差异，不为了方便统一减500秒。

未用时间可事先登记转给本批已有的工程修复，不能突破C/D各条公平上限或新增未授权数值扫描；始终预留E。达到一条上限只关闭该路线，继续独立工作；正常预算收口不是中断失败，更不代表应无限延长。

工作站原生Linux、CPU-only、MPI1、数学/Torch线程1、DataLoader0，每阶段现场选空闲物理核并避开邻SMT，不擅自增加线程。数值树warn12/hard16GiB，factor内部12GiB规划，轻tests/浏览器≤2GiB、自身swap0、无OOC。系统保留max(128GiB,10%effective total)＋至少384GiB邻增长＋本任务预算；free disk≥50GiB、当前任务artifact总量≤20GiB。不得删旧负结果凑空间或改邻任务环境/进程/锁/affinity/watchdog/global BLAS/CUDA/swap。

沿已有持久launcher＋watchdog＋worker；实际physics/discretization/operator与新锚点hash在worker前绑定。launcher单调时钟包括导入、Gram/PC setup、参考装配、保存和审核，至少150s前停止新增长工作、保留至少120s收口。长原生调用受watchdog截止覆盖。没有委派cgroup就如实用约0.5s整树采样，tmux管理开销单列，不称连续内核上限或零干扰。

每个GN接受边界同步原子保存模型/buffers、mu/h0、各计数/预算、RNG、PC构造来源和可重建信息；拒绝试探独立，不能覆写committed。最后两代、阶段锚点、审核点及final保留；重建PC也计入恢复费用，不保存未冻结的可变引用。SIGKILL只保证此前已落盘状态；断连先核对同一任务PID/start_ticks/锁，不重复启动。安全停止优先于最后审核。

## 9. 实现、发布与 Response V9

只在本 canonical linked worktree/执行分支工作。先核对无活跃自身run，再安全fetch/ff；共享origin.fetch不映射本分支时用命令级精确refspec和显式tracking ref，不改共享配置、不reset/stash/amend/强推、不merge master或其他分支。

数值核置于src/solvers，优先新增可复用的参数JVP/GN/阻尼CG组件，复用现有CompleteMomentMap、phase、ResidualMetric、准确G、检查点、authority装配/独立积分和compare-only。stage runner仅编排，不再复制每条大训练器。允许为正确计时/白名单/恢复作局部修复，普通solver和旧任务数学默认不变；FE进程不顶层import Torch，不重装环境。

建议输入，在实现/资格化并clean commit后按依赖串行执行，每项仍为一次明确run：

```text
v9_p5_checks.dat
v9_p5_reference.dat
v9_p_ladder_compare.dat
v9_gn_checks.dat
v9_plain_gn.dat
v9_phase_gn.dat
v9_gn_reconstruct.dat
v9_gn_compare.dat
v9_plain_fit_gn.dat       # 条件D
v9_phase_fit_gn.dat       # 条件D
v9_fit_gn_reconstruct.dat # 条件D
v9_fit_gn_compare.dat     # 条件D
```

目录为 `input/task042extra_feinn_5nm/`。长阶段使用 `python scripts/launch_task42extra_durable.py <one-run.dat>`，包装选择已安装FE/ML环境并调用 `python scripts/run_case.py <one-run.dat>`。先扩展明确白名单，不用旧输入绕过新准入；每阶段清场后才下一阶段。源代码先clean commit再run，新attempt/index不覆盖V1–V8；修复source、运行source与最终文档HEAD分别记录。

至少交付 `response_v9.md`、`outcomes/p_ladder_v9.md`、`outcomes/damped_gn_v9.md`；records包括campaign_design、prefix_identity、p5_authority、p_ladder_comparison、gn_checks、inner_solver/PC计数、trial/accepted compact history、PDE与FIT对照、repair_log、run_index、gate_decisions、resource_costs。保存全部主provenance文件与source/input/model/材料/网格/模式/G/锚点/检查点hash，大数组仍ignored。新d_G/h0/mu等实际标量落盘，历史缺项保持缺项。

summary首页增加最新状态导航，V9追加并保留历史；同步progress、模型总账、test_summary、changed_files。checker从原数据重算严格/研究/表示/离散/资源各类判定，不只读status，也不把监督拟合升格PDE-only。

本review发布端的本地结构/合成代数检查不是M5资格，GitHub原文返回不是浏览器视觉检查。Codex只补查新review和关键新页的实际渲染，失败单列，不以文档样式阻塞数值工作，不批量重复渲染所有历史页。

完成授权矩阵或真正用尽安全/阶段/总预算后，再提交推送 `HEAD:refs/heads/task42extra_feinn_5nm`，报告准确HEAD、显式tracking/ahead-behind、worktree和清场状态，停止等待review。禁止自动p6、h细化、端口扫描、多载波/更大网络、目标尺寸5nm或0.7nm；本批结果无论怎样都不自动merge。
