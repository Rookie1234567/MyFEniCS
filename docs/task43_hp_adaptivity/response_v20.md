# Task43 V20：R10 保存场响应诊断未完成

本轮没有产生可审阅的完整 R10 场响应诊断。四个获准支持槽 T1、T2、D1、D2 均已调用并计费；受影响测试在 D2 再次遇到 fixture 错误后停止，D1 已读 q8 并到达 J 复现检查，但没有完成或落盘任何阶次；D2 两阶分析均 **NOT_RUN**。完整结果、剩余误差排名和位置提案均未生成。这不是 R10 数值响应的正面或负面结论，也没有新正式计算、采样或场恢复。

## 范围与固定输入

本轮遵从 [V19 review §9](review_report_v19.md)：只计划读取已保存的 R9、R10 与 Y6_1 三场及 q8/q10 点集，检查 R9→R10 的既有 p6 动作响应，并提出一个有确定规则的剩余误差位置建议。没有施加新的 h/p 动作；R9 仍是已接受父态，R10 仍是被拒诊断状态，Y6_1 仍是固定参考。

输入清单及其路径和 SHA256 由 [锁定输入](outcomes/records/v20_saved_r10_response_sources/input_lock.json) 与 [V20 合同](outcomes/records/v20_saved_r10_response_contract.json)绑定。正式数组分析没有完成，故本响应不列任何根据 partial 文件推断的 G、J、R00/T00、剩余份额或推荐单元数值。没有读取 Y5_1、Y3 或 Y3_2 数组；没有触及 holdout/control；V19 的旧 q8/q10 原件保持不变。

## 已调用阶段、结果和费用

| 槽 | 结果 | worker/watchdog/supervisor | whole 秒 | 测试或分析边界 |
|---|---|---:|---:|---|
| T1 | 6 passed，1 failed，5 not run | 1/2/2 | 8.491005773 | node 7 的 fixture 断言期待文本 `geometry box`，实际拒绝信息为 `geometric plan box`；`--maxfail=1` 后余下节点未运行。见 [T1 记录](outcomes/records/v20_saved_r10_response_sources/T1/root_decision.json)。 |
| T2 | 6 passed | 0/0/0 | 8.987010908 | 只补跑 T1 失败及被 maxfail 中断的节点；不是另一次完整初始测试批次。见 [T2 记录](outcomes/records/v20_saved_r10_response_sources/T2/root_decision.json)。 |
| D1 | 失败；q8、q10 均无完成阶次 | 1/2/2 | 39.803567743 | checker 将按行重加和得到的模态功率用于 J，和历史 comparison 使用保存 aggregate 的口径不同。见 [D1 决策](outcomes/records/v20_saved_r10_response_sources/D1/root_decision.json)。 |
| D2 | 1 failed，2 not run | 1/2/2 | 14.462614435 | node 9 的 ULP 回归在 witness 选择处失败，已进入 main 并完成输入锁核对，停在同 worker 前置测试；真实 q8、q10 分析均未运行。D2 实际源码 HEAD：`d71f92a604f60990d585e62c9e8f3513629dbae5`。 |

四次 whole 合计 **71.744198859 秒**。监控记录中的最高采样 RSS 为 **443,715,584 B**；CPU affinity 为 CPU 1，单线程配置，task swap 为 0。主控逐项审阅了各槽 trace/resource/终态，并确认可见本任务进程清理完成。RSS 是采样峰值，不代表连续高水位。D1/D2 后输入外层 hash 复核分别计时 3.1411147443577647 / 2.3361078198067844 秒，单列静态费用；其余静态审查、文档整理和人工复核没有完整计量，记为 **NOT_MEASURED**，不补造总 wall。

T1 与 T2 的六个恢复节点通过，但这些测试字节没有覆盖后来为修正 D1 的 J 聚合口径而改动的最终 checker。D2 只运行了三个受影响节点中的第一个；失败后余下两个节点未运行。因此不能把跨槽的部分通过拼成“最终 checker 全套通过”。

## 已定位的工程错误与未验证修正

D1 对照的旧比较实现读取候选记录的 `power.aggregate` 和参考的保存功率；已锁定 modal `metrics` 与这些旧锚点对应。新 checker 则先对模态行重新求和再构造 J。对 `power.R_total`，保存功率之差除以 `1e−5` 后为 `0.40645204737455026`，按行重求和再归一化后为 `0.4064520473578969`，两者相差 `−1.6653345369377348e−11`。该差异经原冻结 J 尺度放大，导致历史锚点复现失败。后续 checker 改为使用 hash-bound 保存 metrics 复现 J，同时仍以原有容差将逐行独立求和与保存锚点交叉核验；没有放宽数值门。D1 保留为失败原件，不因源码修复而追认为成功。

D2 的失败是新 ULP fixture 的序列化排序假设：JSON `sort_keys` 后的 components 字典在并列最大值时选出的 witness，与 `_replay_j` 的原稳定插入顺序不同。失败限定在测试 fixture 的 witness 重绑；没有证据显示共享 `_replay_j` 或数值门有错。D2 结束后已静态修补 fixture，使其保留原始合成 J anchor 中的 witness（`field.E_total_code`）；该修改**未运行、未验证**，不改变 D2 失败状态，也不构成节点通过。此处没有再启动测试或 checker。

主控预审未发现 T1 的文字断言不匹配，也未发现 D2 的 witness 并列排序问题；这两项分别造成了早期测试失败和最后一次槽的失败。机器记录保留原始失败及后续静态修补，不将预审遗漏改写成通过。

## 科学结论、资源与授权边界

由于 D1 在任何阶次标为完成前失败，D2 又在测试前置节点失败，V20 没有得到合法的两阶诊断产品。以下完整产品均为 **NOT_GENERATED**：180 个单元的 R10 剩余差异表、完整 612 通道/J 复现、全域与空间分组量、误差排名及 cumulative 位置提案。未完成本轮科学判定，不能判断 R10 的场差是否局部集中、是否有输出改善，或推荐何处进行未来局部动作；也不能把未测结果写成数值负结果。

本轮新增正式 PDE 数为 0；没有新采样、恢复场、holdout/control 消费或模型扫描。历史正式额度 9/10、末槽封存，旧 R10 拒绝状态及此前历史失败均不变。本轮 T1/T2/D1/D2 四次支持 shell 调用已用尽；失败不退款，也不自动授权另一次恢复、完整分析、正式计算或任何 R10 状态迁移。后续工作需要新的明确审阅与授权。

本轮机器汇总与原始失败索引见 [V20 机器结果记录](outcomes/records/v20_saved_r10_response_results_v1.json)；受影响测试原件、运行 manifest、输入锁和主控终态记录集中在 [V20 来源目录](outcomes/records/v20_saved_r10_response_sources/)。本响应不将这些有限工程检查称为全仓 CI、生产资格或合并批准。

五项能力保持：空间 PARTIAL；选择 PARTIAL；精度 NOT_PASSED；同精度全过程成本 NOT_ESTABLISHED；迭代 NOT_RUN / NOT_QUALIFIED。当前工程交付不完整、科学诊断不完整、合并资格未授予，三者分别陈述。
