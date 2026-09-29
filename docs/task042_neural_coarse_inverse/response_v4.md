# Response V4：V4_GLOBAL_ERROR_TWO_LEVEL

| Review必答项 | 实际回答 |
|---|---|
| 两空间与来源 | OLDPOD：旧256 train对的Q，重新Schur编码；ERROR：预先登记16原train问题、64步轨迹的128个x_star−x_m。两者snapshot/SZ有效rank均128，测试解未进入基 |
| 代数/真实接口 | 四两层恒等式、真实原S/native配对、MPC/80port与恢复均通过；R条件数OLDPOD334.013、ERROR586.120，最大B2SZ缺陷约3.18e-14/1.12e-13 |
| 三诊断与终测 | 两条均strict0/3；physical/mixed都未满足native和固定Schur各0.1。终态`BOUNDED_TWOLEVEL_NEGATIVE`，无候选被选，未使用16项终测not_run，仍unconsumed |
| 无全局因子/容量 | 构造与在线无global p4 factor/fallback/private audit CSR；局部＋R共302309536B，Z＋U89391104B，构建表示/workspace上界481062400B；整树实测峰1128828928B、own swap0 |
| 成本 | 正式六阶段整树wall1534.00828393s；offline/online/审核/IO/释放分账，嵌套计时不相加。全部shared-workstation，性能inconclusive |
| 后续神经路线 | 本批无新NN，不能把非神经空间的自检归为神经贡献。固定B上的两个空间未处理严格收敛困难；未证明空间普遍无效，也未授权扩大网络 |

局部PC分别修正相邻小区域，本批在其前后增加有限全局解方向，试图去掉遍布模型的停滞误差。旧POD和新真实解误差基使用同一完整Schur最小残差两层公式，保持局部PC、原方程、80通道、零初值和256预算。实际P0→P1→双P2→双P3完整执行；没有沿用V3“局部量级1停滞就禁止空间研究”旧前提。

| 路线 / 已消费RHS | 原A4相对残差 | 固定Schur/RHS | port绝对范数 | port operation-relative | 严格返回 |
| --- | --- | --- | --- | --- | --- |
| TWOLEVEL-OLDPOD-V4 / 0 | 0.99858818727 | 0.999092817197 | 0.0333030546374 | 0.0654894807753 | False |
| TWOLEVEL-OLDPOD-V4 / 10 | 0.949242609663 | 0.971634245187 | 0.000954707150083 | 0.480383202996 | False |
| TWOLEVEL-OLDPOD-V4 / 11 | 0.905073739084 | 0.97721673465 | 0.000949297617596 | 0.235770374702 | False |
| TWOLEVEL-ERROR-V4 / 0 | 0.999863649936 | 0.99961809965 | 0.0256415022841 | 0.0849928945237 | False |
| TWOLEVEL-ERROR-V4 / 10 | 0.937175812499 | 0.957474274981 | 0.000927512266936 | 0.334601298612 | False |
| TWOLEVEL-ERROR-V4 / 11 | 0.901084822725 | 0.963534624076 | 0.000946698188098 | 0.203706802155 | False |

六次均到256步/KSP reason−3，失败是原A4/port未达1e-10，不是接口或代数失败。恢复、identity、slave和finite通过；reported/显式Schur、native映射及固定port尺度分别保存。相对port变化不能替代固定Schur与原A4判据。原V1–V3负结果不变。固定局部B没有改变，新全局空间/组合仍未突破平台，部分RHS下降不构成严格收敛。

| 阶段 | 真实 clean source SHA | 现场CPU / math线程 | 整树wall s | 同时整树RSS峰 B | own swap B |
| --- | --- | --- | --- | --- | --- |
| V4-P0 | `8b792d78b06903ef874fbcf14fa06d951ae9c2ff` | 0 / 1 | 102.422415896 | 927145984 | 0 |
| V4-P1 | `8b792d78b06903ef874fbcf14fa06d951ae9c2ff` | 0 / 1 | 449.207465587 | 979628032 | 0 |
| V4-P2-ERROR | `5691d79abe87d3582ede5bbaf8369c5487e7c392` | 0 / 1 | 114.887444319 | 1128828928 | 0 |
| V4-P2-OLDPOD | `5691d79abe87d3582ede5bbaf8369c5487e7c392` | 0 / 1 | 112.648601859 | 1112412160 | 0 |
| V4-P3-OLDPOD | `5691d79abe87d3582ede5bbaf8369c5487e7c392` | 0 / 1 | 377.740587706 | 1040433152 | 0 |
| V4-P3-ERROR | `5691d79abe87d3582ede5bbaf8369c5487e7c392` | 0 / 1 | 377.101768567 | 1040003072 | 0 |

每run均以实际clean source绑定dat、原CSR、physical/mode和artifact SHA。P0/P1使用8b792d78…，P2/P3使用5691d79…，最终文档HEAD不冒充run source。P4隐私隔离的局部修复在未生成fresh数组时完成，数值公式/选择/预算不变，已过targeted tests；没有为停滞增加参数重试。

正式wall合计1534.00828393s，RSS峰取各同时整树峰的最大值，不相加。实际六阶段CPU0是每次现场审计的结果，MPI1、三BLAS线程1、nice10/idle I/O、own lock和独立cache。hard16GiB/warn12GiB、own swap0，保留系统10%或128GiB＋邻增长128GiB余量；无cgroup委派，诚实采用0.5s整树采样停止。没有GPU上下文/训练或邻任务变更。未观察到持续资源压力；邻短phase没有当前可比耗时，不能量化影响或证明零干扰。

最新用户受控共享授权仅覆盖Task042原§2.3已有heavy禁令与全机独占锁；精度、资源、provenance和停止条件保持，不代表F0正式review。所有成本标shared-workstation，performance inconclusive；没有把V3审核时间相减当新加速。新teacher/NN/GPU、P4 generation/qualification、F5/p6、短波、official RTA/A_volume/field/channels均not_run，其中P4因P3未解锁，F5本批无授权。既存seed420620五非零family变体集合保持未消费。

完整[两层结果与通俗说明](outcomes/two_level_global_error_v4.md)、[数据与快照](outcomes/records/training_snapshot_manifest_v4.json)、[空间/谱/恒等式](outcomes/records/coarse_space_algebra_v4.json)、[独立Gate](outcomes/records/gate_decisions_v4.json)、[新终测状态](outcomes/records/fresh_qualification_v4.json)、[每步历史](outcomes/records/two_level_history_v4.csv)、[全过程run/cost索引](outcomes/records/run_index_v4.json)、[测试](outcomes/test_summary.md)。原Review已补做实际GitHub7表/5公式渲染检查，无明显问题，review原文未改。项目进展与模型总账同步本Task042批次；仅推送原执行分支，停止等待ChatGPT review，不merge master或其他分支。
