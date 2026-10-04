# Review V7：复用 Gx784，进入原生工作站有界验证，测清完整 p6 与 AUTO 成本

## 0. 决定、基准与本轮边界

**接受 Response V6 的 Gx784 数值及两组保存场比较，结束这一缩小模型的 x 一致性任务，不重跑 Gx784。立即推进工作站自己的 λ0.7 nm 有界 FE/ABI 验证及原尺寸成本工作；原尺寸正式求解继续 NO-GO。** 下一步要得到实际数值、耗时和内存证据，不再用更换报告编号代替执行。

| 对象 | 本次核实 / 授权 |
|---|---|
| 主线远端 HEAD | `task40extra_0p7nm_engineering`：`b5f85c5976d5f37de1adf769be0243daa5f4e964` |
| dot 远端 HEAD | `task40extra_dot_parallel_cloud`：`5be1210aa79f25c13a7677cc291a4a766a548650` |
| 审阅时间 | 2026-10-04 UTC；本次远端读取未发现比上述基准更新的提交 |
| Gx784 | **数值接受、复用；不再运行**。`tested_x_agreement` 不是原尺寸精度资格 |
| 工作站 W0 | **有条件 GO，一次实际 λ0.7/p6 FE 组件与独立 checker**；第 4 节给出已有 CLI 的准确命令、独立原生环境要求与停止条件 |
| 主线原尺寸离散 / AUTO 账 | **立即 GO**；复用库存，固定一个计数候选，按第 5 节补真实成本；不自动增加精度网格 |
| 原尺寸 AUTO 数值成本探针 W1 | **有条件 GO**；真实完整模式接线、精确小对照和分配前 Gate 通过后，最多一组代表类；当前不是已可运行入口 |
| dot C1a/b/c | **按顺序有条件 GO**；保存授权已获准。C1a 已实际尝试、导入失败，尚无实际 FE 通过结论 |
| 全阶 p6 周期参考逆 W2 | **另立范围的条件实验**，见第 6 节；当前只有组件入口，不能把 `--degree 6` 当完整 p6 求解器 |
| 原尺寸 50×25×140 nm 完整求解 | **NO-GO**；全部 q 因子、AUTO 32,060 接线、完整 p6 恢复、原尺寸精度和端到端成本尚未闭合 |

本轮承接 [Response V6](response_v6.md)、[执行收口](outcomes/records/review_v6_gx784_postprocess_closeout_v1.json)及 [V6](review_report_v6.md)。V6 的 Gx784 执行许可已经完成，不滚动继承为新重试。V7 更新保存状态并授权这里明确列出的工作站小实验；这也取代旧任务书中尚未授权工作站计算的限制，**不授权原尺寸大算例、参数扫描或修改 dot 专属分支**。

最终合同不变：**原尺寸 50×25×140 nm、λ=0.7 nm、完整三维、保留未来非可分三维缺口能力；整机十进制 2,000,000,000,000 B、无 swap；完整必要流程 ≤172,800 s**。冷 JIT/求积、装配、全部分解、迭代、内部恢复、要求的输出/独立检查和清理都在时间内。缩小尺寸、组件或代数残差通过不能替代原尺寸精度与资源资格。

审阅方法：读取两个远端 HEAD、相关提交差异、历次 review/response、源码、已发布记录，以及 task39extra 工作站线和 task035/035b 历史。审阅端命令工具无法启动，本轮没有运行 pytest、ABI 或 FE，没有直接取得 ignored 场文件/Library 原始归档逐字节复算。下文区分**仓库记录核实、源码静态核对、由记录计算、用户最新运行通报、未运行**。不把文档审阅写成独立数值复算通过。

## 1. 主线：Gx784 这一步已经取得什么

这里的 x 一致性，是只提高横向分辨率后，与两个已保存离散解比较；它缩小了当前模型的离散不确定性，但不是连续真解或原尺寸证明。

| 正式量 | V6 结果 | 裁决 |
|---|---:|---|
| 完整原 A6 显式残差，含恢复后重验 | 9.692115162625173e−7 | ≤1e−6，通过 |
| native identity / interior identity | 6.42238071470954e−11 / 3.132899e−18 | 沿原合同通过 |
| 端口残差 | 4.473743083e−16 | ≤1e−8，通过 |
| Gx→Gx784 八项场比较最大值 | 0.0006419146264421262，即 **0.0641915%** | ≤1%，通过 |
| F5→Gx784 八项场比较最大值 | 0.0006420202550004441，即 **0.0642020%** | ≤1%，通过 |
| 原冻结 11 个显著复模式最大差，两对分别 | 8.030064719462767e−5 / 8.148431581802385e−5 | 约0.00803% / 0.00815%，≤1%，通过 |
| 两对功率差最大值 | 约2.4943e−6 | ≤1e−3，通过 |
| 能量/两种吸收差 | 约2.069652e−8 | ≤1e−5，通过 |
| R / T / A_balance / A_volume | 0.07612656490058632 / 0.9057668832851113 / 0.01810655181430232 / 0.018106531117781374 | residual-qualified 缩小模型输出 |
| R00_s / R00_p | 0.07612609133082268 / 1.81947525589e−21 | 不把 s 与总量混写 |

输入 `nonseparable_gx784_p6_q4_review_v5.dat` 的 SHA256 为 `12f2e0dbed831f56c6e41133cdad292d0b70bea828087348ca8ede13142da422`；仍是 **14×4×14、p6、原准确 p4 预条件、340 模式、φ0**，材料、Fresnel 背景、相位与数学案例未变。求解源码 `2374d0d556aed7a415202757daa2b94b76ad399b`；后处理源码 `fea2b6c01b34940a6393bd47a4f545d6d53d61b4`。保存路径与原始量见收口 JSON，不复制场文件进 Git。

场比较仍用冻结 F5 同量分母、三场精确轴并集与相同材料公共体积；模式两对分别用首场 Gx/F5 幅值，原 11 keys 不变。不能因结果已通过而改用新分母、入射归一化、相位拟合或删模式。独立 checker SHA256：`6d3efb845189d6c84665baaa35a5f43e2bc35d94e8a22b0165785b67e125bc99`。

**保留旧负结果：F3/F5 散射 E 2.611883%、scaled-curl 2.750374%、显著复模式 1.555605%，均曾超过1%。** 四角 Gx≈F5、Gz仍差约2.6%说明该区间主要对 x 敏感；新增 Gx784 通过才支持这一缩小模型的 tested_x_agreement。它没有证明原尺寸 z/y/p/AUTO 收敛，也没有消除缺口模型的其他离散误差。本轮不追加 x/y/z/direct/p/M 点，不重做背景归因。

### 1.1 时间和 swap 必须按实际范围陈述

| 范围 | 记录 | 解释 |
|---|---:|---|
| 求解 workflow monotonic | 3431.6226415440906 s | 约57.19分钟；不包括后续独立保存场比较 |
| 求解监督任务树 RSS 峰值 | 7,782,744,064 B | 约7.783十进制GB；不是整机峰值 |
| 求解任务树 swap | 0 | 仅该任务树口径 |
| 同期系统 `pswpout` 增量 | **151页** | 整机发生 swap 写出；归因未知，不能写整机 swap0 |
| 后处理监督 wall / RSS | 1442.1525664149085 s / 946,765,824 B | 任务树 swap0；不把这一项遗漏 |
| 两个已知 wall 段相加，derived | 4873.775207958999 s，约81.23分钟 | 不是无缝端到端实测；准备/间隙范围另列 |
| 共享账本已用 / 剩余 | 5428.582333962078 / 167371.41766603792 s | 包括保守扣费/预留规则，不能叫纯 PDE 时间 |
| 旧启动成本 | 4.619253995631944 s | 保留；不是 PDE 时间；旧 AUTO 生成时间仍 unknown |

结论是**数值门通过、原尺寸资源门未授予，整机零 swap 不能通过**。不为消除这151页的文字限制而重跑 Gx784，不擅自对别的作业 `swapoff`。V6 后处理分类/源码接续修复及7项针对性、31项文档合同测试按已发布证据接受；不声称本审阅重新运行或 CI 通过。尚无计时证据的历史间隙继续 unknown，本轮不专门追补它们而延迟新数值工作。

## 2. dot：恢复、合成候选、实际尝试分别记账

| 证据层级 | 当前状态 | 后续使用方式 |
|---|---|---|
| V15 旧 X/XZ/Y 小尺度 p4/532 | 已发布历史通过；旧环境/旧载体，原始数据有缺失 | 保留历史结论；不继承为新环境通过或原尺寸资格 |
| 旧低内存端口/532分解前对照 | 已发布历史组件证据 | 只支持设计方向 |
| 旧只读 pivot 崩溃及修复后环境中断 | 失败保留；最后独立 checker **UNKNOWN** | 不能改成 PASS |
| 恢复的精确原 H 源码 | 有源码身份和27项纯代数、4项元数据检查 | 不等于 FE/PETSc 接线通过 |
| 新 fresh-C1 候选与运行环境 | 已发布79项非 FE 测试及独立新 ABI | 安装/import通过不等于组件求解通过 |
| `3c7458fad7c002babac4e634be4788b664be9ee5` | 新的显式启用精确分片投影，53项新测试、94项相关回归（另4 skipped、1 deselected） | 合成资格；没有 FE、RSS或加速证明 |
| `5be1210aa79f25c13a7677cc291a4a766a548650` | 只新增合成传输样本 | 不是新数值实现或实际 FE 结果 |
| Library 保存最新通报 | **用户已批准无损压缩存 Library；约1.07MB保存、空目录取回及成员hash检查通过** | 接受为最新运行通报；不再等待保存授权。它不是尚未产生的 C1 科学 raw 通过 |
| C1a 最新通报 | 资源准入通过；实际启动后缺 `pyvista`，约3秒导入退出，未到组件求解 | 标 `attempted_import_failed_before_FE`；失败与成本保留，允许下面的一次受控修复重放 |

Library 约1.07MB收据与这次 pyvista 失败尚未出现在本次读取的远端 HEAD。执行方只需把已有收据绑定到下一次发布，不重做已经成功的合成传输试验、不把原先“保存待用户确认”继续当阻塞。实际 C1 raw 仍须在产生后完成独立保存/取回/成员 hash 核对。

新版投影把大矩形临时量分成小片，精确生成同一个稀疏投影，目的是降低瞬时工作区。源码 `bounded_compact_q_projection.py` 与 `TwoCellBlockProvider` 保留非 Hermitian 复数共轭关系，不靠阈值裁零。**仅设置正的 `compact_projection_max_owned_bytes` 才启用；默认 None 仍走旧路径。** `compact_projection_tile_width=32` 不是一项精度参数。

其 owned-array 上限包含自身管理的切片与 CSR 生命周期，但不涵盖借用的 Di/XiB 底层数据、q映射、生产者、Python/BLAS额外副本和因子。合成64端口样本中旧矩形工作区166128 B、新19712 B、所报 owned 上界105956 B，只是这一表示边界。样本时间不能证明加速，源码逐片合并/复制可能增加成本；是否合算必须在 C1c 的**全 setup、完整 PC、外层步数与输出**中判断。

源码与恢复约束见 [候选说明](https://github.com/Rookie1234567/MyFEniCS/blob/5be1210aa79f25c13a7677cc291a4a766a548650/docs/task40extra_dot_parallel_cloud/outcomes/bounded_projection_candidate_v1_zh.md)、[可移交合同](https://github.com/Rookie1234567/MyFEniCS/blob/5be1210aa79f25c13a7677cc291a4a766a548650/docs/task40extra_dot_parallel_cloud/outcomes/portable_retained_h_qualification_contract_v1_zh.md)、[原尺寸缺口](https://github.com/Rookie1234567/MyFEniCS/blob/5be1210aa79f25c13a7677cc291a4a766a548650/docs/task40extra_dot_parallel_cloud/outcomes/original_target_remaining_gaps_recovery_v1_zh.md)。两份恢复文档的“环境不可用/库存未确认”已被新事实更新，其完整恢复、原方程与资源要求仍有效。

### 2.1 dot 的执行顺序与有限修复

1. **当前 pyvista 阻塞：**优先把没有参与计算的绘图导入延迟到实际绘图调用，按 traceback 定位，不能吞掉数值依赖异常或用假模块绕过。只允许 dot 执行方修改自己的分支。本报告不替 dot 写代码。最多两轮局部修改/定向检查，验证真实 worker 的 import closure，不以 `--help` 代替。通过后允许**一次同 C1a 的修复重放**，新目录，旧约3秒与失败文件保留；资源、原方程、输入不变。
2. **C1a：**真实80单元 p6/532载体，非零内部与端口 RHS、全部36,000内部自由度恢复、MPC/slave、compact/dense action；worker→独立原始张量 checker→该次实际 raw Library保存及空目录取回。action/recovery≤1e−11、制造解原方程≤1e−10、纯代数≤1e−12；近零分支沿原合同，不更换分母以掩盖失败。
3. **C1b：**fresh p4、全部4q、532完整输出、8,640内部自由度、原四种 RHS、regular/notch；稠密的是端口参考表示，FE/q仍为稀疏。绑定本环境 C1a 与实际raw收据，worker/checker/取回都通过才进下一步。
4. **C1c：**同一 p4 fixture，紧凑两单元构造与上述显式分片投影真正进入计算；运行收据记录 constructor 实参/预算及命中路径。全部4q、非零内部/端口 RHS、完整恢复、regular/notch 与 C1b 完整向量及全部532复数输出比较，保持原 residual/identity/observable 门。默认路径通过或仅一个 q 通过不能替代 C1c。
5. **C2：**公共 PETSc complex 非 Hermitian 小块→实际合格 q 块；测填充、因子工作区、全部并存、setup/回代与整数宽度。然后使用主线真实 AUTO 身份做有界支持成本，禁止删除532断言后直接声称32060可用。

C1每 worker、checker各≤**3 GiB=3,221,225,472 B、4500 s、MPI1/数学线程1、swap0**；至少128 MiB证据余量、磁盘空闲≥2 GiB、未压缩raw≤512 MiB。终止及写出在本阶段预算内。C1b/c各最多一次明确局部实现 bug 的修复重放；C1a就是本次 pyvista 后新增的一次。数值不合格、资源超限或环境中断不自动重放；任何阶段失败，停其下游。文档提交不导致昂贵 Gate 重跑；依赖源码变化则准确说明需要重验的边界。

## 3. 跨分支计时：现在的瓶颈不是再做同一个 p4 优化

依据工作站分支 `task39extra_para_workstation_capacity` 的审阅基准 `584d6e406e6e1ed552fff4fd311b51549c984825`：[F5/H6完整计时](https://github.com/Rookie1234567/MyFEniCS/blob/584d6e406e6e1ed552fff4fd311b51549c984825/docs/task39extra_para_workstation_capacity/outcomes/performance_transfer_v6.md)及[旧2nm OOM终止](https://github.com/Rookie1234567/MyFEniCS/blob/584d6e406e6e1ed552fff4fd311b51549c984825/docs/task39extra_para_workstation_capacity/outcomes/f2_terminal_oom_20261002.md)。

| 历史模型 / 范围 | 实际证据 | 本轮意义 |
|---|---|---|
| 旧2nm p6/h1.5完整迭代 | 185.064677 h后OOM，228步；最新原A6残差约9.7583e−5，未达1e−6；有任务swap | 不重复。OOM涉及NUMA/memory-policy及外部压力，不能单凭此推断整机2TB理论不可能；该次没有合格结果 |
| 新5nm F5 | 全workflow12534.182499 s=3.4817 h，121外层步；原A6 8.7045013e−7；244/244 p4返回通过 | 接受完整已有优化与结果，不重做F5 |
| 新2nm H6-only | 17521.132 s=4.86698 h | 仅H6组件；没有p4分解、完整迭代/恢复/RTA，不能当2nm全求解时间 |
| F5 C步骤 parent inclusive | 4470.977117 s，占workflow35.6703% | 已包含子步骤，不能把MatSolve/恢复/A4再次相加 |
| F5 KSP / setup | 9830.705350 s / 1696.196008 s | KSP平均81.2455 s/外层步；不是C一次耗时 |

保持F5其余工作及步数不变，即使全部 C 步骤免费，derived总加速上限：

```math
S_{\max,C}=\frac{12534.182499}{12534.182499-4470.977117}=1.5544913.
```

这只约束“优化同一 C 步骤”的收益，不是0.7nm预测，也不限制另外改变 setup、完整预条件或外层步数的路线。**相同准确 p4 逆换成周期/紧凑表示，数学作用不变时没有自动减少 p6 外层步数的依据。**舍入可影响轨迹，但不是收敛改进证据。今后同时报 setup、A6/H6、完整PC（含两个C等组成）、外层步数、恢复/输出与总wall；不用单个 MatSolve 倍率替代总成本。

不重复的历史边界：

- task035：实际残差类自适应在匹配成本下不优；DWR（用目标输出的敏感性来挑细化区域）曾有正结果，但没有取得通用同误差生产优势，第二轮亦有成本负结果。
- task035b：分区阶次/轴向加密最强预算内点仍10/12功率与10/12复振幅；后续z节点对照回退，不重新打开同一路线。静态凝聚、精确预分配与生命周期收益直接复用。
- task39extra：既有宏块精确Schur内存问题、近似粗逆负结果及已完成H6/A6/A4工程优化继续保留；不把旧近似p4逆换名再试。
- task40extra：背景归因、M扩展、Gx/Gz/Gx784已做。本轮新问题是**原尺寸离散/完整AUTO成本及真正全阶p6参考逆是否改变完整迭代代价**。

## 4. 工作站立即执行 W0：准确的现有入口与独立 ABI

### 4.1 选择及范围

现有可执行的 λ0.7/p6 小入口是 dot 的 fresh C1a。工作站**仅移交一次相同自包含FE载体，用来证明自己的真实ABI、冷JIT和端口/内部恢复接线**；这不是另做一轮云端算法研究。若已有同源、同输入、同原生ABI的实际合格收据，直接复用，不重复。工作站不再复制云端 C1b/C1c 队列；dot仍拥有算法资格与完整紧凑链。

这比声称主线现有runner已经支持“原尺寸λ0.7新dat”更实在：静态核对发现主线相关profile锁定已有案例；dot CLI也锁定分支、输入与隔离prefix。下面直接使用**canonical clone登记、保持clean的只读dot工作树**，不提交或推送dot，不改其分支。主线保存工作站的轻量移交收据与下一response。不要checkout/reset活动工作树；同名dot工作树已存在则安全复用，不能用`--force`重复占用。

**完整 p6 求解不是此命令的功能。**本次W0只建p6，不偷偷建立p4空间；制造解/恢复通过也不产生原尺寸official R/T/A。

### 4.2 启动所需的真实环境和输入

| 项目 | 固定要求 |
|---|---|
| 主机 | 原生Linux工作站，Linux本地磁盘；可用空闲执行窗口，不干扰现有P2或其他heavy任务 |
| 数值源 | dot `5be1210aa79f25c13a7677cc291a4a766a548650`；若其后只发布了本次pyvista导入修复，先核对diff、相关测试后允许冻结该子提交，不另等文字授权 |
| 实际环境 | 独立prefix，Python3.12、PETSc3.25.6 complex128/int32、MPICH5.0.1、DOLFINx/Basix0.10.0、MPC0.10.5；数学线程1、MPI1、`UCX_TLS=self`；全部模块真实路径在同一prefix |
| 安装输入 | `scripts/task40extra_cloud_recovery/environment_explicit_conda_forge.txt`；官方精确包清单。先核实CPU支持其x86-64-v4包要求；不覆盖已有工作站环境/全局MPI |
| ABI证明 | **在工作站实际运行`qualify_imports_only.py`新建收据**，含本机解释器、加载路径、MPI/PETSc/索引类型；不能复制云端JSON或手工伪造activation marker |
| 物理输入 | `input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat`，SHA256 `6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e` |
| 实际fixture变换 | 入口`pilot_config`固定缩小比例7/135、λ0.7、φ5、80单元4×4×5、p6、manual532、boundary_plane、positive-h；不是主线φ0/340或原尺寸 |
| 资源 | worker/checker各3GiB/4500s；本次工作站W0从环境准备开始至raw保存/清理总计≤4h，所有尝试累计；不足剩余预算不启动 |

当前原生工作站旧PETSc3.19/OpenMPI环境**不能直接拿来运行这个锁定3.25.6/MPICH的入口**。若新prefix尚无，执行者可按上述官方锁文件一次性建立用户目录隔离环境；例如用本机已有可执行micromamba：

```bash
# T40_PREFIX必须是本轮选定的新Linux绝对路径；T40_MAMBA为已有Linux micromamba。
"$T40_MAMBA" --no-rc create -y -p "$T40_PREFIX" \
  --file scripts/task40extra_cloud_recovery/environment_explicit_conda_forge.txt
```

安装/导入准备限60分钟、至多两轮局部修复，不改网络安全设置，不重新安装旧工作站环境。若包源或CPU/ABI不合要求，交准确blocker并继续主线离散/成本工作；不能把旧ABI收据改名。优先取得dot已经发布的无绘图依赖导入修复；不为一项不用的绘图功能拉入庞大图形栈来掩盖依赖关系。

脚本名字含cloud不表示可以借用云收据：以下activation只用于**本机按同一精确包清单新建的独立prefix与本机新收据**。源码核对其无WSL路径依赖；不调用`activate_myfenics_wsl.sh`或WSL launcher。返回记录中历史固定的`qualification_scope`字符串也不能代替实际hostname、内核、prefix和receipt身份。

### 4.3 可直接执行的 W0 命令

先由执行者设置三个真实Linux绝对路径：`T40_SRC`为上述只读dot工作树，`T40_PREFIX`为已安装合格prefix，`T40_EVIDENCE`为该工作树ignored artifacts下本轮新的证据目录。`T40_SOURCE_SHA`默认下面的审阅SHA；采用窄范围修复时改为已核对的完整子提交。这几个是本机路径输入，不是省略了数值参数。

```bash
set -euo pipefail
: "$T40_SRC" "$T40_PREFIX" "$T40_EVIDENCE"
cd "$T40_SRC"
T40_SOURCE_SHA=5be1210aa79f25c13a7677cc291a4a766a548650
test "$(git branch --show-current)" = task40extra_dot_parallel_cloud
test "$(git rev-parse HEAD)" = "$T40_SOURCE_SHA"
test -z "$(git status --porcelain --untracked-files=all)"
test ! -e "$T40_EVIDENCE"
mkdir -p "$T40_EVIDENCE"
git check-ignore "$T40_EVIDENCE"
T40_ABI="$T40_EVIDENCE/workstation_abi.json"

export UCX_TLS=self
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
"$T40_PREFIX/bin/python" scripts/task40extra_cloud_recovery/qualify_imports_only.py \
  --record "$T40_ABI"
source scripts/task40extra_cloud_recovery/activate_fresh_cloud_complex.sh \
  "$T40_PREFIX" "$T40_ABI"
export XDG_CACHE_HOME="$T40_EVIDENCE/cold_jit_cache"
mkdir -p "$XDG_CACHE_HOME"
hostname > "$T40_EVIDENCE/hostname.txt"
uname -a > "$T40_EVIDENCE/uname.txt"

# 与worker一致的数值导入闭包；不创建mesh，不以此声称FE通过。
python -c 'import src.solvers.fullspace_same_mesh_hcurl_pmg_global; import src.solvers.fullspace_same_mesh_hcurl_pmg_physical; import src.solvers.y_orbit_sparse_probe'

python -m benchmarks.run_y_orbit_sparse_probe \
  --dry-admission --fresh-fixture-c1 p6-component --degree 6 \
  --auxiliary-gauge positive-h --dtn-phase-gauge boundary_plane \
  --live-component-oracle --research-memory-gib 3 --research-wall-seconds 4500 \
  --expected-head "$T40_SOURCE_SHA" > "$T40_EVIDENCE/admission.json"

T40_RUN="$T40_SRC/benchmarks/artifacts/task40extra_dot_parallel_cloud/native_c1a_v7_$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$T40_RUN"
python -m benchmarks.run_y_orbit_sparse_probe \
  --run --fresh-fixture-c1 p6-component --degree 6 \
  --auxiliary-gauge positive-h --dtn-phase-gauge boundary_plane \
  --live-component-oracle --research-memory-gib 3 --research-wall-seconds 4500 \
  --expected-head "$T40_SOURCE_SHA" --run-directory "$T40_RUN"
python -m benchmarks.check_y_orbit_sparse_probe "$T40_RUN" \
  --expected-checker-head "$T40_SOURCE_SHA"
```

此命令依据本次读取的两个入口参数与source/environment检查编写，**本审阅未在工作站执行**。精确启用路径见 [runner](https://github.com/Rookie1234567/MyFEniCS/blob/5be1210aa79f25c13a7677cc291a4a766a548650/benchmarks/run_y_orbit_sparse_probe.py)、[checker](https://github.com/Rookie1234567/MyFEniCS/blob/5be1210aa79f25c13a7677cc291a4a766a548650/benchmarks/check_y_orbit_sparse_probe.py)、[source/ABI约束](https://github.com/Rookie1234567/MyFEniCS/blob/5be1210aa79f25c13a7677cc291a4a766a548650/benchmarks/run_real_p4_probe.py)。pyvista错误若仍在导入闭包复现，停在数值启动前，按4.2处理，不先消耗FE运行来试环境。

开始前读取主机活动进程/已有锁、MemAvailable/cgroup、SwapUsed及全局pswpin/pswpout；不得因时间要求终止现有任务。本轮已见工作站仍有其他P2执行的任务信息，实际空闲窗口须执行者核实。父监督器在worker导入/JIT前启动、0.25s采样、全树控制、全局swap增量即停；本次任务树3GiB不能替代整机2TB条件。W0必须记录系统基线，若全局已有swap占用则不能取得整机零swap资格，不擅自清零。

W0以`fresh_p6_cold_setup_begin`及后续实际FE事件为进入数值工作的证据，dry-admission/imports都不算。通过必须同时有worker、独立checker、原方程/全内部恢复和raw取回；失败保存源/输入/本机ABI/命令、阶段、异常、wall/RSS/swap和进程树清理。

**W0最多一次实际FE执行；另允许一次明确的局部实现bug修复重放，累计仍在4h内。**无数值失败、资源停止或环境中断后的自动第二次。仅checker代码局部错误可复用相同已保存raw重放一次，不重跑worker，不改变验收。没有准入时交blocker，不把“将运行”写成已启动。

用户要求的进入计算截止为 **2026-10-04 10:07:14 UTC（新加坡18:07:14）**。主控应尽早交本机启动时间、PID/start-time、命令、source/input/ABI hash及日志位置；等待空闲窗口或安装失败必须在截止前明确报阻塞，不能为赶时限抢占既有heavy任务或声称已进入FE。

## 5. 主线的独占任务：原尺寸候选、完整 AUTO 和真实成本

### 5.1 不再生成库存，不把计数候选变成合格网格

复用 `benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/original_size_auto_mode_manifest.json`；修复目录中同名副本也可，必须保持字节相同。

| 项目 | 已发布值 |
|---|---|
| 完整有序通道 | **32,060**；36,244,923 B；原始与修复清单相同 |
| 清单 SHA256 | `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d` |
| 有序键 digest | `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec` |
| 身份范围 | 原尺寸、λ0.7、θ89°、φ0的外部端口库存；不授予内部网格/缺口精度 |
| 原尺寸计数候选 | 272×4×14=15,232单元；x保留0/16.5/25/33.5/50nm界面，分段78/58/58/78；y为0..25nm四段，z为−10,0,10,…,130nm |
| 候选 p6 维数 | 完整10,228,620；内部6,854,400；保留量+端口3,126,332，均为derived计数 |
| 原 H 对角载荷 / 稠密方阵 | 512,960 B / 16,445,497,600 B，均为complex128表示量，不是整机RSS |

审阅核对了已发布双清单hash和计数；未持有ignored清单本体，不声称自己重算36MB文件。执行方读取已有文件核验上述身份即可，**不重复生成清单**。

这个x分段约束材料界面并保留较细横向长度，是单一成本候选；Gx784的缩小尺寸x一致性不能证明该原尺寸候选的z14、y4或p6精度。首先以规则原尺寸baseline建立可计算路径，同时保持完整三维算子与全部q。φ0、沿y不变的规则材料及均匀入射具有对称性，可用于诊断解中的不期望y分量；**不能删除y自由度/q分支或据此宣布三维缺口y收敛**。

此时不再开缩小模型精度扫描。主线的精度工作是把Gx784完整比较身份接入[四角接口包](outcomes/records/review_v4_four_corner_interface_v1.json)，冻结原尺寸单一候选的物理/网格/阶次/模式定义，并在有能力运行原尺寸之后才选择一个针对剩余误差的独立参考或方向性检查。当前不足以把任何272×4×14求解结果预先视为1%合格。

### 5.2 必须闭合的对象与生命周期

“低内存端口”只压缩边界表示；“内部恢复”是把暂时消去的单元内部未知量重新求回，使最终解满足完整原方程；“周期分块”利用规则参考介质的重复结构分成q块分别求逆。它们节省的对象不同，完整总账不能只列一个H矩阵。

| 成本项 | 当前已知 | 必须补的证据 / 责任 |
|---|---|---|
| JIT与面求积 | max_order142；公式给p4 degree156、p6 degree160，名义79²/81²点 | 实际compiled节点/weights、编译wall/峰值、表格缓存，主线W1 |
| C/D及端口映射 | 模式库存存在；全32060生产接线尚未通过 | 全有序keys、aliases/γ、上下介质/参考平面、稀疏支持/实际值与构建成本，主线W1 |
| p6单元局部消元 | 每单元882=450内部+432保留；原张量12,446,784 B、内部LU3,240,000 B、Schur2,985,984 B、每个耦合/恢复矩形3,110,400 B，均为载荷计算 | 类别去重、复用、同时存活及重算次数；Di/XiB作用、任意内部RHS，主线计数+dot实际组件 |
| 投影工作区 | 精确分片候选只有合成资格 | 实际支持、owned以外借用/临时量、CSR旧新重叠及BLAS复制，dot C1c；主线原尺寸W1提供真实类 |
| H/Hhat | 原H可对角存；凝聚后的Hhat还含内部修正 | 不假设Hhat仍对角；完整修正支持、驻留与构造时间，dot |
| 全部q稀疏分解 | 当前无原尺寸实测fill/后端资格 | 每q rows/NNZ/index宽度、L/U NNZ、ordering、backend工作区、**全部因子同时驻留**及setup/回代，dot C2 |
| 外层与完整PC | p4替换不保证少p6步 | 原A6/H6/完整PC计时、步数、非收敛上界；主线W2，不以单C速度代替 |
| 外层/恢复/输出向量 | 候选74外层向量约3,701,577,088 B，full scratch约4,428,003,200 B，derived | 实际同时数、别名复用、端口/采样/输出checker重叠；不能直接相加当RSS |
| 系统及其他进程 | 不可由worker RSS推出 | 整机/cgroup基线、缓存/编译器后代、正余量、swap基线与增量、rawI/O，工作站主控 |

所有计数写清 measured / derived / predicted / unknown。给每项创建、释放、重用区间，才能合成峰值。整机准入按 min(物理内存、有效cgroup、2e12B)减实际其他占用和冻结系统余量；因子未测不得填写零。索引宽度必须覆盖rows/NNZ/CSR indptr、后端offset与转换；PETSc int64不自动等于MUMPS完整64位支持。

### 5.3 W1：只做一组原尺寸真实端口成本，不先造全体积

**条件授权主线在W0本机数值通过后做这一步；不等待云端保存决定。**它与dot C2分工：主线负责原尺寸物理输入、完整AUTO及真实局部求积/C/D/恢复数据，dot负责紧凑投影和公共后端/全部q。共用raw与接口，不各自重复同一个成本样本。

现有诊断脚本中用随机/重采样modal stress扩大M的部分不是实际AUTO，不能直接把 `mode-size=32060` 当本任务完成。允许在通用src端口/恢复模块中做最小参数化接线，以薄runner读取现有manifest，不复制新的数值算法，不整合整个dot或task39研究分支。

冻结范围：**上下介质各一个代表面，以及一个最大支持的内部修正类**；p4/p6各处理必要的同一组对象。使用原尺寸面积、材料、Bloch/出射相位、真实模式系数和完整32,060keys，可以分批，不能以小M抽样代替。先用同类的小完整keys集合与显式旧表示做精确对照（action/恢复≤1e−11、相关原方程≤1e−10），再准入全keys。这不是另一轮M收敛扫描。

整个W1（准备、冷JIT、p4/p6对象、checker、写出）**≤7200s、任务树≤16GiB=17,179,869,184B、MPI1/线程1、swap0**，所有尝试累计；分配前纳入workspace与已有对象；预算不足即controlled_stop。不得构造原尺寸全体积矩阵或目标规模LU。若这些代表类不是类别全集上界，明确不能推广为总成本。最多两轮局部接线/针对性测试；不新增第二组面/网格、不扫描batch/tile参数。

**当前主线没有这一完整AUTO实数值成本入口，状态是“允许最小实现后执行”，不是现成可跑。**执行者交付真实`--help`、冻结输入/manifest hash、完整无FE控制链检查和实际命令后，在上述边界内直接运行；不虚构一个现存CLI、不再等待新review。只读成本账可在W0/云端阻塞时继续，实际FE必须先有本机资格。

W1通过只授予对象成本证据；JIT超限、完整支持超内存或index不安全就停止该路线的向上规模升级。不能用线性RSS外推或只算H将原尺寸改判GO。

## 6. W2：若要改变 p6 外层步数，只允许一个完整对照

全阶p6周期参考逆的意思是：规则参考问题也在同一个p6空间中求逆，再把三维缺口作为与参考问题的差异交给外层处理。它有可能改变p6外层收敛，而只替换准确p4逆的存储通常没有这个作用；代价是更大的p6投影/分解与完整恢复。因此值得保留为**独立反证实验**，不能继承C1a的组件资格。

**W2不在当前可直接运行状态。**准入须有C1c实际完整紧凑链与raw取回、工作站自身ABI/FE资格，以及单独显式启用的p6完整链入口/无FE资源控制测试。不得把 `run_y_orbit_sparse_probe --degree 6 --fresh-fixture-c1 p6-component` 改名当全链。dot完成C1c后交接口/证据，主线负责最小文件级移交和这个性能对照；不让dot同时开另一套p6试验。

| 项目 | W2 唯一允许范围 |
|---|---|
| fixture | 复用fresh80单元、λ0.7、φ5、532完整模式、p6；原regular与同一两单元notch、同一物理RHS，全部4q；不改变网格/材料/相位/模式 |
| 被比较对象 | 同一原A6外层，用当前准确p4-based完整PC作对照，与新增全阶p6周期参考逆作候选；各一次，不能与φ0/Gx784直接比timing或复数值 |
| 完整性 | 全部36,000内部自由度、非零内部/端口测试载荷、MPC/slave、全532输出；因子全部并存时实际测量，不用单q乘4替代 |
| 数学门 | 原A6显式真残差≤1e−6；恢复/原方程identity≤1e−10、端口≤1e−8；候选参考逆regular制造解≤1e−10；小对照action/恢复≤1e−11 |
| 同离散物理对照 | 两个合格原A6解在相同坐标、同相位、固定对照范数下，总/散射E及scaled-curl≤1%；预冻结对照显著复模式≤1%、全532保留；功率差≤1e−3、能量≤1e−5。不能用制造解替物理notch解 |
| 时间/内存 | 整个对照组准备、cold setup、两路线、恢复、checker、清理累计≤21600s（6h）；任务树≤64GiB=68,719,476,736B，整机准入/零swap不变 |
| 迭代边界 | FGMRES32、零初值，两路线都最多128外层步；原显式残差定期及结束重算。超时、达到步限或数值失败即收口，不追加256/512步 |
| 性能裁决 | 比完整wall、setup、完整PC、外层步数、恢复/检查和同时峰值；只有候选同门通过且完整wall优于该对照，才称这个小fixture的实际收益；不是原尺寸收益 |

这是本轮**最多一个条件对照组**，不是新增扫描。两路线有一条未收敛，只能给已用成本/残差趋势与下界，不能宣布候选获得全流程加速。若候选每步更贵且没有足够少的步数补偿，关闭这一参数下的p6参考逆升级；不再重做p4替换期待自动降步数。

若尚无可审查的完整p6入口，两轮局部实现/定向检查仍未接通，则W2保持not_run并交具体缺口；先完成W1真实成本，不为赶截止伪造命令。这个条件实验不阻塞第4节现成W0。

## 7. 原尺寸准入、替代方向与一轮结束的条件

当前证据**不足以证明原尺寸目标可在2TB/48h内实现**。已有缩小模型数值通过、表示节省和5nm工程加速都是进展，但目标电尺寸、AUTO求积、全q填充、完整p6步数及原尺寸精度没有闭合。不能写“工作站大规模验证就绪”，也不能仅据旧OOM判定目标本身不可算。

下一轮原尺寸GO至少同时需要：一个有精度依据的原尺寸离散候选；完整AUTO按物理身份接线；独立原方程与完整p6恢复；合格公共后端与实际整数容量；全部q因子并存/临时量/向量/输出的整机峰值上界与实测锚点；完整必要流程含迭代上界在172800s内。仅最后一项作乐观外推也不能获得GO。

有界出口只按出现的瓶颈选一个，**不是自动追加实验许可**：

| 实际瓶颈 | 有依据的后续选择 | 本轮停止边界 |
|---|---|---|
| 大矩形投影临时量超限、完整稀疏输出可容纳 | 复用本次显式分片投影；先完成C1c反证 | 不另写一个同类投影器，不裁零/删模式 |
| 单q能装下、全部q因子并存不能 | 核算有限因子批次/精确重算的完整时间；只有48h仍成立才另提实现 | 本轮不悄悄改为OOC或依赖swap |
| 单q填充本身过大或完整PC/步数仍不支持48h | 明确当前精确参考逆参数路线不准入。另考虑此前仅设计的局部求解加递归物理粗纠错，其目的须是改变规模增长和外层步数 | 不回到已失败的宏块/近似p4逆扫描；须有新的单一反证合同才运行 |
| 原尺寸精度证据仍不足 | 在可承受完整流程后，按实际剩余误差选择一次方向性/独立参考；规则y对称性只作辅助 | 不先复制旧背景归因或盲加密缺口，不用功率闭合替场/模式误差 |

V7工作站研究累计上限为**43,200s（W0≤14,400、W1≤7,200、W2≤21,600）**，包括各阶段准备、失败、重放、checker及清理；分项预算不能借用扩大，剩余时间不足则不启动下一阶段。保留V6旧账本和5,428.582334s历史扣费，V7另追加有来源的增量账，不改写旧成本，不把研究分项相加声称原尺寸已满足48h。云端每阶段沿第2节独立小预算；同一机器一次一个heavy case。

停止条件包括ABI/整数宽度不合、活动作业冲突、资源/全局swap触发、完整模式/恢复缺失、原方程不合、raw不能保存/取回、明确修复额度耗尽。失败交付须包含最后完成阶段、实际数值与限值、输入/source/本机ABI/原始成员hash、完整命令、时间/内存口径、树清理及下一项为何not_run；不能只交一个failed标签。无关文档/元数据小错可局部修复，不触发FE重跑、环境重装或大规模全仓测试。

本轮待执行者核实的是**工作站可用窗口、独立prefix/CPU兼容、最新pyvista窄修复SHA、实际C1收据及原AUTO文件可读性**，不是再问用户是否允许Library保存。主线φ0/340、dotφ5/532、原尺寸φ0/AUTO32060三种身份必须分别保留；沿四角接口统一单位、模式顺序、Bloch/出射基、参考平面、背景和相位，只有完全同身份对象才做复数值对照。

本报告只提交主线V7，不修改dot/master、不开合并、不干扰现有任务。执行结束把新增事实写入下一response及现有summary/索引，保留全部历史负结果；不要为每次启动错误再开review编号。报告静态核对与远端发布不能代替运行测试，工作站是否实际启动以执行回执为准。本次仅做Markdown结构、源码参数和单文件提交检查；本地文档合同测试未运行，网页渲染检查结果在交付回执说明。

## 8. 可直接交给执行 Codex 的文本

> 在canonical clone登记的task40extra_0p7nm_engineering工作树安全拉取并完整读取docs/task40extra_0p7nm_engineering/review_report_v7.md；审阅主线基准b5f85c5976d5f37de1adf769be0243daa5f4e964、dot只读基准5be1210aa79f25c13a7677cc291a4a766a548650。保留活动任务和所有失败，不reset、不改dot/master、不合并。Gx784已完成并接受tested_x_agreement，禁止重跑；记录任务swap0与系统151页swapout的区别，复用保存场、冻结分母及11模式。
>
> 优先按第4节在原生工作站执行一次λ0.7/p6 fresh C1a移交验证。只读dot源码使用canonical登记的clean同名工作树；按官方锁文件建立独立Linux prefix，工作站实际生成自己的ABI收据，不能复制云端收据、调用WSL wrapper或伪造marker。先解决真实pyvista导入闭包，最多两轮局部修补；可以采用核对过的仅导入修复子提交。按第4.3节已有CLI依次dry-admission→p6-component→独立checker→实际raw保存与空目录取回。worker/checker各3GiB/4500s，整个W0含准备和失败≤4h；最多一次实际FE加一次明确bug修复重放，数值/资源失败不重试。先取得空闲窗口，不干扰P2等已有作业。在2026-10-04 10:07:14 UTC前给实际FE启动时间/PID/source/input/ABI hash及日志；未能启动则准确给blocker，不能把import/dry-admission报成FE。
>
> 主线独立推进第5节原尺寸候选与AUTO账：复用32060模式清单，manifest SHA256=52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d、ordered-key digest=03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec，不再生成。272×4×14只是计数候选。W0通过后，以最小参数化接线完成一组原尺寸真实上下介质代表面/最大内部修正类的W1，完整keys不抽样；≤16GiB/7200s，包括JIT和checker，不建目标全体积或LU。没有现成W1入口，先交真实命令和控制检查再在授权内执行，不虚构已有可跑命令。
>
> dot由自己的执行者保持C1a受控导入修复重放→原方程独立checker→实际raw Library保存取回→C1b稠密端口参考链→C1c显式启用新精确投影的完整4q/内部恢复/532输出→C2公共PETSc后端/成本的顺序。保存已经获准，约1.07MB传输检查通过；尚无实际FE通过结论。C1a/b不能代替C1c，合成测试不能代替FE或加速。
>
> 只有C1c及工作站本机资格通过且新入口完成，才按第6节做唯一W2：同80单元/φ5/532/p6、regular/notch，对照准确p4-based完整PC与全阶p6周期参考逆；≤64GiB/21600s全组、FGMRES32/max128，完整A6≤1e−6、恢复identity≤1e−10、端口≤1e−8，以及固定场/模式/功率/能量门。当前p6-component不是完整链。量setup、完整PC、步数和总wall，不重复F5/H6优化、不把C优化上限约1.554倍当目标加速。W2条件不满足就交not_run，不等待它而停掉W1。
>
> V7工作站全部研究累计≤43200s，分项不互借；整机≤十进制2e12B、swap0、一次一heavy，保留历史成本，所有阶段含恢复/输出/checker/清理。原尺寸精度、AUTO接线、全部q因子并存/填充、完整p6恢复及172800s端到端成本未闭合前始终NO-GO。通过、受控停止或修复额度耗尽均交真实证据和下一response后结束，不追加网格、p/M扫描或无限重试。
