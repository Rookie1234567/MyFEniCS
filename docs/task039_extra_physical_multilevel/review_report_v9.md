# Task39extra Review V9：固定16次新搜索，隔离p4复用收益并用完整三维求解裁决

## 0. 身份、结论与本轮权限

```text
repository         = Rookie1234567/MyFEniCS
branch             = task39extra
review_date        = 2026-09-10
reviewed_HEAD      = ee1f486599da1dda4419cc6c28463a8d0df481c3
original_task_base = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
previous_materials = review_report_v8.md / response_v9.md
execution          = L0 -> L1(equal-new-work controls) -> conditional L2(original)
                     -> conditional L3(notch) -> L4(closeout)
response_required  = response_v10.md
new_profile        = balanced_h6_entity_gcrot8_new16_v9
new_I4_policy      = FIXED_NEW16_RECYCLE8
ordinary_default   = unchanged
master_merge       = NOT_APPROVED
```

**本轮消除的blocker：尚未分清“有限复用池确实不够有效”，还是“它有作用，但V8用旧方向替代了过多新搜索”。只做一次相同新搜索预算的对照；有明确收益就接回完整p6，无收益就关闭这个具体复用分支，不继续参数搜索。**

V8的原始模型59步、真残差0.0911427717，仍为受控负结果。保留V5准确p4 LU下的双模型成功，以及V6/V7/V8全部负结果。新合同不是纠正Codex少跑步骤：V8按原review正确执行了池满后8次新搜索。本轮由用户明确授权，改变的是实验设计，不追溯改判旧结果。

本轮只在小内存笔记本的既有合格Linux环境处理13.5 nm。用户已确认5 nm另线同步推进；不等待、不重复、不改变该线，不操作其进程、目录、分支或预算。最终目标仍为约2 TB整机内存内、0.7 nm、complex128、Nedelec H(curl)、双Floquet、Fourier-DtN、任意非可分三维周期单胞散射；本轮只资格化两个冻结离散模型。

**明确覆盖范围：** 只对新profile覆盖V8固定`m=8`的新方向分配；覆盖首次外层“每8步缩比”筛选为第6节的按时间检查；以第7节统一I4载荷上限替换本profile中V8的额外64MiB记账边界。V8的池隔离、真实算子、底层准确性、旧profile、历史筛选、最终物理精度和系统安全要求均不变。目录盘点未见新的补充task文件；同任务review按本目录版本衔接，不另建分支。

## 1. 接受的证据与需要分开的结论

下表均为已提交measured记录，时间为各记录的实际solve节点，不是本review新跑的PDE；百分比与工作量关系为derived。RSS为相应进程树采样峰值，GB为十进制。

| 范围 / 分母 | 已有结果 | 本轮解释 |
|---|---|---|
| V8与V7 A，第56个外层PC | 时间1731.024 / 2490.940 s；残差0.0932053 / 0.0751498 | V8该节点更快，但残差更大；不等于同精度加速 |
| 接近1800 s的真实节点 | V8第59步0.0911428；V7 A第41步0.1131115 | 有限时间窗口正信号，不推定最终收敛 |
| V8前59PC内部工作 | 118次I4、980次B4；V7 A同前缀1888次B4 | 少48.093%，主要由预定新工作缩减造成，不是同精度提前收敛 |
| V8固定6 RHS | RESET/CARRY约103.680 / 84.276 s；4项残差改善、1项相同、1项变差 | 值得隔离新工作量再比较一次，不能称通用复用成功 |
| V8终态资源 | RSS1.530 GB，swap增量0；official/notch未运行 | 低存储但完整求解未通过 |
| V5准确粗逆 | 原始564步、true约9.93e-7；notch576步、true约9.35e-7，完整场/功率通过 | 不重跑；继续作同模型参考与成功基线 |

证据入口：[Response V9](response_v9.md)、[V8中心结果](outcomes/recycled_p4_outer_v8.md)、[V8 compact](outcomes/records/recycled_p4_outer_v8.json)、[逐I4记录](outcomes/records/recycled_p4_i4_rows_v8.json)、[V7中心结果](outcomes/bounded_inexact_outer_v7.md)。V5参考窗口448页系统换出归因限制保留。

旧SciPy调用的实际新搜索长度是`ml=m+max(k-r,0)`，r为进入搜索前保留的有效方向数。V8的m=k=8，使前8次I4新工作为16到9，之后110次为8；合计980。**本轮不能再用“相同m/k参数”冒充相同新工作量。**

不重新做误差投影、全场参考、谱分析、旧长程求解或full252构建。不宣称空间复用必然消除剩余误差；也不以V8失败证明所有recycling无效。

## 2. 冻结物理、数值身份与允许改动

| 对象 | 冻结合同 |
|---|---|
| 原始模型 | 13.5 nm，grazing1度、azimuth0度、s；50×25 nm周期，z=-10到130 nm；Si/air及原损耗 |
| 离散 | p6/h10，252六面体；p6独立164592/存储173802；p4独立48960/存储53084 |
| 原physical SHA | 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f |
| 原mode SHA | dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 |
| 算子与传递 | 原full-space matrix-free A6/b；P64/P64H、native A4、cached exact volume及完整80模式DtN不变 |
| 外层 | 同一BAL_H顺序与H6，right FGMRES32、max2048，零初值，一个持续KSP |
| 内部基础PC | V7 A实体作用：CU、内部响应、792 edge/774 face、原权重/反馈、既有MPI1 owner路由；不换回H4/p2，不换full252 |
| 复用机制 | 现有flexible GCROT、同一截断`smallest`、k=8、maxiter=1、atol=0；只改变新搜索长度分配 |
| 缺口 | V5冻结8个cell keys及对应材料实体、独立physical SHA和参考；不得按新recipe改形状 |
| 输出 | 合法探针127.5/-7.5 nm，同坐标复数E/H、near field、R/T/A/A_volume、80模式 |
| 环境 | 既有ABI、complex128、MPI1、线程1，记录IntType和SciPy实际源码；不升级库 |

优先在`src/solvers/physical_recycled_i4.py`及现有policy/runtime中增加显式策略参数，复用通用runner/checker。旧V8默认行为与已有回归保持不变，不复制新的大型求解框架。允许新dat/profile、相关focused测试、标量计时和必要记账。正式入口统一为`python scripts/run_case.py input/path/to/case.dat`。

不允许全局p4/p6矩阵或LU、全局稠密T、另一粗阶次、另一recycling算法、rank扩展、更多内层循环、正反扫/权重扫描、新DD/PML、准二维替代或恢复旧解。只有既有S/p2小底层和实体局部因子允许按原合同复用。

## 3. 核心变更：固定新工作，而不是固定库参数m

### 3.1 唯一新方向分配

对每次非零RHS，给一个GCROT周期**最多16次新的B4作用、最多16个新Arnoldi方向**，外加最多8个已有方向。达到原A4目标或安全截止可提前返回，但不得仅因池满而自动缩减到8步。

在本地SciPy 1.11.4已确认的`ml=m+max(k-r,0)`路径中，应在有效池rank确定后采用：

```math
m_{\mathrm{call}}=16-\max(8-r,0),\qquad
m_{\mathrm{call}}+\max(8-r,0)=16,\qquad 0\le r\le8.
```

| 入场有效池rank r | m_call | 新搜索上限ml | 保留旧方向上限 |
|---:|---:|---:|---:|
| 0 | 8 | 16 | 8 |
| 4 | 12 | 16 | 8 |
| 8 | 16 | 16 | 8 |

这不是根据残差调参；它是保证同一新工作上限的确定性换算。**不能直接固定m=16、k=8而让空池生成24次新搜索；也不能在一个周期结束后再开第二周期补步。**

r必须取本次工作副本完成合法化/正交化后的有效rank。库若再次剔除相关列，需要确认实际ml仍受16上限约束；使用最小适配或显式有界搜索参数，不能盲信入口len(CU)。在B4回调真正执行第17次前拒绝超额工作并按正确性/计数问题收口，不能先执行再记为16。

“16”是上限，不是强迫已达标方程继续计算。每次记录requested/completed/discarded的新B4、实际Arnoldi长度、有效rank、m_call、提前停止原因。若因时间线少做，不得称该样本已经完成等新工作量对照；安全优先，不延时补齐。相同新B4次数仍不意味着相同总时间或完全相同搜索空间。

### 3.2 不变的复用代数

只保存本次运行自身生成的有限方向U及其真实A4像Q，保证：

```math
A_4U=Q,\qquad Q^HQ=I,\qquad U,Q\in\mathbb{C}^{N_4\times r}.
```

保留初始投影和新方向的解空间反馈，不能只投影残差而忘记相应解修正：

```math
c_0=UQ^Hg,\qquad B=Q^HA_4Z,\qquad
A_4(Z-UB)=(I-QQ^H)A_4Z,\qquad c=c_0+(Z-UB)y.
```

仍用稳定QR/SVD，`truncate='smallest'`，不加入harmonic-Ritz或另一筛选。SciPy末尾的`(None,x.copy())`不进入持久池；临时新方向和事务副本都计费。保留最多8对不等于发现了8个普适物理模态。

### 3.3 内部截止与正确性

I4继续以真实A4的1e-4为提前停止目标，不是外层准入硬Gate。沿用25 s安全返回请求、30 s费用边界；包含投影、正交化、新搜索、截断、native残差及审计。未达目标但有限且合法的返回仍为`INNER_APPROXIMATE_RETURN`。

安全截止可使用已有适配取得最后完整更新；若只能退回本次池投影，记录丢弃的新工作，不把未提交方向计为有效收益。连续两次非零RHS无合法返回，或连续三次超30 s，按原`INNER_COST_BLOCKED`停止。非有限、错映射、配对失败、算子身份冲突不能伪装成“允许不精确”。正常相关方向剔除不算故障。

## 4. 状态隔离、粗细平衡与参考使用

同一模型只持有一个池，按真实g1、当前反馈g2的调用顺序共享。正式原始模型从空池、零外层初值开始；notch也重新从空池开始并重建自己的材料因子。L1控制池必须在正式运行前销毁。参考解、真实误差、历史最终解、工作站数据不进入池、初值或方向选择。

每次池更新沿用事务式工作副本：finite、约束、rank、正交及AU配对通过才提交。绑定physical/mesh/material/quadrature/Floquet/map/mode/owner/ABI身份。数值身份变化先释放旧池；不能因数组shape相同就复用。同一状态快照应可重放，不要求演化后的有状态PC满足无状态线性等式。

BAL_H保持实际流程：

```text
g1 = P64H(q)
c1, eps1 = I4_fixednew16(g1, pool)
zc = P64(c1)
s = H6(q - A6(zc))
g2 = P64H(A6(s))              # 由这次c1实际生成
c2, eps2 = I4_fixednew16(g2, pool)
z = zc + s - P64(c2)
```

```math
P_{64}^H(q-A_6z)=\varepsilon_1-\varepsilon_2,
\qquad \varepsilon_i=g_i-A_4c_i.
```

检查的是该式闭合，不要求右端为零。真实fine A6始终准确。每次保存原A4相对残差、eps绝对范数及RHS范数；pool配对/正交限1e-10，rank阈值1e-12相对尺度；首个非空池、每32次I4及退出做既有native抽查。BAL_H首PC、每32PC及退出的操作尺度闭合限1e-8。复用已有作用做检查，避免重复计算所有列；检查费用如实计入。

## 5. L0–L1：一次有限等新工作量对照，随后按条件进入真实问题

### L0：准备及最小实现检查

按根/docs/适用AGENTS、工作原则、当前task、V8/V9、最新response/summary核对canonical worktree、branch/HEAD/upstream、clean source、ABI、complex128、MPI/线程、MemAvailable/cgroup、swap、磁盘和watchdog。只核对本轮实际依赖，不再写全历史报告。

重点回归：rank0至8的新工作分配，rank剔除后仍有上限，禁止24步；zero/相关RHS；池身份和答案隔离；超时与合法返回；复数共轭和解空间反馈；输入不变、slave/owner；旧V8 profile行为不变。一个合并非Hermitian复数fixture足够，不开阶次/网格扫描。原网格只重核变更影响的桥，A4身份沿1e-10、cached/native沿1e-11。prototype先提交，再以clean SHA运行。

### L1a：6份固定输入，RESET16与CARRY16各一次

使用已有且hash一致的A2R160 g1/g2、LIGHT448 g1/g2、JOINT448 g1/g2，顺序不变。两组都调用新策略，区别仅为：RESET16每RHS前清空池；CARRY16仅序列开始时清空。两组均最多16次新B4、同目标、同截止、同局部因子，池rank最多8。底层构建一次，两个池顺序使用与释放。

最多12次I4，不再重跑V8的8新方向版本，其结果仅引用历史记录。报告每项native残差、eps范数、池投影效果、实际新工作和全部A4分类、时间、瞬时载荷，以及已有reference可支持的场差。不得为了补参考重建LU。两序列累计成本必须包含从空池的第一项，不能只挑末尾受益项；入场第一项应核对同初值/作用一致性，而不是计作复用收益。

完整16新B4的成对项可以作等新工作量比较。较早达到true target的项单列“达到同目标所需工作”；时间截止或未提交更新项单列“不等实际工作”，不声称因果隔离完成。

### L1b：固定的投入决策，不再用一句“有正信号”无限延长

去掉第一项冷启动，对有效成对项取i集合。至少需要3项（原有5项优先全部使用）；缺文件不重建参考、不追加新样本。令rho为各自原A4相对残差，将低于提前目标的数值截到1e-4，仅用于本节投入统计：

```math
q_i=\frac{\max(\rho_{i,\mathrm{CARRY16}},10^{-4})}
           {\max(\rho_{i,\mathrm{RESET16}},10^{-4})},\qquad
G=\exp\!\left(\frac{1}{n}\sum_i\log q_i\right).
```

正常进入L2需同时满足：G不高于0.90；至少60%的有效项有q_i小于1；没有q_i大于2；所有实际成对调用累计CARRY/RESET时间比不高于1.50；正确性及资源合格。若两组已全部达到1e-4，则转按同目标工作/时间比较：CARRY累计时间不高于RESET的0.90可准入。提前target命中应同时保留未截断数字，不能用截断重写物理解或终态。

这些阈值是一次固定的工程投入选择，不是FGMRES收敛定理，也不要求完整PC单次残差下降。不满足则以`EQUAL_NEW_WORK_NO_CLEAR_GAIN`收口；不足3项则`COMPARISON_EVIDENCE_LIMITED`，不是“复用无效”。不可再扫描rank/容差/循环数以凑准入。

通过后，允许最多2次完整新BAL_H控制（已有A2R160与LIGHT448的合法q），控制池从空开始并按次共享，实际重算g2；核对第4节并记录完整PC费用。两次均超90 s则按`COARSE_ACTION_COST_BLOCKED`收口；否则释放控制池，**直接执行L2，不停审**。控制场误差若可得必须报告，但单次残差大于1不是拒绝原因。

L0/L1准备、相关测试与有限数值控制合计不超过3600 s，其中有限控制900 s，二者为包含关系。缺失非必要参考不阻断已有可信比较；不能用剩余预算继续单g1研究。

## 6. L2–L3：完整原始/缺口求解，按时间而非每步降幅限制投入

本轮至多一场新原始模型和一场条件notch。均用新dat、零外层初值、空池、一个持续FGMRES32，禁止加载V7/V8的解或离线控制池。每8步和退出前算原A6真残差，每32步保存安全checkpoint。每个时间检查点在第一个可用安全边界用当前解重新算真残差，并记录实际超出秒数；不等待整段restart，也不清KSP或池。

**首次筛选明确改为固定求解时间下的绝对进展，消除不同单步成本对“每8步缩比”的混淆。仅对新profile生效，V8第59步负结果不追溯改判。**

| 节点 / 单位 | 继续或停止规则 |
|---|---|
| solve约1800 s | 已达1e-6则转输出；否则rho不高于0.10可继续，高于0.10按`TIME_PROGRESS_SCREEN_STOP`结束 |
| 第128步 | 仅保存观察，不以该步数提前替代1800 s时间检查 |
| solve约5400 s | 尚未达1e-6且rho大于1e-3，按`PROGRESS_INSUFFICIENT_AT_MID_BUDGET`停止 |
| 完整上限 | solve10800 s、workflow14400 s、2048步，先到者停止；全部内层、检查和保存计入 |

时间采用既有conservative_realtime并保留monotonic等原字段；不再研究系统校时。上述只是资源投入规则，不表示更长时间必不收敛。没有正常进展不放宽门槛或续跑。新曲线与V5/V7/V8使用真实同时间附近节点及共同步数分别比较，不用终点总时长宣称加速。

原始残差及完整输出通过后，立即同profile执行冻结notch。其材料因子独立构建、池重新为空、算法与工作量不调。失败则保留该几何适用性缺口并结束；不切第二算法。参考是各自同模型参考，不互比两个不同结构的R/T/A来判误差。

| 完整Gate | 要求 |
|---|---|
| 原A6 | full explicit norm(b-A6x)/norm(b)不高于1e-6 |
| 场与近场 | 对同模型reference的L2/scaled-curl不高于1e-4；selected E/H、同位置near-field，近零量另报绝对差；不拟合相位 |
| 功率/耗散 | R/T/A/A_volume对各自参考绝对差不高于1e-5 |
| 独立闭合 | R+T+A_volume与1之差，以及A与A_volume之差，均不高于1e-5 |
| 全80模式 | 复幅值向量相对差不高于1e-4；逐通道功率最大绝对差不高于1e-6 |
| 内部/资源 | 原A4残差、pool与eps闭合、实际新工作及完整同期RSS/zero-swap/成本合格 |

未收敛场不生成official输出。仅收敛后的输出工程错误允许从同一已保存解恢复一次，不重求场。两份参考已有，不授权新增直接参考；网格收敛与短波鲁棒性不由本轮同离散对照证明。

## 7. 内存、费用与运行边界

持久池仍最多8对。当前48960独立行的U/Q数值载荷为`2*48960*8*16=12533760 B`；若按53084存储行则为13589504 B。这是derived载荷，不是RSS，不能混用两种坐标口径。

固定16次新搜索时，池满后同时活跃的旧方向与新搜索向量比V8多。**本profile统一限定“I4搜索向量＋持久/事务池＋QR/SVD/截断临时数组＋适配向量”的峰数值/索引载荷为128MiB。** 该统一口径替代V8“扣除变长V/Z后的额外64MiB”规则，持久rank不增加；不是分配承诺或实测RSS。另报相对RESET16真正新增的峰载荷。禁止只改常数而漏算库内部副本；应先用16新方向重新建立数组生存期账本。

其余安全合同保持：effective_total为可见物理/cgroup较小值；reserve=max(4GiB,15% effective_total)；launch cap=min(12,000,000,000B,effective_available-reserve)，运行中保持余量。S/p2底层8192总行、矩阵/转换/factor/workspace预审512MiB；实体/bubble/owner/原缓存256MiB载荷上限。整机2GB仅优化指标，不是本轮准入硬线。

一次一个本机heavy，进程树包括Python、MPI、FFCx和编译后代；全程监测系统/作业swap及完整RSS。硬安全优先于等工作量和保存；无法归因的系统swap不能称zero-swap或数学失败。不得同时保留两套PC、两个控制池、full252或旧p4 LU。notch不能复用原始数值因子。

| 费用项 | 本轮上限与记账 |
|---|---|
| L0/L1 | 合计3600 s，其中有限控制900 s |
| 新原始模型 | 至多1次，solve10800 s/workflow14400 s |
| 条件notch | 至多1次，同上，含自己的setup |
| 全批 | 36000 s，父/子不重复计费；各项额度不是保证全部可叠加使用 |
| 不授权 | 第二组参数、额外原始续跑、新子域/PML、fine/p4 direct、MPI扩展、5 nm或0.7 nm heavy |

实际setup/solve/recovery与reserve/policy上限分别记录；不能再把reserved3600 s报成实测准备时间。旧V7/V8成本只作历史对照，不再次并入新批账本。记录cold构建与缓存加载范围，未测fresh cost不能伪称已消除。

## 8. L4：集中收口、证据与停止后的决定

L0到L3按上述分流连续执行，最终新增`response_v10.md`。新中心建议`outcomes/equal_work_recycled_p4_v9.md`与`outcomes/records/equal_work_recycled_p4_v9.json`，复用逐I4紧凑schema并加入effective_rank/m_call/requested_new/completed_new和中断字段。更新summary、run_index、test_summary、两本项目总账和handoff；不要每个微测试再建一套文档。

必须回答：

1. 相同新搜索上限是否真实执行；哪些成对样本完成16次，哪些提前到目标或被时间截断；不能只报参数。
2. 等新工作量下CARRY是否比RESET有修正质量收益，代价多少；全六项、累计时间、实际B4/A4、G及退化项全部保留。
3. 新完整原始/notch是否通过；同时间和同迭代两个维度比较V5/V7/V8，终点不同不能冒充提速。
4. 新128MiB统一I4载荷、持久池载荷、完整PDE RSS分别是多少；不是把派生bytes叫实测RSS。
5. 失败属于实现/资源/没有组件收益/完整外层进展不足中的哪一项；不能自动归因rank8不足或所有复用无效。

两模型全部通过才标`EQUAL_WORK_RECYCLE_TWO_MODEL_PASS`；只有原始通过标`ORIGINAL_PASS_NOTCH_UNQUALIFIED`；受控未完成标`EQUAL_WORK_RECYCLE_BOUNDED_NEGATIVE`并细分原因；数值通过但较慢要明确memory/time tradeoff。此前V5成功和V6–V8负结果、swap限制、旧checker证据不变。

**本轮是当前rank8/实体基础PC下最后一次隔离新工作量的对照，不形成rank/步数扫描。** 无明确整体收益便关闭这个具体复用组合。跨多单元完整物理子域只可写成后续设计建议，须对照旧16-slab/小patch、总因子库存、全局纠错与底层规模；本轮不得自动实施。5 nm独立工作继续，不把它当作本批延长或等待的理由。

正式每次绑定input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json以及ABI/MPI/线程、mode/map/cache/artifact hash。终止保存可恢复的最后解/真残差，释放KSP、池、S/实体因子与无用矩阵，记录RSS变化后恢复合格场；清场全部本机后代，不操作其他任务进程。

提交计划：通用策略参数与最小回归 -> clean SHA的L1 -> 若准入，clean同算法源码L2/L3 -> 统一outcomes/response。ChatGPT只新增本review；Codex不修改review、不amend、不强推、不合并master；HEAD若推进先核对差异，不擅自merge/rebase其他活动分支。

## 9. 方法依据与文档范围

- [SciPy 1.11.4 gcrotmk接口](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.sparse.linalg.gcrotmk.html)与[该版本源码](https://github.com/scipy/scipy/blob/v1.11.4/scipy/sparse/linalg/_isolve/_gcrotmk.py)：支持复数、flexible PC和CU复用；实际ml分配、原位更新及退出解副本以本机源码核对，不能由在线参数名猜测。
- [PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：外层可接收非线性/变化的内部求解；这不是任意有限粗逆的收敛保证，不据网页版本升级ABI。
- 数学接口与物理冻结继承[Task](task.md)、[Review V8](review_report_v8.md)；本review只覆盖第0节列出的策略与投入边界，不追溯更改历史。

**交付目标：用相同新搜索预算分清复用的真实收益，并尽快取得完整三维求解的肯定或否定结果；不是通过少做工作制造“提速”，也不是继续延长一个内部问题直到越过门槛。**
