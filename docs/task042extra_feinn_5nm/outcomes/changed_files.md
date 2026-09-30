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
