# Review V18：把 Ny=8 推进到整场资格，形成 E1 的当前容量结论

## 0. 主审裁决与本轮成果要求

**V17 有实质进展，裁决为 pass_with_qualifications。保存局部系统上的恢复问题已经关闭；真正按行分块的 CSR 构建已在 Gx560 完整场中通过；原尺寸几何拓扑和 q 结构上界也已有新证据。下一轮重点是完成 Ny=8 的完整参考算子资格并争取小型非可分整场，把 E1 从“当前对象账不完整”推进到实测阶段容量，以及明确最终网格与单场成本之间的关系。**

最终目标继续为：真空波长 **0.7 nm**、原尺寸 **50×25×140 nm**、真实非可分三维材料/几何、complex128 Nédélec H(curl)、x/y Floquet 与 z Fourier-DtN；**2,000,000,000,000 B 左右整机物理内存且留系统余量，任务零 swap；单场必要准备、构建、求解、恢复、输出和检查全过程不超过 172800 s。**

当前目标状态仍是 **NOT_QUALIFIED**。这个结论表示证据尚未闭合，没有证明目标不可计算。V17 的小 A6、能量闭合和 CSR 上界各自有用，分别解决代数求解、物理输出一致性和结构容量的一部分问题。[S1]–[S5]

| 对象 | V18 审阅结论 | 后续处理 |
|---|---|---|
| S2 保存局部恢复、P4 保存端口读回 | 接受已完成的有限范围闭环 | 复用已通过数据；相关代码未变则不重跑 |
| V17 row-tile / Gx560 | 功能和完整离散场通过 | 继续显式研究路线；不以重复三步收敛作为主要新增成果 |
| Ny=8 native maps / RHS | 已有真实组件证据 | 完整参考算子及正式 solver 接入仍需完成 |
| E1 当前 p6 reference 路线 | HELD_INCOMPLETE_CURRENT_OWNER_EVIDENCE | 用当前构建与生命周期测量形成完整准入判断；安全即继续整场 |
| 原尺寸结构 | 实测拓扑 + 派生保守界 | 审计推导、收紧结构/索引界；尚无目标 p6 CSR 或因子测量 |
| 原尺寸精度、2 TB / 48 h | NOT_QUALIFIED | y/z/模式截断、因子填充和端到端成本继续推进 |
| 本轮执行位置和分工 | 既有 Task40 本机链路 | 执行者实现/测试/运行；主控冻结源码并集中提交推送 |
| master / ordinary default | 保持研究分支和显式 opt-in | 本报告不批准合并或修改普通默认路线 |

**本轮优先交付新的科学或工程能力：一个完整 Ny=8 算子资格及条件整场、E1 当前实现的实测阶段容量、可复核的目标结构与成本模型。** 普通 bug 采用定向修复后继续，某一路线的真实失败只停止依赖该失败的后续计算。

## 1. 固定审阅身份与证据范围

| 项目 | 本次固定值 |
|---|---|
| repository | Rookie1234567/MyFEniCS |
| execution branch | task40extra_0p7nm_engineering |
| 审阅 base HEAD | 57f20cc66b3de65c696def2b9bf783ddcbfce55e |
| base 提交时间 | 2026-10-08T07:32:12Z |
| base 提交说明 | docs(task40): close Review V17 with qualified numerical and capacity evidence |
| Gx560 V17 实际数值源码 | cbdcc12812b439f5252949ad1279331b86a2dbb6 |
| B0 row-tile 实际组件源码 | ca913307d3cdd5a455c2718138bf2089151b3887 |
| Ny=8 maps/action 实际源码 | d790964079628e7fadaa84354bc209db4262ecb9 |
| 输出 checker 后续修复源码 | 23626f44243d19d58af41d15a8ccafcba41ee54b |
| canonical worktree | /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering |
| 已记录计算环境 | WSL2；PETSc complex128/int32；MPICH；MPI1、数学线程1，以每次 ABI receipt 为准 |
| 本报告 / 下一轮回应 | review_report_v18.md / response_v18.md |

本次读取了 V17 response、四份 compact、run index、summary/test summary、六次相关实现提交，以及 row-tile、原生 Ny=8、worker、MUMPS 与输出 checker 的相关源码。对四份 compact 和 response/summary/test summary 的**七份远程 UTF-8 内容**重算 SHA-256，并核对 Git blob 身份，均与登记值一致。这是远程文档内容身份复核，没有重新运行 PDE 或重算本机 ignored 数值数组。[S1]–[S7]

本报告在提交前检查数值合计、Markdown 表格列数、围栏、14 个固定来源引用和行尾空白。没有运行仓库 pytest、FE/PDE 或 CI；GitHub 网页实际 rendered view 未验证，不能把源码读取当作网页渲染验证。

Ny=8 maps/action 的原始工件路径及 SHA 已登记，但该 ignored 文件在此远程 commit 的读取返回 404；compact 未给出具体异常栈和失败数值。因此本报告不能将其归因为某一个维数、相位或数值错误。P0 应由本机执行者提取已有原始收据中的具体失败点，无须为了获得异常说明先重做 FE。[S2]

本报告只新增审阅文档。后续实施仍在上述 canonical worktree，不另建聊天、项目、checkout/worktree，不启用 collaboration subagents 或 Codex 定时任务，不 SSH、不操作工作站、dot、Task042 或其他项目。最新 V18 执行合同覆盖旧导航的 review 序号；历史原始记录保持不变。

## 2. V17 已完成什么

### 2.1 Gx560 完整离散解成立，物理尺寸必须正确表述

Gx560 是原尺寸解析几何按 **7/135** 缩小后的模型，实际周期约为 x=2.592592593 nm、y=1.296296296 nm，z 从 −0.518518519 到 6.740740741 nm；仍使用 0.7 nm 材料与波长。它有 560 cells（10×4×14）、p6、340 个有序模式，并由四 q p6 reference PC 修正真实非可分 target 算子。[S1]、[S4]

| 指标 | V17 已记录结果 | 解释 |
|---|---:|---|
| 外层迭代数 | 3 | 求解器迭代证据 |
| 释放后完整原 A6 | 4.7044300024e-9 | 通过 1e-6 |
| 独立 native A6 witness | 4.7043098759e-9 | 通过 1e-6 |
| R | 0.07612406709 | 官方输出 |
| T | 0.90576922010 | 官方输出 |
| A_balance | 0.01810671281 | 官方输出 |
| A_volume | 0.01810671258 | 与 balance 相差约 2.37e-10 |
| V17/V16 保存场比较 | 已报告的场/模式差均为 0 | 同物理、网格、MPC、carrier、模式身份；输入文件字节 SHA 不同 |
| 四 q rows | 28508 / 28508 / 28576 / 28508 | 实际结构 |
| 四 q NNZ 合计 | 62024788 | 实际存储槽数 |
| 三次实际 PC | 初始状态均通过，无整体增广修正 | 不能据此声称本次生产轨迹调用过修正分支 |

三次 PC 的 q 真残差最大值分别约 2.930e-11、2.964e-11、3.857e-12，均通过原 strict 1e-10；native complete FE 最大约 1.144e-10，alpha closure 最大约 1.852e-13。原 V15 bounded/native/budget/closure 合同保持。[S4]

输出 checker attempt04 的 row-tile 和 admission-ledger guards 均非空且通过。它依据保存的已完成 CSR 范数和账本重新检查 guard，**没有重新作用整个数值 operator**。旧 guard 为空的基础 receipt 保留为历史记录，不能替代 attempt04。[S4]、[S7]、[S12]

这些是可靠的实现一致性和离散求解证据。它们没有增加原尺寸的 y/z 分辨率，也没有形成新的网格收敛结论。

### 2.2 性能有观察改善，主要时间仍不在 KSP

以下 GB 均为十进制；RSS 与 cgroup 是不同观测口径，不能相加。

| 同范围指标 | V16 | V17 | V17 相对变化 |
|---|---:|---:|---:|
| run_case 父段 monotonic | 2274.267 s | 2112.682 s | −7.10% |
| 进程树 RSS 峰 | 10.205 GB | 10.134 GB | −0.70% |
| 专用 cgroup memory peak | 11.908 GB | 11.170 GB | −6.19% |
| 同时四 q factor allocated upper | 4.692 GB | 4.692 GB | 未减少 |

V17 worker 约 **35.21 min**，其中 KSP.solve_only 为 **71.631 s，占 3.39%**。四个 numeric factorization 子阶段合计约 16.437 s；它们既不是完整 setup，也不能再加到父时间上。三步收敛已经很好，下一项时间优化应从实际占主导的构建、准备、native 检查、恢复/输出父阶段中选择。[S5]

这两次单次观测的 CPU 供给、宿主状态和缓存条件没有形成受控对照，不能将全部差值归因于 row-tile。B0 的 candidate 构建 60.538 s、legacy 59.266 s，candidate 在这个组件上没有更快。完整单场冷启动时间仍 unknown，因为必要 checker 的边界未与 worker 完整闭合；版本间资格比较等一次性开发工作也需从每场必要工作中明确分列。[S1]、[S3]、[S5]

### 2.3 已关闭的恢复问题直接复用

S2 原始 complex128 保存系统上，直接 LU 的 top/bottom forward error 为 2.203e-11 / 2.424e-11，超过原 1e-11；同因子、原方程残差驱动的修正后为 5.352e-14 / 5.143e-14。独立 checker 重新打开保存数组后通过。top 尝试 2 次、接受 1 次，bottom 尝试并接受 3 次，直接 LU 负结果保留。[S2]

P4 独立 D 读回覆盖每面 882 个原生行、每面 16030 个有序模式；D/端口作用与独立 plane phase/Hp 检查通过。它们关闭保存系统和有限向量组件的相应问题，没有证明完整目标算子的所有列。

**V18 不再把这些已通过的保存组件设为所有工作的前置重算任务。** 仅当新实现改变其依赖时做对应回归，也不自动对每个 production cell 强制加入三次修正。

## 3. 两个关键缺口与一个优先优化点

### 3.1 Ny=8 的剩余工作超过“再修一个映射断言”

实测 Ny=8、局部窗 ell=2、平移副本 K=4，160 global cells、每个 twist 40 local cells。八个 FE q 全部存在，532 个有序模式覆盖一次；q=0…7 对应端口数为 **[76, 76, 76, 76, 0, 76, 76, 76]**。

q=4 只是端口集合为空，不能删除其 FE sector。RHS 独立保存向量检查有 26 项通过，最大 source-fold 缺陷约 3.944e-15，重构缺陷约 6.235e-16；固定 C alpha witness 仍只是一条向量证据。maps/action worker 保留 WORKER_FAILED、raw 为 PARTIAL_COMPONENT，完整 off-diagonal 算子资格尚未完成。[S2]

源码中 generic Ny transport 已独立存在，但生产 builder 仍要求 y 轴节点数为 5，多处完整性检查仍固定 range(4)，生产 inverse 仍检查四个 factor。因此 Ny=8 maps/RHS 成功不会自动形成八 q 正式 PC。[S8]、[S9]、[S10]

有价值的扩展方向是保持 ell=2，Ny=K×ell：

```math
q=b+jK,\qquad b=0,\ldots,K-1,\qquad j=0,1.
```

Ny 从 4 到 8 增加 twist/q 数；在相同 x/z 网格下，局部窗仍只有两个 y 单元。这为 y 细化提供了结构清楚的实现路径。**这是源码结构支持的工程推论，不是因子内存严格线性或迭代数不变的测量承诺**；模式分配、原生映射、局部度量与完整 target 成本仍须实测。[S8]

尤其要区分：应满足 q 非对角小量门的是 **沿 y 平移不变的 regular reference**。真实三维缺口的 target 会耦合 q；不得把 target 非对角项删掉以强行满足 reference 的对角化门。

### 3.2 E1 尚未得到当前实现的总体容量判断

E1 当前库存为 760 cells、156 raw geometry classes、231 oriented classes；派生 assembly workspace payload 上界为 **5.559 GB**，装配后 retained numeric owner 公式为 **2.877 GB**。每个 oriented class 对应约 12.449 MB 的该类 retained 公式，但这些不是整个 solver 的同时峰值。[S5]

V17 缺少体积对象、raw/oriented tensor、Schur/cache、q CSR、PETSc、factor、恢复/输出之间的完整阶段交叠账，且没有当前 E1 的 OS/cgroup 释放测量，所以 release credit=0。历史 19.193 GB 来自 V15 投影，不能当作当前 V17 的精确需求，也不能据其永久拒绝任何当前构建测量。

E1 的新状态不是一次 numeric 不收敛，也不是 V17 新的 resource stop。下一步应安排**有局部上界和逐阶段停止能力的当前构建测量**，补齐账并实际压缩可证明无用的对象交叠；若仍无法安全容纳，则给出具体缺口，而不是只有相同的 HELD 标签。

### 3.3 优先候选：完成非对角行块后立即计算范数并释放

当前 V17 的 pattern 已按行分块，但 numeric pass 仍累加到四个完整 CSR。源码明确保留 00/01/10/11 四块直到完整 Frobenius gate，随后才返回对角块。Gx560 两个 sector 的四块 payload 分别约 **1.243 GB / 1.239 GB**；它们顺序构建，不能把 2.482 GB 相加当同时内存。[S3]、[S4]、[S10]

允许实现一个明确选择的候选：对不相交输出行块，完成该块的**全部贡献累加、重复项合并及抵消**后，计算非对角块范数并释放，只保留后续 factor/真残差需要的对角 CSR。完整范数可按以下恒等式累计：

```math
\|A_{01}\|_F^2=\sum_t\|A_{01}[I_t,:]\|_F^2,\qquad
\|A_{10}\|_F^2=\sum_t\|A_{10}[I_t,:]\|_F^2.
```

I_t 必须是不重叠且覆盖全部输出行的分区；每个 tile 的条目必须先累加完整。不能累加各 contribution 的范数来替代最终矩阵范数，也不能用若干随机作用向量替代原完整 operator/off-diagonal 门。沿原同一 diagonal scale 归一化并保持 1e-11。[S10]

这种做法可能减少构建时的存活量，但它是**尚未测量的新候选**。需要记录路由、spool、重读、projection 次数和真实 I/O；不要为了节省矩阵存储而隐藏 FE/Hhat 的大量重复生成，也不要将磁盘描述符/行块 staging 混称为 MUMPS OOC。它不保证独自关闭 E1，最终是否保留由真实峰值、额外时间和功能资格决定。

## 4. Ny=8 连续推进合同

### N0：先消除失败原因不透明

从 V17 原始 attempt02 读取异常类型、最后已通过阶段、首个失败 gate、实际值/尺度/门限、traceback 和进程退出原因，保留原 attempt/source/hash。若文件没有相关字段，明确写“原收据缺失”，用最小组件重现定位；不补写旧收据。

先区分工程中断与真实数值门失败。q=4 空端口的已修复问题不能被重新解释为 FE q 缺失。失败定位与 E1/目标结构工作无依赖，不阻断它们。

### N1：完成参考算子的完整资格

复用当前 160-cell、ell=2、K=4、532-mode 的实际 FE 组件和冻结物理身份，补全以下内容：

- 八个 q、四个 twist、全部 interior/edge/face 原生映射、primal/dual fold/lift、Bloch seam、非零 RHS 和归一化保持原门。
- 对 regular reference 的 FE、端口左右耦合、D/H 及凝聚贡献完成所有必要列或等价的完整分块比较；禁止只有一个 C alpha witness 却标 full C PASS。
- 可以逐列/逐行块流式核对完整离散算子，避免大矩阵同时驻留；覆盖范围、遗漏数量、各块 Frobenius/相对误差须可审计。
- 优先利用原生局部 tensor、凝聚恒等式和覆盖全部贡献的分块装配完成资格，避免对每个全局基向量重复一次完整 FE 构建。
- 完整 off-diagonal gate 使用原 1e-11；mapping 原 1e-12。独立 oracle 不能直接复用候选同一 fold/lift/condensation 结果作为答案。
- 保存 q=4 零端口与非零 FE RHS、非 Hermitian 复材料、非平凡 y 相位的必要负例/实体见证。已有 B0 的 azimuth=5° 身份继续使用。

关键实现进入 src 的通用模块；benchmark/driver 负责编排和收据，不把正式算法留在 ignored 脚本。对无关模块无需全仓回归。

### N2：接入显式 Ny=8 生产路径

N1 完整通过后，允许将泛化连接到实际 launcher → run_case → worker → profile → reference builder → factors → inverse → checker。依据实际 Ny/q inventory 构造并验证集合，不使用“改几个 range(4)”作为完整设计。

至少核对 q 配对、端口空集合、所有 mode identity、八份 factor 的生命周期、每次 PC 的 q solve 次数、修正与 residual budget、真实非可分 target A6、恢复及官方输出。旧 Ny=4 路线保持明确回归；影响其数值依赖才运行必要完整 anchor。

Ny=8 沿 V15 数值合同扩展**计数**：一次初始 PC 完整处理八个 q；至多一次完整增广修正，即至多额外八次 q MatSolve，分别报告真实调用数。不得将每 q 的限额放大成任意次数，也不得悄悄改变整体误差预算或归一化尺度。

### N3：条件性完成第一场 Ny=8 非可分 target

N1/N2 通过、源代码冻结、真实资源与剩余时间允许后，**直接完成一个 4×8×5=160-cell B0-Y8 p6 非可分整场**。它继承 B0 的解析几何、材料、0.7 nm、grazing=1°、azimuth=5°、s 偏振、532 ordered modes 和 x/z 轴，仅将同一 y 区间均匀二分。原 B0 输入及模式身份以 [S13] 和实际保存场为基线，不能混入 Gx560 的另一入射/模式身份。

比较对象优先用已通过恢复/checker 的 B0 Ny=4 保存场，核对 source、物理、几何、模式和采样身份后，在共同物理坐标/子单元上比较 E/H/scaled-curl、散射场、R/T/A 和完整衍射级。跨网格不比较自由度编号数组，不拟合全局相位。

整场代数与物理 gate 通过后，这项结果可称“Ny=8 正式小模型接入通过”；Ny4/Ny8 差值是**小模型方向细化观察**。x/z 很粗，不能据一对 y 网格宣布原尺寸 y 收敛或整个解已准。若 y 变化大，也应保存真实场并继续分析，不把它误当 solver bug。

如果 N1/N2 的真实问题阻断 N3，继续 E1、稀疏生命周期与目标结构工作，不以调低门限换 Ny=8 整场资格。

## 5. E1：通过当前构建测量作出可执行的容量决策

### 5.1 先形成阶段与独立 backing 的账

从旧 Gx560/E1 收据和当前源码建立一个轻量 owner 表，每项包括独立 backing 标识、字节、持有者、首次分配/最后使用、alias 关系、可否释放及依据。只围绕实际分配前后的关键边界记账，不为每个 scalar 建平行账本。

必须覆盖：target volume/native action、regular/global/local FE 对象、raw/oriented tensors、local LU/Schur/recovery、映射/transform bank、四 q CSR、PETSc 输入矩阵、MUMPS symbolic/numeric、Krylov、PC 检查、完整恢复和输出、必要 checker。source/canonical CSR 可能 alias；PETSc/MUMPS 是否复制要记录实际接口与观测，不能按对象名猜。

当前 MUMPS wrapper 会保存 source/canonical 输入、显式转换数组、PETSc 矩阵和 factor；对输入的保留承担真残差与身份检查职责。删去其所需原矩阵并不构成合格节省。[S11]

在每个峰值候选阶段同时记录 unique backing、进程树 RSS、cgroup current/peak、任务 swap 与将要分配的保守上界。释放 credit 以生命周期和实际观测为依据；Python del 不等于 RSS 必然下降。已经包含在当前 RSS 的存活数组不再追加成未来增量。

### 5.2 允许安全的 E1 分阶段构建，而非等待未知项自行消失

原 E1 保持 10×4×19=760 cells、p6、588 ordered modes 及原三维缺口。先从几何/类库存和当前代码给出**下一有界构建阶段**的增量上界，在独立 watchdog 下逐步测量；每个阶段前检查：

```math
M_{\rm current}+\Delta M_{\rm next}+R_{\rm required}
\le M_{\rm effective},
\qquad
\Delta M_{\rm next}+R_{\rm required}\le M_{\rm available}.
```

按现有 resource policy 解释 effective/available 与已扣余量，避免重复计入。对尚不可证明的未来项用保守上界；不能写 0，也不能把已知不安全的完整 build 当测量手段。小的安全前缀可以完成，受影响的大阶段在分配前停止。

优先实施已证明最后使用结束的 build-only owner 释放，以及第 3.3 节候选。raw/oriented 缓存是否共享，必须基于精确几何/材料/方向身份；不新增尺寸舍入合并不同单元。

阶段目标是：**当前真实几何/类构建 → 当前 q CSR → all-q symbolic → 基于当前存活量和 symbolic 的 numeric/startup/KSP/恢复输出准入**。symbolic 本身也要受资源门监督；可以报告安全前缀，不强行走到全部四 q。

一旦全部后续阶段有可解释的资源上界、剩余固定窗口可容纳完整必要流程，主控冻结后继续 E1 numeric、startup、KSP、恢复和 checker，无须再向用户逐阶段请示。若同一进程中前缀仍有效，尽量继续使用；若仅保存了证据而非可恢复对象，重建成本如实计入，不能假装免费复用。

### 5.3 若 E1 仍不准入，给出明确缺口与已实现收益

回应至少列出：停止前最后实测阶段、当前存活量、下一阶段上界、系统余量、实际有效 cap、缺口字节、最主要两类 owner、已做的释放及测量差值。旧 19.193 GB 和历史 6.530 GB future factor 估算只能作为历史对照，不能代替本轮总投影。

第 3.3 节候选是否保留，应由一次相关实体组件及必要完整场的结果决定。若增加了显著重放/I/O 且没有达到需要的同时内存收益，保留负结果，采用已经合格的 V17 路线继续其他工作。不同阶段的峰值、两 sector 之和、payload 与 RSS 均不混算。

## 6. 面向原尺寸 2 TB / 48 h 的下一步证据

### 6.1 接受拓扑实测，审计并收紧当前结构界

V17 已实际建立 272×4×14=15232-cell 目标几何拓扑，并用 224-cell 原生 p6/MPC 校准推导完整计数。目标 p6 space 尚未建立，以下不是目标数值 CSR 实测。[S3]

| q | 派生 rows | structural NNZ 上界 | 一份 CSR payload 上界 |
|---|---:|---:|---:|
| 0 | 781500 | 1766802960 | 35339185204 B |
| 1 | 781604 | 1784757520 | 35698276820 B |
| 2 | 781624 | 1788212800 | 35767382500 B |
| 3 | 781604 | 1784757520 | 35698276820 B |
| 四个不同 q 合计 | 3126332 | 7124530800 | 142503121344 B |

full-storage 10228620、periodic-independent 9948672、interior 6854400、trace 3094272 也是拓扑加原生校准的派生计数；trace 与加端口后的 q 行数合计不要混淆。

当前最大结构 NNZ 上界 1788212800 小于 int32 最大值 2147483647，余量为 359270847。这个 PASS 只限当前候选 FE/CSR 的形状、列号和 offset 上界；没有证明更细 Ny/z、更大 mode cutoff、PETSc 转换临时偏移或 factor 内部所有索引安全。

本轮继续在本机有界资源内完成：

- 将目标 support 上界的推导与实际实现入口纳入可复用、受版本控制的计数器，说明哪些来自实际拓扑、哪些来自校准、哪些是保守并集。
- 对边界、周期 seam、全部方向排列、所有 target x/z 代表、q 端口分组逐项说明覆盖证明。抽样可校准实现，但仅抽样不能证明全目标上界。
- 用压缩 stencil、区间或逐行块计数收紧界；记录结构槽数、可能抵消/数值非零的区别。无法得到精确 NNZ 时继续保留可证明的上下界。
- 对计划的 Ny=8 候选重新计数 q 数/rows/modes/类数和索引上界；不能复制 Ny=4 的 142.503 GB 作为新网格容量。
- 不分配原尺寸完整 q 数值 CSR、全局 factor 或 target PDE；若某一步连结构本身都不能安全容纳，报告最大已覆盖部分和未覆盖量。

当前 target 几何有 29 raw / 60 oriented classes，而 E1 为 156 / 231。**按 cells 线性外推局部缓存并不可靠**；容量模型应显式保留几何/材料/方向类数这个变量。[S3]、[S5]

### 6.2 把 142.503 GB 变成预算约束，而非可行性承诺

该数是一份四 q CSR 的保守载荷之和，不含 factor 填充、不含其他必需对象，也不是观测到的同时峰值。对每个实际阶段使用：

```math
M_{\rm peak}
=\max_s\left[
 M_{\rm target/local}(s)+M_{\rm qCSR/PETSc}(s)
 +M_{\rm factors}(s)+M_{\rm work/output}(s)
\right].
```

只有时间交叠的独立 backing 才同加；物理 RAM 内另留实际系统和其他必要占用。对可证明同时保留的因子，允许的总 factor 预算应由剩余空间反算：

```math
B_{\rm factor}
=B_{\rm physical}-R_{\rm system}
-M_{\rm other,\ simultaneous}.
```

然后比较当前规模 actual symbolic/numeric 的可靠信息及对目标的有依据估计，明确 raw INFOG、解码方法、allocated/used、未知量和误差范围。不能把 Gx560 的 factor/CSR 比例乘目标 CSR 上界就宣布通过，也不能把单 q CSR 小于 2 TB 当作整体通过。

以现有 ABI 继续安全研究。当前 CSR int32 上界通过，不等于所有将来规模已经通过 32 位资格；实际出现超限字段时先形成具体 64 位依赖/迁移清单，本轮不重装 ABI 或切工作站。

### 6.3 原尺寸精度要由方向对照选择最终网格

0.7 nm 的缩小几何和原尺寸几何相差 135/7 的线性尺度；Gx560 不能代理原尺寸分辨率。当前候选 Ny=4、z 常见 10 nm 间距既不能仅按真空 k0h 判死，也不能凭 p6、三步迭代或能量闭合判准。固定斜入射分量、材料响应、三维散射与倏逝近场共同决定误差。

本轮先完成 Ny=8 的接入和小模型 y 观察，并整理已有同几何 x、z、模式阶梯的保存场。下一张用于工程精度的网格需要明示唯一变化、比较对象及成本，不同时改 y/z/mode cutoff 后笼统称“更细”。

保持既有方向观察目标：E/H/scaled-curl 相对变化 1%，R/T/A/A_volume 绝对变化 1e-3，并单列散射场、界面邻域和显著衍射级。它们是工程观察门，两个网格接近最多称 tested agreement，不等于连续极限证明。[S14]

原尺寸的 32060 AUTO 传播通道库存并不自动覆盖最终倏逝截断资格。每增加模式要重新审计端口耦合、q 图、局部缓存和 factor，而不只计算一个 dense M×M 对象的字节。原尺寸 x/y/z 与通道资格继续明确为未完成。

### 6.4 新必要运行必须直接闭合单场时间

在下一场必要完整运行外层记录统一 t_start/t_end，包含必要 ABI/JIT/准备、volume/local condensation、q pattern/numeric build、symbolic/numeric factor、startup/native 检查、KSP、恢复、释放、官方输出与必需 checker。

输出一个互不重叠的父阶段时间表和最大实际同时内存阶段。子阶段可以嵌入解释，但不再叠加进总时间；不把 worker 减 KSP 的差额全部命名为装配。一次性版本比较、软件资格、开发修复与每场必需检查分列，当前 campaign charge 另列。

从现有 Gx560 events 可提取的时间直接提取，缺失保留 unknown，不为补计时重跑历史 PDE。新运行应至少回答：最大父阶段是什么，是否反复构建同一类对象，增长由 cells、class、modes、q 数还是 factor 支配，哪些阶段已有可复用且计入读写成本的资产。

**48 h 的最终判断需要原尺寸、精度合格网格上的完整关键路径。** 本轮的有价值结果是缩小其中可测的未知项，并形成可以代入实测数据的预算；没有足够规模的数据时保持区间/假设，不给单一乐观时长。

## 7. 执行顺序、必要整场和普通 bug 处理

| 阶段 | 具体工作 | 依赖和继续规则 |
|---|---|---|
| P0 | 核对当前 source/worktree、固定窗口、run index；提取 Ny=8 原失败点及已有 Gx/E1 计时与 owner | 不重跑已通过保存恢复；不刷新窗口 |
| P1 | N1 完整 Ny=8 参考算子资格；实现显式 N2 接口 | P1 失败不阻断 P2/P3 |
| P2 | 当前 E1 阶段 owner 账与安全构建测量；必要生命周期/非对角行块候选 | 软件边界 + 实际 B0 四块 oracle；冻结数值源码 |
| P3 | 目标支持计数推导/索引审计、Ny=8 候选计数、端到端计时接入 | 不依赖 E1 完整准入 |
| P4 | N3 条件 Ny=8 B0 整场；E1 资源与时间允许即完整运行 | 一次一个 heavy；通过后继续保存场对照 |
| P5 | response_v18、四份 compact、summary/test summary、run index 与项目账本 | 正负结果及 unknown 分开；主控集中提交推送 |

P1/P2/P3 可由既有主控安排独立工作的先后，不新建执行者或同时跑多个 heavy。建议在续作前段就完成 Ny=8 首次完整资格尝试和 E1 首个当前阶段测量，避免将新能力全部推到窗口末尾。

必要整场遵循变更影响和复用：

- 新 Ny=8 整场按 N3 执行一次正常资格运行。
- E1 安全即作为当前更大非可分 anchor；不先机械重跑 Gx560/Gx784。
- 若改动影响旧 Ny=4 数值语义而小组件不足，先做一场必要 B0 Ny=4 完整 anchor；身份匹配时复用其保存基线。
- 若 E1 不准入，但新的共享稀疏/生命周期路径仍缺中型完整资格，可以安排一场 Gx560；说明它验证的实际变化。若代码未影响该路径则复用 V17。
- 正常科学配置优先收敛为 Ny=8 B0、条件 E1 或必要 Gx560、以及确有需要的 Ny=4 B0，避免形成一组无判别力扫描。已通过场的 checker/输出修复使用保存场重放。

所有新增 case 在运行前一次性核对实际 allowlist/profile/window/dispatcher/worker/checker 链路。保留 wrong-stage、wrong-window、wrong-profile、错误 source/input、漏 q/漏 mode、非空 V18 guard 的必要负例；不只测试孤立 helper。

普通 NameError、可定位 shape/序列化错误、scope/ABI 注册、checker 或可证明 owner 生命周期错误，应在当前窗口内最小修复、定向验证、由主控冻结源码后继续受影响阶段。有效保存场不因后处理错误重解。实现发生变化时 receipt 绑定实际运行 SHA，禁止边算边热改。

同一根因已重复失败时，切换到有判别力的局部重现和调用链检查，不原样第三次启动重 PDE。修复后的必要受影响重放是当前工程工作，成本继续计入；不得用“bug”名义反复筛选更快样本或延长窗口。

NaN/Inf、真实身份/物理/数值门失败、任务 swap、资源不足或窗口截止，停止受影响路径并保留原始证据；仍可继续不依赖它的安全工作。中间迭代未到终态残差不是应立即停止的最终失败。主控状态询问不是 kill 指令。

## 8. 固定窗口：V18 继续现有剩余预算

本次审阅时 V17 固定窗口尚未到期。**V18 不新建或刷新 24 h 窗口**，继续以下已经存在的窗口：

| 字段 | 固定值 |
|---|---|
| 路径 | benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/campaign_window_v17.json |
| SHA-256 | 83f47e542dc28309d398a55c6b7e1b1ca76dab25dead854d88cc6feb6758ed24 |
| T0 UTC | 2026-10-08T00:38:07.073088478Z |
| deadline UTC | 2026-10-09T00:38:07.073088478Z |
| deadline 新加坡时间 | 2026-10-09 08:38:07.073088478 +08:00 |
| 收口保留 | 600 s，按现有 campaign API 执行 |
| 最新已提交 observation UTC | 2026-10-08T06:54:16.097512Z |
| 当时累计保守 charge | 22569.025418519 s |
| 当时 remaining numerical | 63230.974581481 s |

以上 remaining 是 **as-of snapshot**；审阅、文档、等待和后续工程仍继续消耗同一窗口。续作必须先调用现有 API 观察当前剩余量，不能复制旧 remaining，也不能用新 review 文件名开新时钟。API observation、monotonic 运行时间、UTC 差值和 campaign charge 分开。[S5]

若用户转交时窗口已结束，则保存/整理已有结果并收口，不从本报告推出一个自动重开的新计算窗口。24 h 是当前开发窗口，最终单场 48 h 是另一个目标，二者不得混用。主控需要新增运行入口登记时，应绑定这份现存窗口，不能仅因为 review 变为 V18 就要求另一份新 manifest。

## 9. 数值、物理和资源门保持

| 项目 | V18 合同 |
|---|---|
| p6 reference PC | NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15，保留原 strict 结果和 FAIL |
| actual per-q bounded solve、native FE、非抵消 budget | 各原 1e-8 条件与原/冻结归一化尺度 |
| 初始 factor probe / 旧 strict q 检查 | 原 1e-10，分别报告 |
| alpha closure | 原 1e-9 |
| decomposition closure | 原 1e-10 |
| 完整增广修正 | 每 PC 最多一次；四 q 最多额外 4 次 MatSolve，八 q 最多额外 8 次 |
| target 原 A6、释放后 A6 | ≤1e-6；原 target identity 1e-10 |
| 能量闭合、两种吸收一致性 | 原绝对 1e-5 |
| 同离散实现/参考比较 | E/H/scaled-curl、显著复振幅 1e-4；R/T/A 绝对 1e-5；逐模式功率绝对 1e-6 |
| mapping / regular operator off-diagonal | 原 1e-12 / 1e-11 |
| 局部 known-state 恢复 / 原与约化方程 | 原 1e-11 / 1e-10 |
| 离散方向变化 | 另按第 6.3 节工程观察门，不套用同离散实现一致性门 |
| 计算配置 | 零初值；FGMRES restart=32、max_it=2048；MPI1、数学线程1、complex128 |
| MUMPS | 既有后端/排序/主元/BLR/OOC/线程设置；不做参数扫描 |
| 资源 | 现场物理/cgroup 余量与独立 watchdog；任务零 swap；一次一个 heavy |

保持原材料、缺口、完整有序模式、Floquet、DtN 和 p6 target；不以减少模式、提高损耗、抬 resource cap、切低精度或删除真实 q 耦合制造通过。任何未经本报告定义的数值合同更改单独审阅。

## 10. 交付要求和下次审阅标准

沿现有四份 compact 的组织，提交轻量证据和 raw 路径/hash；大矩阵、场、因子、完整事件日志留在既有 artifact/results 中。

| 文件 | 必须回答的问题 |
|---|---|
| outcomes/records/review_v18_component_closure.json | Ny=8 原失败点是什么？完整 reference 算子覆盖是否闭合？八 q/空端口/真实 RHS 的资格怎样？ |
| outcomes/records/review_v18_sparse_capacity.json | 非对角行块或生命周期候选改变了什么？实际 backing/峰值/时间怎样？目标与 Ny=8 结构界依据是什么？ |
| outcomes/records/review_v18_formal_results.json | 新 Ny=8/E1/必要 anchor 哪些实际完成？每场 source/input/ABI、A6、物理、模式、PC 合同及保存比较是什么？ |
| outcomes/records/review_v18_cost_and_readiness.json | 新必要整场端到端是否闭合？E1 当前缺口具体多少？2 TB/48 h 哪些未知项被缩小？固定窗口实际剩余和终态是什么？ |

同步 response_v18、summary、test summary、run index、development_model_registry 和 development_progress。执行者负责实现与证据，主控审查、冻结和集中 commit/push 到同一 Task40 分支；不写 master。

本轮成功的判断不以文档篇数或 pytest 总数为依据。应能明确指出至少一项新增能力或被实测收紧的硬问题，并给出其他路线的具体进展：Ny=8 从部分组件进入完整资格及条件整场，E1 的当前阶段内存/安全后续被确定，目标结构推导与必要运行的实际成本获得可复核的数据。

对无法完成的项目，记录首个真实阻塞、已覆盖范围、尚缺字段和下一项最小有判别力工作；不得把未尝试归为数值失败，也不得以重复旧 HELD 数字替代当前研究。只要当前窗口和真实门允许，就连续执行本合同已经授权的后续阶段。

**本次裁决：接受 V17 的有限范围成果，继续 V18 研究；原尺寸 0.7 nm、2 TB、48 h 仍 NOT_QUALIFIED。** 本次审阅只新增文档，没有运行 FE/PDE、修改数值源码或启动计算窗口。报告的远程来源、数值转录和 Markdown 结构需核对；GitHub 网页实际渲染若工具无法确认，保留未验证状态，由主控补查，不因此重算科学任务。

## 证据入口

以下链接固定到本次审阅 base，避免后续分支提交改变审阅依据。

- 结果与账本：V17 回应 [S1]；组件 [S2]；稀疏与容量 [S3]；正式场 [S4]；成本与 readiness [S5]；run index [S6]；测试摘要 [S7]。
- 数值入口：一般 Ny transport [S8]；实际 FE 组件 [S9]；q 装配与 reference builder [S10]；MUMPS owner [S11]；输出 checker [S12]。
- 冻结合同：B0 输入 [S13]；任务目标、物理与精度合同 [S14]。

[S1]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/docs/task40extra_0p7nm_engineering/response_v17.md
[S2]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/docs/task40extra_0p7nm_engineering/outcomes/records/review_v17_component_closure.json
[S3]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/docs/task40extra_0p7nm_engineering/outcomes/records/review_v17_sparse_capacity.json
[S4]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/docs/task40extra_0p7nm_engineering/outcomes/records/review_v17_formal_results.json
[S5]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/docs/task40extra_0p7nm_engineering/outcomes/records/review_v17_cost_and_readiness.json
[S6]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[S7]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/docs/task40extra_0p7nm_engineering/outcomes/test_summary.md
[S8]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/src/solvers/task40_v17_ny_orbit.py
[S9]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/src/solvers/task40_v17_ny_orbit_fe_component.py
[S10]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/src/solvers/task40_v10_p6_yorbit.py
[S11]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/src/solvers/task40_v10_p6_mumps.py
[S12]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/src/runners/task40_v10_output_checker.py
[S13]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/input/task40extra_0p7nm_engineering/b0_p6_reference_v17.dat
[S14]: https://github.com/Rookie1234567/MyFEniCS/blob/57f20cc66b3de65c696def2b9bf783ddcbfce55e/docs/task40extra_0p7nm_engineering/task.md

