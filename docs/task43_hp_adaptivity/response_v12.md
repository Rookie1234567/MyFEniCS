# Response V12：两次受控支持运行结束，最终两处测试断言未验证

V12 没有产生新的科学结果。授权的 S1 支持验证和一次窄恢复均已使用；恢复后仍有两个测试断言未通过。主控已关闭动态执行链：D1、P2R、P3、P4、P5 均未运行，也没有新增正式 dispatch。之后只静态修正了这两个断言；这些最终测试字节没有运行，不能记为通过。主控对两轮静态预审都漏掉确定性 fixture/断言问题负责；这些问题不归因于 ABI、数学或求解性能。没有合并许可。

本轮实际修复了四个研究入口和对应测试：补上 `Mapping` 导入；允许固定 seed8 加密必须带来的相邻单元闭包，并核对每个子单元继承自己的父阶次；从 live view 取得模态身份，先保存正常 correction 后的 primary（本次主解及其原始向量），再进入容易失败的场采样。原数组读取还核对同一个 RHS、solution 以及两种相反符号的残差，并把恢复网格索引和系数绑定到这个主解，防止散列重新计算后仍混入另一解的数据。这些改变用于防止错误放行和丢失已算数据，没有改变共享数值核心或冻结容差。

执行恢复 manifest 只显式选择 D1 或 P2R 的固定产物路径，原 V11 合同及 SHA 不改。旧 A2 已保存数组的复算已前移到实际空间构造之前并单独持久化；空间调用增加委托原函数的 BEGIN/END 观察，不改变缓存算法。上述实际空间及旧数组步骤本轮没有到达：合成 fixture 中的 FE 和残差值不能代替它们。

## 运行终态与证据边界

| 尝试 | 测试结果 | whole-watchdog 与资源 | 结论 |
|---|---|---|---|
| S1，源码 HEAD `4ab4e4e8a80fb13f4c4dde63decfe282b897567e` | 24 个参数化节点：10 passed、14 failed | 42.5156832835637 s；进程树 RSS 采样峰 284,934,144 B；worker/watchdog/launcher退出码 `1/2/2`；task swap 0，清理完成 | 失败来自两个 fixture 问题：observer 向量 `copy` 的源/目标方向与 PETSc 语义相反，以及 orders JSON fixture 未创建。不是 ABI、数值或性能结果 |
| 一次窄恢复，源码 HEAD `14f94a7491c6545c6280ac2a67629e9941a38317` | 14 个节点：12 passed、2 failed | 7.066758690867573 s；进程树 RSS 采样峰 265,719,808 B；worker/watchdog/launcher退出码 `1/2/2`；task swap 0，清理完成 | 两个失败分别是 NumPy 不同形状数组使用 `!=`，以及 `pytest.raises` 正则与实际拒绝信息不匹配；真实比较和拒绝路径已运行，但相应 selector 未通过 |
| 两处最终静态修正 | 未运行 | 不适用 | 将数组断言改为 `np.array_equal`，并使正则匹配实际 `root-verified successful attempt` 错误。没有pytest、native import、driver或科学链验证最终字节 |

两轮合计 whole-watchdog 为 `49.582441974431276 s`。每轮都是一个受监控 worker；watchdog 是其直接父进程，`strace -D` tracer 也由 watchdog 管理，launcher 在外层。worker/watchdog/launcher 的退出码分别为 `1/2/2`，这不是进程数量。CPU 观察为 1、task swap 为 0，进程清理完整。S1 有 57 次 affinity getter、0 setter 和 4 个 `SIGCHLD`，其中一条来自预设 exit-7 fixture；窄恢复有 19 次 getter、0 setter、0 signal。主控审阅的 trace、资源行和 runtime identity 未发现额外硬失败。这些受控支持记录只说明测试执行环境和 fixture 路径，不证明模型数值资格或 D1 性能。逐轮终态见 [S1 root closeout](outcomes/records/v12_recovery_sources/support/focused_attempt1/root_closeout.json) 与[窄恢复 root closeout](outcomes/records/v12_recovery_sources/support/focused_recovery1/root_closeout.json)。机器汇总见[V12 recovery/science record](outcomes/records/v12_recovery_and_scientific_results_v1.json)。

## 静态/准备阶段的局部失败账

以下事件发生在静态准备、读取或检查命令中，均不计为 driver 或动态槽。已测三项静态动作耗时分别为 `0.9796270658262074 s`、`6.468700077850372 s` 和 `0.08011862775310874 s`，小计 `7.528445771429688 s`；其余编辑/读审与本次最终文档检查耗时 `NOT_MEASURED`，不补造总 wall。修正后的两次实际 dispatch 均有干净的 launch source 状态，`source_status` 为空。较早的 `initial_identity.json` 在 fetch 完成、冻结快照之前记录了本轮 agent 的 round1 修改与 root 摘录，与其中“only excerpt”的备注不完全一致；它不是干净 dispatch 快照，不能代替后两份 launch 身份。

| 局部事件 | 实际结果与处理 |
|---|---|
| initial identity 网络探测 | `ls-remote` 因 DNS 以 128 退出；主控误将 fetch 与探测并行，fetch 随后成功。该初始身份材料是在 fetch 后、最终冻结前形成，按上文保留其非 clean 状态。 |
| agent 裸 `python` | 命令以 127 退出，没有执行 Python 代码；不构成代码运行或测试。 |
| P2 路径读取 | `head` 读取旧 P2 路径时以 1 退出，随后用有效路径和记录核对；不将其描述为读错 HEAD，也不改写旧证据。 |
| 静态 `rg` 路径 | 对错误的 `dyadic_hexa_forest` 路径的一次 `rg` 以 2 退出，随后沿真实路径补查。 |
| S1 worker log | 首次读取用了错误的 tail 路径一次，随后改读 `watchdog/worker.log`；没有因此重跑。 |
| Ruff 定位 | 恢复准备中的裸 `ruff` 不可达（`FileNotFoundError`），随后用 `.venv/bin/ruff` 完成静态检查；一次 `ls ~/.local/bin/ruff` 以 2 退出，路径不存在。 |
| P5 fixture 只读定位 | root 首次对遗漏 `artifacts/` 层的路径执行一次 `rg`，以 2 退出；随后改正并完成静态阅读。 |

最终测试文件静态检查另耗时 `0.14229252189397812 s`；截至此项的已测静态小计为 `7.670738293323666 s`，编辑、读审和最终文档检查仍为 `NOT_MEASURED`。最终未运行测试文件SHA256为 `451f0a71d84b5bc7df28e79124d2f4e9022c7d69b541d03517538ca7e6e743ae`，两处静态修改diff SHA256为 `fdec9915a932adfb3f5c9239e2909c0a2b412b74aea6919ab27aec612921ac19`。最终字节的stdlib AST、Ruff `F821/F822/F823` 与 diff check 通过；这只是静态检查，pytest仍为 `NOT_RUN`。记录见[最终未运行字节静态检查](outcomes/records/v12_recovery_sources/preparation/final_unrun_static_check.json)和[两断言diff](outcomes/records/v12_recovery_sources/preparation/final_unrun_test_assertions.diff)。这些局部失败均按原样登记；它们与两轮 driver 终态分账，也不改变 pytest 节点的通过/失败数。

## V11 review §9 的逐项收口

| 项 | V12 证据与结论 |
|---|---|
| V11-01：旧 `Mapping` 调用兼容 | S1 中真实 main/audit 路径的旧 no-seed 调用通过；不是 common-points selector 对此项的证明，也不外推为所有最终字节已通过。 |
| V11-02：真实 builder、必要闭包与后置 gate | S1 的 seed、main sentinel 和 common-points节点通过；闭包/额外请求和 FE 边界进入真实计划与审计路径。仍受整轮失败及后续源码变动的验证边界约束。 |
| V11-03：真实 observer 保存顺序与故障隔离 | 窄恢复四个 observer 场景通过：A1/P4 正常、raw 门拒绝、q10 后处理失败均走实际 `_run_impl` observer。失败路径保留 primary；raw 失败不生成 q8/q10，q10 失败保留 q8 且没有 q10。 |
| V11-04：联合恢复身份和数组绑定 | 窄恢复四个真实 reader 场景通过，包括合法包及 source identity、系数、恢复索引混包拒绝。 |
| V11-05：P5 首读绑定和前后输入快照 | terminal 首读漂移、输入漂移、q10 故障和 ledger marker 故障四个负向节点通过。成功节点的 synthetic compare 已返回，但在数组断言失败；之后joined-key、首尾快照相等、验证次数和文件断言均为 `NOT_REACHED`。主控只读看到该fixture的input start=end且q8/q10文件存在，不替代未到达的pytest断言。 |
| V11-06：真实 `compare_v11_union` fixture | synthetic结果为 `COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE`，`official_result=false`、sampling sensitivity unresolved，未写selection transition。引用Y6_1，FE计数为Y6_1=1、R9=1、R9_H8=2（ΔFE=1）。q10得到`POSITIVE_FIXED_REFERENCE_OUTPUT_RESPONSE`：ΔG=+5e−6、ΔJ=+0.5；q8得到`NEGATIVE_OR_TRADEOFF_RESPONSE`：ΔG=−1e−5、ΔJ=−1.0，两种分类相冲突。该synthetic路径在比较器返回后被数组断言终止，整体selector失败；没有正式端点或PDE比较。 |
| V11-07：D1 薄观察与缓存委托 | S1 中 wrapper 的原函数委托、缓存命中、异常保留和别名恢复测试通过。D1 本身没有运行，故没有实际阶段性能、CPU归因或缓存行为结论。 |
| V11-08：trace/资源及历史证据 | 两轮 closeout、完整 trace 事件/栈帧摘录、资源采样和历史 excerpt 保留；主控完成只读复核。该证据不补成数值或性能资格。 |

S1 的失败 fixture 修复后，窄恢复只针对登记的 14 个节点；没有完整 V12 focused suite 在同一最终源码字节下通过。两处最终静态修正后的精确剩余动态验证对象为 `test_compare_v11_union_reads_bound_p2_p4_inputs_and_preserves_q8[None]` 和 `test_v12_p2_joined_source_binding_rejects_root_terminal_failure`。只有取得这两个节点的新明确验证授权、实际验证通过且主控核对该门后，才可重新考虑后续科学链；本回应不授予该授权。

## 科学状态、额度与下一步

| 项目 | 当前状态 |
|---|---|
| accepted parent / 最后接受状态 | accepted9 / R9；R10 仍拒绝 |
| 空间 / 选择 | `PARTIAL` / `PARTIAL` |
| 最终精度 | `NOT_PASSED` |
| 同精度全过程成本 | `NOT_ESTABLISHED` |
| 迭代能力 | `NOT_RUN / NOT_QUALIFIED`；0.7 nm 未运行 |
| 新正式计算 | 0；V11 授权的 A1_q3、R9_H8 正式槽均未使用；旧正式额度仍 5/6，末槽封存，扩展包络 5/8 |
| 支持与下游 | S1 主验证及局部恢复合计 2/2 已用；V12 新支持总计 2/4，D1/P2R 各 0/1 且当前前门不合格；D1/P2R/P3/P4/P5 均 `NOT_RUN`；无 READY、生产资格或 merge approval |

最小后续动作仅是由用户/正式审阅明确授权上表两个受影响 selector 的验证，并先核对新 launch 对最终测试字节的绑定。只有验证通过并经主控核验后，才可另行考虑是否恢复科学链；通过前不启动 D1/P2R/P3/P4/P5，不以剩余正式槽或历史支持额度代替授权。历史任务书、review、response、失败记录和初始 recovery manifest 均保留原件。
