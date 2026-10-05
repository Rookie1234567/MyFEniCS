# Response V27：已实际生成，原清单逐字节重现失败

**本轮完成了 Review V26 的两处工程修复、定向资格和唯一原生 R 生成。保存文件没有达到原件的字节/hash门，因此停止依赖它的 B0/B1；这是输入重现失败，不是资源拒绝、q60失败或有限元求解失败。** 已完成独立保存复核与拒绝闭环，没有重新生成、换环境试参或把不同清单登记成原件。

端口清单描述每个外部波动模式的方向、极化和归一化。模式名称相同仍不能保证这些数值相同；本合同要求整份文件逐字节一致，避免后续边界载荷和独立checker使用不同数据。本轮已有全部模式名称及物理身份，但尚没有合同要求的原清单。

## 1. 实际完成、失败与未运行

| Review V26 阶段 / 口径 | 结果、具体门及原因 | 证据 |
| --- | --- | --- |
| P0 / implemented、fixture measured | 修复候选核范围、拒绝观察、Git/blob封存和最终标记顺序；23新增＋16受影响旧测试，共39通过；旧92项A按原收据复用 | [测试](outcomes/records/targeted_tests_v27.json)、[有限修复](outcomes/records/repair_log_v27.json) |
| R资源与原生ABI / measured | 两层新样本均通过；CPU12、数学线程1/MPI1、原60秒PSI门；complex128/int32；无FE action | [运行/ABI](outcomes/records/run_index_v27.json) |
| R文件 / failed | 实际36,263,033 B，要求36,244,923 B，差18,110 B；完整SHA不符；实际只生成1次 | [输入](outcomes/records/input_reproduction_v27.json) |
| R部分身份 / measured | 32060唯一有序key、每个side/极化8015项；key及模型物理hash符合原值；包含manifest hash的inventory身份不符 | [保存重算](outcomes/records/independent_checker_v27.json) |
| 保存、封存及拒绝 / measured | 43份Git blob与实际manifest分别封存、独立重开；实际失败候选不能提交；最终ledger和B输入标记均不存在 | [独立checker](outcomes/records/independent_checker_v27.json) |
| B0/B1及B1保存checker / not_run | 原输入重现门失败，不能使用该候选做真实方向/MPC或32060项q60物理资格 | [Gate](outcomes/records/gate_decisions_v27.json) |
| B2/W2、全局FE、NN / not_run | 本包无这些权限；新FE action、factor/solve、Gram、NN训练均0 | [包与边界](outcomes/records/integration_packet_v27.json) |

预期manifest SHA256为`52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`；实际为`7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e`。实际有序key SHA256为`03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec`，物理身份SHA256为`a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f`，后二者符合合同。

独立复核从保存文件重算，没有调用生成器。文件与固定canonical JSON读回一致；原36244923B正文仍不可用，所以原数值逐字段差为`NOT_RETAINED_ORIGINAL_BYTES_UNAVAILABLE`，差异根因为`UNKNOWN`。不能据此断言不同ABI、序列化、方向、浮点末位或材料是唯一原因，更不能宣称数值等价。[专题](outcomes/w1_input_reproduction_v27.md)列出原值、hash及拒绝链。

## 2. 工程修复与资格边界

原启动器先选核再pin，内层容易只搜索继承的一核。新实现保存pin前允许范围和自身身份，内层在新观察上检验该范围与当前cpuset交集，保留所有原忙率、SMT、睡眠窄affinity和邻线程排除。只移动自身身份匹配的终端树。默认调用行为保留；本轮实际两层通过，不把这个事实反写为旧两次拒绝的精确归因。

Git blob是固定提交里的源码，不是输出目录里的数值文件。现在分开校验两者；成功路径必须先确认监督成功、清场和候选正确，再封存、重开消费者、提交ledger，最后发布B输入标记。完整fixture覆盖实际writer→seal→重开→消费者，并拒绝坏源码、坏manifest/更新hash的坏内容、缺raw及失败监督。真实R虽数值身份失败，仍成功封存43份源码与失败文件；实际`commit_recovery`以`W1_R_CLEARED_CORRECT_CANDIDATE_REQUIRED`拒绝，没有最终标记。

启动binding扩至29份实际依赖，包含资源观察、tmux和watchdog链。P0首次两个fixture失败及一次旧A收据路径资格失败均保留并局部修好，最终39项、Ruff/compileall/4个dat解析通过。干净实现冻结后工程修复轮数0；没有正常数值失败重启。未运行full pytest、CI、旧92项A或旧重型资格，未重装环境。[分组边界](outcomes/records/selective_merge_manifest_v27.json)没有production或master合并批准。

## 3. 源码、资源与完整费用

| 身份 / 时间与内存口径 | 实际值及限制 |
| --- | --- |
| 分支 / 冻结base | `task42extra_feinn_5nm` / `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff` |
| 本轮权威输入 | Review V26 seal `a9afaa9112d7395f7b8991602906606237db87c3` |
| clean实现及实际R source | `904131e19396c4b6896d42056df2e27387908c1f`；后续文档HEAD不冒充该source |
| 原数学 / 闭包 | `c354afa449fb80cfb5012e7d2ff66a3e3e64e088`；43文件/1,054,179B；实际receiver29文件另绑定 |
| 新连续总窗 / 子限额 | 10800s；P0≤1800s、R≤900s、R/B/checker共享≤7200s、交付预留1800s；没有重写旧窗 |
| P0完整边界 | 1144.441616s；含120s明确保守开场allowance，不冒称精确首次工具时间 |
| 实际R全链 / watchdog子段 | 81.936506s / 18.688100s；后者嵌套，不能相加；包括加载、PSI、生成、保存及封存 |
| R同时树采样峰 / 自身swap | 437,981,184 B / 0；hard2GiB，含身份匹配tmux/launcher/worker；watchdog前峰NOT_RETAINED |
| 最后39项测试 / 保存独立审计 | 3.453455s、峰91,508,736 B / 4.873763s、峰341,622,784 B；均hard2GiB、swap0并清场 |
| R/B准入额度实用 | 外/内共2份；采样与60s压力等待合计62.653522s，门12份/300s；没有资源重准入或后台轮询 |

[完整费用](outcomes/records/resource_costs_v27.json)保留所有P0失败/重验、审计、发布和浏览器尾段；嵌套阶段不双加。旧A2361.839628s、V25 2846.101466s、V26交付2590.730724s、失联3284s和原外部/审阅日历间隔均保留；项目精确累计仍UNKNOWN。最终通知后收据为ignored `tmp/task42extra/w1_receiver/v27/delivery_receipt.json`，记录完整交付尾段，不把提前snapshot冒充最终总费用。

资源采用原系统max(128GiB,10%)＋384GiB邻增长预留、ownswap/OOC0、单空闲物理核/单线程/CPU-only/MPI1；未修改邻任务、共享环境或Git配置。实际worker监督COMPLETED/exit0表示生成和保存过程正常结束，**科学判定仍为BITWISE_REPRODUCTION_FAILED**；它不是原方程或边界PASS。

## 4. 交付与停止

本轮原残差、E/H/curl、六点、全部复通道、R/T/A/A_volume及逐级功率均NOT_RUN，没有新场精度证书。M3600较好、Mfinal退化、D0成本否决/D1未运行、旧q30/q60负结果、全部FAIL/UNKNOWN及费用不改。

保持 **FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED**。原50×25×140nm、Si17/120nm、λ0.7完整三维FE、十进制2e12B整机、自身swap/OOC0、172800s完整冷流程及原精度门尚未达成。未来若要继续B，需要真实原hash-bound字节或新的明确身份合同；本轮不自行替换、放宽或重试该输入。

[summary](outcomes/summary.md)、[run/source](outcomes/records/run_index_v27.json)、[可消费接入状态](outcomes/records/integration_packet_v27.json)、[呈现范围](outcomes/records/render_check_v27.json)。只提交推送本分支，精确fetch核验与自身清场后发一次正式通知，随后停止等待ChatGPT审阅；不改其他分支、不合并master。

实际GitHub呈现已有限核验：发布`007f61b8ce31224e9547e82a7cf7c70bf8374feb`的两新页标题/开头、全部3表和5张实际目视图可读；浏览器监督19.558924s、同时树峰1,705,955,328B、自身swap0并清场。复用Review V26原视觉收据，不重渲染历史；本seal仅追加呈现/成本收据与尾段文字，尾段及其他导航页未重新视觉核验。[呈现范围](outcomes/records/render_check_v27.json)。
