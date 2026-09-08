# Task39extra Review V2：完整 S6 连续排布复核与三方向联合修正

## 0. 审阅身份与裁决

```text
repository                = Rookie1234567/MyFEniCS
branch                    = task39extra
review_date               = 2026-09-08
reviewed_HEAD             = 2b4de1b8802c4702c1abc8e998952a1b7dc3e110
original_task_base        = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
previous_review_response  = review_report_v1.md / response_v2.md
last_formal_LIGHT_source  = cbf56e87e515ab0c3fc5756cb6cf52feb047f610
future_stop_fix_source    = 597546311feea60d61acb2a9999b706dd895dcf0
response_required         = response_v3.md
execution                 = F0 -> F1 -> conditional F2 -> conditional F3 -> F4 -> F5
mandatory_review_stop     = F5 or unresolved common correctness/safety blocker
production_default        = unchanged
master_merge              = NOT_APPROVED
5nm/0p7nm/workstation_PDE  = not authorized in this batch
```

**本轮消除的 blocker：当前准确 p4 中间逆已经能运行，但完整 PC 的成本与方向组合仍不足以使原始 p6 问题实用收敛。只补查一个具体的等价提速机会，并按条件检验一个三方向联合修正，不继续无限更换 PC。**

最终目标仍为约 2 TB 整机内存内的 0.7 nm、complex128、Nedelec H(curl)、双 Floquet、开放边界、任意非可分三维周期单胞。当前仅在约 16 GB 本机、13.5 nm 上执行。

本轮用户明确同意再试一次。本 Review 前瞻性授权下文的有限连续批次，替代 V1 的 R6 停止后不得继续比较的限制；不改写 task.md、V1、response_v1/v2 或历史 raw。分支保持 task39extra，不建新分支，不修改 master。

审阅结论：接受已提交成本和负结果的限定解释；完整 solver 仍 NOT_QUALIFIED。此次只读核对远程文档、结构化记录和相关源码，没有重跑 PDE，也没有读取全部 ignored raw。Response V2 中“文档待提交”的语句是写作时状态；已提交远程身份以 reviewed_HEAD 为准，本地 worktree 是否干净仍须 Codex 启动时核对。

## 1. 本轮依据：哪些已确定，哪些仍是假设

证据入口：[当前 summary](outcomes/summary.md)、[Response V2](response_v2.md)、[成本报告](outcomes/cost_and_contribution_v1.md)、[紧凑记录](outcomes/records/cost_and_contribution_v1.json)。时间单位 s，内存十进制 B；本表是历史 measured/derived，不是新实测。

| 已测事项 | 结果 | 决策边界 |
|---|---:|---|
| 原完整 S6 PC 同机中位 | 22.0213867295 s | 原实现基线，不是每个问题的通用标准 |
| R1 等价原型中位 | 74.8708934441 s，原基线的 3.3999 倍 | 作用等价通过、性能失败；不说明所有等价优化无效 |
| 8 单元连续排布诊断 | 0.152499587 → 0.036731375 s；误差 1.38e-15 | 相对慢原型的组件收益，不是完整 S6 的收益 |
| R3 LIGHT 完整 PC | 582 次，中位 10.2938923936 s | H6–p4–H6 已更便宜，但不是原 S6 等价加速 |
| R3 最后安全结果 | 第 576 步，原 A6 真残差 0.0791360407785889 | 目标 1e-6 未达；第 582 步 reported 不代替停止时真残差 |
| R3 原 p4 参考解 | 583 次，最大残差 7.0581639701e-11 | p4 已解准，不再提高精度或增加内层步数 |
| p4 修正统计 | MR 后 rho 中位 0.981889；563/582 的单位步长 rho>1 | 不允许强制 alpha=1，也不能据此认定 p4 空间完全无用 |
| R3 资源 | RSS 3352014848 B；cap 8588566528 B；swap 0 | 当前主要限制不是内存耗尽 |
| 已完成的真实物理输出 | not_run | 没有正式 E/H、R/T/A、体吸收及非可分结构资格 |

关键事实：完整 S6 的 `physical_equivalent_fast.py` 尚未使用后来 LIGHT 的 `contiguous_work=True`；这个缺口值得一次完整 PC 检查，但不保证能胜过原 FFCx 实现。R3 的准确 p4 方向通常被顺序 MR 大幅缩小，联合选权是待检验的解释之一，不是已经确定的唯一根因。

## 2. 只允许两个候选，明确连续执行顺序

| 阶段 | 内容 | 后续，不在小阶段停审 |
|---|---|---|
| F0 | 核对已有运行、身份、raw 和停止修复 | 完成后直接 F1，不重写历史综述 |
| F1 | 完整 S6 的唯一 packed 等价版本，短的同输入对照 | 相对原基线提速至少 25% 才 F2；否则直接 F3 |
| F2，条件 | packed S6–p4–S6，原始模型零初值完整求解一次 | 数值及输出通过就 F4；仅性能/算法不足则 F3 |
| F3，条件 | 固定 LIGHT 的三个方向联合选权，原始模型完整求解一次 | 通过就 F4；失败就 F5，不再增加第三候选 |
| F4，条件 | 成功配置直接用于同尺度非可分三维模型一次 | 无论结果如何均 F5，不针对结构重新调参 |
| F5 | 统一证据与 response_v3.md | 集中审阅；剩余预算不是新增运行许可 |

F2 达到真实残差但输出实现失败时，先修复同一解的恢复，不重跑求解；真实物理 Gate 失败要查共同方程/后处理/离散，不能假定换 PC 能修正。共同 A6/A4、输入、映射、残差身份或资源监控不可信时停止受影响工作，而不是沿条件跳到下一 PC。

**最多两场原始完整求解加一场非可分挑战。**本轮不新增 h5 full solve、fine direct 控制、5 nm 或 0.7 nm PDE；已有 matched reference 可只读复用，缺失写 AUTHORITY_LIMITED。不再恢复未修改的旧 S6、旧 LIGHT 或 continuation 长跑。

## 3. 冻结物理、离散与资源身份

沿用 [task.md](task.md) §3 和 [Review V1](review_report_v1.md)：13.5 nm、grazing 1°、azimuth 0°、s 入射、幅值 1；50×25 nm 周期，z=-10…130 nm；原始 grating/materials；p6/h10 affine hex；完整 dual Floquet、80 DtN modes、原 quadrature。原 p6 独立 rows=164592，存储 rows=173802；p4 独立 rows=48960，增广参考矩阵 rows=53164。

```text
physical_model_sha256 = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
mode_manifest_sha256  = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
```

最终始终求原 A6 u=b；P64、P64^H、A4、材料、负质量项、DtN 均不改。p4 继续用一次 MUMPS symbolic/numeric 后反复回代，每个 RHS 用原 A4 显式检查相对残差<=1e-10。增广参考是准确实现 A4 作用，不是全局 p6 direct PC，不显式求逆。

新 profile 建议固定为 `a2r_packed_equivalent_v2`、`light_p4ref_jointmr3_v2`，写入独立 `.dat` 与 resolved config；新 input SHA 重新计算，不能硬填旧 input hash。正式入口仍为 `python scripts/run_case.py input/path/to/case.dat`；一个 dat 只表示一次明确计算。ordinary default 不变。

全部运行保持 MPI1、complex128、已资格化同一 Linux/WSL ABI、线程数 1。不升级 BLAS/MPI/PETSc、不换硬件后把收益归于 PC。p4 全局 factor 仍是诊断依赖；通过也不宣称 factor-free、波长鲁棒、2 TB 容量或任意所有结构通过。原底层小 factor 的 4096 rows/512 MiB 限制继续有效。

## 4. F1：只补查已有 packing，禁止扩展成新的优化项目

packing 是把局部实部/虚部整理成连续内存再运算，不是降低精度。仅在现有 S6 等价实现的 B6 和 PC 内部 split A6 volume 内启用已有 `contiguous_work=True`，batch_size 保持 8。原始外层 A6 和显式真残差 authority 保留原实现。

保留同一 setup 已生成的对角、power10 seed/window、Chebyshev degree3、P63/P31、p3/p1 矩阵及 factor、P64/A4、三个顺序 MR。不得重新估计窗口后称为等价，也不得减少平滑次数或把 S6 换成 H6。固定材料/几何信息可复用；每次变化的输入、ghost、约束相位相关值必须更新。

同一 parent 的一次共享 setup 中，在原路径和 packed 路径间切换对照；资源或既有 API 不允许共享时最多两次构建，并记录原因。输入最多三个：归一化物理 RHS、由合法 checkpoint576 primal 在当前原 A6 上重算的残差、seed3902 的合法复向量。checkpoint 不可取得时不编造，使用其余输入即可；不为补齐三个输入另跑 PDE。

两路径各最多 7 次完整 PC 调用，其中首次只标记预热，其余按相同输入配对计时。原始规模对照总计不超过 16 次 apply、2400 s（含构建和失败尝试）。复用现有 profile/comparison runner；不用旧 74.87 s 作为速度分母，也不能只用历史22秒代替必要的同机基线。

| Gate | 通过条件 | 未通过后的动作 |
|---|---|---|
| 同输入 action/transfer | relative<=1e-11；零/近零另报尺度化绝对差 | packed 路径明确修错最多一次；仍不等价就停用它 |
| 完整 S6 / PC | relative<=1e-8，且原 A6 作用于两输出的差可解释 | 不要求迭代轨迹逐位一致，不隐藏错误 |
| 稳定性 | finite、输入不变、slave-zero、orientation/复共轭正确 | 共同基础损坏则停止；仅新路径错误则恢复可信 LIGHT |
| 完整速度 | packed/原实现的配对中位比<=0.75，报告全部样本 | 进 F2；否则记 INSUFFICIENT，直接 F3 |
| 资源 | §8 安全上限，冷/热、表格/缓冲全记账 | 只属于 packed 的容量问题可跳 F3，共同 A4 超限则停止 |

这是一次窄范围补查，不扫描 batch、compiler、线程、backend 组合或再写一套 sum-factorization 平台。未过25%只表示本批次不继续投入这项等价优化，不等于数学算法无效。

## 5. F2：确有提速才重新检验完整 S6 组合

F1 达线后运行一次原始模型，zero start、准确 p4、原顺序三个 MR；首次32步是本次完整求解的一部分，不另设启动 screen。使用 §8 的统一预算，周期显式残差仍由原 A6 计算。

与原 A2R 比较共同的实测残差阈值和总耗时，报告 setup、PC、外层、监控、输出；不把 160 步的历史正信号当成最终收敛保证。若有明显同迭代残差退化，先审查等价与身份，不悄悄放宽容差。

通过则跳过 F3，直接非可分 F4。合法方程上预算用尽仍未通过，则直接 F3，不续跑、不增加 restart、不用旧解热启动 F3。所有旧负结果保持原状。

## 6. F3：唯一数学改动——固定 LIGHT 的三方向联合接受

### 6.1 它解决什么问题

原流程逐段选一个复步长；后面方向出现后，不再重新调整前面系数。新流程保留原来已经生成的三个候选方向，在这一次 PC 的末尾联合选三个系数，检查能否利用方向之间的互补、抵消关系。

**固定使用 R3 的 LIGHT/H6 作为方向发生器，不在 S6/H6 间再选一次，不比较不同生成顺序。** H6、连续排布 B6、对角/window、p4 reference、P64、原 A6 都采用已验证的 R3 定义。F1 的新 PC 内部快速 A6 不移入这个候选，保持其与 R3 的数学比较清楚。

### 6.2 三个方向必须按旧顺序产生

一次 PC 输入 q 是任意合法 p6 Krylov 向量，不一定是物理 RHS。令 r0=q。Q4 表示 P64 A4^-1 P64^H：

```math
\begin{aligned}
d_1&=H_6r_0, & w_1&=A_6d_1, & r_1&=r_0-\alpha_1w_1,\\
d_2&=Q_4r_1, & w_2&=A_6d_2, & r_2&=r_1-\alpha_2w_2,\\
d_3&=H_6r_2, & w_3&=A_6d_3, & r_3&=r_2-\alpha_3w_3.
\end{aligned}
```

alpha_j 使用旧一维复 MR，不强制为1，不按结果截断；输入或方向为零时沿用明确零规则。保存原顺序候选：

```math
z_{\rm seq}=\alpha_1d_1+\alpha_2d_2+\alpha_3d_3.
```

不得先做联合接受再重新生成后方向，也不得把三个方向都改由同一个 q 产生。这些是别的算法，本轮不授权。

### 6.3 只在末尾解三个未知系数的小最小二乘

```math
D=[d_1,d_2,d_3],\qquad W=[w_1,w_2,w_3],\qquad
c_*\in\mathop{\rm argmin}_{c\in\mathbb C^3}\|q-Wc\|_2,
\qquad z_{\rm joint}=Dc_*.
```

不构造大逆、不增加 p4 RHS、不更改外层 Arnoldi 算法；这不是对完整 MPGMRES 的复现声明。原顺序系数是本次三维系数空间中的可行点，所以在精确算术、未丢弃方向时：

```math
\|q-A_6z_{\rm joint}\|_2\le\|q-A_6z_{\rm seq}\|_2.
```

**该不等式只适用于同一输入、同一组三个已生成方向。不能由此保证后续外层更快或最终收敛。** 数值截秩后不再直接援引全空间最优性，按下一节的实际残差 safeguard 处理。

### 6.4 稳定实现与回退合同

非零 w_j 先按 s_j=norm(w_j) 归一化；用 w_j/s_j 做最小二乘，返回方向相应使用 d_j/s_j。使用稳定 QR，必要时对至多3列的三角因子做小 SVD；固定相对 singular-value cutoff=1e-12并记录，禁止扫描阈值。不得解 W^H W 正规方程以免平方放大条件问题。

MPI1 可用暂存 N×3 的薄 QR；这些是一次 PC 的工作列，不是新全局粗基库。不得构造 N×N/FE×mode 稠密矩阵。未来 MPI 分布式时必须采用分布式内积/QR而非 gather；本批次不实现新 MPI campaign。

复内积方向按本机 petsc4py 实际语义核对，至少用非实数系数测试。零列、rank1/2、近相关、zero RHS、缩放悬殊情况必须有清楚处理，不手动强制 rank3。有限系数求解退化可回退到已经保存的 z_seq；物理 action、p4 求解或输入出现 nonfinite/身份错误必须停止，不能靠回退隐藏共同错误。

每个新 PC 最多额外计算一次原 A6 z_joint，直接测量 joint residual；三个旧 MR 的 w_j 缓存复用。若候选非有限，或 joint residual 超过已存顺序残差加 `1e-10*norm(q)`，返回 z_seq并记录原因。该容差仅是浮点 safeguard，不是外层残差容差；显著或持续触发需要报告，不静默称联合成功。回退不重新执行 H6 或 p4。外层仍独立计算 A6z并按原规则核验真实残差。

每次 PC 的新增向量工作载荷限定在16个fine复向量以内，新增数组总预算<=64MiB（当前网格）；原/新峰值均实测。六个 D/W 列在173802存储行上约16.7MB只是 derived 下限，还要加 QR、残差和库工作区。工作区可复用，但旧方向不得跨 PC 累积；释放前不能仍被内层引用。

新 profile 的计数：H6=2、B6=4、p4 solve=1、旧方向 A6=3、联合核验 A6<=1；外层/monitor action 另列。联合求解增加的时间必须计入 PC，不能只报方向生成的耗时。

### 6.5 最小实现检查后直接求原始模型

一个合并的 tiny 代数测试批次覆盖复数联合系数、相关列、回退和输入不变；可以和现有真实 LIGHT 组件测试一起执行，禁止扩展为一串 p/h/source 资格化。原始规模前三次 PC 保留同输入 z_seq 与 z_joint 的紧凑比较，作为正式求解开头，不另跑一场训练/筛选 PDE。

第一次 full solve 就是原始 p6/h10、zero start。不得先用历史 checkpoint 续跑再 fresh，也不因少量 PC 的 rho 改善不够而禁止外层。结构正确但本次预算内未完成，记为该联合候选未资格化，不再换第二种权重、顺序或粗阶次。

每32步汇总：顺序/联合残差比、数值rank、最多三个归一化奇异值、系数和方向范数、fallback次数、额外A6/QR成本。不要只用系数绝对值判断贡献，更不能把583个不同RHS串成一条内层收敛曲线。仅 scalar summaries 入Git，完整向量保持ignored。

## 7. F4：成功后立即检验非可分三维，F5集中收口

F2或F3取得原始数值及输出资格后，直接采用 task.md §3.2 的同尺度材料缺口：原grating内满足中心坐标 x>0、abs(y)<period_y/4、40nm<=z<80nm 的cell改为air。保存 canonical cell keys 与实际材料实体，证明同时破坏y均匀和z挤出；选空或未破坏则修实现，不能挑更容易结构。

使用原始模型成功的同一 profile/参数/预算，zero start；按新材料重建 A4 factor、B6和窗口，不能复用旧材料数值。传递、周期、外部80 modes保持合同；新 physical/input SHA 独立记录。没有notch输入入口时完成原task范围内的最小接线，不将未实现当作准二维替代许可。

输出复 E/H、近场、R/T/A、A_volume、全部真实衍射级和复幅值，包括新出现的横向n不为0通道。通过只代表这一非可分case，不代表所有结构或连续极限。

原始与非可分通过则F5；某个共同物理/安全错误无法消除，或F3/非可分在预算内失败，也F5。没有阶段性停审，无需用户中途再选择参数。**如果这轮两个限定候选都没有产生合格原始场，停止本地 S6/H6+p4 的继续变体与延时，集中重新评估物理粗修正/细层互补机制。**这关闭的是本轮候选，不宣布全部物理多层或Full3D iterative不可能。

## 8. 运行预算、资源与退出

| 范围 | 上限/要求 | 说明 |
|---|---:|---|
| F1原始规模对照 | 2400s，最多16完整PC | 含setup、warmup和失败尝试 |
| 外层 | right FGMRES32，max_it2048 | 不加大restart，不扫描次数 |
| 每场 solve | 7200s | 与V1同上限，不因“还在下降”延长 |
| 每场 workflow | 10800s | 冷构建、factor、solve、释放、输出、checker全包含 |
| V2批次累计计算 | 36000s | 新账本，含测试/失败/重跑；不合并V1未用额度 |
| 正式 full solve 数 | 原始<=2，非可分<=1 | 首个原始通过便跳过第二候选 |
| 真实残差 | 原A6 <=1e-6；原A4 <=1e-10 | 不放宽，不用projection或shifted残差冒充 |

内存继续按有效RAM/cgroup与available扣`max(4GiB,15%有效整机容量)`余量，总cap不超过12,000,000,000B；实际可更低，不硬填上次8.59GB。动态余量、完整parent/MPI/compiler后代RSS、zero-swap、一次一个heavy全部保留。PSS另列，不把采样峰值说成连续严格上界。参考factor每次新材料仍需安全symbolic/numeric Gate。

停滞规则沿用V1：至少256步后，连续4个完整32步周期的真实残差比均>=0.99才受控停止。预算或资源先到则先停止；错误/nonfinite/用户停止优先。第一次失败保留原记录；只允许明确实现bug修复后针对受影响项重跑，且仍计入原数量/总预算，数学不成功不能标为bug。

复用5975463的合作停止修复，并最小扩展到本轮两个显式profile；不能仍只对旧LIGHT启用。每步reported、每8步或120s后的下一安全点保存真实残差/解，32步保留周期账本；不改变restart和Arnoldi空间。性能停止只请求应用安全收口一次，最多60s且仍满足安全cap，失败则全树硬停并保留last_safe。资源越线立即全树处理，不为保存越cap。

成功时保存最终解及hash，释放PC/KSP/p4因子和无用矩阵，实测RSS下降，再恢复/输出；异常时最小失败summary应先落盘，cleanup异常另列。不能将事后停止修复追溯成旧运行正常退出。

## 9. 物理验收、比较与状态

沿用 task.md §8：独立能量 `abs(R+T+A_volume-1)<=1e-5`，`abs(A-A_volume)<=1e-5`；finite、被动性、通道求和、canonical与同坐标E/H检查。相同离散matched reference的E/H和复幅值相对L2<=1e-4，R/T/A/A_volume绝对差<=1e-5，显著通道功率绝对差<=1e-6；近零项另报绝对误差，不拟合整体相位。

没有匹配独立数组则标 AUTHORITY_LIMITED，不伪造、不为了填表启动fine direct。小true residual不是p/h精度资格，R+T+A由定义闭合不是独立能量证明。未收敛场不产生official结果。外层reported/explicit同归一化差按已有Gate核对。

比较重点是实测 time-to-residual 与完整workflow。复用旧A2R/R3曲线，不重跑长基线；只对共同观测门槛报告时间，不对1e-6外推承诺。联合版本PC更贵但步数减少可能有价值；单步更快但更难收敛不算成功。

| 状态 | 含义 |
|---|---|
| PACKED_EQUIVALENCE_SPEED_PASS / INSUFFICIENT | 一次完整S6补查的结果，不等于solver通过 |
| JOINT_MR3_LOCAL_GAIN_ONLY | 同输入三方向组合有益，但没有完整物理解 |
| JOINT_MR3_NOT_QUALIFIED | 本候选未完成数值/输出/资源合同；不再自动改联合算法 |
| REFERENCE_ASSISTED_ORIGINAL_PASS | 原始p6方程及输出通过，仍含p4诊断factor |
| REFERENCE_ASSISTED_3D_PAIR_PASS | 原始及指定非可分case通过，精度/独立authority/扩展限制并列 |
| PERFORMANCE_CONTROLLED_STOP / ITERATION_BUDGET_EXHAUSTED | 预算内未完成，不等于永不收敛 |
| IMPLEMENTATION_BLOCKED / RESOURCE_BLOCKED / EVIDENCE_INCOMPLETE | 实现、资源、证据问题分别报告，禁止改写为数值否定 |

## 10. 代码、证据与提交

只修改现有通用kernel/profile/PC、必要dat/notch接线和停止路由；优先复用 `physical_equivalent_fast.py`、`fullspace_partial_assembly.py`、`fullspace_physical_intermediate.py`、`physical_light_setup.py` 与既有runner/monitor/checker。联合QR helper独立可测试，不再复制一个大型task runner。immutable旧profile含义保留，新行为显式opt-in。

建议普通提交顺序：packed显式版本及有限对照 -> jointmr3 helper/profile与停止接线（仅条件触发） -> 原始/非可分证据 -> Response V3收口。正式PDE前必须clean commit并绑定前后SHA；不amend、不强推、不改旧raw，不混入系统调优或无关重构。

每次计算保留原有 `input_original.dat`、`resolved_config.json`、`run_manifest.json`、input/physical/source SHA、`run_summary.json`，外加完整ABI、MPI/线程、mesh/tag/mode/parameter、resource与artifact hash。旧失败包含在历史，不删除或重写为通过。

本轮只增加一份中心结果说明和小JSON：`outcomes/packed_and_joint_mr_v2.md`、`outcomes/records/packed_and_joint_mr_v2.json`；同步summary、run_index、test_summary、workstation_handoff和两个项目总账。raw继续ignored，不再为每个子步骤增加平行报告。性能计时复用既有账本，不另造一套预算框架。

targeted测试合并运行，最终改动后一次task-focused回归；不因文档变化重跑PDE，不跑全仓测试来替代物理结果。工具缺失如Ruff应如实记录，不安装或谎称通过。Markdown用fenced math、表格列数和链接检查；静态/本地预览与GitHub可视核验分别报告，未看到网页就不声称渲染通过。

`response_v3.md`需给出每个条件为何进入/跳过，完整branch/base/final SHA、改动数值影响、实际运行/未运行、packed完整收益、联合rank/回退/额外成本与完整收敛、所有输出及参考限制、真实峰值/系统余量/退出、负结果、后续唯一blocker。不得只报测试数量或漂亮的单PC数字。

## 11. 收口原则

**这次只回答两个问题：完整 S6 的具体布局改进能否产生实际收益；现有三个方向是否能通过联合选权产生更有效的完整修正。不是承诺一定算通，也不是再次开放所有方法。**

若通过，尽快取得指定非可分场并准备工作站资格；若未通过，给出当前候选的成本和数值边界，停止本轮重复。0.7 nm必须继续走通用三维Full3D路线；2 TB会放宽容量，但不能代替有效的全局纠错、可扩展底层与精度证据。
