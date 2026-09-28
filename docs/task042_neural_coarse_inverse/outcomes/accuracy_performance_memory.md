# 严格粗逆的准确性、时间与内存

| 路线/作用 | 严格通过 | 实际 PH b6 原A4残差 | 同 RHS port closure | 非零 RHS 内部恢复最大 | 整树 wall s | 整树 RSS 峰 |
|---|---|---|---|---|---|---|
| R-B0 | 1/16，仅零 RHS | 0.998655 | 0.465472 | 4.70942e-16 | 486.668 | 0.793 GiB |
| R-LIN | 1/16，仅零 RHS | 0.998262 | 0.239496 | 2.11953e-16 | 1239.273 | 0.962 GiB |
| R-NN | 1/16，仅零 RHS | 0.998456 | 0.179987 | 2.20347e-16 | 1238.082 | 0.937 GiB |

表内时间为同一16RHS组的监督工作流wall（含launcher、装载、p4构建/PC setup、求解、验算和释放），RSS为0.5s采样的launcher与全部后代同时RSS和。全部是shared-workstation，绝非无争用条件的中位加速；没有合格路线，按任务书不追加三次计时。实际teacher8参考、F1完整p6接口和F4 p4-only生命周期/库存不同，不能作正式时间或20%内存Gate的分母。

## 逐载荷真残差

| index / 未见载荷 | R-B0 A4 / port | R-LIN A4 / port | R-NN A4 / port |
|---|---|---|---|
| 0 / physical_PH_b6 | 0.998655 / 0.465472 | 0.998262 / 0.239496 | 0.998456 / 0.179987 |
| 1 / zero | 0 / 0 | 0 / 0 | 0 / 0 |
| 2 / F1_rhs0_r_000 | 0.998655 / 0.465472 | 0.998262 / 0.239496 | 0.998456 / 0.179987 |
| 3 / F1_rhs0_r_032 | 1 / 0.984073 | 0.999304 / 0.230701 | 0.999522 / 0.231518 |
| 4 / F1_rhs0_r_128 | 1 / 0.999995 | 0.999302 / 0.23056 | 0.99952 / 0.2325 |
| 5 / F1_rhs0_r_256 | 1 / 1 | 0.999302 / 0.23056 | 0.99952 / 0.2325 |
| 6 / physical_phase_i | 0.998655 / 0.465472 | 0.998262 / 0.239496 | 0.998433 / 0.220653 |
| 7 / physical_amp_1e-3 | 0.998655 / 0.465472 | 0.998262 / 0.239496 | 0.998456 / 0.179987 |
| 8 / physical_amp_1e3 | 0.998655 / 0.465472 | 0.998262 / 0.239496 | 0.998456 / 0.179987 |
| 9 / unseen_internal_only | 1.89056 / 0.740581 | 1.86265 / 0.129738 | 1.86219 / 0.169348 |
| 10 / unseen_port_only | 0.954193 / 0.276458 | 0.861691 / 0.148338 | 0.822191 / 0.123535 |
| 11 / unseen_mixed | 1.00078 / 0.62499 | 0.98513 / 0.167229 | 0.991893 / 0.249092 |
| 12 / unseen_mixed_phase_i | 1.00078 / 0.62499 | 0.98513 / 0.167229 | 0.991053 / 0.257942 |
| 13 / unseen_mixed_amp_1e-3 | 1.00078 / 0.62499 | 0.98513 / 0.167229 | 0.991893 / 0.249092 |
| 14 / unseen_mixed_amp_1e3 | 1.00078 / 0.62499 | 0.98513 / 0.167229 | 0.991893 / 0.249092 |
| 15 / seed420400_remaining_0000 | 0.910583 / 0.430199 | 0.602504 / 0.118919 | 0.631766 / 0.125327 |

非零项全部固定RIGHT FGMRES32/max256/零初值，迭代达到256；三条路线各15个非零未通过原A4门限`1e-10`。port closure也需<=1e-10，内部恢复与native/Schur恒等式独立保存，不因先拒绝native而省略。零RHS精确零、0iterations且不调用backend；原raw `native_audit`沿用了前项缓存，不能归因到零RHS，v2摘要置null并使用zero自身的三项0检查。原始证据未改写。[全部精确数值/PC耗时 CSV](records/strict_rhs_metrics_v2.csv)，[R-B0](records/f4_b0_complete_v2.json)、[R-LIN](records/f4_lin_complete_v2.json)、[R-NN](records/f4_nn_complete_v2.json)。

## 表示和训练与严格资格的区别

| rank | validation 误差表示比 | validation 最佳 native残差比 | validation 线性 native残差 | 表示及在线buffer B | rank wall s |
|---|---|---|---|---|---|
| 16 | 0.732241 | 0.633718 | 2.20516 | 24675584 | 42.515 |
| 32 | 0.687492 | 0.507641 | 1.80659 | 43866880 | 45.873 |
| 64 | 0.63802 | 0.414244 | 1.50899 | 82274048 | 60.624 |
| 128 | 0.513825 | 0.333884 | 1.26123 | 159186688 | 79.966 |

oracle先取B0一步后的剩余误差，再问有限basis能否表示teacher修正，并在该子空间寻找原方程最佳残差。两个validation中位比门限在数据生成前登记为`.90 / .99`，只作为继续小模型训练的诊断信号。rank128 train误差表示比`.00983542966728795`，validation为`.5138245737888352`，已显示明显的未见载荷表示差距。validation线性一步native中位仍为`1.2612261732272319`，离`1e-10`很远；F4迭代也未补足差距。

模型300epochs/CPU FP64、validation选51，teacher坐标与完整native Gram（含正交剩余项）联合loss；best validation总loss`4.947570117563409`，epoch0为`5.342281302071337`。loss下降不能替代原方程资格。冻结Torch→NumPy16validation probe相对差`5.71091073830398e-17`，FE集成的独立probe差在R-NN构造record实测。heldout16仅严格评估，未用于rank/width/epoch选型，之后标consumed。

## 分阶段完整成本

| 实际阶段/尝试 | 状态 | 真实 clean source SHA | 整树监督 wall s | 采样整树 RSS 峰 | own swap B / GPU |
|---|---|---|---|---|---|
| f1_b0_shared | FAILED | ae5b7d2b79dec38056e4a8b9bd986429989455dd | 5.981 | 0.283 GiB | 0 / CPU-only |
| f1_b0_shared_retry1 | FAILED | 23cb4710e3ed2c8f7c51fd2b3f4e4dd952bea716 | 8.654 | 0.400 GiB | 0 / CPU-only |
| f1_b0_shared_retry2 | FAILED | f194e455cf904d255fbb30151f21d12be19bc56b | 1079.193 | 2.198 GiB | 0 / CPU-only |
| f1_b0_shared_retry3 | FAILED | 7188564f1a284049ddac3eb32a77ccbda84c5c6b | 881.548 | 1.080 GiB | 0 / CPU-only |
| f1_b0_shared_retry4 | COARSE_INVERSE_NOT_QUALIFIED | cca180f875bd22146f2d30fa4d004e372135dfbb | 1242.043 | 1.529 GiB | 0 / CPU-only |
| f2_teacher_shared | TEACHER_QUALIFIED | b72448bb2117a0221f041f1b47ac41049750a3c7 | 1687.602 | 1.451 GiB | 0 / CPU-only |
| f2_oracle_shared | REPRESENTATION_POSITIVE | d9de8ad69bfeeac4860e5187e1738c902a3d808e | 358.751 | 1.309 GiB | 0 / CPU-only |
| f3_train_shared | TRAINING_COMPLETED | a221d881bae9405c98e351df2b0b9533582e6d50 | 22.268 | 0.337 GiB | 0 / CPU-only |
| f4_b0_shared | COARSE_INVERSE_NOT_QUALIFIED | 7216efa605bae155ee383fd716c0fae422448b52 | 486.668 | 0.793 GiB | 0 / CPU-only |
| f4_linear_shared | COARSE_INVERSE_NOT_QUALIFIED | 7216efa605bae155ee383fd716c0fae422448b52 | 1239.273 | 0.962 GiB | 0 / CPU-only |
| f4_neural_shared | COARSE_INVERSE_NOT_QUALIFIED | 7216efa605bae155ee383fd716c0fae422448b52 | 1238.082 | 0.937 GiB | 0 / CPU-only |

上述尝试合计监督wall`8250.064113 s`；各阶段整树RSS最大取`2359627776 B`，own swap最大0；不累加阶段峰。所有成本shared-workstation。训练有载`19.036173629 s`，监督工作流还包含独立ML导入、数据/模型装载和保存。teacher分解setup6.264s、384对数据生成及审核分开见[teacher记录](records/teacher_complete_v2.json)；oracle各rank wall包括构建与原方程审核。安装、ABI和targeted checks额外成本见[测试](test_summary.md)，没有把未监控的编辑/Git等待算进数值总时间。

B0局部因子载荷177886464B，cell/port3469728B；R-LIN表示/在线buffer159186688B，R-NN另有824320B权重。cell、patch、128行bottom均计入构造声明；实际数组载荷与RSS口径不同，basis/temp/Krylov/Python/allocator开销由整树监督覆盖，无额外private audit CSR。teacher后端factor NNZ40282272、RINFOG15报告644.516352decimalMB，只是后端factor载荷，不等于进程峰。离线teacher释放/退出后才开始oracle和候选。

G-no-factor与绝对资源上限已通过；低内存迭代、线性和神经严格资格均失败。G-memory/G-time为`inconclusive`，G-neural无正信号，不宣布TB量级收益或所有网格无效。没有合格单次节省，N=1/10/100的合格总成本及break-even为`undefined`；可记录离线teacher+oracle+训练成本，但不能用失败求解推算摊销。[未运行p6比较](records/full_p6_comparison_v2.csv)全部保留not_run。

验证集原方程残差loss的线性初始映射为1.6581681312213055，所选NN为1.837990301367067，记录`LINEAR_BASELINE_PREFERRED`，仅指该离线native方程目标。它不代表任一粗逆可部署，也不是三进程端到端性能胜出；combined teacher/native loss用于选择epoch，两类目标不可混称。

| 摊销次数N | R-LIN / R-NN合格总成本 | break-even | 原因 |
|---|---|---|---|
| 1 | undefined | undefined | 无合格粗返回，失败计时不能作有效solve成本 |
| 10 | undefined | undefined | 同上；未自动重放终测组 |
| 100 | undefined | undefined | 同上；未作无界重复或外推加速 |

离线teacher（含8参考、384对数据与审核）1687.601743s、oracle358.751261s、NN训练监督22.267641s分开实测；合计2068.620645s为shared-workstation离线成本，basis/PC setup含在各候选工作流中，不能二次累计。尚无严格合格单次节省，不能由该离线合计推断摊销阈值。


## V3 最新有限诊断（原V2正文保留）

| 已消费诊断RHS / index | 旧B0原A4 | 新GEO原A4 | 新GEO port closure | 新GEO port绝对残差 | 末32步Schur降幅 | 严格返回 |
|---|---|---|---|---|---|---|
| physical_PH_b6 / 0 | 0.998654967105 | 0.891957825531 | 0.00773091335604 | 0.187210874612 | 5.70298292157e-06 | False |
| unseen_port_only / 10 | 0.954192801905 | 0.935861877336 | 0.725338952963 | 0.000935056697255 | 1.23982140442e-05 | False |
| unseen_mixed / 11 | 1.000780838 | 0.932010701839 | 0.677921290639 | 0.000951255917368 | 1.24422653291e-07 | False |

| 新阶段 | 真实clean source | 现场核 / threads | 整树wall s | 整树RSS峰 B | own swap B |
|---|---|---|---|---|---|
| V3-reuse | `b158c5301e7ff59000b15b335672afdb61c5e5e1` | 12 / 1 | 141.744161531 | 1074900992 | 0 |
| V3-overlap | `7fc3f1434cf4f38f43e5244ebfed3a19d0780a26` | 0 / 1 | 2494.75110155 | 945766400 | 0 |

新结构仅3个consumed诊断，全部未通过原1e-10；新teacher/训练not_run，fixed Q的线性最优性不变。新port相对closure同时报告绝对残差，不能混淆分母变化；共享成本/performance inconclusive。旧16测试已消费且原失败保留。全部逐步独立残差见[历史CSV](records/full_residual_history_v3.csv)，末周期分流见[Gate](records/gate_decisions_v3.json)。
