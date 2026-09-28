# Task042 Response V3：有限诊断完成，全局粗逆仍未合格

| 身份 | 实际值 |
|---|---|
| branch / worktree | `task42_neural_coarse_inverse` / `/home/fenics/Projects/NN-Lab` canonical linked worktree |
| 起点 / base | `d42a7de47bcd966472d58367bab93872d31584e7` / `ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| reuse source | `b158c5301e7ff59000b15b335672afdb61c5e5e1` |
| 唯一结构source | `7fc3f1434cf4f38f43e5244ebfed3a19d0780a26`；clean启动，后续文档HEAD不替代 |
| 终态 / F5 | `BOUNDED_STRUCTURAL_GLOBAL_STAGNATION` / not_run，等待review，不merge |

按用户授权仅新增一个有限B0/表示诊断批次；受控共享CPU覆盖仅Task042旧heavy禁令和全机独占要求，不取消资源/精度/provenance，不代表F0正式review。原task/review及response_v1/v2、所有失败raw和v2数字记录保留。普通默认与旧连续512行B0冻结合同未改。[完整授权与预登记](outcomes/bounded_diagnostic_design_v3.md)。

已有实现证据是原A4/A6接口、完整80通道和严格返回；复用诊断是三个代表RHS ×三候选的已有失败状态，不重跑旧KSP。reported Schur与显式矩阵/独立单元Schur一致，native映射最坏7.44e-15、提交恢复一致；这些样本未发现残差接口bug。reported为绝对范数，Schur/RHS、operation-scale/native/port分母不同。原physical B0/LIN/NN port绝对0.0353871/0.0420845/0.0399233，不能把相对closure下降当作绝对端口改善。[9状态实值](outcomes/records/reused_diagnostics_v3.json)、[范数、端口绝对误差与restart诊断](outcomes/residual_diagnosis_v3.md)。

CPU差异已按实际证据核清：oracle manifest/source_state/worker affinity为33，F4-B0为45；v2概括CPU0不准确，本页明确纠正，不猜填或回写raw。[逐run manifest与affinity](outcomes/records/cpu_provenance_v3.json)。一次旧选核准入拒绝未启动FE，活动样本证实宽休眠线程最后PSR被误当占用；V3显式准入用逐CPU/线程活动且仍完整避让窄亲和性/SMT，同旧默认隔离。[证据](outcomes/records/admission_repair_v3.json)。

旧512行连续编号块可能拆开相邻单元共用的场分量；新结构把这些分量放入交叠小问题，分别修正后按共享次数平均，代价是更多局部回代。R-GEO-CELL80-v3把每个物理单元Nédélec边/面trace支撑经已有MPC master映射纳入小问题，共享边/面及周期主从造成重叠；每域完整80port。限制为canonical坐标提取，延拓按次数平均，相位已在原约束装配中，不重复施加。只因子原Schur主子块，max272行、252块；全factor 302047392B、表示/buffer 3010048B，构造前保存容量计划；无global p4 LU/hidden fallback/private audit CSR。原A4/A6/80通道和最终验算不变。

| 已消费诊断RHS / index | 旧B0原A4 | 新GEO原A4 | 新GEO port closure | 新GEO port绝对残差 | 末32步Schur降幅 | 严格返回 |
|---|---|---|---|---|---|---|
| physical_PH_b6 / 0 | 0.998654967105 | 0.891957825531 | 0.00773091335604 | 0.187210874612 | 5.70298292157e-06 | False |
| unseen_port_only / 10 | 0.954192801905 | 0.935861877336 | 0.725338952963 | 0.000935056697255 | 1.23982140442e-05 | False |
| unseen_mixed / 11 | 1.000780838 | 0.932010701839 | 0.677921290639 | 0.000951255917368 | 1.24422653291e-07 | False |

原label中的unseen沿用旧artifact ID，不代表本轮fresh。三项仅已消费诊断，0..256逐步reported/显式Schur与独立native/port/recovery完整保留；新PC使physical的native残差下降约11%，PC探针显示局部修正有更有效的分量；这支持几何局部耦合处理有所改善。剩余全局困难方向仍量级1并停滞，不能称严格收敛，也未作谱测来区分低频、共振或其他机制。port相对分母增大需同时看绝对残差。原R-LIN在固定Q/native范数下已达到精确最小残差；同Q的MLP不能默认胜过它。本轮不改变loss、不增rank/width/epoch或迭代，不扩展新网络。

按预登记停滞条件停止，真实停滞误差空间对照和新offline teacher not_run；没有教师解泄漏在线/初值。旧16heldout已消费，只诊断；结构source冻结后另选seed420620独立整族16项，未生成/测试，不称fresh终测。F5/p6外层、official RTA/A_volume/场/80复模态/所有通道功率、短波、GPU均not_run。[完整曲线](outcomes/records/full_residual_history_v3.csv)、[分流](outcomes/records/gate_decisions_v3.json)。

| 新阶段 | 真实clean source | 现场核 / threads | 整树wall s | 整树RSS峰 B | own swap B |
|---|---|---|---|---|---|
| V3-reuse | `b158c5301e7ff59000b15b335672afdb61c5e5e1` | 12 / 1 | 141.744161531 | 1074900992 | 0 |
| V3-overlap | `7fc3f1434cf4f38f43e5244ebfed3a19d0780a26` | 0 / 1 | 2494.75110155 | 945766400 | 0 |

新数值监督wall合计2636.49526309s、最大同时整树RSS1074900992B、own swap0，Task042 CPU-only、无GPU VRAM分配；教师/训练新成本0（not_run）。geom setup、数值PC及逐步审核/probe成本单列。全部shared-workstation，性能inconclusive。16GiB整树/12GiB warn包含launcher/compiler/后代，0.5s监督，无cgroup委派不假称连续内核限制；own lock/阶段顺序、独立FE/ML/cache、math1、nice10/idle I/O，未调整任何邻任务/锁/watchdog。PSI未持续触线、邻身份/CPU推进观测保留；无可比实时阶段指标，不能证明零影响或量化争用。编辑/Git总会话成本未持续采样，辅助测试/后处理另计。[资源/全部source账](outcomes/records/run_index_v3.json)。

前期48纯数组/协议、4 FE支撑/ABI/旧默认、4准入/监督通过；收口49项定向测试通过，资源测试改用原始整树样本断言并保留失败尝试，监督器/数值源码不改；最终focused/static/文档render证据在[测试页](outcomes/test_summary.md)。原继承文档checker问题保留，不声称全仓/CI全绿。本轮outcomes及development_progress/model_registry新增V3段，旧负结果原文保留。[最新summary](outcomes/summary.md)明确区分inherited/reused/new measured/not_run和依赖边界。仅推送 `git push origin HEAD:refs/heads/task42_neural_coarse_inverse`；精确最终完整HEAD、upstream/clean/ahead-behind由实际push后回报。停止等待ChatGPT review，不merge。
