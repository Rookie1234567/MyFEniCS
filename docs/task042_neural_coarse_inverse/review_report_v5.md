# Review V5：V7 负结果审查与有界尺度／实现修正

## 0. 决定、身份与所针对的 blocker

**接受 V7 的材料、真实接口和固定配置负结果记录，但三条候选均不授予求解器资格。继续 Task042，不重新开启 p4 近似逆路线；本批只做一次对角变量尺度均衡 LSQR 对照，并修正优化器停机状态、等价优化神经 trace 前反向计算。不扩大网络、不增加载波、不续跑原两小时训练、不自动启动更大模型。**

要消除的不确定性是：当前 0.7 nm 单次神经 FE 试验中，变量尺度是否妨碍收敛，以及逐单元网络／矩映射是否消耗了不必要的计算时间。这是两个独立问题，分别验收；任何一个改善都不自动说明另一个已经解决。

```text
repository                  = Rookie1234567/MyFEniCS
execution_branch            = task42_neural_coarse_inverse
worktree                    = /home/fenics/Projects/NN-Lab
review_date                 = 2026-09-29
reviewed_HEAD               = c4fadde46978f2ba0ca3e25734311b6d3c8599c5
original_base_SHA           = ccd357885f7f9be84efe3be07868cc94f13d93fc
latest_review               = review_report_v4.md @ 18084a6213570e26a0a0941e628717f2c63fd00a
latest_response_reviewed    = response_v7.md
V7_three_route_source       = 7c4037a279cefd8546c51e8ae6cf0172c3eab89d
V7_reference_source         = 19adac7e3babb50c0028714684c220b713979196
V7_verification_fix_source  = 1ff6f8ba3dcb48dee0fd41f762bf624822ea1457
V7_review_decision          = ACCEPTED_WITH_LIMITATIONS_NOT_SOLVER_QUALIFIED
next_batch                  = V8_SCALING_AND_EXECUTION_CALIBRATION
response_required           = response_v8.md
material_state              = MATERIAL_READY_USER_SUPPLIED
old_p4_inverse_route        = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate         = NOT_QUALIFIED
master_merge                = NOT_APPROVED
```

最终目标不变：现有约 2 TB 工作站资源内，端到端不超过 48 小时，得到一个新的、真正非可分三维周期单胞的合格 0.7 nm 有限元解。当前微型模型不是最终目标规模，不能仅因标签为 0.7 nm 就宣布高频目标通过。

ChatGPT 实际读取了远程合同、response、summary、原始比较／计时和优化器代码；未 SSH 重跑工作站，未重算全部 ignored 数组。下文 measured 是仓库记录；公式结论是代数推导；下一批结果全部尚未运行。

## 1. V7 证据与审阅结论

依据：[Response V7](response_v7.md)、[详细结果](outcomes/neural_fe_single_solve_v7.md)、[原始比较](outcomes/records/neural_fe_comparison_v7.csv)、[逐点审核](outcomes/records/convergence_checkpoints_v7.csv)、[独立参考](outcomes/records/independent_blind_validation_v7.json)、[成本分账](outcomes/records/target_48h_budget_v7.json)。

| 路线／同一 micro-pilot | Schur 相对残差 | native 散射相对残差 | 全场 L2 相对差 | 散射场 L2 相对差 | 路线内部 wall / s |
|---|---:|---:|---:|---:|---:|
| NEURAL-TRACE | 0.9132631447 | 0.6611632265 | 0.0691964566 | 0.6612506374 | 7142.986080 |
| FREE-FE-OPT | 0.7973385649 | 2.1794111627 | 0.1055094041 | 1.0082620438 | 586.544889 |
| FE-LSQR | 0.0716025799 | 0.0287277515 | 0.1046399326 | 0.9999532575 | 560.600598 |

三条路线的原方程、场、功率 Gate 均未通过。NN 1611 closure／500 Adam／48 次完整 L-BFGS 外层调用，因 wall 停止；FREE 2000 closure，LSQR 1921 步，均达到规定工作预算。路线 wall 不是 launcher 整树总 wall；不同层级计时不得相加。NN 的场更接近参考但仍不合格，LSQR 的残差下降更多但未恢复准确散射，不能只选有利指标宣布赢家。

| 正结果或异常／身份 | 记录 | 本次解释 |
|---|---|---|
| 材料／真实 N1 measured | 四行材料已固化；S/Sᴴ/native 配对约 1e-15；真实方向导数最大约 1.82e-9 | 可复用接口，不再以材料不足或合成接口代替真实状态 |
| 独立同网格 p3 参考 measured | Schur 6.42415e-12，native 3.01796e-12；能量闭合 2.90634e-12 | 当前离散存在可信参考；非连续极限或 p 收敛证明 |
| Adam 早期 measured | NN 第25 closure Schur 8.8123；FREE 为295.2807，均从1开始 | 支持检查尺度／步长，不单独证明网络容量不足或唯一根因 |
| NN exclusive timer measured | forward 1600.5259 s，backward 5051.0396 s；S 156.6818 s，Sᴴ 299.6054 s | 前反向约占路线 wall 的93.1%，是明确实现优化对象，非预测加速 |
| 全批资源 measured | V7 八正式阶段8579.8250 s；采样同时树RSS1073967104 B；own swap0 | 不是资源耗尽；低RSS的失败场不算低内存成功解 |
| 停机语义 code-derived risk | closure 可抛 RouteStop；finally 直接读取当前模型参数 | 有可能冻结未接受的线搜索试探点，须修正并分开标签 |

不得把上述异常推导成“实际系统一定奇异”“全部神经方法不可行”或“调一个学习率必然通过”。也不得因停机语义问题删除 V7：保存的向量已经独立审核，作为该向量的负结果仍然有效；其是否为最近已接受迭代点需另作状态解释。

## 2. 权威、冻结物理与有限授权

先读根／目录 AGENTS、[仓库原则](../repository_work_principles.md)、[原 task](task.md)、Review V1–V4、最新 response/outcomes 和本 review。新范围只限下述 C0–C4；原合同中禁止任意调参仍有效，本 review 仅明确授权一种右对角变量缩放和等价实现／停机修正。原 task/review/response、V1–V7 原始结果、旧 seed420620 池保持不变。

| 冻结身份 | 本批值 |
|---|---|
| 方程 | Full3D，complex128，原 Nédélec H(curl)，原凝聚 trace＋port 增广系统；非 p6/p4 层次 |
| 几何／离散 | 原 V7 缺口 micro，384 hex，p3，h=0.175 nm，grazing1°／azimuth0／s；原积分和双 Floquet／layered DtN |
| 数量 | full FE34050；独立 trace18144；内部13824；slave2082；top20＋bottom20=40 ports；reduced18184 |
| 材料 | `input/materials/si_optical_constants_v1.json`；ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1` |
| 材料 SHA256 | `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2` |
| 0.7 nm Si | n=0.999885140474+4.32477054e-6i；epsilon=n*n；air/mu 与原合同一致 |
| physical SHA | `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de` |
| mode SHA | `93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262` |
| 网络 | 3×64 tanh，8固定载波，11696实参数，原seed420906；40复port独立，架构／相位／矩求积不变 |

保留 `0.699999988 -> nominal 0.7` 的显式材料别名，求解仍用0.7；不索要同一张表、不联网替换数值、不重新跑四个波长。运行前核对实际 schema、packet、背景仿射换元、RHS、master 顺序和所有 hash；不能只核对 physical 标签而忽略具体数组身份。

## 3. C0：复用证据与预登记，不重新搭建一轮 F0

读取必要的 V7 action/moment packet、三个冻结状态及标量历史，确认 local artifact 的实际路径与 hash。缺文件则针对性报告；不猜造 sandbox／本机路径，不重新跑 teacher、旧 PC、三条完整路线或全仓测试来填补记录。

登记一个唯一 scaled-LSQR 输入、一个固定批量化候选和下面的资源／停止规则。已有 N1、材料、网格和原算子未变的部分按 source＋artifact 复用；新增缩放／批量／停机行为单独验证。允许只读查看失败训练的已接受／试探历史，不把准确参考用作优化参数、缩放或网络初始化。原训练数据和终测概念不混用：本批是已知 pilot 的诊断续研，不称 fresh 未见几何泛化。

## 4. C1：修正 L-BFGS 停机与检查点语义

### 4.1 问题与最小修复

当前 [优化器](../../src/solvers/neural_fe_optimization.py) 可在 closure 内抛预算异常，而外层 finally 直接保存 live 参数。已读取的 [PyTorch v2.7.1 实现](https://github.com/pytorch/pytorch/blob/v2.7.1/torch/optim/lbfgs.py) 中 `_directional_evaluate` 是先移动到试探参数、调用 closure、正常返回后才恢复；异常时不保证恢复。现场仍须记录实际 torch 版本／实现身份，不能仅凭版本名假定路径相同。

在任务自己的 adapter 中修复，不编辑已安装 torch 或系统环境。**采用明确事务边界：每次 Adam 更新或 L-BFGS 外层 step 开始前保存最近一个完整提交状态；外层 step 正常结束后才提交新状态。** L-BFGS 内含多个内迭代时，若只掌握外层边界，就准确称 `LAST_COMPLETED_OUTER_STEP`，不要冒称最近一个内部 Wolfe 接受点。

预算／异常从 closure 抛出时恢复该提交参数，已执行的试探 closure、S/Sᴴ 和时间照计；不重置预算。若声称可恢复续跑，还必须保存／恢复一致的 optimizer state，否则明确 `PARAMETER_ONLY_CHECKPOINT_NOT_RESUMABLE`。本批不授权续跑原 V7。

保存 `committed` 与 `last_trial` 两类状态及其 source/hash/计数，不用同一文件轮流覆盖导致语义不明。所有日志写出 `state_kind`、outer id、closure id、LSQR step 和接受状态；计数不同不混称“迭代数”。closure 内完整审核是观察，不能将试探点自动提升为已接受状态。试探点若确实通过方程 Gate，其数值检查仍可如实记录，但不得借异常路径静默成为可恢复训练状态。

正常预算到期预留 final audit／checkpoint 时间；资源 emergency 时优先安全停止，仅保存允许的最低记录，不能为完成审核越过硬资源限制。

### 4.2 必须测试，但不重跑长 PDE

用小型实参数／复数残差问题，覆盖正常 step、线搜索首个及后续试探 closure 的预算异常、非有限值、初始 closure 异常；核对恢复的参数 hash、optimizer 状态资格和消耗计数。设置合成问题确保实际进入线搜索，不以未触发路径的测试充数。至少一个测试证明旧语义会留下试探参数、新语义恢复到已声明边界。

原 V7 的最终向量及已审核数值保持。若能从已有历史确定其是试探或已接受点，新增解释；不能无依据逆推出最后接受权重。无法还原时记 `V7_ACCEPTANCE_STATE_UNKNOWN`，不是重新跑两小时的理由。C1 的历史语义缺口不影响独立 LSQR 对照的执行。

## 5. C2：唯一的变量尺度均衡 LSQR 对照

### 5.1 它做什么，不做什么

不同系数若在方程中的作用大小差很多，统一步长或迭代可能难以兼顾。本试验只重新标定未知量的单位；用原算子的列范数定义正实对角矩阵 D：

```math
c_j=\lVert S e_j\rVert_2,\qquad D_{jj}=c_j^{-1},\qquad z=Dy,\qquad \widetilde S=SD.
```

所有 trace 和40个 port 列统一使用同一规则；无经验 block 权重、平滑轮数或目标解幅值拟合。每个 c_j 必须有限且严格为正，D及其逆必须可表示。真实零列／溢出等不静默用1或epsilon顶替，记录 `SCALING_DEFINITION_BLOCKED` 并停止本数值路线。极小但非零列报告范围；本批不通过阈值扫描、clipping或damping改变定义。

```math
\min_y\frac{\lVert b-SDy\rVert_2^2}{2\lVert b\rVert_2^2},\qquad
\widetilde S^H v=D^H S^H v,\qquad z=Dy.
```

这是右对角预条件／变量变换，不是强 p4 逆。不改左侧方程权重，不做 row scaling、不加正则项、不形成 SᴴS、不删弱列或端口。D可逆时原方程和可表达解集合不变；不保证条件数或实际收敛一定改善。LSQR 官方文档建议关注列尺度：[SciPy LSQR Notes](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.lsqr.html)，该建议不是本项目的成功保证。

### 5.2 构造 D 的允许路径与成本

**本批优先回答尺度假设，不要求先实现目标规模的列范数计算。** 允许一个独立、小规模、operator-only setup 进程读取已保存且配对合格的本问题 S CSR；没有保存时，允许复用现有独立参考的**装配函数**重建一次 S，但不创建任何 KSP factor、不做 symbolic/numeric/solve、不加载准确解。该例外仅限18184行的本pilot，不授权目标规模全局矩阵。

先正确合并重复行列贡献及相位，再从组装后的 S 求列范数；不能把各单元列范数平方和当作全局列范数平方。禁止 dense S 或全局 SVD、近似列范数随机扫描、逐列18184次整算子调用作为默认实现。用最多8个预定列（覆盖trace和port）与 action.apply(e_j) 独立核对范数；另用3个固定seed的非零复向量验证CSR正向与原S作用，operation-relative目标1e-10。

只输出 c、D、尺寸／单位／source／hash／列范数统计及配对记录。setup结束销毁CSR和临时对象、退出清场后才启动候选。candidate只允许原action packet与D，不读取CSR、因子或参考场。完整报告 `SCALING_SETUP_USES_SMALL_ASSEMBLED_S`；其时间、RSS计入从零准备的候选成本，不能只测后续matrix-free solve来宣称全流程无装配。目标规模的streaming列范数或其他部署实现仍为未验证事项，不在本批扩展开发。

D与旧准确解没有数据依赖。允许重用同算子的矩阵，不等于允许重用其解；输入白名单和进程分离必须能审计。

### 5.3 新候选一次运行

新名为 `FE-LSQR-COLUMN-SCALED`，从 y=0 开始，保持与V7相同的复数LSQR递推、精度、BIDIAGONALIZATION停止、无额外PC和原RHS。不得从NN、FREE、旧LSQR或参考warm start。候选使用 S(Dy) 和 DᴴSᴴv，先通过复数dot test、实际z恢复及loss一致性检查（operation-relative1e-10）。不只在实数／零向量上配对。

与V7保留相同的至多2000次S/Sᴴ作用上限（含初始、审核和最终作用），最多7200s路线wall；每25个LSQR迭代及最终做原完整审核。精确打印两类计数，不能把审核消耗从额度外隐藏。比较相同累计S/Sᴴ工作点，单列D setup成本；若新路线提前成功则如实停。预算不能因不收敛延长。

控制代码复用旧LSQR，仅新增对角包装与新profile，避免同时更换正交化、restart或停止准则。现有旧LSQR无需完整重跑；若实现基础递推改动才重新决定受影响证据，不能一边改算法一边称只改尺度。

### 5.4 冻结后验证与判读

求解进程结束并冻结状态后，单独验证进程复用V7的同网格p3准确场；先核对实际文件和hash，不重新分解／求解参考。参考只作这次诊断的独立比较，不调整D或checkpoint选择。参考不可得时继续原方程审核，场比较标not_run，不以重新LU自动填空。

全部采用原始物理坐标 z=Dy：原Schur／未凝聚augmented／native、port绝对与固定分母及operation-relative、恢复、slave-zero、total和scattered E/H/curl、完整复通道、R/T/A/A_volume与能量。loss用 b−Sz，不用缩放参数norm代替物理值；失败场的功率只作diagnostic。

严格资格沿用Review V3/V4：原方程各1e-6、恢复1e-10及slave-zero、同离散场／curl／selected E/H／全复通道1e-4、R/T/A/A_volume1e-5、逐通道功率1e-6、能量闭合1e-5，保持近零规则。为防total背景掩盖错误，本批另显式要求scattered E的L2相对差≤1e-4才称完整同离散资格；这是新增更明确检查，不回写V7。

除严格pass外，研究正信号预登记为：在相同或更少S/Sᴴ工作内，Schur及native各比V7 LSQR至少降低10倍，且scattered L2相对误差≤0.5。数值锚点为Schur≤0.0071602580、native≤0.0028727752。只降低loss而场仍≈100%时标 `RESIDUAL_ONLY_IMPROVEMENT_NOT_FIELD_PASS`。阈值仅为下一步研究决策，不是物理资格或定理；不足则保留负结果，不扫新D。诊断改善不许可自动开始神经尺度训练。

## 6. C3：神经前反向的数学等价批量化

这条工作线回答“同一网络每一步能否更便宜”，不改变网络能表达什么，不依赖C2必须收敛。C2数值失败不阻止本项有界工程检查；本项没有加速也不阻止C2执行。

固定3×64／8载波／FP64及原边面矩、orientation、owner、MPC、参数顺序与loss。允许缓存固定坐标、Jacobian、载波相位和已验证的常量映射，按至多8个owner-cell一批计算并重算VJP；登记一个batch=8候选，与原batch=1比较。不搜索多个batch尺寸。若容量预检不通过，保留batch1并报告，不自动扩大资源。新增持久缓存≤512MiB，每批图／临时数组先估算并受整树16GiB限制。

可以仅评估对最终trace确有贡献的采样点，但要按原完整矩及方向变换证明删除的是严格零贡献，不能删face高阶矩、重拟合求积、改变积分degree或把内部采样删除等同于删除物理内部恢复。禁止把数学近似缓存或量化称为等价优化。

验证参数集固定为：原零初始化、V6非零接口见证、V7神经最终冻结参数。后者只作为相同数值函数的测试输入，不作为新训练初值。所有state来源hash入档；缺历史参数时报告并用预登记seed420908的非零小扰动替代，不能读取参考场构造测试参数。

对每个state比较全独立trace、同一非零port下完整loss、实参数梯度（包含端口映射）以及一次克隆Adam更新。trace/loss/系数梯度配对相对≤1e-10；近零按明确绝对尺度并报告，不能零对零独自资格化。非零state上至少3个实参数方向FD稳定区≤1e-5，复用有限差分步长表。不因重排累积不能逐bit一致就误判失败，也不放宽到物理误差量级。

固定一个非零state，原版／新版交替顺序做3组成对独立进程微基准，每次1个warm-up和5个完整loss＋gradient评估，参数不更新。记录全部样本、中位数、冷setup、缓存bytes、树RSS、线程和S/Sᴴ数；端到端closure应包含相同原算子和VJP，不只计小MLP。受共享负载影响时标inconclusive；完整closure中位时间降低至少20%且总RSS合规才称本pilot实现性能正信号。不是求解加速或神经数值增量。

本批**不重跑500 Adam＋L-BFGS，不续训旧checkpoint，不训练新网络、不改学习率、初始化、层数、方向数或loss权重**。梯度统计、t/port尺度、输出层／隐藏层变化可从已有state和上述有限评估得到；没有接受状态原始历史就标unknown，不能重放长训练制造日志。

## 7. C4：合并证据，但分开作决定

| 检查维度 | 本批应回答 | 不能声称 |
|---|---|---|
| 停机安全 | 异常是否恢复到声明的提交边界，已花试探成本是否全部记录 | 因修复后测试通过就把V7判成功 |
| 尺度数值 | 一个固定D是否改善原残差及真实散射场 | 简单列均衡能处理所有Maxwell难度，或所有低内存PC可行／不可行 |
| 表示／优化 | 现有证据更支持尺度问题还是仍unknown | 不经独立实验宣布网络容量不足、超参必可修复或NN普遍无用 |
| 批量实现 | 相同函数与梯度是否更便宜，峰值是否受控 | 用固定state微基准声称48小时目标或完整神经解通过 |

若C2有正信号，下一轮可以建议一种明确的神经变量／输出尺度研究，但不得在本批自动实施。若C2不改善，不要求继续扫尺度，也不据此禁止一切神经研究；给出已排除与未排除因素。网络是否可拟合准确参考的监督诊断本批仍未授权，不能读reference回训。

不做新p4 enrichment，即便scaled LSQR通过也只先提交本固定离散资格。目标级48小时、任意三维泛化、精度收敛和目标规模DtN／存储仍未验证。最终只提出一个有本批证据支持的下一最小步骤。

## 8. 资源、预算和停止规则

用户受控共享CPU授权继续：其他heavy存在不自动阻塞，不要求全机独占锁；Task042自有nonblocking锁、内部阶段顺序，现场检查邻任务／监督器／数据加载线程与SMT后选核，MPI1、全部数学与Torch线程1、DataLoader0。只对自己nice10／idle I/O，独立环境、cache、TMP、FFCx和输出，不升级ABI/BLAS/CUDA，不使用GPU，不操作邻任务、其锁、环境、HEAD、亲和性、优先级或watchdog。

整树RSS hard16GiB／warn12GiB、own swap0、无OOC，磁盘自由≥50GiB、artifacts≤20GiB；系统余量max(128GiB,effective_total的10%)、邻增长128GiB及本任务16GiB均保留。没有cgroup委派时如实使用原0.5s采样监督，不称内核连续保证；资源紧张仅停止自身后代。不能承诺绝对零干扰，性能标shared-workstation。

V7最终[累计账](outcomes/records/resource_costs_v7.json)为8751.379832064034s，原10h上限尚余27248.620167935966s。现场核对后续应计费用。**本次新增数值有载与有界辅助检查总量最多4h，并同时受V6起累计10h剩余额度约束，取较小者；不重置已发生费用。** 其中D/setup≤1h；scaled LSQR含最终保存≤2h；C1/C3/验证与辅助合计使用余下预算。上限是停止预算，不是ETA。任何因错误修复的重放也计入。

格式／schema或实现错误允许一次有证据的最小修复并只重放受影响部分；停滞不是bug，不提高工作上限。部分artifact缺失或某工作线失败时完成其他独立可做部分；无无限轮询、后台自动启动或把all-not-run当成唯一交付。

## 9. 实现、提交与交付

复用 `neural_fe_optimization.py`、`bounded_complex_lsqr.py`、`neural_trace_torch.py`、action packet、原checker和shared runner；数值改动进入src并显式opt-in。新增one-run dat分别对应尺度准备、scaled-LSQR、固定state批量验证等清楚stage，正式FE通过 `python scripts/run_case.py input/task042_neural_coarse_inverse/<one-run>.dat`。不复制每模型一套runner，不全仓重构或执行无关full pytest。

提交计划：C1停机事务与最小tests；C2对角定义／准备／包装与tests；C3批量化与等价tests；C4 compact证据与response。实际运行前clean实现commit，绑定环境、source、输入和artifact hash；后续文档HEAD不能冒充运行source，活跃run内不为文档提交改变其受检HEAD。一个Task仍用本分支，未经批准不merge/rebase其他分支，不amend/强推。

必须交付 `response_v8.md`、`outcomes/scaling_and_execution_v8.md` 和 compact records：

```text
run_index_v8.json
optimizer_stop_semantics_v8.json
column_scaling_v8.json
scaled_lsqr_comparison_v8.csv
convergence_checkpoints_v8.csv
batch_equivalence_v8.json
batch_costs_v8.csv
gate_decisions_v8.json
resource_costs_v8.json
```

结合实际字段可合并小记录，不能再造多份漂移权威。同步summary/test_summary/changed_files、development_progress和development_model_registry；材料入口继续指向既有canonical表，不复制新版本。旧数据不回写，新增解释链接原文件；大型矩阵、向量、checkpoint仍ignored。

正式run继续保存原dat、resolved_config、manifest、input/physical/material/array/source哈希、run_summary、真实MPI／线程及整树监控。缩放额外保存D来源、设置成本、原S关联和candidate输入白名单；批量化额外保存state与映射身份；停机额外保存committed/trial语义。GitHub公式／表格按仓库标准检查，无法取得渲染页则明确未核验，不伪称通过。

Response V8首先报告精确HEAD、base、upstream、工作树与实际阶段，随后分别回答：停机问题是否复现并修正；D是否来自原矩阵且与答案隔离；scaled-LSQR的原残差／散射场是否改善；batch等价与完整步成本是否改善；完整内存、累计预算与未运行项；唯一下一步建议。目标解仍未合格时直说，不能以某一技术分项PASS覆盖全部。

只推送 `git push origin HEAD:refs/heads/task42_neural_coarse_inverse`，完成有限批次后停止等待review。**本审查不批准新NN长训练、恢复旧p4路线、扩大模型或合并master。**
