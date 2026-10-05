# Response V26：确定性输入恢复接线已资格化，原生阶段两次资源拒绝

按[Review V25 §8](review_report_v25.md#8-原件接续审阅一次恢复确定性输入随后完成真实全模式边界资格)新增了可执行的输入恢复和新来源凭据分支，完成16项增量测试并冻结实现。两次持久launcher均通过外层资源盘点，随后在固定到单核的内层盘点中被空闲物理核门拒绝，**原生worker和模式生成次数均为0**。因此本批为`PARTIAL_RESOURCE_ADMISSION_REFUSED`，原manifest能否跨ABI逐字节恢复仍UNKNOWN，B0/B1及数值保存checker未运行；不是hash不匹配，也不是q60数值失败。

这项实现把“从冻结源码重现确定性输入”和“伪造旧运行账本”分开：仅允许原配置、模式生成和序列化调用一次；新凭据记录本次真实来源，并核对固定Git物理身份、文件字节和成功监督。它解决缺少旧大文件时的真实接入问题，代价是新增来源验证和受影响逻辑资格；本轮尚无实际恢复或数值收益。

## 1. 工作包与实际出口

| 阶段 / 数据身份 | 实际结果、原门和单位 | 证据与限制 |
| --- | --- | --- |
| A / 已接受证据复用 | 旧92项JUnit、原资格SHA均保持；未重跑A | [旧阶段](outcomes/records/stage_A_v26.json)、[独立审阅](outcomes/records/review_v25_stage_A_audit.json) |
| R新增逻辑 / measured fixture | 16/16、Ruff、compileall及公开dat解析通过；失败监督、错正文/source/hash、假旧ledger、未封存候选均拒绝 | [增量测试](outcomes/records/targeted_tests_v26.json)；不是原生FE或模式生成证据 |
| R实际恢复 / not_run | 两次内层CPU准入拒绝；一次实测新窗口重新准入已用尽；没有生成manifest或新receipt | [运行](outcomes/records/run_index_v26.json)、[保存收据检查](outcomes/records/independent_checker_v26.json) |
| 必须匹配的原输入 / UNKNOWN | 36,244,923B、32060有序key及两项完整SHA均未实测；物理/库存身份由固定Git原文绑定 | [可消费合同](outcomes/records/integration_packet_v26.json)；未把数量或schema正确当逐字节恢复 |
| B0 / not_run | 原生Basix方向、周期缝/角点及fresh W1 ABI未运行 | R输入及安全资源前置未闭合 |
| B1和保存checker / not_run | 全32060实际覆盖0；q60原分母门1e-10、区间矩1e-12未判定 | 无数值raw，不能用16个fixture或旧局部q60证据替代 |
| B2 / not_authorized | 本包没有四个局部LU/恢复；主线按自己的Review承担 | 不重造旧104成员NPZ，不复制dot工作 |
| 原尺寸场与神经 / not_run | E/H/curl、六点、全复通道、R/T/A/A_volume无新值；NN/Gram/Maxwell因子/solve均0 | `FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED`保持 |

## 2. 准确来源和拒绝归因

| 身份 / 实际阶段 | 完整SHA或原字段 |
| --- | --- |
| 接棒review seal | `045b8d991a78d4e06962439e4e4ec1ac9668633e` |
| 冻结base | `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff` |
| clean实现 / 增量受测源码 | `9ec41386a0ab8c17ae2447507648ab2b039feeae`；正式数值worker尚未运行 |
| 重新准入dat登记 / 路径修正 | `bc824b64f8960e82a422e298275f71ebc288bf9f` → `8675c9551e3cf9bfa5e8b881bd72a87344d9cc08`；数值核心字节相同 |
| 原数学来源 | `c354afa449fb80cfb5012e7d2ff66a3e3e64e088`；43个实际导入/activation/源dat/身份文件、1,054,179B，逐Git blob复核 |
| 期待manifest SHA256 | `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`，未生成 |
| 期待有序key SHA256 | `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec`，未实测 |
| 固定Git身份原文 | `03b5c44136f132d203237211ea1499faec1c25d3c1f47225e0c662d00aca4ea0`，16783B；新receipt分支不扩大旧ledger两hash白名单 |

第一次外层盘点找到11个候选CPU并选CPU2；第二次正式外层盘点找到6个候选并选CPU1。两次内层都报`No audited unoccupied physical core; do not overlap a busy worker/SMT sibling`，尚未到60s PSI稳定窗、ABI或原生成器。其失败时的逐核分数没有保存，无法把瞬时邻任务迁移与固定核观察器/自身父链归因区分开。**这是实际准入链拒绝，不是已证明整机没有空闲CPU，也不是RAM、JIT、MUMPS或数学失败。** 未改变审计阈值、邻项目、亲和性或环境以绕过拒绝。

资源重新准入前保存了真实候选集合变化，核对第一tmux server/pane已退出；只进行了合同允许的一次重新准入。第二次拒绝后停止数值链，没有第三次准入、后台轮询或换ABI试hash。两个own terminal身份均已消失、锁FREE；完整清场及最终HEAD另见本机最终交付收据。

首次资源元数据整数键写出错误、fixture导入/Mapping错误、lint失败和重新准入dat错误均保留。[修复账](outcomes/records/repair_log_v26.json)逐项记录failure→hypothesis→change→test→retry；重新准入dat曾沿用旧output_root，重复启动保护在worker前拒绝，修正后才进入第二次资源审计。该额外路径修正发生在元数据修复之后，**按独立工程轮严格计数超过剩余一轮的口径，保留为流程限定，不能记整批合同PASS**；没有因此新增实际数值候选或生成次数。

## 3. 完整成本与未测部分

唯一连续R/B窗为2026-10-05 00:33:56.793657 UTC→03:33:56.793657 UTC（10800s）；包含首项接线、开发、失败、等待、测试、保存、Git和交付。R及接线1800s、数值/checker7200s、尾段1800s共同受总窗约束，没有在恢复或重新准入时刷新deadline。已保存数值链停止观察为T0后1358.198787s，最终交付尾段按真实时钟补记，不运行到预算上限。

| measured / retained / UNKNOWN；成本口径 | 实际值及限制 |
| --- | --- |
| 新增四次受监督轻测试合计 / s | 10.139373，嵌套在连续窗内，不再次相加；两次15/16失败、一次16项通过但lint失败、最后整体通过 |
| 最后资格树 / s、B | 2.656706 / 同时采样峰90,886,144B，hard2,147,483,648B、ownswap0、清场 |
| 全部新增受监督测试树峰 / B | 93,003,776B；不能把各阶段峰累加当同时峰 |
| 正式R launcher树峰 | `NOT_RETAINED_BEFORE_WATCHDOG`；未启动native watchdog/worker，不能宣称整个准备链已有连续kernel 2GiB证书 |
| 外层内存余量 / B | 两次有效可用均约2.1364e12B；系统预留216,310,038,528B及邻增长412,316,860,416B保持，PSI读数0 |
| 原A / 旧V25 / 旧失联 / s | 2361.839628 / 2846.101466 / 3284全部保留；A到R的真实日历间隔另计，不冒称连续14400s或完整48h |
| 数值worker/checker / 新factor、solve、NN、OOC | 0s / 0；轻工具未持续采样部分不补造峰值；精确项目累计仍UNKNOWN |

[资源账](outcomes/records/resource_costs_v26.json)保留启动上界、日历间隔、原窗hash及终段收据入口；上界含观察/清场延迟，不能冒充worker精确耗时。代码恢复协议和全部频率覆盖已实现，但实际跨ABI、原件hash、所有频率/ell0..6的Decimal参照、物理入射RHS、坐标相位、全H及完整目标MPC均未取得新的数值资格。

## 4. 交付、下一步和保留边界

[接收说明](../../benchmarks/cases/w1_receiver/README.md)、[专题](outcomes/w1_input_recovery_v26.md)、[Gate](outcomes/records/gate_decisions_v26.json)、[完整run/source/hash](outcomes/records/run_index_v26.json)、[最小接入包](outcomes/records/integration_packet_v26.json)、[六类依赖](outcomes/records/selective_merge_manifest_v26.json)已更新。旧A原92项及Review V25有限视觉收据按绑定复用；新页本地结构检查独立记录，资源链关闭后未启动浏览器，**新GitHub视觉NOT_RUN**，不能沿用旧页PASS。[呈现边界](outcomes/records/render_check_v26.json)。

保存M3600中期较好、Mfinal最终退化、D0成本否决/D1未运行、所有旧q30/q60负结果、FAIL/UNKNOWN和费用。不修改主线、dot、旧Task042或master。下一实质缺口是本支固定核准入链的可核归因与一次真正输入恢复；当前不得自动重新准入或重跑，需审阅明确新资源/修复范围后继续既有组件，不加新求解器或配置扫描。

原目标仍为50×25×140nm、Si17/120nm、λ0.7nm完整三维FE，在十进制2,000,000,000,000B整机、自身swap/OOC0及连续172800s完整冷流程内满足原精度门；尚未达成。只推送精确`task42extra_feinn_5nm`，准确最终HEAD/base、tracking/ahead-behind、clean与自身清场在最终回复及ignored交付收据报告；整批一次通知审阅线程后停止工具。
