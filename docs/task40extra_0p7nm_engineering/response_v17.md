# Review V17 执行回应

V17 已在同一 Task40 执行分支完成本轮局部恢复复核、P4 原始 D 读回、Ny=8 小组件、B0 行分块稀疏构建组件、目标结构计数，以及 Gx560 p6 完整 anchor。Gx560 是把原尺寸 50×25×140 nm 几何按 `7/135` 缩小后的 0.7 nm 解析模型：冻结输入中的 x/y 周期分别为 `2.5925925926/1.2962962963 nm`，z 范围为 `-0.5185185185` 至 `6.7407407407 nm`。Gx560 离散求解、官方物理输出和与 V16 保存场的同离散比较通过；这不是原尺寸模型的场，也不构成原尺寸资格。Ny=8 的映射与 FE 右端项有实测结果，但 maps/action 仍为部分资格；E1 和原尺寸目标没有运行或取得容量资格。没有改 ordinary solver default；执行者不提交或推送，材料待主控集中审阅后按分工处理。

本回应的 review base 为 `efe79a1f9bdb33dd1694ea737139d807172b1f31`。文档收口开始时分支为 `task40extra_0p7nm_engineering`、HEAD 为 `23626f44243d19d58af41d15a8ccafcba41ee54b`，tracked 工作树干净。各项正式计算绑定自己的实际源码 SHA，不用收口 HEAD 代替运行源码：B0 行分块组件 `ca913307d3cdd5a455c2718138bf2089151b3887`，Gx560 正式求解 `cbdcc12812b439f5252949ad1279331b86a2dbb6`，Ny=8 maps/action `d790964079628e7fadaa84354bc209db4262ecb9`。

| Review 阶段 | 实际结果 | 状态及边界 |
|---|---|---|
| P1：S2 保存局部方程 | 同一保存矩阵和右端项下，直接 LU 的 top/bottom 前向误差为 `2.20293e-11 / 2.42443e-11`，超过原 `1e-11`；同因子修正后为 `5.35247e-14 / 5.14331e-14`，独立 checker 重算通过 | 每面最多 3 次修正：top 尝试 2 次、接受 1 次；bottom 尝试并接受 3 次。每步都对原始 complex128 `Vii` 重算残差；直接 LU 负结果保留。仅复核保存的小系统，没有重装体积或重解 PDE |
| P1：P4 原始 D / plane 读回 | 对 top、bottom 各 16,030 个有序模式、每面全部 882 个原生行做独立 D 作用；每面原/约化端口方程通过。独立 plane phase/Hp 逐 key 最大相对误差小于 `4.55e-16` | 组件级独立读回通过；不是目标全局矩阵或 PDE |
| P2：Ny=8 native maps/action | 实测 `Ny=8, ell=2, K=4`；532 个有序模式恰好覆盖，global q=0…7 均有 FE sector；映射门 `1e-12` 通过。q 端口计数为 `[76,76,76,76,0,76,76,76]` | maps/action worker 总分类为 `WORKER_FAILED`，保存 raw 为 `PARTIAL_COMPONENT`；完整 off-diagonal 算子门未资格化 |
| P2：Ny=8 FE RHS | 独立的 RHS fold/lift/gauge attempt02 通过。保存向量独立复核的 26 项通过：16 项 source fold、8 项伴随功恒等式、2 项重构 | `PASS_ACTUAL_RHS_FOLD_LIFT_GAUGE`；一个固定 `C alpha` 向量见证不等于完整 C 算子列资格 |
| P3：B0 row-tile CSR | B0 p6、四 q 的 00/01/10/11 四块均与 legacy 结果数值等价；组件总状态通过。新方案按输出行分块合并稀疏项，避免构造随行列数平方增长的全形状 bitset | 只证明 80-cell B0 组件；总构建时间 `60.538 s`，legacy 为 `59.266 s`，新路线在此组件没有更快。另有 50,000 行 hash-bound software fixture 跨过旧形状限制，00/01/10/11 四块通过，`1 passed in 0.48 s`；无 FE 或全局因子，不证明目标容量 |
| P4：原尺寸拓扑与 support | 15,232-cell 目标几何拓扑实测；从 224-cell 原生 p6/MPC 校准推导每 q 的保守 support/CSR 上界；这些上界满足 int32 结构安全 | 目标 p6 空间、数值 CSR、Schur 或因子均未构造；派生上界不是实际 NNZ 或容量通过 |
| P5：Gx560 必要 anchor | V17 row-tile 路线下完成 560-cell、p6、340-mode Full3D 求解；A6、物理输出 checker、与 V16 保存场对照均通过 | 必要离散 anchor 通过；单场完整冷启动关键路径仍 unknown，E1 与目标容量未关闭 |

## 保存局部恢复和独立端口证据

S2 的两组原始 `Vii/Vit/Bi/fi/trace` 与 known-state 输入身份没有变化。直接 `np.linalg.solve` 的 residual 很小，但 forward error 仍超过 `1e-11`；因此保留其负结果，而不把“方程 residual 小”误作已通过 known-state 前向门。已有恢复 helper 对原始 complex128 `Vii` 重算残差，在残差有改善时才接受更新，并重用同一个因子；残差累加使用该环境的 complex256，候选解保持 complex128。top 尝试 2 次、接受 1 次，第二次残差未改善而停止；bottom 接受了最多 3 次更新。逐步原矩阵残差轨迹保存在 replay receipt 中；top 与 bottom 的 refined state 分别达到 `5.35247e-14` 和 `5.14331e-14`，独立 checker 重新打开保存数组后复算通过。这个结果关闭了保存小系统上的恢复回退，不表示所有生产 cell 都已加入多次修正。

P4 D checker 使用独立解析矩阵作用，覆盖 top 和 bottom 各 882 个原生行、每面各 16,030 个有序模式（两面共 32,060 个 face-mode pairs）；top/bottom 的 q60 作用相对差分别为 `4.33e-14 / 2.29e-14`，原/约化端口方程最大相对误差分别约 `6.47e-15 / 5.08e-15`。随后 plane phase/Hp 读回在 `1e-12` 原门内通过。该证据验证保存向量和两端口的全部模式行，仍不等于全局目标矩阵或所有可能输入向量的算子范数证明。

## Ny=8 的 q=4 解释与门限

Ny=8 继续使用两个 y 单元作为局部窗，实测四个平移副本 `K=4`，所以总共有八个 global q。记录中的 `[76,76,76,76,0,76,76,76]` 是每个 global q 上的**端口模式数**，并非 FE q 的存在标志。原生 inventory 明确记录 `global_q_coverage=[0,…,7]`、`all_FE_q_covered=true`、`all_ordered_modes_covered_once=true`；q=4 的 FE sector 存在，只是该层没有端口模式。冻结于 `d790964079628e7fadaa84354bc209db4262ecb9` 的 adapter 已按空端口集合处理，因此该计数不构成放宽 mapping 门限的理由。

实际 p6 FE RHS 路线另行测量并通过 source fold、primal/dual work 和四 twist 重构。maps/action 原始工件仍标为 `PARTIAL_COMPONENT`，worker 仍保留 `WORKER_FAILED` 分类；它的有限 regular-reference action witness 不能替代完整 off-diagonal operator 门，RHS 单向量通过也不能证明完整 C 算子列。Ny=8 target KSP、全局因子、缺口算子完整矩阵和官方 R/T/A 都是 `not_run`。

## 行分块构建与目标 support 的边界

行分块 CSR 的做法是一次只处理一段输出行，收集这些行实际需要的列位置，再写成排序的稀疏行结构；这样能避免先分配整个 `rows × columns` 位图。B0 实际组件覆盖两个 sector 的四块矩阵，candidate 与 legacy 均独立生成并逐块比较，四块误差均通过；candidate 两-sector 汇总 `60.537550 s`，legacy `59.265882 s`，所以它证明功能等价，不是这次小模型上的速度收益。原始 B0 收据记录了逐阶段工作量：q pair `[0,2] / [1,3]` 分别有 `516/669` 次 pattern layout、每个 pair 各 1 次 layout pass，`516/669` 次 numeric contribution、每个 pair 各 1 次 numeric pass；projection 与 sparse accumulation 调用数各为 `2064/2676`。pattern 时间为 `3.326/3.578 s`，numeric parent 为 `21.028/26.355 s`；其中 contribution generation `2.337/2.950 s`、projection `8.146/9.840 s`、accumulation `1.599/1.933 s` 是 numeric parent 的子区间，不重复相加。support-route flush 为 `40/51` 次，descriptor logical I/O 分别读 `24,140,016/29,054,640 B`、写 `1,322,896/1,680,096 B`；每个 sector pair 的最大同时 scratch 为 `53,684,424 B`，低于 `268,435,456 B` staging contract。另有 hash-bound 50,000 行软件边界 fixture：四块通过，`1 passed in 0.48 s`；它不构造 FE 或全局因子，也不证明目标容量。

Gx560 是原尺寸 `50×25×140 nm` 几何按 `7/135` 缩小后的解析模型，冻结输入的周期为 x=`2.5925925926 nm`、y=`1.2962962963 nm`，z=`[-0.5185185185, 6.7407407407] nm`；它不是原尺寸场。原尺寸几何拓扑实测为 `272×4×14=15,232` cells。p6 full-storage rows `10,228,620` 与 periodic-independent rows `9,948,672` 是由实测拓扑和 224-cell native p6/MPC 校准派生的计数，不是目标 FE space 的实测 DoF；目标 FE space 未建立。每 q 的 781,500–781,624 行及约 1.767–1.788 billion 结构 NNZ 是通过该校准得到的保守上界；四个不同 q 的 payload 上界合计 142,503,121,344 B，但它不是某一时刻同时存活的 owner 峰值。int32 结论只限于这份结构上界的形状、列号和 offset。目标 q 的实际数值 NNZ、CSR `indptr`、填充、因子和同时存活 owner 仍未测量。

## Gx560 正式结果

Gx560 使用相同的 0.7 nm 非可分三维几何、560 cells（10×4×14）、p6、340 个有序模式与四个 q。四个 q 的 CSR rows 为 `28,508 / 28,508 / 28,576 / 28,508`，NNZ 为 `15,457,680 / 15,483,524 / 15,600,060 / 15,483,524`，合计 62,024,788。三步外层迭代后的完整 target A6 为 `4.7044300024e-9`，独立 native witness 为 `4.7043098759e-9`，均低于 `1e-6`。

V17 延续既有 V15 reference-PC 合同：每次 PC 对 q 的 bounded solve 上限为 `1e-8`，逐 q strict true-residual 门为 `1e-10`；alpha closure 为 `1e-9`，native complete/eliminated FE 与 noncancelling budget 为 `1e-8`，decomposition closure 为 `1e-10`；每次最多允许一次整体增广修正。三次调用都由初始状态通过并选中，实际没有执行额外增广修正。

| PC call | q0/q1/q2/q3 true residual（均通过 `1e-10`） | native complete FE residual | alpha closure residual |
|---|---|---:|---:|
| 1 | `2.930e-11 / 2.322e-13 / 7.951e-14 / 3.021e-13` | `1.144e-10` | `9.848e-14` |
| 2 | `2.964e-11 / 4.894e-13 / 2.024e-13 / 4.145e-13` | `7.559e-11` | `1.852e-13` |
| 3 | `3.857e-12 / 5.942e-13 / 4.636e-15 / 5.977e-13` | `7.600e-12` | `1.709e-13` |

官方端口 modal amplitudes 给出 `R=0.07612406709`、`T=0.90576922010`、`A_balance=0.01810671281`；体积分吸收 `A_volume=0.01810671258`，两种吸收估计相差 `2.37e-10`。零级反射分别为 `R00_s=0.07612359351`、`R00_p=7.34e-22`、`R00_total=0.07612359351`。attempt04 独立输出 checker `PASS`（SHA-256 `3131b161…3637492`），row-tile assembly 与 allocation-ledger 两个 guard 均非空且通过；checker 从保存的 CSR 证据复算 guard 指标，但没有重新作用数值 operator。它逐个检查 q pair `[0,2]` 与 `[1,3]` 的四块矩阵，两个 sector 的 staging peak 均为 `69,154,421 B`，对应完整四块 CSR payload 为 `1,242,673,808 B` 与 `1,239,138,064 B`；两 sector 顺序构建，payload 合计 `2,481,811,872 B` 不代表同时存活量。allocation ledger 有 `19,379` 个完整 admission、0 个不完整 admission。旧 `9e3f64e0…3f1b1` receipt 仍保留为基础输出复核，其 V17 guard 槽为空，不能替代 attempt04。与 V16 保存场对照使用共同 560 个子单元和相同物理/网格/MPC/模式身份，E/H/scaled-curl、340 模式功率及冻结显著模式振幅都通过原门；两次输入文件 SHA 不同，不能称为逐字节相同的输入。

四个 q 因子同时 live 时，原始 receipt 中 INFOG19 allocated upper 合计为 `4,692,000,000 B`、INFOG22 used upper 合计为 `4,118,000,000 B`；销毁前最后一次同时树 RSS 采样为 `10,022,801,408 B`，不是销毁后的零值。纯 `PETSc.KSP.solve_only` 时间为 `71.630558198 s`；四个 q 的 numeric factorization 时间为 `4.063932/3.953524/4.011221/4.408180 s`，对应 numeric true residual 为 `1.522e-11/2.631e-12/9.171e-13/2.767e-12`。run_case 父段 monotonic 为 `2112.6819 s`，watchdog interval 为 `2112.5596 s`，两者是不同计时口径，不能相加。进程树 RSS 峰为 `10,133,843,968 B`，专用 cgroup memory peak 为 `11,170,443,264 B`；任务树和 cgroup swap 均为 0，PSS 未采样。WSL 全局 swap 在此区间变化为 106 页入、8,774 页出，但无法归属到该任务。正式 worker 计时与后续 checker 修复/场比较没有完整闭合为一个冷启动关键路径，因此完整单场总时间保持 `unknown`。同范围单次观测中，V16→V17 parent interval 从 `2274.267412469 s` 到 `2112.681948589 s`（少 `161.585464 s`，约 `7.10%`），树 RSS 从 `10,204,880,896 B` 到 `10,133,843,968 B`（少 `71,036,928 B`，约 `0.70%`），cgroup peak 从 `11,907,702,784 B` 到 `11,170,443,264 B`（少 `737,259,520 B`，约 `6.19%`）；两次 allocated factor upper 都为 `4,692,000,000 B`。这是单次观测差，CPU 供给/主机状态未受控，host-global swap 不能归属到任务，且 V17 checker 修复及保存场比较在 worker 外；不能归因于 row-tile builder 提速或当作完整冷启动时间。第一次 launcher route preflight 因缺 V17 固定窗口登记在 FE 启动前失败；保留该工程失败记录，修复后的 Gx560 attempt02 才是正式数值运行。

## E1 与原尺寸 readiness

本轮没有新启动 E1。当前更新的几何和类库存显示 E1 为 760 cells、156 个 raw geometry classes、231 个 oriented classes。assembly workspace payload 上界为 5,559,442,632 B；装配后 retained numeric owner 公式为 2,877,242,904 B；没有当前 E1 销毁后 OS/cgroup 释放测量，release credit 为 0。缺少所有同时存活体积对象、raw/oriented tensor、Schur/cache、factor、恢复和输出 owner 的完整阶段交叠账，因此仍标 `HELD_INCOMPLETE_CURRENT_OWNER_EVIDENCE`。历史 V15 的 `19,192,602,560 B` 是旧投影，不能冒充 V17 测量或当前 E1 总投影；本轮不是一次新的 E1 resource stop。

V17 固定窗口未刷新。既有 campaign API 在 `2026-10-08T06:54:16.097512Z` 记录 as-of observation：累计保守 charge `22,569.02541851903 s`，剩余 numerical budget `63,230.97458148097 s`。这按窗口相邻时钟计费，包含工程、等待和执行经过时间，不是 PDE CPU 或正式运行时间之和；该观察之后的文档与审查仍继续计费。V16 窗口历史累计 `85,892.89690395721 s`、剩余 0；窗口外准备成本保持 `unknown`。

原尺寸 `50×25×140 nm` 的 q CSR、完整数值因子、全物理求解与 y/z 精度均未资格化。2 TB 十进制内存和 48 h 单场目标仍为 `NOT_QUALIFIED`，这代表当前证据不够，不代表已经证明模型不可计算。ordinary default 未改，master 未合并，也没有作选择性合并批准。

## 测试、文档与证据入口

本轮代码路由定向记录为 24 passed、18 deselected；它只覆盖 launcher/run_case 路由，不等于全仓套件。Ny=8 ABI/import preflight 是 no-FE runtime 检查。P1、P4、Ny=8、B0 与 Gx560 的数值和组件结果均按各自原始 receipt 分类，不折算为 pytest 通过数。文档合同测试、JSON 语法和差异检查在最终文档更新后单独记录于 [测试摘要](outcomes/test_summary.md)。full repository pytest、MPI4、Ruff 和 GitHub Actions/CI 未运行。

四份分主题记录为：[component closure](outcomes/records/review_v17_component_closure.json)、[sparse capacity](outcomes/records/review_v17_sparse_capacity.json)、[formal results](outcomes/records/review_v17_formal_results.json)、[cost and readiness](outcomes/records/review_v17_cost_and_readiness.json)。总账、测试摘要和 run index 保留各项 raw artifact path 与 SHA。GitHub 网页 rendered view 本轮受工具 Cache miss 限制，标记 `NOT_VERIFIED_TOOL_LIMIT`；这不影响本地 Markdown/文档合同测试结果，也不触发科学重算。
