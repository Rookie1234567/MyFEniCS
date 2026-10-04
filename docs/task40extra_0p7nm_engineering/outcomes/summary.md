# Task40extra 结果总览：Review V8 当前状态；V7–V4 历史记录

## Review V8：W0 身份门停止与 W1 清单只读核验（当前）

W0 在完整 p6 FE setup 前的 532 模式物理身份门停止：异常为 `ValueError: fresh C1 requires the independently regenerated ordered literal532 physical inventory`，不是 PDE 数值失败或资源停机。worker phase 实测 1.5594090659869835 s，任务树采样 RSS 峰 200,359,936 B、swap 0 B；没有 checker、科学 raw 或 official result。W0 未完成。本机 Task40 artifacts 的有界文件名/大小核对未找到旧冻结的 532 行 gold；唯一其他既存模式 manifest 是 80-mode direct-reference 文件，不能替代。新 W0 与旧 WSL 诊断清单均不匹配冻结 hash，因此该身份 blocker 保留。

| 阶段 | 对象与方式 | 当前证据 | 裁决 |
|---|---|---|---|
| W0 正式 worker | 80 cells、p6-only、532 modes、φ=5°、MPI1；本机独立 WSL2 ABI | 当前窗口第 1 次 worker 在 `fresh_p6_cold_setup_begin` 前停止；后代清空；global swap 页增量 0 | `INCOMPLETE / IDENTITY_GATE_FAILURE`；非 FE、solver、PDE 或资源失败 |
| W1 清单身份 | 对原有 32,060 AUTO 清单及 repair 副本分块 hash、逐行重算有序 keys | 两文件均 36,244,923 B、SHA256 `52d7ec…15490d`；ordered-key SHA `03c196…e95dec`；索引 0–32059 连续 | 只读库存身份 `PASS`；未运行生成器或保留全部 mode rows |
| W1 Task042 移交 | 固定 commit `f3bf7942…1794ee59` 的 V38/V39 boundary/native adapter | 记录精确 blob 身份、材料/网格差异、MPC slave 失败及 volume 未资格 | 只读最小依赖说明；未拷贝代码或继承数值资格 |
| W1 FE/q30–q60、W2、dot | 后续数值阶段 | 当前 W0 未完整通过；没有新面片结构积分、体积作用、C1c raw 或 p6 对照 | `HELD / NOT_RUN` |

原件和 repair 的目标物理身份 canonical SHA256 均为 `a855565b…79eaf1f`，组合 inventory identity 均为 `39b457c3…d0c12`。主线 bottom-Si 折射率为 `0.9998851703688496+4.3236152269189515e-6i`，Task042 为 `0.999885140474+4.32477054e-6i`。Task042 每侧 73×36 面片；主线 272×4×14 只是计数候选，所以其 q30 资格不能当作主线误差证明。最小可复用候选是方向边界核与 `E/Eᴴ` native adapter；adapter 的 Task042 direct-carrier helper 需绑定主线接口。

旧三次 worker 已知小计 200.87894401792437 s、`6bbc` 历史准备费用 unknown、V6 settled debit 5428.582333962078 s 均未更改。V8 固定窗口 T0=`2026-10-04T08:55:26.395534Z`、deadline=`2026-10-04T12:55:26.395534Z`；截至 `2026-10-04T11:33:35.805415Z`，按 UTC 边界推导 elapsed=`9489.409881 s`、remaining=`4910.590119 s`。这不是 monotonic elapsed 或收费；整段准备与 W0 总费用仍 `UNKNOWN_NOT_SETTLED`。worker 启动为 1/4；修复额度为 2/3（event 15 原 `NOT_INFERRED` 快照保留）：`4b780d8` 是固定 deadline/控制入口修复，`8553a22` 是用户另行授权的 local WSL2 profile 资格化（保守计为一轮源级变更）；后续无源身份诊断不计修复。

详见 [Response V8](../response_v8.md)、[W1 清单身份与最小依赖记录](records/review_v8_w1_identity_audit_v1.json)和[运行索引](records/run_index.json)。V7、V6 及更早各节继续作为历史记录保留。

---

## Review V6：Gx784 单次运行与保存场后处理收口

V6 按 review 授权只新增一张 14×4×14（784 单元）Gx784 小网格，复用 340 个端口模式和 p6 完整场/p4 校正流程。p6 产生实际完整电磁场；p4 在迭代中校正 p6 误差，收益是保留 p6 输出，成本是另装配和使用 p4 系统。本轮没有第二张网格、AUTO 重生成、dot 执行或原尺寸计算。

| 模型与方法 | 完整残差与官方结果 | 对照和资源 | 当前裁决 |
|---|---|---|---|
| Gx784；784 cells；Full3D p6 + exact p4 correction；340 ordered modes；MPI1 complex128；p6 full rows 530,400；p4 condensed rows/NNZ 67,988 / 26,295,924 | explicit/post-release A6 9.692115162625173e-7（限值 1e-6）；R/T/A_balance/A_volume=0.07612656490058632 / 0.9057668832851113 / 0.01810655181430232 / 0.018106531117781374；能量闭合 2.0696520941498875e-8 | Gx→Gx784 与 F5→Gx784 八项场差最大 0.06420% 与 0.06420%；11 个冻结显著模式复振幅差最大 0.00803% 与 0.00815%；四类功率绝对差均 <1e-3。全 workflow monotonic 3431.623 s，任务进程树 RSS 峰 7,782,744,064 B、swap 0 B，watchdog 3431.201 s | 离散求解/恢复一致性通过但 AUTHORITY_LIMITED（无同离散 direct reference）；配对比较 tested_x_agreement_pass；不构成 continuum/y 收敛或原尺寸资格 |

R/T 是端口模式功率比，A_balance 是功率平衡吸收，A_volume 是材料体积分吸收。Gx784 的 R00_s/R00_p/R00_total 为 0.07612609133082268 / 1.819475255892784e-21 / 0.07612609133082268。两场配对的场误差分母固定为 F5 同一物理量 L2 范数；显著模式复振幅按各配对首场归一。比较在共同物理坐标子单元上进行，checker 从原始字段独立重算并与保存结果完全一致。

| 时间/预算 | 已结算值 | 口径 |
|---|---:|---|
| Gx784 workflow monotonic / conservative-realtime interval | 3431.622642 / 3812.914413 s | 两种时钟分列；后者受 UTC 偏差影响 |
| Q4 shared-ledger debit | 3812.953841 s | conservative-realtime 收费，不称为 monotonic |
| postprocess attempt2 watchdog / ledger debit | 1442.152566 / 1601.004417 s | 离线保存场比较，不包含 PDE |
| 账本总 used / remaining | 5428.582334 / 167371.417666 s | 总预算 172,800 s；active reservation 为空；含旧扣费、policy debit 与 10 s allowance |
| Gx784 进程树 RSS/swap | 7,782,744,064 / 0 B | 13,507 个采样，身份覆盖完整，后代清空；PSS disabled；全局 swap delta 不归属单个任务 |
| postprocess 进程树 RSS/swap | 946,765,824 / 0 B | 5,680 个采样，身份覆盖完整，后代清空；PSS disabled |

首次保存场 preflight 的分类错配错误和后续两项最小源码修复均保留；首次失败没有进入比较 worker、预算预留或 PDE/factorization，时钟缺样所以 elapsed 为 unknown、未收费。original/repair AUTO 清单身份相同：SHA256 52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d，32,060 个有序 key，digest 03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec；V6 各读取一次，未运行生成器。已有单个 H 对角/稠密矩阵 512,960 / 16,445,497,600 B、p6 单元张量/内部 LU 形状 12,446,784 / 3,240,000 B、trace Schur/单份耦合项 2,985,984 / 3,110,400 B；272×4×14 候选为 15,232 cells、p6 full/interior 10,228,620 / 6,854,400 行，74 个 outer vectors 3,701,577,088 B、retained/full scratch 4,428,003,200 B。这些是 derived 载荷/计数，不是实测峰值。目标尺寸生命周期仍缺冷 JIT、C/D、H/Hhat 同存、恢复/投影缓存与数量、全部 q 因子填充和 workspace、完整迭代与输出时间等实测；不同阶段不能简单相加为同时峰值。原尺寸仍 NO-GO，2 TB 容量未证明；dot、workstation 与 master 状态不变。

详细边界、checker 数值、失败保留和证据链接见 [Response V6](../response_v6.md) 与 [V6 compact closeout record](records/review_v6_gx784_postprocess_closeout_v1.json)。V5/V4 与更早负结果继续保留如下。





---


## Review V5：Gx784 工程失败与后处理安全预检

Gx784 worker 在数值预检和有限元工作前因 enforce-time/旧 observe-only 合同冲突退出，官方场、真残差和 R/T/A 均未生成；这属于工程失败，不是数值失败。修复后的 V5 后处理先重算 solver/recovery Gate，当前旧记录未过 Gate，因此生成 held 对照并停止在 worker、预算预留与 FE 导入之前。唯一 bug replay 已使用，不据此启动第二次正式运行。

| 结论项 | 当前证据 |
|---|---|
| worker 与 Gate | WORKER_FAILED_PRE_NUMERICAL_ENGINEERING_ERROR_NO_OFFICIAL_RESULT；field/residual evidence unavailable，paired field/mode/power HELD / NOT_RUN |
| 记账 | 172800 s 上限；工程保守预算扣时 4.619253995631944 s；active attempt=null；bug replay=1；不是数值求解耗时 |
| 修复与验证 | source 969b4086320b844d44fb0b67092ffe5af2d760b1；47 项相关测试通过；另有文档合同检查见 test summary |
| 边界 | original 与 repair AUTO 清单/ledger 均已存在；本次 closeout 未重生成，旧生成成本 unknown；候选容量仍 unknown；dot HELD / NOT_RUN；master 未合并 |

Held 对照、独立 checker、账本、双份 target/resource ledger hashes 及分项 known/unknown 见 [Response V5](../response_v5.md)、[紧凑 V5 closeout record](records/review_v5_execution_closeout_v1.json) 与 [run index](records/run_index.json)。32,060 通道的大清单保留在 ignored artifact；tracked 记录仅保留路径、SHA、计数和 unknown 容量结论。

---

## Review V4：交叉网格与四角离线结果

本节追加 V4 实际执行结果；后面的 V2、R5 和更早阶段记录保留原样。G00=F3、G10=Gx560、G01=Gz528、G11=F5。p6 是求解实际电磁场的高阶离散；同网格准确 p4 校正用于迭代中近似修正 p6 误差，收益是保留完整 p6 解和输出，代价是还要组装/使用 p4 全局矩阵。四角均使用同一 0.7 nm 物理模型、M=8/N=2 的 340 个有序端口模式和 MPI1/threads1。因为原 F3→F5 同时改变 x 与 z，Gx 只把 x 节点改为 10×4×14、Gz 只把 z 节点改为 6×4×22，以隔离方向影响；y、材料和边界不变。

| 角点 | 网格轴单元 | cells | p6 完整行数 | p4 界面矩阵 rows / NNZ | full A6 真残差 | KSP 秒 | 同时进程树 RSS 峰值 B / swap B | 结果 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| G00 / F3 | 6×4×14 | 336 | 229,680 | 29,332 / 11,293,034 | 7.5936104e-7 | 823.922 | 4,006,539,264 / 0 | official，残差门通过 |
| G10 / Gx560 | 10×4×14 | 560 | 380,040 | 48,660 / 18,782,900 | 9.7334769e-7 | 1,499.305 | 5,255,675,904 / 0 | official，残差门通过 |
| G01 / Gz528 | 6×4×22 | 528 | 359,904 | 45,460 / 17,879,806 | 9.7452954e-7 | 1,522.376 | 5,434,322,944 / 0 | official，残差门通过 |
| G11 / F5 | 10×4×22 | 880 | 595,512 | 75,540 / 29,765,186 | 8.7353225e-7 | 1,797.975 | 7,754,170,368 / 0 | official，残差门通过 |

这里的残差是完整 p6 原系统 `||A6 x-b6||₂/||b6||₂`，限值 1e-6；RSS 是一次运行同时存活进程树峰值，swap 为任务进程树峰值。PSS 未采样。p4 矩阵 NNZ 使用 owned-row `getRow` stored-entry 口径；它不是 p6 外层自由度，也不能直接代表分解填充。

Gx560 与 Gz528 的正式运行另有各自独立的 shared workflow ledger。Gx 的 settled conservative-realtime debit 为 2,141.819255361028 s（2 次尝试：早期 parent 故障 0.024069007951766253 s，正式运行 2,141.795186353076 s；unique bug replay=1）；Gz 为 2,129.84311068633 s（1 次尝试，bug replay=0）。两个 ledger 的 `active_attempt` 均为 `null`。这些数是账本的 conservative-realtime debit，不是纯 monotonic 全流程时长；`run_summary` 的 full-workflow monotonic 值分别为 1,925.862865802017 s 和 1,917.8436222969322 s，KSP-only 分别为 1,499.305480348 s（171 步）和 1,522.375745824 s（202 步）。watchdog elapsed 字段是更窄的进程监控区间。没有精确 setup 分项，故不从总时长相减推算。逐 run 路径及 ledger SHA 见 [run_index](records/run_index.json)，原始 ledger 保持独立文件。

| 角点 | R_total | T_total | A_balance | A_volume | R00_s / R00_p / R00_total |
|---|---:|---:|---:|---:|---:|
| G00 / F3 | 0.075651901996 | 0.906206870522 | 0.018141227482 | 0.018141268088 | 0.075651427914 / 7.2332e-17 / 0.075651427914 |
| G10 / Gx560 | 0.076124070594 | 0.905769197829 | 0.018106731577 | 0.018106711773 | 0.076123597014 / 1.2442e-16 / 0.076123597014 |
| G01 / Gz528 | 0.075651879550 | 0.906206808259 | 0.018141312192 | 0.018141266669 | 0.075651405471 / 4.0495e-20 / 0.075651405471 |
| G11 / F5 | 0.076124071271 | 0.905769239817 | 0.018106688912 | 0.018106713068 | 0.076123597691 / 3.5618e-17 / 0.076123597691 |

相对 F5 的 `|ΔR|/|ΔT|/|ΔA_balance|/|ΔA_volume|` 分别为：G00 `4.72169e-4/4.37631e-4/3.45386e-5/3.45550e-5`；G10 `6.77011e-10/4.19879e-8/4.26649e-8/1.29529e-9`；G01 `4.72192e-4/4.37568e-4/3.46233e-5/3.45536e-5`。每项均小于 1e-3。四角分别检查 `|R_total+T_total+A_volume_total-1|` 和 `|A_balance-A_volume|`；两项均小于 1e-5，实际最大约 4.56e-8。功率门通过不替代复场门。

| 物理域量；误差分母固定为 G1/F5 同量 L2 范数 | x 方向：G10→G11 | z 方向：G01→G11 | x/z 交互量 `(G11-G10-G01+G00)`，相对 G1 |
|---|---:|---:|---:|
| Fresnel 背景下的散射 E | 1.375971e-6 | 2.6118624e-2 | 1.05444e-6 |
| curl(E_scattered)/k0 | 8.788076e-7 | 2.7503537e-2 | 3.93253e-6 |
| top `(0,0,s)` 复模态振幅 | 3.234128e-7 | 1.5507592e-2 | 见全 340 模式记录 |
| 总 E | 1.976082e-7 | 3.7509897e-3 | 见四角记录 |
| 总 H | 1.262070e-7 | 3.9498291e-3 | 见四角记录 |

这里 `curl(E_scattered)/k0` 的计算是先从保存的总电场直接计算 curl，扣除 `layered_fresnel` 背景的解析 curl 得到 `curl(E_scattered)`，再除以 `k0`。散射 E 与该 scaled-curl 的预登记方向假设均得到支持：x-only 细化接近 F5，z-only 细化仍接近 F3。完整物理域场表还包括总/散射 E、H、原始 curl、scaled curl、x/z 增量和交互项；逐材料区数据保存在 volume artifact。该比较只跨 x、z 两轴，不能推出 y 或 continuum convergence。

| 冻结 11 个显著模式的最大复振幅差；各 comparison 按其首角幅度归一化 | 最大值 | 1% 门 |
|---|---:|---|
| G00→G11 | 1.555605% | 失败 |
| x increment G00→G10 | 1.555637% | 失败 |
| z increment G00→G01 | 0.010781% | 通过 |
| G10→G11 | 0.010866% | 通过 |
| G01→G11 | 1.555591% | 失败 |

因此“x 比 z 更接近 G1”的三项主要预登记观测均成立，但 F3→F5 与 Gz→F5 的整体显著模式门仍失败；不能把 overall 1% 模式 Gate 写成通过。旧失败通道也完整保留：`bottom(-1,0,s)` 的 F3→F5 首幅值归一化差为 1.274430%，`top(0,0,s)` 为 1.555605%；Gx→F5 分别为 2.34773e-5 和 3.23413e-7，Gz→F5 分别为 1.260666% 和 1.550759%。各角复振幅、全部 340 行和五种比较均见 mode artifact。

| 检查 / 证据身份 | 结果与边界 |
|---|---|
| 公共体积 | 1,344 子单元（形状 12×4×28），每轴 7 阶求积；物理体积 24.3966874968 nm³，材料标签错配 0 |
| 轴并集 | x/y/z 节点数 13/5/29；仅合并完全相同节点，完整有序节点列在接口包 |
| 模式清单 | 340 ordered modes，80 propagating、210 power-carrying；`power_carrying` 表示有限端口单位振幅的实能流 `mode.power_per_unit_amplitude > 0`，并非传播通道数；四角 manifest digest 相同；保留全部 340 对照行及冻结 11 键 |
| volume 离线分析资源 | 864.838 s；同时进程树 RSS 934,637,568 B、swap 0 B、PSS 未采样；subreaper leader exit 0 且后代清空 |
| 模式离线分析 | 读取已校验保存包；没有场恢复、PDE、矩阵装配或因子化；未单独采样同时进程树资源 |
| 紧凑接口包 | [`review_v4_four_corner_interface_v1.json`](records/review_v4_four_corner_interface_v1.json)，SHA256 `44a878f85c6e50f5aa5c6b53f58addf1350041c33593cf72ea8cb6b961f29e43`；物理参数、精确网格节点、参考面、相位、unknown/recovery、残差、全部物理域字段指标、模式键、功率和资源边界均在其中 |
| 原始离线结果 | [volume artifact](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/four_corner_volume_v1.json)，SHA256 `5f8004f51cb7d9543730281ace16f296cdc47b0358c66038302bf4f39ac40c17`；[mode artifact](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/four_corner_modes_v1.json)，SHA256 `e723cf5fd6dc761e3642582af12b921c05453c581903eaf47abac07816d17df2` |
| 求解/输入来源 | G00 source `a43f7f76a0df0f4440b77834846973b2de7ea3a8`；G10/G01 `9fd295624444cf16b6ba393a0a7c3522f0070f73`；G11 `63dd2a7378153f2ab5094eb5e7a98d05758a39bf`；run/input/physical hashes 在接口包和 [run_index](records/run_index.json) |
| F3 源码索引修正 | `run_index.runs` 中旧 F3 SHA `63dd2a...` 更正为 run manifest 实证的 `a43f7f...`；旧值和修正依据保留在同一 F3 项的 `source_sha_correction`，未变更求解输出 |
| V3-A / V3-B / V4 范围 | 复用已接受的 paired-background attribution，不重算 A；完成预登记 Gx560、Gz528 与四角比较；没有新网格、背景扫描、相位拟合或删除模式 |
| dot / 原尺寸 / 工作站 | dot 仍 `HELD / NOT_RUN`，旧 checker `UNKNOWN`；没有改 dot 或 workstation，没有原尺寸计算，不建立 workstation readiness 或 continuum claim |

## V4 选择性合并分组与下一步

| 依赖组 | 数值行为与依赖 | 测试 / fresh evidence | 决策与顺序 |
|---|---|---|---|
| production numerical/core | 本轮新增 Gx/Gz 输入参数与 `src/geometry/task40_nonseparable_plan.py` 交叉几何/预算登记；`src/io/physical_intermediate_profile.py` 和 `src/runners/task038_launcher.py` 有 parent-FE import/launcher 最小修复；`src/postprocessing/diffraction_3d.py` 是输出后处理调整；另新增 `src/postprocessing/task40_saved_field_h_comparison.py`，恢复已保存场、直接求 curl 并在公共子单元上做离线比较。以上改变研究配置、入口和后处理；生产 Maxwell 方程、有限元离散、矩阵/约束数学及普通 solver default 未变，离线算法明确登记在 `src/` 中 | 四角 official PDE 的 solver source 与原残差/R/T/A 绑定 run_index；新增 comparator 只分析已保存场，不触发 PDE | 新增代码仍属 Task40 研究与离线分析支撑；不作为 production default，未来拆分复用前另行 review |
| reusable runner/watchdog | `benchmarks/postprocess_task40_review_v4_directional_cross.py`、`benchmarks/postprocess_task40_review_v4_modes.py` 与 `src/postprocessing/task40_saved_field_h_comparison.py`；仅读已保存场/模式，依赖既有 `subreaper_watchdog`，不改 watchdog | 三个目标测试文件共 8 passed；V4 volume/mode artifacts 各自绑定 source/artifact SHA；runner 不触发 PDE | 保持 Task40 research/evidence 工具，先经审阅；没有宣称替代通用 runner或可设为默认 |
| checker/benchmark | 本轮无新的独立 checker 或 benchmark case/schema | targeted tests 校验方向量和冻结模式规则；不是 solver checker qualification | 无 checker/benchmark 文件待迁移 |
| compact evidence/docs | `response_v4.md`、V4 summary/test-summary 段、interface JSON、run_index source correction 与新增 Gx/Gz identities | 4 个 JSON 可解析，hash 与索引一致；保留全部 positive/negative/not_run 边界 | 审阅后按文档依赖组迁移；完整历史 records 不改写 |
| research-only | Gx/Gz 输入参数、Task40 交叉几何/预算登记与 launcher/parent import 最小路径修复、`src/postprocessing/task40_saved_field_h_comparison.py` 离线算法、两个 task-scoped postprocessor、M2 crossed-grid 解释与四角数据；无 continuum/y/目标尺寸证据 | 两项离线 artifact；F3/F5 与 Gz/F5 的显著模式 1% Gate 仍失败 | 这些实现只支持本轮研究入口和保存场离线分析；不升 production、不改 ordinary default；方向结果只作后续实验优先级依据 |
| do-not-merge | dot 分支源码、workstation 操作、原尺寸/Phase II solver、任何未经 Review 的 master 变更 | dot `HELD / NOT_RUN`、旧 checker `UNKNOWN`，无新环境 fixture | 本轮无授权或证据，不迁移、不合并 master |

本批结论限定为 Review V4 指定的小尺寸离散模型与已保存场的四角对比。功率一致和 residual 通过说明这四场具有可审查的求解与能量证据；模式/散射场 Gate 的负结果仍然有效。由方向对照可将后续网格投入优先放在 x，但不得把当前证据外推为最终工程精度或原尺寸可运行。


## 一级账：模型结果与campaign状态

| 模型/阶段 | 正式身份 | full A6 residual / Gate | 官方量与比较 | workflow / KSP；同时树RSS / swap | p4 factor rows / NNZ / INFOG29 | 结论 |
|---|---|---:|---|---|---|---|
| F1 G1 M0 | `task40extra_0p7nm_nonseparable_g1_reference_metric_f1_v1`；880 cells；M80 | 8.648911990579289e-7；同离散G1 M0参考通过 | R/T=`0.07612407122165808/0.9057692393459813`；A_volume=`0.018106713007727038` | 2252.535 / 1674.835 s；6,891,311,104 B / 0 B | 75,280 / 28,705,330 / 182,769,024 | 仅资格化G1 M0；不能代替G0 M2 reference |
| F2 G0 M1 | `task40extra_0p7nm_nonseparable_g0_manual_m1_f2_v1`；336 cells；M180 | 9.572475880327875e-7通过；worker exit4 | raw/offline R/T/A_volume=`0.07565188084569026/0.9062068016471507/0.018141266883419625`；worker `official_result=false` | 1123.500 / 809.586 s；3,867,545,600 B / 0 B | 29,172 / 11,033,364 / 55,305,544 | 保存DtN/体积值用于P3 offline比较；未重新发布official result |
| F3 G0 M2 | `task40extra_0p7nm_nonseparable_g0_manual_m2_f3_v1`；336 cells；M340 | 7.593610432084708e-7通过 | R/T=`0.0756519019957502/0.9062068705222379`；A_volume=`0.018141268088495303` | 1174.947 / 823.922 s；4,006,539,264 B / 0 B | 29,332 / 11,293,034 / 56,763,048 | 离散与一致性通过，authority-limited |
| F5 G1 M2 | `task40extra_0p7nm_nonseparable_g1_manual_m2_f5_v1`；880 cells；M340 | 8.735322490524255e-7通过 | R/T=`0.07612407127067708/0.9057692398169153`；A_volume=`0.018106713068250728` | 2448.071 / 1797.975 s；7,754,170,368 B / 0 B | 75,540 / 29,765,186 / 186,881,032 | 离散与一致性通过；M2跨网格场/curl工程门未通过 |
| E1 q=1.25 | `task40extra_0p7nm_nonseparable_e1_manual_m2_growth_v1`；760 cells；M588 | 9.781668525522113e-7通过 | R/T=`0.06235653736791684/0.9159264755357902`；A_volume=`0.021716951725654188` | 4580.375 / 3722.193 s；10,650,341,376 B / 0 B | 65,708 / 26,681,978 / 164,865,416 | 固定波长的电尺寸增长诊断，不是h收敛序列 |
| E2 q=1.5原run | `task40extra_0p7nm_nonseparable_e2_manual_m2_growth_v1`；880 cells；M700 | 9.793073227317083e-7通过；worker exit4，official false | 原worker无official output；v3保存场恢复R/T=`0.05116886160983426/0.9239410512847893`，A_volume=`0.02489005360260621` | 7692.028 / 6776.587 s；11,349,196,800 B / 0 B | 75,900 / 31,287,060 / 182,925,800 | 原失败保留；v3只做离线输出恢复 |
| P1 G0/G1 M0体积/curl | 原G0/G1 M0保存场；1344共同子单元 | 不是新solve | 总场E/H=`0.3750%/0.3949%`通过；散射E=`2.6113%`、散射H/scaled-curl=`2.7498%`失败；官方ΔR/ΔT/ΔA_volume均过0.001 | offline 436.518 s；self RSS 620,851,200 B；无PDE/operator/factor/KSP | 不适用 | P1真实负结果；SHA-bound record在`records/p1_m0_volume_h_agreement_v2.json` |
| P4 F3/F5 M2体积/curl | 共同340个M2 key；G0/G1保存场 | 不是新solve | 总场E/H约`0.3751%/0.3950%`通过；散射E=`2.6119%`、散射H/scaled-curl=`2.7504%`失败；official ΔR/ΔT/ΔA_volume=`0.0004721693/0.0004376307/0.0000345550`通过 | offline 597.979 s；RSS 621,101,056 B；无PDE/operator/factor/KSP | 不适用 | M2场/curl h工程门失败，不能由功率接近覆盖 |

### 零级反射与p6空间维数

| 模型/身份 | R00_s | R00_p | R00_total | 来源/状态 |
|---|---:|---:|---:|---|
| F1 G1 M0 | 0.07612359764215308 | 3.4597741445267834e-17 | 0.07612359764215311 | 正式DtN；F1同离散reference |
| F2 G0 M1 | 0.07565140676565715 | 2.0048467438900223e-17 | 0.07565140676565717 | raw DtN/offline用于P3；worker official_result=false |
| F3 G0 M2 | 0.07565142791421035 | 7.233241618502243e-17 | 0.07565142791421042 | 正式DtN |
| F5 G1 M2 | 0.076123597691134 | 3.5617837904198074e-17 | 0.07612359769113404 | 正式DtN |
| E1 q1.25 | 0.062356105023958414 | 6.083759436e-16 | 0.062356105023959024 | 正式DtN |
| E2 q1.5 v3 output recovery | 0.05116727309447169 | 7.978116094818559e-19 | 0.05116727309447169 | saved-field recovery only；原worker仍失败 |

F1/F3/F2的G0类p6空间为full229,680、active68,256、interior151,200、trace78,480；F1/F5的G1 p6空间为full595,512、active177,120、interior396,000、trace199,512。E1为full514,710、active153,360、interior342,000、trace172,710；E2为full595,512、active177,120、interior396,000、trace199,512。完整有序模式与各显著衍射级见run_index绑定的`dtn_port_diffraction_orders_3d.json`及hash，不把诊断Fourier值混入官方DtN结果。

workflow、独立watchdog、KSP、p6 build和postprocess是不同边界，不相加。E2的KSP事实为已保存阶段记录；其原postprocess独立边界unknown。PSS为null。F1 p4完整存储行是180,240，而实际凝聚factor只有75,280。目录timestamp不是run_id。完整source/input/physical/native ordered-mode SHA及raw字段路径+SHA见`records/run_index.json`、`records/electrical_size_v2.json`和`records/resource_components_v2.json`。F3源码SHA=a43f7f76a0df0f4440b77834846973b2de7ea3a8；F5/E1/E2=63dd2a7378153f2ab5094eb5e7a98d05758a39bf。

## 二级账：资源组成

| 组件 | 证据 | 解释与限制 |
|---|---|---|
| mesh/MPC | G0 336 cells；p6全空间229,680 DOF；单元维数882 | P6构造真实mesh/space，没有构造全局物理operator |
| p6局部LU/Schur/恢复 | 三种tag各取一个单元；内部450×450，trace432×432；非零RHS closure为1.43e-11至2.35e-11 | 真实局部闭合通过1e-10；不代表全域因子容量 |
| p4矩阵/MUMPS | F1 full storage180,240、factor75,280/28,705,330 NNZ；F2 full storage69,856、factor29,172/11,033,364；F3 29,332/11,293,034；F5 75,540/29,765,186；E1 65,708/26,681,978；E2 75,900/31,287,060 | INFOG29依次182,769,024、55,305,544、56,763,048、186,881,032、164,865,416、182,925,800；INFOG16/17是symbolic估计最大/和，18/19是allocated最大/和，22是used进程和，均以decimal MB报告；INFOG29是条目数。matrix payload、ICNTL23受限工作内存限额记录与process-tree RSS另列；全局因子仍是目标尺寸风险 |
| ports/Krylov P6压力 | M=80/340/3904，batch=16；M3904每真实tag双遍约3.739–3.773 s | synthetic/resampled压力，不是完整高M物理端口模型；无M×M矩阵 |
| 同时进程树RSS | F3 4.007 GB；F5 7.754 GB；E1 10.650 GB；E2 11.349 GB | watchdog同时树峰值 |
| inventory/workspace | F3 4.894/1.753 GB；F5 7.876/1.992 GB；E1 10.429/6.031 GB；E2 11.544/6.092 GB | 两者分别是对象账与workspace，不等于RSS，也不相加 |
| JIT/postprocess | P6 form compile=0.00724 s；F3/F5/E1 post=7.176/19.152/19.712 s | E2原post边界unknown；E2 v3离线恢复单列 |

P6知道的numpy backing下界38,432,904 B，显式数组情景上界40,542,856 B；后者不含不透明BLAS/LAPACK工作区。P6自身RUSAGE RSS峰455,610,368 B，task swap未独立采样，不能把两次VmSwap=0监控快照写成峰值零。本轮没有从小模型或对象账外推2 TB容量，也没有调整工作站cap。

## 误差、负结果和下一步

- P1是原G0/G1 M0公共子单元体积/curl比较：总场E/H为0.3750%/0.3949%（过1%），散射E=2.6113%、散射H与scaled-curl=2.7498%（未过1%）；official ΔR/ΔT/ΔA_volume均低于0.001。记录SHA `9d72efd7f21771c7fd0cc779b7cfb0f9272734fe9cbe1757a014d127e4422925`。这不同于R5旧固定坐标样本`h_agreement_v1.json`的`H_AGREEMENT_PASS_ENGINEERING_ONLY`。
- P3显著规则M0 power_ratio≥1e-8是在查看探索性all-80差异后固定；报告保留此事后规则披露，不称预注册。按该有限规则选择M2，M3未触发。
- P4是F3/F5 G0/G1同M2的保存场比较：340 keys相同；总场E/H变化约0.3751%/0.3950%过1%；散射E=2.6119%、散射H/curl=2.7504%、显著模式1.555605%、固定样本最大2.743612%超过1%。官方ΔR=0.0004721693、ΔT=0.0004376307、ΔA_volume=0.0000345550通过0.001。负结果是场/导数误差门未过，不是方程没有离散解。
- E1是一次更大电尺寸诊断点；E2原worker因sample配置后处理检查失败，离线恢复保留其失败分类。
- P6支持三种真实局部块闭合和固定批次synthetic动作可行性；不证明生产端口稀疏度、完整高M或TB容量。
- P7只提出下一阶段设计。原端口块`H_p`经精确消去/trace映射后成为同维增广接口+port贡献`Ĥ_ℓ`并且只计一次；粗层选`R_ℓ=P_ℓ^H`，这不要求物理左右块`D=B^H`，也不把非Hermitian算子变成Hermitian。`ΣT_j^H W_jT_j=I`只约束近似PC patch组合。提案封顶4层、终层≤20,000维/≤200步、外层≤2,048步；见review_v2_campaign.md。
- ordinary default不变；Phase II和master merge都未进行。

## 选择性合并分组

| 依赖组 | 全V2范围 / 数值行为 | 测试与fresh evidence | 建议顺序 |
|---|---|---|---|
| production numerical/core | Task40显式profile/reference-metric候选及其`src/common`、`src/geometry`、`src/io`、`src/postprocessing`、`src/runners`、`src/solvers`改动；部分可能影响数值行为 | reference-metric、M1 authority、geometry、P1/P3/P6 targeted tests；F1只资格化G1 M0；P1/P4保留负结果 | 第一组逐依赖review；不升级ordinary default |
| reusable runner/watchdog | v29 p6 pair runner、subreaper watchdog、E2 saved-output recovery入口 | runner/watchdog/recovery targeted tests；E2 v3不是PDE/factor证据 | 第二组仅迁移经审查通用部分 |
| checker/benchmark | Task40 P1/P3/P6/P2 checker和bounded diagnostic entrypoints | P1 M0与P4 M2已保存结果；P6 fixture2、P4 helper fixture4 | 第三组与相应schema/tests同行 |
| compact evidence/docs | run index、P1/P4/P3/E1/E2/P6 records、summary、test_summary、README、response与项目登记 | JSON/doc/hash/link与diff检查 | 第四组保留到执行分支供review |
| research-only | synthetic M3904压力、Task40显式profile以及P7未实现设计 | 不构成高M完整物理模型、TB容量或Phase II qualification | 保持research-only |
| do-not-merge | e174b91历史`/dev/null`hook绕行、放宽冻结Gate、删除P1/P4 negative、把E2原worker失败改写为成功、普通默认切换 | `repair_ledger_v2.json`保留偏差 | 禁止 |

## V2证据索引

Review V2 campaign见review_v2_campaign.md；执行回应见response_v3.md。机器可读记录包括review_v2_plan.json、p1_m0_volume_h_agreement_v2.json、volume_h_agreement_v2.json、reference_metric_tensor_v2.json、channel_study_v2.json、electrical_size_v2.json、resource_components_v2.json、repair_ledger_v2.json、p6_local_block_inventory_v2.json与run_index.json。旧R5总结紧随本文之后保留，不覆盖。


---

# 历史结果摘要（V1 / R5；原文保留）

# Task40extra B 线 N0–N6 结果总结：0.7 nm 非可分三维 Maxwell

## 当前结果（R5，2026-09-30）

N0–N6 的当前阶段状态是：strict identity 修复后 G0、G1 正式离散解通过；G0 same-discrete direct comparison 通过；G0–G1 fixed-sample/power engineering agreement 通过。N2 与 attempts 1–4 仍按原范围和原分类保留。

| 正式对象 | 方法、模型规模 | Gate / official output | watchdog 资源与时间 |
|---|---|---|---|
| G0 review_v1 | 336 cells；p6 完整场 229,680 rows、active trace 68,256；p6 trace+port 68,336 rows；q4 凝聚因子 29,072 rows / 10,912,592 NNZ；80 modes；FGMRES 152步 | A6 9.798664008005796e-7；identity 1.520588963522625e-11；R/T/A_balance/A_volume=0.0756519645/0.9062068564/0.0181411791/0.0181412571 | simultaneous tree RSS 3,776,098,304 B；swap 0；workflow/KSP 1204.018/787.135 s |
| G1 review_v1 | 880 cells；p6 完整场 595,512 rows、active trace 177,120；p6 trace+port 177,200 rows；q4 凝聚因子 75,280 rows / 28,705,330 NNZ；80 modes；FGMRES 127步 | A6 9.901397191660007e-7；identity 3.2542694546811876e-11；R/T/A_balance/A_volume=0.0761240621/0.9057692206/0.0181067174/0.0181067127 | simultaneous tree RSS 6,855,741,440 B；swap 0；workflow/KSP 4097.994/3135.913 s |
| G0 direct reference | 同 G0 几何/物理；MUMPS 因子作用于 p6 trace+port 的 68,336 rows；229,680 rows 是恢复完整场的存储维数；80 appended modes | direct residual 5.055376131651821e-11；MATCHED_REFERENCE_PASS；R/T/A_balance/A_volume=0.0756519637/0.9062067814/0.0181412550/0.0181412550 | simultaneous tree RSS 11,505,573,888 B；swap 0；watchdog/charged 1647.527/1801.467 s；PSS disabled |

### 零级 s/p 通道与能量闭合

| 模型 | R00_s | R00_p | R00_total | T00_s | T00_p | T00_total | A_volume grating / substrate | R+T+A_volume−1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| G0 iterative | 0.07565149041679828 | 2.7428991838613296e-18 | 0.07565149041679828 | 0.9062066000865279 | 1.4515667553444104e-18 | 0.9062066000865279 | 0.013925879883210604 / 0.004215377168498715 | 7.799209567060927e-8 |
| G1 iterative | 0.07612358848843093 | 7.987426377936068e-16 | 0.07612358848843173 | 0.9057689645333413 | 4.2210952517070463e-16 | 0.9057689645333417 | 0.013893418210626729 / 0.0042132945191538694 | -4.630012484518886e-9 |
| G0 direct reference | 0.07565148957274329 | 2.5940427852720315e-23 | 0.07565148957274329 | 0.9062065250155358 | 3.476815891411563e-23 | 0.9062065250155358 | 0.013925878172457823 / 0.004215376818162912 | 1.6774137634456565e-11 |

各s/p数值是端口模态功率比。G0–G1变化最大的衍射通道为 top (0,0,s) 的 R 增加 0.0004720981 与 bottom (0,0,s) 的 T 减少 0.0004376359；其余被比较的80-mode功率变化小于 3.0e-10。完整排序与所有模式见 [h-agreement record](records/h_agreement_v1.json)。

正式 G0/G1 source SHA=b8a20bd24848a83f2f4fa50b1ccaaa4ec9be9672；inputs 分别为 6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e / 989a351fb27fe5320942ca2392d0e7e872909f0354509e5d59c8c25e43061c86。direct source SHA=393e5c0dddb933848945ab2e18edb73cf69cc224，direct input SHA=c80c921834cb268a9251459795fbda5acf4e9f25347d16ee24dec3b9d85c6c56。direct 规范化 physical sections SHA 与 G0 的 51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661 一致；原始 identity 差异只有 assembly backend。mode SHA=c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a。

R/T 来自 DtN 端口模态功率，A_volume 来自材料区域体积分吸收。q4 行数和 NNZ 是预条件器的独立 q4 凝聚因子规模，不是 p6 外层维数。direct reference 的完整场 residual 用保存的 b 与 Ax 独立复算，记录值完全一致；详细字段、输入/source 与 artifacts hash 见 [identity recovery compact](records/identity_recovery_v1_results.json)。

同离散比较的 FE L2 / scaled-curl 相对误差为 1.0644e-7 / 1.0590e-7；固定坐标场与界面迹最大相对差 4.9591e-7；80-mode outgoing amplitude 向量整体相对差 1.3374e-7；每模功率最大绝对差 7.5071e-8；R/T/A/A_volume 最大总量差 7.5915e-8。所有 applicable Gate 通过。

G0 到 G1 的共同坐标总场变化约 0.374%（E）与 0.393%（H），总功率各绝对差低于 0.000473，过本任务 1% / 0.001 工程 Gate。这仅表示两张网格在固定样本和当前输出上相符，不是连续极限证明；80-mode channel cutoff 仍未资格化。约 2 TB 目标容量仍 UNKNOWN。

| 其他阶段成本 | 实测 / 近似时间 | 解释 |
|---|---:|---|
| R1 full p6 operator diagnosis | 14,039.107309384039 s | 没有全局 p4 factor；诊断阶段 |
| v1 builder 主动停止 | 约101 s | 近似；审查修正后停止，原分类保留 |
| v2 exact-geometry replay | 198.79226663301233 s | 保存向量的离线复核，无 fresh PDE/KSP |
| attempt1–4 shared ledger累计 | 530.8867869906425 s | 历史 ledger scope，与后续 review_v1 分开 |

### Setup、求解和后处理时间

| 模型 | setup | outer adapter | KSP-only | final native / release checks | official postprocess | 主内存对象记录 |
|---|---:|---:|---:|---:|---:|---|
| G0 | 373.096 s | 798.552 s | 787.135 s | 2.045 / 8.730 s | 11.707 s | worker inventory peak 4,429,493,610 B；workspace peak 1,731,541,832 B；Krylov workspace upper 80,909,824 B；同时树RSS峰 3,776,098,304 B |
| G1 | 908.009 s | 3150.090 s | 3135.913 s | 4.890 / 15.448 s | 14.035 s | worker inventory peak 6,627,841,642 B；workspace peak 1,970,721,416 B；Krylov workspace upper 209,804,800 B；同时树RSS峰 6,855,741,440 B |
| G0 direct | setup/factor阶段无可独立确认的 wall-time 切分 | 不适用 | 不适用 | recovery 0.632 s；其余检查独立阶段时间 unknown | 包含在总 charged 时间内，未独立计时 | PETSc 输入矩阵 MatInfo nz_allocated/nz_used=56,834,000/55,984,880 项；MUMPS INFOG16/17=7,932/7,932 decimal MB、INFOG18/19=8,277/8,277 decimal MB、INFOG22=6,798 decimal MB、INFOG29=346,831,808因子项；同时树RSS峰 11,505,573,888 B，峰值worker stage fine_reference_residual_completed |

outer adapter 已包含 KSP-only；这些时长不能相加当作独立阶段总耗时。direct 计时只报告 watchdog elapsed 1647.527 s 与 launch charged 1801.467 s，不从二者差值分配 symbolic、numeric 或 solve 阶段耗时。NNZ 是矩阵非零项数，不是字节；7,932 MB 是准入估计，不是 RSS 峰值。

direct reference 启动时未使用要求的 user-service wrapper，观察到 cgroup /init.scope。发现偏差后未重启或迁移这唯一运行；独立 subreaper watchdog 完成了后代身份跟踪与清场。该流程偏差在 [execution-context 记录](records/r5_execution_context.json) 中单独保留。

下轮唯一建议候选是任务书 §8.1 的有界局部问题加多层全局波动纠错，重点是新传播/接口/粗空间机制与有界总因子预算；不是重做旧 42 宏块 complete-PC。需在下一 review 冻结机制和准确 p4 对照顺序后再决定是否实施。R5 未执行 Phase II；没有新增 PDE。

## 先前 N6 快照（review_v1 正式运行前）

以下 N0–N6 表和 attempt4 指标是 R4 运行前的历史快照。其当时将 G0/G1/direct 标为未运行，不能解释为当前状态；attempt4 的失败数值与分类仍有效并完整保留。

## attempt4 当时的 N6 状态

G0 attempt4 已真实建立 p6/q4 空间并进入外层迭代。 这里的恢复/native identity 检查，是把凝聚后求出的未知量恢复成完整场后，核对它代回原始方程的作用是否与凝聚代数一致。第 8 步，原 A6 相对真残差为 0.16667295750232392（要求 ≤1e-6），native recovery identity 为 3.0748104980683956e-10（要求 ≤1e-10）。worker 原始 summary 分类为 V20_RELEASE_GATE_FAIL。根据每 8 步检查的源码规则，这是恢复/native identity Gate 停止；raw KSP status/reason 未保存，因此具体 callback/reason 属于源码推导。它不是资源停止，也不是 max_it=2048 后仍未收敛的结论。

| 阶段 | 状态 | 证据边界 |
|---|---|---|
| N0 | complete | B线执行分支和 canonical worktree 已绑定 |
| N1 | complete | 0.7 nm 材料、有限三维缺口、G0/G1 计划、80-mode 清单已冻结 |
| N2 | diagnostic_pass_only | 60-cell p2 tiny 残差 1.772707454694957e-12；不是 G0/G1 p6 |
| N3 / G0 | V20_RELEASE_GATE_FAIL | 前三次实现异常保留；attempt4 进入8步 outer solve 后停止于 identity Gate |
| N4 / G1 | NOT_RUN | 没有 h-refinement 或跨网格比较 |
| N5 / G0 direct | NOT_RUN | 没有合格 iterative subject，direct reference 未运行 |
| N6 | closed_limited | 保存受限数值结果、成本和边界；没有精度/容量资格通过 |

p6 高阶有限元用较高次多项式表示复杂电磁场；路线先处理每个单元内部未知量以缩小全局问题，再用 q4/p4 操作纠正解。这样能减少外层未知量，但必须检查恢复后的全场是否仍满足原始 A6 方程和恢复恒等式。小型 p2 诊断、mesh audit 与投影检查仅验证各自环节，不能替代 p6 release Gate。

## attempt4 历史模型与结果

| 项目 | attempt4 实测 | 解释 |
|---|---:|---|
| 输入 SHA256 | 8e00fb6495845902a8113d982242d39ad0f4999b563c2c8049ecc3750b82ac9c | 冻结 G0 p6/q4 输入 |
| source SHA | de44f5bb4da48cd076df2b295ef6fe08b83d52fa | 实际运行源码身份 |
| physical model SHA256 | 51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661 | runner物理模型身份 |
| G0 mesh / spaces | 336 cells；p6 229,680 rows；q4 69,856 rows；80 modes | 几何 audit 和 native AQ projection setup checks 通过 |
| solver | FGMRES，restart=32，max_it=2048；实际8步 | numerical Gate 提前停止，不是迭代上限 |
| official result | false | diagnostic field/error packet 保存；official R/T/A、A_volume 和能量闭合未生成 |

第 8 步 native identity 公式为 e_FE - B*H_p^-1*e_p。主控对已保存数组离线复核，difference 向量等于 native residual 减 derived native residual；范数 1.0129916171163611e-9 除以 operation scale 3.29448470971699 得 3.0748104980683956e-10。超过门槛约 3.07 倍。本记录不把它先验称作 roundoff，也不能由单次 Gate 单独确定其更深根因。

| 指标 | 实测 | 限值 | 状态 |
|---|---:|---:|---|
| 原 A6 full explicit true residual | 0.16667295750232392 | ≤1e-6 | 未通过 |
| native identity relative | 3.0748104980683956e-10 | ≤1e-10 | 未通过 |
| internal residual relative | 6.4490341352469694e-18 | ≤1e-10 | 通过 |
| port closure relative | 1.4794093427202804e-15 | ≤1e-8 | 通过 |
| Schur-port identity relative | 1.3094474052481446e-29 | ≤1e-10 | 通过 |
| final release packet A6 relative | 0.16667295750232333 | ≤1e-6 | 下游释放检查仍未通过 |

源码在 iteration 8 snapshot 中先检查物理残差，再检查 recovery/native/Schur identity。按保存数值可推导 callback 将其记为 RECOVERY_IDENTITY_GATE_FAIL，并返回 DIVERGED_BREAKDOWN；这两个字段均不是 raw KSP 记录。release packet 原生记录 V20_RELEASE_GATE_FAIL。外层 launcher 另外记 exit 4 / WORKER_FAILED；该 wrapper 状态不表示资源停机。完整证明、源码路径和 artifacts hash 见 [attempt4 compact record](records/g0_attempt4_identity_gate_stop.json)。

## 三次实现错误与第四次 Gate

| 运行 | 结果 | 含义 |
|---|---|---|
| attempt1 | parent ledger batch identity 不一致；3.896 s | 数值工作未开始，implementation bug |
| attempt2 | same-mesh wrapper 缺 rectangular_air_void_audit；87.897 s | 实际建成336-cell mesh并通过 native projection 检查，随后 cleanup 实现失败；未进入 outer KSP |
| attempt3 | 新 worktree 缺 Task39 相对 JIT cache 源路径 | FileNotFoundError；单次耗时未独立持久化，implementation bug |
| attempt4 | V20_RELEASE_GATE_FAIL | 进入真实迭代后因恢复/native identity Gate 受控停步；不是前三次 bug 的重分类 |

attempt3 的独立 elapsed 和必要人工修复工时都是 unknown，不能由共享 ledger 的时间差倒推。全部四次 worker、source、artifact SHA 与 ledger 在 [run index](records/run_index.json)。

## Setup、KSP 与资源成本

| 统计 | 值 | 口径 |
|---|---:|---|
| p6 / p4 condensation cold JIT | 58.575 / 18.047 s | 各自compiler event |
| compiler events | 11 | 包含多角色及缓存命中/未命中；不是单一setup时长 |
| qualified JIT hardlinks | 104 files / 1,400,533,851 B | 缓存文件字节，不是驻留内存 |
| p6 build audit | 15.216 s | 原记录 build timer |
| x1 setup-check | 22.907 s | setup-check timer，不表示完整全流程装配 |
| retained outer clock through terminal snapshot | 54.222 s | 保存的 outer elapsed；KSP-only elapsed 未持久化 |
| outer iterations | 8 matvec / 8 PC apply | KSP外层动作计数 |
| setup-inclusive inventory | bridge 13 / p4 26；terminal native 6 / Schur 11 / Hp solve 44 | 原字段各有范围，不能折算成8次outer PC |
| launcher workflow monotonic | 356.929 s | monotonic时间 |
| conservative realtime workflow | 392.257 s | 与monotonic差35.330 s |
| shared ledger | 本次 debit 392.262 s；累计 530.887 s | 账本口径，不是KSP-only时间 |
| process-tree RSS peak | 2,954,866,688 B | watchdog sampled simultaneous process-tree peak |
| swap / PSS | 0 B / disabled | 没有资源 Gate stop；PSS按profile禁用 |
| process cleanup | descendants cleared；identity coverage complete | watchdog 1,397 samples |

共享 ledger、conservative realtime 与 monotonic 是不同观测范围，不相减推造 KSP 或工程工时。cgroup memory peak 未在本次 compact run 记录中报告；不补值。

## attempt4 当时的精度、网格与容量边界

| 问题 | 当前结论 |
|---|---|
| official R/T/A、A_volume、energy closure | NOT_RUN；A6及identity release Gate 未通过 |
| G0–G1 h agreement | NOT_RUN；G1 未运行 |
| G0 same-discrete direct authority | NOT_RUN；direct preflight/factor/solve 未运行 |
| 80-mode channel truncation | CHANNEL_TRUNCATION_UNQUALIFIED |
| 2 TB target feasibility | unknown；一次 G0 RSS 不能外推目标规模 |
| 主导容量对象 | unknown；缺少通过 accuracy Gate 后的容量闭环 |
| Phase II PC | none selected；本批没有候选获得精度/有效性资格 |

没有 best-available discrete reference，也没有工程网格或连续极限结论。N2 tiny 诊断结果不作为 G0 的替代。N6 收口保存失败值和缺失值，不再运行 G1、direct 或其他 PDE。

## 选择性合并建议

| 依赖组 | 代表内容 | 当前建议 |
|---|---|---|
| production numerical/core | Task40 config、geometry、solver/runner profile | 数值 Gate 未通过；不升级 ordinary default |
| reusable runner/watchdog | run_case、JIT staging、watchdog | 保留工作流证据；不是 solver pass |
| checker/benchmark | N1 inventory、geometry fixtures、N2 diagnostic | 只支持各自范围 |
| compact evidence/docs | attempt4 record、run index、summary、response、测试摘要、模型总账 | 可随分支审阅 |
| research-only | 显式 Task40 p6/q4 双凝聚 profile | 保持研究用途，未资格化 |
| do-not-merge | 整体分支、master、ordinary default 切换 | 等待 review/merge approval |

## 证据入口

- [attempt4 compact record](records/g0_attempt4_identity_gate_stop.json)
- [运行索引](records/run_index.json)
- [阶段状态](records/phase_I_results.json)
- [精度与容量](accuracy_and_capacity.md)
- [测试摘要](test_summary.md)
- ignored raw attempt4 artifacts 位于 run index 所列 results 路径。

## Review V7 W0 实际补充执行收口（待审，目标未实现）

本次补充执行已在时间与实现失败边界收口，等待审阅；不自动继续 W1/W2。W0 进入 p6-only setup，生成 8 门 `PASS_COMPONENT_ONLY` same-live receipt 后，worker 在 tuple/list mode identity guard 处 exit 1，未到 full p6 component worker/raw export。修复版 public validator 在 native 主机上对保存 JSON 的 list、tuple 身份形式都通过；主线仅捕获并 hash-check 了 stdout。没有 p6 科学 tensor/场数组、independent tensor/CSR checker、full A6 residual 或 official R/T/A。目标尺寸继续 **NO-GO**。

| 阶段/对象 | 结果 | 数据身份与边界 |
|---|---|---|
| W0 p6-only setup | `FE_REACHED; eight component gates PASS_COMPONENT_ONLY` | 80 cells（4×4×5），degree `{6}`、532 ordered modes、φ=5°；输入文件名中的 `q4` 配置标签未由本 probe 执行为四个 q 或因子 |
| W0 worker | `WORKER_FAILED`, exit 1 | tuple/list ordered-mode identity guard；wall `196.762108860 s` / per-worker limit `199.490712881 s`；不是 time/resource/solver failure |
| 收据 validator | native list/tuple 两次 PASS | same-live JSON 的纯身份/字段重验；非本地主机执行，非 worker replay，FE/JIT 未运行 |
| full p6 worker / scientific raw | `NOT_REACHED` / `NOT_CREATED` | `raw_member_count=0`；p6 tensor/FE field arrays 未生成，独立 tensor/CSR checker 未运行 |
| W1 / W2 | `NOT_RUN` | 本次补充执行不会自动继续；W0 full qualification 未完成，W2 另缺 C1c 与完整 p6 链 |
| 原尺寸 full solve | `NO-GO` | AUTO 接线、全部 q 因子、完整恢复、精度与端到端成本未闭合 |

### 保存组件纯校验结果

| 组件门 | 重算最大 defect/ratio | 限值 | 结果 |
|---|---:|---:|---|
| C/D/H 与 raw action 等价 | `3.5931818134322393e-14` | `1e-10` | PASS |
| 532-mode full-DOF rank-one bound | `2.4672054282185927e-13` | `1e-10` | PASS |
| 五状态 action/recovery/output | `3.099637928778201e-14` | `1e-10` | PASS |
| 物理 FE RHS literal defect | `1.7324712509441664e-14` | `1e-10` | PASS |
| 非零端口 mode equation defect | `1.8654147652106162e-14` | `1e-10` | PASS |
| transform gate ratio | `3.4637921787560976e-6` | `1` | PASS |

这是保存组件收据的重算，不是全域方程 residual 或物理 R/T/A。求积数据是 4 个 facet identity records（两侧 × 两分量、相同节点）与 8 个独立身份比对，不表示执行四个 q cases。

### 资源、历史 attempt 与时间

- 当前 worker 的同时进程树 RSS peak 为 `1,408,434,176 B`，采样间隔约 `0.25 s`；PSS disabled/null；task swap `0 B`。native host preexisting swap `21,600 KiB`，不构成整机 zero-swap 资格。8 GiB raw-export 上界 `6,900,030,936 B` 是导出预算，不是 RAM/RSS。
- 两次 pre-FE worker fail 分别耗时 `2.026239892 s`（missing `src`，RSS `287,481,856 B`）及 `2.090595266 s`（live subreaper identity gate，RSS `290,197,504 B`）；当前 worker `196.762108860 s`。三次 worker elapsed 小计 `200.87894401792437 s`，不包含 `preflight_6bbc` shell/activation blocker，其耗时/收费 unknown。完整准备与 W0 总收费仍 null。
- 四小时 policy cutoff `06:41:49Z` 与 FE 启动 deadline `10:07:14Z` 分开；FE 在启动 deadline 前开始，worker 在 policy cutoff 前退出且 time gate false。policy 窗是派生 allowance，不是实测准备时间；现已到期，不启动新 FE。V6 debit `5,428.582333962078 s` 不变。

native 侧 36 份支持收据 `5,757,491 B` 有逐文件 SHA 和 copy/fsync/readback；原 35-member 包 `47,078 B` 是日志/ABI/资源/测试收据，不是 tensor/场数据。worker 在 raw 导出前失败，科学 p6 tensor/场原始数据没有生成；收据跨窗传输受限是另一项事实。native JIT 64 files、`1,220,807,231 B` 留在原路径。细节见 [actual-run record](records/native_w0_actual_run_v1.json)、[test summary](test_summary.md) 与 [response V7](../response_v7.md)。

5f74 提交中的完整旧 pre-FE ledger 与旧完整 response 均有独立、hash-bound 原文快照：[ledger snapshot](records/review_v7_prefe_snapshot_5f74e15.json)（10,566 B，SHA256 `e89103312f52f5717a3219d7ca01f5ea0c1ff41b178321ba43a62c259eae2f20`）及[旧 response snapshot](../response_v7_prefe_snapshot_5f74e15.md)（12,983 B，SHA256 `922f6efc5e75e63e480025eef60294c70d999d20b0aa96958beaa256244a8bd5`）。旧 response 中目标/AUTO/W1/H 成本账与历史负结果保留完整；早期 source authorization/no-PID/held 仅属历史时点。

本地文档合同 suite 使用 `scripts/activate_myfenics_wsl.sh` 的 `.venv`、PETSc 3.19/Open MPI 4.1.6 旧栈；最终输出见 test summary，不代表 native W0 ABI 或 PDE。native focused `40 passed, 10 skipped` 与两次 public validator PASS 均是已有 native 回执，不代表 PDE 或 raw checker 通过。数值代码仍以 `5f74e15fae6e01e4361325db162806a7319ba3f4` 为基线；主控审核后统一提交推送并回读最终 HEAD。
