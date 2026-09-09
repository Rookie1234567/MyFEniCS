# V7 有界非精确外层：J1 控制、B finite 与 A/B 原始模型收口

本页是 Task39extra V7 的中心结果页。它只覆盖有界内层、有限控制和两条冻结候选的正式外层进展；不覆盖新的物理输出，也不改写 V5 成功基线或 V6 诊断负结果。

## 最终判定

| 对象 | 正式结果 | 适用边界 |
|---|---|---|
| V5 BAL_H 原始模型与唯一 notch | 两个完整模型通过残差、离散参考和物理 Gate | 仍是本任务唯一的双模型 complete success；参考 workflow 的 448 页 global `pswpout` 归因仍为 `UNRESOLVED` |
| V6 递归/粗层诊断 | 已关闭为 `COARSE_APPROXIMATION_UNQUALIFIED` | 保留全部 G1/G2/V6 负结果；不重跑、不把诊断通过提升为生产 solver |
| V7 A：`bounded_entity16_v7` | 121 步后 `PROGRESS_INSUFFICIENT_AT_MID_BUDGET` | 有界 I4、成本和资源检查通过；真残差未过中点线，官方输出未运行 |
| V7 B：`bounded_projected_seq2_16_v7` | 88 步后 `PROGRESS_INSUFFICIENT_AT_MID_BUDGET` | finite 与控制通过；真残差未过中点线，官方输出未运行 |
| V7 总结 | 两条冻结 bounded 候选均为 controlled negative | 只关闭本轮这两条路线；不能推出所有无 global p4 LU 方法都不可能 |

A 的中点真残差为 `0.042564512128266646`，full explicit 值为 `0.04256451212826674`，process-tree RSS 峰为 `1449623552 B`；B 的中点真残差为 `0.06385558342151046`，RSS 峰为 `1517813760 B`。两者都没有生成可用于验收的 fields、R/T/A、`A_volume`、近场或 notch 结果。

## 方法的通俗说明

这两条路线都试图用小的、受内存约束的局部修正，帮助 p6 外层 Krylov 迭代逐步降低真实残差。A 使用高阶边/面实体局部修正，共 1566 个实体小因子（792 edge、774 face）；其中的 `16` 是 I4 的最多内层步数，不是因子数量。B 把 252 个局部因子按 `(i+j+k)%2` 分成两个各 126 个的 parity group，先作用第一组，再作用第二组，中间只做一次完整的 trace operator `T`。这个顺序组合可以保留两组之间的块耦合；它不是一个全局 p4 矩阵或全局 p4 LU。

B 的代价也因此更明确：需要保存并恢复 252 个 144 维局部因子，并在每次外层 PC 中承担完整 `T` action、两组 patch backsolve 和 p2 bottom solve。B 的 finite witness 证明了 additive 与 sequential 的输入、约束和算子闭合关系，但没有证明外层长尾会消失。

`1e-4` 是 I4 的 inner early-stop target，不是 bounded outer 的 hard Gate。B 的 176 次 I4 都是合法的 `INNER_APPROXIMATE_RETURN`，每次最多 16 步，观测耗时均低于 30 秒；A 的 242 次 I4 也都在 16 步上限返回。outer 只把这些近似修正作为预条件作用，最终资格仍由 full explicit true residual 和物理输出决定。

native A4、旧 S bridge、输入不变性和 slave constraint 的闭合检查都通过；这说明实现所调用的局部算子之间没有被本轮审计发现的代数断裂，但没有解决 outer residual longtail。B 的额外 complete `T` 和 252-factor patch 工作在当前实际成本下没有优于 A。这个结论是两条冻结候选的实测比较，不是对所有其他近似方法的不可行性证明。

## A/B 每 8 步残差对照

下表使用各 run 的 full explicit true relative residual。B 在第 88 步触发中点停止；A 继续到第 121 步，因此 B 后续列为空。

| 外层步数 | A entity16 | B projected seq2 | 说明 |
|---:|---:|---:|---|
| 0 | 1.0000000000000000 | 1.0000000000000000 | zero start |
| 8 | 0.8726387558644422 | 0.8980825870473894 |  |
| 16 | 0.4950831369874051 | 0.5359412651884803 |  |
| 24 | 0.2483893141507852 | 0.3095475798583370 |  |
| 32 | 0.1223130735441403 | 0.1731681894882569 |  |
| 40 | 0.1159241650658259 | 0.1659201758526075 |  |
| 48 | 0.1059299391068872 | 0.1558182920852662 |  |
| 56 | 0.0751498225672801 | 0.1473768866960829 |  |
| 64 | 0.0612938700116273 | 0.1076690077099471 |  |
| 72 | 0.0597008436640465 | 0.0947969453681564 |  |
| 80 | 0.0553782701369625 | 0.0792671982435583 |  |
| 88 | 0.0500041776570931 | 0.0638555834215105 | B midpoint |
| 96 | 0.0468733293992664 | — |  |
| 104 | 0.0463218422737854 | — |  |
| 112 | 0.0446280831382297 | — |  |
| 120 | 0.0427058020004082 | — |  |
| 121 | 0.0425645121282666 | — | A midpoint |

两条曲线都在下降，但到冻结的约 5400 秒中点仍分别高于 `1e-3` 进度线，更远高于正式 full residual `1e-6`。B 在第 30 步 screen 的 residual 为 `0.20693967916705572`，screen 通过并继续使用同一个 live KSP；没有因 screen 重启或创建第二个 KSP。

## B finite 与 J2 控制

B finite run 只使用一个当前原始网格 p4 RHS，禁止使用 `e`、reference `y` 或旧 PC 输出。其关键事实如下：

| 控制 | 实测结果 |
|---|---|
| finite witness | `FINITE_COMPARISON_COMPLETED`；输入 unchanged，slave max `0.0`，seq2 explicit relative `0.0` |
| finite formula | `M0 + M1 - M1*T*M0`，其中 `T = F^H A4 (I-CU A4) F` |
| finite local layout | 252 个 144 维因子，parity groups `126/126`，每次局部回代 252 次 |
| complete PCs | A2R160 `61.498345635 s`；LIGHT448 `57.656247095 s`；一条 PC 小于 90 秒，`J2_ADMISSION_OPEN` |
| finite bounded counts | setup 1；complete PC 2；I4 4；实际 H6 2；I4 每个 PC 2 次 |
| finite raw recheck | bounded I4 与 projected trace 通过；A4/B4 各 63，显式 A4 12，T calls 63，底层 bottom MatSolve 189，patch backsolves 15876 |

有限 controls 的独立审计实际看到 4 条 audit：自动 iteration-one、两个 control 各一条和 exit。通用 `bounded_costs` checker 的旧期待值是 2，因此独立 raw recheck 对该字段返回 false；这是 checker contract 的计数差异，不是生产 application 冒充或 finite 数值失败。正式 outer checker 的原规则保持不动，finite-only 根目录的 `checker.json` 仍为 `EVIDENCE_INCOMPLETE`，因为它没有 `physical_intermediate_summary.json`。

完整的有限记录、旧 checker 和独立重算入口见 [B finite compact](records/bounded_inexact_outer_b_controls_v7.json)。

## V5 完整成功基线与 V7 提前停止的总成本对照

V5 是已经完成官方输出和物理 Gate 的成功 baseline；V7 A/B 都在中点提前停止，不能按较低的步数或 RSS 宣称更快得到正确解。下表保留完整 workflow 的时间与 process-tree RSS 口径，V7 的时间注明为本轮受控停止所能观测到的 workflow/whole conservative 时间。

| 模型 | 终态 | true residual | R/T/A | solve / workflow 时间 | process-tree RSS peak |
|---|---|---:|---|---:|---:|
| V5 original BAL_H | 564 步，完整成功 | `9.932289219916342e-7` | `0.365625791/0.0129906323/0.621383577` | solve `6102.6143 s`；whole `6997.531 s` | `3466235904 B` |
| V5 notch BAL_H | 576 步，完整成功 | `9.35170551675826e-7` | `0.337120585/0.0162886742/0.646590741` | whole `7058.7424 s` | `3600924672 B` |
| V7 A entity16 | 121 步，中点失败 | `0.04256451212826674` | `not_run` | parent/whole conservative `5637.122687149011 s`；workflow monotonic `5167.972956766025 s` | `1449623552 B` |
| V7 B projected seq2 | 88 步，中点失败 | `0.06385558342151046` | `not_run` | parent/whole conservative `5622.279368720655 s`；attempt charge `5622.384071101 s` | `1517813760 B` |

V7 的失败 workflow RSS 低于 V5 完整 workflow 的 RSS，但两者不是同一成功条件：V5 已完成 residual、fields 和物理输出，V7 没有。因此这组数据只能说明失败运行的资源观测和停止位置，不能形成“总时间/RSS 更优”的 solver 结论。A 的 `workflow monotonic` 与 B 的 `parent/whole conservative` 属于不同计时口径，不能直接互比；统一比较使用上表的 parent/whole conservative 值。

## 两条外层的实际成本与资源

| 指标 | A `entity16` | B `projected seq2` |
|---|---:|---:|
| outer iterations / PC / I4 | 121 / 121 / 242 | 88 / 88 / 176 |
| B4 / A4 matvec | 3872 / 3872 | 2812 / 2812 |
| S/bottom MatSolve | 7744 / 7744 | 8436 / 8436 |
| B patch backsolve / T completed | 未采用 projected patch / — | 708624 / 2812 |
| refinement | 0 | 0 |
| native volume+DtN cache completed | 11617 | 14061 |
| model attempt charge | `5637.269656583 s` | `5622.384071101 s` |
| process-tree RSS peak | `1449623552 B` | `1517813760 B` |
| process-tree swap peak | `0 B` | `0 B` |
| global swap delta | `0/0` | `0/0` |

B 的完整计数还包括 `88PC/176I4/2812B4/708624patchbacksolve/8436S-MatSolve/refine0`，A 的核心计数为 `121PC/242I4/3872B4/7744S-MatSolve/7744bottom/refine0`。当前共享账本在 finite preparation、controls 和两次外层尝试后为 `total_charged_seconds=12327.598368146999`、`remaining_seconds=30872.401631853`；B 账内已包含 `132.113 s` preparation charge，模型等待时间不重复计入。

两次 process-tree RSS 都低于 2 GB，但这是受控、未完成 outer PDE 的进程树观测，不能写成“2 GB 成功 PDE”或完整求解能力证明。B 的 p2 bottom `rows=7326`、`NNZ=818100` 和 factor 预算是 derived policy budget，不是 RSS 上界；全局 p4 matrix/factor 均未使用。

仍需把扩展债务单独记账：当前 B 仍依赖全局 S/p2 bottom factor（`7326 rows`），252 patch 的历史构造约为 `1603.835 s` 和 `36288` 个 S columns。当前 run 中出现的 `restored_factors=252` 表示复用已保存结构，不表示 fresh 构造成本消失；因此 0.7 nm 扩展债务仍未解除，也没有获得 workstation qualification。

## 负结果、官方输出与因果边界

- A 和 B 都在规定 midpoint 处未达到 `true relative residual <= 1e-3`，也没有达到正式 `1e-6`；二者均不具备本轮 notch 资格。
- fields、near-field、R/T/A、`A_volume`、能量闭合、显著衍射级和 official release 均为 `not_run`，不是 physics mismatch。
- V5 两个完整模型的成功结果仍有效；V6 的互补场、粗层驱动抵消、MR 小步长和 0.7 nm/2 GB 边界仍按原 compact 保留。
- V7 只能关闭 `bounded_entity16_v7` 和 `bounded_projected_seq2_16_v7` 两条冻结候选。它不能证明所有没有 global p4 LU 的方案都不可能，也不能把低内存但未完成的运行升级为生产资格。

## 证据入口

| 内容 | 入口 |
|---|---|
| A 原始外层 compact | [bounded_inexact_outer_a_original_v7.json](records/bounded_inexact_outer_a_original_v7.json)；本轮保持原字节不变 |
| B finite controls compact | [bounded_inexact_outer_b_controls_v7.json](records/bounded_inexact_outer_b_controls_v7.json) |
| B 原始外层 compact | [bounded_inexact_outer_b_original_v7.json](records/bounded_inexact_outer_b_original_v7.json) |
| V6 中心报告与 compact | [coarse inverse replacement V6](coarse_inverse_replacement_v6.md)、[V6 compact](records/coarse_inverse_replacement_v6.json) |
| V5 双模型中心报告 | [balanced coupling V5](balanced_coupling_v5.md)、[V5 compact](records/balanced_coupling_v5.json) |

B compact 绑定 source `355322e8be0716cdc3dd70df2665b8c74ff76583`、input SHA `f0b470a098879c8c6cd85b532c156ab8cec2a9c479e64fd69d28fb265b813022`、physical model SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` 和 mode SHA `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。A compact 绑定其自身 source/input 身份；两份 compact 都保留各自 raw root、关键 JSONL、checkpoint 和 SHA。

本页对应 J5 文档收口；不授权新的 heavy case、延长 outer、改 checker、改生产默认或启动 workstation 0.7 nm 路线。
