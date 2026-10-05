# 改动范围与合并边界

当前实现改动从发布提交起核对；最后的response/outcomes和总账追加另在交付commit中。实现未修改旧Task042历史、任务书或review。正式source hashes见[run index](records/run_index_v1.json)。

| 依赖组 | 文件/用途 | 审阅边界 |
| --- | --- | --- |
| production dispatch | scripts/run_case.py；src/io/feinn_pilot.py | 明确opt-in，原默认solver数学与旧Task042函数含义不改 |
| 完整数值核 | src/solvers/feinn_native.py、feinn_interpolation.py、feinn_torch.py、feinn_fem.py | 完整边/面/内部矩、原A/Aᴴ及准确端口；不是trace恢复 |
| 辅助Riesz | src/solvers/feinn_riesz.py、feinn_cholmod.c | RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR，非无全局因子/可扩展PC结论 |
| 研究优化/验收 | feinn_validation.py、feinn_optimization.py、feinn_reference.py | 统一三路线预算、事务checkpoint、盲准确reference及有条件p4 |
| 可复用task编排 | src/runners/feinn_resources.py、feinn_workflow.py；scripts/activate_task42extra.sh、supervise_task42extra.py | 自有lock/env/cache/CPU-only和whole-tree guard；不改邻任务 |
| 检查工具 | benchmarks/check_feinn_pilot.py及E5容量/render辅助 | 只读或task-local轻量证据工具，不包含新PDE数学 |
| 输入/targeted tests | input/task042extra_feinn_5nm；src/test/test_feinn_*.py | 固定M5/seed/loss/G/近零阈值；只测必要合同 |
| 文档与证据 | docs/task042extra_feinn_5nm/outcomes、response_v1；progress/registry新节 | 所有正/负/未运行保留；旧历史逐字保留 |
| do-not-merge | venvs、raw矩阵/场/history/checkpoints、cache、Firefox profile | ignored，大文件不进入Git，无production资格或master merge |

从发布提交到实现HEAD的文件名单（路径用于审查，不把后续文档HEAD当数值source）：

```text
benchmarks/check_feinn_pilot.py
benchmarks/derive_task42extra_capacity.py
benchmarks/render_task42extra.py
docs/task042extra_feinn_5nm/outcomes/environment_and_isolation.md
docs/task042extra_feinn_5nm/outcomes/method_and_paper_mapping.md
docs/task042extra_feinn_5nm/outcomes/records/design_v1.json
docs/task042extra_feinn_5nm/outcomes/summary.md
input/task042extra_feinn_5nm/design_v1.json
input/task042extra_feinn_5nm/e1_fe.dat
input/task042extra_feinn_5nm/e1_grad.dat
input/task042extra_feinn_5nm/e1_smoke.dat
input/task042extra_feinn_5nm/e3_reference.dat
input/task042extra_feinn_5nm/e4_p4.dat
input/task042extra_feinn_5nm/feinn_dual.dat
input/task042extra_feinn_5nm/feinn_euc.dat
input/task042extra_feinn_5nm/free_fe_dual.dat
scripts/activate_task42extra.sh
scripts/run_case.py
scripts/supervise_task42extra.py
src/io/feinn_pilot.py
src/runners/feinn_resources.py
src/runners/feinn_workflow.py
src/solvers/feinn_cholmod.c
src/solvers/feinn_fem.py
src/solvers/feinn_interpolation.py
src/solvers/feinn_native.py
src/solvers/feinn_optimization.py
src/solvers/feinn_reference.py
src/solvers/feinn_riesz.py
src/solvers/feinn_torch.py
src/solvers/feinn_validation.py
src/test/test_feinn_full_algebra.py
src/test/test_feinn_riesz_ml.py
src/test/test_feinn_transaction_ml.py
```

最终diff还包含本任务compact records和总结、总账追加；它们不改变三条候选数学。没有全仓清理、amend、reset、force push或跨支线merge。本轮只推执行分支等待review，合并任何组仍需review。

## Review V1 后续 V2 增量与选择性合并边界

| 依赖组 | V2增量 | 数值/审阅边界 |
| --- | --- | --- |
| research-only scaling core | `src/solvers/feinn_scaling.py`、`feinn_optimization.py` | 明确opt-in `c=Dy`、`g_y=D* g_c`；原A/f/G/d_G/loss及V1默认路不改，非production资格 |
| compare-only验证 | `src/solvers/feinn_reference.py` | 已冻结候选恢复实际c，复用V1同p3准确参考；无新MUMPS分解/求解 |
| 编排/输入 | `src/io/feinn_pilot.py`、`src/runners/feinn_workflow.py`、`input/task042extra_feinn_5nm/v2_*.dat` | D0/D1/唯一候选/D3各自one-run stage/index；task自有锁/资源监督，不改其他项目 |
| 定向测试/checker | `src/test/test_feinn_scaling_ml.py`、`benchmarks/check_task42extra_v2.py`、局部Markdown检查器、`benchmarks/finalize_task42extra_render_v2.py` | 不以status字符串替代复向量/功率/原残差重算；测试9项+正式D1；渲染复核精确blob/截图hash |
| compact证据/文档 | `response_v2.md`、`outcomes/scaling_diagnostic_v2.md`、V2 records、summary/progress/registry/test/本页；`benchmarks/render_task42extra.py`加载策略 | 旧V1全文和负结果保留；准确运行source绑定在run index；加载策略只影响辅助浏览器 |
| 明示授权排版修正 | `task.md` §5.4唯一 `\operatorname{Re}`→`\mathrm{Re}` | 只改宏、数学不变；旧/新blob及GitHub渲染见Response V2 |
| do-not-merge | ignored原数组/场/history/checkpoint、浏览器profile/cache | 研究数据本机保留；新FREE路线未获solver/production资格，不允许据此合并master |

V2实现提交 `19c725efd27ae5daedba8e77d2ad98375711bb71` 绑定D0/D1/D2正式阶段；局部FE导入修复提交 `bfff1458a389b2c4a4d57112cc771bb33847c20a` 绑定完成的D3。后续证据与文档HEAD不替代这两个实际source。新一行task公式修改已由review明确授权，不推广为一般修改任务书权限。

## Review V2 后续 V3 文件级边界

| 依赖组 | V3 文件 / source | 数值行为与审查边界 |
| --- | --- | --- |
| research-only P0 | `src/solvers/feinn_error_geometry.py`；实现 `d9e5a7d00a1cac82390b058384e0cd9193b472d4` | 只读既存四态和V1参考；一次 Gram 因子、有限 A/Aᴴ/Gsolve，原算子和旧结果不改 |
| research-only P1 | `src/solvers/feinn_reference_fit.py`、`src/test/test_feinn_reference_fit_ml.py`；同实现source | 明确参考暴露的完整矩 G 场拟合；只用原架构/初始化/Adam500＋LBFGS，参数-only checkpoint，不设生产默认 |
| 中断后留存态/P2 compare-only | `src/solvers/feinn_reference.py`、`feinn_reference_fit.py`、workflow、`v3_retained_snapshot.dat`；复验source `7c2bffe4dff7b2c9a918ade6ec02a45e168b4890` | 唯一训练缺final，只登记Adam500字节哈希与参数对应完整c，独立q30和原FE场/端口/功率；参考不再MUMPS求解；监督结果不得自动升级为official |
| one-run/资源编排 | `src/io/feinn_pilot.py`、`src/runners/feinn_workflow.py`、`input/task042extra_feinn_5nm/v3_*.dat` | 新唯一stage/index和V3 4h/原16h预算；clean source、CPU-only/MPI1/自有锁与整树采样监督 |
| checker/文档 | `benchmarks/check_task42extra_v3.py`、`check_task42extra_docs_v3.py`、`finalize_task42extra_render_v3.py`；本目录V3 compact records/response/summary、两份总账追加 | 从原c、G、复E/H、全40复通道与功率重算；旧V1/V2文档和负结果保留，GitHub新review及新增文档实际渲染单列 |
| do-not-merge | `.venv*`、`tmp/`、`results/`、`benchmarks/artifacts/task42extra/` | 忽略的大数组、场、checkpoints、浏览器截图/profile；研究权重不得用于旧路线、Task042或0.7nm |

本批新路线即使拟合成功也属参考已暴露研究，不是 production numerical/core、ordinary default 或目标尺寸资格。最终source、测试和fresh PDE证据以[run index V3](records/run_index_v3.json)与[Response V3](../response_v3.md)为准；本轮没有fresh PDE求解，只有原M5固定数据上的监督表示及独立同离散复验。

## Review V3 后续 V4 文件级边界

| 依赖组 / 建议审阅顺序 | 本轮文件与用途 | 数值行为 / 依赖 / 验证 |
| --- | --- | --- |
| production numerical/core | 无新生产默认或Maxwell数学 | 原A/G/矩/材料/几何不变；无fresh无标签PDE资格，不建议生产晋级 |
| reusable runner/watchdog，第1组 | src/solvers/optimization_checkpoint.py；src/runners/guarded_exec.py、durable_terminal.py；scripts/launch_task42extra_durable.py | 同步完整optimizer事务和原子检查点；独立tmux承载完整launcher；父死亡保护；9/11小tests及4类自身进程故障证据。组件资格限本任务所测路径 |
| research-only，第2组依赖第1组 | src/solvers/feinn_boundary_replay.py；src/io/feinn_pilot.py；4个V4 one-run dat；src/runners/feinn_workflow.py | 特定Adam500→fresh L-BFGS适配，预算/索引/标签保护；R0 source538c632、R1唯一负结果及R2独立audit。C2时间留白修正仅targeted，没有第二次正式证据 |
| research-only复验，第3组 | src/solvers/feinn_reference_fit.py、feinn_reference.py | 冻结buffer→完整q15/q30，compare-only路由和标签政策；同V1参考、新MUMPS0；fit数学不改，FE无顶层Torch |
| checker/benchmark，第4组 | benchmarks/check_task42extra_durability.py、check_task42extra_v4.py；check_task42extra_docs.py、check_task42extra_docs_v3.py、finalize_task42extra_render_v3.py；src/test/test_optimizer_checkpoint_ml.py、test_replay_budget_clock.py | 原始checkpoint/复向量/功率/资源验算；旧文档工具默认保留V3，参数化新增V4，不复制求解器；新增tests、Ruff、compile、只查新节Markdown/渲染 |
| compact evidence/docs，第5组 | response_v4、durable_replay_v4、required records、summary追加、progress/registry/test/changed_files新节 | 保留全部旧历史；运行source与文档HEAD分开；字段/分母/计数/负结果/预算偏差明确 |
| do-not-merge | venv/cache/tmux sockets、raw native/G/矩/场/PT/NPZ/完整history、Firefox profile与截图 | ignored大数据；监督权重禁止作为生产或旧路线/Task042/0.7nm初始化；不自动merge |

这些分组仅供文件级审查，没有master merge approval。R1源码为538c6320679d9a3ce3efe5e6d6ebef062963f601，R2为c8a057a46645542aaa17a38b78e64c6add80cb68；后续文档/checker不冒充实算源码。源码变更只影响明确opt-in研究路径，旧V1/V2结果和V3中断原字节未重写。C1提交17文件、C2最小修正4文件，最终本批完整路径清单见[publication manifest](records/publication_manifest_v4.json)。

## Review V4 后续 V5 文件级边界

| 依赖组 / 文件 | 数值行为与依赖 | 测试 / fresh evidence | 建议合入顺序与边界 |
| --- | --- | --- | --- |
| research-only core：src/solvers/feinn_gqr.py、feinn_readout.py | 固定特征完整矩列、G-QR＋小R SVD、390实读出回写；依赖原CoordinateField/CompleteMomentMap/G与模型 | 11项定向tests、S0、唯一S1与独立ML/FE；严格Gate失败 | 不进production default；等待review |
| reusable runner：feinn_workflow.py、launch_task42extra_durable.py | 新明确stage/namespace、label与预算；launcher准入起单调时钟；旧路径默认不改 | persistent短dummy、4个新one-run清场 | 先单独审阅监督组件，不整支merge |
| input/schema：src/io/feinn_pilot.py、4个v5 dat | opt-in whitelist及5个监督标签；各stage独立环境 | 输入/隔离定向tests及manifest | 依赖core/runner，没有普通solver资格 |
| checker/benchmark：check_task42extra_v5.py、check_task42extra_clock.py | 只从原数组/记录重算，不实现新的求解器 | G/物理/资源独立checker，clock dummy | 可单独审阅；不改V1–V4结果 |
| docs/render：两个既有检查器增加显式V5参数 | 默认历史版本不变，只检查新review与新节 | 本地Markdown与实际GitHub新view | evidence/docs与数值core分开审阅 |
| compact evidence/docs | response_v5、frozen_hidden_readout_v5、7类records及summary/进度/模型/测试追加 | 绑定实际source与artifact hashes | 保留正/负事实，review后再定selective merge |
| do-not-merge | Phi/Q/G/native/model/fields/venv/cache/log/profile等ignored artifacts | compact hashes可审阅 | 不进Git，不接回旧无标签模型/Task042/0.7nm |

原CoordinateField/CompleteMomentMap及A/G/材料/背景默认数学不改；V1–V4、旧Task042历史不覆盖。本轮无amend/强推、master/其他支线merge或大模型计算。

## Review V5 后续 V6 文件级边界

| 依赖组 | 改动 / 数值影响 | 资格与建议顺序 |
| --- | --- | --- |
| research-only numerical/core | feinn_restricted_residual.py / feinn_residual_readout.py；固定空间原native残差读出；原默认solver不变 | 10定向tests＋T0＋唯一T1＋T2；不生产default |
| reusable runner/watchdog | feinn_workflow/pilot/durable launcher；4新stage、7角色字段、3600s/600s/1800s预算 | 复用持久监督/150s时钟；依赖core与4one-run dat |
| checker/benchmark | check_task42extra_v6.py；V5资源聚合器参数化默认语义不变；scoped docs/render扩展6 | 独立原字段重算；≤256/8/12/512，先core/runner后checker |
| compact evidence/docs | V6设计/checks/projection/comparison/run/resource/gate、response/诊断及summary/总账追加 | 保留V1–V5历史；review未改；供审阅不自动merge |
| do-not-merge | Phi/Q/B/QR大数组、NPZ/PT、timelines/browserprofiles | 全部ignored；新参数没有optimizer续训资格 |

四阶段实际source为a2f6ea85a24cb5e7c233d266aaab9911fc695dcc；之后checker/文档HEAD不充当数值源码。旧数学/数据证据保持原source与hash，不声称V6提升production。新stage路径在input/task042extra_feinn_5nm/v6_*.dat；仅当前分支，没有修改旧Task042或其他项目/全机配置。

## Review V6 后续 V7 文件级边界

| 依赖组 / 建议审阅顺序 | 文件与行为 | 测试及fresh证据 / 合入边界 |
| --- | --- | --- |
| production numerical/core | 无新生产默认；原p3材料、方程、背景、端口和历史参考不改 | 没有新神经或目标模型资格，不建议生产晋级 |
| research-only core，第1组 | src/solvers/feinn_discretization_audit.py；feinn_reference.py 的可选 audit hooks；feinn_fem.py 的显式DtN q15参数 | C1 ten targeted tests＋U0；p4参考未完成、比较未运行；新factor仅REFERENCE_ONLY，普通默认行为保留 |
| reusable runner/watchdog，第2组 | src/io/feinn_pilot.py、src/runners/feinn_workflow.py、scripts/launch_task42extra_durable.py；三个v7 dat | opt-in audit白名单、独立index；C2启动前身份/长原生调用截止修正10项定向tests，没有正式重放；依赖第1组 |
| checker/benchmark，第3组 | benchmarks/check_task42extra_v7.py；V5资源聚合器可选新factor计数；scoped docs/render显式7参数；四个V7 test文件 | 原字段重算，不实现新求解器；保留失败参考的RESOURCE_ONLY记录，不能伪造qualified index；默认历史版本不变 |
| compact evidence/docs，第4组 | response_v7、p3_p4_authority_v7、phase_representation_plan_v7及records；summary/进度/模型/tests/changed_files新增节 | C1实际source与C2停止后修正分开，原中断manifest字节保留，旧e4_p4与V1–V6不覆盖；真实渲染另核 |
| do-not-merge | venv/cache、native/矩阵/场/原日志、tmux sockets、浏览器profile/截图 | 大数组全部ignored；本批相位只有设计，无训练器或权重；任何p4标签训练须新授权 |

本轮只有一次真实p4启动，装配预算受控停止后不自动第二次factor。实际运行source为76d863e43d2fc1b5bed8b1c835aa6f43bb2c93d2；C2修正/checker为c2bfd3ce2ae5d499b6d8afe6a0b3fc3cf743a2a9。后续文档HEAD不替代实算source；保护的task/reviews未修改。文件级清单、依赖、测试和建议顺序见[publication manifest](records/publication_manifest_v7.json)，仅供审阅，master merge未批准。

## Review V7 后续 V8 文件级边界

| 依赖组 / 建议审阅顺序 | 本轮文件和用途 | 数值行为、依赖、tests/fresh evidence |
| --- | --- | --- |
| production numerical/core | 无新普通solver默认 | 原物理/材料/p3方程不改；无新NN资格，不生产晋级 |
| research-only authority，第1组 | feinn_authority_assembly.py（含独立Basix积分核）；discretization/reference明确可选策略 | 原局部张量准确全局CSR及独立Basix审核；A最小tests、一次p4参考和跨阶比较；仅REFERENCE_ONLY |
| research-only phase，第2组 | feinn_phase.py、feinn_phase_moments.py、feinn_phase_training.py、feinn_phase_verification.py、feinn_phase_compare.py | 完整矩前固定物理相位；同原参数规模、C无标签/D监督隔离；B/C/D与独立ML/FE，严格原残差负结果 |
| reusable runner/watchdog，第3组 | feinn_campaign.py、feinn_workflow.py、feinn_pilot.py、launch_task42extra_durable.py；独立v8 one-run dat | opt-in阶段、A–E依赖/新12h计费、实际p4预绑定、独立activation/白名单和持久监督；不扩大旧Gate或修改邻任务 |
| checker/benchmark，第4组 | check_task42extra_v8.py、docs_v3/finalize_render_v3显式8；本轮定向test文件（含既有选定组件） | 原字段/复场/真实分母/功率/标签/状态/资源重算；历史版本默认不变，不实现新求解器 |
| compact evidence/docs，第5组 | response_v8、authority_recovery_v8、phase_feinn_v8、records、summary/总账/测试追加 | 运行source与文档HEAD分开；完整费用和负结果，不改旧task/reviews/e4/history |
| do-not-merge | venv/cache、CSR/native/G/矩、PT/NPZ/optimizer/history、tmux socket、Firefox profile/截图 | ignored大数组；D权重禁止反馈C、旧路线、Task042或0.7nm，无master merge approval |

具体路径、每组依赖、源码SHA和资格入口见[publication manifest](records/publication_manifest_v8.json)。先审数值core，再opt-in runner/inputs，再checker，最后compact文档；所有组件均待review，不能整支线自动merge。没有p5/h细化/更多端口/多载波/目标尺寸计算。

## Review V8 后续 V9 文件级边界

本批增加准确p5审计和全参数GN研究路径。source提交均在正式run前clean；完整修改列表由Review发布到本轮Git diff核对，旧task/review/规则不改。

| 依赖组 / 建议顺序 | 文件与数值行为 | 对应资格 / 合并边界 |
|---|---|---|
| production numerical/core（候选，未批准） | feinn_exact_condensation.py、feinn_bounded_field_integrals.py、feinn_reference.py显式reduced_system；feinn_native.py≤8cell等价作用；默认数学不变 | 新p5/full配对/独立作用/参考Gate；先审查通用核，不能整枝合并 |
| reusable runner/watchdog | feinn_workflow.py、feinn_gn_campaign.py、durable入口白名单/预算/真实source；既有监督与原子保存复用 | targeted FE无Torch分派、事务/预算测试和每run清场；再审查编排 |
| checker/benchmark | check_task42extra_v9.py；V8 CSV writer只增加version参数默认8；docs/render checker显式version9 | 原字段Gate/故意损坏见证、Ruff/compileall、实际渲染；不重新实现求解 |
| compact evidence/docs | response9、p_ladder9、damped_gn9、records、summary当前导航、progress/registry/tests | 原始数值/失败/费用/hash保留，可独立审阅；无生产通过声明 |
| research-only | feinn_parameter_jvp.py、damped_gauss_newton.py、feinn_gn_training.py、新one-run dat与相位比较扩展 | 小/真实GN资格和负结果；不进入ordinary default或自动为其他物理初始化 |
| do-not-merge | ignored fullFE/矩阵/因子、PC基、全部模型/optimizer/checkpoint、完整资源日志/cache | 本地hash索引；不提交大数组，不迁入production训练权重 |

未来selective merge只能按依赖组取经过审查的最小文件；当前没有merge approval。授权只推送本任务分支，不改Task042历史或其他worktree。

## Review V9 后续 V10 文件级边界

| 依赖组 / 建议审阅顺序 | 数值行为、文件和依赖 | tests / fresh evidence / 合并边界 |
|---|---|---|
| production numerical/core | 无普通solver默认改变，原A/f/G、完整矩、q15和物理不改 | 无新NN资格或merge approval |
| research-only，第1组 | feinn_cached_derivatives.py/feinn_derivative_reuse.py：detached激活、匹配解析参数切线/伴随；damped_gauss_newton.py/feinn_gn_budget.py/feinn_gn_training.py预算安全；feinn_gn_freeze.py独立保全导出；phase_verification完整重建 | 小链/事务＋四态真实配对＋正式C/D/E；保留旧AD独立对照，不能提升为production default |
| reusable runner/watchdog，第2组 | feinn_cached_gn_campaign.py/feinn_gn_recovery.py/feinn_workflow.py/feinn_pilot.py/durable launcher：stage白名单、独立activation、继承预算/计数/GN/PC、own完整状态恢复 | 环境/阶段/FE无Torch守卫、恢复测试和每run清场；不改其他项目监督/共享环境 |
| research-only inputs，第3组 | 14个v10 one-run dat，qualified FE/ML按stage独立串行 | 所有正式run source clean、输入hash绑定，新attempt不覆盖V1–V9 |
| checker/benchmark，第4组 | check_task42extra_v10.py及5个负例tests；cached/runner/recovery/export/FE dispatch targeted tests；docs/render/finalizer显式version10 | 原字段重算、≤200KiB JSON、预算/标签/完整proposal与actual screenshots校验；不实现新PDE求解 |
| compact evidence/docs，第5组 | response_v10、derivative_reuse_v10、cached_gn_v10、records、summary首页及progress/registry/tests/changed追加 | actual source与文档HEAD区分；负结果/中断/全部费用保留，不修改旧task/review/Task042 |
| do-not-merge | ignored完整矩/Gram/native/参考/PC基/模型/optimizer/GN/history、环境/cache/tmux socket/浏览器profile截图 | 仅hash索引；D权重不反馈C/Task042/0.7nm；大数组不入Git |

实际逐文件SHA与依赖组见[publication manifest](records/publication_manifest_v10.json)。数值组件须逐组审查最小依赖，再看runner/inputs、checker，最后文档；本轮只推本任务分支，不amend/强推/merge、不新增高阶/网格/端口/目标尺寸运行。
# Review V10 后续 V11 文件级边界

新功能按依赖组审阅，普通 solver 默认、物理模型、旧参考和历史证据不改。仅执行分支保留，production/merge 未批准。

| 依赖组 | 文件/行为 | 资格与合入边界 |
|---|---|---|
| research-only numerical adapter | `src/solvers/feinn_parameter_metric.py`；`damped_gauss_newton.py` opt-in 固定M及原参数真残差；`feinn_metric_diagnostic.py` | 两种坐标关系、S=I、真实 g/K/FD 配对；固定度量改变优化步，不改变 A/f/G/loss；不提升 production default |
| reusable training/transactions | `feinn_gn_training.py` opt-in fork、八组真实更新、固定时间点、完整状态；`feinn_gn_recovery.py` | 继承原费用/状态；原子保存后审核；V11最多一次恢复、实际0；先接通 adapter，再审阅事务层 |
| runner/watchdog | `feinn_metric_campaign.py`；`feinn_workflow.py`；`feinn_resources.py`；`src/io/feinn_pilot.py`；`launch_task42extra_durable.py`；本批 one-run dat | 复用持久监督、60s原PSI窗口与独立FE/ML环境；没有放宽 CPU/内存/swap Gate；新 index 不覆盖历史 |
| frozen verification | `feinn_metric_verification.py` | 共同时间及共同接受步数的真实已落盘状态，不选best；ML q15/q30、FE compare-only reuse；运行 source 与文档 HEAD 分开 |
| checker/benchmark | `check_task42extra_v11.py`；docs/render opt-in version11 | 原字段独立重算，不重新实现求解；compact JSON≤200KiB；无空闲核的 preflight 保留真实未采样口径 |
| targeted tests | `test_feinn_parameter_metric.py`、`test_feinn_metric_runner_ml.py`、`test_feinn_metric_fd_repair_ml.py`、`test_feinn_metric_verification_ml.py` | 小复数代数、事务/恢复、FD稳定区、实际状态选择；不 full pytest |
| compact evidence/docs | Response V11、parameter_metric、summary新导航、records、progress/模型总账、本页与test_summary | 负结果、失败尝试、资源停止和旧历史均保留；独立审核仍未给出严格PDE资格 |
| do-not-merge | ignored PT/NPZ、矩阵、Gram因子、参数缓存、完整 history/resources、浏览器profile/原始截图 | 仅路径/hash留compact证据；无标签状态也不能供Task042/0.7nm生产初始化 |

建议依赖审阅顺序为 adapter及小测试→事务与runner→冻结复验/checker→证据；本轮没有合并授权。旧V1–V10正文在下方原样保留。


# Review V11 后续 V12 文件级边界

新增仅为保存态诊断，不提升普通solver默认或生产资格；所有旧task/review/response、参考和负结果不改。

| 依赖组 | 组件/行为 | 验证与边界 |
| --- | --- | --- |
| production numerical/core | 无晋级项 | 原A/f/G、材料、完整FE/端口、q15及验收门不变 |
| research-only | feinn_diagnostic_algebra/saved_state/saved_attribution/local_reachability/saved_field_diagnostics | 带符号二次型、稳定实投影、18保存场、两态16列与恢复见证；参考标签只分析，无optimizer/PDE新解 |
| reusable runner/watchdog | attribution_campaign、workflow的opt-in stage/文件白名单、feinn_pilot与durable launcher | 5个独立dat、既有activation/60sPSI/树监督/原子保存；不改他人或共享配置，不循环资源重启 |
| checker/benchmark | check_task42extra_v12、docs checker version12、5个新test模块 | 原向量/标量重算、非Hermitian/损坏记录、8-cell FE接线；合并24项未运行明确记录 |
| compact evidence/docs | Response12、诊断/辅助角色、records、summary导航及总账/progress/tests/本页 | 新知识/限制/完整成本/真实source/hash；暂停NN主解，不复制传统求解器 |
| do-not-merge | ignored PT/NPZ/native/G因子/缓存/全history/资源采样/tmux/browserprofile与截图 | 仅hash留Git，标签/权重不反馈Task042或.7nm，不以诊断投影作初始化 |

建议依赖审阅顺序：小代数/冻结与接口tests→研究诊断→opt-in runner/inputs→checker→compact证据。每阶段真实source另记；本轮没有merge授权。

# Review V12 后续 V13 文件级边界

| 依赖组 | 文件 / 改动 | 数值与合入边界 |
| --- | --- | --- |
| production numerical/core | 无晋级项 | ordinary solver不变，无合并授权 |
| reusable runner/watchdog | 现有feinn_attribution_campaign、feinn_workflow与durable launcher的v13显式入口 | 复用通用编排、单独dat、无新重启循环；原监督门未放宽 |
| checker/benchmark | check_task42extra_v12、docs_v3；对应checker/background/inventory测试 | C1原向量分类、D0/D1映射、背景算术独立Gate、新页选择；不能称新求解器 |
| compact evidence/docs | response_v13、evidence_closure_v13、records、summary/测试/文件表与本任务总账 | 保留历史，实际数值source与文档HEAD分开 |
| research-only | feinn_saved_field_diagnostics的新背景见证、累计A4保全与v13输入 | 无新矩阵/因子/NN；完整P34和原作用复用，仅M5诊断资格 |
| do-not-merge | 所有旧失败/未资格化NN、监督权重、ignored大型场/模型/timeline | 不作production默认或初始化，不复制别任务求解器/存储 |

逐文件hash、依赖、测试及fresh诊断来源见[六组manifest](records/selective_merge_manifest_v13.json)。实际Bsource为8000ee893a42e2f3cef288fe4652ee1052d511e7；后续只有checker选择/文档/证据收口，不重跑数值。

# Review V13 后续 V14 文档交接

| 依赖组 | 实际改动 | 数值与合入边界 |
| --- | --- | --- |
| compact evidence/docs | README当前暂停与历史初建导航、response_v14、summary页首停止链接、本测试/文件节和本任务进度；一个轻量归档收据 | 数值代码/输入/旧task/review/response与记录不改，无新模型/PDE/factor；复用[V13六组manifest](records/selective_merge_manifest_v13.json)，production numerical/core仍为空，未批准合并 |

本次改变页parser/链接与实际render资格、最小路径可访问性及资源见[归档收据](records/archive_receipt_v14.json)。大数组、checkpoint、原轨迹和截图留ignored；不复制一套数值记录或开展存储迁移。

## V15：研究用保存数组共同下降核及证据

新增src/solvers/feinn_common_descent.py（参数球与小型二次式上下界）、src/runners/feinn_common_descent_arrays.py（白名单/先hash后评价）、benchmarks/run_feinn_common_descent.py薄入口、benchmarks/check_feinn_common_descent.py独立原数组checker和src/test/test_feinn_common_descent.py。新增冻结设计、权限/hash、结果/比较/独立checker、Gate/资源/repair/run/渲染/依赖组及response_v15/topic；summary/README/测试/进度/总账仅同步当前范围。普通训练器/PDE/MPC/端口/环境/历史review/结果均不改；大数组仍ignored。[六组依赖](records/selective_merge_manifest_v15.json)。

V15额外最小修复benchmarks/render_task42extra.py：滚动时重取当前DOM并拒绝脱离页面的旧节点；仅影响可审阅截图，不影响数值源码或旧证据。原失败及修复source988d5af5476032ca29f95ad03536a858487c28f0单列render/repair记录。

## V16：证据验收边界修复

现有benchmarks/check_feinn_common_descent.py、src/runners/feinn_common_descent_arrays.py及薄入口新增完整覆盖/四点/实际冻结ledger/用途/独立五层Gate；不修改run producer或src/solvers/feinn_common_descent.py旧数值核。feinn_diagnostic_algebra.py只新增复用quadratic_change的冻结方向二次式解释；相关pure fixtures扩展。新response/专题/compact记录及README/summary/进度/总账仅追加本轮事实，原V15 result/checker/候选与所有历史不改。[六依赖组](records/selective_merge_manifest_v16.json)，无production默认或训练调度晋级。

## V17：一次轻量交接，无数值源码改动

只新增response_v17、diagnostic_dependencies_v17与handoff_receipt_v17；README当前边界、summary页首导航、本测试/文件节、项目进度及本任务模型总账同步暂停和最新并行分工。原task/review/response/数值kernel/runner/checker/tests及V15–V16结果候选均未改。[六类依赖manifest](records/diagnostic_dependencies_v17.json)列准确静态闭包，无producer/优化授权、无接收方/迁移部署或production晋级；raw/完整AST审计/cache仍ignored。

## V18：Review V17整批诊断

新小凸诊断核在src/solvers，参数化数组runner在src/runners；三个独立checker在benchmarks。B只接续旧保存场数学路径并加四区原量/checker；C只实现冻结方向的事务前向、原点核验、编号/MPC恢复和不同序号的原子边界，不复制训练器/传统solver。已有workflow、campaign及durable launcher增加明确V18 opt-in和白名单/计时绑定，ordinary default不改；新的三个one-run dat按ML/FE独立激活执行。

新response_v18、专题及compact设计/运行/检查/Gate/资源/修复/测试/渲染/CSV记录，summary页首导航、README及本支总账更新，历史正文不删。准确文件/hash/依赖/建议顺序见[六组manifest](records/selective_merge_manifest_v18.json)。大场、模型、缓存和完整采样留ignored；production numerical/core为空，未授权master合并。

## V19：当前循环停止交接，仅文档与compact证据

README改为Review V18权威和P0/P1/P2边界；summary只在页首追加，旧正文完整保留；本任务模型总账新增3.44.17、进度/测试/changed_files只追加；新增response_v19与closeout_receipt_v19。只落实已接受归因、流程限定、原目标及暂停状态，没有新数值结果。

原task/review/Response V18/结果/候选和源码、其他任务/分支均未改；不用新文档HEAD代替运行source。原六组[manifest](records/selective_merge_manifest_v18.json)继续有效：本轮仅compact evidence/docs；production numerical/core、runner/watchdog、checker/benchmark、research-only源码均无新增，ignored时钟/检查/浏览器收据属于do-not-merge。本轮无迁移部署或master合并建议。

## V20：完整3D相位适配FE显式研究入口

+src内新增固定几何计划、新空间构建/独立gψ审计/资格/参考与物理比较/保存负态诊断；已有体弱式/端口/物理action/export/exact_solve只加显式opt-in，ordinary/M5默认不改。准确边界端口换元保留原物理alpha和原门，未推广solver默认。新runner只做独立账本/资源/身份编排，durable入口包含import前时钟及监督tmux根，checker只读原数组重算。输入设计和八个one-run dat冻结新物理角色，未跑E4受Gate保护。

+新Response/专题/设计/资格/运行/checker/Gate/完整成本/修复/模式样本区域CSV与依赖manifest；summary只前置V20，README当前入口更新，进度/模型总账/测试只追加本支事实。原task/reviews/历史响应与旧数组及其他分支不改。全部raw/F/CSR/场/资源轨迹/cache和浏览器图留ignored。production numerical/core无晋级：[六类依赖](records/selective_merge_manifest_v20.json)。

## V21：准确原点端口与面闭包、独立保存比较

新增src准确整数回代/拓扑迹/联合资格/冻结p3恢复内核，既有reference/condensation/physical默认不变，仅opt-in研究修复；参数化campaign支持V21阶段、角色子集明确Gate、source/ABI内容hash与durable白名单，不复制求解器或campaign。独立Decimal checker、MPC保存身份/模式近零负控与局部测试。新Response/专题/compact/CSV和原尺寸derived差距/依赖组；summary只前置，测试/进度/本支总账只追加，旧task/reviews/场/α/负结果不改。大数组与raw/浏览器图ignored；[六类依赖](records/selective_merge_manifest_v21.json)无production/merge授权。

## V22：可靠输出与解析面显式opt-in、独立比较

新增src总场SplitVector/affine_state、资格状态机及解析Fourier-Legendre面组件，已有准确端口/物理比较/RHS/凝聚只加明确opt-in或计费，ordinary默认不改。既有参数化campaign/one-run与durable选择新独立V22 index，不复制runner/传统解；checker从原CSR/向量/物理数组重新判断，旧状态不覆盖。新增局部pure fixtures、9个dat、完整compact/CSV/Response/专题/导航/本任务总账；所有大场/CSR/原轨迹/浏览器图留ignored。六类依赖及测试/fresh数据/建议顺序见[manifest](records/selective_merge_manifest_v22.json)；production/core无晋级、没有merge授权。


## V23：实际资格拦截与最小可消费[0,1]积分

新增src严格资格守卫/区间矩适配/局部端口泛函，existing correction入口在加载/求解前拦截，ordinary receiver q60默认不变。沿已有campaign/one-run/durable增V23显式薄分派，不复制传统求解器；benchmarks只做固定局部fixture、独立Decimal/保存数组checker和完整冷成本记录。新增最小接收方示例/显式委托patch、5个dat、局部设计及3个定向测试文件。

新增Response V23、单个专题、compact原分母/运行/资格/checker/成本/修复/渲染/六依赖组；本任务README/summary导航及自己的progress/model/test条目同步，全部历史不删。原task/review/旧场/旧α和其他分支未改，所有大数组/完整Decimal字符串/资源轨迹/浏览器profile留ignored。source与文档HEAD分开；无新Maxwell/Gram/NN，production numerical/core为空，接收线仍须自己的完整keys/物理资格。

[六类依赖](records/selective_merge_manifest_v23.json)、[可运行包](../../../benchmarks/cases/portable_interval_facet/README.md)、[运行source](records/run_index_v23.json)。

## V24：固定主线组件接收和保存检查器局部I/O修复

新增src/runners/frozen_source_snapshot与fresh_component_receiver只做已有Git objects的最小hash-bound闭包、显式one-run/time/resource/锁/隔离tmux绑定，不维护第二个数学worker。saved_component_checker只为原数学checker提供自身FD及canonical只读加载，benchmarks/check_saved_array_snapshot逐原件stream/hash/关闭/fsync；没有新求解内核。feinn_resources/task042_shared仅加显式opt-in单核观察器自耗补偿，ordinary default与邻任务排除门保持。scripts公开入口及5个receiver dat均拒绝重复run目录；旧失败目录不覆盖。

三份targeted test文件最终28项通过，数学d4b6ed6b源码/cache133文件未改。新增response_v24/W0专题、compact数值/Gate/资源/修复/输入/955行CSV，README更新当前用户接续、summary仅前置并逐字保留历史；自己的progress/model/test同步。raw/科学报告/依赖cache/终端/完整采样留ignored。无其他分支/工作树或master变动；六组边界见[manifest](records/selective_merge_manifest_v24.json)。

## V25：W1统一合同、固定q60与原数组checker接入

clean实现357748671d1e8106027c0ee680cfdedb874837ec新增src/io/w1_receiver_contract、src/solvers/w1_boundary_components、src/runners/w1_component_payload及w1_component_receiver；scripts两个入口只增加显式W1 schema分支，ordinary default不改。数学调用冻结主线19文件闭包与本支既有区间矩，不复制W1数值算法，不调用旧runner默认目录或旧q30。增加29个pure fixture和11个串行dat、最小dependencies.json及接收README。

本次只在任务README/summary前置新结果并保存历史全文，在progress/model末尾追加本任务条目；新增response_v25、一个W1专题及输入/运行/Gate/资源/修复/测试/接收/选择性分组/呈现compact记录。源代码资格为49相关fixture/Ruff/compileall，native资源拒绝及原件缺失使实际P0/P1/P2未资格化；大数组和完整观察日志留ignored。旧权威、旧数值、其他分支/worktree均不改，依赖组见[六类分组](records/selective_merge_manifest_v25.json)，没有生产合入授权。

## V26：R新来源接收、原窗继承及真实拒绝交付

实现9ec41386新增src/io/w1_reproduced_input和src/runners/w1_input_recovery；在现有W1 IO/evidence/receiver/payload中加入显式input_recovery及bitwise_reproduced_v26分支。沿用同一durable/one-run，不复制求解器；冻结c354afa真实导入闭包扩为43文件，原19-file manifest不改。旧ledger白名单、数学源码、普通默认、原task/review不改。新增4个R/B dat、4个资源重新准入dat与16项pure测试；bc824b64的dat根错误由8675c955修正，全部失败保留，严格修复池流程限定不隐藏。

本轮增加Response V26、专题及run/来源/测试/成本/repair/Gate/接收/分组/呈现compact；README/summary只前置当前条目，progress/model/test只追加本任务内容。原生worker0、模式生成0、B0/B1/checker未运行，不提升生产或NN资格。大日志、原资格、资源盘点与受监督轨迹留ignored；[六依赖组](records/selective_merge_manifest_v26.json)、[源文件hash](records/run_index_v26.json)明确收口边界，未修改其他分支或合并master。
