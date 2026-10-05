# V26：输入恢复与全模式q60接入的真实边界

本专题说明如何把缺失的确定性模式文件恢复后送入同一条验收链。现有源码和小身份文件已可读，新增入口只调用原冻结生成函数一次；随后要求文件逐字节与原件一致，新来源凭据不得冒充旧ledger。逻辑定向资格已完成，但本轮两次固定核资源审计拒绝，原生成函数未执行，不能把实现存在写成原件已恢复。

| 固定阶段 / 数据身份 | 输入、方法和实际状态 | 独立证据 |
| --- | --- | --- |
| R / implemented、not_run | 原c354afa源dat/43-file闭包；固定目标配置及五个原模式元数据helper；生成次数0 | [input/source合同](records/integration_packet_v26.json) |
| 新来源分支 / measured fixture | `bitwise_reproduced_v26`单独验证schema、完整物理正文、Git blob、manifest和成功监督；16个fixture通过 | [测试](records/targeted_tests_v26.json)，无新旧ledger混同 |
| 单一窗口 / measured fixture | R deadline从首项准备冻结；B只附加输入binding，不能新建现在+10800s | [原窗及费用](records/resource_costs_v26.json) |
| 原生准入 / controlled resource refusal | 两次外层有候选，固定核内层拒绝；第二次为实测新窗口的唯一重新准入 | [运行与原日志hash](records/run_index_v26.json) |
| B0/B1 / not_run | 原生方向/MPC、唯一q60及32060模式输出、独立保存checker未执行 | [Gate](records/gate_decisions_v26.json)；无数值raw |

预期原文件为36,244,923B、SHA `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`，32060-key SHA为`03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec`。本轮没有原件大小或SHA的新实测结果，逐字节重现能力UNKNOWN，旧两ledger/NPZ继续NOT_AVAILABLE。准入失败之前不调用生成器，路径保护拒绝也不当作一次数值生成。

完整q60组件将使用原(100,1)面片及90/46/46/90分段，覆盖p4/p6完整迹列、top/bottom、原H、B/D、三方向作用/伴随、居中与绝对坐标以及真实入射载荷。新频率清单从实际面宽和所有mode取得全部去重频率、ell0..6，复用既有固定Decimal80/110参照；已经修正过去只抽极端频率的入口。**目前仅完整覆盖逻辑fixture通过，实际频率列表和全部原分母门均未运行。** 没有扫描q、换分母或把旧q30/q60差5.70590933解释为本次q60FAIL。

新受监督轻测试树峰93,003,776B、ownswap0，最后16项资格2.656706s；正式两次launcher在watchdog/ABI前退出，整条launcher历史同时峰NOT_RETAINED。固定核自身观察耗费与邻迁移的区别没有足够原始分数，保持UNKNOWN，不更改排除规则“修成通过”。初始元数据/fixture/lint/路径错误和严格修复轮计数限定见[全部修复](records/repair_log_v26.json)；数值链关闭后只做保存收据、Git原文及文档核对，不继续准入。

源码、记录与输入的建议消费顺序见[分组manifest](records/selective_merge_manifest_v26.json)；当前包是可审阅的opt-in实现，**原生资格未闭合，不是production组件或有效前向解**。B2局部LU/恢复由主线自身合同承担，本支不重构旧104成员、AUTO、owner、传统PC或dot后端/存储。没有NN/Gram/全局Maxwell因子或solve，FEINN主求解器暂停、无验证神经净增益，原0.7nm完整三维/decimal2e12B/172800s目标和原门均保持。

本轮完整回应见[Response V26](../response_v26.md)；元数据保存检查不等于B1数值checker，见[检查范围](records/independent_checker_v26.json)。两份新页的标题及全部4表已在发布`6a6983064c67a7cba13c64a046c557559c99a7d2`上实际目视通过（6图，21.901543s/1,775,185,920B/ownswap0并清场）；最终呈现尾段seal不移植为全页复验，其他导航页仍未视觉检查。未改审阅页只复用其已封存的有限范围。
