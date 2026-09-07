# Task39extra Review V1：保留物理修正正信号，压缩单步成本并连续检验轻量组合

## 0. 审阅身份与执行裁决

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = task39extra
reviewed_HEAD              = 836619bbfd6ebe8f73a4b0f954bd34d54523587c
original_task_base         = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
review_date                = 2026-09-07
reviewed_response          = response_v1.md
A2R_measurement_source     = 54ab46cf4c8378a9b27650ca6963cadb34013a2f
postmeasurement_cost_fix   = adc448814c3022fdf6d1a688da69a28238e7db9c
response_required          = response_v2.md
execution                  = R0 -> R1 -> conditional R2 -> conditional R3 -> R4 -> R5 -> R6
mandatory_review_stop      = R6 closeout or unresolvable common safety/correctness blocker
master_merge               = NOT_APPROVED
workstation/5nm/0p7nm_PDE   = not authorized by this review
```

本轮首先消除的 blocker 是：**准确 p4 物理修正已经能够在本机运行，但完整预条件器每步成本高，尚未取得原始 p6 物理解。先尝试保留数学作用的性能优化；若收益不足或完整求解仍未通过，连续进入一个预先定义的轻量 PC，不在每个阶段停审。**

最终目标不变：约 2 TB 整机内存内，0.7 nm、complex128、Nedelec H(curl)、双 Floquet、z 开放的任意非可分三维周期单胞。当前在约 16 GB 本机上只运行 13.5 nm；不把更快的辅助计算当最终目标，不转准二维。

接受 Response V1 对已测结果及边界的记载，不授予 solver/production/merge PASS。旧 `PERFORMANCE_CONTROLLED_STOP`、未完成尾段及全部负结果保留。A2R 出现了值得保留的阶段性下降，不等于已经证明最终收敛。

用户本轮要求连续多推进。本 Review 前瞻性扩展 task.md 的单一候选和停止规则：允许下面一个等价优化版本和一个轻量结构版本，以及条件完整求解与非可分挑战。**不是无限候选搜索，也不是原样延长旧 A2R。** task.md 和旧记录不覆盖；仅冲突的执行权限以本 Review 为准。

## 1. 已核对结果：22 秒不是通用失败门槛

来源为 [Response V1](response_v1.md)、[summary](outcomes/summary.md)、[run_index](outcomes/records/run_index.json)。以下时间单位 s，内存为十进制 B/GB；派生平均不冒充新实测。

| 对象 | 结果 | 数据身份与边界 |
|---|---:|---|
| 原始模型 | 13.5 nm、1°、p6/h10、MPI1、80 modes | measured identity |
| p6 / p4 独立 rows | 164592 / 48960 | measured |
| p4 增广矩阵 | 53164 rows，24730144 NNZ | measured；不是 fine direct |
| p4 参考求解 | 163 RHS，最大原 A4 相对残差 5.7889315844880267e-11 | measured；每次限值 1e-10 |
| A6 第 32/64/96/128/160 步残差 | 0.463384 / 0.410054 / 0.313986 / 0.275389 / 0.182508 | measured；目标 1e-6 未达 |
| 五个完整周期 | 合计约 3528.55 s，160 步 | derived sum；约 22.05 s/step |
| 完整 PC | 中位 20.6115 s；163 次总 3360.9387 s | measured aggregate |
| positive_pre / physical_middle / positive_post | 1451.4745 / 457.1767 / 1452.0173 s | measured nested stage totals |
| p4 reference solve 加原 A4 检查 | 合计 79.7010 s，约 0.4890 s/RHS | measured/derived；已包含于 middle，不再累加 |
| RSS / 动态 cap / swap | 3588677632 / 8736759808 / 0 B | sampled simultaneous process tree |
| 最终尾段 | 163 完整 PC，第 164 partial；最后合法 checkpoint=160 | 停止瞬间最终残差、正常 recovery 未取得 |

预后两个阶段约占 PC 时间 86.4%，但其中包含各自 MR/真实 A6 检查，**不能把阶段总耗时全部归于 S6 内部，更不能因为耗时大就认定无贡献**。163 个输入来自不同 Krylov 方向，不是一条中间残差曲线。既有 S6/S3 累计序号误加已由 checker 重算，不为计数修复重跑 PDE。

22 秒取决于一遍 PC 的工作量、机器、实现和收敛效率，不能单看这个数字判定算法坏。当前代码的一遍 S6 含两次 degree-3 Chebyshev、两次 B6 residual action 及 p3/p1 路径；按实现推导每遍 S6 含 6 次 B6 action，两遍共 12 次。该计数须在 R0 用实际增量确认，不将生命周期序号相加。

旧 standalone S6 并非永远卡在 0.48：后续 restart64 continuation 到历史 checkpoint3048 约为 0.1535。A2R 的 160 步改善是阶段性信号；不同 restart、起点及单步工作量不能换算成严格 speedup。

## 2. 本轮成功指标与比较口径

目标优先级：完整原始物理解和非可分三维结果 > 达到指定残差的总时间 > 再压单次 PC 时间。不得以“22 秒压到 5 秒但不能收敛”替代成功。

```math
T_{\rm full}=T_{\rm setup}+T_{\rm solve}+T_{\rm release/post},
\qquad
T_{\rm solve}=\sum_k(T_{\rm PC,k}+T_{A,k}+T_{\rm orth,k}+T_{\rm other,k}).
```

必须报告 cold setup、warm apply、完整 solve 和输出阶段；嵌套计时不重复相加。未达到 1e-6 时 `time_to_1e-6=not_reached`，不能用拟合值冒充。对两次都达到的残差门槛比较实测 time-to-residual；同一步残差只作补充。

性能筛选预先固定：同机同输入的完整 PC 中位耗时减少至少 25% 为本批次“足够进入完整等价复跑”的工程线；50% 为强收益，约 5 s/PC 只是 stretch，不是普适要求。小于 25% 不等于算法无效，含义仅是停止继续微调该等价优化批次，转 R3。局部内核快十倍而完整 PC 未改善，不算达线。

## 3. 冻结身份与必须保留的条件

沿用 task.md §3 的 A2 物理模型、p6/h10、完整三维网格、原始材料和入射、80 个完整 DtN keys、quadrature、独立/存储 DoF 语义。不得缩域、降阶、加物理损耗、改角度或减模式来提速。

```text
physical_model_sha256 = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
mode_manifest_sha256  = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
```

新 backend/profile/预算写入显式 `.dat` 和 resolved config，actual input SHA 重新计算。正式入口仍为 `python scripts/run_case.py input/path/to/case.dat`。每个 dat 对应一次明确计算，禁止同一 dat 隐藏循环启动多种 PC。

R2、R3 均保持准确 A4 参考、原 P64/P64^H、三个 MR 方向处理、right FGMRES32 和 zero start；改变点仅限下文白名单。p4 参考一次 symbolic/numeric、重复 RHS 回代，每次显式检查原 A4 residual<=1e-10；不显式形成 A4 逆、不用 fine A6 LU 作 PC。

本批次仍为 reference-assisted 研究。即使取得场，53164-row p4 factor 也不能被称为有界生产 coarse 或 0.7 nm 可扩展解。原 positive/shifted p1 的 4096 rows/512 MiB 限制不取消；R3 未用的底层应不创建或安全释放。

## 4. R0：利用已有记录并定位最多两个主要热点

先核对当前 worktree、是否已有 heavy、raw 哈希与 source/physical/mode 身份。远端未变化不等于本地未运行；不重复启动，不擅自中止已有任务。A2R 原 raw 不修改。

离线读取 163 个完整 `pc_applies`，按 32 步周期及末尾 3 个完整 PC 汇总每阶段 raw_unit_rho、MR 后 rho、alpha、残差范数、方向范数和成本；第 164 partial 不补全。不能按 alpha 大小单独判断有效性，它依赖方向缩放。

```math
\eta=\frac{|(A_6d)^Hr|}{\|A_6d\|\,\|r\|},
\qquad \rho_{\rm MR}^{\,2}=1-\eta^2.
```

上式是非零方向、精确一维 MR 的代数关系；从 rho 派生 eta 时记录舍入误差，明显越界不静默 clip。各阶段 residual 和外层物理 residual 不是同一个量；阶段效果有顺序依赖，离线贡献不能证明“删掉此阶段也不影响以后迭代”。

若已有数据不能细分时间，只增加轻量事件计时：B6 action、P63/P63^H、B3/p1、P64/P64^H、A4 回代/检查、A6 volume/DtN、MR/Vec、日志与采样。采用 PETSc events 或低开销单调时钟，核对实际 3.19.6 等本机版本；不升级环境、不把开发主分支API当本机必有功能。禁止 `-info` 洪泛或逐向量日志进入性能比较。

一次原始规模 profiling 构建，最多 3 个合法输入：归一化 physical RHS、合法恢复的 checkpoint160 残差、固定 seed 的独立复向量；checkpoint不可用时用前两种可获得的输入完成，报告缺口，不因此新开长跑。旧/新完整 PC A/B 对照最多 16 次 apply（含预热和重复），该计时批次含 setup 最多 1800 s；不是新的多源收敛 campaign。

只分析前两个主热点。raw 无法取得时不伪造贡献，使用已提交 aggregate 加该窄 profiling；若源/物理身份不可核验，则停止受影响 PDE，不能跨身份猜测。

## 5. R1：一批数学等价的性能优化

### 5.1 保持什么不变

保留 `S6 -> physical A4 reference -> S6` 完整修正过程、原 Chebyshev degree/window/seed、对角、粗算子、transfer、MR、独立自由度和外层 A6。这里优化“同一计算怎么做”，不是“少做几步计算”。

允许针对已定位热点：复用固定几何/材料/基函数和索引信息；批量局部运算与精确 sum factorization/partial assembly；重用 Vec/缓冲；减少不必要的重复打包、转换和数据遍历；只在同一输入和确定依赖下复用已算 action。每次变化的场系数、ghost、MPC phase 及 material tags 必须更新，禁止错误缓存随 RHS 变化的数据。

优化高阶内核限当前已覆盖的 affine Q1 hex、H(curl)、DG0 材料与原积分规则，并明确其他单元支持边界。单元张量结构不等于准二维几何假设；每个单元仍使用自身真实材料/几何。没有必要时不编写新的内核平台。不得形成 global B6/A6 AIJ、dense cell tensor 库、FE-sized Z/AZ 库，或为 warm 数字把冷编译成本移出监控。

未改动的原 A6 action 保留为 true-residual authority；若为 PC 内部新增 A6 等价快速 backend，最终/周期残差仍用原独立 action 检查。p4 已经便宜，不继续追求更小 inner residual 或重开 shifted inner 参数扫描。

### 5.2 等价与资源 Gate

同一合法输入下，受影响的 B6/action/transfer 相对差<=1e-11，完整 S6/完整 PC 输出相对差<=1e-8，同时比较 A6 作用于两种输出的差。零/近零输出另报绝对差并按实际尺度检查，不用 tiny 分母制造巨大比值。复共轭、orientation、多master交叉项、slave-zero、输入不变、repeat/finite 必须闭合。

保留一个合并的 targeted 检查批次；必要原始输入对照与 profiling 共用，不增加 positive-only 资格链。三向量一致不等于全空间证明，R2 的真实外层是最终检验。浮点迭代轨迹不要求 bitwise 相同；出现明显劣化先查等价和身份，不宣布数学等价性自动保证相同步数。

完整 PC 同机 A/B 比值<=0.75 且总资源通过：进 R2。收益不足、或一次明确实现修复后仍未取得可验证等价优化：保留原可信实现，直接进 R3，不停审。不得把不等价的新 backend偷偷带入 R3；若共同底层已损坏且不能恢复，则安全停止。

R0/R1 的性能测量各自最多一次完整构建，必要 correctness tests 集中执行；不反复构建 p4 factor做几十组 compiler/backend/线程扫描。

## 6. R2：等价加速版本的原始完整求解

只有 R1 达线才执行一次。使用新显式 profile `a2r_equivalent_fast_v1`，从零初值开始；不把旧 checkpoint160 的 continuation 当 fresh，也不为本轮先续跑再重跑。

首 32 步就是完整求解的组成部分，不另起 screen。比较旧 residual32=0.463384 的作用仅为回归提示，不设必须逐点更小的微小差异 Gate。profile source 在运行前提交并保持 clean；完整记录全部成本、每步reported及周期true residual。

在下述统一预算内：达到 true residual 与输出 Gate，直接 R4；性能/数值未达目标或资源使此实现不可行，但共同 A6/A4/身份仍有效，直接进入 R3。**不因 R2 失败宣布 p4 物理多层不可能，也不重复 R2。**

## 7. R3：唯一预授权的轻量结构 PC

### 7.1 为什么试，以及哪里改变

准确 p4 已承担一部分全局修正，旧 S6 还在每侧完整走 p3/p1 层级。本候选检验：能否只保留 fine-level 的便宜平滑，让 p4 负责主要全局修正，从而降低重复粗层工作。

设 H6 是旧 `FixedChebyshevJacobiPETSc` 在 B6 上的一次 degree-3 作用，**不是完整 S6，也不是一个已经不存在的 B6 显式逆矩阵**。使用同一精确 Jacobi 对角、同一 deterministic power10 规则和 window factors；不在真实不定 A6 上直接套 SPD Chebyshev。

```math
\mathcal P_{\rm light}:\quad
H_6\ \xrightarrow{\rm MR}\
P_{64}A_4^{-1}P_{64}^H\ \xrightarrow{\rm MR}\
H_6\ \xrightarrow{\rm MR}.
```

逐段仍使用更新后的 residual，沿用原三个 MR 接受公式和计数。p4 原矩阵/直接精度/P64不变；新 profile 为 `p6smooth_p4ref_p6smooth_v1`。

每次 PC 的 positive 路径 H6 调用 2 次，S6 调用 0 次，p3/p1 positive coarse solve 0 次；按现代码 degree-3 推导 B6 action 从 12 次降到 4 次，实际计数必须确认。A4 仍一次解，MR 仍三次原 A6 检查。p3/p1 数据若仅为旧builder暂时保留，计入内存并说明，不假称已释放；优先只构造需要的 p6 shell/smoother。

这是**新 PC 的数学结构变更**，不是R1等价优化。它可能更快，也可能因失去有用粗修正而收敛变差；不能把速度收益预先当解法通过。H6还在全细空间提供修正，不允许退化为仅p4低秩修正。三阶平滑和两次调用固定，不扫描次数/degree/window。

### 7.2 如何检验，不额外停止

R1未达线，或R2未取得完整合格解时，自动进本阶段。只用已有tiny/原始向量检查接线、finite、slave与公式，然后第一场外层就运行原始 p6/h10、零初值。**不以一次 PC rho>某阈值禁止外层，也不为轻量版新建多网格四源campaign。**

保持原 A6、物理、FGMRES32和下述统一预算；同样比较time-to-residual，而不只比较每步秒数。通过后立即 R4。未通过则进入R6收口；本 Review 不授权第三种PC、重开PML/Robin/全谱/GenEO/75D或换p5。

R1的等价优化可用于本阶段，但只能使用已经通过等价检查的backend。若性能不理想来自共同硬件/软件环境，不能换MPI/线程/BLAS后把收益计作PC结构改善。

## 8. 连续运行预算：前瞻性扩展，不修改历史失败

为避免只跑到一小时又在几百步前停止，本轮对新授权 R2、R3、R4 各 case 统一采用：

| 量 | 本轮合同 | 边界 |
|---|---:|---|
| 外层 | right FGMRES，restart32 | 不扫描 restart，保持原内积和归一化 |
| max_it | 2048 | 取代新case的旧512；不追加到几万步 |
| solve wall | 7200 s | 包含全部PC、检查、I/O；不是一定能完成的时间承诺 |
| 完整workflow | 10800 s | 含冷setup、symbolic/numeric、solve、释放、恢复、checker |
| 外层残差 | <=1e-6 | 原始 A6 与 b，不放宽 |
| p4 reference residual | <=1e-10，每次求解检查 | 不以KSP标签替代 |
| 本批次计算累计上限 | 36000 s | 所有测量/测试/heavy job wall合计，含已失败/partial；不含人类等待时间 |

这些是用户本轮连续推进要求下的研究投入上限，**不是残差外推保证，也不授权原样复活旧 run**。只有等价优化有实测收益或新轻量组合才使用新上限。以前的3600秒停止原样保留，不能改判成“旧任务预算其实应是7200”。

最多两场原始模型完整求解（R2、条件R3），其中第一场失败才试下一场；最多一场非可分挑战（R4），最多一场可负担的独立direct控制（R5）。若第一种已经通过，跳过第二种，直接非可分。R5受剩余总预算约束，不能挤占R4。临时计时不是额外的完整PDE。

可预设保守停滞停止：已完成至少256步、且连续4个完整32步周期各自true residual比均>=0.99，才按`STAGNATION_CONTROLLED_STOP`退出该case。没有满足这一规则就按统一步数/时间上限，不按“看起来慢”任意停止。资源、nonfinite、breakdown或用户明确停止随时优先。上游输入/算子/残差authority错误不是更换PC的依据，必须先解决或停止共同路径。

## 9. R4–R6：原始通过后直接进入非可分与交付

### R4：非可分真实三维

R2或R3取得数值/输出Gate后，立即运行 task.md §3.2 的同尺度材料notch，用成功的同一profile、同预算、零初值；不为notch调整平滑器、p4、MR或参数。P64和本模型的A4、B6、对角/window重新按该模型构造，不能复用不同材料下的factor或谱估计值。

新tag recipe必须写入dat/physical SHA，验证同时破坏y均匀和z挤出；没有实现输入入口时按原task允许范围完成最小接线，不用“只测原始规则结构”替代。该case是全三维材料挑战，不宣称覆盖一切几何。

成功同轮保存E/H、近场、全部真实衍射级及R/T/A/A_volume；不得仅保留旧12个通道而遗漏新的n不等于0通道。失败保留`NONSEPARABLE_CHALLENGE_NOT_QUALIFIED`，进入R6，不重新挑更容易结构。

### R5：参考与容量，只做必要补齐

优先读取已有同离散独立数组核验；缺失保持`AUTHORITY_LIMITED`。本批次最多一次原始模型已有Full3D direct独立控制，需同物理、同fine离散、相同mode/quadrature和安全symbolic预审，预算计入累计；不把direct作为新PC。若成本不安全就不跑，不因缺参考把迭代解硬判错误，也不宣称已获全场精度authority。

h5本轮只做无需高成本装配/factor的rows、底层cap和内存增长预审，不再追加一个h5 full solve；其数值资格移交后续review。保留本task底层4096 rows/512MiB界限，不用工作站内存扩充绕开global coarse扩展问题。

### R6：统一收口

R0、R1、R2、R3之间无需中途审阅或等待用户选择参数。成功走到R4/R5；两个候选都未通过、共同安全/正确性阻碍无法消除、或总预算耗尽时收口。提交response_v2后再集中审阅，不自行启动第三PC或5nm/0.7nm heavy。

## 10. 资源、可观察性与退出闭环

沿用task.md §6安全预算：有效RAM/cgroup和available扣至少4GiB或15%整机余量，总hard不超过12,000,000,000B，实际cap可更低；warning=0.85cap。动态余量、zero-swap、一次一个heavy、完整compiler descendants和parent均纳入。记录实际ABI/版本，不能将目录标签当DOLFINx版本证明；不切换系统库或安装新GPU栈。

缓存增加必须给出组件bytes、生命周期和随N增长模型，仍受同一cap；不允许dense全局矩阵或稠密逐cell矩阵库存。计时既不能漏冷构建，也不能把热缓存重复装配多次后平均掩盖真实成本。

每外层步只写轻量reported residual和计数；每8步或距上次合法快照120s（在下一个安全monitor点）构造当前近似解，显式计算原A6残差并更新solution-only安全快照；32步周期仍保留原记录。**监控频率不改变restart，不清空Arnoldi空间，不强制提前重启。** 构造当前解时正确包含当前cycle初值，避免重复叠加；使用实际petsc4py支持的buildSolution或相应安全接口，并计入时间。

这些monitor是在算法安全点执行，不在异步signal handler中做MPI/PETSc。性能停止先请求安全收口，等待不超过60s且仍在内存安全线内；安全点不能到达则硬停并报告last_safe，不伪造最终残差。资源越线立即全树终止，不能为写文件继续超cap。parent独立记录停止原因、信号/时间、所有PID清场及cache-tail；异常释放不能阻止最小失败summary落盘，分别记录secondary cleanup error。

成功流程：保存最终合法解及solution hash -> 释放KSP/PC/p4 factor和无用矩阵 -> 实测RSS -> recovery/postprocess。checker/输出属于同一workflow预算。旧计数误加和旧缺summary不重写；仅修未来路径。

## 11. 数值/物理/状态判定

继承task.md §8：原A6 true residual<=1e-6，reported与显式归一化一致；独立能量闭合 `abs(R+T+A_volume-1)<=1e-5`、`abs(A-A_volume)<=1e-5`；finite、被动性、通道求和、复E/H、canonical与近场齐全。matched同离散参考的E/H相对L2<=1e-4，RTA/A_volume绝对差<=1e-5，显著功率<=1e-6，复幅值向量相对L2<=1e-4；近零项另报绝对误差，不拟合整体相位。不同h不能沿用same-discretization容差声称网格收敛。

| 状态 | 必须如何解释 |
|---|---|
| `EQUIVALENT_SPEEDUP_PASS` | 数学作用对照及完整PC性能通过，不等于完整求解通过 |
| `EQUIVALENT_SPEEDUP_INSUFFICIENT` | 此批次提速不足，自动R3；不否定原PC数学可能性 |
| `LIGHT_PC_FASTER_BUT_NUMERICAL_UNQUALIFIED` | 轻量版更快但未达残差；不能只报速度 |
| `REFERENCE_ASSISTED_ORIGINAL_PASS` | 原始p6问题求解/输出通过，但仍依赖p4诊断factor |
| `REFERENCE_ASSISTED_3D_PAIR_PASS` | 原始与指定非可分case均通过，独立authority/精度限制并列 |
| `PERFORMANCE_CONTROLLED_STOP` / `ITERATION_BUDGET_EXHAUSTED` | 达真实预算而未取得合格场，不等于永不收敛 |
| `RESOURCE_BLOCKED` / `IMPLEMENTATION_BLOCKED` / `EVIDENCE_INCOMPLETE` | 资源、实现、证据分别报告，不改写为算法不收敛 |

不得把reference-assisted pair升级为`LOCAL_13P5NM_3D_READY_FOR_WORKSTATION`的factor-free/可扩展含义。本轮可以得到有用的真实场和明确的机制参考，但A4迭代近似逆及短波鲁棒性仍需后续解决。0.7nm、任意所有结构、2TB容量和production均未由本轮自动证明。

## 12. 代码、提交和证据文件

只改与定位热点、backend选择、H6 adapter、必要nonseparable输入、monitor/退出和checker有关的通用模块。优先复用以下入口，不另造一个大型Task runner：

```text
src/solvers/fullspace_mpc_action.py
src/solvers/fullspace_same_mesh_hcurl_pmg_p6.py
src/solvers/fullspace_lor_edge_geometric_mg_global.py
src/solvers/fullspace_physical_intermediate.py
src/solvers/fullspace_physical_intermediate_runtime.py
src/solvers/fullspace_p4_reference.py
src/runners/physical_intermediate.py
src/solvers/fullspace_memory_first_krylov.py
```

ordinary profile不变；新数值行为显式opt-in。legacy与fast路径可在独立模块/后端保留，不从旧SHA临时import一套不受控代码。正式运行前有clean commit，source前后核对，结果根不可覆盖。不amend、强推、删除旧负结果，不写master，不建新分支。

建议提交：一项性能/退出原型及合并targeted tests；一项条件轻量PC接线（需要时）；随后原始和非可分结果分阶段记录、统一closeout。每小patch不跑全仓；最终task-focused regression集中一次，明确测试属于哪一SHA。无CI不声称CI通过。

新增一个紧凑 `outcomes/cost_and_contribution_v1.md` 和对应小JSON，更新既有summary、run_index、test_summary、workstation_handoff及两个项目总账；不要每个步骤生成平行报告体系。raw vectors/cache/timeline继续ignored，Git记录hash和关键曲线。

response_v2至少给出：实际分支与SHA、哪些阶段被自动触发/跳过、原始22秒口径、热点exclusive/inclusive拆分、数学等价误差与同机A/B成本、轻量版是否使用、time-to-residual/完整wall/RSS、normal/partial退出、所有物理输出、非可分结果、reference-only与独立authority缺口，以及后续需要解决的唯一主要blocker。中途可写增量证据，但不以“需要review”人为停止已授权条件链。

## 13. 审阅依据与边界

仓库依据：[任务书](task.md)、[回应](response_v1.md)、[汇总](outcomes/summary.md)、[运行索引](outcomes/records/run_index.json)、[移交边界](outcomes/workstation_handoff.md)、[S6源码](../../src/solvers/fullspace_same_mesh_hcurl_pmg_p6.py)、[平滑器源码](../../src/solvers/fullspace_lor_edge_geometric_mg_global.py)。文件和数值按reviewed_HEAD解释，不对忽略的raw宣称已独立重算。

方法说明来自PETSc官方 [Profiling](https://petsc.org/release/manual/profiling/) 与 [KSPBuildSolution](https://petsc.org/release/manualpages/KSP/KSPBuildSolution/)，以及MFEM官方 [Performance and Partial Assembly](https://mfem.org/performance/)。它们支持计时和局部算子实现方法，不证明本候选的收敛/速度；运行仍以本机实际API为准。

ChatGPT本轮仅只读审计与新增Review，没有运行PDE或实测加速。Markdown静态结构与远程回读应检查；若无法观察GitHub可视渲染，不把它写成visual PASS。

**最终原则：22秒不是必须放弃PC的理由。先量清楚、保留有效修正并加速；收益不足就按本Review自动测试唯一轻量组合，得到真实模型和条件非可分结果后再集中审阅，而不是无限优化或无限换算法。**
