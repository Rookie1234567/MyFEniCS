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


## 唯一新结构：R-GEO-CELL80-v3

先把相邻单元共用的边/面未知量放进有交叠的小问题，分别解局部修正后按共享次数平均，检验旧按编号分块是否切断了重要局部耦合。采用一个物理六面体的全部p4 Nédélec trace支撑作为一个子域；支撑包括边/面的切向自由度，其基函数跨相邻单元延伸，且Floquet从端支撑通过已有复数MPC映射纳入主端。用现有 `owned_active_support_groups` 从真实cell recovery/trace map取得独立主自由度，复用历史slab方法的支撑/加性限制延拓原则；不迁移它的大子域因子、shift或参数扫描。旧Task39递归粗逆和bubble的量级1停滞，以及PARA001/005无神经额外收益/私有CSR超预算的证据仍保留；本结构没有已有同配置实测，不重复旧大算例。

局部矩阵是已约束、已装配的原Schur主子矩阵，包含这些自由度的邻单元贡献，不能把裸单元Schur当作整个子域算子。限制为canonical master/port坐标提取，延拓为同坐标求和后乘共享次数的倒数。Floquet相位/方向已由原装配的复数共轭约束处理，不在限制/延拓重复施加。每子域带完整80端口，共享次数252，保留其原dense DtN块/相位/所有耦合，不截断通道。对子域原矩阵直接局部LU，无shift、hidden fallback；局部奇异即停止并保留错误。

```math
I_K=\mathrm{support}_{\mathrm{MPC}}(K)\cup\{\mathrm{all\ 80\ ports}\},\qquad
B_{\mathrm{geo}}r=D^{-1}\sum_K R_K^T(S_{I_K,I_K})^{-1}R_Kr.
```

`D`是每个canonical未知量出现的子域次数；这仍是处理全空间的固定线性PC，不是global p4逆。内层FGMRES和最终原A4/port/recovery不变；本轮不把NN附在此结构上。

| 构造前预算 | 上界 bytes / 身份 | 条件 |
|---|---|---|
| 252子域、每域192trace+80port | 最大272行（derived from frozen FE）；实际支撑逐域核验 | 小于global21824、原6000行patch上限 |
| 全部局部LU和pivot | 298577664，derived dense payload upper bound | 加原cell/port3469728后302047392 <512MiB |
| 临时reader/Fortran/LAPACK预留 | 3586048，一次仅一个域，derived | 不同时存局部块副本；因子最终payload逐字节核对 |
| 索引/次数/权重/在线buffer | 构造前逐项计算；512MiB上限 | 无basis/weights/私有audit CSR |
| 整树工程规划 | 8GiB，predicted reserve | 原p4 runtime预留4GiB，包含实际复用峰1.001GiB的校准；不是allocator/RSS数学上界，16GiB整树采样停止仍有效 |

构造前保存所有实际support/几何hash、multiplicity、因子/临时/表示账，再读第一个局部块。只在已消费index0/10/11上各运行一次RIGHT32/max256/zero，0..256每步完整保存reported/显式Schur及独立原native/port/recovery；0/32/...256另测PC作用，观察耗时与PC诊断开销单列。无旧state/teacher解作为初值。新结构开始前source提交clean；候选冻结后才单独选择未参与设计的集合，未运行不能称fresh终测。

预登记停止分流：若physical或mixed仍为量级1（原A4>=0.1）且末32步Schur改善不足1%，停止扩展teacher、表示和训练；仅port-only改善不足以证明全局困难方向消除。否则做有限same<=128 rank/512MiB的既有POD与真实停滞误差空间对照；teacher只可离线分进程，退出后再候选，不漏在线。无论本轮诊断如何，F5不自动授权；严格资格仍要求新的未见集合全部原A4/port/recovery<=1e-10。

复用9份状态已复现：reported与显式Schur一致，native映射最大差7.44e-15，恢复状态一致。Schur报告是绝对范数，常用相对值除原Schur RHS；旧audit另一数值除RHS范数加算子输出范数，native除有效原RHS，port除参与项范数和，不能直接比较这些数字。physical旧三路线port分母分别0.0760242/0.175721/0.221812；相对closure变小不保证绝对port错误变小。本轮不修改范数或loss权重。
