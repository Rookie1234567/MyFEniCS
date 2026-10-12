# V76：廉价对照和三方向残差最小化的有费用结论

Jacobi在这个固定问题上有早期作用，原残差由1降到0.38883，64步为0.34171；但没有达到预登记0.1门。三方向SMR能避免旧固定和的坏方向，仍未取得完整方程或场，且64步原残差0.36008差于廉价Jacobi。关闭固定低维粗修正＋当前主子块RAS的组合微调，不以剩余额度补尾部。

| measured同题配置 | 累计步 | 原true | 接口true | prepared-start全过程/s | 科学出口 |
|---|---:|---:|---:|---:|---|
| B0 | 32 | 1.93460766967 | 0.376872295207 | 520.729 | 效果门或最终资格未过 |
| BJ | 32 | 0.38882658639 | 0.379105019552 | 526.966 | 效果门或最终资格未过 |
| PROMOTED | 64 | 0.341713600189 | 0.33941522177 | 546.174 | 效果门或最终资格未过 |
| SMR | 64 | 0.360076582954 | 0.147596138687 | 2401.451 | 效果门或最终资格未过 |

复对角只使用原各单元/MPC及真实port的对角；零对角逆值固定1，未扫描shift/阻尼。SMR分别生成输入、旧p2/port粗修正、38块局部修正，用原作用的三个像解复数小最小二乘；这改变修正组合，增加作用及三角解成本，属于非线性PC，不是神经收益。W/D仅两个资格输入完整保存，迭代只存小秩/权重/保护元数据。[完整回应](../response_v76.md)

## 已实际完成与未运行

全部授权分流完成：B0/BJ各32步，无39因子；BJ通过32门后独立KSP续至累计64并停止；SMR实际39numeric、两个真实输入保护、64步FGMRES及完整原式后停止。4次KSP/160新步，没有新的分区、Z/E0、harmonic或fine全局矩阵/因子。旧V71 CAPACITY_BLOCKED与V75数值FAIL保持，旧窗口closed不重开。

完整canonical/native/port系数和原式向量已保存，新进程独立q15/q63重算四态差0。formal1e-6、retained1e-11和严格同离散场门未通过；原残差>1e-2的四态六场/240点/828衍射/RTA/吸收为NOT_RUN_BY_FAIL_FAST_POLICY，不能称official。保存828port不等于完整模式物理评分；后者未运行。[科学checker](records/scientific_checks_v76.json) · [系数与输入/source](records/source_array_bindings_v76.json)

## 实际成本与适用边界

Jacobi两段实际总1073.140750s；SMR单case2401.451390s且未更有效。不授同精度生产时间或内存收益。全监督sampled峰41.453971863GiB、gap1.36729622912s、swap/OOC0；80GiB因子子门和96GiB live共驻门通过，预测和sampled峰分列。父packet/Z/E0准备以及全部失败仍计历史成本，prepared-start不是geometry cold N1。

新作用次数、全部command费用/峰/gap、源码与原始增量归档、ordinary修复和最终closed状态由[费用](records/resource_costs_v76.json)、[效果曲线](records/residual_history_v76.json)、[PC证据](records/operator_PC_checks_v76.json)、[决策/修复](records/decisions_repairs_v76.json)绑定。旧partial归档未覆盖，无PDE重放；GitHub视觉NOT_VERIFIED。

下一项仅建议在新合同下改变局部传输/波动空间的稳定性机制，先对同RHS核算相对Jacobi的真实收益；当前不实施、不开新窗口、不通知邻支。有限失败不证明所有Maxwell迭代不可能；旧空间精度FAIL、原尺寸0.7nm/2TB48h及NN20仍未资格。

最终结算UTC 2026-10-12T05:15:37.590387+00:00：已知不重叠wrapper/增量归档费用 5442.469386690s（包括失败与尾部文档补消费），研究实时时长 8191.785677s；新去重存储 5612798460B，Task累计 202405766642B，free 2671173070848B。ledger closed/active null、后代清场及自有锁释放已核实。先前费用为阶段快照，此段及最终费用记录为当前完整下界；unknown保持，未重复相加父费用。
