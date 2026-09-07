# Task39extra 工作站移交边界

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
