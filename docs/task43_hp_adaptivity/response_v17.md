# Response V17：P8 空间门通过，求解端点未完成

V16 review 授权的 S→F→C 链已执行到 F。S 的独立空间审计通过，P8 比 R9 增加 250 个独立有限元未知量；F 在应用 worker 的 watchdog 父链检查处退出，未生成合格求解端点，因此 C 没有运行。这个结果不能说明 p 加密的输出精度或效率好坏，也不是数值残差失败。

本轮的 p 加密把固定模型中一个局部单元的多项式阶次从 p5 提到 p6，让单元内部的场表示更灵活；它没有把单元再切小。FE 是施加周期约束后仍需独立求解的未知量数。它用于衡量离散规模，但不能单独代表精度。

本次固定 phi90 模型的周期为 50×50 nm，计算域高 140 nm，波长 13.5 nm，使用 q15/q28 积分、R13 模态和 612 个通道，并以 Y6_1 为比较参考。空间变更只针对固定 box `[16.5, 5, -10] → [33.5, 10, 0] nm`：global cell 8 与 forest root index 4 是同一目标单元的两种编号，该单元由 p5 升至 p6；没有 h 分裂。合同配置 normal correction=1、extra correction=0，但 F 未到达实际修正阶段。因而 S 的 FE 结果明确对应这一个局部 P8 计划。

## 阶段结果

| 阶段 | 实测结果 | 解释与边界 | 证据 |
|---|---|---|---|
| S：P8 空间 | 180 个叶单元，p5/p6 为 27/153，无 h 分裂；独立 FE=110,722，R9=110,472，ΔFE=250。trace/interior 为 35,392/75,330；周期从属行 5,452 | 这些是独立空间审计的实值。p6 carrier 124,530 行含 8,356 个未激活行，不能把 carrier 当成独立 FE。返回的 36,004 trace+R13 行是预测值，矩阵未装配 | [S joined](outcomes/records/v17_r9_p8_sources/S_space_joined_terminal.json)、[空间摘录](outcomes/records/v17_r9_p8_sources/S_space_plan_audit_excerpt.json) |
| F：网格与弱式准备 | mesh build 结束；函数空间记录 carrier 124,530、Floquet 约束 5,730；场形式、边界和变分形式阶段均有结束记录 | 这些是 F 的局部 carrier/约束计数，不是独立 FE。F 未保存独立 `runtime_identity.json`；源代码在 `preflight_end` 前调用 runtime envelope 检查，故只能推断该前门返回，不能补写完整 F 环境实值 | [F terminal 摘录](outcomes/records/v17_r9_p8_sources/F_partial_terminal_excerpt.json) |
| F：求解入口 | `task43_solve_and_observe_begin` 后抛出 `RuntimeError: V11 application worker is not the watchdog's direct child`；worker trace 以 1 退出 | 守卫拒绝丢失的父子关系。未得到合格 primary、残差、normal/extra 修正、612 通道 R/T、A_volume 或 q8/q10 的 E/H/G/J；不归因于 p 方法的数值失败 | [ignored partial terminal](../../benchmarks/artifacts/task43/v16_p8/formal/R9_P8_attempt1/run/task43_v16_p8_partial_terminal.json)、[F 轻量摘录](outcomes/records/v17_r9_p8_sources/F_partial_terminal_excerpt.json) |
| C：四场比较 | NOT_RUN | F 不完整，当前合同不允许从不合格 F 继续到 C；唯一 C root 不存在 | [机器结果](outcomes/records/v17_r9_p8_scientific_results_v1.json) |

S 实测 P8 ΔFE=250；旧 H8 的 ΔFE=6,268 是历史复用结果。因为 P8 没有 primary 场，无法比较两者每个未知量带来的输出收益。最终精度仍 `NOT_PASSED`，同精度全过程成本仍 `NOT_ESTABLISHED`；空间和选择能力仍为 `PARTIAL`，迭代仍 `NOT_RUN / NOT_QUALIFIED`。accepted9/R9 保持最后接受状态，R10 仍拒绝，没有 transition10。

## F 的退出、资源与 trace

F 外层执行会话回报 143，但 `launcher_exit_code.txt` 写入 0；`watchdog_exit_code.txt` 和 `watchdog/summary.json` 均缺失。正常路径先写 watchdog exit code；shell 退出时 EXIT trap 才写 launcher exit code。现有记录不足以解释外层 143 与 launcher 文件 0 的矛盾，也不足以确定 watchdog 终态为什么缺失；信号来源和退出原因均为 `UNKNOWN`。

启动与结束时间相减得到 760.278162547 秒，这是 launcher 时间戳区间，不是 watchdog whole。F 的 watchdog whole 未测得；末条资源样本 elapsed 756.7104571810924 秒只构成已观测下界。1,114 条样本的同时进程树 RSS 峰为 1,040,801,792 B，采样到的进程树 task swap 峰为 0，所有可见成员都在 CPU1；但样本在 worker 退出前终止，资源 Gate 不能判为通过。`progress_3d.jsonl` 中的 `swap_used_mb` 来自全局 `/proc/meminfo`，不是本任务 swap，故不用于 task swap 结论。

八份 trace 共 1,043 行：35 个 getter、3 个成功 setter、1 个 status 0 的正常 SIGCHLD，未分类事件为 0；3 个 setter 都设置为 CPU1，调用栈涉及 SCOTCH 网格分区线程上下文的初始化和退出。worker trace 退出 1、orted trace 退出 0，八份 trace 均有退出尾行。完整非栈原行和 setter 调用栈见 [trace 摘录](outcomes/records/v17_r9_p8_sources/F_trace_nonstack_and_setter_stack.jsonl)。这些调用不构成非 CPU1 失败。

主控较早观察到 watchdog 消失时，worker、tracer 和 orted 仍存活并已脱离原父链；之后的只读记录显示四个相关 PID 均已不存在，主控动作列表为空。没有证据表明本轮主控发送了信号，也没有证据证明 watchdog 正常清理通过。静态源码中 watchdog 已注册 TERM/INT 处理并有 `finally` 清理，因此目前不能把原因归为缺少该处理器。失败来源仍未定位，未声称已修复。

## 次数、费用与下一步

| 账户／费用 | 本轮收口值 | 分类 |
|---|---:|---|
| V16 review support | 3/5：T main、T recovery、S；C 未用 | T 原槽 2/2；用户另授权单节点补验 1/1，单独记账 |
| Formal | 8/9；P8 1/1，F 已消耗 | 不因 F 不完整退回槽位；历史封存槽不动 |
| 已测 whole | 两次 T 合计 82.05409320862964 s；用户补验 12.767253825906664 s；S 310.5137330442667 s | 分项保留；F whole 为 `not_measured` |
| F 已观测时长 | 末条样本 756.7104571810924 s；launcher 时间戳区间派生 760.278162547 s | 前者仅下界，后者不是 workflow whole，不相加 |
| 静态费用 | T preflight 1.7144702672958374 s；F root 只读审计 1.6008896040730178 s | 与动态 whole 分开；手工编辑/文档未测 |

T 资格记录 `PASS_LIMITED_V16_SUPPORT` 保留 V15 `review_commit` 语义，并另绑定 V16 authorization review；最终测试文件 SHA256 为 `c7ae026e40ac782652b17e87e7399eef541c139ff62900b20caf7ea59e34a236`。资格沿用17项历史同字节证据，另有1项用户单独授权且实测的节点；这不等于一次最终18项测试批次。E 仍未资格化且禁止。S joined 的一次静态断言错误已保留：检查器把 builder 的 `maximum_level=1` 能力误当成实际分裂层数；根据 parent builder capability=1、实际 splits=0 和 180 个叶单元作了局部更正。没有改运行脚本、源码或合同，也没有动态重试。

精确下一项是定位外层 launch/tool-session 的终止和退出留证丢失：需要能把信号来源、watchdog/worker 生命周期、终态文件写入及真实 whole 连接起来。此因仍未知，本回应不提出猜测性源码修复。F 不合格意味着当前 C、任何重试和 E 恢复均不运行；相关动作需要新的明确授权。

机器结果和精简来源索引见 [V17 machine record](outcomes/records/v17_r9_p8_scientific_results_v1.json) 与 [V17 sources](outcomes/records/v17_r9_p8_sources/README.md)。运行源码 HEAD 为 `ddbe92264d17f1111dcb551431b3b96d26b0d167`。本轮执行了 S 和 F；F 失败后的收口仅进行静态证据整理与文档更新，没有新增测试或动态运行，也没有改数值源码、合同、activation、ABI 或 launch 脚本。
