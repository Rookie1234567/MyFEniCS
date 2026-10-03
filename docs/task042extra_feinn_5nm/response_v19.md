# Response V19：落实 Review V18，结束当前 M5 优化循环

[Review V18](review_report_v18.md) 的 P0 已落实到当前 README、summary、进度和模型总账。科研证据接受但流程限定保留；维持 **FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED**。本轮没有新数值结果，完成一次交接后停止。P1没有真实接收输入包，`NOT_REQUESTED_NO_RUN`；P2重启条件未满足，不构成数值许可。不为确认读过报告再要求一个review编号。

## 输入、当前范围及实际修改

| 对象 / 数据身份 | 实际核对及处理 |
| --- | --- |
| 精确分支 / 发布HEAD | task42extra_feinn_5nm / a88c1be95e1b50760a69e0530c85ad78408a632e；显式tracking同SHA、0/0、起始clean |
| 冻结base / canonical | fbac3d8777fcfd897d93b898cb9f460f79ddd6ff / /home/fenics/Projects/Maxwell3D-Lab/task-repository.git；已登记NN-Lab-V2、祖先核对通过 |
| 审阅输入 / 数值来源，复用 | 原交付c5d320e055e2128e8ba65dda4cc176fe2c013ffe；A33fe1bc05c89eeef50de1fb44ae64cc96e868852，B b42f042064fcef431e2e7d64eddcbfd43b2bf65a，C及检查/恢复ca7ad5d51fc6e3d10b635f7ca795092fabfd7ccb。新的文档HEAD不替代运行source |
| P0，文档/元数据 | README当前执行范围、summary页首导航、本任务进度/模型条目、测试/changed_files及本回执；[compact收据](outcomes/records/closeout_receipt_v19.json)绑定输入、资源及检查范围 |
| 历史，未改 | task/review、原V18结果和旧收据、V1–V17原记录、M3600较好态/Mfinal最终退化、UNKNOWN/NOT_RETAINED、全部失败和费用；完整旧summary正文保留 |
| 条件P1 / P2，not_run | 无接收方及固定数据包，不运行辅助；无新机制/严格无标签及成本方案，不重启研究 |

先只读确认本任务无活跃计算、numerical.lock空闲，再按精确refspec安全fetch/fast-forward，未改共享Git配置、环境或其他worktree。结构只复核路径与提交差量，复用审阅全库索引；不把它称为逐行语义审阅，也不重复28模块静态清单。数值源码按未变hash复用，不加载大场、网络或FE库。

## 已接受证据和停止投资的依据

下表均是已保存M5/p3数据的审阅结论，非本轮新测。M5仍是5nm、384hex、31968独立复FE、40端口和8966实参数。N/R/F是原残差平方、G加权残差能量、G场误差能量相对各自原点的比值，原点为1；这里的R不是反射率。G场误差同时计入电场和curl，不能替代完整场/通道精度。

| 已有诊断 / 同原p3参考 | M3600，中期较好态 | Mfinal，最终退化态 | 原门及解释 |
| --- | ---: | ---: | --- |
| A线性N / F | 0.993833582643 / 0.996039955334 | 0.980847213997 / 0.998407317822 | 方向可行；最优界宽3.891e-6/1.608e-7高于1e-7，两态UNKNOWN |
| C实际native原值→新值 | 0.885852183253→0.883116256995 | 0.846541904928→0.838398187887 | 均远高于严格1e-6，不是有效解 |
| C实际R−1 | 1.007948258e-7 | 1.790179320e-7 | 均超过1e-8，不增门FAIL；不缩步或留余量重跑 |
| 实际网络相对线性场的额外G改善占总改善 | 0.07695% | 0.42375% | 分母为实际网络本次总G改善；主要改善来自线性选向，不等于完整成本NN收益 |
| 旧散射E / curl相对误差 | 0.0933002764708 / 0.0935415151962 | 0.122944519716 / 0.123039105854 | 较好时刻与最终退化均保留；原场门1e-4未过 |

[审阅保存向量分解](outcomes/records/review_v18_evidence_audit.json) 还显示实际网络相对线性场的N变化一态负、一态正。不能把当前主要线性收益计作真正神经增量，也不能由有限负结果断言全部神经表示不可能。

B原保存场积分完成此前缺失的归因：E误差能量增加0.155486609849，其中正交叉项0.119581031358占76.91%；scaled-curl占76.81%。交叉项为正表示更新较多地扩大原有误差。周期和界面邻层体积覆盖50%/68.75%，平均集中度约1；较宽且重叠的区域不能排除薄层、个别模式或参数效率问题。checker只独立重算已保存积分的代数关系，没有第二套FE积分器。本轮不重算这些量，见[原专题](outcomes/native_constraint_and_field_attribution_v18.md)。

## 保留的流程、成本和用途边界

| 项目 | 本次落实的准确边界 |
| --- | --- |
| 原科研交付 | ACCEPTED_WITH_PROCESS_QUALIFICATIONS；初始五项修复另加正式保存bug、资源拒绝到再准入映射未完整闭合，不追认无条件流程PASS |
| 原费用 | 旧失联3284s、失败/重放/Gram费用及未知尾段保留。V18观察点加启动额5706.080003495095s、加300s尾段额度上界6006.080003495095s；不是精确项目总成本 |
| D0 / D1 | COST_VETO / NOT_RUN_COST_VETO；必要前缀≥15758.7400951s对传统完整672.462895285s，不运行完成器或改写未运行状态 |
| 可复用checker限制 | A verify未自行绑定原theta半径与原始列/rcond/秩；本次四半径已由审阅独立验证。无实际复用需要，本轮不修代码、不重跑A/B/C |
| 原渲染证据 | Review V18最终字节公式实际通过，审阅另补齐原专题两区域表右侧；复用hash-bound收据，旧失败/执行端部分视图不追改。新页的本地与发布后实际视图分开记账 |
| 合并/生产用途 | 无production numerical/core晋级，无主求解器或生产初值资格，无master合并授权；原六组[manifest](outcomes/records/selective_merge_manifest_v18.json)继续有效 |

pure身份检查已通过：发布文档、task/Response V18及16份未变源码hash、4669个tracked路径和提交差量核对，监督3.00519637496s，采样同时树峰57,675,776B、自身swap0、已清场。改变页parser/链接/JSON与自动历史字节检查在worker启动前因无空闲物理核被拒绝；一次实测新窗口后唯一再准入仍拒绝，故 **NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE**。不绕过准入直接运行脚本，不继续等待或启动浏览器；新页视觉同为资源未运行，不能标文档Gate全PASS。Git差量人工核对及`git diff --check`单列，不替代parser/视觉。实际拒绝、观测和检查范围见[P0收据](outcomes/records/closeout_receipt_v19.json)。未变源码旧52 targeted/Ruff/compileall证据复用，没有新增pytest、full pytest、CI或PDE通过声明。

完整P0时钟从2026-10-03 13:40:54 UTC首次明确观察计，另保守计启动60s，总限3600s、最后600s收口。轻任务由既有资源监督运行，现场选空闲物理核和SMT、线程1、warn1.75/hard2GiB、自身swap/OOC0，保留系统max(128GiB,有效整机10%)、384GiB邻增长及50GiB磁盘。阶段采样RSS与完整父墙钟分开，嵌套worker不重复计费；封存观察点及未测回复尾段分别记账，不伪造精确旧总账。

## 交接与最终目标

仅引用Review V18冻结的并行证据：主线 `2374d0d556aed7a415202757daa2b94b76ad399b` 控制链已补检，Gx784正式执行尚未开始；dot `3c7458fad7c002babac4e634be4788b664be9ee5` 是合成分块投影证据，真实FE/紧凑存储/后端资格由它完成。本轮不更新其他分支，不复制求解器、存储验证或消费者，不作跨模型排名。

最终仍是原50×25×140nm、Si17/120nm、λ0.7nm完整三维FE、十进制2,000,000,000,000B整机、自身swap0和172800s完整流程。原native/增广/独立残差1e-6、MPC1e-10、场/复通道1e-4、功率/能量1e-5、逐级功率1e-6及求积门不变。将来须同时给出实质新机制、严格无标签同成本对照和≥20%净收益的可检验成本预案，解释原尺寸Gram/插值/端口生命周期，才值得提出新的完整批次；P2不是自动授权。

本次实际推进是把已完成归因变成明确停止决策，释放计算配额给有λ0.7合同的并行任务。资源门保留新文档检查未验证项，不取消已完成状态交接，也不要求为确认收信另发review。只提交推送本分支，核对最终完整HEAD、显式tracking/ahead-behind、clean及自身清场，再向审阅窗口发送一次完成通知并停止。
