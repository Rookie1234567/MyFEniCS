# Task042 V3 有界诊断授权与预登记

| 项目 | 本轮范围 / 单位与身份 |
|---|---|
| 起点 | local/remote `d42a7de47bcd966472d58367bab93872d31584e7`，clean；冻结base不变 |
| 用户授权 | 仅一个有限B0/表示诊断批次；新增命名与显式opt-in；不修改旧task/review、旧B0合同或普通默认 |
| 保留结论 | R-B0/R-LIN/R-NN各15个非零失败，仅零通过；原16个heldout已消费，只作诊断；F5未运行 |
| 复用集合 | 旧F4 index0 physical、index10 port-only、index11 mixed；三个候选各一次已有失败状态与4个已存残差快照，不重跑旧KSP |
| 先验检查 | KSP绝对Schur报告、显式矩阵/独立单元Schur、原native A4、端口、恢复、PC幅值、restart变化及范数分母；不先改loss |
| 原准则 | MPI1，数学线程1，complex128；RIGHT FGMRES32/max256/zero/rtol1e-12；严格原A4/port/recovery全部1e-10 |
| 条件推进 | 完成复用诊断后只登记一个几何重叠PC；构造前证明局部因子、表示和临时对象容量；少量已消费RHS比较，量级1停滞则停止扩大表示/训练 |
| 未授权 | 新网络、增加rank/width/epoch、迭代预算/容差改动、GPU/短波/p6外层、扫描与global p4 LU部署 |

用户明确要求“当前R-LIN已是固定Q、固定native范数下的精确最小残差修正”。同一Q上预测系数的MLP没有优于该精确最优解的理论空间；本轮先诊断修正空间和全局耦合，不扩大网络。

用户继续授权Task042受控共享CPU运行，覆盖仅本任务旧§2.3 heavy禁止/全机独占要求；原task/review历史保留，授权不代表F0正式review。只使用自有nonblocking lock，一次数值阶段，现场选不与忙物理核/SMT同胞冲突的核心，nice10/idle I/O，仅监督和清理本树。RSS整树16GiB/12GiB、own swap0、原reserve加邻增长规划128GiB、磁盘50GiB/artifact20GiB仍有效；无cgroup委派时如实声明0.5s采样整树停止，不假称内核限制。FE/ML/缓存/结果均在NN-Lab，只读原生prefix，不操作邻任务或锁。

所有成本标shared-workstation，性能inconclusive。新负载前记录资源基线，运行中只读低开销PSI/status和既有短阶段记录；有持续压力只撤Task042。旧快照不足以填补不存在的restart状态：V2仅保存0/32/128/256显式残差向量，其余边界只报告已存KSP标量；新结构运行将显式逐步记录。

CPU审计以[逐run实际证据](records/cpu_provenance_v3.json)为准：oracle manifest和worker affinity都是33，F4-B0都是45，其余已核FE是0。V2“全部CPU0”的概括不准确；本页明确纠正，原response/raw记录不回写、不猜填。ML实际affinity另从其原始环境记录取证。

复用输入和原artifact哈希见[diagnostic_v3.json](../../../input/task042_neural_coarse_inverse/diagnostic_v3.json)。正式FE前实现提交clean，run绑定真实source SHA；之后仅在本执行分支提交response_v3及outcomes/两总账，推送后等待review，不merge。

首次数值启动在旧准入时拒绝，未启动FE worker。只读逐核/逐线程样本显示76个宽线程中仅7个有CPU计数推进，多个物理核busy=0；旧逻辑把休眠线程最后PSR当作忙核。V3显式profile改用一秒实际逐核busy<=5%，仍完整排除窄亲和性邻线程及其SMT同胞，排除活动/无法确认的宽线程所在核；V2默认不改。4个准入/自有监督测试通过，[修复证据](records/admission_repair_v3.json)保留失败与原始样本，不是数值参数重跑。
