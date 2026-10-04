# Task42extra：NN-Lab-V2 / FEINN研究与0.7nm有限元表示支撑

当前执行权威为 [Review V21](review_report_v21.md)，整批结果见 [Response V22](response_v22.md)。hi/lo的给定算子算术与解析面块/作用资格通过，实际原点物理投影仍FAIL；保存c的新算子残差触发E3/E4各一次同配置研究修正，独立完整比较为 STRICT_FINITE_P_FIELD_MODE_FAIL / REFERENCE_LIMITED。原尺寸32060-key冻结manifest本体缺失，交最小算法接口而不重建AUTO；无NN训练，FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED，无production/merge approval。

当前入口：[解析面/可靠输出专题](outcomes/reliable_affine_ports_v22.md)、[运行](outcomes/records/run_index_v22.json)、[checker](outcomes/records/independent_checker_v22.json)、[费用](outcomes/records/resource_costs_v22.json)、[最小接入包](outcomes/records/minimal_integration_v22.json)、[summary](outcomes/summary.md)。旧V21三种single-array失败、普通p6旧q15负项、中期较好/终态退化与全部历史保留；确定性修正不算神经收益。

| 项目 | 冻结身份 / 当前状态 |
|---|---|
| 远程仓库 | Rookie1234567/MyFEniCS |
| 执行分支 | `task42extra_feinn_5nm` |
| 冻结base | `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`，来自 `task42_neural_coarse_inverse` |
| canonical / 工作树根 | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` / 已登记 `/home/fenics/Projects/NN-Lab-V2` |
| 首轮问题 | 5 nm、Si/air、非可分三维缺口、双Floquet/Fourier-DtN；384 hex/p3小型资格试验 |
| 历史首轮方法 | 坐标网络→完整Nédélec边/面/内部矩→原native全FE残差；对比欧氏与Riesz对偶loss |
| V22实际方法 | 双分量总场和解析面Fourier矩的显式组件；两次同G0/p/κ修正与保存场独立比较，NN/Gram因子为0 |
| 历史与Task042区别 | 不仅训练trace、不求p4逆；端口仅准确解析消元；历史NN的内部FE系数由完整矩产生；本轮无网络 |
| 历史Gram辅助成本 | 小型DUAL路线允许准确稀疏Gram因子，必须全程记账；不称无全局因子生产方案 |
| 执行端 | 工作站原生Linux；独立worktree/环境/cache；已有项目只读，不改其运行 |
| 本轮资源与预算 | Review V21完整43200s，最后留1800s；单空闲物理核/线程1、CPU-only/MPI1；pure2GiB/FEwarn12-hard16GiB、自身swap/OOC0；系统max(128GiB,有效整机10%)+384GiB邻增长。批次收口，不能自动再次运行 |
| 当前结果 | 给定D/H算术通过；实际原点物理投影仍失败。两次修正native约6.29e-11/2.96e-10，散射场/完整模式仍超门；原尺寸manifest缺失，严格参考受限，NN暂停和D0/D1不变 |
| 本轮检查边界 | 受影响pure fixtures、真实保存场MPC/损坏检查、空气Poynting、Ruff/compileall/局部文档与一次纯数组checker；full pytest/CI未运行，旧失败保留 |
| 历史V16数组分析源码 / checker源码 | `99f2968be8d715a6f2e6985f5b032c53ca505950` / `a14dd6187336c866f0a327760f10c4ece0140a8d`；[V16 run index](outcomes/records/run_index_v16.json)保留旧C1/数值身份 |
| V22实际source | 修正/独立FE比较 `c3844846435764cd0ca7a4351a1ba8374373b6ae`；最小接入/最终pure checker `0a49003c9af140144aaf07f48f0c81e1490b5500`；其余阶段见新run index，不以文档HEAD冒充source |
| 最终目标 | 原尺寸50×25×140nm、Si线宽17nm/高120nm、λ=0.7nm、完整三维FE；十进制2,000,000,000,000B整机、swap0、172800s完整流程；仍未运行/未资格化 |

## 历史M5冻结结论与最小证据

下表只引用已有M5/p3记录：5nm、384hex、31968独立复FE、40端口。原残差衡量场代回方程的不平衡；场误差衡量与同p3准确参考的距离，越低越好。原残差门1e-6、total/scattered E/H/curl及完整复通道门1e-4、功率/能量门1e-5、逐级功率门1e-6均未放宽，未过残差门的功率只作诊断。

| 冻结对象 | 已有结果 / 状态及单位 | 证据与边界 |
| --- | --- | --- |
| 无标签PDE求解 / 神经增量 | 无合格解 / NO_VERIFIED_NN_INCREMENT | [Review V18](review_report_v18.md)；额外G改善占总改善仅0.07695%/0.42375%，缓存、监督拟合及局部比较不算完整成本神经增益 |
| M3600较好中间态 / Mfinal退化 | 原native 0.885852/0.846542；散射E相对误差0.0933003/0.122945，无量纲，均未过原门 | [保存场及完整物理量](outcomes/records/saved_physics_reuse_v12.json)；两态和实际退化段均保留，不按参考误差改选终态 |
| 有限局部目标方向分歧 | 保存向量分类闭环；网络全局表达极限UNKNOWN | [checker](outcomes/records/independent_checker_v13.json)、[八个见证](outcomes/records/witness_norm_reuse_v13.json)；不是完整参数空间或全局条件数结论 |
| D0成本预检 / D1完成器 | COST_VETO_CONFIRMED / NOT_RUN_COST_VETO | [状态映射](outcomes/records/status_mapping_v13.json)、[完整成本否决](outcomes/records/auxiliary_cost_v12.json)；未运行完成器不写成数值失败 |
| V13同总场背景转换 | p3参考的p4相对残差3.55236→5.20557；2次A4，原分母不改 | [背景原记录](outcomes/records/background_conversion_v13.json)；未消除基线，不改变同p3失败，不新建G4或参考 |
| 历史积分未运行 / 本次接续 | 旧NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE保留；V18新索引完成E/curl交叉与四区域积分；V2/V6 optimizer/RNG仍NOT_RETAINED | [V18积分](outcomes/records/saved_integral_results_v18.json)、[旧回执](response_v13.md)；不改旧index或重造历史 |
| 公式渲染 / 历史失败 | Review V18最终公式实际渲染通过；审阅另补齐V18两张区域表右侧，范围闭合；旧执行端失败/部分视图原收据不改 | [V18审阅收据](outcomes/records/review_v18_evidence_audit.json)、[旧V18记录](outcomes/records/render_check_v18.json)、[V13原失败](outcomes/records/render_check_v13.json)；不批量重渲染历史 |
| 原尺寸0.7nm与生产 / 合并 | NOT_RUN / NOT_QUALIFIED；无production numerical/core晋级、无merge授权 | [依赖组manifest](outcomes/records/selective_merge_manifest_v13.json)；本地raw可读不等于跨机持久恢复资格 |

证据保留原路径和hash绑定，大场、矩阵、checkpoint与完整轨迹留ignored目录。归档只核对最小入口及现有收据的可访问性，缺失时报告具体未验证项；不全量重验、清理或迁移历史。

## 历史V19交接边界（不再作为当前授权）

[Review V17](review_report_v17.md) 的 A/B/C 已完成，之后 [Review V18 §6](review_report_v18.md) 只准一次 P0 状态落实，当前已按本范围交接。A 的最优性UNKNOWN、旧V15/V16负结果、C数值超门均保留。B的约77%正交叉项支持“更新扩大既有误差”，较宽且重叠的区域没有强平均集中，不排除薄层或个别模式。初始五项修复另加正式保存bug及资源再准入对应不完整的流程限定不追认为无条件PASS；[运行索引](outcomes/records/run_index_v18.json)、[资源账](outcomes/records/resource_costs_v18.json)、[依赖组](outcomes/records/selective_merge_manifest_v18.json)不改。

并行线仅引用 Review V18 的冻结信息：主线 `2374d0d556aed7a415202757daa2b94b76ad399b` 的控制链补检已过，Gx784正式执行尚未开始，由该线按自己的合同推进；AUTO32060库存不是成功解。dot `3c7458fad7c002babac4e634be4788b664be9ee5` 新增合成精确分块投影，真实FE/紧凑存储/后端资格仍待该线完成。本轮未同步或修改这些分支；不同模型/精度口径不可作求解器或NN排名。

P1需要真实接收方、固定hash-bound旧/新场及参考、逐项物理身份映射和现有checker未回答的问题；当前无包，`NOT_REQUESTED_NO_RUN`，不造消费者或再做V17静态清单。A checker尚未自行绑定原theta半径和原始列/rcond/秩；本次四半径已由审阅独立核实，结果有效，今后实际复用前须最小补拒绝检查，本轮无复用需要故不改代码。

P2只是将来重新研究的条件，不是本轮数值授权：须有指向原尺寸λ0.7nm的实质新机制、无标签严格对照及含特征/训练/辅助分解/恢复/验算的完整成本预案，能解释M5精度差距、≥20%同成本优势及2TB/48h生命周期。条件不具备，暂停就是正式终点。本批一次提交推送和完成通知后结束，不为确认收信再要求review，不合并master。

## 历史：首次空目录建立（已完成）

2026-09-29首次启动时，用户只创建空目录，Codex按task §2核验canonical并登记linked worktree、建立独立环境；本目录本身就是repo根，没有嵌套MyFEniCS。原E0–E5和response_v1为首轮历史，随后经历正式review闭环，不能再按空目录重建或重跑。

当前已有仓库、环境和保存证据。再次接续先核对既有作业、锁、branch/HEAD/工作树和最新review，仅安全同步本分支；不clone、不新建分支、不reset/stash/覆盖已有工作，不改旧NN-Lab或其他项目。

V20补充当前检查：8处受影响页本地parser/716行原数组CSV/历史保留及20相关pure文档合同通过；旧全库40任务测试存在修改前相同失败，新关键页实际视觉另记[呈现记录](outcomes/records/render_check_v20.json)，不追改历史未运行项。
