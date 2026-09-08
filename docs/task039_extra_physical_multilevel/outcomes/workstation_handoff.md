# Task39extra 工作站移交边界：V2关闭

| Review V2 / F5 | 当前结论 |
|---|---|
| F1 / F2 | 完整packed S6数学等价通过；配对中位0.938459>0.75，速度不足，F2 not_run |
| F3原始模型 | 13.5nm/1°/p6h10/MPI1/80modes；source `60b8df2a24cbcd96e49e018be22fb64f06eeae3f`；零初值476步真残差0.10535820013809101>1e-6 |
| 方法与失败含义 | 保留H6–准确p4–H6三个顺序方向，仅末尾联合选权；局部残差比中位0.979479，rank3/无回退；不足以让完整p6收敛 |
| 用户收尾 | USER_REQUESTED_CONTROLLED_STOP；raw worker CONTROLLED_STOP、wrapper WORKER_FAILED/exit4并列；未触发原自动budget/stagnation Gate |
| 时间限制 | workflow monotonic7588.369777 / UTC8363.831318 s；solve至请求monotonic6791.466003 / UTC7478.995420 s；UTC solve超7200，原因未唯一确定，不能声称全部wall预算通过 |
| 资源与清场 | RSS/PSS峰3351887872/3317217280 B，28753样本均可读；cap8525078528 B、至少4GiB余量无违规；swap0，56 PID清场 |
| 后续 | F4/official锁定，无第三候选、续跑或0.7nm资格；仅F5文档/测试/审阅后提交推送，非master merge |

本轮没有合格原始场，不具备工作站solver资格；global p4诊断factor和难误差消除效率仍是限制。0.7nm、2TB容量和任意非可分结构均未通过。停止的是这两个限定候选，不是数学不可能性结论；无后续已授权PDE。

| V2 selective merge依赖组 | 数值行为 / 依赖 / 测试与fresh evidence / 建议顺序 |
|---|---|
| production numerical/core | 不提升本轮profile或joint算法；原A6/A4保持，既有组件候选仍需独立review；ordinary默认不变 |
| reusable runner/watchdog | 新profile接线和应用PID停止复用597；依赖原launcher/worker；test365/366/368，fresh F3用户停止safe476与清场；双时钟及user-wrapper分类限制须保留，core后审 |
| checker/benchmark | 已有计数checker与只读raw审计，依赖逐PC/周期/资源/哈希；不重新实现solver；接线后审 |
| compact evidence/docs | F1速度不足、F3未收敛/用户停止、时钟差异、完整索引与Response V3；最后合入 |
| research-only | packed S6及joint MR3、dat/profile、p4全局诊断factor；joint改变PC数值组合，依赖H6/原MR/A6/P64/A4/MUMPS；F1/实现tiny通过但fresh F3残差未过；禁止生产默认 |
| do-not-merge | raw向量、checkpoint、matrix/factor、cache、timeline、私有audit与测试scratch，保持ignored |

仅为依赖组建议，未获master merge approval。证据见[中心报告](packed_and_joint_mr_v2.md)与[response_v3](../response_v3.md)。

## 历史V1/A5移交快照（不作为新增运行授权）


| Review v1 / R6 更新 | 当前边界 |
|---|---|
| R1 | 等价通过、性能不通过；74.87089344408014 s对22.021386729524238 s；不是S6数学或收敛失败 |
| R3 formal source | `cbf56e87e515ab0c3fc5756cb6cf52feb047f610`；原始p6/h10 MPI1 H6–p4–H6零初值 |
| 数值 / 资源 | solve7200.255611149943 s，last_safe576真残差0.0791360407785889；workflow7966.278611822054 s，RSS3352014848 B，swap0；动态cap与4GiB余量无违规 |
| 停止修复 | `597546311feea60d61acb2a9999b706dd895dcf0`未来LIGHT opt-in；23局部测试通过；没有R3重跑，没有补齐原worker终态 |
| 资格 | `LIGHT_PC_FASTER_BUT_NUMERICAL_UNQUALIFIED`作为解释，parent正式分类仍为`PERFORMANCE_CONTROLLED_STOP`；不满足reference-assisted PASS或生产资格 |
| 下一步 | 集中review；不运行R4/R5/第三PC，不延长预算；完整S6+contiguous packing重新资格化为not_run |

本轮减少了单次修正成本，但准确p4逆辅助下的外层收敛效率仍是主要blocker。p4全局诊断factor依赖未解除；非可分、独立同离散authority和0.7nm物理收敛未取得。下面历史A5表保留，其旧“下一review”由当前R6证据补充，不作为新运行授权。见 [成本与贡献](cost_and_contribution_v1.md) 和 [response_v2](../response_v2.md)。

| 项目 | 当前可交付内容 |
|---|---|
| 状态 | 本机真实性能 Gate 已发生，可以移交可复现代码和机制证据；不是可用 solver 资格移交 |
| 正式 source / 输入 | `54ab46cf4c8378a9b27650ca6963cadb34013a2f`；[原 A2R dat](../../../input/task39extra/original_13p5nm_p6h10_p4_reference.dat) |
| 事后计数修复 source | `adc448814c3022fdf6d1a688da69a28238e7db9c`；只修账本，不使旧数值 evidence 失效 |
| 本机限制 | 13.5 nm/1° 原 p6/h10 到 3600 s 仍未达 1e-6；非可分、h5、独立 direct、official 输出均未运行 |
| 结果入口 | [总结](summary.md)、[运行/源码/原始 hash 索引](records/run_index.json)、[测试](test_summary.md) |

准确的 p4 中间逆已经把单 PC 中位耗时降至约 20.61 s，但未使外层在冻结预算内成功；最后 160 步真残差为 0.18250767622880507。尚不能仅凭这一诊断区分中间空间表示、S6、MR 或外层重启对最终效率的贡献。下一 review 需选择具体比较，不能自动增加预算或换算法。

底层直接求解是把一个小问题整体分解后反复回代，当前便宜，但规模增长时会成为内存和串行瓶颈。当前 positive p1 为 1067 rows，p3 为 23073 rows；p1 的 4096 rows/512 MiB 合同仍有效。A2R p4 的 53164-row 增广分解是显式诊断，不能拿它绕过生产底层限制。h5 未运行，不宣称已知其可容纳。

| 工作站阶段（全部未授权启动） | 必须先解决的问题 |
|---|---|
| W0 | 用户实际迁移后确认可见 RAM、NUMA、MPI/线程和 complex ABI；最新 review 冻结输入/预算后核验 13.5 nm 原始与非可分问题，不能把当前未通过结果冒充通过 baseline |
| W1 | 5 nm 真实非可分材料和至少两个有意义离散；核验场、衍射级与体吸收，不混淆旧 10° 与本任务 1° |
| W2 | 用有界局部/分布式多层方法解除随 N 增长的 global direct 底层瓶颈；至少三个实测规模点校准容量与总工作 |
| W3 / W4 | 仅必要的 2 nm 或 1 nm 中间点，再到 0.7 nm 受控规模与目标尺寸；保留三维材料变化及矢量 Maxwell，不做准二维替代 |

2 TB 是规划机器级容量，实际预算需用真实 MemTotal 与有效余量重新冻结。任务建议线为 `min(0.80*effective_total, effective_available-reserve)`，并非实测承诺。以 10^9 个 complex128 未知量估算，FGMRES32 的约 65 个 V/Z 向量仅存储就约 1.04×10^12 B（1040 decimal GB），尚无 FE/PC/编译/后处理；这是 derived 模型，不是可运行证据。本机 restart32 不保证适用于工作站 0.7 nm。

容量链须分别校准材料、离散精度、外部通道、local inverse、global coarse、DtN、MPI 复制七类限制，统计同时存活的对象；不能把旧 256 GiB no-go 直接变成 2 TB no-go。

| selective merge 依赖组 | 内容 / 数值影响 / 证据 / 顺序 |
|---|---|
| production numerical/core 候选 | 已独立验证的可复用传递、S6 精确对角等组件；依赖既有 FE/MPC/setup，对角保持原积分及约束。三单元与 serial/MPI2 oracle 已绑定；仅组件候选，不含未资格化的主 profile，不提升生产默认 |
| reusable runner/watchdog | 既有 public launcher/worker 和同 parent 资源链；先依赖 core，再接显式 profile。正式证据为本次受控停止；保留 worker 正常完成缺口 |
| checker/benchmark | 原输出 checker + 最小计数重算；依赖逐次 raw；test356/359/360 19 passed。只影响未来计数，不改 solver |
| compact evidence/docs | 五中心文件、开发总账、hash-bound 索引；最后合入，保持旧负结果 |
| research-only | 未资格化的 A2 物理中间层/shifted-cycle，以及 A2R augmented p4 reference、各自显式 dat/profile 与 tests；依赖可复用传递、S6、original A4/carrier/MPC/MUMPS。A2R 163 RHS 通过但 outer 未过，两条候选均不得升级为 production default |
| do-not-merge | 大型 results、cache、矩阵/分解、checkpoint solution 和完整 timeline；保持 ignored，以 hash 定位 |

此表为审阅建议，未获 merge approval。下一动作是集中 review，非工作站 heavy 启动授权。

| R6 selective merge补充依赖组 | 行为 / 依赖 / 验证 / 顺序 |
|---|---|
| production numerical/core候选 | 可复用局部作用/packing与monitor组件；保持原A6，依赖FE/MPC；局部oracle与bitwise monitor测试支持；先审core，不把未资格化profile升为默认 |
| reusable runner/watchdog | LIGHT应用PID/start-ticks登记、一次安全停止请求、超时/资源整树硬停；依赖launcher/worker marker；真实MPI1五路径小fixture；在core之后审阅，fresh大PDE未运行 |
| checker/benchmark | PC成本与贡献审计、32步曲线、真实残差快照；依赖raw记录；不重算求解器，不伪造终态 |
| compact evidence/docs | 本轮hash-bound小JSON、成本文档、summary/response及总账；最后合入，保留A5与R1/R3负结果 |
| research-only | S6等价fast、H6–p4–H6及p4诊断factor；分别依赖原action、transfer、MR、MUMPS；fresh R1速度失败/R3性能停止，禁止生产默认 |
| do-not-merge | 私有完整audit、raw向量、factor、cache、timeline与测试scratch；保持ignored |
