# Task39extra Review V8：有界 p4 搜索空间复用，以完整三维求解裁决

## 0. 身份、审阅结论与授权

```text
repository          = Rookie1234567/MyFEniCS
branch              = task39extra
review_date         = 2026-09-10
reviewed_HEAD       = f5456d9f6c680beab26fc290e8e7799f032c77f8
original_task_base  = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
previous_materials  = review_report_v7.md / response_v8.md
execution           = K0 -> K1 -> K2(original) -> conditional K3(notch) -> K4
response_required   = response_v9.md
new_profile         = balanced_h6_entity_gcrot8_v8
ordinary_default    = unchanged
master_merge        = NOT_APPROVED
```

**本轮针对的 blocker：去掉全局 p4 LU 后，当前局部物理修正尚不能以经济的成本支撑完整 p6。固定模型内反复求解同一个 A4，但旧 I4 每次清空搜索信息。本轮只检验：有界复用计算自身产生的方向，能否减少重复搜索并改善完整求解。** “重复困难方向可以复用”是待验证假设，不是已确认的唯一失败原因，也不是收敛保证。

用户已说明 5 nm 扩展在另一条线同步进行。本批仅在现有小内存笔记本的已资格化 Linux 环境研究 13.5 nm；不等待、不重复、不改变另一条线的工作，不启动或停止其进程，不借用其预算，不自行合并分支。最终目标仍是约 2 TB 整机内存内的 0.7 nm、complex128、Nedelec H(curl)、双 Floquet、Fourier-DtN、任意非可分三维周期单胞散射。

接受 V7 两条候选的受控负结果及收口；保留 V5 准确 p4 粗逆下的双模型成功。本轮仅授权一种新的搜索信息管理机制，复用 V7 A 的实体 PC，不重新开启 projected seq2、更多分组或增步扫描。新的 K0–K4 连续执行，正常子项不合格按本文分流，最终统一交 response_v9，不逐个小测试停审。

**明确覆盖旧限制：** 仅对此 opt-in profile，允许在同一模型、同一次正式求解内，跨 p4 RHS 保留最多 8 对合法方向及其 A4 像；允许由该空间对当前 RHS 构造投影初始修正。这是对原 task 的 persistent Z/AZ 禁令、V7 每次完全零初值和不跨 RHS 保存搜索信息规定的窄例外。禁止全局逆库、跨模型热启动和参考答案泄漏等其他限制不变；旧记录与旧阈值不改判。更大物理子域仅保留为未来备选，本批不实现第二条架构。

## 1. 已有证据与不应重复的工作

以下是 reviewed_HEAD 已提交的 measured 记录，不是本审阅重新计算的 PDE。GB 为十进制，RSS 为相应进程树采样峰值。

| 对象 | 结果 / 单位 | 本轮定位 |
|---|---|---|
| V5 BAL_H + 准确 p4 LU | 原始564步、true约9.93e-7、solve6102.6s、RSS3.466GB；notch576步、true约9.35e-7、RSS3.601GB | 完整双模型基线与参考复用；不是0.7nm资格 |
| V7 A entity16 | 原始121步、true0.0425645121、solve5423.95s、RSS1.450GB；242次I4、3872次B4 | 局部组件仍可复用；原完整候选保持失败 |
| V7 B projected seq2 | 原始88步、true0.0638555834、solve5407.72s、RSS1.518GB | 本批不再扩大或重跑 |
| 现有 I4 实现 | physical_recursive_coarse.py 每个 RHS 新建 KSP、清空初值，返回后销毁；局部因子复用，Krylov方向不跨调用保留 | 本轮唯一要改变的组织方式 |

证据：[Response V8](response_v8.md)、[V7中心结果](outcomes/bounded_inexact_outer_v7.md)、[summary](outcomes/summary.md)、[现有I4源码](../../src/solvers/physical_recursive_coarse.py)。V7较低RSS对应未完成求解，不是低内存成功；V5参考448页系统换出归因限制继续保留。

不重新建立 fine reference，不重算旧三个误差的最佳投影，不延长单个 g1，不重建 full252 的36,288列，不补跑旧A/B、S6、PML或正定测试系列。低内存不等于完全无局部因子；现有有界 S/p2 和实体因子依赖继续明示。

## 2. 冻结物理、算子和已有 PC

| 项目 | 固定值或规则 |
|---|---|
| 原始模型 | 13.5nm、grazing1度、azimuth0度、s；50×25nm周期，z=-10到130nm；Si/air，原损耗 |
| 离散 | p6/h10、252六面体；p6独立164592/存储173802；p4独立48960/存储53084 |
| 原physical SHA | 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f |
| 原mode SHA | dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 |
| fine方程 | 原 full-space matrix-free A6/b、积分、双Floquet、完整80模式DtN不变 |
| 外层 | BAL_H顺序、H6、P64/P64H；right FGMRES32、max2048；正式解从零开始 |
| p4物理作用 | 真实A4；沿用已资格化 cached exact volume + 原DtN；最终残差用native A4 |
| 内部基础PC | V7 A实体数学作用：原CU、内部响应、792 edge/774 face、原权重和反馈、合法MPI1 owner路由 |
| notch | V5冻结的8个cell keys及实体材料分布；使用自己的算子、局部因子及参考；不得换更容易的结构 |
| 输出位置 | V5合法外部探针127.5/-7.5nm；同坐标E/H、near field、全部模式 |
| ABI/MPI | 现有资格栈、complex128、MPI1/线程1；记录全部版本及IntType，不升级环境 |

数值核心放入通用 src/solvers 模块；runner只编排与记账，checker只读证据。正式入口仍是 `python scripts/run_case.py input/path/to/case.dat`。允许新增小型 GCROT/PETSc 向量适配模块及显式 profile，不复制一套庞大任务专用框架。

本轮不构造全局p6/p4 AIJ或LU，不保存全局稠密T，不改生产默认，不转回凝聚fine架构，不减少模式，不使用准二维或Hybrid代替。原始与notch不同材料，不能只因行数相同而共用数值因子或复用空间。

## 3. 新机制：保留少量已发现方向，后续 RHS 不从空搜索开始

### 3.1 解释与数学对象

同一模型的内部问题是 A4 c=g，A4不变而g随外层更新。保留有限个解空间方向 U 以及它们的原算子像 Q，并归一化使：

```math
A_4U=Q,\qquad Q^HQ=I,\qquad U,Q\in\mathbb C^{N_4\times k},\quad 0\le k\le8.
```

这里Q不是参考解，U不是p4逆矩阵；它们只覆盖一个小子空间。实现使用现有合法坐标及范数，不能重复计算ghost/slave条目。新RHS可先获得：

```math
c_0=UQ^Hg,\qquad r_0=g-A_4c_0.
```

该修正只利用当前RHS和已有方向，不读取准确解。随后在残差上生成新方向，并对Q所张成的像空间进行投影。若新预条件方向组成Z、B=Q^HA4Z，后续修正必须包含对应的解空间反馈：

```math
A_4(Z-UB)=(I-QQ^H)A_4Z,\qquad c=c_0+(Z-UB)y.
```

因此不能只在残差端减Q分量，却忘了在解端减UB。小最小二乘用稳定QR/SVD，不显式形成正规方程。真实A4仍是目标算子，实体PC只生成搜索方向。

完整选择采用 **flexible GCROT 的有界截断复用**，不把“先投影一次再普通迭代”冒充完整recycling，也不把它称作已实现的harmonic-Ritz GCRO-DR。GCROT会保留、组合和丢弃计算自身产生的方向；小奇异值截断按实现定义，不自行反转筛选规则或声称选中了物理本征模。

### 3.2 唯一算法与实现边界

首选使用现有环境的 `scipy.sparse.linalg.gcrotmk` 及薄的matrix-free/PETSc适配：`m=8, k=8, maxiter=1, truncate='smallest', discard_C=False`，rtol/tol兼容映射到1e-4，atol=0。先核对本机实际SciPy版本、源码和签名并记录，不按在线最新版升级。

**实际新工作以计数为准：每次RHS最多16次新的B4作用、最多16个新Arnoldi方向。** 常见GCROT实现会在空间未填满时补充新方向；上述参数通常从空空间最多16步，池满时最多8步。不能把 `maxiter=16` 误当总共16步，也不能再加一个外部循环补足或延长。rank下降时也不能越过16次新B4上限。最多8个旧方向加受限新方向，不承诺与旧FGMRES16逐位相同。

允许为安全中断、获得已完成小最小二乘对应的候选解及记录成本做最小适配；不得因此重写整套外层、安装HPDDM、切换到另一recycling算法或比较多个后端。若本机接口缺少必要功能，在准备预算内使用明确引用同一GCROT公式的最小兼容实现并核验；无法实现则报告具体 blocker，不进入无期限软件建设。

GCROT库的CU可能原位修改，某些版本退出时还附加一份 `(None, x)` 解副本。适配必须检查实际源码：此额外解副本不进入本轮长期复用池；退出时只提交不超过8对已验证的方向及其像，不能悄悄保留第9对或所有历史解。临时第9个更新方向允许在本次截断工作区出现，内存计费且调用结束释放。空间选择固定为上述GCROT截断，不扫描rank、截断策略、RHS顺序或容差。

## 4. 复用状态、答案隔离与数值安全

一个正式模型只拥有一个复用池，按实际调用顺序在 g1、当前反馈g2以及后续PC之间共享。允许一次I4完成并核验后更新池，再供下一次I4使用；不拆成未经授权的多个池，不为g2专门学习另一组参数。

池身份至少绑定 A4 physical/mesh/material、quadrature、Floquet/map、mode及normalization、scalar dtype、owner布局、数值实现身份和profile。身份变化必须先释放旧池并重新从空开始；意外不一致不能静默继续。允许数学等价源码桥，但不得仅因shape相同就复用。

**正式原始模型与notch均从空池、零外层初值开始。** 有限控制的池在正式运行前销毁，原始的池不带入notch。参考场、直接法解、真实误差、旧最终解和工作站数据都不用于初始化U、挑方向、决定停止或修改参数。当前求解自身产生的有限方向可以保留，固定容量替换，不是建立答案缓存。

每次持久状态更新必须是事务式：工作副本通过finite、约束、配对与rank检查后才替换已验证池。一个正常线性相关方向可以被丢弃，不作数值故障；相同池快照、相同输入可重放，但演化后的池不要求返回与旧调用相同的解。不得对这类有状态/非线性PC强行要求线性或无状态repeat等式。

主要检查：Q正交性操作尺度误差不高于1e-10；A4U=Q的操作尺度闭合不高于1e-10；新增/更新所需A4检查计入成本。优先利用本次已有作用及QR变换，避免每次重算所有旧列；首个非空池及每32次I4做一次至多8列native抽查，退出核对最后更新。近相关列用rank-revealing QR/SVD剔除，rank阈值采用1e-12相对尺度。非有限、错误配对或同身份作用不一致是正确性问题，不以“清空再试”掩盖。

### 一次 BAL_H 的近似误差仍然记账

```text
g1 = P64H(q)
c1, eps1 = I4_recycled(g1, pool)      # eps1 = g1 - A4(c1)
zc = P64(c1)
s  = H6(q - A6(zc))
g2 = P64H(A6(s))                     # 必须由本次c1实际生成
c2, eps2 = I4_recycled(g2, pool)
z  = zc + s - P64(c2)
```

即使两次调用的池状态不同，仍核对：

```math
P_{64}^H(q-A_6z)=\varepsilon_1-\varepsilon_2.
```

沿用V7操作尺度1e-8闭合线，不要求右边为零；逐调用记录两次真实A4残差和RHS绝对尺度。原A6始终准确，不能将不精确粗逆变成不精确fine矩阵作用。

## 5. I4工作与内存合同

| 项目 | 固定规则 |
|---|---|
| early target | 原A4相对残差1e-4，只作提前返回目标，不是外层准入硬线 |
| 新迭代工作 | 每RHS最多16次B4；GCROT一轮，不做隐藏追加或跨段延长 |
| 时间 | 延续V7：25s请求安全返回、30s费用边界，包含投影、正交化、更新、native残差及检查 |
| 返回 | 已完成合法搜索或池投影对应的有限解；未达标为INNER_APPROXIMATE_RETURN，不写converged |
| 真残差 | 每次退出计算g-A4c；不能仅用投影残差或库info裁决 |
| 零RHS | 返回零，不破坏池；单独计数，不触发无方向故障 |
| 新增内存 | U/Q持久数值最多8对；复用模块额外峰载荷含事务副本/QR/SVD/索引不超过64MiB |

在当前53084存储行下，8对complex128方向的数值载荷为 `2*53084*8*16=13589504 B`，约13.59MB（derived，非实测RSS）。64MiB只限新增模块；内层新Krylov向量、外层V/Z、局部因子、所有FE/端口和运行环境还须计入完整进程树。不得靠留在库内部的未计数CU或持久workspace突破限制。

安全监控必须能在A4/B4回调中看到deadline，不只等待GCROT外循环callback。有限时间到达时返回最后一个完整的小最小二乘更新；接口不能给出中途候选时，可回退到本次已验证的池投影候选，并明确记录丢弃的新工作及原因，禁止误标部分结果已提交。未完成更新不改变持久池。连续两次非零RHS既无可用投影也无合法新方向，或连续三次超过30s，按INNER_COST_BLOCKED停止，不无限返回零、不自动放大时间线。安全资源终止优先于保存。

现有S/p2及局部块的参考型准确性要求、有限精化策略不变，本轮不同时把它们改成不精确算子。rank8只是固定工程候选，不承诺足够描述任意短波问题。

## 6. K0–K1：一次有限准备与序列对照，随后必须进入真实模型

K0读取根/docs/相关源码AGENTS、工作原则、task、最新review/response和summary，确认canonical worktree、branch/base/HEAD/upstream、clean source、ABI、complex128、MPI/线程、系统余量、swap、磁盘和watchdog。只读取本机任务实际需要的历史资料，不重写全历史报告。目录盘点未发现同任务额外task文件；已有补充授权结果以各outcomes索引为准，不把其旧“继续”文字当新运行权限。

K1集中完成最小相关测试：复数投影及解空间反馈、固定状态重放、rank截断、零/相关RHS、配对及约束、输入不变、时间截断、池身份重置、错误隔离、eps闭合及清理。用小型非Hermitian复数矩阵与直接解核对代数，再在原始规模只重核改动影响的native/cached/owner接口；既有A4桥沿1e-10、cached/native沿1e-11。禁止借测试扩大为谱/网格扫描。

固定有限序列为既有六份p4输入：A2R160 g1/g2、LIGHT448 g1/g2、JOINT448 g1/g2，按此顺序各用一次。加载确实存在且hash匹配的数组；缺项明确标记，可继续其余有效项及正式外层，不重建p4/fine LU以补齐测试。

在同一个新驱动中做两条有限序列：RESET在每个RHS前清空池，CARRY仅在第一项前清空；各至多6次I4，总12次。其余算法和工作上限相同，比较累计新B4/A4次数、累计时间、每项native残差、池投影前后残差、rank/丢弃原因，以及已有参考可支持的场差。RESET通常每次生成更多新方向，必须报告实际成本，不把参数相同当作实际工作相同。RESET不是新完整PDE候选，也不重跑旧A长程曲线。

再允许最多2次完整新BAL_H控制（A2R160、LIGHT448的已存合法q）；两次共享一个从空开始的新控制池，实际生成各自反馈g2。随后释放控制池。两次I4目标未达或单次PC残差增加都不阻止原始试跑；有限控制不能被当作完整通过。若两次完整PC均超过90s，只进入至多8步/600s的原始接线成本检查后收口，不展开正式长跑。

**准备/验证/有限控制计算合计上限3600s，有限数值控制子预算900s，互为包含。** 测试按最终改动重跑相关项，不每次做全仓库测试，不因为一个序列向量缺参考而重新进行整套诊断。提交clean prototype后直接K2，不先交一份接口完成报告等待下一轮。

## 7. K2/K3：一次原始求解，成功后立即同配置notch

正式新profile只有一个。原始模型一次、条件notch一次；均零外层初值、空复用池、同一个持续的outer KSP。不得恢复V7的x121/x88，也不得加载有限序列末尾的池。

沿用V7比较口径：每8步和退出前计算原A6真实残差，每32步保存安全解。128步或solve1800s先到时，已达1e-6则完成；否则继续条件是rho不高于1e-2，或至少16步、rho不高于0.30且最后两个完整8步区间均下降、两段几何平均缩比不高于0.80。中间检查不重启KSP、不清池。

继续后在solve5400s检查：尚未达到1e-6且rho仍大于1e-3，保存结果并停止为PROGRESS_INSUFFICIENT_AT_MID_BUDGET。否则继续至solve10800s、workflow14400s或2048步先到者。以上是投入规则，不是数学不可能性定理。没有达成整体进展时不扫描k=16/32、增加内层循环、切到full252或重开子域法。

原始通过残差及输出检查后，立即运行冻结notch；为其重建匹配实体PC，池从空开始，算法/截断/步数/容差不调。缺口失败如实保留，只关闭当前候选的双模型资格；不使用原始R/T/A当作缺口参考。

| 完整验收项 | 门槛与说明 |
|---|---|
| 原方程 | full explicit norm(b-A6x)/norm(b)不高于1e-6 |
| 同模型参考场 | L2、scaled-curl相对差不高于1e-4；同位置selected E/H和近场，近零量另报绝对差，不拟合复相位 |
| 功率和耗散 | R/T/A/A_volume对各自参考绝对差不高于1e-5 |
| 独立守恒 | R+T+A_volume与1之差、A与A_volume之差均不高于1e-5 |
| 全部80模式 | 复幅值向量相对差不高于1e-4，逐通道功率最大绝对差不高于1e-6 |
| 内部与复用 | 未达1e-4如实报告；AU/Q与eps关系、身份、rank和新增内存合同成立 |
| 资源 | 完整同期进程树、系统余量、zero-swap和全部setup/solve/recovery成本闭合 |

不合格场不得产生official输出。允许仅输出工程错误时从同一已收敛解恢复一次，不重新求场。两份参考已存在，不授权新增直接参考。

## 8. 资源、预算与运行隔离

本机有效资源取可见物理/cgroup限额较小值；reserve=max(4GiB,15% effective_total)，launch cap=min(12,000,000,000B,effective_available-reserve)，运行中维持余量。一次一个本机heavy，包含Python/MPI/FFCx/compiler全部后代；系统/作业swap新增按既有合同安全停止，归因不明与数值失败分列。保留现行conservative_realtime，不重开时钟工程。

S/p2底层仍限定8192总行、矩阵/转换/factor/workspace预审512MiB；实体/bubble/owner及原缓存沿V7的256MiB载荷上限，新增recycle模块另列64MiB且都纳入总live-set。不同时保留旧p4 LU、full252或第二套PC。2GB是优化指标，不是正式原始试跑硬入口。

| 计算项 | 本轮上限 |
|---|---|
| K0/K1全部准备与验证 | 3600s，其中有限控制900s；包含编译、失败与兼容适配测试 |
| 原始模型 | 1次，solve10800s/workflow14400s，含筛选与退出 |
| 条件notch | 1次，同上，含其自身setup；不继承原始数值池 |
| 全批计算总账 | 36000s；父/子嵌套不重复计费；文档/等待不冒充计算时间 |
| 不授权 | 第二种recycling、rank/策略扫描、额外原始长跑、新DD/PML、工作站或短波heavy |

5nm分支按其独立授权继续；本review不取消或改变那些授权，不把其进程当本机后代清理，不强行同步另一活动分支。若使用同一远端分支且HEAD前进，先检查改动范围与身份，不在dirty或不明源码上正式运行，不整体merge/rebase其他research分支。

新增池是O(kN4)存储，不能将当前约13.6MB外推为任意规模常数。MPI1适配不声称MPI可扩展；未来应按owner保存、避免每rank复制。S/p2全局因子的规模上限和高阶局部处理的波长鲁棒性仍是未解决项。本轮成功也不能称完全factor-free或0.7nm通过。

## 9. K4收口、证据与停止后的决定

新中心文件建议为 `outcomes/recycled_p4_outer_v8.md`、`outcomes/records/recycled_p4_outer_v8.json`，更新summary、run_index、test_summary、两本项目总账及handoff；统一新增response_v9.md，不修改旧review、旧response或负结果。状态入口清晰，禁止在summary顶部无限追加相互矛盾的“最新/待审”。

至少记录：profile/源码/ABI及GCROT实现身份；每I4的RHS序号(g1/g2)、开始/结束rank、实际新方向/B4数、全部A4作用分类、池投影与最终native残差、eps范数、截断/重置原因、orthogonalization/update耗时、池及临时bytes；外层逐8步曲线、完整成本/RSS与物理输出。每32次I4保存小型Gram/身份摘要；不把每个长向量逐调用写盘或进入Git。

持久池只驻留当前模型的求解过程；检查点可保存有限池供审计，但本批不授权加载它续跑或为新正式模型预热。正常终止保存解与最终残差，释放外层/内层、池、S及实体因子和无用数组，记录RSS变化后恢复输出；清理全部本机后代。

K4必须回答：

1. CARRY相对RESET在这组输入上是否减少实际总工作；哪些输入受益或退化，不能只挑最后一项。
2. 原始/notch是否完成；与V5成功基线和V7失败基线在相同残差/时间口径下如何比较。
3. 成功若只依赖复用池长期积累，rank、方向替换及不同RHS的收益是否有记录；不能宣称发现了普遍低秩困难空间。
4. 整个程序实际省多少内存、增加多少时间；1e-4未达占比如何；不能只报告约13.6MB。
5. 若失败，是接口/数值故障、资源/成本阻碍，还是有限rank候选对完整问题没有足够收益；不得自动归因所有recycling无效。

只有两模型全部Gate通过才标 `RECYCLED_P4_TWO_MODEL_PASS`；仅原始通过为 `ORIGINAL_PASS_NOTCH_UNQUALIFIED`；受控未完成为 `RECYCLE_BOUNDED_NEGATIVE`，缺实现能力为 `RECYCLE_IMPLEMENTATION_BLOCKED`。成功但比V5更慢必须标注memory/time tradeoff。有限序列改善但外层失败也按整体负结果收口，不继续扩rank。

**本批结束不自动转入更大子域。** 若本候选无整体收益，下一份设计才评估跨多个单元的完整物理子域，并对照旧16-slab/当前patch的区别；不能在本轮末尾临时再追加一个PC。继续探索的对象应由本批结果决定，而不是由剩余预算决定。

## 10. 提交计划与方法来源

先提交通用recycled I4/安全返回/数据适配与focused测试，再以clean SHA执行有限控制和原始/条件notch，最后提交outcomes、总账和response。ChatGPT只新增本review，Codex实现/执行；不amend、不强推、不merge master。正式保存input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json及原/新profile、mode/map/cache/环境和artifact hash。

方法来源仅用于构造和界定算法，不给当前Maxwell问题提供通过保证：

- [SciPy gcrotmk](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.gcrotmk.html)：flexible GCROT、complex/LinearOperator、CU复用和截断。实施须核对本地版本的实际源码，不能只按在线参数描述推测工作量。
- [PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：右预条件FGMRES允许内部非线性/变化求解；本轮外层不替换。
- [Hicken与Zingg，2010](https://epubs.siam.org/doi/10.1137/090754674)，A simplified and flexible variant of GCROT for solving nonsymmetric linear systems，SIAM J. Sci. Comput. 32(3)，1672–1694（页码以出版社记录为准）。本轮不混称为GCRO-DR，也不另开文献调研任务。

**交付核心：只用一份固定小容量复用池，确认低存储实体粗逆能否在重复调用中积累有效信息，并在完整原始与非可分三维模型上取得可核验的结果。不是证明一个内部样本终于达到某个数字，也不是重新罗列所有PC。**
