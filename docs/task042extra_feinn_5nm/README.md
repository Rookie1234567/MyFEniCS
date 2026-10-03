# Task42extra：NN-Lab-V2 / 5 nm compatible FEINN

本目录对应独立支线，不是原 Task042 的新版本或旧粗逆续跑。当前裁决以 [Review V15](review_report_v15.md) 为准：`FEINN_MAIN_SOLVER_ON_HOLD` / `NO_VERIFIED_NN_INCREMENT`。保存向量和背景转换诊断已接受，尚无解准原方程的无标签网络，也无同精度、完整成本下的神经增益。网络全局表达极限仍未知，不把有限负结果推广为所有神经方法无效。

当前交接见 [Response V16](response_v16.md)；本轮原记录复验见 [checker与两方向归因](outcomes/checker_integrity_v16.md)，原数组诊断为 [Response V15](response_v15.md) / [共同下降专题](outcomes/common_descent_v15.md)，详细正负结果和历史导航见 [summary](outcomes/summary.md)。[task.md](task.md) 保留首轮冻结合同，[AGENTS.md](AGENTS.md) 为目录规则；其初建状态不是当前待运行计划。

| 项目 | 冻结身份 / 当前状态 |
|---|---|
| 远程仓库 | Rookie1234567/MyFEniCS |
| 执行分支 | `task42extra_feinn_5nm` |
| 冻结base | `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`，来自 `task42_neural_coarse_inverse` |
| canonical / 工作树根 | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` / 已登记 `/home/fenics/Projects/NN-Lab-V2` |
| 首轮问题 | 5 nm、Si/air、非可分三维缺口、双Floquet/Fourier-DtN；384 hex/p3小型资格试验 |
| 方法 | 坐标网络→完整Nédélec边/面/内部矩→原native全FE残差；对比欧氏与Riesz对偶loss |
| 与Task042区别 | 不仅训练trace、不求p4逆；端口仅准确解析消元；内部FE系数由网络矩产生 |
| 辅助成本 | 小型DUAL路线允许准确稀疏Gram因子，必须全程记账；不称无全局因子生产方案 |
| 执行端 | 工作站原生Linux；独立worktree/环境/cache；已有项目只读，不改其运行 |
| 本轮资源与预算 | 本轮保存记录checker/两方向归因完整≤7200s；1空闲物理核、线程1、轻任务整树≤2GiB、自身swap/OOC0；系统余量及至少384GiB邻增长预留不变 |
| 当前结果 | `FEINN_MAIN_SOLVER_ON_HOLD` / `NO_VERIFIED_NN_INCREMENT`；本轮完整记录复验和两方向归因已完成，暂停数值探索，生产初值未批准 |
| 原数组分析源码 / 新checker源码 | `99f2968be8d715a6f2e6985f5b032c53ca505950` / `a14dd6187336c866f0a327760f10c4ece0140a8d`；[V16 run index](outcomes/records/run_index_v16.json)保留旧C1/数值身份，不以文档HEAD冒充source |
| 最终目标 | 原尺寸50×25×140nm、Si线宽17nm/高120nm、λ=0.7nm、完整三维FE；十进制2,000,000,000,000B整机、swap0、172800s完整流程；仍未运行/未资格化 |

## 冻结结论与最小证据

下表只引用已有M5/p3记录：5nm、384hex、31968独立复FE、40端口。原残差衡量场代回方程的不平衡；场误差衡量与同p3准确参考的距离，越低越好。原残差门1e-6、total/scattered E/H/curl及完整复通道门1e-4、功率/能量门1e-5、逐级功率门1e-6均未放宽，未过残差门的功率只作诊断。

| 冻结对象 | 已有结果 / 状态及单位 | 证据与边界 |
| --- | --- | --- |
| 无标签PDE求解 / 神经增量 | 无合格解 / NO_VERIFIED_NN_INCREMENT | [Review V13](review_report_v13.md)；缓存加速、监督拟合和确定性比较不算神经求解增益 |
| M3600较好中间态 / Mfinal退化 | 原native 0.885852/0.846542；散射E相对误差0.0933003/0.122945，无量纲，均未过原门 | [保存场及完整物理量](outcomes/records/saved_physics_reuse_v12.json)；两态和实际退化段均保留，不按参考误差改选终态 |
| 有限局部目标方向分歧 | 保存向量分类闭环；网络全局表达极限UNKNOWN | [checker](outcomes/records/independent_checker_v13.json)、[八个见证](outcomes/records/witness_norm_reuse_v13.json)；不是完整参数空间或全局条件数结论 |
| D0成本预检 / D1完成器 | COST_VETO_CONFIRMED / NOT_RUN_COST_VETO | [状态映射](outcomes/records/status_mapping_v13.json)、[完整成本否决](outcomes/records/auxiliary_cost_v12.json)；未运行完成器不写成数值失败 |
| V13同总场背景转换 | p3参考的p4相对残差3.55236→5.20557；2次A4，原分母不改 | [背景原记录](outcomes/records/background_conversion_v13.json)；未消除基线，不改变同p3失败，不新建G4或参考 |
| 未完成积分 / 遗失历史状态 | 新E/curl交叉及邻层积分NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE；V2/V6 optimizer/RNG NOT_RETAINED | [V13专题](outcomes/evidence_closure_v13.md)及[旧回执](response_v13.md)；不补造或重演历史 |
| 公式渲染 / 历史失败 | 审阅已确认最终专题字节的parser与实际GitHub渲染PASS；首次失败及资源未复验记录保留 | [Review V13收据](outcomes/records/review_v13_evidence_audit.json)、[原失败记录](outcomes/records/render_check_v13.json)；不把后续PASS追改成旧检查通过 |
| 原尺寸0.7nm与生产 / 合并 | NOT_RUN / NOT_QUALIFIED；无production numerical/core晋级、无merge授权 | [依赖组manifest](outcomes/records/selective_merge_manifest_v13.json)；本地raw可读不等于跨机持久恢复资格 |

证据保留原路径和hash绑定，大场、矩阵、checkpoint与完整轨迹留ignored目录。归档只核对最小入口及现有收据的可访问性，缺失时报告具体未验证项；不全量重验、清理或迁移历史。

## 当前接续边界

Review V15要求补齐原批次checker，现已完整验收8唯一配置/32点/4候选与实际账本。原共同下降数值未重算优化；PDE8两态微弱能量下降与native增加、Mfinal ALL16参考oracle和M3600界宽UNKNOWN保留。仅沿两条冻结PDE8方向分析原残差一阶/二阶项，均为方向本身冲突，没有新步或前向。详见[独立五层决策](outcomes/records/independent_checker_v16.json)。主线Gx784/AUTO是已分配而非本支已产生的结果；dot实际C1/持久证据仍待资格，本支不复制工作。

以后只有满足[Review V13 P2](review_report_v13.md)的全部条件——新具体假设、无参考标签的单一干预、可区分解释的保存数据预检、同成本非NN对照、完整必要成本、原全部精度门和有限停止计划——才提出重启审阅。它不是本轮自动分支。只在精确执行分支提交/推送，完成后等待review，不合并master。

## 历史：首次空目录建立（已完成）

2026-09-29首次启动时，用户只创建空目录，Codex按task §2核验canonical并登记linked worktree、建立独立环境；本目录本身就是repo根，没有嵌套MyFEniCS。原E0–E5和response_v1为首轮历史，随后经历正式review闭环，不能再按空目录重建或重跑。

当前已有仓库、环境和保存证据。再次接续先核对既有作业、锁、branch/HEAD/工作树和最新review，仅安全同步本分支；不clone、不新建分支、不reset/stash/覆盖已有工作，不改旧NN-Lab或其他项目。
