# Task44 Response V1：可复用六层入口与首 A 试算前置

**当前分类：首A完成原装配/符号分析，在numeric前资源准入拒绝；没有正式FE训练标签或代理精度结论。**

首轮源码/软件前置阶段记录如下；首A实际失败和新的预算/检查点修复见末节。

已按用户覆盖在 dot own 分支实现，不切换或重置母任务分支。母任务固定参照 `db790f92a186988c5147f1828d15c07034e7c430` 与本分支兼容差异及缓存适用假设见 [README](README.md)。原任务书未改；48小时覆盖、盲测与安全边界见 [execution_override](execution_override.md)。

| 项目 | 实际证据 | 能说明什么 / 不能说明什么 |
|---|---|---|
| 材料 | 12 项测试、独立算术与来源核验通过 | 三种测试材料可重算；不是薄膜实测材料准确性 |
| 轻量几何/结果合同 | 10 项定向测试通过；generic `.dat` dry-run 通过 | 六参数独立、物理固定、身份与输出负控有效；不是 FE 精度 |
| A–D actual mesh/mode/phase | 每点144hex、836模式、160传播模式；解析体积/正Jacobian/周期对面与基变换通过 | 实际网格与端口坐标约定闭合；0积分、0求解 |
| MUMPS 公开API | 2×2 staged symbolic/numeric 与普通路径、dense oracle 一致，显式RR≈2.16e−16 | 可以在数值因子前取得真实符号估计；不能推大模型一定容纳 |
| 监督与ABI | 独立runtime、正常/timeout/request/拒控与阶段预算测试通过 | 能监测当前机器；不是OS硬配额 |
| GP 软件 | 23项测试及独立复跑通过；8/4/6坐标冻结 | 软件流程和盲封机制可用；无真实FE训练标签 |

新增通用功能包括：六层材料区域与贴体mesh；boundary-plane DtN；重新计算原全部FE+aux方程残差；每材料体吸收和实际MPC门；分级memory admission；同过程载入源/库与ABI核验。既有默认非六层路径不切换算法；新功能显式 opt-in。

测试采用分层方式：纯软件测试没有 FE/JIT；MPI1 complex128/int32 的 native prefix 和公开因子测试由唯一数值 owner 在今日资格化 runtime 执行。已完成 `compileall src scripts benchmarks/supervision_task44`、`git diff --check`。当前没有新CI结论，未因这批窄新增运行整库全测试。

下一步是唯一 owner 的首 A 受控资格试算：资源门、完整原残差、R/T/R00/体吸收均必须真实通过；随后再做 A–D 与预声明的离散/端口/顶部空气对照。普通失败保留并修复，不用软件PASS替代标签资格，不把未运行写成通过。

轻量证据汇总：[software_prefix_summary.json](outcomes/software_prefix_summary.json)。完整运行时与原始小资格证据另行保全，不进入 Git 大对象；此公开摘要不是可自足重放的原始环境。


## 首A实际与普通修复（2026-10-30）

首A监督总1242.566597秒，采样整树峰值3,168,022,528字节、4941采样、零swap、child1但clean释放；0数值因子、无R/T/Av、无原残差标签。原凝聚装配阶段约1149.76秒，端口插入完成1236.99秒；这不是卡死。纯分阶段记录尚不能精确拆出原raw类与Schur时间，所以新源补类级进度，不编造已测细账。

[MUMPS语义核验与新预算](memory_and_checkpoint_policy.md)消除重复的2倍预测余量，但没有降低真实资源/物理门。raw精确检查点19项软件控制通过；7项预算算术控制通过，均不替代正式求解。下一fresh A仍由唯一owner按新源身份、独立审阅及完整监督执行；原失败永久保留。[紧凑原失败证据](outcomes/first_A_admission.json)。

## 13:33 UTC：首个单样本数值结果与下一C

A_v2已独立通过完整原FE+aux残差2.24183e−7、能量缺口−8.88757e−10，R=0.10376673824/T=0.88008220448；完整cold监督1428.157635s、峰6,597,210,112B。没有以condensed残差替原残差，也没有把Av=1−R−T代替独立体吸收。原A_v1失败与1242.566597s成本完整保留。

下一C保同recipe，只有更保守rank1 JIT预算两常量256→2560MiB；精确diff/全module AST检查证明没有算子或输出算术变化，原/新execution与FE集合SHA分别保存。单样本通过不构成训练资格，四独立稳定性对照尚未运行；当前不消费盲标签。公开结果与证书见outcomes/A_v2_result.json和resource_only_equivalence_v1.json。
